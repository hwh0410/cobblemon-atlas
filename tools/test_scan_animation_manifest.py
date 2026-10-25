"""Run with: python3 -m unittest discover -s tools -p 'test_*.py'"""
import json
import tempfile
import unittest
from pathlib import Path

from scan_animation_manifest import main, references, value_digest


class ManifestTests(unittest.TestCase):
    def test_clip_hash_ignores_json_key_order(self):
        self.assertEqual(value_digest({"bones": {"body": {"rotation": [0, 1, 0]}}, "loop": True}),
                         value_digest({"loop": True, "bones": {"body": {"rotation": [0, 1, 0]}}}))
        self.assertNotEqual(value_digest({"loop": True}), value_digest({"loop": False}))

    def test_bedrock_quotes(self):
        _, calls = references({"x": "q.bedrock('idle','ground') and q.bedrock(\"fly\",\"air\")"})
        self.assertEqual(calls, [("idle", "ground"), ("fly", "air")])

    def test_isolation_and_resume(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            pack = root / "merged_pack"
            for folder in ("geo", "poser", "animations"):
                (pack / folder).mkdir(parents=True)
            (pack / "bedrock/pokemon/resolvers/0130_gyarados").mkdir(parents=True)
            (pack / "bedrock/pokemon/posers/0130_gyarados").mkdir(parents=True)
            (pack / "bedrock/pokemon/models/0130_gyarados").mkdir(parents=True)
            (pack / "bedrock/pokemon/animations/0130_gyarados").mkdir(parents=True)
            (pack / "bedrock/pokemon/resolvers/0130_gyarados/2_gyarados_mega.json").write_text(json.dumps({"species": "cobblemon:gyarados", "variations": [{"aspects": ["mega"], "model": "cobblemon:gyarados_mega.geo"}]}))
            (pack / "bedrock/pokemon/posers/0130_gyarados/gyarados.json").write_text(json.dumps({"poses": []}))
            (pack / "bedrock/pokemon/models/0130_gyarados/gyarados_mega.geo.json").write_text(json.dumps({"minecraft:geometry": [{"bones": [{"name": "fin"}]}]}))
            (pack / "bedrock/pokemon/animations/0130_gyarados/gyarados.animation.json").write_text(json.dumps({"animations": {"animation.gyarados.air_idle": {"bones": {"fin": {"rotation": {"0": [0, 0, 0], "1": [1, 0, 0]}}}}}}))
            (pack / "geo/gengar.geo.json").write_text(json.dumps({"minecraft:geometry": [{"bones": [{"name": "body"}]}]}))
            (pack / "geo/gengar_mega.geo.json").write_text(json.dumps({"minecraft:geometry": [{"bones": [{"name": "wing"}]}]}))
            (pack / "poser/gengar.json").write_text(json.dumps({"idle": "animation.gengar.ground_idle"}))
            (pack / "animations/moves.json").write_text(json.dumps({"animations": {
                "animation.gengar.ground_idle": {"bones": {"body": {"rotation": {"0.0": [0, 0, 0], "1.0": [0, 10, 0]}}}},
                "animation.gengar_mega.fly": {"bones": {"wing": {"rotation": {"0.0": [0, 0, 0], "1.0": [0, 20, 0]}}}}
            }}))
            index = root / "index.json"
            index.write_text(json.dumps([
                {"id": "0094_gengar", "pokemon_id": "0094", "form": "gengar", "kind": "base", "image_path": "assets/pokemon-animated/0094_gengar.webp"},
                {"id": "0094_gengar_mega", "pokemon_id": "0094", "form": "gengar_mega", "kind": "special", "image_path": "assets/pokemon-animated/0094_gengar_mega.webp"},
                {"id": "0130_gyarados_mega", "pokemon_id": "0130", "form": "gyarados_mega", "kind": "special", "image_path": "assets/pokemon-animated/0130_gyarados_mega.webp"}
            ]))
            dest = root / "out.json"
            argv = ["--pack", f"merged_pack={pack}", "--index", str(index), "--output", str(dest), "--all"]
            self.assertEqual(main(argv), 0)
            payload = json.loads(dest.read_text())
            a, b, mega = payload["entries"]
            self.assertEqual([x["clip_key"] for x in a["actions"]], ["animation.gengar.ground_idle"])
            self.assertEqual([x["clip_key"] for x in b["actions"]], ["animation.gengar_mega.fly"])
            self.assertEqual(a["actions"][0]["status"], "pending")
            self.assertIsNone(a["actions"][0]["file"])
            self.assertEqual(len(mega["actions"]), 1)
            self.assertEqual(mega["actions"][0]["model_bones_matched"], 1)
            self.assertEqual(mega["actions"][0]["evidence"], "audit")
            self.assertIn("shared_poser_requires_link_validation", mega["actions"][0]["reason"])
            self.assertTrue(mega["resources"]["resolver"])
            self.assertEqual(main(argv + ["--resume"]), 0)
            self.assertEqual(json.loads(dest.read_text())["summary"]["resumed_forms"], 3)


if __name__ == "__main__":
    unittest.main()
