import ast
import unittest
from pathlib import Path

from alas_headless.alas_daily_config_contract import validate_alas_daily_config
from alas_headless.semantic_oracle import SemanticGateClosed
from scripts.python.verify_alas_daily_config import verify_clean_upstream


ROOT = Path(__file__).resolve().parents[1]
PINNED_UPSTREAM = Path(r"E:\Disk0Merged\H\program\AzurLaneAutoScript-upstream-readonly")


def _values(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "use_daily_skip": True,
        "escort_mission": "first",
        "escort_mission_fleet": 1,
        "advance_mission": "second",
        "advance_mission_fleet": 2,
        "fierce_assault": "third",
        "fierce_assault_fleet": 3,
        "tactical_training": "second",
        "tactical_training_fleet": 4,
        "supply_line_disruption": "third",
        "module_development": "second",
        "module_development_fleet": 5,
        "emergency_module_development": "first",
        "emergency_module_development_fleet": 6,
    }
    values.update(overrides)
    return values


class AlasDailyConfigTests(unittest.TestCase):
    def test_exact_pinned_upstream_replay_when_available(self):
        if not PINNED_UPSTREAM.joinpath("module/daily/daily.py").is_file():
            self.skipTest("local pinned ALAS verification tree is unavailable")
        result = verify_clean_upstream(PINNED_UPSTREAM)
        self.assertTrue(result["passed"])
        self.assertEqual(result["field_count"], 14)
        self.assertEqual(result["accepted_case_count"], 64)
        self.assertEqual(result["invalid_case_count"], 80)
        self.assertEqual(
            result["original_decisions"]["standard_mapping"][0], [2, 4]
        )
        self.assertEqual(
            result["original_decisions"]["emergency_mapping"][0], [2, 5]
        )
        self.assertEqual(
            result["original_decisions"]["cases"]["supply_skip_enabled"][
                "executions"
            ],
            [{"remain": 2, "stage": 2, "fleet": 0}],
        )
        self.assertEqual(result["mutation_budget"], 0)
        self.assertFalse(result["android_input_injected"])

    def test_declared_stage_and_fleet_choices_are_accepted(self):
        for stage in ("skip", "first", "second", "third"):
            snapshot = validate_alas_daily_config(
                **_values(tactical_training=stage)
            )
            self.assertEqual(snapshot.tactical_training, stage)
        for fleet in range(1, 7):
            snapshot = validate_alas_daily_config(
                **_values(tactical_training_fleet=fleet)
            )
            self.assertEqual(snapshot.tactical_training_fleet, fleet)

    def test_invalid_stage_fleet_and_boolean_values_fail_closed(self):
        for field, value in (
            ("tactical_training", "fourth"),
            ("module_development", "third"),
            ("escort_mission", " FIRST"),
            ("tactical_training_fleet", 0),
            ("tactical_training_fleet", 7),
            ("tactical_training_fleet", True),
            ("tactical_training_fleet", "1"),
            ("use_daily_skip", 1),
            ("use_daily_skip", "true"),
        ):
            with self.subTest(field=field, value=value), self.assertRaises(
                SemanticGateClosed
            ):
                validate_alas_daily_config(**_values(**{field: value}))

    def test_patch_validates_before_original_daily_state_machine(self):
        patch = ROOT.joinpath(
            "integration/alas/series/0080-current-task-flow-ports.patch"
        ).read_text(encoding="utf-8")
        self.assertIn(
            "from alas_headless import SemanticGateClosed, validate_alas_daily_config",
            patch,
        )
        self.assertIn("def _validate_daily_config(self):", patch)
        self.assertIn("self._validate_daily_config()\n         self.daily_run()", patch)

    def test_sources_compile(self):
        for relative in (
            "python/alas_headless/alas_daily_config_contract.py",
            "python/alas_headless/alas_daily_config_replay.py",
            "scripts/python/verify_alas_daily_config.py",
        ):
            ast.parse(ROOT.joinpath(relative).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
