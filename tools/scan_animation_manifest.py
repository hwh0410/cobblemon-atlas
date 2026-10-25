#!/usr/bin/env python3
"""Conservative, read-only-by-default Cobblemon animation inventory.

The scanner never renders, modifies existing WebP, or declares a clip playable.
Pass one or more extracted resource-pack roots using --pack NAME=PATH.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import sys
import tempfile
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INDEX = ROOT / "mega-showdown/data/pokemon-animated.json"
DEFAULT_OUT = ROOT / "scan-output/animation-actions.json"
CLIP_RE = re.compile(r"animation[.][\w.:-]+", re.I)
BEDROCK_RE = re.compile(r"q[.]bedrock\(\s*(['\"])(.*?)\1\s*,\s*(['\"])(.*?)\3\s*\)", re.I)
VALID = re.compile(r"^[a-z0-9_-]+$")


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def safe_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8-sig")), None
    except (OSError, ValueError, UnicodeError) as exc:
        return None, str(exc)


def atomic_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".animation-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, indent=2)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def collect(root, name):
    """Read only relevant JSON. Return exact provenance for each resource."""
    records = []
    for p in sorted(root.rglob("*.json")):
        rel = p.relative_to(root).as_posix()
        low = rel.lower()
        if not any(k in low for k in ("animation", "poser", "resolver", "geo", "bedrock", "species")):
            continue
        data, error = safe_json(p)
        records.append(dict(pack=name, root=root, path=p, relative=rel,
                            data=data, error=error, sha256=digest(p)))
    return records


def model_bones(data):
    result = set()
    if not isinstance(data, dict):
        return result
    models = data.get("minecraft:geometry", [])
    if isinstance(models, dict):
        models = [models]
    for model in models if isinstance(models, list) else []:
        if isinstance(model, dict):
            for bone in model.get("bones", []):
                if isinstance(bone, dict) and isinstance(bone.get("name"), str):
                    result.add(bone["name"].lower())
    return result


def animations(data):
    if not isinstance(data, dict):
        return {}
    clips = data.get("animations", {})
    return clips if isinstance(clips, dict) else {}


def references(data):
    """Parse linked clip strings, including single/double-quoted q.bedrock args."""
    strings = []
    def visit(value):
        if isinstance(value, str):
            strings.append(value)
        elif isinstance(value, dict):
            for k, v in value.items():
                visit(k)
                visit(v)
        elif isinstance(value, list):
            for v in value:
                visit(v)
    visit(data)
    raw = "\n".join(strings)
    return set(CLIP_RE.findall(raw)), [(x[1], x[3]) for x in BEDROCK_RE.findall(raw)]


def dynamic_info(clip):
    channels = ("rotation", "position", "scale")
    bones = clip.get("bones", {}) if isinstance(clip, dict) else {}
    if not isinstance(bones, dict):
        bones = {}
    animated = set()
    conditional = False
    for name, bone in bones.items():
        if not isinstance(bone, dict):
            continue
        values = [bone[c] for c in channels if c in bone]
        raw = json.dumps(values, ensure_ascii=False)
        if any(isinstance(v, dict) and len(v) > 1 for v in values) or re.search(
            r"q[.]|query[.]|math[.]|variable[.]|\b(?:sin|cos)\s*\(", raw, re.I
        ):
            animated.add(name.lower())
        if re.search(r"\?|q[.]|query[.]|variable[.]", raw, re.I):
            conditional = True
    return animated, conditional


def classify(key):
    s = key.lower().replace("-", "_")
    terms = [
        ("blink", "expression", "眨眼"), ("sleep", "rest", "睡眠"),
        ("rest", "rest", "休息"), ("air_idle", "idle", "空中待機"),
        ("ground_idle", "idle", "地面待機"), ("idle", "idle", "待機"),
        ("fly", "move", "飛行"), ("swim", "move", "游泳"),
        ("walk", "move", "行走"), ("run", "move", "奔跑"),
        ("battle", "battle", "戰鬥"), ("attack", "battle", "攻擊"),
        ("cry", "expression", "叫聲"),
    ]
    for token, category, zh in terms:
        if token in s:
            return category, zh
    return "other", key.rsplit(".", 1)[-1]


def aliases(form):
    """Exact form first. Base species fallback is not valid for special models."""
    name = form[5:] if re.match(r"^\d{4}_", form) else form
    return {form.lower(), name.lower()}


def owned(record, names):
    # Only explicit filename/path evidence. Do not attach generic shared clips.
    stem = record["path"].stem.lower()
    parts = record["relative"].lower().split("/")
    # A base Gengar must never claim gengar_mega poser/geometry by prefix.
    return any(n == stem or n in parts or stem == n + ".geo" or
               stem == n + ".poser" or stem == n + ".resolver"
               for n in names)


def action_id(clip_key, used):
    base = re.sub(r"[^a-z0-9_-]+", "_", clip_key.lower().split(".")[-1]).strip("_") or "clip"
    value = base
    if value in used:
        value = base + "_" + hashlib.sha256(clip_key.encode()).hexdigest()[:8]
    used.add(value)
    return value


def scan_form(form, records, clip_catalog):
    name = form["id"]
    names = aliases(name)
    relevant = [r for r in records if owned(r, names)]
    geometries = [(r, model_bones(r["data"])) for r in relevant]
    geometries = [(r, bones) for r, bones in geometries if bones]
    posers = [r for r in relevant if "poser" in r["relative"].lower()]
    resolvers = [r for r in relevant if "resolver" in r["relative"].lower()]
    # Animation JSON may live in a generic path. Discover by exact clip namespace,
    # but require the form to be named in the key or referenced by a form poser.
    form_refs = set()
    bedrock_refs = []
    for r in posers + resolvers:
        refs, calls = references(r["data"])
        form_refs.update(refs)
        bedrock_refs.extend(calls)
    clip_candidates = []
    linked_keys = form_refs
    for name_part in names:
        clip_candidates.extend((key, clip, r, True, key in linked_keys)
                               for key, clip, r in clip_catalog.get("prefix", {}).get(name_part, []))
    for key in linked_keys:
        clip_candidates.extend((key, clip, r, False, True)
                               for clip, r in clip_catalog.get("key", {}).get(key, []))
    # A clip found both by explicit namespace and poser reference is one source.
    clip_candidates = list({(key, r["pack"], r["relative"]): (key, clip, r, specific, linked)
                            for key, clip, r, specific, linked in clip_candidates}.values())
    # Multiple clips with the same name are source conflicts, never silently merged.
    by_key = defaultdict(list)
    for candidate in clip_candidates:
        by_key[candidate[0]].append(candidate)
    used = set()
    actions = []
    model_pack_bones = defaultdict(set)
    for geo, bones in geometries:
        model_pack_bones[geo["pack"]].update(bones)
    for key in sorted(by_key):
        candidates = sorted(by_key[key], key=lambda c: (c[2]["pack"], c[2]["relative"]))
        conflict = len({c[2]["sha256"] for c in candidates}) > 1
        for i, (clip_key, clip, source, specific, linked) in enumerate(candidates):
            moving, conditional = dynamic_info(clip)
            matching = moving & model_pack_bones[source["pack"]]
            category, label = classify(clip_key)
            aid = action_id(key if i == 0 else key + "_" + source["pack"] + str(i), used)
            duration = clip.get("animation_length") if isinstance(clip, dict) else None
            loop = clip.get("loop") if isinstance(clip, dict) else None
            if isinstance(loop, str):
                loop = loop.lower() in ("true", "hold_on_last_frame")
            same_pack_geo = [r for r, bones in geometries if r["pack"] == source["pack"]]
            # Even 100% bone overlap cannot certify a renderable animation.
            reasons = []
            if not same_pack_geo:
                reasons.append("missing_same_pack_geometry")
            if not matching:
                reasons.append("no_matching_dynamic_bones")
            if conflict:
                reasons.append("duplicate_clip_key_conflict")
            if conditional:
                reasons.append("conditional_or_molang_needs_render_check")
            if not posers:
                reasons.append("poser_not_resolved")
            confidence = "candidate" if matching and same_pack_geo and posers and not conflict else "audit"
            actions.append(dict(id=aid, clip_key=clip_key, label_zh=label,
                                category=category, status="pending", file=None, bytes=None,
                                source_pack=source["pack"], animation_path=source["relative"],
                                animation_sha256=source["sha256"], poser_paths=[r["relative"] for r in posers],
                                resolver_paths=[r["relative"] for r in resolvers],
                                geometry_paths=[r["relative"] for r in same_pack_geo],
                                duration_sec=duration if isinstance(duration, (int, float)) else None,
                                loop=loop if isinstance(loop, bool) else None,
                                dynamic_bones=len(moving), model_bones_matched=len(matching),
                                conditional=conditional, conflict=conflict, evidence=confidence,
                                reason=reasons, render_job_key=hashlib.sha256(
                                    (name + clip_key + source["sha256"] + "|" + "|".join(
                                        sorted(x["sha256"] for x in same_pack_geo + posers)
                                    ) + "|preset-v1").encode()).hexdigest()))
    choices = [a for a in actions if a["evidence"] == "candidate" and a["category"] == "idle"]
    choices.sort(key=lambda a: (a["conditional"], -a["model_bones_matched"], a["id"]))
    return dict(form_id=name, pokemon_id=form["pokemon_id"], model_id=name,
                display_name=form.get("form", name), kind=form.get("kind"),
                default_image="mega-showdown/" + form["image_path"],
                default_action_id=choices[0]["id"] if choices else None,
                resources=dict(geometry=[r["relative"] for r, _ in geometries],
                               poser=[r["relative"] for r in posers],
                               resolver=[r["relative"] for r in resolvers],
                               bedrock_calls=bedrock_refs), actions=actions)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pack", action="append", default=[], metavar="NAME=DIR",
                        help="Extracted resource pack; repeat for each source")
    parser.add_argument("--index", type=Path, default=DEFAULT_INDEX)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--forms", nargs="+", help="Exact IDs such as 0094_gengar")
    parser.add_argument("--all", action="store_true", help="Scan every indexed form")
    parser.add_argument("--dry-run", action="store_true", help="No output files")
    parser.add_argument("--resume", action="store_true", help="Reuse entries with unchanged input fingerprint")
    parser.add_argument("--publish", action="store_true", help="Explicitly output to website data path")
    args = parser.parse_args(argv)
    if not args.pack:
        parser.error("at least one --pack NAME=DIR is required (source files are not in GitHub)")
    packs = []
    for spec in args.pack:
        if "=" not in spec:
            parser.error("--pack must be NAME=DIR")
        name, raw = spec.split("=", 1)
        path = Path(raw).expanduser().resolve()
        if not name or not VALID.fullmatch(name) or not path.is_dir():
            parser.error("invalid pack name or directory: " + spec)
        packs.append((name, path))
    if len(set(n for n, _ in packs)) != len(packs):
        parser.error("pack names must be unique")
    index, error = safe_json(args.index)
    if error or not isinstance(index, list):
        parser.error("invalid website index: " + str(error))
    selected = set(args.forms or [])
    forms = [f for f in index if not selected or f["id"] in selected]
    if selected - {f["id"] for f in forms}:
        parser.error("unknown form ID(s): " + ", ".join(sorted(selected - {f["id"] for f in forms})))
    if args.publish:
        args.output = ROOT / "mega-showdown/data/animation-actions.json"
    elif args.output.resolve() == (ROOT / "mega-showdown/data/animation-actions.json").resolve():
        parser.error("site manifest requires explicit --publish")
    old = {}
    if args.resume and args.output.is_file():
        prior, err = safe_json(args.output)
        if not err and isinstance(prior, dict):
            old = {e["form_id"]: e for e in prior.get("entries", [])}
    records = []
    for name, path in packs:
        records.extend(collect(path, name))
    clip_catalog = {"prefix": defaultdict(list), "key": defaultdict(list)}
    for r in records:
        for key, clip in animations(r["data"]).items():
            clip_catalog["key"][key].append((clip, r))
            pieces = key.lower().split(".")
            if len(pieces) >= 3 and pieces[0] == "animation":
                clip_catalog["prefix"][pieces[1]].append((key, clip, r))
    # All resource hashes are included: any changed file invalidates cached results.
    source_version = hashlib.sha256("\n".join(
        f"{r['pack']}:{r['relative']}:{r['sha256']}" for r in sorted(records, key=lambda r: (r["pack"], r["relative"]))
    ).encode()).hexdigest()
    index_hash = digest(args.index)
    fingerprint = hashlib.sha256((source_version + index_hash).encode()).hexdigest()
    entries = []
    reused = 0
    for f in forms:
        if old.get(f["id"], {}).get("scan_fingerprint") == fingerprint:
            entries.append(old[f["id"]]); reused += 1
        else:
            entry = scan_form(f, records, clip_catalog)
            entry["scan_fingerprint"] = fingerprint
            entries.append(entry)
    summary = dict(forms=len(entries), forms_with_actions=sum(bool(e["actions"]) for e in entries),
                   actions=sum(len(e["actions"]) for e in entries),
                   conflicts=sum(a["conflict"] for e in entries for a in e["actions"]),
                   missing_geometry=sum(not e["resources"]["geometry"] for e in entries),
                   no_matched_dynamic_bones=sum(not a["model_bones_matched"] for e in entries for a in e["actions"]),
                   parse_errors=[f"{r['pack']}:{r['relative']}: {r['error']}" for r in records if r["error"]],
                   resumed_forms=reused)
    result = dict(schema_version=1, generated_at=datetime.now(timezone.utc).isoformat(),
                  source_version=source_version, source_packs=[n for n, _ in packs],
                  entries=entries, summary=summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if args.dry_run:
        print("DRY RUN: no files written")
        return 0
    atomic_json(args.output, result)
    report = args.output.with_suffix(".csv")
    fd, tmp = tempfile.mkstemp(prefix=".actions-", suffix=".tmp", dir=report.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(["form_id", "clip_key", "action_id", "source_pack", "evidence", "status", "dynamic_bones", "matched_bones", "conflict", "reason"])
            for e in entries:
                for a in e["actions"]:
                    w.writerow([e["form_id"], a["clip_key"], a["id"], a["source_pack"], a["evidence"], a["status"], a["dynamic_bones"], a["model_bones_matched"], a["conflict"], ";".join(a["reason"])])
        os.replace(tmp, report)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    print("Wrote:", args.output, report, sep="\n  ")
    return 0


if __name__ == "__main__":
    sys.exit(main())
