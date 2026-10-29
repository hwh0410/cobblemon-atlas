#!/usr/bin/env python3
"""Resolver-correct pose + overlay test, with a control animation for each trial.

All outputs are isolated candidates. An overlay is successful only if it adds
visible pixels beyond the exact same base clip at the same sample times.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image

from compare_pose_layers import load_renderer, sample_contact
from render_action_jobs import adjust_fixed_camera, channel_sampler, inspect_frames
from render_resolved_forms import extract_clips

TRIALS = {
    "0150_mewtwo": [("standing_blink", "standing", "animation.mewtwo.blink")],
    "0384_rayquaza": [
        ("standing_cry", "standing", "animation.rayquaza.cry"),
        ("standing_physical_attack", "standing", "animation.rayquaza.physical_attack"),
        ("standing_special_attack", "standing", "animation.rayquaza.special_attack"),
    ],
}


def overlay_difference(base, layered):
    if len(base) != len(layered):
        raise ValueError("frame counts differ")
    changes = []
    for a, b in zip(base, layered):
        va = np.asarray(a.convert("RGBA"), dtype=np.int16)
        vb = np.asarray(b.convert("RGBA"), dtype=np.int16)
        changes.append(int(np.count_nonzero(np.max(np.abs(va-vb), axis=2) > 10)))
    return max(changes, default=0), changes


def prepare(repo, form, selected):
    merged = repo / "merged_pack"
    geo = json.loads((merged / selected["model"]).read_text(encoding="utf-8-sig"))["minecraft:geometry"][0]
    poser = json.loads((merged / selected["poser"]).read_text(encoding="utf-8-sig"))
    texture = np.asarray(Image.open(merged / selected["texture"]).convert("RGBA"), dtype=np.float32) / 255.0
    renderer = load_renderer(repo / "tools/render_portraits.py")
    _, layers = renderer.species_setup(form)
    ids = [x["geometry"] for x in layers if x.get("geometry") and "held" not in str(x["geometry"])]
    if not ids:
        raise RuntimeError("No prepared geometry layer")
    override = dict(renderer.geo_index())
    for name in ids:
        override[name] = geo
    renderer.geo_index = lambda: override
    orig_texture = renderer.load_texture
    renderer.load_texture = lambda path, fn=orig_texture: (
        texture if path and f"textures/entity/{form}/" in path
        and "shiny" not in path and "blank" not in path else fn(path))
    info = renderer.find_animations(form, form.split("_", 1)[-1])
    info["poser"] = str(merged / selected["poser"])
    info["profileScale"] = float(poser.get("profileScale") or 1.0)
    info["profileTranslation"] = list(poser.get("profileTranslation") or [0, 0, 0])
    renderer.find_animations = lambda folder, species: info
    group = "_".join(form.split("_")[:2])
    clips = {}
    for path in sorted((merged / "bedrock/pokemon/animations" / group).glob("*.animation.json")):
        clips.update(json.loads(path.read_text(encoding="utf-8-sig")).get("animations", {}))
    return renderer, poser, geo, info, clips


def render_trial(renderer, form, poser, info, clips, label, base_pose, overlay, dest, geo):
    base, skipped = extract_clips(poser["poses"][base_pose], clips)
    report = {"base_pose": base_pose, "base_clips": base, "overlay_clip": overlay,
              "unsupported_pose_expressions": skipped,
              "declared_in_poser": overlay in set(extract_all_poser_keys(poser))}
    if not base or overlay not in clips:
        report.update(status="audit", reason="missing_base_or_overlay_clip")
        return report
    bone_names = {b.get("name", "").casefold() for b in geo.get("bones", [])}
    overlay_bones = clips[overlay].get("bones", {})
    if not isinstance(overlay_bones, dict):
        report.update(status="audit", reason="bad_overlay_bones")
        return report
    missing = sorted(k for k in overlay_bones if k.casefold() not in bone_names)
    report["overlay_matched_bones"] = len(overlay_bones) - len(missing)
    report["overlay_unmatched_bones"] = missing
    if missing or not overlay_bones:
        report.update(status="audit", reason="overlay_bone_mismatch")
        return report
    state = {"time": 0.0, "period": 2.0, "loop": True}
    renderer.channel_at_zero = channel_sampler(renderer, state)
    original_collect = renderer.collect_anim
    # Standalone Rayquaza action clips encode absolute bone targets. Override
    # repeated channels instead of adding the base rotations a second time.
    from render_blend_modes import collect_override
    report["blend_policy"] = "action_channel_override" if form == "0384_rayquaza" else "additive"
    info["profileScale"] = float(poser.get("profileScale") or 1.0)
    info["profileTranslation"] = list(poser.get("profileTranslation") or [0, 0, 0])
    fixed_camera = None
    for attempt in range(1, 9):
        sequences = []
        for selection in (base, base + [overlay]):
            info["clips"] = [(key, clips[key]) for key in selection]
            if form == "0384_rayquaza" and len(selection) > len(base):
                renderer.collect_anim = lambda _info, module=renderer: collect_override(module, _info)
            else:
                renderer.collect_anim = original_collect
            frames = []
            for n in range(24):
                state["time"] = n / 12.0
                image, _ = renderer.render_species(form, size=224, ss=2, frame="cobblemon")
                frames.append(image.convert("RGBA"))
            sequences.append(frames)
        base_frames, layered_frames = sequences
        combined_stats = inspect_frames(base_frames + layered_frames, 12)
        if not combined_stats["visible"] or combined_stats["min_margin_px"] >= 6:
            break
        if attempt < 8:
            adjust_fixed_camera(info, combined_stats["alpha_bbox"], 224)
    renderer.collect_anim = original_collect
    base_stats = inspect_frames(base_frames, 12)
    layered_stats = inspect_frames(layered_frames, 12)
    overlay_max, overlay_per_frame = overlay_difference(base_frames, layered_frames)
    sample_contact(base_frames, form + "/" + label + " base", dest / (label + "_base_contact.png"))
    sample_contact(layered_frames, form + "/" + label + " combined", dest / (label + "_combined_contact.png"))
    report.update(base_motion_pixels=base_stats["changed_pixels_max"],
                  combined_motion_pixels=layered_stats["changed_pixels_max"],
                  overlay_change_pixels_max=overlay_max,
                  overlay_change_pixels_per_frame=overlay_per_frame,
                  frame_margin_px=combined_stats["min_margin_px"],
                  framing_attempts=attempt,
                  camera_scale=info["profileScale"],
                  camera_translation=info["profileTranslation"])
    if not combined_stats["visible"] or combined_stats["min_margin_px"] < 6:
        report.update(status="audit", reason="invisible_or_cropped")
    elif overlay_max < 12:
        report.update(status="audit", reason="overlay_has_no_visible_effect")
    elif not layered_stats["motion_pass"]:
        report.update(status="audit", reason="combined_clip_has_no_motion")
    else:
        target = dest / (label + ".webp")
        layered_frames[0].save(target, format="WEBP", save_all=True,
                               append_images=layered_frames[1:], duration=83,
                               loop=0, quality=90, method=5)
        with Image.open(target) as check:
            decoded = []
            for i in range(check.n_frames):
                check.seek(i)
                decoded.append(check.convert("RGBA").copy())
        decoded_motion = inspect_frames(decoded, 12)
        report["decoded_frames"] = len(decoded)
        report["decoded_motion_pixels"] = decoded_motion["changed_pixels_max"]
        if len(decoded) > 1 and decoded_motion["motion_pass"]:
            report.update(status="candidate_overlay", file=target.name,
                          semantic_review="required", approved_for_publication=False)
        else:
            report.update(status="audit", reason="decoded_webp_lost_motion")
    return report


def extract_all_poser_keys(poser):
    import re
    pattern = re.compile(r"q\.bedrock(?:_stateful|_quirk)?\(\s*['\"]([^'\"]+)['\"]\s*,\s*['\"]([^'\"]+)['\"]", re.I)
    for match in pattern.finditer(json.dumps(poser)):
        yield "animation." + match.group(1) + "." + match.group(2)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--resolved", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    data = json.loads(args.resolved.read_text(encoding="utf-8"))
    args.out.mkdir(parents=True, exist_ok=True)
    report = {"schema_version": 1, "purpose": "layered_pilot_not_published", "forms": {}}
    for row in data.get("forms", []):
        form = row.get("form_id")
        if form not in TRIALS:
            continue
        if row.get("status") != "resolved":
            report["forms"][form] = {"status": "audit", "reason": row.get("reason")}
            continue
        try:
            renderer, poser, geo, info, clips = prepare(args.repo.resolve(), form, row["selected"])
            dest = args.out / form
            dest.mkdir(parents=True, exist_ok=True)
            trials = {}
            for label, pose, overlay in TRIALS[form]:
                trials[label] = render_trial(renderer, form, poser, info, clips,
                                             label, pose, overlay, dest, geo)
                print(form, label, trials[label]["status"],
                      trials[label].get("overlay_change_pixels_max"), flush=True)
            report["forms"][form] = {"status": "tested", "trials": trials}
        except Exception as error:
            report["forms"][form] = {"status": "failed", "reason": str(error)}
            print(form, "FAILED", error, flush=True)
    target = args.out / "layered-render-pilot.json"
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("Layered pilot report:", target)


if __name__ == "__main__":
    main()
