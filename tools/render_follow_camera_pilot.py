#!/usr/bin/env python3
"""Fixed-vs-smoothed-follow framing for Resolver Rayquaza action clips.

Candidate-only, never modifies the historical portrait collection.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from PIL import Image

from compare_pose_layers import sample_contact
from render_action_jobs import adjust_fixed_camera, channel_sampler, inspect_frames
from render_layered_pilot import prepare
from render_blend_modes import collect_override

CLIPS = ["animation.rayquaza.physical_attack", "animation.rayquaza.special_attack"]
SIZE, FPS, COUNT = 224, 12, 24


def compute_target_camera(bbox, base_scale, base_translation, target_extent=154):
    """Estimate camera directly from a fully visible reference-frame bbox.

    The formulas invert the original renderer's Cobblemon profile projection.
    """
    if not bbox:
        return base_scale, list(base_translation)
    w, h = bbox[2]-bbox[0], bbox[3]-bbox[1]
    if w < 1 or h < 1:
        return base_scale, list(base_translation)
    gui = SIZE / 25.0
    cx, cy = (bbox[0]+bbox[2])/2, (bbox[1]+bbox[3])/2
    old_off_x = gui * (12.5 + 11.25 * base_translation[0])
    old_off_y = gui * (1.0 + 11.25 * (base_translation[1] + 1.5 * base_scale))
    ratio = max(0.70, min(2.40, target_extent/max(w, h)))
    scale = base_scale * ratio
    offset_x = SIZE/2 - ratio*(cx-old_off_x)
    offset_y = SIZE/2 - ratio*(cy-old_off_y)
    translation_x = (offset_x/gui - 12.5)/11.25
    translation_y = ((offset_y/gui - 1.0)/11.25 - 1.5*scale)
    return scale, [translation_x, translation_y, base_translation[2]]


def smooth_series(values, passes=2):
    """Edge-preserving smoothing for a single non-looping action sequence."""
    seq = list(values)
    if not seq:
        return []
    for _ in range(passes):
        previous = seq
        seq = [sum(weight*previous[min(max(i+offset, 0), len(previous)-1)]
                   for offset, weight in ((-2, 1), (-1, 2), (0, 3), (1, 2), (2, 1)))/9
               for i in range(len(previous))]
    return seq


def smooth_cameras(targets):
    # Log interpolation keeps zoom positive and avoids asymmetric zoom steps.
    scales = smooth_series([math.log(max(1e-6, s)) for s, _ in targets])
    axes = [smooth_series([tr[k] for _, tr in targets]) for k in range(3)]
    return [(math.exp(scales[i]), [axes[k][i] for k in range(3)])
            for i in range(len(targets))]


def render_clip(renderer, form, info, state, clip, scale, translation, cameras=None, ss=2):
    info["clips"] = [(clip[0], clip[1])]
    frames = []
    for i in range(COUNT):
        state["time"] = state["period"] * i / (COUNT-1)
        ps, tr = cameras[i] if cameras is not None else (scale, translation)
        info["profileScale"] = ps
        info["profileTranslation"] = tr
        frame, _ = renderer.render_species(form, size=SIZE, ss=ss, frame="cobblemon")
        frames.append(frame.convert("RGBA"))
    return frames


def render_pair(renderer, form, info, key, clip, poser, dest):
    state = {"time": 0.0, "period": float(clip.get("animation_length") or 2.0), "loop": False}
    if not math.isfinite(state["period"]) or state["period"] < .1:
        state["period"] = 2.0
    renderer.channel_at_zero = channel_sampler(renderer, state)
    renderer.collect_anim = lambda x, m=renderer: collect_override(m, x)
    start_scale = float(poser.get("profileScale") or 1.0)
    start_translation = list(poser.get("profileTranslation") or [0, 0, 0])
    while len(start_translation) < 3:
        start_translation.append(0)
    scale, tr = start_scale, start_translation
    for attempt in range(1, 9):
        fixed = render_clip(renderer, form, info, state, (key, clip), scale, tr, ss=1)
        stats = inspect_frames(fixed, 12)
        if not stats["visible"] or stats["min_margin_px"] >= 12:
            break
        if attempt < 8:
            camera = {"profileScale": scale, "profileTranslation": tr}
            adjust_fixed_camera(camera, stats["alpha_bbox"], SIZE)
            scale, tr = camera["profileScale"], camera["profileTranslation"]
    # Reference bboxes must be measured against this SAME fixed projection.
    bboxes = [im.getchannel("A").getbbox() for im in fixed]
    targets = [compute_target_camera(b, scale, tr) for b in bboxes]
    cameras = smooth_cameras(targets)
    fixed_hq = render_clip(renderer, form, info, state, (key, clip), scale, tr, ss=2)
    follow = render_clip(renderer, form, info, state, (key, clip), scale, tr, cameras=cameras, ss=2)
    fixed_stats = inspect_frames(fixed_hq, 12)
    follow_stats = inspect_frames(follow, 12)
    margins = []
    occupancies = []
    for im in follow:
        b = im.getchannel("A").getbbox()
        if not b:
            margins.append(0)
            occupancies.append(0)
        else:
            margins.append(min(b[0], b[1], SIZE-b[2], SIZE-b[3]))
            occupancies.append(max(b[2]-b[0], b[3]-b[1]))
    sample_contact(fixed_hq, form+"/"+key+"/fixed", dest/(key+"_fixed_contact.png"))
    sample_contact(follow, form+"/"+key+"/follow", dest/(key+"_follow_contact.png"))
    ratios = [cameras[i+1][0]/cameras[i][0] for i in range(len(cameras)-1)]
    report = {"clip_key": key, "duration_sec": state["period"],
              "fixed_changed_pixels": fixed_stats["changed_pixels_max"],
              "fixed_bbox": fixed_stats["alpha_bbox"],
              "follow_changed_pixels": follow_stats["changed_pixels_max"],
              "follow_bbox": follow_stats["alpha_bbox"],
              "follow_per_frame_margins": margins,
              "follow_per_frame_extents": occupancies,
              "max_adjacent_zoom_ratio": round(max([1.0]+[max(r, 1/r) for r in ratios]), 4),
              "wide_camera_attempts": attempt,
              "wide_camera_scale": scale,
              "status": "visual_review_required", "approved_for_publication": False}
    if (follow_stats["visible"] and follow_stats["motion_pass"] and
            min(margins) >= 6 and report["max_adjacent_zoom_ratio"] < 1.25):
        file = dest/(key+"_follow.webp")
        follow[0].save(file, format="WEBP", save_all=True,
                       append_images=follow[1:], duration=round(1000/FPS),loop=1,
                       quality=90, method=5)
        with Image.open(file) as decoded:
            frames = []
            for i in range(decoded.n_frames):
                decoded.seek(i)
                frames.append(decoded.convert("RGBA").copy())
        quality = inspect_frames(frames, 12)
        if len(frames) > 1 and quality["motion_pass"]:
            report.update(status="candidate_follow_unapproved", file=file.name,
                          decoded_frames=len(frames))
        else:
            report["status"] = "decoded_motion_failed"
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True, type=Path)
    parser.add_argument("--resolved", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    data = json.loads(args.resolved.read_text(encoding="utf-8"))
    selected = next((r["selected"] for r in data.get("forms", [])
                     if r["form_id"] == "0384_rayquaza" and r.get("status") == "resolved"), None)
    if not selected:
        raise ValueError("Rayquaza is not Resolver-resolved")
    renderer, poser, geo, info, clips = prepare(args.repo.resolve(), "0384_rayquaza", selected)
    output = args.out.resolve()
    dest = output/"0384_rayquaza"
    dest.mkdir(parents=True, exist_ok=True)
    report = {"schema_version": 1, "purpose": "follow_camera_review_not_published", "trials": {}}
    for key in CLIPS:
        if key not in clips:
            report["trials"][key] = {"status": "missing_clip"}
            continue
        try:
            report["trials"][key] = render_pair(renderer,"0384_rayquaza",info,
                                                 key.rsplit(".",1)[-1],clips[key],poser,dest)
        except Exception as exc:
            report["trials"][key] = {"status": "error", "reason": str(exc)}
        print(key, report["trials"][key]["status"], flush=True)
    path = output/"follow-camera-report.json"
    path.write_text(json.dumps(report, ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("Follow-camera report:",path)


if __name__ == "__main__":
    main()
