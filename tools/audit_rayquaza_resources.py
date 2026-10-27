#!/usr/bin/env python3
"""Inventory Rayquaza model/poser/resolver/entity/animation references across packs.

Read-only over source packs; writes a structured evidence report to --out.
This does not assume that similarly named files represent the in-game default.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

BEDROCK = re.compile(
    r"q\.(bedrock|bedrock_stateful|bedrock_quirk)\(\s*(['\"])(.*?)\2\s*,\s*(['\"])(.*?)\4\s*\)",
    re.I,
)


def get_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8-sig")), None
    except (OSError, ValueError, UnicodeError) as exc:
        return None, str(exc)


def clips_in(value):
    if isinstance(value, str):
        return [{"reference": f"animation.{m.group(3)}.{m.group(5)}",
                 "function": m.group(1), "expression": value} for m in BEDROCK.finditer(value)]
    if isinstance(value, list):
        return [x for item in value for x in clips_in(item)]
    if isinstance(value, dict):
        return [x for item in value.values() for x in clips_in(item)]
    return []


def geometry_details(data):
    geometries = data.get("minecraft:geometry", []) if isinstance(data, dict) else []
    if isinstance(geometries, dict):
        geometries = [geometries]
    output=[]
    for geo in geometries:
        if not isinstance(geo, dict):
            continue
        desc=geo.get("description",{})
        bones=geo.get("bones",[])
        names=[b.get("name") for b in bones if isinstance(b,dict) and b.get("name")]
        output.append({
            "identifier":desc.get("identifier"), "bones":len(names),
            "bone_names":names,
            "roots":[b.get("name") for b in bones if isinstance(b,dict) and not b.get("parent")],
        })
    return output


def paths_for(root, pack):
    if pack=="merged_pack":
        folders=("bedrock/pokemon/posers/0384_rayquaza",
                 "bedrock/pokemon/resolvers/0384_rayquaza",
                 "bedrock/pokemon/models/0384_rayquaza",
                 "bedrock/pokemon/animations/0384_rayquaza")
    else:
        folders=("cobblemon/animations/0384_rayquaza",
                 "cobblemon/models/entity/0384_rayquaza",
                 "cobblemon/models/entity/0384_rayquaza_mega",
                 "cobblemon/entity")
    paths=[]
    for folder in folders:
        base=root/folder
        if not base.exists():
            continue
        for p in sorted(base.rglob("*.json")):
            if pack=="development_resource_packs" and folder=="cobblemon/entity" and "rayquaza" not in p.name.lower():
                continue
            paths.append(p)
    return sorted(set(paths))


def summarize(path, root, pack, data):
    rel=path.relative_to(root).as_posix()
    stem=path.name.lower()
    x={"pack":pack,"path":rel,
       "sha256":hashlib.sha256(path.read_bytes()).hexdigest(),
       "kind":"other"}
    if "poser" in rel and isinstance(data,dict):
        x["kind"]="poser"
        x["root_bone"]=data.get("rootBone")
        x["profile_scale"]=data.get("profileScale")
        x["poses"]={}
        for name,pose in data.get("poses",{}).items():
            x["poses"][name]={
                "pose_types":pose.get("poseTypes",[]),
                "is_battle":pose.get("isBattle",False),
                "conditions":pose.get("condition"),
                "references":clips_in({"animations":pose.get("animations",[]),
                                       "namedAnimations":pose.get("namedAnimations",{}),
                                       "quirks":pose.get("quirks",[])}),
                "unresolved_expressions":[v for v in pose.get("animations",[])
                                         if isinstance(v,str) and not BEDROCK.search(v)],
            }
    elif "resolvers" in rel:
        x["kind"]="resolver"
        x["species"]=data.get("species") if isinstance(data,dict) else None
        x["variations"]=[{"aspects":v.get("aspects",[]),"model":v.get("model"),
                           "texture":v.get("texture"),"poser":v.get("poser")}
                         for v in data.get("variations",[]) if isinstance(v,dict)] if isinstance(data,dict) else []
    elif "animations" in rel and isinstance(data,dict):
        x["kind"]="animations"
        x["clips"]={key:{"length":val.get("animation_length"),
                          "loop":val.get("loop"),
                          "bones":list(val.get("bones",{}))}
                    for key,val in data.get("animations",{}).items() if isinstance(val,dict)}
    elif ".geo.json" in stem and isinstance(data,dict):
        x["kind"]="geometry"
        x["geometries"]=geometry_details(data)
    elif ".entity.json" in stem and isinstance(data,dict):
        x["kind"]="entity"
        x["description"]=data.get("minecraft:client_entity",{}).get("description",{})
    return x


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--repo",required=True,type=Path)
    p.add_argument("--out",required=True,type=Path)
    args=p.parse_args()
    repo=args.repo.expanduser().resolve()
    resources=[];parse_errors=[]
    for pack in ("merged_pack","development_resource_packs"):
        root=repo/pack
        if not root.is_dir():
            raise FileNotFoundError(root)
        for path in paths_for(root,pack):
            data,error=get_json(path)
            if error:
                parse_errors.append({"path":str(path),"error":error})
                continue
            resources.append(summarize(path,root,pack,data))
    clip_keys={}
    for item in resources:
        if item["kind"]=="animations":
            for key in item["clips"]:
                clip_keys.setdefault(key,[]).append({"pack":item["pack"],"path":item["path"]})
    geometry_names={i["identifier"]:i for x in resources if x["kind"]=="geometry"
                    for i in x["geometries"]}
    missing=[]
    for x in resources:
        if x["kind"]!="poser":
            continue
        for pose_name,pose in x["poses"].items():
            for ref in pose["references"]:
                if ref["reference"] not in clip_keys:
                    missing.append({"poser":x["path"],"pose":pose_name,
                                    "clip":ref["reference"]})
    output={
        "schema_version":1,"purpose":"resource_mapping_not_render_validation",
        "resources":resources,
        "summary":{"total_json":len(resources),
                   "kinds":{kind:sum(x["kind"]==kind for x in resources)
                            for kind in sorted({x["kind"] for x in resources})},
                   "poser_paths":[x["path"] for x in resources if x["kind"]=="poser"],
                   "geometry_identifiers":sorted(k for k in geometry_names if isinstance(k,str)),
                   "missing_poser_clips":missing,
                   "parse_errors":parse_errors},
        "limitations":[
            "Resolver and client entity references are listed, but runtime variant choice may be conditional.",
            "Kotlin / resource pack precedence or extra non-JSON sources require separate runtime verification.",
        ],
    }
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(output,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(output["summary"],ensure_ascii=False,indent=2))
    print("Written:",args.out)


if __name__=="__main__":
    main()
