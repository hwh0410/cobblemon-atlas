import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from compare_animation_sources import clip_features, scan


class SourceComparisonTests(unittest.TestCase):
    def test_temporal_evidence(self):
        bones = {"head"}
        animated = {"bones": {"head": {"rotation": {"0.0": [0, 0, 0], "1.0": [10, 0, 0]}}}}
        fixed = {"bones": {"head": {"rotation": [10, 0, 0]}}}
        self.assertEqual(clip_features(animated, bones)["motion_evidence"], "keyframes")
        self.assertEqual(clip_features(fixed, bones)["motion_evidence"], "static_or_unproven")
        self.assertEqual(clip_features({"bones": {"head": {"rotation": "math.sin(q.anim_time)"}}}, bones)["motion_evidence"], "time_expression")
        self.assertEqual(clip_features({"bones": {"locator_item": {"position": "q.anim_time"}}}, {"locator_item"})["motion_evidence"], "static_or_unproven")

    def test_zip_scanner_selects_sources_without_extracting(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            merged = td / "merged.zip"
            development = td / "dev.zip"
            pose = {"poses": {"standing": {"animations": ["q.bedrock('mewtwo', 'ground_idle')"]}}}
            static = {"animations": {"animation.mewtwo.ground_idle": {
                "bones": {"head": {"rotation": [0, 0, 0]}}}}}
            dynamic = {"animations": {"animation.mewtwo.ground_idle": {
                "bones": {"head": {"rotation": {"0.0": [0, 0, 0], "1.0": [5, 0, 0]}}}}}}
            with zipfile.ZipFile(merged, "w") as archive:
                archive.writestr("merged_pack/bedrock/pokemon/posers/0150_mewtwo/mewtwo.json", json.dumps(pose))
                archive.writestr("merged_pack/bedrock/pokemon/animations/0150_mewtwo/a.animation.json", json.dumps(static))
            with zipfile.ZipFile(development, "w") as archive:
                archive.writestr("development_resource_packs/cobblemon/animations/0150_mewtwo/a.animation.json", json.dumps(dynamic))
            resolved = {"forms": [{"form_id": "0150_mewtwo", "selected": {
                "model": "mewtwo.geo.json", "poser": "bedrock/pokemon/posers/0150_mewtwo/mewtwo.json",
                "bone_names": ["head"]}}]}
            report = scan(merged, development, resolved, ["0150_mewtwo"])["forms"]["0150_mewtwo"]
            self.assertEqual(report["summary"]["same_key_different_content"], 1)
            self.assertEqual(report["summary"]["potential_dynamic_versions"], 1)
            self.assertTrue(report["promising_candidates"][0]["referenced_by_resolver_poser"])
            self.assertEqual(report["promising_candidates"][0]["source_pack"], "development_resource_packs")


if __name__ == "__main__":
    unittest.main()
