import ast
import itertools
import unittest
from pathlib import Path

from alas_headless.alas_dorm_config_contract import (
    DORM_FOOD_VALUES,
    parse_alas_dorm_feed_filter,
    validate_alas_dorm_config,
)
from alas_headless.alas_dorm_config_replay import verify_dorm_config
from alas_headless.semantic_oracle import SemanticGateClosed


ROOT = Path(__file__).resolve().parents[1]
LIVE_ALAS = Path(r"H:\program\AzurLaneAutoScript-alas-topdown-live")


class AlasDormConfigTests(unittest.TestCase):
    def test_exact_live_tree_replay_when_available(self):
        if not LIVE_ALAS.joinpath("module/dorm/dorm.py").is_file():
            self.skipTest("local pinned/patched ALAS verification tree is unavailable")
        result = verify_dorm_config(LIVE_ALAS)
        self.assertTrue(result["passed"])
        self.assertEqual(result["field_count"], 3)
        self.assertEqual(result["accepted_case_count"], 7824)
        self.assertEqual(result["food_order_count"], 1956)
        self.assertEqual(result["invalid_case_count"], 22)
        self.assertEqual(result["mutation_budget"], 0)
        self.assertFalse(result["real_collect_called"])
        self.assertFalse(result["real_feed_called"])
        self.assertFalse(result["android_input_injected"])

    def test_all_boolean_and_food_order_combinations_are_classified(self):
        order_count = 0
        for length in range(1, len(DORM_FOOD_VALUES) + 1):
            for order in itertools.permutations(DORM_FOOD_VALUES, length):
                text = " > ".join(str(value) for value in order)
                self.assertEqual(parse_alas_dorm_feed_filter(text), order)
                for collect, feed in itertools.product((False, True), repeat=2):
                    snapshot = validate_alas_dorm_config(
                        collect=collect,
                        feed=feed,
                        feed_filter=text,
                    )
                    self.assertEqual(snapshot.feed_order, order)
                order_count += 1
        self.assertEqual(order_count, 1956)

    def test_invalid_single_fields_fail_closed(self):
        for field in ("collect", "feed"):
            for value in (0, 1, None, "true", [], {}):
                values = {
                    "collect": True,
                    "feed": True,
                    "feed_filter": "20000 > 10000",
                }
                values[field] = value
                with self.subTest(field=field, value=value), self.assertRaises(
                    SemanticGateClosed
                ):
                    validate_alas_dorm_config(**values)
        for value in (
            None,
            True,
            1,
            "",
            "unknown",
            "1000 >> 2000",
            "1000 > 1000",
            "4000",
            "01000",
            "1000x",
        ):
            with self.subTest(feed_filter=value), self.assertRaises(
                SemanticGateClosed
            ):
                validate_alas_dorm_config(
                    collect=True,
                    feed=True,
                    feed_filter=value,
                )

    def test_patch_gates_original_dorm_entry(self):
        patch = ROOT.joinpath(
            "integration/alas/series/0030-research-dorm-build-flow-ports.patch"
        ).read_text(encoding="utf-8")
        self.assertEqual(patch.count("validate_alas_dorm_config("), 1)

    def test_sources_compile(self):
        for relative in (
            "python/alas_headless/alas_dorm_config_contract.py",
            "python/alas_headless/alas_dorm_config_replay.py",
            "scripts/python/verify_alas_dorm_config.py",
        ):
            ast.parse(ROOT.joinpath(relative).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
