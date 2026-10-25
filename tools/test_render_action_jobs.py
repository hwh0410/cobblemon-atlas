import tempfile
import unittest
from pathlib import Path

from PIL import Image

from render_action_jobs import atomic_json, channel_sampler, inspect_frames, adjust_fixed_camera, choose_actions


class FakeRenderer:
    @staticmethod
    def molang(value, t=0):
        return float(value)


class RenderActionTests(unittest.TestCase):
    def test_prefer_dynamic_duplicate_but_allow_exact_variant(self):
        entries = [{"form_id":"0249_lugia","actions":[
            {"id":"air_idle","clip_key":"animation.lugia.air_idle","source_pack":"development_resource_packs","model_bones_matched":0,"dynamic_bones":0,"evidence":"audit"},
            {"id":"air_idle_abcd1234","clip_key":"animation.lugia.air_idle","source_pack":"merged_pack","model_bones_matched":48,"dynamic_bones":49,"evidence":"audit"}
        ]}]
        selected = choose_actions(entries,{"0249_lugia"},["air_idle"])
        self.assertEqual(selected[0][1]["source_pack"],"merged_pack")
        self.assertEqual(selected[0][2],"air_idle")
        exact = choose_actions(entries,{"0249_lugia"},["air_idle_abcd1234"])
        self.assertEqual(exact[0][2],"air_idle_abcd1234")
    def test_interpolate(self):
        state = {"time": 0.5, "period": 1.0, "loop": False}
        sample = channel_sampler(FakeRenderer(), state)
        self.assertEqual(sample({"0.0": [0, 0, 0], "1.0": [10, 0, 0]}), [5, 0, 0])

    def test_motion_and_atomic_report(self):
        images = [Image.new("RGBA", (20, 20)) for _ in range(2)]
        images[0].putpixel((8, 8), (255, 0, 0, 255))
        images[1].putpixel((9, 8), (255, 0, 0, 255))
        result = inspect_frames(images, 1)
        self.assertTrue(result["motion_pass"])
        self.assertEqual(result["edge_alpha_pixels"], 0)
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "result.json"
            atomic_json(target, result)
            self.assertTrue(target.is_file())

    def test_union_bbox_and_camera_correction(self):
        frames = [Image.new("RGBA", (20, 20)) for _ in range(2)]
        frames[0].putpixel((19, 8), (255, 0, 0, 255))
        frames[1].putpixel((0, 10), (255, 0, 0, 255))
        stats = inspect_frames(frames, 1)
        self.assertEqual(stats["alpha_bbox"], (0, 8, 20, 11))
        self.assertGreater(stats["edge_alpha_pixels"], 0)
        info = {"profileScale": 1.0, "profileTranslation": [0, 0, 0]}
        adjust_fixed_camera(info, (48, 52, 224, 185), 224)
        self.assertLess(info["profileScale"], 1.0)
        self.assertLess(info["profileTranslation"][0], 0)


if __name__ == "__main__":
    unittest.main()
