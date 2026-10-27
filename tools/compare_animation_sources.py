#!/usr/bin/env python3
"""Compare animation clips in two existing source ZIPs without extracting them.

Read-only: reports candidate temporal evidence and bone compatibility; no
clip is approved for animation output based on this inventory alone.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import zipfile
from collections import defaultdict
from pathlib import Path

TIME_EXPRESSION = re.compile(r"(?:q|query)\.(?:anim_time|life_time|age|time)|(?:v|variable)\.anim_time", re.I)
POSE_CALL = re.compile(r"q\.bedrock(?:_stateful|_quirk)?\(\s*['\"]([^'\"]+)['\"]\s*,\s*['\"]([^'\"]+)['\"]", re.I)
PACK_DIRS = {
    "merged_pack": "bedrock/pokemon/animations",
    "development_resource_packs": "cobblemon/animations",
}


def folder_for(form):
    return "_".join(form.split("_")[:2])


def sha(data):
    return hashlib.sha256(json.dumps(data, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def clip_features(clip, geometry_bones):
    bones = clip.get("bones", {})
    if not isinstance(bones, dict):
        bones = {}
    matched = []
    unmatched = []
    keyframes = 0
    changing_keyframes = 0
    time_expressions = 0
    other_expressions = 0
    for bone, channels in bones.items():
        (matched if bone.casefold() in geometry_bones else unmatched).append(bone)
        if not isinstance(channels, dict):
            continue
        for channel in ("position", "rotation", "scale"):
            value = channels.get(channel)
            if value is None:
                continue
            if isinstance(value, dict):
                try:
                    frames = sorted((float(t), v) for t, v in value.items())
                except (ValueError, TypeError):
                    frames = []
                if len(frames) > 1:
                    keyframes += 1
                    if len({json.dumps(v, sort_keys=True) for _, v in frames}) > 1:
                        changing_keyframes += 1
            encoded = json.dumps(value).lower()
            if TIME_EXPRESSION.search(encoded):
                time_expressions += 1
            elif "math." in encoded or "q." in encoded or "query." in encoded:
                other_expressions += 1
    # Time expressions are possible motion, not definitive without rendering.
    evidence = ("keyframes" if changing_keyframes else
                "time_expression" if time_expressions else "static_or_unproven")
    return {
        "clip_bones": len(bones), "matched_bones": len(matched),
        "unmatched_bones": unmatched[:20],
        "keyframed_channels": keyframes,
        "changing_keyframed_channels": changing_keyframes,
        "time_expression_channels": time_expressions,
        "other_expression_channels": other_expressions,
        "motion_evidence": evidence,
        "duration_sec": clip.get("animation_length"), "loop": clip.get("loop"),
    }


def read_zip_json(z, member):
    try:
        return json.loads(z.read(member).decode("utf-8-sig"))
    except KeyError:
        return None


def poser_references(z, selected):
    poser = selected.get("poser")
    if not poser:
        return set(), "resolver_poser_missing"
    data = read_zip_json(z, "merged_pack/" + poser)
    if not data:
        return set(), "resolver_poser_not_found_in_zip"
    found = set()
    # Include namedAnimations, quirks, conditions, and ordinary pose clips.
    for match in POSE_CALL.finditer(json.dumps(data, ensure_ascii=False)):
        found.add("animation." + match.group(1) + "." + match.group(2))
    return found, None


def scan_form(archives, form, resolved):
    selected = resolved.get("selected")
    if not selected:
        return {"status": "audit", "reason": resolved.get("reason")}
    known = {str(b).casefold() for b in selected.get("bone_names", [])}
    refs, poser_error = poser_references(archives["merged_pack"], selected)
    variants = defaultdict(list)
    for pack, archive in archives.items():
        prefix = f"{pack}/{PACK_DIRS[pack]}/{folder_for(form)}/"
        for member in sorted(archive.namelist()):
            if not member.startswith(prefix) or not member.endswith(".animation.json"):
                continue
            data = read_zip_json(archive, member)
            if not isinstance(data, dict):
                continue
            for key, clip in data.get("animations", {}).items():
                if not isinstance(clip, dict):
                    continue
                features = clip_features(clip, known)
                variants[key].append({"source_pack": pack, "source_path": member[len(pack) + 1:],
                                      "clip_sha256": sha(clip), "referenced_by_resolver_poser": key in refs,
                                      **features})
    indexed = {}
    for name, entries in sorted(variants.items()):
        hashes = {e["clip_sha256"] for e in entries}
        for entry in entries:
            entry["cross_pack_conflict"] = len(hashes) > 1
            entry["potential_dynamic_candidate"] = (
                entry["matched_bones"] > 0 and entry["motion_evidence"] != "static_or_unproven")
        indexed[name] = entries
    all_entries = [e for v in indexed.values() for e in v]
    promising = [dict(clip_key=k, **e) for k, v in indexed.items() for e in v
                 if e["potential_dynamic_candidate"]]
    promising.sort(key=lambda e: (-e["matched_bones"],
                                   e["motion_evidence"] != "keyframes",
                                   not e["referenced_by_resolver_poser"], e["clip_key"]))
    return {"status": "scanned", "selected_geometry": selected.get("model"),
            "selected_bones": len(known), "selected_poser": selected.get("poser"),
            "poser_read_error": poser_error, "poser_referenced_keys": sorted(refs),
            "summary": {"unique_clips": len(indexed), "source_versions": len(all_entries),
                        "potential_dynamic_versions": len(promising),
                        "same_key_different_content": sum(len({e["clip_sha256"] for e in v}) > 1
                                                          for v in indexed.values())},
            "promising_candidates": promising,
            "clips": indexed}


def scan(merged_zip, development_zip, resolved, forms):
    rows = {r["form_id"]: r for r in resolved.get("forms", [])}
    with zipfile.ZipFile(merged_zip) as merged, zipfile.ZipFile(development_zip) as development:
        archives = {"merged_pack": merged, "development_resource_packs": development}
        return {"schema_version": 1, "purpose": "source_inventory_only_not_rendered_or_approved",
                "forms": {form: scan_form(archives, form, rows.get(form, {})) for form in forms}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--merged-zip", required=True, type=Path)
    parser.add_argument("--development-zip", required=True, type=Path)
    parser.add_argument("--resolved", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--forms", nargs="+", default=["0150_mewtwo", "0384_rayquaza"])
    args = parser.parse_args()
    resolved = json.loads(args.resolved.read_text(encoding="utf-8"))
    result = scan(args.merged_zip, args.development_zip, resolved, args.forms)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    for form, info in result["forms"].items():
        print(form, info.get("status"), info.get("summary"))
        for candidate in info.get("promising_candidates", [])[:12]:
            print("  ", candidate["clip_key"], candidate["source_pack"],
                  "matched", candidate["matched_bones"],
                  "evidence", candidate["motion_evidence"],
                  "poser_ref", candidate["referenced_by_resolver_poser"])
    print("Source comparison:", args.out)


if __name__ == "__main__":
    main()
