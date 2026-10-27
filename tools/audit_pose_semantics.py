#!/usr/bin/env python3
"""Conservative semantic QA of already-rendered resolver pose candidates.

The labels here are evidence flags, NOT proof that a pose is or is not
appropriate in Minecraft. Never promotes candidates into published assets.
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path


def pose_family(pose):
    name = pose.lower().replace("_", "-")
    if any(x in name for x in ("fly", "hover")):
        return "air"
    if any(x in name for x in ("swim", "float", "water")):
        return "water"
    if any(x in name for x in ("walk", "run")):
        return "walk"
    if any(x in name for x in ("standing", "idle", "stand")):
        return "idle"
    return "other"


def clip_family(key):
    name = key.rsplit(".", 1)[-1].lower().replace("_", "-")
    if any(x in name for x in ("air", "fly", "hover")):
        return "air"
    if any(x in name for x in ("swim", "float", "water")):
        return "water"
    if any(x in name for x in ("walk", "run")):
        return "walk"
    if any(x in name for x in ("ground-idle", "idle", "standing")):
        return "idle"
    return "other"


def audit_form(form, details):
    poses = details.get("poses", {})
    by_clips = defaultdict(list)
    for name, item in poses.items():
        keys = tuple(item.get("clip_keys") or [])
        if keys:
            by_clips[keys].append(name)
    results = {}
    for name, item in poses.items():
        keys = tuple(item.get("clip_keys") or [])
        flags = []
        others = [other for other in by_clips.get(keys, []) if other != name] if keys else []
        if others:
            flags.append("shared_exact_clip_set")
        if item.get("status") == "static_pose":
            flags.append("static_pose_not_animation")
        if item.get("status") not in {"candidate", "static_pose"}:
            flags.append("render_not_validated")
        family = pose_family(name)
        families = [clip_family(key) for key in keys]
        # Only flag unambiguous mismatches; e.g. flying based on ground_walk.
        if family == "air" and families and all(x in {"idle", "walk"} for x in families):
            flags.append("air_pose_uses_ground_clip")
        elif family == "water" and families and all(x in {"air", "idle", "walk"} for x in families):
            flags.append("water_pose_uses_other_context_clip")
        results[name] = {
            "render_status": item.get("status"),
            "clip_keys": list(keys),
            "same_clip_as": sorted(others),
            "pose_family": family,
            "clip_families": families,
            "flags": flags,
            "semantic_review": "required" if flags else "unverified",
            "approved_for_publication": False,
        }
    return results


def audit_report(render_report):
    forms = {}
    counts = defaultdict(int)
    for form, details in render_report.get("forms", {}).items():
        if not details.get("poses"):
            forms[form] = {"status": details.get("status", "audit"), "poses": {}}
            continue
        poses = audit_form(form, details)
        for item in poses.values():
            for flag in item["flags"]:
                counts[flag] += 1
        forms[form] = {"status": details.get("status"), "poses": poses}
    return {"schema_version": 1, "purpose": "semantic_review_only_not_published",
            "summary": dict(sorted(counts.items())), "forms": forms}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    data = json.loads(args.report.read_text(encoding="utf-8"))
    audit = audit_report(data)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for form, item in audit["forms"].items():
        for pose, details in item["poses"].items():
            print(form, pose, "flags=", ",".join(details["flags"]) or "none",
                  "same_clip_as=", details["same_clip_as"])
    print("Semantic audit:", args.out)


if __name__ == "__main__":
    main()
