import copy
import json
import unittest
from pathlib import Path
from types import SimpleNamespace

from alas_headless.adapter.task_profile import (
    G36TaskProfileError,
    canonical_g36_task_profile_json,
    load_g36_task_profile,
    parse_g36_task_profile,
)


ROOT = Path(__file__).resolve().parents[1]
PROFILE_PATH = (
    ROOT
    / "integration"
    / "alas"
    / "profiles"
    / "g36-12-4-normal-one-battle.zero-input.json"
)


class G36TaskProfileTests(unittest.TestCase):
    def setUp(self):
        self.source = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
        self.profile = load_g36_task_profile(PROFILE_PATH)

    def test_checked_in_profile_is_exact_zero_input_slice(self):
        self.assertEqual(
            self.profile.profile_id,
            "cn-9.7.10-12-4-normal-one-battle",
        )
        self.assertEqual(self.profile.qualification["battle_limit"], 1)
        self.assertEqual(self.profile.qualification["input_mode"], "zero-input")
        self.assertEqual(
            self.profile.qualification["preflight_stop_boundary"],
            "original-device-click-grid",
        )
        self.assertIsNone(self.profile.combat_call["save_get_items"])
        self.assertEqual(
            parse_g36_task_profile(
                canonical_g36_task_profile_json(self.profile)
            ).sha256,
            self.profile.sha256,
        )

    def test_every_bound_value_contributes_to_profile_hash(self):
        baseline = self.profile.sha256
        sections = ("game_identity", "qualification", "alas_config", "combat_call")
        for section in sections:
            for key, value in self.source[section].items():
                with self.subTest(section=section, key=key):
                    changed = copy.deepcopy(self.source)
                    changed[section][key] = self._different_value(value)
                    encoded = json.dumps(changed, separators=(",", ":"), sort_keys=True)
                    try:
                        candidate = parse_g36_task_profile(encoded)
                    except G36TaskProfileError:
                        continue
                    self.assertNotEqual(candidate.sha256, baseline)
                    with self.assertRaises(G36TaskProfileError):
                        candidate.require_preflight_hash(baseline)

    def test_profile_hash_is_required_by_preflight(self):
        self.profile.require_preflight_hash(self.profile.sha256)
        with self.assertRaises(G36TaskProfileError):
            self.profile.require_preflight_hash("0" * 64)

    def test_all_bound_alas_values_are_checked(self):
        config = SimpleNamespace(**dict(self.profile.alas_config))
        self.profile.require_alas_config(config)
        for name, value in self.profile.alas_config.items():
            with self.subTest(name=name):
                changed = SimpleNamespace(**dict(self.profile.alas_config))
                setattr(changed, name, self._different_value(value))
                with self.assertRaises(G36TaskProfileError):
                    self.profile.require_alas_config(changed)

    def test_unknown_duplicate_and_noncanonical_values_fail_closed(self):
        unknown = copy.deepcopy(self.source)
        unknown["qualification"]["unexpected"] = False
        with self.assertRaises(G36TaskProfileError):
            parse_g36_task_profile(json.dumps(unknown))
        with self.assertRaises(G36TaskProfileError):
            parse_g36_task_profile('{"schema":"x","schema":"y"}')
        boolean_integer = copy.deepcopy(self.source)
        boolean_integer["alas_config"]["Fleet_Fleet1"] = True
        with self.assertRaises(G36TaskProfileError):
            parse_g36_task_profile(json.dumps(boolean_integer))

    @staticmethod
    def _different_value(value):
        if isinstance(value, bool):
            return not value
        if value is None:
            return False
        if isinstance(value, int):
            return value + 1
        if isinstance(value, float):
            return value + 0.1
        if isinstance(value, list):
            return value + [9.9]
        if isinstance(value, tuple):
            return value + (9.9,)
        return value + "-drift"


if __name__ == "__main__":
    unittest.main()
