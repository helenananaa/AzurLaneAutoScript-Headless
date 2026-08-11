import copy
import json
import tempfile
import unittest
from pathlib import Path

from scripts.python.build_g36_capability_surface import (
    G36CapabilitySurfaceError,
    build_surface,
    canonical_json,
)


ROOT = Path(__file__).resolve().parents[1]
SURFACE = ROOT / "integration" / "alas" / "g36-capability-surface.json"
NORMAL = ROOT / "integration" / "alas" / "g36-normal-replay-surface.json"
DEFENSIVE = (
    ROOT
    / "integration"
    / "alas"
    / "combat-defensive-branch-replay-g28.json"
)
PROFILE = (
    ROOT
    / "integration"
    / "alas"
    / "profiles"
    / "g36-12-4-normal-one-battle.zero-input.json"
)


class G36CapabilitySurfaceTests(unittest.TestCase):
    def test_checked_in_surface_rebuilds_exactly(self):
        expected = json.loads(SURFACE.read_text(encoding="utf-8"))
        rebuilt = build_surface(
            normal_path=NORMAL,
            defensive_path=DEFENSIVE,
            profile_path=PROFILE,
        )
        self.assertEqual(rebuilt, expected)
        self.assertEqual(
            canonical_json(rebuilt), SURFACE.read_text(encoding="utf-8")
        )
        self.assertFalse(rebuilt["input_injected"])
        self.assertFalse(rebuilt["review"]["capability_promotion"])
        self.assertFalse(rebuilt["review"]["production_ready"])
        self.assertEqual(rebuilt["comparison"]["g19_normal_resources_added"], [])
        self.assertEqual(rebuilt["comparison"]["g19_normal_resources_removed"], [])

    def test_normal_query_addition_or_removal_requires_review(self):
        source = json.loads(NORMAL.read_text(encoding="utf-8"))
        for name, mutate in (
            ("added", lambda values: values + ["UNREVIEWED"]),
            ("removed", lambda values: values[1:]),
        ):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                changed = copy.deepcopy(source)
                changed["resource_query_names"] = mutate(
                    changed["resource_query_names"]
                )
                path = Path(directory) / "normal.json"
                path.write_text(json.dumps(changed), encoding="utf-8")
                with self.assertRaises(G36CapabilitySurfaceError):
                    build_surface(
                        normal_path=path,
                        defensive_path=DEFENSIVE,
                        profile_path=PROFILE,
                    )

    def test_profile_hash_is_part_of_surface_identity(self):
        profile = json.loads(PROFILE.read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as directory:
            profile["alas_config"]["Campaign_UseAutoSearch"] = True
            path = Path(directory) / "profile.json"
            path.write_text(json.dumps(profile), encoding="utf-8")
            with self.assertRaises(G36CapabilitySurfaceError):
                build_surface(
                    normal_path=NORMAL,
                    defensive_path=DEFENSIVE,
                    profile_path=path,
                )


if __name__ == "__main__":
    unittest.main()
