import tempfile
import unittest
from pathlib import Path

from PIL import Image

from render_action_jobs import atomic_json, channel_sampler, inspect_frames


class FakeRenderer:
    @staticmethod
    def molang(value, t=0):
        return float(value)


class RenderActionTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
