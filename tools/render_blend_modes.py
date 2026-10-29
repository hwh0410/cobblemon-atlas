#!/usr/bin/env python3
"""Compare additive vs per-channel override motion on Resolver Rayquaza.

Outputs only review candidates, never writes formal renders or site assets.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image

from compare_pose_layers import sample_contact
from render_action_jobs import adjust_fixed_camera, channel_sampler, inspect_frames
from render_layered_pilot import prepare, overlay_difference
from render_resolved_forms import extract_clips

OVERLAYS = ["animation.rayquaza.cry", "animation.rayquaza.physical_attack",
            "animation.rayquaza.special_attack"]


def collect_override(renderer, info):
    """Last clip wins per bone/channel, leaving untouched base channels intact.

    Bedrock clips are treated as absolute channel targets, not as additive
    deltas. The parent pose still contributes all channels the action omits.
    """
    result = {}
    for _, clip in info["clips"]:
        for bone, channels in clip.get("bones", {}).items():
            row = result.setdefault(bone.casefold(), {})
            for name in ("rotation", "position", "scale"):
                if name in channels:
                    value = renderer.channel_at_zero(channels[name])
                    if value is not None:
                        row[name] = value
    return result


def bbox_area(stats):
    b = stats.get("alpha_bbox")
    return max(0, b[2]-b[0]) * max(0, b[3]-b[1]) if b else 0


def run_modes(repo, resolved, output):
    form = "0384_rayquaza"
    selected = next((r["selected"] for r in resolved["forms"]
                     if r["form_id"] == form and r.get("status") == "resolved"), None)
    if not selected:
        raise RuntimeError("Normal Rayquaza Resolver assets not resolved")
    renderer, poser, geo, info, clips = prepare(repo, form, selected)
    base, skipped = extract_clips(poser["poses"]["standing"], clips)
    if not base:
        raise RuntimeError("Missing base standing clip")
    original_collect = renderer.collect_anim
    state = {"time": 0.0, "period": 2.0, "loop": True}
    renderer.channel_at_zero = channel_sampler(renderer, state)
    dest = output / form
    dest.mkdir(parents=True, exist_ok=True)
    report = {"schema_version": 1, "purpose": "blend_review_not_published",
              "form_id": form, "base_clips": base, "skipped_base_expressions": skipped,
              "model": selected["model"], "trials": {}}
    for overlay in OVERLAYS:
        label = overlay.rsplit(".", 1)[-1]
        if overlay not in clips:
            report["trials"][label] = {"status": "audit", "reason": "missing_overlay"}
            continue
        skeleton = {str(b.get("name", "")).casefold() for b in geo["bones"]}
        unknown = [b for b in clips[overlay].get("bones", {}) if b.casefold() not in skeleton]
        if unknown:
            report["trials"][label] = {"status": "audit", "reason": "unmatched_bones",
                                        "unmatched_bones": unknown}
            continue
        info["profileScale"] = float(poser.get("profileScale") or 1.0)
        info["profileTranslation"] = list(poser.get("profileTranslation") or [0, 0, 0])
        modes = {
            "base": (base, "original"),
            "action_only": ([overlay], "original"),
            "additive": (base + [overlay], "original"),
            "override": (base + [overlay], "override"),
        }
        try:
            for attempt in range(1, 9):
                renders = {}
                for mode, (keys, strategy) in modes.items():
                    info["clips"] = [(k, clips[k]) for k in keys]
                    if strategy == "override":
                        renderer.collect_anim = lambda _info, m=renderer: collect_override(m, _info)
                    else:
                        renderer.collect_anim = original_collect
                    frames = []
                    for i in range(24):
                        state["time"] = i / 12.0
                        frame, _ = renderer.render_species(form, size=224, ss=2, frame="cobblemon")
                        frames.append(frame.convert("RGBA"))
                    renders[mode] = frames
                global_stats = inspect_frames([img for sequence in renders.values() for img in sequence], 12)
                if not global_stats["visible"] or global_stats["min_margin_px"] >= 6:
                    break
                if attempt < 8:
                    adjust_fixed_camera(info, global_stats["alpha_bbox"], 224)
        finally:
            renderer.collect_anim = original_collect
        records = {}
        baseline = renders["base"]
        base_stats = inspect_frames(baseline, 12)
        for mode, frames in renders.items():
            stats = inspect_frames(frames, 12)
            delta, _ = overlay_difference(baseline, frames)
            size_ratio = (round(bbox_area(stats)/bbox_area(base_stats), 3)
                          if bbox_area(base_stats) else None)
            sample_contact(frames, form+"/"+label+"/"+mode,
                           dest/(label+"_"+mode+"_contact.png"))
            records[mode] = {"changed_pixels_max": stats["changed_pixels_max"],
                             "extra_pixels_vs_base": delta,
                             "bbox": stats["alpha_bbox"],
                             "size_ratio_vs_base": size_ratio,
                             "margin_px": stats["min_margin_px"]}
        candidate = records["override"]
        # A large silhouette-area change is only a warning; never proof of bad pose.
        suspicious = (candidate["size_ratio_vs_base"] is None or
                      candidate["size_ratio_vs_base"] < .65 or
                      candidate["size_ratio_vs_base"] > 1.9)
        status = "visual_review_required"
        if (candidate["extra_pixels_vs_base"] >= 12 and
                candidate["changed_pixels_max"] >= 12 and
                candidate["margin_px"] >= 6 and not suspicious):
            out_file = dest/(label+"_override.webp")
            frames = renders["override"]
            frames[0].save(out_file, format="WEBP", save_all=True,
                           append_images=frames[1:], duration=83, loop=0, quality=90, method=5)
            with Image.open(out_file) as decoded:
                copied = []
                for i in range(decoded.n_frames):
                    decoded.seek(i)
                    copied.append(decoded.convert("RGBA").copy())
            verified = inspect_frames(copied, 12)
            if len(copied) > 1 and verified["motion_pass"]:
                status = "candidate_override_unapproved"
                candidate["file"] = out_file.name
                candidate["decoded_frames"] = len(copied)
            else:
                status = "decoded_motion_failed"
        report["trials"][label] = {"status": status, "frame_attempts": attempt,
                                    "camera_scale": info["profileScale"],
                                    "camera_translation": info["profileTranslation"],
                                    "suspicious_silhouette_change": suspicious,
                                    "approved_for_publication": False,
                                    "modes": records}
        print(label, status, "override extra pixels", candidate["extra_pixels_vs_base"],
              "silhouette ratio", candidate["size_ratio_vs_base"], flush=True)
    output.mkdir(parents=True, exist_ok=True)
    target = output / "blend-mode-comparison.json"
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print("Blend report:", target)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--resolved", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    data = json.loads(args.resolved.read_text(encoding="utf-8"))
    run_modes(args.repo.resolve(), data, args.out.resolve())


if __name__ == "__main__":
    main()
