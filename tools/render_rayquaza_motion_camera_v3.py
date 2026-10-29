#!/usr/bin/env python3
"""Rayquaza physical attack V3: motion-aware camera blending with strict margins.
No publication; renders alongside V2 with source animation untouched.
"""
from __future__ import annotations
import argparse,json,math
from pathlib import Path
import numpy as np
from PIL import Image
from render_safe_camera_pilot import (FRAME_COUNT,bbox_margin,limit_cameras,
  safe_render,render_clip_at)
from render_follow_camera_pilot import (prepare,compute_target_camera,smooth_cameras,
  channel_sampler,collect_override,sample_contact,inspect_frames)
from render_action_jobs import adjust_fixed_camera

KEY="animation.rayquaza.physical_attack"
SIZE=224

def image_center(image):
    a=np.asarray(image.getchannel("A"))
    y,x=np.nonzero(a>16)
    return None if not len(x) else (float(x.mean()),float(y.mean()))

def distance(a,b):
    return 0 if a is None or b is None else math.dist(a,b)

def blend_camera(wide, follow, weight):
    s=wide[0]+weight*(follow[0]-wide[0])
    tr=[a+weight*(b-a) for a,b in zip(wide[1],follow[1])]
    return s,tr

def camera_plan(wide, follow_cameras, fixed_centers, max_extra_jump_px=4.0):
    """Reduce follow-camera influence around large native jumps.

    This is a preview plan; actual post-render jump is evaluated separately.
    """
    weights=[]
    for i in range(len(follow_cameras)):
        prev=distance(fixed_centers[i-1],fixed_centers[i]) if i>0 else 0
        nxt=distance(fixed_centers[i],fixed_centers[i+1]) if i+1<len(fixed_centers) else 0
        peak=max(prev,nxt)
        weights.append(1.0 if peak<18 else max(0.0,min(1.0,18/peak)))
    return [blend_camera(wide,c,w) for c,w in zip(follow_cameras,weights)],weights

def render_one(renderer,info,state,clip,i,camera):
    return render_clip_at(renderer,"0384_rayquaza",info,state,clip,i,*camera)

def bounded_frames(renderer,info,state,clip,wide,planned,fixed,
                   max_added_step=5.0,min_margin=12):
    """Search candidate camera strengths; reject ones amplifying native step.

    Use fixed-wide camera for a frame where no candidate meets margin+step.
    The comparison is image-centric and deliberately conservative.
    """
    out=[];selected=[]; fallback=0; fixed_centers=list(map(image_center,fixed))
    for i,candidate in enumerate(planned):
        chosen=None;camera=None
        for strength in (1.0,.75,.5,.25,0.0):
            test_camera=blend_camera(wide,candidate,strength)
            im=render_one(renderer,info,state,clip,i,test_camera)
            if bbox_margin(im)<min_margin:continue
            if i:
                previous=image_center(out[-1])
                jump=distance(previous,image_center(im))
                original=distance(fixed_centers[i-1],fixed_centers[i])
                if jump>max(20,original+max_added_step):continue
            chosen=im;camera=test_camera;break
        if chosen is None:
            chosen=fixed[i];camera=wide;fallback+=1
        out.append(chosen);selected.append(camera)
    return out,selected,fallback

def jumps(frames):
    cs=[image_center(im) for im in frames]
    return [round(distance(a,b),2) for a,b in zip(cs,cs[1:])]

def run(args):
    forms=json.loads(args.resolved.read_text())["forms"]
    selection=next((r["selected"] for r in forms if r.get("form_id")=="0384_rayquaza"
                    and r.get("status")=="resolved"),None)
    if selection is None:raise ValueError("Resolver lacks Rayquaza")
    renderer,poser,geo,info,clips=prepare(args.repo.resolve(),"0384_rayquaza",selection)
    clip=(KEY,clips[KEY]);duration=float(clip[1].get("animation_length") or 4.75)
    state={"time":0.0,"period":duration,"loop":False}
    renderer.channel_at_zero=channel_sampler(renderer,state)
    renderer.collect_anim=lambda x,m=renderer:collect_override(m,x)
    trans=list(poser.get("profileTranslation") or [0,0,0])
    while len(trans)<3:trans.append(0)
    wide=(float(poser.get("profileScale") or 1),trans)
    for _ in range(10):
        fixed=[render_one(renderer,info,state,clip,i,wide) for i in range(FRAME_COUNT)]
        if min(map(bbox_margin,fixed))>=16:break
        stats=inspect_frames(fixed,12)
        camera={"profileScale":wide[0],"profileTranslation":list(wide[1])}
        adjust_fixed_camera(camera,stats["alpha_bbox"],SIZE)
        wide=(float(camera["profileScale"]),list(camera["profileTranslation"]))
    fixed=[render_one(renderer,info,state,clip,i,wide) for i in range(FRAME_COUNT)]
    follow=limit_cameras(smooth_cameras([
       compute_target_camera(f.getchannel("A").getbbox(),*wide,target_extent=144)
       for f in fixed]),wide[0])
    v2,_,_=safe_render(renderer,"0384_rayquaza",info,state,clip,wide,follow)
    plan,weights=camera_plan(wide,follow,list(map(image_center,fixed)))
    v3,cameras,fallback=bounded_frames(renderer,info,state,clip,wide,plan,fixed)
    directory=args.out/"0384_rayquaza"
    directory.mkdir(parents=True,exist_ok=True)
    for label,frames in (("fixed",fixed),("v2",v2),("v3",v3)):
        sample_contact(frames,"Rayquaza physical attack "+label,directory/("physical_attack_"+label+"_contact.png"))
    new_jumps=jumps(v3);old_jumps=jumps(v2);base_jumps=jumps(fixed)
    margins=[bbox_margin(im) for im in v3]
    report={"schema_version":1,"purpose":"physical_attack_v3_review_only",
      "duration_sec":duration,"source_frames":FRAME_COUNT,
      "max_jump_fixed_px":max(base_jumps),"max_jump_v2_px":max(old_jumps),
      "max_jump_v3_px":max(new_jumps),"per_step_v3":new_jumps,
      "per_step_fixed":base_jumps,"fallback_frames":fallback,
      "min_margin_px":min(margins),"unsafe_frames":sum(m<12 for m in margins),
      "camera_strengths":weights,"approved_for_publication":False,
      "status":"visual_review_required"}
    # Preserve timing and decoded count for review; never overwrite V2.
    if report["unsafe_frames"]==0 and inspect_frames(v3,12)["motion_pass"]:
        target=directory/"physical_attack_v3.webp"
        ms=round(duration*1000/FRAME_COUNT)
        v3[0].save(target,format="WEBP",save_all=True,
           append_images=v3[1:],duration=ms,loop=0,quality=90,method=5)
        with Image.open(target) as check:
            total=0
            for i in range(check.n_frames):
                check.seek(i);total+=int(check.info.get("duration",0))
            report.update(webp_file=target.name,decoded_frames=check.n_frames,
                          decoded_duration_ms=total)
        report["status"]="candidate_unapproved"
    args.out.mkdir(parents=True,exist_ok=True)
    target=args.out/"physical-attack-v3-report.json"
    target.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({k:v for k,v in report.items() if not isinstance(v,list)},indent=2))
    print(target)

def main():
    p=argparse.ArgumentParser()
    for name in ("repo","resolved","out"):p.add_argument("--"+name,type=Path,required=True)
    run(p.parse_args())
if __name__=="__main__":main()
