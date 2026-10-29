#!/usr/bin/env python3
"""Compare old 100-bone prepared Rayquaza with resolver-selected 51-bone model.

Monkeypatches only this process's renderer lookup; never edits packs, checkpoints
or website files. Candidate animations are not production quality.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import numpy as np
from PIL import Image

from compare_pose_layers import load_renderer, sample_contact
from render_action_jobs import channel_sampler, inspect_frames

CLIP = re.compile(r"q\.bedrock\(\s*(['\"])(.*?)\1\s*,\s*(['\"])(.*?)\3\s*\)",re.I)


def pose_keys(pose, available):
    keys=[]
    for obj in pose.get("animations",[]):
        expr=obj if isinstance(obj,str) else ""
        match=CLIP.search(expr)
        if match:
            key=f"animation.{match.group(2)}.{match.group(4)}"
            if key in available:
                keys.append(key)
    return keys


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--repo",type=Path,required=True)
    p.add_argument("--out",type=Path,required=True)
    args=p.parse_args()
    repo=args.repo.resolve();out=args.out.resolve();out.mkdir(parents=True,exist_ok=True)
    resolver_file=repo/"merged_pack/bedrock/pokemon/resolvers/0384_rayquaza/0_rayquaza_base.json"
    resolver=json.loads(resolver_file.read_text(encoding="utf-8-sig"))
    variation=next(v for v in resolver["variations"] if not v.get("aspects"))
    assert variation["model"]=="cobblemon:rayquaza2.geo",variation
    assert variation["poser"]=="cobblemon:rayquaza2",variation
    geometry_file=repo/"merged_pack/bedrock/pokemon/models/0384_rayquaza/rayquaza2.geo.json"
    geometry=json.loads(geometry_file.read_text(encoding="utf-8-sig"))["minecraft:geometry"][0]
    assert len(geometry["bones"])==51
    poser_file=repo/"merged_pack/bedrock/pokemon/posers/0384_rayquaza/rayquaza2.json"
    poser=json.loads(poser_file.read_text(encoding="utf-8-sig"))
    anim_dir=repo/"merged_pack/bedrock/pokemon/animations/0384_rayquaza"
    animations={}
    for file in sorted(anim_dir.glob("*.animation.json")):
        animations.update(json.loads(file.read_text(encoding="utf-8-sig")).get("animations",{}))
    renderer=load_renderer(repo/"tools/render_portraits.py")
    info=renderer.find_animations("0384_rayquaza","rayquaza")
    info["profileScale"]=poser.get("profileScale",1.0)
    info["profileTranslation"]=poser.get("profileTranslation",[0,0,0])
    info["poser"]=str(poser_file)
    base_index=renderer.geo_index()
    assert "geometry.rayquaza" in base_index
    old_geometry=base_index["geometry.rayquaza"]
    old_lookup=renderer.geo_index
    old_find=renderer.find_animations
    old_texture=renderer.load_texture
    src_texture=repo/"merged_pack/textures/pokemon/0384_rayquaza/rayquaza.png"
    if not src_texture.is_file():
        raise FileNotFoundError(src_texture)
    tex=np.asarray(Image.open(src_texture).convert("RGBA"),dtype=np.float32)/255
    state={"time":0.0,"period":2.0,"loop":True}
    renderer.channel_at_zero=channel_sampler(renderer,state)
    report={"resolver":variation,"geometry_file":str(geometry_file),
            "poser_file":str(poser_file),
            "legacy_bones":len(old_geometry["bones"]),
            "resolver_bones":len(geometry["bones"]),"experiments":{},
            "limitations":["Uses the existing CPU renderer; other runtime pose conditions are not implemented.",
                           "Per-frame fit is diagnostic and may introduce camera motion.",
                           "Correct pose appearance still requires visual comparison to the game."]}
    try:
        for name,model,pose_name in [
            ("legacy_100_rest",old_geometry,None),
            ("resolver_51_rest",geometry,None),
            ("resolver_51_standing",geometry,"standing"),
            ("resolver_51_walking",geometry,"walking"),
            ("resolver_51_fly",geometry,"fly"),
            ("resolver_51_hover",geometry,"hover"),
        ]:
            if pose_name and pose_name not in poser.get("poses",{}):
                continue
            clips=pose_keys(poser["poses"][pose_name],animations) if pose_name else []
            if pose_name and not clips:
                continue
            info["clips"]=[(key,animations[key]) for key in clips]
            override=dict(base_index)
            override["geometry.rayquaza"]=model
            renderer.geo_index=lambda o=override:o
            renderer.find_animations=lambda folder,species,inf=info:inf
            renderer.load_texture=lambda path,fn=old_texture: (tex if path and
                "textures/entity/0384_rayquaza/rayquaza" in path and
                "shiny" not in path else fn(path))
            frames=[]
            for i in range(24):
                state["time"]=i/12
                img,_=renderer.render_species("0384_rayquaza",size=224,ss=2,frame="fit",
                                               rest=(pose_name is None))
                frames.append(img.convert("RGBA"))
            sample_contact(frames,name,out/(name+"_contact.png"))
            target=out/(name+".webp")
            frames[0].save(target,format="WEBP",save_all=True,append_images=frames[1:],
                           duration=83,loop=0,quality=90,method=5)
            stats=inspect_frames(frames,12)
            report["experiments"][name]={"clip_keys":clips,**stats,
                "contact":name+"_contact.png","webp":name+".webp"}
            print(name,"clips",clips,"motion",stats["changed_pixels_max"],flush=True)
    finally:
        renderer.geo_index=old_lookup
        renderer.find_animations=old_find
        renderer.load_texture=old_texture
    target=out/"resolver-model-comparison.json"
    target.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print("Report:",target)


if __name__=="__main__":
    main()
