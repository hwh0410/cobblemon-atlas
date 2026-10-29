#!/usr/bin/env python3
"""Safe-camera Rayquaza comparison. Does not publish or alter existing portraits."""
from __future__ import annotations
import argparse, json, math
from pathlib import Path
from PIL import Image
from render_follow_camera_pilot import (prepare, compute_target_camera,
    smooth_cameras, render_clip, CLIPS, SIZE, inspect_frames, sample_contact,
    channel_sampler, collect_override)

def bbox_margin(image):
    b=image.getchannel("A").getbbox()
    return (-1 if not b else min(b[0],b[1],SIZE-b[2],SIZE-b[3]))

def limit_cameras(cameras, wide_scale, max_multiplier=1.85, max_jump=1.08):
    """Clamp zoom and movement in time while retaining deterministic frame count."""
    result=[]
    for scale,tr in cameras:
        s=min(max(scale,wide_scale),wide_scale*max_multiplier)
        if result:
            prior=result[-1][0]
            s=max(prior/max_jump,min(prior*max_jump,s))
        result.append((s,list(tr)))
    return result

def safe_render(renderer, form, info, state, clip, wide, cameras, min_margin=12):
    """Per-frame bounded backoff; fall back to the proven wide fixed camera."""
    output=[]; used=[]; fallback=0
    for i,(target_scale,target_tr) in enumerate(cameras):
        scale=target_scale
        # Preserve wide-camera center when the zoom target is unsafe.
        frame=None; chosen=(wide[0],list(wide[1]))
        for k in range(9):
            trial=render_clip_at(renderer,form,info,state,clip,i,scale,target_tr)
            if bbox_margin(trial)>=min_margin:
                frame=trial; chosen=(scale,list(target_tr)); break
            scale=(scale+wide[0])*0.5
        if frame is None:
            trial=render_clip_at(renderer,form,info,state,clip,i,*wide)
            frame=trial; fallback+=1
        output.append(frame);used.append(chosen)
    return output,used,fallback

def render_clip_at(renderer,form,info,state,clip,index,scale,tr):
    info["clips"]=[clip]
    info["profileScale"]=scale
    info["profileTranslation"]=list(tr)
    state["time"]=state["period"]*index/(FRAME_COUNT-1)
    im,_=renderer.render_species(form,size=SIZE,ss=2,frame="cobblemon")
    return im.convert("RGBA")

FRAME_COUNT=48

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--repo",type=Path,required=True)
    p.add_argument("--resolved",type=Path,required=True)
    p.add_argument("--out",type=Path,required=True)
    args=p.parse_args()
    forms=json.loads(args.resolved.read_text())["forms"]
    resolved=next((r["selected"] for r in forms if r.get("form_id")=="0384_rayquaza" and r.get("status")=="resolved"),None)
    if resolved is None: raise RuntimeError("Rayquaza resolver mapping not found")
    renderer,poser,geo,info,clips=prepare(args.repo.resolve(),"0384_rayquaza",resolved)
    out=args.out.resolve();dest=out/"0384_rayquaza";dest.mkdir(parents=True,exist_ok=True)
    report={"schema_version":2,"purpose":"safe_camera_review_only","frames":FRAME_COUNT,"trials":{}}
    for key in CLIPS:
        if key not in clips: report["trials"][key]={"status":"missing_clip"};continue
        clip=clips[key];short=key.rsplit(".",1)[-1]
        duration=float(clip.get("animation_length") or 2)
        state={"time":0.0,"period":duration,"loop":False}
        renderer.channel_at_zero=channel_sampler(renderer,state)
        renderer.collect_anim=lambda x,m=renderer:collect_override(m,x)
        scale=float(poser.get("profileScale") or 1)
        trans=list(poser.get("profileTranslation") or [0,0,0])
        while len(trans)<3:trans.append(0)
        wide=(scale,trans)
        from render_action_jobs import adjust_fixed_camera
        for n in range(10):
            frames=[render_clip_at(renderer,"0384_rayquaza",info,state,(key,clip),i,*wide) for i in range(FRAME_COUNT)]
            margins=[bbox_margin(f) for f in frames]
            if min(margins)>=16:break
            stats=inspect_frames(frames,12)
            camera={"profileScale":wide[0],"profileTranslation":wide[1]}
            adjust_fixed_camera(camera,stats["alpha_bbox"],SIZE)
            wide=(float(camera["profileScale"]),list(camera["profileTranslation"]))
        initial=[render_clip_at(renderer,"0384_rayquaza",info,state,(key,clip),i,*wide) for i in range(FRAME_COUNT)]
        bboxes=[f.getchannel("A").getbbox() for f in initial]
        targets=[compute_target_camera(b,*wide,target_extent=144) for b in bboxes]
        cameras=limit_cameras(smooth_cameras(targets),wide[0])
        follows,used,fallback=safe_render(renderer,"0384_rayquaza",info,state,(key,clip),wide,cameras)
        ms=[bbox_margin(f) for f in follows]
        report["trials"][key]={"min_margin":min(ms),"unsafe_frames":sum(x<12 for x in ms),
            "fallback_frames":fallback,"wide_min_margin":min(bbox_margin(f) for f in initial),
            "status":"visual_review_required","approved_for_publication":False}
        sample_contact(initial,"Rayquaza "+short+" fixed",dest/(short+"_fixed_contact.png"))
        sample_contact(follows,"Rayquaza "+short+" safe",dest/(short+"_safe_contact.png"))
        if min(ms)>=12 and inspect_frames(follows,12)["motion_pass"]:
            target=dest/(short+"_safe.webp")
            follows[0].save(target,format="WEBP",save_all=True,append_images=follows[1:],
               duration=round(duration*1000/FRAME_COUNT),loop=0,quality=90,method=5)
            with Image.open(target) as im:
                report["trials"][key]["decoded_frames"]=im.n_frames
            report["trials"][key]["status"]="candidate_unapproved"
        print(key,report["trials"][key],flush=True)
    result=out/"safe-camera-report.json"
    result.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n")
    print("Report:",result)

if __name__=="__main__": main()
