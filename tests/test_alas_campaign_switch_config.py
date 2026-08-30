import ast
import itertools
import unittest
from pathlib import Path

from alas_headless.alas_campaign_switch_config_contract import (
    validate_alas_campaign_switch_config,
)
from alas_headless.alas_campaign_switch_config_replay import (
    verify_campaign_switch_config,
)
from alas_headless.semantic_oracle import SemanticGateClosed


ROOT = Path(__file__).resolve().parents[1]
LIVE_ALAS = Path(r"E:\Disk0Merged\H\program\AzurLaneAutoScript-alas-topdown-live")


class AlasCampaignSwitchConfigTests(unittest.TestCase):
    def test_exact_live_tree_replay_when_available(self):
        if not LIVE_ALAS.joinpath("module/campaign/run.py").is_file():
            self.skipTest("local pinned/patched ALAS verification tree is unavailable")
        result = verify_campaign_switch_config(LIVE_ALAS)
        self.assertTrue(result["passed"])
        self.assertEqual(result["field_count"], 4)
        self.assertEqual(result["panel_count"], 16)
        self.assertEqual(result["accepted_case_count"], 16)
        self.assertEqual(result["invalid_case_count"], 24)
        self.assertEqual(result["mutation_budget"], 0)
        self.assertFalse(result["android_input_injected"])

    def test_all_boolean_combinations_are_classified(self):
        for values in itertools.product((False, True), repeat=4):
            with self.subTest(values=values):
                snapshot = validate_alas_campaign_switch_config(
                    use_fleet_lock=values[0],
                    use_auto_search=values[1],
                    use_2x_book=values[2],
                    ambush_evade=values[3],
                )
                self.assertEqual(
                    (
                        snapshot.use_fleet_lock,
                        snapshot.use_auto_search,
                        snapshot.use_2x_book,
                        snapshot.ambush_evade,
                    ),
                    values,
                )

    def test_invalid_single_fields_fail_closed(self):
        fields = (
            "use_fleet_lock",
            "use_auto_search",
            "use_2x_book",
            "ambush_evade",
        )
        for field in fields:
            for value in (0, 1, None, "true", [], {}):
                values = dict(
                    use_fleet_lock=True,
                    use_auto_search=True,
                    use_2x_book=False,
                    ambush_evade=True,
                )
                values[field] = value
                with self.subTest(field=field, value=value), self.assertRaises(
                    SemanticGateClosed
                ):
                    validate_alas_campaign_switch_config(**values)

    def test_patch_gates_original_campaign_runner(self):
        patch = ROOT.joinpath(
            "integration/alas/series/0050-combat-flow-ports.patch"
        ).read_text(encoding="utf-8")
        self.assertEqual(
            patch.count("self._validate_campaign_switch_config()"), 1
        )

    def test_sources_compile(self):
        for relative in (
            "python/alas_headless/alas_campaign_switch_config_contract.py",
            "python/alas_headless/alas_campaign_switch_config_replay.py",
            "scripts/python/verify_alas_campaign_switch_config.py",
        ):
            ast.parse(ROOT.joinpath(relative).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
