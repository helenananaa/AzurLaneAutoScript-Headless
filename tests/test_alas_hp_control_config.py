import ast
import math
import unittest
from pathlib import Path

from alas_headless.alas_hp_control_config_contract import (
    validate_alas_hp_control_config,
)
from alas_headless.semantic_oracle import SemanticGateClosed


ROOT = Path(__file__).resolve().parents[1]


def defaults():
    return {
        "use_hp_balance": False,
        "use_emergency_repair": False,
        "use_low_hp_retreat": False,
        "hp_balance_threshold": 0.2,
        "hp_balance_weight": "1000, 1000, 1000",
        "repair_use_single_threshold": 0.3,
        "repair_use_multi_threshold": 0.6,
        "low_hp_retreat_threshold": 0.3,
    }


class AlasHpControlConfigTests(unittest.TestCase):
    def test_disabled_safe_surface_accepts_ratio_boundaries_and_weights(self):
        for field in (
            "hp_balance_threshold",
            "repair_use_single_threshold",
            "repair_use_multi_threshold",
            "low_hp_retreat_threshold",
        ):
            for value in (0, 0.5, 1):
                with self.subTest(field=field, value=value):
                    config = defaults()
                    config[field] = value
                    self.assertEqual(
                        getattr(validate_alas_hp_control_config(**config), field),
                        float(value),
                    )
        for value, expected in (
            ("1,2,3", (1, 2, 3)),
            ("1000， 500， 250", (1000, 500, 250)),
        ):
            config = defaults()
            config["hp_balance_weight"] = value
            self.assertEqual(
                validate_alas_hp_control_config(**config).hp_balance_weight,
                expected,
            )

    def test_features_admit_configuration_and_keep_input_checks_local(self):
        for field in ('use_hp_balance', 'use_emergency_repair', 'use_low_hp_retreat'):
            config = defaults()
            config[field] = True
            with self.subTest(field=field):
                self.assertTrue(getattr(validate_alas_hp_control_config(**config), field))

    def test_low_hp_retreat_is_admitted_with_original_threshold(self):
        config = defaults()
        config['use_low_hp_retreat'] = True
        config['low_hp_retreat_threshold'] = 0.3
        snapshot = validate_alas_hp_control_config(**config)
        self.assertTrue(snapshot.use_low_hp_retreat)
        self.assertEqual(snapshot.low_hp_retreat_threshold, 0.3)

    def test_invalid_values_fail_closed(self):
        for field, value in (
            ("use_hp_balance", 1),
            ("hp_balance_threshold", -0.1),
            ("repair_use_single_threshold", 1.1),
            ("repair_use_multi_threshold", math.inf),
            ("low_hp_retreat_threshold", "0.3"),
            ("hp_balance_weight", "1,2"),
            ("hp_balance_weight", "1,0,2"),
            ("hp_balance_weight", "0.1,2,3"),
            ("hp_balance_weight", "1,nan,2"),
        ):
            config = defaults()
            config[field] = value
            with self.subTest(field=field, value=value), self.assertRaises(
                SemanticGateClosed
            ):
                validate_alas_hp_control_config(**config)

    def test_patch_validates_before_campaign_context(self):
        patch = ROOT.joinpath(
            "integration/alas/series/0050-combat-flow-ports.patch"
        ).read_text(encoding="utf-8")
        validation = patch.index(
            "semantic_adapter.validate_campaign_hp_control_config("
        )
        self.assertLess(
            patch.index("semantic_adapter.validate_campaign_fleet_config("),
            validation,
        )
        self.assertLess(
            validation,
            patch.index("semantic_adapter.begin_campaign_pre_sortie("),
        )

    def test_sources_compile(self):
        for relative in (
            "python/alas_headless/alas_hp_control_config_contract.py",
            "python/alas_headless/alas_hp_control_config_replay.py",
            "scripts/python/verify_alas_hp_control_config.py",
        ):
            ast.parse(ROOT.joinpath(relative).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
