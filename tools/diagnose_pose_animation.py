#!/usr/bin/env python3
"""Offline, non-mutating bone/keyframe diagnostics for resolver-selected poses."""
from __future__ import annotations

import argparse
import json
import math
import re
from pathlib import Path

from render_resolved_forms import extract_clips, pick_poses
from render_action_jobs import channel_sampler


def load(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def norm(name):
    return str(name).casefold()


def numeric_variation(channel):
    """Raw keyframe audit, without pretending to evaluate every MoLang expression."""
    if isinstance(channel, dict):
        samples = [json.dumps(v, sort_keys=True) for v in channel.values()]
        return len(set(samples)) > 1, len(samples)
    return False, 1


def inspect_clip(clip, bone_names):
    bones = clip.get("bones", {})
    if not isinstance(bones, dict):
        return {"error": "clip.bones is not an object"}
    known = {norm(n) for n in bone_names}
    matched = []
    unmatched = []
    keyframed = []
    expressions = []
    for name, channels in bones.items():
        (matched if norm(name) in known else unmatched).append(name)
        if not isinstance(channels, dict):
            continue
        for kind in ("rotation", "position", "scale"):
            if kind not in channels:
                continue
            value = channels[kind]
            varied, count = numeric_variation(value)
            if varied or count > 1:
                keyframed.append({"bone": name, "channel": kind, "keys": count, "distinct_values": varied})
            if re.search(r"\b(math\.|query\.|q\.|variable\.|v\.)", json.dumps(value), re.I):
                expressions.append({"bone": name, "channel": kind})
    return {"clip_bones": len(bones), "matched_bones": len(matched),
            "unmatched_bones": unmatched, "keyframed_channels": keyframed[:40],
            "expression_channels": expressions[:40],
            "animation_length": clip.get("animation_length"), "loop": clip.get("loop")}


def inspect_form(repo, row):
    sel = row["selected"]
    merged = repo / "merged_pack"
    geometry = load(merged / sel["model"])["minecraft:geometry"][0]
    poser = load(merged / sel["poser"])
    bones = [b["name"] for b in geometry.get("bones", []) if "name" in b]
    form = row["form_id"]
    species_folder = "_".join(form.split("_")[:2])
    animation_dir = merged / "bedrock/pokemon/animations" / species_folder
    animations = {}
    sources = {}
    for source in sorted(animation_dir.glob("*.animation.json")):
        for key, value in load(source).get("animations", {}).items():
            animations[key] = value
            sources[key] = str(source.relative_to(repo))
    poses = {}
    for pose_name in pick_poses(poser):
        keys, skipped = extract_clips(poser["poses"][pose_name], animations)
        poses[pose_name] = {"clip_keys": keys, "unhandled_pose_expressions": skipped,
                            "clips": {key: {"source": sources[key], **inspect_clip(animations[key], bones)}
                                      for key in keys}}
    return {"form_id": form, "geometry": sel["model"], "poser": sel["poser"],
            "geometry_bones": len(bones), "poses": poses}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--resolved", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--forms", nargs="*", default=["0150_mewtwo", "0384_rayquaza"])
    args = parser.parse_args()
    data = load(args.resolved)
    report = {"schema_version": 1, "purpose": "diagnostic_only_not_published", "forms": {}}
    for row in data.get("forms", []):
        form = row.get("form_id")
        if form not in args.forms:
            continue
        if row.get("status") != "resolved":
            report["forms"][form] = {"status": "audit", "reason": row.get("reason")}
            continue
        try:
            report["forms"][form] = inspect_form(args.repo.resolve(), row)
        except (OSError, ValueError, KeyError, TypeError) as error:
            report["forms"][form] = {"status": "error", "reason": str(error)}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    for form, result in report["forms"].items():
        print("FORM", form, "bones", result.get("geometry_bones"))
        for pose, info in result.get("poses", {}).items():
            print(" POSE", pose, "clips", len(info["clip_keys"]))
            for name, clip in info["clips"].items():
                print("  ", name, "matched", clip.get("matched_bones"), "/", clip.get("clip_bones"),
                      "keyframed", len(clip.get("keyframed_channels", [])),
                      "expressions", len(clip.get("expression_channels", [])),
                      "missing", clip.get("unmatched_bones", []))
    print("Diagnostic report:", args.out)


if __name__ == "__main__":
    main()
