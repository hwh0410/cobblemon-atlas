import math
import unittest

from render_follow_camera_pilot import compute_target_camera, smooth_cameras


class FollowCameraTests(unittest.TestCase):
    def test_centered_frame_keeps_center_after_zoom(self):
        scale, translation = compute_target_camera((62, 82, 162, 142), .3, [0, 1, -10])
        self.assertAlmostEqual(scale, .3*1.54, places=4)
        self.assertEqual(len(translation), 3)
        self.assertEqual(translation[2], -10)

    def test_smoothing_positive_and_reduces_jump(self):
        targets = [(.2, [0, 0, -10]), (.2, [0, 0, -10]),
                   (.8, [2, 2, -10]), (.2, [0, 0, -10]), (.2, [0, 0, -10])]
        results = smooth_cameras(targets)
        self.assertTrue(all(v[0] > 0 for v in results))
        self.assertLess(results[2][0], .8)
        self.assertGreater(results[2][0], .2)
        self.assertTrue(all(math.isfinite(x) for _, tr in results for x in tr))


if __name__ == "__main__":
    unittest.main()
