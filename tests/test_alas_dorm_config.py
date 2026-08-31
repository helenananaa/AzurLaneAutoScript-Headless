import ast
import itertools
import json
import runpy
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
LIVE_ALAS = Path(r"E:\Disk0Merged\H\program\AzurLaneAutoScript-alas-topdown-live")
DORM_FEED_EVIDENCE_ORACLE_SHA256 = (
    "96b7b240be56bac8a0262c503e2e9b65b42a5f5eba80eaad623adfebae2d7f40"
)
DORM_FEED_EVIDENCE_ADAPTER_SHA256 = (
    "99cfc62760cf28ec52ef306624eb0b76fb5d32bbd4e2a1041137e3ee744e0358"
)


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

    def test_single_numeric_filter_survives_original_config_canonicalization(self):
        self.assertEqual(parse_alas_dorm_feed_filter(1000), (1000,))
        self.assertEqual(
            validate_alas_dorm_config(
                collect=False,
                feed=True,
                feed_filter=1000,
            ).feed_order,
            (1000,),
        )

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
            999,
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

    def test_live_validation_plans_every_original_feed_pass(self):
        module = runpy.run_path(
            str(ROOT / "scripts/python/run_alas_dorm_feed_live_validation.py")
        )
        plan = module["_planned_feeds"](
            {
                "food": 32038,
                "capacity": 40000,
                "items": [
                    {"item_id": 50001, "value": 1000, "count": 1},
                    {"item_id": 50002, "value": 2000, "count": 1},
                    {"item_id": 50003, "value": 3000, "count": 1},
                    {"item_id": 50004, "value": 5000, "count": 1},
                    {"item_id": 50005, "value": 10000, "count": 1},
                    {"item_id": 50006, "value": 20000, "count": 0},
                ],
            },
            feed_filter="20000 > 10000 > 5000 > 3000 > 2000 > 1000",
        )
        self.assertEqual(
            plan,
            (
                {"item_id": 50004, "value": 5000, "dispatch_count": 1},
                {"item_id": 50002, "value": 2000, "dispatch_count": 1},
            ),
        )

    def test_live_dorm_feed_receipts_cover_enabled_disabled_and_numeric_filter(self):
        expected_hashes = {
            # All three historical feed receipts used this adapter revision.
            # Do not couple consumptive evidence to later unrelated adapter
            # improvements such as Reward resource collection.
            "adapter": DORM_FEED_EVIDENCE_ADAPTER_SHA256,
            # The three feeds consume real food.  Pin the exact Oracle source
            # used on that run so an unrelated later UI-surface improvement
            # (such as the Shop frame-pair fix) does not invalidate
            # non-repeatable positive evidence.
            "oracle": DORM_FEED_EVIDENCE_ORACLE_SHA256,
        }
        receipts = {
            "enabled": "integration/alas/dorm-feed-r10-live-validation-receipt.json",
            "disabled": "integration/alas/dorm-feed-r11-disabled-live-validation-receipt.json",
            "numeric": "integration/alas/dorm-feed-r13-filter-1000-live-validation-receipt.json",
        }
        loaded = {
            name: json.loads(ROOT.joinpath(path).read_text(encoding="utf-8"))
            for name, path in receipts.items()
        }
        for receipt in loaded.values():
            self.assertTrue(receipt["passed"])
            self.assertTrue(receipt["task_result"])
            self.assertEqual(receipt["dorm_feed_grant_remaining"], 0)
            self.assertEqual(receipt["after"]["cleanup"], "main")
            self.assertTrue(receipt["temporary_config_removed"])
            self.assertEqual(
                {name: receipt["source_sha256"][name] for name in expected_hashes},
                expected_hashes,
            )

        enabled = loaded["enabled"]
        self.assertTrue(enabled["configured"]["Dorm.Feed"])
        self.assertGreater(enabled["planned_dispatch_count"], 0)
        self.assertEqual(
            tuple(item["semantic_id"] for item in enabled["dispatches"]),
            tuple(
                "dorm/feed/item/{0}".format(step["item_id"])
                for step in enabled["planned_feeds"]
                for _ in range(step["dispatch_count"])
            ),
        )

        disabled = loaded["disabled"]
        self.assertFalse(disabled["configured"]["Dorm.Feed"])
        self.assertEqual(disabled["dispatches"], [])
        self.assertEqual(disabled["planned_dispatch_count"], 0)

        numeric = loaded["numeric"]
        self.assertEqual(numeric["configured"]["Dorm.FeedFilter"], "1000")
        self.assertEqual(
            numeric["planned_feeds"],
            [{"item_id": 50001, "value": 1000, "dispatch_count": 1}],
        )
        self.assertEqual(
            [item["semantic_id"] for item in numeric["dispatches"]],
            ["dorm/feed/item/50001"],
        )
        before = numeric["before"]["feed"]
        after = numeric["after"]["feed"]
        before_item = next(item for item in before["items"] if item["item_id"] == 50001)
        after_item = next(item for item in after["items"] if item["item_id"] == 50001)
        self.assertEqual(after_item["count"], before_item["count"] - 1)

        no_stock = json.loads(
            ROOT.joinpath(
                "integration/alas/dorm-feed-r14-filter-20000-no-stock-live-validation-receipt.json"
            ).read_text(encoding="utf-8")
        )
        self.assertTrue(no_stock["passed"])
        self.assertTrue(no_stock["configured"]["Dorm.Feed"])
        self.assertEqual(no_stock["configured"]["Dorm.FeedFilter"], "20000")
        self.assertFalse(no_stock["expect_feed"])
        self.assertEqual(no_stock["planned_dispatch_count"], 0)
        self.assertEqual(no_stock["dispatches"], [])
        self.assertEqual(no_stock["before"]["feed"]["food"], 0)
        self.assertEqual(no_stock["before"]["feed"]["capacity"], 40000)
        item = next(
            value
            for value in no_stock["before"]["feed"]["items"]
            if value["value"] == 20000
        )
        self.assertEqual(item["count"], 0)
        self.assertEqual(no_stock["after"]["cleanup"], "main")
        self.assertTrue(no_stock["temporary_config_removed"])

    def test_sources_compile(self):
        for relative in (
            "python/alas_headless/alas_dorm_config_contract.py",
            "python/alas_headless/alas_dorm_config_replay.py",
            "scripts/python/verify_alas_dorm_config.py",
            "scripts/python/run_alas_dorm_feed_live_validation.py",
        ):
            ast.parse(ROOT.joinpath(relative).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
