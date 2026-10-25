"""Run with: python3 -m unittest discover -s tools -p 'test_*.py'"""
import json
import tempfile
import unittest
from pathlib import Path

from scan_animation_manifest import main, references


class ManifestTests(unittest.TestCase):
    def test_bedrock_quotes(self):
        _, calls = references({"x": "q.bedrock('idle','ground') and q.bedrock(\"fly\",\"air\")"})
        self.assertEqual(calls, [("idle", "ground"), ("fly", "air")])

    def test_isolation_and_resume(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            pack = root / "merged_pack"
            for folder in ("geo", "poser", "animations"):
                (pack / folder).mkdir(parents=True)
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
                {"id": "0094_gengar_mega", "pokemon_id": "0094", "form": "gengar_mega", "kind": "special", "image_path": "assets/pokemon-animated/0094_gengar_mega.webp"}
            ]))
            dest = root / "out.json"
            argv = ["--pack", f"merged_pack={pack}", "--index", str(index), "--output", str(dest), "--all"]
            self.assertEqual(main(argv), 0)
            payload = json.loads(dest.read_text())
            a, b = payload["entries"]
            self.assertEqual([x["clip_key"] for x in a["actions"]], ["animation.gengar.ground_idle"])
            self.assertEqual([x["clip_key"] for x in b["actions"]], ["animation.gengar_mega.fly"])
            self.assertEqual(a["actions"][0]["status"], "pending")
            self.assertIsNone(a["actions"][0]["file"])
            self.assertEqual(main(argv + ["--resume"]), 0)
            self.assertEqual(json.loads(dest.read_text())["summary"]["resumed_forms"], 2)


if __name__ == "__main__":
    unittest.main()
