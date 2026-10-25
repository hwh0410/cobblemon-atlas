#!/usr/bin/env python3
"""Review semantic quality of already-rendered action WebPs without altering them."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from PIL import Image, ImageDraw, ImageOps
import numpy as np

def examine(path: Path, *, samples: int = 6):
    with Image.open(path) as im:
        count = getattr(im, "n_frames", 1)
        indexes = sorted(set(round(i*(count-1)/(samples-1)) for i in range(samples))) if samples>1 else [0]
        frames=[]
        for i in indexes:
            im.seek(i)
            frames.append(im.convert("RGBA").copy())
    sizes=[]; coverage=[]; boxes=[]
    for f in frames:
        alpha=np.asarray(f.getchannel("A"))
        ys,xs=np.nonzero(alpha>8)
        if len(xs):
            box=[int(xs.min()),int(ys.min()),int(xs.max()+1),int(ys.max()+1)]
            sizes.append([round((box[2]-box[0])/f.width,3),round((box[3]-box[1])/f.height,3)])
            coverage.append(round(float(len(xs)/(f.width*f.height)),4))
        else:
            box=None;sizes.append([0,0]);coverage.append(0.)
        boxes.append(box)
    return frames,{"decoded_frames":count,"sampled_indices":indexes,"frame_bboxes":boxes,
        "bbox_width_fraction":[x[0] for x in sizes],
        "bbox_height_fraction":[x[1] for x in sizes],
        "alpha_coverage_fraction":coverage}

def contact_sheet(frames, title, target):
    size=frames[0].size
    pad=16
    canvas=Image.new("RGB",(len(frames)*(size[0]+pad)+pad,size[1]+58),(37,41,49))
    for idx,frame in enumerate(frames):
        x=pad+idx*(size[0]+pad)
        bg=Image.new("RGBA",size,(63,69,79,255))
        bg.alpha_composite(frame)
        canvas.paste(bg.convert("RGB"),(x,36))
    dr=ImageDraw.Draw(canvas)
    dr.text((pad,10),title,fill=(255,255,255))
    target.parent.mkdir(parents=True,exist_ok=True)
    canvas.save(target,format="PNG")

def audit(root, form_actions, out, manifest, min_short_side=.22, max_refits=4):
    idx={e["form_id"]:e for e in manifest.get("entries",[])}
    report={"schema_version":1,"policy":"review_only_no_webp_mutations","jobs":{}}
    for form,action in form_actions:
        key=f"{form}/{action}"
        path=root/"renders"/form/(action+".webp")
        if not path.is_file():
            report["jobs"][key]={"review":"missing","reason":"webp_not_found"}
            continue
        frames,metrics=examine(path)
        choices=[a for a in idx.get(form,{}).get("actions",[])
                 if a.get("clip_key","").rsplit(".",1)[-1]==action]
        choices.sort(key=lambda a:(a.get("model_bones_matched",0),a.get("source_pack")=="merged_pack"),reverse=True)
        selected=choices[0] if choices else {}
        previous=json.loads((root/"checkpoints/render-jobs.json").read_text()).get("jobs",{}).get(key,{})
        flags=[]
        if "old" in action.lower() or "test" in action.lower():flags.append("legacy_or_test_clip_name")
        if min(min(a,b) for a,b in zip(metrics["bbox_width_fraction"],metrics["bbox_height_fraction"])) < min_short_side:
            flags.append("small_projected_short_side")
        if previous.get("framing_attempts",0)>max_refits:flags.append("many_framing_attempts")
        if selected.get("model_bones_matched",0)<=0:flags.append("bone_match_not_verified")
        if not flags:flags.append("requires_human_motion_review")
        target=out/(form+"_"+action+"_contact.png")
        contact_sheet(frames,key,target)
        report["jobs"][key]={"review":"manual_required","flags":flags,"source_pack":previous.get("source_pack"),
            "clip_key":previous.get("clip_key"),"prior_status":previous.get("status"),
            "framing_attempts":previous.get("framing_attempts"),
            "model_bones_matched":selected.get("model_bones_matched"),
            "dynamic_bones":selected.get("dynamic_bones"),"poser_paths":selected.get("poser_paths",[]),
            "contact_sheet":target.name,**metrics}
    out.mkdir(parents=True,exist_ok=True)
    dest=out/"semantic-audit.json"
    dest.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    return dest

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--drive-root",type=Path,required=True)
    p.add_argument("--manifest",type=Path,required=True)
    p.add_argument("--out",type=Path,required=True)
    p.add_argument("--min-short-side",type=float,default=.22)
    a=p.parse_args()
    entries=json.loads(a.manifest.read_text())
    jobs=[("0384_rayquaza","ground_walk"),("0384_rayquaza","physical_attackold2"),
          ("0384_rayquaza","ground_idle"),("0150_mewtwo","pose_fly"),
          ("0150_mewtwo","air_fly"),("0150_mewtwo","pose_hover")]
    result=audit(a.drive_root,jobs,a.out,entries,a.min_short_side)
    print("Semantic audit:",result)
if __name__=="__main__":
    main()
