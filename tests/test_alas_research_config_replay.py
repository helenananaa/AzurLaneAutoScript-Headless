import ast
import re
import unittest
from pathlib import Path
from types import SimpleNamespace

from alas_headless.alas_adapter import AlasSemanticAdapter
from alas_headless.alas_research_config_replay import verify_research_config
from alas_headless.semantic_oracle import SemanticGateClosed


ROOT = Path(__file__).resolve().parents[1]
LIVE_ALAS = Path(r"H:\program\AzurLaneAutoScript-alas-topdown-live")


class ResearchConfigReplayTests(unittest.TestCase):
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
