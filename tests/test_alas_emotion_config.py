import ast
import unittest
from datetime import datetime, timezone
from pathlib import Path

from alas_headless.alas_emotion_config_contract import (
    EMOTION_CONTROLS,
    EMOTION_PUBLIC_MODES,
    EMOTION_RECOVERY_LOCATIONS,
    validate_alas_emotion_config,
)
from alas_headless.alas_emotion_config_replay import verify_emotion_config
from alas_headless.semantic_oracle import SemanticGateClosed


ROOT = Path(__file__).resolve().parents[1]
LIVE_ALAS = Path(r"H:\program\AzurLaneAutoScript-alas-topdown-live")


def defaults():
    return {
        "mode": "calculate",
        "fleet1_value": 119,
        "fleet1_record": datetime(2026, 8, 15),
        "fleet1_control": "prevent_green_face",
        "fleet1_recover": "not_in_dormitory",
        "fleet1_oath": False,
        "fleet2_value": 119,
        "fleet2_record": datetime(2026, 8, 15),
        "fleet2_control": "prevent_green_face",
        "fleet2_recover": "not_in_dormitory",
        "fleet2_oath": False,
    }


class AlasEmotionConfigTests(unittest.TestCase):
    def test_exact_live_tree_replay_when_available(self):
        if not LIVE_ALAS.joinpath("module/combat/emotion.py").is_file():
            self.skipTest("local pinned/patched ALAS verification tree is unavailable")
        result = verify_emotion_config(LIVE_ALAS)
        self.assertTrue(result["passed"])
        self.assertEqual(result["field_count"], 11)
        self.assertEqual(result["panel_count"], 17)
        self.assertEqual(result["mutation_budget"], 0)
        self.assertFalse(result["android_input_injected"])

    def test_modes_and_complete_fleet_enums_are_classified(self):
        for mode in EMOTION_PUBLIC_MODES + ("nothing",):
            config = defaults()
            config["mode"] = mode
            self.assertEqual(validate_alas_emotion_config(**config).mode, mode)
        for fleet in (1, 2):
            for control in EMOTION_CONTROLS:
                for recover in EMOTION_RECOVERY_LOCATIONS:
                    if control == "keep_exp_bonus" and recover == "not_in_dormitory":
                        continue
                    for oath in (False, True):
                        with self.subTest(
                            fleet=fleet, control=control, recover=recover, oath=oath
                        ):
                            config = defaults()
                            config[f"fleet{fleet}_control"] = control
                            config[f"fleet{fleet}_recover"] = recover
                            config[f"fleet{fleet}_oath"] = oath
                            validate_alas_emotion_config(**config)

    def test_invalid_and_incompatible_values_fail_closed(self):
        for field, value in (
            ("mode", "unknown"),
            ("fleet1_value", -1),
            ("fleet1_value", 151),
            ("fleet1_value", True),
            ("fleet1_record", "2026-08-15"),
            ("fleet1_record", datetime(2026, 8, 15, tzinfo=timezone.utc)),
            ("fleet1_control", "unknown"),
            ("fleet1_recover", "unknown"),
            ("fleet1_oath", 1),
        ):
            config = defaults()
            config[field] = value
            with self.subTest(field=field, value=value), self.assertRaises(
                SemanticGateClosed
            ):
                validate_alas_emotion_config(**config)
        for fleet in (1, 2):
            config = defaults()
            config[f"fleet{fleet}_control"] = "keep_exp_bonus"
            config[f"fleet{fleet}_recover"] = "not_in_dormitory"
            with self.assertRaises(SemanticGateClosed):
                validate_alas_emotion_config(**config)

    def test_patch_gates_central_emotion_constructor(self):
        patch = ROOT.joinpath(
            "integration/alas/series/0050-combat-flow-ports.patch"
        ).read_text(encoding="utf-8")
        self.assertIn("diff --git a/module/combat/emotion.py", patch)
        self.assertIn("validate_alas_emotion_config(", patch)
        self.assertLess(
            patch.index("validate_alas_emotion_config("),
            patch.index("self.config = config", patch.index("validate_alas_emotion_config(")),
        )

    def test_sources_compile(self):
        for relative in (
            "python/alas_headless/alas_emotion_config_contract.py",
            "python/alas_headless/alas_emotion_config_replay.py",
            "scripts/python/verify_alas_emotion_config.py",
        ):
            ast.parse(ROOT.joinpath(relative).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
