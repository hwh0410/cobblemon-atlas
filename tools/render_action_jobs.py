#!/usr/bin/env python3
"""Render exact Manifest clips with an existing LOCAL render_portraits.py.

The original renderer remains on your Mac; this wrapper never uploads it.
No existing WebP is replaced unless --overwrite is explicitly provided.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import os
import re
import shutil
import sys
import tempfile
import time
from pathlib import Path

SAFE = re.compile(r"^[a-z0-9_-]+$")
DEFAULT_PRESET = "atlas-actions-pilot-v1"


def sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".jobs-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(value, f, ensure_ascii=False, indent=2)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def load_renderer(path):
    spec = importlib.util.spec_from_file_location("atlas_local_original_renderer", path)
    if spec is None or spec.loader is None:
        raise ValueError("Cannot import renderer: " + str(path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def channel_sampler(renderer, state):
    """Interpolate keyframes; reuse the existing MoLang interpreter for values."""
    def vec(raw, t):
        if isinstance(raw, dict):
            raw = raw.get("post", raw.get("pre", [0, 0, 0]))
        if isinstance(raw, (list, tuple)):
            v = [renderer.molang(x, t=t) for x in raw]
            return (v + [0] * 3)[:3]
        n = renderer.molang(raw, t=t)
        return [n, n, n]

    def sample(channel):
        t = state["time"]
        period = max(1e-6, state["period"])
        if state["loop"]:
            t %= period
        if not isinstance(channel, dict):
            return vec(channel, t)
        try:
            keys = sorted((float(k), k) for k in channel)
        except (TypeError, ValueError):
            return None
        if not keys:
            return None
        if len(keys) == 1 or t <= keys[0][0]:
            return vec(channel[keys[0][1]], t)
        for i in range(len(keys) - 1):
            a, b = keys[i], keys[i + 1]
            if t <= b[0]:
                va = vec(channel[a[1]], t)
                vb = vec(channel[b[1]], t)
                f = max(0.0, min(1.0, (t - a[0]) / (b[0] - a[0])))
                return [x + (y - x) * f for x, y in zip(va, vb)]
        if state["loop"] and period > keys[-1][0]:
            va = vec(channel[keys[-1][1]], t)
            vb = vec(channel[keys[0][1]], t)
            f = min(1.0, (t - keys[-1][0]) / (period - keys[-1][0]))
            return [x + (y - x) * f for x, y in zip(va, vb)]
        return vec(channel[keys[-1][1]], t)
    return sample


def inspect_frames(frames, minimum):
    import numpy as np
    from PIL import ImageChops

    first = frames[0].convert("RGBA")
    changed = []
    for frame in frames[1:]:
        diff = ImageChops.difference(first, frame.convert("RGBA"))
        changed.append(int(np.count_nonzero(np.max(np.asarray(diff), axis=2) > 10)))
    boxes = [f.convert("RGBA").getchannel("A").getbbox() for f in frames]
    boxes = [b for b in boxes if b]
    bbox = ((min(b[0] for b in boxes), min(b[1] for b in boxes),
             max(b[2] for b in boxes), max(b[3] for b in boxes)) if boxes else None)
    edges = 0
    for frame in frames:
        alpha = np.asarray(frame.convert("RGBA").getchannel("A"))
        if alpha.size:
            edges += int(sum(map(np.count_nonzero, (alpha[0, :], alpha[-1, :], alpha[:, 0], alpha[:, -1]))))
    margin = (min(bbox[0], bbox[1], first.width - bbox[2], first.height - bbox[3])
              if bbox else 0)
    return dict(changed_pixels_max=max(changed, default=0),
                n_frames=len(frames), alpha_bbox=bbox, edge_alpha_pixels=edges, min_margin_px=margin,
                motion_pass=max(changed, default=0) >= minimum,
                visible=bool(bbox))


def adjust_fixed_camera(info, bbox, size):
    """Conservative zoom-out and re-center after an edge-touching pilot render."""
    if not bbox:
        return
    shift_unit = size * 11.25 / 25.0
    cx = (bbox[0] + bbox[2]) / 2
    cy = (bbox[1] + bbox[3]) / 2
    tr = list(info.get("profileTranslation") or [0, 0, 0])
    while len(tr) < 3:
        tr.append(0)
    tr[0] -= .8 * (cx - size / 2) / shift_unit
    tr[1] -= .8 * (cy - size / 2) / shift_unit
    info["profileTranslation"] = tr
    # Stronger zoom-out is needed for wide wings/turning bodies (notably Lugia).
    # Each trial still keeps the whole animation on one fixed camera.
    info["profileScale"] = float(info.get("profileScale") or 1.0) * .80


def choose_actions(entries, forms, requested):
    """Resolve duplicate clip versions by motion evidence, retaining explicit hashed IDs."""
    chosen = {}
    for entry in entries:
        form = entry["form_id"]
        if form not in forms:
            continue
        for token in requested:
            explicit = [a for a in entry["actions"] if a["id"] == token]
            if explicit and re.search(r"_[0-9a-f]{8}$", token):
                candidates = explicit
                output_id = token
            else:
                candidates = [a for a in entry["actions"] if
                              a["clip_key"] == token or
                              a["clip_key"].rsplit(".", 1)[-1] == token]
                if not candidates:
                    candidates = explicit
                output_id = token.rsplit(".", 1)[-1]
            if not candidates:
                continue
            best = max(candidates, key=lambda a: (
                a.get("model_bones_matched", 0) > 0,
                a.get("model_bones_matched", 0),
                a.get("dynamic_bones", 0),
                a.get("evidence") == "candidate",
                a.get("source_pack") == "merged_pack",
                a.get("clip_sha256", "")))
            chosen[(form, output_id)] = (entry, best, output_id)
    return list(chosen.values())


def ranked_poser_paths(paths, form):
    """Prefer the precise non-Mega poser before similarly named form variants.

    The file list is not a priority list: alphabetical ordering can put
    megarayquaza.json ahead of rayquaza.json for normal Rayquaza.
    """
    species = form.split("_", 1)[-1].lower()
    base = species.removesuffix("_mega")
    def score(rel):
        stem = Path(rel).stem.lower()
        if stem == species:
            return (0, stem, rel)
        if stem == base:
            return (1, stem, rel)
        if species.endswith("_mega") and "mega" in stem:
            return (2, stem, rel)
        if "mega" not in species and "mega" in stem:
            return (5, stem, rel)
        return (3, stem, rel)
    return sorted(paths, key=score)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--repo", type=Path, required=True, help="Local cobblemon-bedrock root")
    p.add_argument("--renderer", type=Path, help="Local tools/render_portraits.py")
    p.add_argument("--manifest", type=Path, required=True)
    p.add_argument("--forms", nargs="+", required=True)
    p.add_argument("--actions", nargs="+", required=True, help="Action IDs or exact clip keys")
    p.add_argument("--out", type=Path, help="Dedicated local output folder")
    p.add_argument("--sync-root", type=Path, help="Mounted Drive folder with renders/ and checkpoints/; mirror each completed job")
    p.add_argument("--fps", type=int, default=12)
    p.add_argument("--seconds", type=float, default=2)
    p.add_argument("--size", type=int, default=224)
    p.add_argument("--ss", type=int, default=2)
    p.add_argument("--quality", type=int, default=90)
    p.add_argument("--min-motion-pixels", type=int, default=12)
    p.add_argument("--frame-padding", type=int, default=6, help="Minimum clear pixels on all sides")
    p.add_argument("--auto-frame-attempts", type=int, default=8, help="Max fixed-camera framing passes")
    p.add_argument("--overwrite", action="store_true", help="Explicitly replace action outputs")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args(argv)
    if not (1 <= args.fps <= 30 and .1 <= args.seconds <= 10 and 64 <= args.size <= 1024 and 1 <= args.ss <= 4 and 1 <= args.quality <= 100 and 0 <= args.frame_padding <= 32 and 1 <= args.auto_frame_attempts <= 8):
        p.error("fps/seconds/size/ss/quality out of range")
    repo = args.repo.expanduser().resolve()
    renderer_path = (args.renderer or repo / "tools/render_portraits.py").expanduser().resolve()
    index = json.loads(args.manifest.expanduser().read_text(encoding="utf-8"))
    chosen = choose_actions(index.get("entries", []), set(args.forms), args.actions)
    if not chosen:
        p.error("No matching form/action pairs in Manifest")
    out_dir = (args.out or repo / "captures/atlas_action_pilot").expanduser().resolve()
    legacy_root = (repo / "mega-showdown/assets/pokemon-animated").resolve()
    if out_dir == legacy_root or legacy_root in out_dir.parents:
        p.error("Cannot write to legacy pokemon-animated directory")
    sync_root = args.sync_root.expanduser().resolve() if args.sync_root else None
    if sync_root and (sync_root == legacy_root or legacy_root in sync_root.parents):
        p.error("Cannot sync into the legacy WebP folder")
    for entry, action, output_id in chosen:
        print(f"{entry['form_id']}: {output_id} ({action['clip_key']}) | {action['source_pack']} | {action['evidence']} | manifest_id={action['id']}")
    if args.dry_run:
        return 0
    if not renderer_path.is_file():
        p.error("Missing local renderer: " + str(renderer_path))
    renderer = load_renderer(renderer_path)
    from PIL import Image
    if not hasattr(renderer, "render_species"):
        p.error("Renderer lacks render_species")
    # Explicit root mapping; the Manifest's relative paths are never URL-fetched.
    pack_roots = {
        "merged_pack": repo / "merged_pack",
        "development_resource_packs": repo / "development_resource_packs",
    }
    result_file = out_dir / "render-jobs.json"
    if sync_root and not result_file.exists():
        checkpoint = sync_root / "checkpoints/render-jobs.json"
        if checkpoint.is_file():
            result_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(checkpoint, result_file)
    results = json.loads(result_file.read_text(encoding="utf-8")) if result_file.exists() else {"schema_version": 1, "jobs": {}}
    out_dir.mkdir(parents=True, exist_ok=True)
    errors = 0
    for entry, action, output_id in chosen:
        form, aid = entry["form_id"], output_id
        if not SAFE.fullmatch(form) or not SAFE.fullmatch(aid):
            print("SKIP unsafe ID", form, aid)
            errors += 1
            continue
        source_root = pack_roots.get(action["source_pack"])
        relative = Path(action["animation_path"])
        if source_root is None or relative.is_absolute() or ".." in relative.parts:
            print("SKIP invalid source", form, aid)
            errors += 1
            continue
        source = source_root / relative
        preset = dict(fps=args.fps, seconds=args.seconds, size=args.size, ss=args.ss, quality=args.quality,
                      frame="cobblemon-adaptive-v2", padding=args.frame_padding,
                      passes=args.auto_frame_attempts, source_sha=action["animation_sha256"], job=action["render_job_key"],
                      renderer_sha=hashlib.sha256(renderer_path.read_bytes()).hexdigest())
        job_key = sha(json.dumps(preset, sort_keys=True))
        job_id = f"{form}/{aid}"
        dest = out_dir / form / (aid + ".webp")
        previous = results["jobs"].get(job_id, {})
        if sync_root and not dest.exists() and previous.get("status") == "ready" and previous.get("job_key") == job_key:
            remote = sync_root / "renders" / form / (aid + ".webp")
            if remote.is_file():
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(remote, dest)
        if dest.exists() and not args.overwrite:
            if previous.get("job_key") == job_key and previous.get("status") == "ready":
                print("RESUME already ready:", dest)
            else:
                print("PROTECTED existing output differs from current job; use a separate --out or explicitly --overwrite:", dest)
                errors += 1
            continue
        try:
            if not source.is_file():
                raise FileNotFoundError(source)
            if hashlib.sha256(source.read_bytes()).hexdigest() != action["animation_sha256"]:
                raise ValueError("Animation source changed; rescan Manifest first")
            entity = repo / "development_resource_packs/cobblemon/entity" / (form + ".entity.json")
            if not entity.is_file():
                raise FileNotFoundError("Missing prepared entity: " + str(entity))
            clip = renderer.load_json(str(source)).get("animations", {}).get(action["clip_key"])
            if not isinstance(clip, dict):
                raise ValueError("Exact clip_key missing from selected source")
            state = {"time": 0.0, "period": float(clip.get("animation_length") or args.seconds),
                     "loop": clip.get("loop", True) is not False}
            if not math.isfinite(state["period"]) or state["period"] <= 0:
                state["period"] = args.seconds
            renderer.channel_at_zero = channel_sampler(renderer, state)
            old_find = renderer.find_animations
            info = old_find(form, form.split("_", 1)[-1])
            info["clips"] = [(action["clip_key"], clip)]
            # Recover any same-pack poser metadata for fixed camera framing.
            for rel in ranked_poser_paths(action.get("poser_paths", []), form):
                poser_file = source_root / rel
                if poser_file.is_file():
                    poser = renderer.load_json(str(poser_file))
                    info["profileScale"] = poser.get("profileScale", info.get("profileScale") or 1.0)
                    info["profileTranslation"] = poser.get("profileTranslation", info.get("profileTranslation") or [0, 0, 0])
                    info["poser"] = str(poser_file)
                    break
            info["profileScale"] = info.get("profileScale") or 1.0
            renderer.find_animations = lambda folder, species, fixed=info: fixed
            frames = []
            started = time.monotonic()
            count = max(2, round(args.fps * args.seconds))
            try:
                for attempt in range(1, args.auto_frame_attempts + 1):
                    frames = []
                    for frame_no in range(count):
                        state["time"] = (frame_no / (count if state["loop"] else max(1, count - 1))) * state["period"]
                        im, _ = renderer.render_species(form, size=args.size, ss=args.ss, frame="cobblemon")
                        frames.append(im.convert("RGBA"))
                    stats = inspect_frames(frames, args.min_motion_pixels)
                    print(f"  framing {attempt}/{args.auto_frame_attempts}: bbox={stats['alpha_bbox']} margin={stats['min_margin_px']} motion={stats['changed_pixels_max']}", flush=True)
                    if not stats["visible"] or not stats["motion_pass"] or stats["min_margin_px"] >= args.frame_padding:
                        break
                    if attempt < args.auto_frame_attempts:
                        adjust_fixed_camera(info, stats["alpha_bbox"], args.size)
            finally:
                renderer.find_animations = old_find
            stats["framing_attempts"] = attempt
            stats["final_profile_scale"] = info["profileScale"]
            stats["final_profile_translation"] = info.get("profileTranslation")
            if not stats["visible"] or not stats["motion_pass"]:
                status = "static" if stats["visible"] else "failed"
                reason = "no_visible_frame_motion" if stats["visible"] else "empty_render"
            elif stats["min_margin_px"] < args.frame_padding:
                status, reason = "failed", "touches_canvas_edge_review_crop"
            else:
                dest.parent.mkdir(parents=True, exist_ok=True)
                temp = dest.with_suffix(".tmp.webp")
                try:
                    frames[0].save(temp, format="WEBP", save_all=True, append_images=frames[1:],
                                   duration=round(1000 / args.fps), loop=0 if state["loop"] else 1,
                                   quality=args.quality, method=5)
                    with Image.open(temp) as verify:
                        decoded = verify.n_frames
                        decoded_frames = []
                        for frame_no in range(decoded):
                            verify.seek(frame_no)
                            decoded_frames.append(verify.convert("RGBA").copy())
                        verify.seek(decoded - 1)
                        verify.load()
                    if decoded < 2:
                        raise ValueError("WebP decode returned fewer than two frames")
                    decoded_stats = inspect_frames(decoded_frames, args.min_motion_pixels)
                    if not decoded_stats["motion_pass"]:
                        raise ValueError("WebP decoded frames lost visible motion")
                    if not decoded_stats["visible"]:
                        raise ValueError("WebP decoded frames are invisible")
                    stats["decoded_frames"] = decoded
                    stats["decoded_changed_pixels_max"] = decoded_stats["changed_pixels_max"]
                    os.replace(temp, dest)
                    status, reason = "ready", None
                finally:
                    if temp.exists():
                        temp.unlink()
            record = dict(status=status, reason=reason, file=str(dest) if status == "ready" else None,
                          bytes=dest.stat().st_size if status == "ready" else None,
                          job_key=job_key, clip_key=action["clip_key"], source_pack=action["source_pack"],
                          elapsed_sec=round(time.monotonic() - started, 2), **stats)
            print(status.upper(), job_id, stats["changed_pixels_max"], "pixels", flush=True)
        except Exception as exc:
            record = dict(status="failed", reason=f"{type(exc).__name__}: {exc}", job_key=job_key)
            print("FAILED", job_id, record["reason"], flush=True)
        results["jobs"][job_id] = record
        atomic_json(result_file, results)
        if sync_root:
            try:
                if record["status"] == "ready":
                    target = sync_root / "renders" / form / (aid + ".webp")
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(dest, target)
                atomic_json(sync_root / "checkpoints/render-jobs.json", results)
                print("SYNCED Drive:", job_id, record["status"], flush=True)
            except (OSError, ValueError) as exc:
                print("DRIVE SYNC FAILED:", job_id, exc, flush=True)
                errors += 1
        if record["status"] != "ready":
            errors += 1
    print("Report:", result_file)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
