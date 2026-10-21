"""Commission regression cases for the adapter."""

import time
import unittest
from alas_headless import (
    AlasSemanticAdapter,
    AlasSemanticSession,
    AlasSemanticUnmapped,
    SemanticGateClosed,
)
from tests.semantic_support.adapter_cases import AlasSemanticAdapterTestsSupport
from tests.semantic_support.adapter_fixtures import FakeOracle, NamedButton
from types import SimpleNamespace
from unittest.mock import patch


class AlasSemanticAdapterTests(AlasSemanticAdapterTestsSupport, unittest.TestCase):
    def test_commission_reward_and_navigation_are_distinct_alas_inputs(self):
        adapter, oracle, _ = self.make_adapter()
        adapter.begin_commission()

        self.assertEqual(
            adapter.semantic_id_for("REWARD_1"), "reward/commission/finish"
        )
        self.assertEqual(
            adapter.semantic_id_for("REWARD_GOTO_COMMISSION"),
            "reward/commission/go",
        )
        self.assertEqual(
            adapter.semantic_id_for("AUTO_SEARCH_MENU_EXIT"),
            "reward/campaign-total/exit",
        )
        self.assertTrue(adapter.appear(NamedButton("REWARD_1")))
        with self.assertRaises(SemanticGateClosed):
            adapter.click(NamedButton("REWARD_1"))
        self.assertEqual(oracle.click_calls, [])

    def test_commission_reward_chain_uses_one_budget_and_typed_counter_proof(self):
        oracle = FakeOracle()
        oracle.exists_values["reward/commission/finish"] = True
        oracle.enabled_values = {
            "reward/commission/finish": True,
            "reward/ship-exp/close": True,
            "reward/award-info/close": True,
            "reward/award-info1/close": False,
            "commission/page/back": True,
        }
        oracle.reward_summary_values = [1, 1, 0]
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            commission_reward_budget=1,
        )
        adapter.begin_commission()

        self.assertTrue(adapter.commission_reward_pending())
        self.assertTrue(adapter.commission_reward_allowed())
        claim = adapter.click(NamedButton("REWARD_1"))
        duplicate = adapter.click(NamedButton("REWARD_1_WHITE"))
        self.assertTrue(adapter.appear(NamedButton("EXP_INFO_S_REWARD")))
        exp = adapter.click(NamedButton("REWARD_SAVE_CLICK"))
        exp_duplicate = adapter.click(NamedButton("EXP_INFO_S_REWARD"))
        award = adapter.click(NamedButton("GET_ITEMS_3"))
        award_duplicate = adapter.click(NamedButton("GET_ITEMS_1"))
        oracle.enabled_values["reward/award-info/close"] = False
        award_after_disappear = adapter.click(NamedButton("GET_ITEMS_2"))
        proof = adapter.confirm_commission_reward()

        self.assertEqual(claim, duplicate)
        self.assertEqual(exp.semantic_id, exp_duplicate.semantic_id)
        self.assertEqual(award.semantic_id, award_duplicate.semantic_id)
        self.assertEqual(award, award_after_disappear)
        self.assertEqual(exp.semantic_id, "reward/ship-exp/close")
        self.assertEqual(award.semantic_id, "reward/award-info/close")
        self.assertEqual(proof.before_finished_count, 1)
        self.assertEqual(proof.after_finished_count, 0)
        self.assertEqual(
            proof.close_semantic_ids,
            (
                "reward/ship-exp/close",
                "reward/ship-exp/close",
                "reward/award-info/close",
                "reward/award-info/close",
            ),
        )
        self.assertEqual(
            oracle.click_calls,
            [
                "reward/commission/finish",
                "reward/ship-exp/close",
                "reward/ship-exp/close",
                "reward/award-info/close",
                "reward/award-info/close",
                "commission/page/back",
            ],
        )

    def test_commission_reward_claims_multiple_finished_rows_with_one_input(self):
        oracle = FakeOracle()
        oracle.exists_values["reward/commission/finish"] = True
        oracle.enabled_values["reward/commission/finish"] = True
        oracle.reward_summary_values = [2, 2, 0]
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            commission_reward_budget=1,
        )
        adapter.begin_commission()

        self.assertTrue(adapter.commission_reward_pending())
        self.assertTrue(adapter.commission_reward_allowed())
        adapter.click(NamedButton("REWARD_1"))
        adapter._commission_context.reward_close_receipts.append(
            SimpleNamespace(semantic_id="reward/award-info/close")
        )
        proof = adapter.confirm_commission_reward()
        self.assertEqual(proof.before_finished_count, 2)
        self.assertEqual(proof.after_finished_count, 0)
        self.assertEqual(
            oracle.click_calls,
            ["reward/commission/finish", "commission/page/back"],
        )

    def test_commission_reward_revalidates_larger_count_before_input(self):
        oracle = FakeOracle()
        oracle.exists_values["reward/commission/finish"] = True
        oracle.enabled_values["reward/commission/finish"] = True
        oracle.reward_summary_values = [1, 2]
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            commission_reward_budget=1,
        )
        adapter.begin_commission()

        self.assertTrue(adapter.commission_reward_pending())
        self.assertTrue(adapter.commission_reward_allowed())
        receipt = adapter.click(NamedButton("REWARD_1"))

        self.assertEqual(receipt.semantic_id, "reward/commission/finish")
        self.assertEqual(adapter._commission_context.reward_detected_count, 2)
        self.assertEqual(oracle.click_calls, ["reward/commission/finish"])

    def test_unknown_commission_presence_is_false_only_on_proven_surface(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.enabled_values['meowfficer/page/back'] = False
        adapter.begin_commission()
        oracle.exists_values["reward/page/back"] = True

        self.assertFalse(adapter.appear(NamedButton("OIL_MAXED")))
        self.assertFalse(adapter.appear(NamedButton("GUILD_POPUP_CONFIRM")))
        self.assertFalse(adapter.appear(NamedButton("GUILD_POPUP_CANCEL")))

        oracle.exists_values.clear()
        adapter._commission_context.passive_transition_until = time.monotonic() - 1
        with self.assertRaises(AlasSemanticUnmapped):
            adapter.appear(NamedButton("OIL_MAXED"))
        self.assertFalse(adapter.appear(NamedButton("GUILD_POPUP_CONFIRM")))

    def test_commission_page_transition_has_bounded_passive_probe_grace(self):
        adapter, oracle, _ = self.make_adapter()
        adapter.begin_commission()
        adapter.click(NamedButton("REWARD_GOTO_COMMISSION"))

        self.assertFalse(adapter.appear(NamedButton("EXERCISE_CHECK")))

        adapter._commission_context.passive_transition_until = time.monotonic() - 1
        with self.assertRaises(AlasSemanticUnmapped):
            adapter.appear(NamedButton("EXERCISE_CHECK"))

    def test_commission_scroll_delegates_only_inside_commission_context(self):
        adapter, oracle, _ = self.make_adapter()

        with self.assertRaises(SemanticGateClosed):
            adapter.commission_scroll_state()

        adapter.begin_commission()
        state = adapter.commission_scroll_state()
        next_proof = adapter.commission_scroll_next()
        top_proof = adapter.commission_scroll_to_top()

        self.assertTrue(state.scrollable)
        self.assertEqual(next_proof.direction, "next")
        self.assertEqual(top_proof.direction, "top")
        self.assertEqual(
            oracle.commission_scroll_calls,
            ["state", "next", "top"],
        )

    def test_commission_start_uses_exact_row_and_independent_one_input_budget(self):
        oracle = FakeOracle()
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            commission_start_budget=1,
        )
        adapter.begin_commission()
        signature = (
            1,
            "日常资源开发III",
            15,
            3600,
            "pending",
            "faxiankuangmai",
        )
        row = NamedButton("COMMISSION_ROW_1")
        row.semantic_commission_signature = signature

        adapter.click(row)
        self.assertTrue(adapter.appear(NamedButton("COMMISSION_ADVICE")))
        adapter.click(NamedButton("COMMISSION_ADVICE"))
        oracle.commission_detail_value = SimpleNamespace(
            signature=("日常资源开发III", 15, 3600),
            selected_ship_count=6,
            oil_cost=0,
        )
        self.assertTrue(adapter.appear(NamedButton("COMMISSION_START")))
        first = adapter.click(NamedButton("COMMISSION_START"))
        duplicate = adapter.click(NamedButton("COMMISSION_START"))

        self.assertEqual(first, duplicate)
        self.assertFalse(adapter.commission_start_allowed())
        self.assertEqual(
            oracle.click_calls,
            [
                "commission/row/1",
                "commission/detail/recommend",
                "commission/detail/start",
            ],
        )

    def test_commission_start_accepts_nonzero_oil_with_budget(self):
        oracle = FakeOracle()
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            commission_start_budget=1,
        )
        adapter.begin_commission()
        signature = (
            1,
            "日常资源开发III",
            15,
            3600,
            "pending",
            "faxiankuangmai",
        )
        row = NamedButton("COMMISSION_ROW_1")
        row.semantic_commission_signature = signature
        adapter.click(row)
        oracle.commission_detail_value = SimpleNamespace(
            signature=("日常资源开发III", 15, 3600),
            selected_ship_count=6,
            oil_cost=10,
        )

        self.assertTrue(adapter.appear(NamedButton("COMMISSION_START")))
        adapter.click(NamedButton("COMMISSION_START"))
        self.assertEqual(
            oracle.click_calls,
            ["commission/row/1", "commission/detail/start"],
        )

    def test_commission_nonzero_oil_prompt_confirms_exact_recorded_cost(self):
        oracle = FakeOracle()
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            commission_start_budget=1,
        )
        adapter.begin_commission()
        signature = (
            1,
            "日常资源开发III",
            15,
            3600,
            "pending",
            "faxiankuangmai",
        )
        row = NamedButton("COMMISSION_ROW_1")
        row.semantic_commission_signature = signature
        adapter.click(row)
        oracle.commission_detail_value = SimpleNamespace(
            signature=("日常资源开发III", 15, 3600),
            selected_ship_count=6,
            oil_cost=1200,
        )
        adapter.click(NamedButton("COMMISSION_START"))
        oracle.commission_start_prompt_cost_value = 1200

        self.assertTrue(adapter.appear(NamedButton("POPUP_CONFIRM")))
        receipt = adapter.click(NamedButton("POPUP_CONFIRM"))

        self.assertEqual(receipt.semantic_id, "commission/start/confirm")
        self.assertEqual(oracle.click_calls[-1], "commission/start/confirm")

    def test_commission_start_proof_precedes_exact_detail_close(self):
        oracle = FakeOracle()
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            commission_start_budget=1,
        )
        adapter.begin_commission()
        signature = (
            1,
            "日常资源开发III",
            15,
            3600,
            "pending",
            "faxiankuangmai",
        )
        row = NamedButton("COMMISSION_ROW_1")
        row.semantic_commission_signature = signature
        adapter.click(row)
        oracle.commission_detail_value = SimpleNamespace(
            signature=("日常资源开发III", 15, 3600),
            selected_ship_count=6,
            oil_cost=0,
        )
        adapter.click(NamedButton("COMMISSION_START"))

        proof = adapter.commission_start_proof()
        receipt = adapter.close_started_commission_detail()

        self.assertEqual(proof.after_status_sprite, "tag_ongoing")
        self.assertEqual(
            oracle.last_commission_transition_signature,
            signature,
        )
        self.assertEqual(receipt.semantic_id, "commission/detail/back")
        self.assertEqual(
            oracle.wait_calls[-1],
            ("reward/page/back", 12.0, receipt.generation),
        )

    def test_commission_start_defaults_closed(self):
        adapter, _, _ = self.make_adapter()
        adapter.begin_commission()
        self.assertFalse(adapter.commission_start_allowed())

    def test_environment_factory_parses_commission_reward_budget(self):
        environment = {
            "ALAS_SEMANTIC_MODE": "1",
            "ALAS_SEMANTIC_DRIVER_REVISION": (
                "be80ce591a481c12d60c50d6040d40c035b40a2b"
            ),
            "ALAS_SEMANTIC_COMMISSION_REWARD_BUDGET": "1",
        }
        with patch.dict("os.environ", environment, clear=True):
            session = AlasSemanticSession.from_environment("emulator-test")

        self.assertEqual(session.commission_reward_budget, 1)

        environment["ALAS_SEMANTIC_COMMISSION_REWARD_BUDGET"] = "01"
        with patch.dict("os.environ", environment, clear=True):
            with self.assertRaises(SemanticGateClosed):
                AlasSemanticSession.from_environment("emulator-test")

    def test_environment_factory_parses_canonical_commission_start_budget(self):
        environment = {
            "ALAS_SEMANTIC_MODE": "1",
            "ALAS_SEMANTIC_DRIVER_REVISION": (
                "be80ce591a481c12d60c50d6040d40c035b40a2b"
            ),
            "ALAS_SEMANTIC_COMMISSION_START_BUDGET": "1",
        }
        with patch.dict("os.environ", environment, clear=True):
            session = AlasSemanticSession.from_environment("emulator-test")
        self.assertEqual(session.commission_start_budget, 1)

        environment["ALAS_SEMANTIC_COMMISSION_START_BUDGET"] = "01"
        with patch.dict("os.environ", environment, clear=True):
            with self.assertRaises(SemanticGateClosed):
                AlasSemanticSession.from_environment("emulator-test")
