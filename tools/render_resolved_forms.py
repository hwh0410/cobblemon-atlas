#!/usr/bin/env python3
"""Resolver-accurate cross-form pose pilot. Writes only an isolated output folder.

Uses the existing CPU rasterizer in memory, substituting the Resolver-selected
geometry and texture, never modifying the prepared source resource packs.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import numpy as np
from PIL import Image

from compare_pose_layers import load_renderer, sample_contact
from render_action_jobs import adjust_fixed_camera, channel_sampler, inspect_frames

BEDROCK=re.compile(r"q\.bedrock\(\s*(['\"])(.*?)\1\s*,\s*(['\"])(.*?)\3\s*\)",re.I)


def extract_clips(pose, animations):
    clips=[];skipped=[]
    for entry in pose.get("animations",[]):
        if not isinstance(entry,str):
            skipped.append(entry)
            continue
        match=BEDROCK.search(entry)
        if not match:
            skipped.append(entry)
            continue
        key=f"animation.{match.group(2)}.{match.group(4)}"
        if key in animations:
            clips.append(key)
        else:
            skipped.append({"missing_clip":key})
    return clips,skipped


def pick_poses(poser):
    names=list(poser.get("poses",{}))
    pref=["standing","walking","walk","fly","flying","hover","hovering","float","floating"]
    return [p for p in pref if p in names][:4]


def render_form(repo,form,resolved,out):
    selected=resolved["selected"]
    merged=repo/"merged_pack"
    geo_data=json.loads((merged/selected["model"]).read_text(encoding="utf-8-sig"))
    geo=geo_data["minecraft:geometry"][0]
    poser=json.loads((merged/selected["poser"]).read_text(encoding="utf-8-sig"))
    texture=np.asarray(Image.open(merged/selected["texture"]).convert("RGBA"),dtype=np.float32)/255.0
    renderer=load_renderer(repo/"tools/render_portraits.py")
    _,layers=renderer.species_setup(form)
    geometry_ids=[x["geometry"] for x in layers if x.get("geometry") and
                  "held" not in str(x.get("geometry"))]
    if not geometry_ids:
        raise RuntimeError(f"No prepared base geometry layer for {form}")
    original_geos=renderer.geo_index()
    override=dict(original_geos)
    for name in geometry_ids:
        override[name]=geo
    renderer.geo_index=lambda:override
    old_texture=renderer.load_texture
    renderer.load_texture=lambda rel,fn=old_texture: (
        texture if rel and f"textures/entity/{form}/" in rel
        and "shiny" not in rel and "blank" not in rel else fn(rel))
    info=renderer.find_animations(form,form.split("_",1)[-1])
    info["profileScale"]=float(poser.get("profileScale") or 1.0)
    info["profileTranslation"]=poser.get("profileTranslation") or [0,0,0]
    info["poser"]=str(merged/selected["poser"])
    renderer.find_animations=lambda folder,species:info
    animations={}
    group=form.split("_",1)[0]+"_"+form.split("_",1)[1].split("_")[0]
    anim_folder=merged/"bedrock/pokemon/animations"/group
    for file in sorted(anim_folder.glob("*.animation.json")):
        animations.update(json.loads(file.read_text(encoding="utf-8-sig")).get("animations",{}))
    state={"time":0.0,"period":2.0,"loop":True}
    renderer.channel_at_zero=channel_sampler(renderer,state)
    output={"model":selected["model"],"poser":selected["poser"],
            "texture":selected["texture"],"bones":selected["bone_count"],
            "poses":{}}
    dest=out/form;dest.mkdir(parents=True,exist_ok=True)
    for pose_name in pick_poses(poser):
        keys,skipped=extract_clips(poser["poses"][pose_name],animations)
        row={"clip_keys":keys,"unsupported_expressions":skipped}
        if not keys:
            row["status"]="audit";row["reason"]="no_renderable_pose_clips"
            output["poses"][pose_name]=row
            continue
        info["clips"]=[(key,animations[key]) for key in keys]
        # Same fixed camera for the whole animation; conservative recentering
        # may require multiple passes for large movements.
        start_scale=float(poser.get("profileScale") or 1.0)
        start_trans=list(poser.get("profileTranslation") or [0,0,0])
        info["profileScale"]=start_scale
        info["profileTranslation"]=start_trans
        for attempt in range(1,9):
            frames=[]
            for i in range(24):
                state["time"]=i/12
                img,_=renderer.render_species(form,size=224,ss=2,frame="cobblemon")
                frames.append(img.convert("RGBA"))
            metrics=inspect_frames(frames,12)
            if not metrics["visible"] or not metrics["motion_pass"] or metrics["min_margin_px"]>=6:
                break
            if attempt<8:
                adjust_fixed_camera(info,metrics["alpha_bbox"],224)
        sample_contact(frames,form+"/"+pose_name,dest/(pose_name+"_contact.png"))
        row.update(metrics)
        row["framing_attempts"]=attempt
        row["camera_scale"]=info["profileScale"]
        row["camera_translation"]=info["profileTranslation"]
        if metrics["visible"] and metrics["motion_pass"] and metrics["min_margin_px"]>=6:
            file=dest/(pose_name+".webp")
            frames[0].save(file,format="WEBP",save_all=True,append_images=frames[1:],
                           duration=83,loop=0,quality=90,method=5)
            row["status"]="candidate"
            row["file"]=file.name
        else:
            row["status"]="audit"
            row["reason"]="static_empty_or_bad_frame"
        output["poses"][pose_name]=row
        print(form,pose_name,row["status"],keys,flush=True)
    return output


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--repo",required=True,type=Path)
    p.add_argument("--resolved",required=True,type=Path)
    p.add_argument("--out",required=True,type=Path)
    args=p.parse_args()
    repo=args.repo.resolve();out=args.out.resolve()
    d=json.loads(args.resolved.read_text(encoding="utf-8"))
    report={"schema_version":1,"status":"candidate_only_not_published","forms":{}}
    for row in d.get("forms",[]):
        form=row["form_id"]
        if row["status"]!="resolved":
            report["forms"][form]={"status":"audit","reason":row.get("reason")}
            print(form,"AUDIT",row.get("reason"))
            continue
        try:
            report["forms"][form]={"status":"rendered",
                                   **render_form(repo,form,row,out)}
        except Exception as exc:
            report["forms"][form]={"status":"failed",
                                   "reason":f"{type(exc).__name__}: {exc}"}
            print(form,"FAILED",exc,flush=True)
    out.mkdir(parents=True,exist_ok=True)
    target=out/"resolved-render-pilot.json"
    target.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print("Pilot report:",target)


if __name__=="__main__":
    main()
