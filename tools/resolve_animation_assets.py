#!/usr/bin/env python3
"""Resolve model/poser/texture per form from Cobblemon Resolver JSON.

Conservative: ambiguous or missing selections remain audit rather than silently
falling back to a similarly named prepared model. No source files are modified.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def sha256(path):
    h=hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda:f.read(1024*1024),b""):
            h.update(block)
    return h.hexdigest()


def form_parts(form):
    bits=form.split("_")
    if len(bits)<2 or not bits[0].isdigit():
        raise ValueError(f"Unsupported form ID: {form}")
    aspects=[]
    species=bits[1]
    # This is intentionally limited; unfamiliar suffixes must be audited.
    for term in bits[2:]:
        if term in {"mega","shiny","gmax","alolan","galarian","hisuian","paldean"}:
            aspects.append(term)
        else:
            aspects.append(term)
    return bits[0]+"_"+species,aspects


def resolve_one(root,form):
    folder,aspects=form_parts(form)
    base=root/"bedrock/pokemon"
    resolver_folder=base/"resolvers"/folder
    evidence=[]
    for file in sorted(resolver_folder.glob("*.json")):
        try:
            contents=json.loads(file.read_text(encoding="utf-8-sig"))
        except (OSError,ValueError,UnicodeError):
            continue
        for idx,var in enumerate(contents.get("variations",[])):
            if not isinstance(var,dict):
                continue
            va=var.get("aspects",[])
            if not isinstance(va,list):
                continue
            # Unknown aspect semantics and partial variants are not inferred.
            if sorted(va)!=sorted(aspects):
                continue
            if not var.get("model"):
                continue
            evidence.append((file,idx,var))
    output={"form_id":form,"aspects":aspects,"status":"audit","reason":None,
            "candidate_count":len(evidence),"candidates":[]}
    for file,idx,var in evidence:
        mname=var["model"].split(":")[-1]
        stem=mname[:-4] if mname.endswith(".geo") else mname
        model=base/"models"/folder/(stem+".geo.json")
        pname=var.get("poser")
        poser=base/"posers"/folder/(pname.split(":")[-1]+".json") if pname else None
        texture=var.get("texture")
        texpath=root/texture.split(":",1)[-1] if texture else None
        if texpath and not texpath.suffix:
            texpath=texpath.with_suffix(".png")
        evidence_row={"resolver":str(file.relative_to(root)),"variation":idx,
                      "model":str(model.relative_to(root)),
                      "poser":str(poser.relative_to(root)) if poser else None,
                      "texture":str(texpath.relative_to(root)) if texpath else None,
                      "model_exists":model.is_file(),
                      "poser_exists":poser.is_file() if poser else False,
                      "texture_exists":texpath.is_file() if texpath else False}
        if model.is_file():
            evidence_row["model_sha256"]=sha256(model)
            data=json.loads(model.read_text(encoding="utf-8-sig"))
            bones=[b.get("name") for g in data.get("minecraft:geometry",[])
                   for b in g.get("bones",[]) if b.get("name")]
            evidence_row["bone_count"]=len(bones)
            evidence_row["bone_names"]=bones
        if poser and poser.is_file():
            evidence_row["poser_sha256"]=sha256(poser)
            evidence_row["poses"]=list(json.loads(poser.read_text(encoding="utf-8-sig")).get("poses",{}))
        if texpath and texpath.is_file():
            evidence_row["texture_sha256"]=sha256(texpath)
        output["candidates"].append(evidence_row)
    valid=[x for x in output["candidates"]
           if x["model_exists"] and x["poser_exists"] and x["texture_exists"]]
    if len(valid)==1:
        output["status"]="resolved"
        output["selected"]=valid[0]
    elif len(valid)>1:
        output["reason"]="multiple_valid_resolver_variations"
    elif not evidence:
        output["reason"]="no_explicit_matching_resolver_variant"
    else:
        output["reason"]="missing_model_poser_or_texture"
    return output


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--repo",required=True,type=Path)
    p.add_argument("--forms",required=True,nargs="+")
    p.add_argument("--out",required=True,type=Path)
    args=p.parse_args()
    root=args.repo.resolve()/"merged_pack"
    if not root.is_dir():
        raise FileNotFoundError(root)
    entries=[resolve_one(root,form) for form in args.forms]
    report={"schema_version":1,"source_pack":"merged_pack","forms":entries,
            "summary":{"resolved":sum(x["status"]=="resolved" for x in entries),
                       "audit":sum(x["status"]=="audit" for x in entries)}}
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(report["summary"],ensure_ascii=False))
    for item in entries:
        print(item["form_id"],item["status"],item.get("reason"),
              item.get("selected",{}).get("bone_count"))


if __name__=="__main__":
    main()
