import ast
import itertools
import unittest
from pathlib import Path

from alas_headless.alas_commission_config_contract import (
    COMMISSION_PRESETS,
    parse_alas_commission_custom_filter,
    validate_alas_commission_config,
)
from alas_headless.alas_commission_config_replay import verify_commission_config
from alas_headless.semantic_oracle import SemanticGateClosed


ROOT = Path(__file__).resolve().parents[1]
LIVE_ALAS = Path(r"E:\Disk0Merged\H\program\AzurLaneAutoScript-alas-topdown-live")


class AlasCommissionConfigTests(unittest.TestCase):
    default_filter = "DailyEvent > Major > shortest"

    def test_exact_live_tree_replay_when_available(self):
        if not LIVE_ALAS.joinpath("module/commission/commission.py").is_file():
            self.skipTest("local pinned/patched ALAS verification tree is unavailable")
        result = verify_commission_config(LIVE_ALAS)
        self.assertTrue(result["passed"])
        self.assertEqual(result["field_count"], 3)
        self.assertEqual(result["accepted_case_count"], 12)
        self.assertEqual(result["preset_resolution_case_count"], 12)
        self.assertEqual(result["invalid_case_count"], 21)
        self.assertEqual(result["mutation_budget"], 0)
        self.assertFalse(result["real_reward_claimed"])
        self.assertFalse(result["real_commission_started"])
        self.assertFalse(result["android_input_injected"])

    def test_all_preset_and_major_combinations_are_classified(self):
        for preset, do_major in itertools.product(
            COMMISSION_PRESETS, (False, True)
        ):
            snapshot = validate_alas_commission_config(
                preset_filter=preset,
                custom_filter=self.default_filter,
                do_major_commission=do_major,
            )
            self.assertEqual(snapshot.preset_filter, preset)
            self.assertEqual(snapshot.do_major_commission, do_major)
            self.assertEqual(bool(snapshot.custom_tokens), preset == "custom")

    def test_presets_ignore_inactive_custom_filter_and_allow_upstream_fallback(self):
        for preset in ("cube", "future-upstream-preset"):
            for custom_filter in (None, "", "obsolete-filter", []):
                with self.subTest(preset=preset, custom_filter=custom_filter):
                    snapshot = validate_alas_commission_config(
                        preset_filter=preset,
                        custom_filter=custom_filter,
                        do_major_commission=False,
                    )
                    self.assertEqual(snapshot.preset_filter, preset)
                    self.assertEqual(snapshot.custom_tokens, ())

    def test_custom_filter_grammar_and_invalid_fields(self):
        self.assertEqual(
            parse_alas_commission_custom_filter(
                "Major ＞ Gem－8 ❯ ExtraCube-0:30 > 1.5 > shortest"
            ),
            ("major", "gem-8", "extracube-0:30", "1.5", "shortest"),
        )
        invalid_values = {
            "preset_filter": (None, True, 1, "", []),
            "do_major_commission": (0, 1, None, "true", [], {}),
        }
        for field, values in invalid_values.items():
            for value in values:
                case = {
                    "preset_filter": "cube",
                    "custom_filter": self.default_filter,
                    "do_major_commission": False,
                }
                case[field] = value
                with self.subTest(field=field, value=value), self.assertRaises(
                    SemanticGateClosed
                ):
                    validate_alas_commission_config(**case)
        for value in (
            None,
            True,
            1,
            "",
            ">",
            "unknown",
            "Cube-",
            "100:00",
            "ExtraCube-0:3",
            "Gem-8x",
        ):
            with self.subTest(custom_filter=value), self.assertRaises(
                SemanticGateClosed
            ):
                validate_alas_commission_config(
                    preset_filter="custom",
                    custom_filter=value,
                    do_major_commission=False,
                )

    def test_patch_gates_original_commission_entry(self):
        patch = ROOT.joinpath(
            "integration/alas/series/0020-commission-tactical-flow-ports.patch"
        ).read_text(encoding="utf-8")
        self.assertEqual(patch.count("validate_alas_commission_config("), 1)

    def test_sources_compile(self):
        for relative in (
            "python/alas_headless/alas_commission_config_contract.py",
            "python/alas_headless/alas_commission_config_replay.py",
            "scripts/python/verify_alas_commission_config.py",
        ):
            ast.parse(ROOT.joinpath(relative).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
