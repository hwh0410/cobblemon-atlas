import unittest

from audit_pose_semantics import audit_report


class SemanticAuditTest(unittest.TestCase):
    def test_alias_and_context_mismatch(self):
        data = {"forms": {"0384_rayquaza": {"status": "rendered", "poses": {
            "walking": {"clip_keys": ["animation.rayquaza.ground_walk"], "status": "candidate"},
            "fly": {"clip_keys": ["animation.rayquaza.ground_walk"], "status": "candidate"},
            "standing": {"clip_keys": ["animation.rayquaza.ground_idle"], "status": "candidate"},
            "hover": {"clip_keys": ["animation.rayquaza.ground_idle"], "status": "candidate"},
        }}}}
        report = audit_report(data)
        fly = report["forms"]["0384_rayquaza"]["poses"]["fly"]
        self.assertIn("shared_exact_clip_set", fly["flags"])
        self.assertIn("air_pose_uses_ground_clip", fly["flags"])
        self.assertEqual(fly["same_clip_as"], ["walking"])
        self.assertFalse(fly["approved_for_publication"])

    def test_static_pose_not_playable(self):
        data = {"forms": {"0150_mewtwo": {"status": "rendered", "poses": {
            "standing": {"clip_keys": ["animation.mewtwo.ground_idle"], "status": "static_pose"},
        }}}}
        pose = audit_report(data)["forms"]["0150_mewtwo"]["poses"]["standing"]
        self.assertEqual(pose["semantic_review"], "required")
        self.assertIn("static_pose_not_animation", pose["flags"])

    def test_distinct_clip_is_still_unverified(self):
        data = {"forms": {"x": {"status": "rendered", "poses": {
            "fly": {"clip_keys": ["animation.foo.air_fly"], "status": "candidate"},
        }}}}
        pose = audit_report(data)["forms"]["x"]["poses"]["fly"]
        self.assertEqual(pose["flags"], [])
        self.assertEqual(pose["semantic_review"], "unverified")
        self.assertFalse(pose["approved_for_publication"])


if __name__ == "__main__":
    unittest.main()
