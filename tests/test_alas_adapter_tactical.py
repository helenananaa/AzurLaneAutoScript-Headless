"""Tactical regression cases for the adapter."""

import unittest
from alas_headless import AlasSemanticAdapter, AlasSemanticSession, SemanticGateClosed
from tests.semantic_support.adapter_cases import AlasSemanticAdapterTestsSupport
from tests.semantic_support.adapter_fixtures import FakeOracle, NamedButton
from types import SimpleNamespace
from unittest.mock import patch


class AlasSemanticAdapterTests(AlasSemanticAdapterTestsSupport, unittest.TestCase):
    def test_tactical_assignment_budget_is_spent_only_on_course_confirm(self):
        oracle = FakeOracle()
        oracle.tactical_book_values = [
            SimpleNamespace(position=1, selected=True, count=6)
        ]
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            tactical_assign_budget=1,
        )
        adapter.begin_tactical()

        adapter.click(NamedButton("TACTICAL_CLASS_START"))
        self.assertEqual(adapter._action_ledger.remaining("tactical.assign"), 1)
        receipt = adapter.click(NamedButton("POPUP_CONFIRM_TACTICAL"))

        self.assertEqual(receipt.semantic_id, "tactical/course/confirm")
        self.assertEqual(adapter._action_ledger.remaining("tactical.assign"), 0)
        with self.assertRaises(SemanticGateClosed):
            adapter.click(NamedButton("POPUP_CONFIRM"))

    def test_tactical_navigation_from_build_queue_has_passive_scan_grace(self):
        adapter, oracle, _ = self.make_adapter()
        adapter.begin_tactical()
        oracle.build_queue_visible_value = True
        oracle.enabled_values["build/page/back"] = True

        adapter.click(NamedButton("GOTO_MAIN"))

        self.assertFalse(adapter.appear(NamedButton("EXERCISE_CHECK")))

    def test_tactical_back_has_passive_scan_grace(self):
        adapter, oracle, _ = self.make_adapter()
        adapter.begin_tactical()
        oracle.enabled_values["tactical/dock/back"] = False
        oracle.enabled_values["tactical/page/back"] = True

        receipt = adapter.click(NamedButton("BACK_ARROW"))
        oracle.enabled_values.clear()
        oracle.enabled_values["tactical/dock/back"] = False
        oracle.enabled_values["tactical/page/back"] = False
        duplicate = adapter.click(NamedButton("BACK_ARROW"))

        self.assertEqual(receipt.semantic_id, "tactical/page/back")
        self.assertEqual(duplicate, receipt)
        self.assertEqual(oracle.click_calls, ["tactical/page/back"])
        self.assertFalse(adapter.appear(NamedButton("SP_CHECK")))

    def test_tactical_check_precedes_unrelated_global_page_classification(self):
        adapter, oracle, _ = self.make_adapter()
        adapter.begin_tactical()
        oracle.exists_values["tactical/page/back"] = True
        for target in (
            "tactical/dock/cancel",
            "tactical/skill/confirm",
            "tactical/book/start",
            "tactical/course/confirm",
            "tactical/course/cancel",
        ):
            oracle.enabled_values[target] = False
        oracle.war_archives_page_visible = lambda: (_ for _ in ()).throw(
            AssertionError("unrelated War Archives probe")
        )

        self.assertTrue(adapter.appear(NamedButton("TACTICAL_CHECK")))
        self.assertFalse(adapter.appear(NamedButton("POPUP_CANCEL")))
        self.assertFalse(adapter.appear(NamedButton("POPUP_CONFIRM_WHITE")))
        self.assertFalse(adapter.appear(NamedButton("GET_MISSION")))
        oracle.enabled_values["tactical/course/confirm"] = True
        self.assertFalse(adapter.appear(NamedButton("TACTICAL_CHECK")))
        self.assertFalse(adapter.appear(NamedButton("ADD_NEW_STUDENT")))

    def test_tactical_course_probe_treats_truncated_absent_msgbox_as_non_match(self):
        adapter, oracle, _ = self.make_adapter()
        adapter.begin_tactical()
        oracle.exists_values["tactical/page/back"] = True
        for target in (
            "tactical/dock/cancel",
            "tactical/skill/confirm",
            "tactical/book/start",
        ):
            oracle.enabled_values[target] = False
        enabled = oracle.enabled

        def truncated_course_probe(target):
            if target.startswith("tactical/course/"):
                raise SemanticGateClosed("toggle snapshot is truncated")
            return enabled(target)

        oracle.enabled = truncated_course_probe

        self.assertTrue(adapter.appear(NamedButton("TACTICAL_CHECK")))
        self.assertFalse(adapter.appear(NamedButton("POPUP_CONFIRM")))

    def test_tactical_countdown_and_safe_continue_cancel_use_typed_state(self):
        oracle = FakeOracle()
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            allow_tactical_rewards=True,
        )
        oracle.tactical_slot_values = [SimpleNamespace(slot=1)]
        oracle.tactical_remaining_values = (3723, 90)
        oracle.tactical_prompt_text = "「舰船」学习完成，「技能」技能获得450点经验是否继续学习该技能？"
        adapter.begin_tactical()

        self.assertEqual(len(adapter.tactical_slots()), 1)
        self.assertEqual(adapter.tactical_remaining_seconds(), (3723, 90))
        self.assertTrue(adapter.cancel_tactical_continue_if_present())
        self.assertFalse(adapter.cancel_tactical_continue_if_present())
        self.assertEqual(oracle.click_calls, ["tactical/continue/cancel"])
        adapter.end_commission()

    def test_tactical_continue_cancel_accepts_the_consumed_reward_receipt(self):
        oracle = FakeOracle()
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            allow_tactical_rewards=True,
        )
        oracle.tactical_prompt_text = (
            "「舰船」学习完成，「技能」技能获得450点经验是否继续学习该技能？"
        )
        adapter.begin_tactical()
        reward_receipt = adapter._dispatch_mutation(
            "tactical.reward",
            lambda: oracle.click_receipt("reward/tactical/finish"),
        )
        adapter._commission_context.tactical_reward_receipt = reward_receipt

        self.assertEqual(adapter._action_ledger.remaining("tactical.reward"), 0)
        self.assertTrue(adapter.cancel_tactical_continue_if_present())
        self.assertEqual(oracle.click_calls, ["tactical/continue/cancel"])
        adapter.end_commission()

    def test_tactical_continue_cancel_is_not_cached_without_postcondition(self):
        oracle = FakeOracle()
        oracle.clear_tactical_prompt_on_cancel = False
        prompt = "「舰船」学习完成，「技能」技能获得450点经验是否继续学习该技能？"
        oracle.tactical_prompt_text = prompt
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            allow_tactical_rewards=True,
        )
        adapter.begin_tactical()

        with patch(
            "alas_headless.adapter.semantic.tactical.time.monotonic",
            side_effect=(0.0, 6.0),
        ), self.assertRaisesRegex(SemanticGateClosed, "was not observed"):
            adapter.cancel_tactical_continue_if_present()

        self.assertNotIn(
            prompt, adapter._commission_context.cancelled_tactical_prompts
        )
        self.assertEqual(oracle.click_calls, ["tactical/continue/cancel"])

    def test_tactical_passive_continue_probe_is_false_without_prompt_or_opt_in(self):
        oracle = FakeOracle()
        adapter = AlasSemanticAdapter(oracle, lambda: None)
        adapter.begin_tactical()

        self.assertFalse(adapter.cancel_tactical_continue_if_present())

        oracle.tactical_prompt_text = "舰船学习完成，是否继续学习该技能？"
        with self.assertRaises(SemanticGateClosed):
            adapter.cancel_tactical_continue_if_present()

    def test_tactical_book_progress_ocr_strips_only_the_selected_book_bonus(self):
        adapter, oracle, _ = self.make_adapter()
        adapter.begin_tactical()
        oracle.tactical_book_skill_progress_value = "900/3200"

        value = adapter.ocr_text(
            [(771, 191, 951, 209)], alphabet="0123456789/IDSB"
        )

        self.assertEqual(value, "900/3200")

    def test_environment_factory_keeps_tactical_reward_opt_in_separate(self):
        environment = {
            "ALAS_SEMANTIC_MODE": "1",
            "ALAS_SEMANTIC_DRIVER_REVISION": (
                "be80ce591a481c12d60c50d6040d40c035b40a2b"
            ),
            "ALAS_SEMANTIC_ALLOW_TACTICAL_REWARDS": "1",
        }
        with patch.dict("os.environ", environment, clear=True):
            session = AlasSemanticSession.from_environment("emulator-test")

        self.assertTrue(session.allow_tactical_rewards)
        self.assertEqual(session.commission_reward_budget, 0)
