#!/usr/bin/env python3
"""Controlled Rayquaza pose-layer comparison, without writing website or official renders."""
from __future__ import annotations

import argparse
import importlib.util
import json
import shutil
from pathlib import Path

from PIL import Image, ImageDraw

from render_action_jobs import channel_sampler, choose_actions, inspect_frames, ranked_poser_paths

VARIANTS = {
    "rest": (),
    "ground_idle": ("ground_idle",),
    "ground_walk": ("ground_walk",),
    "idle_plus_walk": ("ground_idle", "ground_walk"),
}


def load_renderer(path):
    spec = importlib.util.spec_from_file_location("atlas_compare_original", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load renderer {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def clip_source(root, action):
    rel = Path(action["animation_path"])
    if rel.is_absolute() or ".." in rel.parts:
        raise ValueError("Unsafe clip path")
    path = root / action["source_pack"] / rel
    if not path.is_file():
        raise FileNotFoundError(path)
    return path


def sample_contact(frames, label, output, sample_count=6):
    indexes = sorted(set(round(i * (len(frames) - 1) / (sample_count - 1))
                         for i in range(sample_count)))
    selected = [frames[i] for i in indexes]
    w, h = selected[0].size
    margin = 12
    sheet = Image.new("RGB", ((w + margin) * len(selected) + margin, h + 40), (35, 40, 48))
    draw = ImageDraw.Draw(sheet)
    draw.text((margin, 8), label + " — frames " + ",".join(map(str, indexes)), fill="white")
    for i, frame in enumerate(selected):
        panel = Image.new("RGBA", (w, h), (66, 73, 83, 255))
        panel.alpha_composite(frame.convert("RGBA"))
        sheet.paste(panel.convert("RGB"), (margin + i * (w + margin), 32))
    sheet.save(output)


def run(repo, manifest, out, size, fps, seconds, ss):
    form = "0384_rayquaza"
    entries = json.loads(manifest.read_text(encoding="utf-8")).get("entries", [])
    selected = choose_actions(entries, {form}, ["ground_idle", "ground_walk"])
    actions = {name: action for _, action, name in selected}
    if set(actions) != {"ground_idle", "ground_walk"}:
        raise RuntimeError("Manifest missing Rayquaza ground_idle or ground_walk")
    source_names = {a["source_pack"] for a in actions.values()}
    if source_names != {"merged_pack"}:
        raise RuntimeError(f"Expected one merged_pack source: {source_names}")
    renderer = load_renderer(repo / "tools/render_portraits.py")
    loaded = {}
    for name, action in actions.items():
        loaded[name] = renderer.load_json(str(clip_source(repo, action)))["animations"][action["clip_key"]]

    info = renderer.find_animations(form, "rayquaza")
    poser_paths = ranked_poser_paths(actions["ground_walk"].get("poser_paths", []), form)
    for rel in poser_paths:
        p = repo / "merged_pack" / rel
        if p.is_file() and p.stem == "rayquaza":
            poser = renderer.load_json(str(p))
            info["profileScale"] = poser.get("profileScale", info.get("profileScale", 1.0))
            info["profileTranslation"] = poser.get("profileTranslation", info.get("profileTranslation", [0, 0, 0]))
            info["poser"] = str(p)
            break
    # Use identical camera for all variants, including the large-amplitude poses.
    # This is a diagnostic preset derived from the previously verified fit run.
    info["profileScale"] = 0.2
    info["profileTranslation"] = [0.0, 0.9126984126984127, -10]
    chosen_poser = info.get("poser")
    old_find = renderer.find_animations
    renderer.find_animations = lambda folder, species: info
    state = {"time": 0.0, "period": seconds, "loop": True}
    renderer.channel_at_zero = channel_sampler(renderer, state)
    out.mkdir(parents=True, exist_ok=True)
    report = {"schema_version": 1, "form": form, "fps": fps, "seconds": seconds,
              "fixed_camera": {"scale": 0.2, "translation": info["profileTranslation"]},
              "poser": chosen_poser, "variants": {}}
    try:
        count = max(2, round(fps * seconds))
        for name, clip_names in VARIANTS.items():
            info["clips"] = [(actions[n]["clip_key"], loaded[n]) for n in clip_names]
            frames = []
            for k in range(count):
                state["time"] = seconds * k / count
                frame, _ = renderer.render_species(form, size=size, ss=ss, frame="cobblemon",
                                                   rest=(name == "rest"))
                frames.append(frame.convert("RGBA"))
            stats = inspect_frames(frames, 12)
            sample_contact(frames, name, out / (name + "_contact.png"))
            # Each variant is diagnostic, not playable / published.
            output = out / (name + ".webp")
            frames[0].save(output, format="WEBP", save_all=True, append_images=frames[1:],
                           duration=round(1000 / fps), loop=0, quality=90, method=5)
            report["variants"][name] = {
                "clip_keys": [actions[n]["clip_key"] for n in clip_names],
                "visual_status": "requires_human_review", "file": output.name,
                "contact": name + "_contact.png", **stats,
            }
            print(name, "motion:", stats["changed_pixels_max"], "bbox:", stats["alpha_bbox"],
                  "margin:", stats["min_margin_px"], flush=True)
    finally:
        renderer.find_animations = old_find
    (out / "pose-layer-comparison.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--size", type=int, default=224)
    parser.add_argument("--fps", type=int, default=12)
    parser.add_argument("--seconds", type=float, default=2.0)
    parser.add_argument("--ss", type=int, default=2)
    args = parser.parse_args()
    run(args.repo.resolve(), args.manifest, args.out, args.size, args.fps, args.seconds, args.ss)


if __name__ == "__main__":
    main()
