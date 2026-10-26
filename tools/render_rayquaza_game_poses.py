#!/usr/bin/env python3
"""Audit Cobblemon Rayquaza Poser references and render its actual pose clips.

Diagnostic only: ignores conditional q.look / quirks (reports them); never writes
to the official action folder or changes the existing checkpoint.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from PIL import Image

from compare_pose_layers import load_renderer, sample_contact
from render_action_jobs import channel_sampler, inspect_frames

BEDROCK = re.compile(
    r"q\.bedrock\(\s*(['\"])([^'\"]+)\1\s*,\s*(['\"])([^'\"]+)\3\s*\)",
    re.I,
)


def animation_expressions(pose):
    out = []
    for entry in pose.get("animations", []):
        if isinstance(entry, str):
            out.append((entry, None))
        elif isinstance(entry, dict):
            out.append((str(entry.get("animation", "")), entry.get("condition")))
    return out


def inspect_poser(data, animations):
    rows = {}
    for pose_name, pose in data.get("poses", {}).items():
        clips = []
        unsupported = []
        for expr, condition in animation_expressions(pose):
            m = BEDROCK.search(expr)
            if m:
                key = f"animation.{m.group(2)}.{m.group(4)}"
                clips.append({
                    "key": key, "condition": condition,
                    "found": key in animations,
                    "bone_channels": len(animations.get(key, {}).get("bones", {})),
                })
            else:
                unsupported.append({"expression": expr, "condition": condition})
        rows[pose_name] = {
            "pose_types": pose.get("poseTypes", []),
            "is_battle": bool(pose.get("isBattle", False)),
            "conditions": pose.get("condition"),
            "clips": clips, "unsupported": unsupported,
            "quirks": pose.get("quirks", []),
            "transformed_parts": pose.get("transformedParts", []),
        }
    return rows


def choose_poses(rows, count=4):
    # Select actual game-defined non-battle poses, with flying first.
    order = ["flying", "hovering", "floating", "standing", "profile",
             "fly", "hover", "float"]
    chosen = []
    for term in order:
        matches = [name for name, row in rows.items()
                   if term in name.lower() and not row["is_battle"]
                   and any(c["found"] and c["condition"] is None for c in row["clips"])]
        for name in matches:
            if name not in chosen:
                chosen.append(name)
        if len(chosen) >= count:
            break
    return chosen[:count]


def run(repo, out, fps=12, seconds=2, size=224, ss=2):
    form = "0384_rayquaza"
    pack = repo / "merged_pack"
    poser_path = pack / "bedrock/pokemon/posers/0384_rayquaza/rayquaza.json"
    if not poser_path.is_file():
        raise FileNotFoundError(poser_path)
    poser = json.loads(poser_path.read_text(encoding="utf-8-sig"))
    animation_files = sorted((pack / "bedrock/pokemon/animations/0384_rayquaza").glob("*.json"))
    if not animation_files:
        raise FileNotFoundError("No Rayquaza Bedrock animation JSON files")
    animations = {}
    for path in animation_files:
        animations.update(json.loads(path.read_text(encoding="utf-8-sig")).get("animations", {}))
    rows = inspect_poser(poser, animations)
    selected = choose_poses(rows)
    out.mkdir(parents=True, exist_ok=True)
    report = {"schema_version": 1, "form": form, "poser":str(poser_path),
              "animation_files":[str(x) for x in animation_files],
              "all_pose_definitions":rows, "selected_poses":selected, "renders":{},
              "limitations":["q.look, quirks and conditional clips are not executed",
                             "Additive clip interpretation is an experimental approximation",
                             "Fixed camera may need framing for non-profile poses"]}
    renderer=load_renderer(repo / "tools/render_portraits.py")
    info=renderer.find_animations(form, "rayquaza")
    info["poser"]=str(poser_path)
    info["profileScale"]=float(poser.get("profileScale") or info.get("profileScale") or 1.0)
    info["profileTranslation"]=poser.get("profileTranslation") or info.get("profileTranslation") or [0,0,0]
    old_find=renderer.find_animations
    renderer.find_animations=lambda folder,species:info
    state={"time":0.0,"period":seconds,"loop":True}
    renderer.channel_at_zero=channel_sampler(renderer,state)
    try:
        for name in selected:
            eligible=[c["key"] for c in rows[name]["clips"]
                      if c["found"] and c["condition"] is None]
            if not eligible:
                continue
            info["clips"]=[(key,animations[key]) for key in eligible]
            frames=[]
            for i in range(max(2, round(fps*seconds))):
                state["time"]=seconds*i/max(2,round(fps*seconds))
                frame,_=renderer.render_species(form,size=size,ss=ss,frame="fit")
                frames.append(frame.convert("RGBA"))
            metrics=inspect_frames(frames,12)
            safe=re.sub(r"[^a-zA-Z0-9_-]","_",name)
            sample_contact(frames,name,out/(safe+"_contact.png"))
            target=out/(safe+".webp")
            frames[0].save(target,format="WEBP",save_all=True,append_images=frames[1:],
                           duration=round(1000/fps),loop=0,quality=90,method=5)
            report["renders"][name]={"clips":eligible,"file":target.name,
                                    "contact":safe+"_contact.png",**metrics}
            print(name, eligible, "motion",metrics["changed_pixels_max"],flush=True)
    finally:
        renderer.find_animations=old_find
    result=out/"rayquaza-game-poses.json"
    result.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print("Game pose report:",result)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--repo",required=True,type=Path)
    p.add_argument("--out",required=True,type=Path)
    a=p.parse_args()
    run(a.repo.resolve(),a.out.resolve())


if __name__=="__main__":
    main()
