import unittest

from PIL import Image

from render_layered_pilot import extract_all_poser_keys, overlay_difference


class LayeredPilotTests(unittest.TestCase):
    def test_overlay_difference_requires_real_change(self):
        base = [Image.new("RGBA", (10, 10), (0, 0, 0, 0)) for _ in range(3)]
        same, per_frame = overlay_difference(base, base)
        self.assertEqual(same, 0)
        self.assertEqual(per_frame, [0, 0, 0])
        changed = [image.copy() for image in base]
        changed[1].putpixel((3, 4), (255, 0, 0, 255))
        maximum, samples = overlay_difference(base, changed)
        self.assertEqual(maximum, 1)
        self.assertEqual(samples, [0, 1, 0])

    def test_poser_stateful_and_quirk_refs(self):
        poser = {"poses": {"standing": {"quirks": ["q.bedrock_quirk('mewtwo', 'blink')"]}},
                 "animations": {"cry": "q.bedrock_stateful('mewtwo','cry')"}}
        self.assertEqual(set(extract_all_poser_keys(poser)),
                         {"animation.mewtwo.blink", "animation.mewtwo.cry"})


if __name__ == "__main__":
    unittest.main()
