import unittest
from dataclasses import fields
from types import SimpleNamespace

from alas_headless.alas_adapter import (
    AlasSemanticAdapter,
    ResearchProjectStatus,
    _BuildFlowContext,
    _DormFlowContext,
    _ResearchFlowContext,
)
from alas_headless.semantic_oracle import SemanticGateClosed
from tests.test_alas_adapter import FakeOracle, NamedButton


class ResearchDormBuildLedgerTests(unittest.TestCase):
    @staticmethod
    def select_research_project(adapter, oracle):
        oracle.research_project_values = [
            SimpleNamespace(
                slot=1,
                code="G-412",
                status=ResearchProjectStatus.DETAIL,
                button=SimpleNamespace(actionable=True),
            )
        ]
        adapter.click(NamedButton("ENTRANCE_1"))

    @staticmethod
    def expose_build_submit(adapter, oracle):
        oracle.enabled_values.update(
            {
                "build/warning/confirm": False,
                "build/prep/confirm": True,
            }
        )
        adapter.click(NamedButton("MAIN_GOTO_BUILD"))
        adapter.click(NamedButton("BUILD_SUBMIT_ORDERS"))

    def test_flow_contexts_store_evidence_but_no_action_authority(self):
        for context_type in (
            _ResearchFlowContext,
            _DormFlowContext,
            _BuildFlowContext,
        ):
            names = {item.name for item in fields(context_type)}
            self.assertFalse(any(name.endswith("budget") for name in names))
        research_names = {item.name for item in fields(_ResearchFlowContext)}
        self.assertIn("queue_add_requires_start_grant", research_names)
        self.assertNotIn("queue_add_uses_start_budget", research_names)

    def test_zero_grants_refuse_all_family_mutations_before_backend(self):
        cases = []

        research_oracle = FakeOracle()
        research = AlasSemanticAdapter(research_oracle, lambda: None)
        research.begin_research()
        self.select_research_project(research, research_oracle)
        cases.append(
            (research, lambda: research.click(NamedButton("RESEARCH_START")))
        )

        dorm_oracle = FakeOracle()
        dorm = AlasSemanticAdapter(dorm_oracle, lambda: None)
        dorm.begin_dorm()
        cases.append((dorm, lambda: dorm.click(NamedButton("DORM_QUICK_COLLECT"))))

        build_oracle = FakeOracle()
        build = AlasSemanticAdapter(build_oracle, lambda: None)
        build.begin_build()
        self.expose_build_submit(build, build_oracle)
        cases.append(
            (build, lambda: build.click(NamedButton("POPUP_CONFIRM_GACHA_ORDER")))
        )

        for adapter, mutate in cases:
            with self.subTest(adapter=type(adapter).__name__):
                before = list(adapter.oracle.click_calls)
                with self.assertRaises(SemanticGateClosed):
                    mutate()
                self.assertEqual(adapter.oracle.click_calls, before)

    def test_research_start_and_reward_are_one_use_across_flow_reopen(self):
        oracle = FakeOracle()
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            research_start_budget=1,
            research_reward_budget=1,
        )
        adapter.begin_research()
        self.select_research_project(adapter, oracle)
        adapter.click(NamedButton("RESEARCH_START"))
        start = adapter.click(NamedButton("POPUP_CONFIRM_RESEARCH_START"))
        self.assertEqual(start.capability_id, "research.start")
        self.assertEqual(start.policy_sha256, adapter._action_ledger.policy_sha256)

        oracle.research_queue_value = SimpleNamespace(
            entries=(),
            reward_claimable=True,
            empty_slots=5,
            first_remaining_seconds=0,
        )
        reward = adapter.click(NamedButton("QUEUE_CLAIM_REWARD"))
        self.assertEqual(reward.capability_id, "research.reward")

        adapter.end_research()
        adapter.begin_research()
        self.select_research_project(adapter, oracle)
        with self.assertRaises(SemanticGateClosed):
            adapter.click(NamedButton("RESEARCH_START"))
        with self.assertRaises(SemanticGateClosed):
            adapter.click(NamedButton("QUEUE_CLAIM_REWARD"))

    def test_dorm_collect_and_feed_are_one_use_across_flow_reopen(self):
        oracle = FakeOracle()
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            dorm_collect_budget=1,
            dorm_feed_budget=2,
        )
        adapter.begin_dorm()
        collect = adapter.click(NamedButton("DORM_QUICK_COLLECT"))
        feeds = adapter.dorm_feed_food(0, 2)
        self.assertEqual(collect.capability_id, "dorm.collect")
        self.assertEqual([receipt.capability_id for receipt in feeds], ["dorm.feed"] * 2)
        self.assertTrue(
            all(
                receipt.policy_sha256 == adapter._action_ledger.policy_sha256
                for receipt in feeds
            )
        )
        self.assertEqual(adapter._action_ledger.remaining("dorm.feed"), 0)

        adapter.end_dorm()
        adapter.begin_dorm()
        with self.assertRaises(SemanticGateClosed):
            adapter.click(NamedButton("DORM_QUICK_COLLECT"))
        with self.assertRaises(SemanticGateClosed):
            adapter.dorm_feed_food(0, 1)

    def test_build_submit_is_one_use_across_flow_reopen(self):
        oracle = FakeOracle()
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            build_submit_budget=1,
        )
        adapter.begin_build()
        self.expose_build_submit(adapter, oracle)
        receipt = adapter.click(NamedButton("POPUP_CONFIRM_GACHA_ORDER"))
        self.assertEqual(receipt.capability_id, "build.submit")
        self.assertEqual(receipt.policy_sha256, adapter._action_ledger.policy_sha256)

        adapter.end_build()
        adapter.begin_build()
        self.expose_build_submit(adapter, oracle)
        with self.assertRaises(SemanticGateClosed):
            adapter.click(NamedButton("POPUP_CONFIRM_GACHA_ORDER"))
        self.assertEqual(oracle.click_calls.count("build/prep/confirm"), 1)

    def test_backend_exceptions_permanently_consume_each_family_grant(self):
        research_oracle = FakeOracle()
        research = AlasSemanticAdapter(
            research_oracle,
            lambda: None,
            research_start_budget=1,
        )
        research.begin_research()
        self.select_research_project(research, research_oracle)
        research.click(NamedButton("RESEARCH_START"))
        original_research_click = research_oracle.click
        research_oracle.click = lambda semantic_id: (_ for _ in ()).throw(
            RuntimeError("ambiguous research input")
        )
        with self.assertRaises(RuntimeError):
            research.click(NamedButton("POPUP_CONFIRM_RESEARCH_START"))
        research_oracle.click = original_research_click
        self.assertEqual(research._action_ledger.remaining("research.start"), 0)

        dorm_oracle = FakeOracle()
        dorm = AlasSemanticAdapter(
            dorm_oracle,
            lambda: None,
            dorm_feed_budget=1,
        )
        dorm.begin_dorm()
        original_dorm_click = dorm_oracle.click_dorm_food
        dorm_oracle.click_dorm_food = lambda item_id: (_ for _ in ()).throw(
            RuntimeError("ambiguous dorm input")
        )
        with self.assertRaises(RuntimeError):
            dorm.dorm_feed_food(0, 1)
        dorm_oracle.click_dorm_food = original_dorm_click
        self.assertEqual(dorm._action_ledger.remaining("dorm.feed"), 0)

        build_oracle = FakeOracle()
        build = AlasSemanticAdapter(
            build_oracle,
            lambda: None,
            build_submit_budget=1,
        )
        build.begin_build()
        self.expose_build_submit(build, build_oracle)
        original_build_click = build_oracle.click
        build_oracle.click = lambda semantic_id: (_ for _ in ()).throw(
            RuntimeError("ambiguous build input")
        )
        with self.assertRaises(RuntimeError):
            build.click(NamedButton("POPUP_CONFIRM_GACHA_ORDER"))
        build_oracle.click = original_build_click
        self.assertEqual(build._action_ledger.remaining("build.submit"), 0)

    def test_nested_flow_refusal_does_not_consume_or_mint_grants(self):
        adapter = AlasSemanticAdapter(
            FakeOracle(),
            lambda: None,
            research_start_budget=1,
            dorm_collect_budget=1,
            build_submit_budget=1,
        )
        adapter.begin_research()
        with self.assertRaises(SemanticGateClosed):
            adapter.begin_dorm()
        with self.assertRaises(SemanticGateClosed):
            adapter.begin_build()
        self.assertEqual(adapter._action_ledger.remaining("research.start"), 1)
        self.assertEqual(adapter._action_ledger.remaining("dorm.collect"), 1)
        self.assertEqual(adapter._action_ledger.remaining("build.submit"), 1)

    def test_closed_ledger_refuses_all_family_mutations_before_backend(self):
        oracle = FakeOracle()
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            research_start_budget=1,
            dorm_collect_budget=1,
            build_submit_budget=1,
        )
        adapter._action_ledger.close()
        adapter.begin_research()
        self.select_research_project(adapter, oracle)
        before = list(oracle.click_calls)
        with self.assertRaises(SemanticGateClosed):
            adapter.click(NamedButton("RESEARCH_START"))
        self.assertEqual(oracle.click_calls, before)
        adapter.end_research()

        adapter.begin_dorm()
        with self.assertRaises(SemanticGateClosed):
            adapter.click(NamedButton("DORM_QUICK_COLLECT"))
        with self.assertRaises(SemanticGateClosed):
            adapter.dorm_feed_food(0, 1)
        self.assertEqual(oracle.dorm_feed_state_value.food, 0)
        adapter.end_dorm()

        adapter.begin_build()
        self.expose_build_submit(adapter, oracle)
        before = list(oracle.click_calls)
        with self.assertRaises(SemanticGateClosed):
            adapter.click(NamedButton("POPUP_CONFIRM_GACHA_ORDER"))
        self.assertEqual(oracle.click_calls, before)


if __name__ == "__main__":
    unittest.main()
