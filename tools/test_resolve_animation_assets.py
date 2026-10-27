import json
import tempfile
import unittest
from pathlib import Path
from resolve_animation_assets import resolve_one, form_parts


class ResolverTests(unittest.TestCase):
    def test_form_parts(self):
        self.assertEqual(form_parts("0384_rayquaza"),("0384_rayquaza",[]))
        self.assertEqual(form_parts("0130_gyarados_mega"),("0130_gyarados",["mega"]))

    def test_exact_model_poser_texture(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            files={
                "bedrock/pokemon/resolvers/0384_rayquaza/0.json":
                    {"variations":[{"aspects":[],"model":"cobblemon:rayquaza2.geo",
                                    "poser":"cobblemon:rayquaza2",
                                    "texture":"cobblemon:textures/pokemon/0384_rayquaza/rayquaza.png"}]},
                "bedrock/pokemon/models/0384_rayquaza/rayquaza2.geo.json":
                    {"minecraft:geometry":[{"description":{"identifier":"geometry.r2"},
                                            "bones":[{"name":"root"}]}]},
                "bedrock/pokemon/posers/0384_rayquaza/rayquaza2.json":
                    {"poses":{"standing":{}}},
            }
            for name,value in files.items():
                p=root/name;p.parent.mkdir(parents=True,exist_ok=True)
                p.write_text(json.dumps(value))
            tex=root/"textures/pokemon/0384_rayquaza/rayquaza.png"
            tex.parent.mkdir(parents=True,exist_ok=True);tex.write_bytes(b"fake")
            result=resolve_one(root,"0384_rayquaza")
            self.assertEqual(result["status"],"resolved")
            self.assertEqual(result["selected"]["bone_count"],1)
            self.assertIn("rayquaza2.geo.json",result["selected"]["model"])

    def test_ambiguous_or_missing_never_guessed(self):
        with tempfile.TemporaryDirectory() as tmp:
            result=resolve_one(Path(tmp),"0384_rayquaza")
            self.assertEqual(result["status"],"audit")
            self.assertEqual(result["reason"],"no_explicit_matching_resolver_variant")


if __name__=="__main__":
    unittest.main()
