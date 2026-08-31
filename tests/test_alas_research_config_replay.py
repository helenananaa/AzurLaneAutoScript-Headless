import ast
import json
import re
import unittest
from pathlib import Path
from types import SimpleNamespace

from alas_headless.alas_adapter import AlasSemanticAdapter
from alas_headless.alas_research_config_contract import (
    RESEARCH_PRESET_FILTERS,
    RESEARCH_RESOURCE_STRATEGIES,
    validate_alas_research_allow_delay,
    validate_alas_research_selector_config,
)
from alas_headless.alas_research_config_replay import verify_research_config
from alas_headless.semantic_oracle import SemanticGateClosed


ROOT = Path(__file__).resolve().parents[1]
LIVE_ALAS = Path(r"E:\Disk0Merged\H\program\AzurLaneAutoScript-alas-topdown-live")


class ResearchConfigReplayTests(unittest.TestCase):
    def test_contract_matches_exact_pinned_public_surface(self):
        if not LIVE_ALAS.joinpath("module/config/argument/args.json").is_file():
            self.skipTest("local pinned ALAS verification tree is unavailable")
        args = json.loads(
            LIVE_ALAS.joinpath("module/config/argument/args.json").read_text(
                encoding="utf-8"
            )
        )["Research"]["Research"]
        self.assertEqual(tuple(args["PresetFilter"]["option"]), RESEARCH_PRESET_FILTERS)
        for field in ("UseCoin", "UseCube", "UsePart"):
            self.assertEqual(tuple(args[field]["option"]), RESEARCH_RESOURCE_STRATEGIES)

    def test_contract_accepts_every_public_value_and_preserves_unknown_fallback(self):
        for preset in (*RESEARCH_PRESET_FILTERS, "future-upstream-preset"):
            with self.subTest(preset=preset):
                snapshot = validate_alas_research_selector_config(
                    preset_filter=preset,
                    custom_filter="S9-Q0.5 > reset",
                    allow_delay=True,
                    use_coin="always_use",
                    use_cube="only_05_hour",
                    use_part="do_not_use",
                )
                self.assertEqual(snapshot.preset_filter, preset)
        for strategy in RESEARCH_RESOURCE_STRATEGIES:
            with self.subTest(strategy=strategy):
                snapshot = validate_alas_research_selector_config(
                    preset_filter="custom",
                    custom_filter="S9-Q0.5",
                    allow_delay=False,
                    use_coin=strategy,
                    use_cube=strategy,
                    use_part=strategy,
                )
                self.assertEqual(snapshot.use_coin, strategy)
        self.assertIs(validate_alas_research_allow_delay(False), False)
        self.assertIs(validate_alas_research_allow_delay(True), True)

    def test_contract_rejects_ambiguous_field_types_and_values(self):
        valid = {
            "preset_filter": "custom",
            "custom_filter": "S9-Q0.5",
            "allow_delay": True,
            "use_coin": "always_use",
            "use_cube": "only_05_hour",
            "use_part": "do_not_use",
        }
        invalid = {
            "preset_filter": (None, ""),
            "custom_filter": (None, "  "),
            "allow_delay": (1, "true", None),
            "use_coin": (True, "sometimes", None),
            "use_cube": (False, "", None),
            "use_part": (1, "ALWAYS_USE", None),
        }
        for field, values in invalid.items():
            for value in values:
                with self.subTest(field=field, value=value):
                    candidate = dict(valid)
                    candidate[field] = value
                    with self.assertRaises(SemanticGateClosed):
                        validate_alas_research_selector_config(**candidate)

    def test_exact_live_patched_tree_when_available(self):
        if not LIVE_ALAS.joinpath("module/research/selector.py").is_file():
            self.skipTest("local pinned/patched ALAS verification tree is unavailable")
        result = verify_research_config(LIVE_ALAS)
        self.assertTrue(result["passed"])
        self.assertEqual(result["public_preset_count"], 26)
        self.assertEqual(result["resource_policy_rows"], 36)
        self.assertEqual(result["mutation_budget"], 0)
        self.assertFalse(result["android_input_injected"])

    def test_filter_gate_rejects_partial_or_empty_tokens(self):
        filter_ = SimpleNamespace(
            regex=re.compile(r"s[1-9]-q(?:0\.5|1)"),
            is_preset=lambda value: value in ("reset", "shortest"),
        )
        adapter = SimpleNamespace()
        AlasSemanticAdapter.validate_research_filter(
            adapter, filter_, "S9-Q0.5 > reset"
        )
        for value in ("S9-Q0.5junk", "S9-Q0.5 > ", "unknown"):
            with self.subTest(value=value), self.assertRaises(SemanticGateClosed):
                AlasSemanticAdapter.validate_research_filter(adapter, filter_, value)

    def test_replay_source_compiles(self):
        source = ROOT.joinpath(
            "python/alas_headless/alas_research_config_replay.py"
        ).read_text(encoding="utf-8")
        ast.parse(source)


if __name__ == "__main__":
    unittest.main()
