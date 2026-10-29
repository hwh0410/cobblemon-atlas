import unittest

from render_blend_modes import collect_override, bbox_area


class FakeRenderer:
    @staticmethod
    def channel_at_zero(channel):
        return channel


class BlendTests(unittest.TestCase):
    def test_last_clip_wins_only_overlapping_channels(self):
        base = {"bones": {"Body": {"rotation": [30, 0, 0],
                                   "position": [1, 2, 3]},
                          "Tail": {"rotation": [5, 0, 0]}}}
        attack = {"bones": {"Body": {"rotation": [60, 0, 0]}}}
        result = collect_override(FakeRenderer(), {"clips": [("base", base), ("attack", attack)]})
        self.assertEqual(result["body"]["rotation"], [60, 0, 0])
        self.assertEqual(result["body"]["position"], [1, 2, 3])
        self.assertEqual(result["tail"]["rotation"], [5, 0, 0])

    def test_silhouette_area(self):
        self.assertEqual(bbox_area({"alpha_bbox": (2, 3, 12, 8)}), 50)
        self.assertEqual(bbox_area({"alpha_bbox": None}), 0)


if __name__ == "__main__":
    unittest.main()
