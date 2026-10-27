#!/usr/bin/env python3
"""Audit decoded animated WebP timing and motion without re-rendering source assets."""
import argparse
import json
import math
from pathlib import Path
import numpy as np
from PIL import Image

def audit_file(path, expected_duration_seconds=None, expected_source_frames=48):
    with Image.open(path) as image:
        n=getattr(image,"n_frames",1)
        records=[]
        previous=None
        for index in range(n):
            image.seek(index)
            frame=image.convert("RGBA")
            rgba=np.asarray(frame,dtype=np.uint8)
            mask=rgba[:,:,3]>16
            pixels=np.argwhere(mask)
            if len(pixels):
                cy,cx=np.mean(pixels,axis=0)
                extent=[int(pixels[:,1].min()),int(pixels[:,0].min()),
                        int(pixels[:,1].max())+1,int(pixels[:,0].max())+1]
            else:
                cx=cy=0.0;extent=None
            duration=int(image.info.get("duration",0) or 0)
            if previous is None:
                changed=0
            else:
                changed=int(np.count_nonzero(np.max(np.abs(
                    rgba.astype(np.int16)-previous.astype(np.int16)),axis=2)>10))
            records.append(dict(index=index,duration_ms=duration,alpha_bbox=extent,
                                center_x=round(float(cx),2),center_y=round(float(cy),2),
                                changed_pixels_previous=changed))
            previous=rgba
    timing_ms=sum(r["duration_ms"] for r in records)
    expected_ms=(round(expected_duration_seconds*1000/expected_source_frames)*expected_source_frames
                 if expected_duration_seconds else None)
    jumps=[math.hypot(b["center_x"]-a["center_x"],b["center_y"]-a["center_y"])
           for a,b in zip(records,records[1:]) if a["alpha_bbox"] and b["alpha_bbox"]]
    change=[r["changed_pixels_previous"] for r in records[1:]]
    comparison=(None if not expected_ms or timing_ms==0 else abs(timing_ms-expected_ms)/expected_ms)
    warnings=[]
    if n < 2: warnings.append("single_frame")
    if not timing_ms: warnings.append("missing_duration_metadata")
    if comparison is not None and comparison > 0.08: warnings.append("duration_mismatch_over_8_percent")
    if any((r["alpha_bbox"] is None) for r in records): warnings.append("blank_frame")
    if jumps and max(jumps)>35: warnings.append("large_centroid_step_review")
    if change and max(change)>14000: warnings.append("large_frame_pixel_change_review")
    return dict(file=path.name,expected_source_frames=expected_source_frames,
        decoded_frames=n,merged_frame_count=max(0,expected_source_frames-n),
        decoded_duration_ms=timing_ms,expected_duration_ms=expected_ms,
        duration_error_fraction=None if comparison is None else round(comparison,4),
        max_centroid_step_px=round(max(jumps,default=0),2),
        max_changed_pixels_adjacent=max(change,default=0),
        note="Fewer decoded frames may reflect WebP frame coalescing, not data loss.",
        warnings=warnings,quality_status="review_required" if warnings else "timing_pass_visual_review_pending",
        approved_for_publication=False,frames=records)

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--input",required=True,type=Path)
    p.add_argument("--out",required=True,type=Path)
    args=p.parse_args()
    expected={"physical_attack":4.75,"special_attack":4.8333}
    output={"schema_version":1,"purpose":"webp_timing_qc_no_publication","files":{}}
    for name,seconds in expected.items():
        f=args.input/"0384_rayquaza"/(name+"_safe.webp")
        if not f.is_file():
            output["files"][name]={"status":"missing_file"};continue
        output["files"][name]=audit_file(f,seconds)
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(output,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    for k,v in output["files"].items():
        print(k,v.get("quality_status",v.get("status")),
              "frames",v.get("decoded_frames"),"ms",v.get("decoded_duration_ms"),
              "warnings",v.get("warnings"),flush=True)
    print("REPORT",args.out)

if __name__=="__main__": main()
