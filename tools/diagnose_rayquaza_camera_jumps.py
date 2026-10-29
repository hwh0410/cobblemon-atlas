#!/usr/bin/env python3
"""Locate camera-induced versus action-induced jumps in Rayquaza physical attack.
Independent diagnostic: does not overwrite WebPs or publish to Atlas.
"""
import argparse, json, math
from pathlib import Path
import numpy as np
from PIL import Image
from render_safe_camera_pilot import (
    prepare, render_clip_at, bbox_margin, limit_cameras, safe_render, FRAME_COUNT)
from render_follow_camera_pilot import (
    compute_target_camera, smooth_cameras, channel_sampler, collect_override)
from render_action_jobs import adjust_fixed_camera, inspect_frames

KEY="animation.rayquaza.physical_attack"

def center(im):
    a=np.asarray(im.getchannel("A"))
    y,x=np.nonzero(a>16)
    return None if len(x)==0 else (float(np.mean(x)),float(np.mean(y)))

def steps(centers):
    return [None if a is None or b is None else round(math.dist(a,b),2)
            for a,b in zip(centers,centers[1:])]

def top_jumps(steps, count=8):
    return sorted(({"from":i,"to":i+1,"distance_px":v}
                   for i,v in enumerate(steps) if v is not None),
                  key=lambda d:-d["distance_px"])[:count]

def main():
    p=argparse.ArgumentParser()
    for field in ("repo","resolved","out"):p.add_argument("--"+field,type=Path,required=True)
    args=p.parse_args()
    records=json.loads(args.resolved.read_text())["forms"]
    selected=next((r["selected"] for r in records if r.get("form_id")=="0384_rayquaza" and r.get("status")=="resolved"),None)
    if selected is None: raise RuntimeError("Cannot resolve Rayquaza")
    renderer,poser,geo,info,clips=prepare(args.repo.resolve(),"0384_rayquaza",selected)
    clip=clips[KEY]
    duration=float(clip.get("animation_length") or 4.75)
    state={"time":0.0,"period":duration,"loop":False}
    renderer.channel_at_zero=channel_sampler(renderer,state)
    renderer.collect_anim=lambda info,m=renderer: collect_override(m,info)
    scale=float(poser.get("profileScale") or 1)
    tr=list(poser.get("profileTranslation") or [0,0,0])
    while len(tr)<3:tr.append(0)
    wide=(scale,tr)
    for _ in range(10):
        frames=[render_clip_at(renderer,"0384_rayquaza",info,state,(KEY,clip),i,*wide)
                for i in range(FRAME_COUNT)]
        if min(bbox_margin(f) for f in frames)>=16:break
        q=inspect_frames(frames,12)
        camera={"profileScale":wide[0],"profileTranslation":wide[1]}
        adjust_fixed_camera(camera,q["alpha_bbox"],224)
        wide=(float(camera["profileScale"]),list(camera["profileTranslation"]))
    fixed=[render_clip_at(renderer,"0384_rayquaza",info,state,(KEY,clip),i,*wide)
           for i in range(FRAME_COUNT)]
    target=[compute_target_camera(f.getchannel("A").getbbox(),*wide,target_extent=144)
            for f in fixed]
    cameras=limit_cameras(smooth_cameras(target),wide[0])
    safe,actual,fallback=safe_render(renderer,"0384_rayquaza",info,state,(KEY,clip),wide,cameras)
    cf=[center(f) for f in fixed]; cs=[center(f) for f in safe]
    fixed_step=steps(cf); safe_step=steps(cs)
    camera_step=[round(math.hypot(s[0]-f[0],s[1]-f[1]),2)
                 if s is not None and f is not None else None for s,f in zip(cs,cf)]
    issue=[]
    for i,(fs,ss) in enumerate(zip(fixed_step,safe_step)):
        if ss is not None and ss>35:
            issue.append({"from":i,"to":i+1,"safe_jump":ss,"fixed_jump":fs,
                          "likely_camera_amplification":bool(fs is not None and ss>fs+15)})
    output={"schema_version":1,"purpose":"physical_attack_camera_diagnosis_only",
        "duration_sec":duration,"source_frames":FRAME_COUNT,"fallback_frames":fallback,
        "camera_fixed_centers":cf,"camera_safe_centers":cs,
        "fixed_step_px":fixed_step,"safe_step_px":safe_step,
        "fixed_top_jumps":top_jumps(fixed_step),"safe_top_jumps":top_jumps(safe_step),
        "camera_displacement_vs_fixed_px":camera_step,"jump_cases":issue,
        "tail_note":"Original WebP kept untouched; the prior last encoded frame lasts 594 ms.",
        "approved_for_publication":False}
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(output,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("Max fixed jump:",max(v or 0 for v in fixed_step))
    print("Max safe jump:",max(v or 0 for v in safe_step))
    print("Jump cases:",issue)
    print("Report:",args.out)

if __name__=="__main__":main()
