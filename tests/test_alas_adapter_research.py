"""Research regression cases for the adapter."""

import time
import unittest
from alas_headless import (
    AlasSemanticAdapter,
    AlasSemanticSession,
    AlasSemanticUnmapped,
    ResearchProjectStatus,
    SemanticGateClosed,
)
from tests.semantic_support.adapter_cases import AlasSemanticAdapterTestsSupport
from tests.semantic_support.adapter_fixtures import FakeOracle, NamedButton
from types import SimpleNamespace
from unittest.mock import Mock, patch
from alas_headless.adapter.semantic.contracts import AlasSemanticActionDeferred


class AlasSemanticAdapterTests(AlasSemanticAdapterTestsSupport, unittest.TestCase):
    def test_research_progress_notice_uses_original_popup_port_without_research_task(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.exists_values["research/progress/confirm"] = True
        oracle.enabled_values["research/progress/confirm"] = True
        for name in ("GOTO_MAIN", "GOTO_MAIN_WHITE", "RPG_HOME"):
            self.assertFalse(adapter.appear(NamedButton(name)))
        self.assertTrue(adapter.appear(NamedButton("POPUP_CONFIRM")))
        self.assertTrue(adapter.appear(NamedButton("POPUP_CANCEL")))
        self.assertEqual(adapter.click(NamedButton("POPUP_CONFIRM")).semantic_id, "research/progress/confirm")
        self.assertIsNone(adapter._research_context)

    def test_main_dorm_and_research_menus_use_distinct_typed_buttons(self):
        adapter, _, _ = self.make_adapter()

        self.assertEqual(
            adapter.semantic_id_for("MAIN_GOTO_DORMMENU"), "main/live"
        )
        self.assertEqual(
            adapter.semantic_id_for("MAIN_GOTO_RESHMENU_WHITE"), "main/tech"
        )
        self.assertEqual(
            adapter.semantic_id_for("DORMMENU_GOTO_DORM"), "dorm-menu/dorm"
        )
        self.assertEqual(
            adapter.semantic_id_for("DORMMENU_GOTO_ACADEMY"),
            "dorm-menu/academy",
        )

    def test_research_menu_short_circuits_unrelated_shop_page_probe(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.exists_values["research-menu/page/back"] = True
        oracle.recommendation_shop_visible = Mock(
            side_effect=SemanticGateClosed("shop snapshots are unrelated")
        )

        self.assertFalse(adapter.appear(NamedButton("FLEET_CHECK")))
        self.assertTrue(adapter.appear(NamedButton("RESHMENU_CHECK")))
        oracle.recommendation_shop_visible.assert_not_called()

    def test_research_menu_owns_passive_urgent_commission_probe(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.exists_values['research-menu/page/back'] = True
        self.assertFalse(adapter.appear(NamedButton('GET_MISSION')))
        for name in ('GET_ITEMS_1', 'GET_ITEMS_2', 'GET_ITEMS_3', 'GET_SHIP'):
            self.assertFalse(adapter.appear(NamedButton(name)))
        oracle._campaign_urgent_notice_matches = lambda state: True
        with self.assertRaisesRegex(SemanticGateClosed, 'urgent commission notice'):
            adapter.appear(NamedButton('GET_MISSION'))
        oracle.exists_values['research-menu/page/back'] = False
        oracle._campaign_urgent_notice_matches = lambda state: False
        adapter._record_mission_transition(SimpleNamespace(semantic_id='research/page/back'))
        self.assertGreater(adapter._research_menu_return_transition_until, time.monotonic())
        self.assertFalse(adapter.appear(NamedButton('GET_MISSION')))
        self.assertFalse(adapter.appear(NamedButton('GET_ITEMS_1')))
        self.assertFalse(adapter.appear(NamedButton('MONTHLY_PASS_NOTICE')))
        self.assertFalse(adapter.appear(NamedButton('MAP_PREPARATION')))
        oracle._blocking_rules = lambda state, target: [SimpleNamespace(blocker_id='research-page')]
        self.assertFalse(adapter.appear(NamedButton('MONTHLY_PASS_NOTICE')))
        oracle._blocking_rules = lambda state, target: [SimpleNamespace(blocker_id='unknown-overlay')]
        with self.assertRaisesRegex(AlasSemanticUnmapped, 'MONTHLY_PASS_NOTICE'):
            adapter.appear(NamedButton('MONTHLY_PASS_NOTICE'))
        with self.assertRaisesRegex(AlasSemanticUnmapped, 'MAP_PREPARATION'):
            adapter.appear(NamedButton('MAP_PREPARATION'))
        oracle._blocking_rules = lambda state, target: []
        adapter._research_menu_return_transition_until = 0.0
        with self.assertRaisesRegex(AlasSemanticUnmapped, 'GET_MISSION'):
            adapter.appear(NamedButton('GET_MISSION'))

    def test_research_page_short_circuits_unrelated_page_probe(self):
        adapter, oracle, _ = self.make_adapter()
        adapter.begin_research()
        oracle.exists_values["research/page/back"] = True
        oracle.enabled_values["research/page/back"] = True
        oracle.enabled_values["research/detail/root"] = False
        oracle.research_project_values = [SimpleNamespace(slot=index) for index in range(5)]
        oracle.recommendation_shop_visible = Mock(
            side_effect=SemanticGateClosed("shop snapshots are unrelated")
        )

        self.assertFalse(adapter.appear(NamedButton("FLEET_CHECK")))
        self.assertTrue(adapter.appear(NamedButton("RESEARCH_CHECK")))
        oracle.recommendation_shop_visible.assert_not_called()

    def test_retained_research_page_is_navigable_without_a_research_task(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.exists_values['research/page/back'] = True
        oracle.enabled_values['research/page/back'] = True
        oracle.enabled_values['research/detail/root'] = False
        oracle.research_project_values = [SimpleNamespace(slot=index) for index in range(5)]
        self.assertIsNone(adapter._research_context)
        oracle._blocking_rules = Mock(return_value=[SimpleNamespace(blocker_id='research-page')])
        self.assertFalse(adapter.appear(NamedButton('DOCK_CHECK')))
        self.assertFalse(adapter.appear(NamedButton('GOTO_MAIN_WHITE')))
        self.assertFalse(adapter.appear(NamedButton('RPG_HOME')))
        self.assertFalse(adapter.appear(NamedButton('FLEET_CHECK')))
        self.assertTrue(adapter.appear(NamedButton('RESEARCH_CHECK')))
        self.assertEqual(oracle.click_calls, [])
        oracle.enabled_values['research/page/back'] = True
        self.assertEqual(adapter.click(NamedButton('BACK_ARROW')).semantic_id, 'research/page/back')
        self.assertEqual(oracle.click_calls, ['research/page/back'])
        oracle.exists_values.clear()
        oracle._blocking_rules.return_value = []
        adapter = AlasSemanticAdapter(oracle, package_gate=lambda: None)
        with self.assertRaises(AlasSemanticUnmapped):
            adapter.appear(NamedButton('DOCK_CHECK'))

    def test_research_page_check_rejects_selected_detail_panel(self):
        adapter, oracle, _ = self.make_adapter()
        adapter.begin_research()
        oracle.research_projects_visible_value = False
        oracle.enabled_values["research/detail/root"] = True

        self.assertFalse(adapter.appear(NamedButton("RESEARCH_CHECK")))

    def test_research_decision_preserves_native_unknown_card_and_complete_snapshot(self):
        adapter, oracle, _ = self.make_adapter()
        adapter.begin_research()
        oracle.research_project_values = [
            SimpleNamespace(
                slot=slot,
                unity_index=slot,
                code="Q-{0:03d}".format(slot),
                series=9,
                duration_seconds=1800,
            )
            for slot in range(1, 6)
        ]

        class Project:
            def __init__(self, name, series):
                self.name = name
                self.series = series
                self.valid = name != "Q-003"

        projects = adapter.research_projects_for_alas(Project)
        self.assertEqual([project.valid for project in projects], [True, True, False, True, True])
        self.assertEqual(oracle.click_calls, [])

        oracle.research_project_values[2].code = "Q-103"
        projects = adapter.research_projects_for_alas(Project)
        self.assertEqual([project.name for project in projects], [
            "Q-001", "Q-002", "Q-103", "Q-004", "Q-005"
        ])
        oracle.research_project_values[4].slot = 4
        with self.assertRaisesRegex(SemanticGateClosed, "slots are incomplete"):
            adapter.research_projects_for_alas(Project)
        self.assertEqual(oracle.click_calls, [])

    def test_research_page_stable_requires_two_identical_typed_snapshots(self):
        adapter, oracle, _ = self.make_adapter()
        adapter.begin_research()
        oracle.research_project_values = [
            SimpleNamespace(
                slot=slot,
                unity_index=slot,
                code="Q-{0:03d}".format(slot),
                series=9,
                duration_seconds=1800,
                status=ResearchProjectStatus.DETAIL,
            )
            for slot in range(1, 6)
        ]

        adapter.research_page_stable()

        self.assertEqual(oracle.click_calls, [])
        self.assertEqual(adapter.research_statuses(), ["detail"] * 5)

    def test_research_detail_stable_requires_two_identical_typed_snapshots(self):
        adapter, oracle, _ = self.make_adapter()
        adapter.begin_research()
        oracle.research_detail_value = SimpleNamespace(
            code="G-412",
            subtitle="small project",
            duration_seconds=5400,
            resource_id="gold",
            resource_owned=9000,
            resource_required=1500,
            requirement="",
            can_start=True,
            can_queue=False,
            is_running=False,
            is_finished=False,
        )

        adapter.research_detail_stable()

        self.assertEqual(oracle.click_calls, [])

    def test_research_code_selection_tracks_the_current_card_position(self):
        adapter, oracle, _ = self.make_adapter()
        refreshed = []
        adapter._input_frame_refresher = lambda: refreshed.append(True)
        adapter.begin_research()
        oracle.research_project_values = [
            SimpleNamespace(
                slot=1,
                unity_index=2,
                code="G-236-MI",
                status=ResearchProjectStatus.DETAIL,
            ),
            SimpleNamespace(
                slot=5,
                unity_index=1,
                code="D-381-MI",
                status=ResearchProjectStatus.DETAIL,
            ),
        ]

        receipt = adapter.click_research_project_code("G-236-MI")

        self.assertEqual(receipt.semantic_id, "research/project/1")
        self.assertEqual(adapter._research_context.selected_slot, 1)
        self.assertEqual(adapter._research_context.selected_code, "G-236-MI")
        self.assertEqual(oracle.click_calls, ["research/project/1"])
        self.assertEqual(refreshed, [True])

    def test_research_code_selection_retries_fresh_snapshot_without_using_cache(self):
        adapter, oracle, _ = self.make_adapter()
        adapter.begin_research()
        oracle.research_project_values = [
            SimpleNamespace(
                slot=1,
                unity_index=1,
                code="D-737-MI",
                status=ResearchProjectStatus.DETAIL,
            )
        ]
        self.assertEqual(adapter.research_projects()[0].code, "D-737-MI")
        original_projects = oracle.research_projects
        reads = 0

        def transitional_projects():
            nonlocal reads
            reads += 1
            if reads == 1:
                raise SemanticGateClosed("research snapshots are not coherent")
            return original_projects()

        oracle.research_projects = transitional_projects
        receipt = adapter.click_research_project_code("D-737-MI")

        self.assertEqual(receipt.semantic_id, "research/project/1")
        self.assertEqual(reads, 2)
        self.assertEqual(oracle.click_calls, ["research/project/1"])

    def test_research_code_selection_rejects_a_cached_card_that_was_replaced(self):
        adapter, oracle, _ = self.make_adapter()
        adapter.begin_research()
        oracle.research_project_values = [
            SimpleNamespace(
                slot=1,
                unity_index=1,
                code="D-737-MI",
                status=ResearchProjectStatus.DETAIL,
            )
        ]
        adapter.research_projects()
        oracle.research_project_values = [
            SimpleNamespace(
                slot=1,
                unity_index=1,
                code="G-236-MI",
                status=ResearchProjectStatus.DETAIL,
            )
        ]

        with self.assertRaisesRegex(SemanticGateClosed, "ambiguous"):
            adapter.click_research_project_code("D-737-MI")

        self.assertEqual(oracle.click_calls, [])

    def test_research_code_selection_uses_upstream_position_for_duplicates(self):
        adapter, oracle, _ = self.make_adapter()
        adapter.begin_research()
        oracle.research_project_values = [
            SimpleNamespace(
                slot=1,
                unity_index=1,
                code="C-153-MI",
                series=9,
                status=ResearchProjectStatus.DETAIL,
            ),
            SimpleNamespace(
                slot=5,
                unity_index=2,
                code="C-153-MI",
                series=9,
                status=ResearchProjectStatus.DETAIL,
            ),
        ]

        with self.assertRaisesRegex(SemanticGateClosed, "ambiguous"):
            adapter.click_research_project_code("C-153-MI")
        receipt = adapter.click_research_project_code(
            "C-153-MI", position=1, series=9
        )

        self.assertEqual(receipt.semantic_id, "research/project/5")
        self.assertEqual(adapter._research_context.selected_slot, 5)

        with self.assertRaisesRegex(SemanticGateClosed, "no longer matches"):
            adapter.click_research_project_code("G-236-MI", position=1, series=9)

    def test_research_queue_entry_retries_only_before_one_exact_input(self):
        adapter, oracle, _ = self.make_adapter()
        refreshed = []
        adapter._input_frame_refresher = lambda: refreshed.append(True)
        adapter.begin_research()
        original_click = oracle.click
        attempts = 0

        def transitional_click(semantic_id):
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise SemanticGateClosed("semantic target is not actionable")
            return original_click(semantic_id)

        oracle.click = transitional_click
        with patch("alas_headless.alas_adapter.time.sleep") as sleep:
            receipt = adapter.click(NamedButton("RESEARCH_GOTO_QUEUE"))

        self.assertEqual(receipt.semantic_id, "research/queue/enter")
        self.assertEqual(refreshed, [True, True])
        self.assertEqual(oracle.click_calls, ["research/queue/enter"])
        sleep.assert_called_once_with(0.25)

    def test_research_queue_entry_requires_panel_postcondition_without_second_input(self):
        adapter, oracle, _ = self.make_adapter()
        adapter.begin_research()
        oracle.research_queue_visible_value = False

        for _ in range(2):
            with self.assertRaisesRegex(SemanticGateClosed, "identity is not proven"):
                adapter.click(NamedButton("RESEARCH_GOTO_QUEUE"))

        self.assertEqual(oracle.click_calls, ["research/queue/enter"])

    def test_research_atomic_start_confirms_the_selected_exact_cost(self):
        oracle = FakeOracle()
        oracle.research_project_values = [
            SimpleNamespace(
                slot=1,
                unity_index=3,
                code="G-236-MI",
                status=ResearchProjectStatus.DETAIL,
            )
        ]
        oracle.research_detail_value = SimpleNamespace(
            code="G-236-MI",
            subtitle="small project",
            duration_seconds=9000,
            resource_id="gold",
            resource_owned=51507,
            resource_required=3000,
            requirement="",
            can_start=True,
            can_queue=False,
            is_running=False,
            is_finished=False,
        )
        oracle.research_prompt_cost = ("gold", 3000)
        original_click = oracle.click

        def click(semantic_id):
            receipt = original_click(semantic_id)
            if semantic_id == "research/start/confirm":
                oracle.research_detail_value.is_running = True
                oracle.research_detail_value.can_start = False
            return receipt

        oracle.click = click
        original_prompt_cost = oracle.research_start_prompt_cost
        prompt_reads = 0

        def research_start_prompt_cost():
            nonlocal prompt_reads
            prompt_reads += 1
            if prompt_reads == 1:
                raise SemanticGateClosed("Msgbox snapshots are not coherent")
            return original_prompt_cost()

        oracle.research_start_prompt_cost = research_start_prompt_cost
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            research_start_budget=1,
        )
        adapter.begin_research()

        self.assertTrue(adapter.start_research_project_code("G-236-MI"))

        self.assertEqual(adapter._action_ledger.remaining("research.start"), 0)
        self.assertGreaterEqual(prompt_reads, 2)
        self.assertEqual(
            oracle.click_calls,
            [
                "research/project/1",
                "research/detail/start",
                "research/start/confirm",
            ],
        )

    def test_research_atomic_start_preserves_running_project_for_queue_add(self):
        oracle = FakeOracle()
        oracle.research_project_values = [
            SimpleNamespace(
                slot=2,
                unity_index=4,
                code="G-412-MI",
                status=ResearchProjectStatus.RUNNING,
            )
        ]
        oracle.research_detail_value = SimpleNamespace(
            code="G-412-MI",
            subtitle="small project",
            duration_seconds=5400,
            resource_id="",
            resource_owned=0,
            resource_required=0,
            requirement="",
            can_start=False,
            can_queue=True,
            is_running=True,
            is_finished=False,
        )
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            research_start_budget=1,
        )
        adapter.begin_research()

        self.assertTrue(adapter.start_research_project_code("G-412-MI"))
        self.assertEqual(adapter._action_ledger.remaining("research.start"), 1)
        self.assertEqual(oracle.click_calls, ["research/project/2"])

    def test_research_atomic_start_dispatches_resource_free_project_directly(self):
        oracle = FakeOracle()
        oracle.research_project_values = [
            SimpleNamespace(
                slot=4,
                unity_index=5,
                code="C-153-MI",
                status=ResearchProjectStatus.DETAIL,
            )
        ]
        oracle.research_detail_value = SimpleNamespace(
            code="C-153-MI",
            subtitle="medium project",
            duration_seconds=21600,
            resource_id="",
            resource_owned=0,
            resource_required=0,
            requirement="",
            can_start=True,
            can_queue=False,
            is_running=False,
            is_finished=False,
        )
        original_click = oracle.click

        def click(semantic_id):
            receipt = original_click(semantic_id)
            if semantic_id == "research/detail/start":
                oracle.research_detail_value.is_running = True
                oracle.research_detail_value.can_start = False
            return receipt

        oracle.click = click
        adapter = AlasSemanticAdapter(oracle, lambda: None, research_start_budget=1)
        adapter.begin_research()

        self.assertTrue(adapter.start_research_project_code("C-153-MI"))
        self.assertEqual(adapter._action_ledger.remaining("research.start"), 0)
        self.assertEqual(
            oracle.click_calls,
            ["research/project/4", "research/detail/start"],
        )

    def test_research_atomic_start_matches_normalized_part_prompt(self):
        oracle = FakeOracle()
        oracle.research_project_values = [
            SimpleNamespace(
                slot=1,
                unity_index=1,
                code="Q-289-MI",
                status=ResearchProjectStatus.DETAIL,
            )
        ]
        oracle.research_detail_value = SimpleNamespace(
            code="Q-289-MI",
            subtitle="small project",
            duration_seconds=7200,
            resource_id="research_part_t2",
            resource_owned=29300,
            resource_required=20,
            requirement="",
            can_start=True,
            can_queue=False,
            is_running=False,
            is_finished=False,
        )
        oracle.research_prompt_cost = ("research_part_t2", 20)
        original_click = oracle.click

        def click(semantic_id):
            receipt = original_click(semantic_id)
            if semantic_id == "research/start/confirm":
                oracle.research_detail_value.is_running = True
                oracle.research_detail_value.can_start = False
            return receipt

        oracle.click = click
        adapter = AlasSemanticAdapter(oracle, lambda: None, research_start_budget=1)
        adapter.begin_research()

        self.assertTrue(adapter.start_research_project_code("Q-289-MI"))
        self.assertEqual(adapter._action_ledger.remaining("research.start"), 0)
        self.assertEqual(
            oracle.click_calls,
            [
                "research/project/1",
                "research/detail/start",
                "research/start/confirm",
            ],
        )

    def test_research_multi_resource_insufficient_closes_without_start(self):
        oracle = FakeOracle()
        oracle.research_project_values = [
            SimpleNamespace(
                slot=1,
                unity_index=5,
                code="Q-068-UL",
                status=ResearchProjectStatus.DETAIL,
            )
        ]
        oracle.research_detail_value = SimpleNamespace(
            code="Q-068-UL",
            subtitle="small project",
            duration_seconds=1800,
            resource_id="gold",
            resource_owned=1380,
            resource_required=5000,
            resource_costs=(
                SimpleNamespace(resource_id="gold", owned=1380, required=5000),
                SimpleNamespace(resource_id="17033", owned=29858, required=20),
            ),
            requirement="",
            can_start=False,
            can_queue=False,
            is_running=False,
            is_finished=False,
        )
        adapter = AlasSemanticAdapter(oracle, lambda: None, research_start_budget=0)
        adapter.begin_research()

        self.assertFalse(adapter.start_research_project_code("Q-068-UL"))

        self.assertEqual(
            oracle.click_calls,
            ["research/project/1", "research/detail/root"],
        )
        self.assertEqual(adapter._action_ledger.remaining("research.start"), 0)

    def test_research_multi_resource_start_confirms_all_costs(self):
        oracle = FakeOracle()
        oracle.research_project_values = [
            SimpleNamespace(
                slot=1,
                unity_index=5,
                code="Q-068-UL",
                status=ResearchProjectStatus.DETAIL,
            )
        ]
        oracle.research_detail_value = SimpleNamespace(
            code="Q-068-UL",
            subtitle="small project",
            duration_seconds=1800,
            resource_id="gold",
            resource_owned=6000,
            resource_required=5000,
            resource_costs=(
                SimpleNamespace(resource_id="gold", owned=6000, required=5000),
                SimpleNamespace(resource_id="17033", owned=30, required=20),
            ),
            requirement="",
            can_start=True,
            can_queue=False,
            is_running=False,
            is_finished=False,
        )
        adapter = AlasSemanticAdapter(oracle, lambda: None, research_start_budget=1)
        adapter.begin_research()

        oracle.research_start_prompt_costs = lambda: (("17033", 20), ("gold", 5000))
        original_click = oracle.click
        def click(semantic_id):
            receipt = original_click(semantic_id)
            if semantic_id == "research/start/confirm":
                oracle.research_detail_value.is_running = True
                oracle.research_detail_value.can_start = False
            return receipt
        oracle.click = click
        self.assertTrue(adapter.start_research_project_code("Q-068-UL"))
        self.assertEqual(oracle.click_calls, ["research/project/1", "research/detail/start", "research/start/confirm"])
        self.assertEqual(adapter._action_ledger.remaining("research.start"), 0)

    def test_research_multi_resource_confirmation_rejects_missing_or_changed_cost(self):
        oracle = FakeOracle()
        oracle.research_detail_value.resource_costs = (
            SimpleNamespace(resource_id="gold", owned=6000, required=5000),
            SimpleNamespace(resource_id="17033", owned=30, required=20),
        )
        adapter = AlasSemanticAdapter(oracle, lambda: None, research_start_budget=1)
        adapter.begin_research()
        adapter.click(NamedButton("RESEARCH_START"))
        for costs in ((("gold", 5000),), (("17033", 21), ("gold", 5000)),
                      (("17033", 20), ("gold", 5001)), None):
            with self.subTest(costs=costs):
                oracle.research_start_prompt_costs = lambda: costs
                self.assertFalse(adapter.appear(NamedButton("POPUP_CONFIRM")))
                with self.assertRaisesRegex(SemanticGateClosed, "does not match"):
                    adapter.click(NamedButton("POPUP_CONFIRM"))
                self.assertEqual(adapter._action_ledger.remaining("research.start"), 1)
                self.assertEqual(oracle.click_calls, ["research/detail/start"])
        oracle.research_start_prompt_costs = lambda: (("17033", 20), ("gold", 5000))
        self.assertTrue(adapter.appear(NamedButton("POPUP_CONFIRM")))
        adapter.click(NamedButton("POPUP_CONFIRM"))
        self.assertEqual(adapter._action_ledger.remaining("research.start"), 0)

    def test_research_cost_change_at_input_frame_preserves_grant(self):
        oracle = FakeOracle()
        adapter = AlasSemanticAdapter(oracle, lambda: None, research_start_budget=1)
        adapter.begin_research()
        adapter.click(NamedButton("RESEARCH_START"))
        fresh = FakeOracle()
        fresh.research_prompt_cost = ("gold", 1501)
        adapter._fresh_input_oracle = lambda: fresh
        with self.assertRaisesRegex(SemanticGateClosed, "changed before"):
            adapter.click(NamedButton("POPUP_CONFIRM"))
        self.assertEqual(fresh.click_calls, [])
        self.assertEqual(adapter._action_ledger.remaining("research.start"), 1)
        fresh.research_prompt_cost = ("gold", 1500)
        adapter.click(NamedButton("POPUP_CONFIRM"))
        self.assertEqual(fresh.click_calls, ["research/start/confirm"])
        self.assertEqual(adapter._action_ledger.remaining("research.start"), 0)

    def test_research_start_budget_is_spent_only_on_matching_final_confirm(self):
        oracle = FakeOracle()
        project = SimpleNamespace(
            slot=1,
            code="G-412",
            status=ResearchProjectStatus.DETAIL,
            button=SimpleNamespace(actionable=True),
        )
        oracle.research_project_values = [project]
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            research_start_budget=1,
        )
        adapter.begin_research()

        adapter.click(NamedButton("ENTRANCE_1"))
        adapter.click(NamedButton("RESEARCH_START"))
        self.assertEqual(adapter._action_ledger.remaining("research.start"), 1)
        self.assertTrue(adapter.appear(NamedButton("POPUP_CANCEL")))
        self.assertTrue(adapter.appear(NamedButton("POPUP_CONFIRM")))
        receipt = adapter.click(NamedButton("POPUP_CONFIRM_RESEARCH_START"))

        self.assertEqual(receipt.semantic_id, "research/start/confirm")
        self.assertEqual(adapter._action_ledger.remaining("research.start"), 0)
        with self.assertRaises(SemanticGateClosed):
            adapter.click(NamedButton("POPUP_CONFIRM"))
        self.assertEqual(
            oracle.click_calls,
            [
                "research/project/1",
                "research/detail/start",
                "research/start/confirm",
            ],
        )

    def test_research_start_budget_can_admit_one_existing_running_queue_add(self):
        for status in (ResearchProjectStatus.RUNNING, ResearchProjectStatus.WAITING):
            with self.subTest(status=status):
                oracle = FakeOracle()
                oracle.research_project_values = [
                    SimpleNamespace(slot=1, code="G-412", status=status)
                ]
                adapter = AlasSemanticAdapter(
                    oracle, lambda: None, research_start_budget=1,
                )
                adapter.begin_research()
                adapter.click(NamedButton("ENTRANCE_1"))

                receipt = adapter.click(NamedButton("RESEARCH_QUEUE_ADD"))
                duplicate = adapter.click(NamedButton("RESEARCH_QUEUE_ADD"))

                self.assertEqual(receipt.semantic_id, "research/detail/queue")
                self.assertEqual(duplicate, receipt)
                self.assertEqual(adapter._action_ledger.remaining("research.start"), 1)
                self.assertTrue(adapter.appear(NamedButton("POPUP_CANCEL")))
                self.assertTrue(adapter.appear(NamedButton("POPUP_CONFIRM")))
                confirm = adapter.click(NamedButton("POPUP_CONFIRM_RESEARCH_QUEUE"))
                self.assertEqual(confirm.semantic_id, "research/queue/confirm")
                self.assertEqual(adapter._action_ledger.remaining("research.start"), 0)
                self.assertEqual(
                    oracle.click_calls,
                    ["research/project/1", "research/detail/queue", "research/queue/confirm"],
                )

                gated = AlasSemanticAdapter(oracle, lambda: None)
                gated.begin_research()
                gated.click(NamedButton("ENTRANCE_1"))
                with self.assertRaisesRegex(AlasSemanticActionDeferred, "research.start"):
                    gated.click(NamedButton("RESEARCH_QUEUE_ADD"))

                oracle.enabled_values["research/detail/stop"] = False
                unsafe = AlasSemanticAdapter(
                    oracle, lambda: None, research_start_budget=1,
                )
                unsafe.begin_research()
                unsafe.click(NamedButton("ENTRANCE_1"))
                with self.assertRaisesRegex(SemanticGateClosed, "budgeted running project"):
                    unsafe.click(NamedButton("RESEARCH_QUEUE_ADD"))

    def test_research_session_prioritizes_exact_network_reconnect_popup(self):
        adapter, oracle, _ = self.make_adapter()
        adapter.begin_research()
        oracle.enabled_values["overlay/network-reconnect/cancel"] = True
        oracle.enabled_values["overlay/network-reconnect/confirm"] = True
        session = AlasSemanticSession.__new__(AlasSemanticSession)
        session.adapter = adapter
        session.open = lambda: adapter
        session.refresh_frame = lambda: None

        self.assertFalse(session.appear(NamedButton("RESEARCH_CHECK")))
        self.assertTrue(session.appear(NamedButton("POPUP_CANCEL")))
        self.assertTrue(session.appear(NamedButton("POPUP_CONFIRM")))
        receipt = session.click(NamedButton("POPUP_CONFIRM"))
        self.assertEqual(receipt.semantic_id, "overlay/network-reconnect/confirm")
        self.assertEqual(oracle.click_calls, ["overlay/network-reconnect/confirm"])
        adapter.end_research()

    def test_research_menu_entries_use_exact_typed_buttons(self):
        adapter, _, _ = self.make_adapter()

        self.assertEqual(
            adapter.semantic_id_for("RESHMENU_GOTO_RESEARCH"),
            "research-menu/research",
        )
        self.assertEqual(
            adapter.semantic_id_for("RESHMENU_GOTO_SHIPYARD"),
            "research-menu/shipyard",
        )
        self.assertEqual(
            adapter.semantic_id_for("ENTRANCE_3"), "research/project/3"
        )

    def test_research_ocr_companions_use_typed_project_model(self):
        adapter, oracle, _ = self.make_adapter()
        adapter.begin_research()
        oracle.research_project_values = [
            SimpleNamespace(
                slot=1,
                series=9,
                status=ResearchProjectStatus.DETAIL,
            ),
            SimpleNamespace(
                slot=2,
                series=8,
                status=ResearchProjectStatus.RUNNING,
            ),
        ]

        self.assertEqual(adapter.research_series(), [9, 8])
        self.assertEqual(adapter.research_statuses(), ["detail", "running"])
        self.assertIsNone(adapter.research_finished_index())

    def test_research_navigation_has_bounded_passive_scan_grace(self):
        adapter, oracle, _ = self.make_adapter()
        adapter.begin_research()

        main_entry = adapter.click(NamedButton("MAIN_GOTO_RESHMENU"))
        main_duplicate = adapter.click(NamedButton("MAIN_GOTO_RESHMENU_WHITE"))
        research_entry = adapter.click(NamedButton("RESHMENU_GOTO_RESEARCH"))
        research_duplicate = adapter.click(NamedButton("RESHMENU_GOTO_RESEARCH"))
        queue_entry = adapter.click(NamedButton("RESEARCH_GOTO_QUEUE"))
        queue_duplicate = adapter.click(NamedButton("RESEARCH_GOTO_QUEUE"))
        back = adapter.click(NamedButton("BACK_ARROW"))
        back_duplicate = adapter.click(NamedButton("BACK_ARROW"))

        self.assertEqual(main_duplicate, main_entry)
        self.assertEqual(research_duplicate, research_entry)
        self.assertEqual(queue_duplicate, queue_entry)
        self.assertEqual(back_duplicate, back)
        self.assertEqual(
            oracle.click_calls,
            [
                "main/tech",
                "research-menu/research",
                "research/queue/enter",
                "research/page/back",
            ],
        )
        self.assertFalse(adapter.appear(NamedButton("FLEET_CHECK")))
        adapter._research_context.passive_transition_until = time.monotonic() - 1.0
        self.assertFalse(adapter.appear(NamedButton("FLEET_CHECK")))
        adapter._research_menu_return_transition_until = time.monotonic() - 1.0
        with self.assertRaises(AlasSemanticUnmapped):
            adapter.appear(NamedButton("FLEET_CHECK"))

    def test_main_tech_repeat_waits_for_exact_research_menu(self):
        adapter, oracle, _ = self.make_adapter()
        first = adapter.click(NamedButton('MAIN_GOTO_RESHMENU'))
        oracle.enabled_values['main/tech'] = False
        oracle.exists_values['research-menu/page/back'] = False
        oracle.enabled_values['research-menu/page/back'] = False
        def source_not_actionable(target):
            oracle.exists_values['research-menu/page/back'] = True
            oracle.enabled_values['research-menu/page/back'] = True
            raise SemanticGateClosed('semantic target is not actionable')

        oracle.click = Mock(side_effect=source_not_actionable)
        oracle.read_state = Mock(return_value=SimpleNamespace(generation=first.generation + 1))
        repeated = adapter.click(NamedButton('MAIN_GOTO_RESHMENU_WHITE'))

        self.assertIs(repeated, first)
        oracle.click.assert_called_once_with('main/tech')

    def test_research_entry_after_grace_requires_fresh_destination(self):
        adapter, oracle, _ = self.make_adapter()
        adapter.begin_research()
        first = adapter.click(NamedButton("RESHMENU_GOTO_RESEARCH"))
        adapter._research_context.passive_transition_until = 0
        oracle.enabled_values["research/page/back"] = True
        oracle.research_projects = Mock(return_value=[object()] * 5)
        oracle.read_state = Mock(return_value=SimpleNamespace(generation=first.generation + 1))
        self.assertIs(adapter.click(NamedButton("RESHMENU_GOTO_RESEARCH")), first)
        self.assertEqual(oracle.click_calls, ["research-menu/research"])
        for visible, enabled, generation in ((False, True, first.generation + 1),
                                             (True, False, first.generation + 1),
                                             (True, True, first.generation)):
            oracle.research_projects.return_value = [object()] * 5 if visible else []
            oracle.enabled_values["research/page/back"] = enabled
            oracle.read_state.return_value.generation = generation
            self.assertIsNone(adapter._research_entry_completed())
        adapter.end_research()
        self.assertIsNone(adapter._research_entry_completed())

    def test_research_entry_missing_source_rechecks_destination_before_input_only(self):
        from alas_headless.oracle.errors import SemanticTargetMissing
        adapter, oracle, _ = self.make_adapter()
        adapter.begin_research()
        first = adapter.click(NamedButton("RESHMENU_GOTO_RESEARCH"))
        adapter._research_context.passive_transition_until = 0
        adapter._research_entry_completed = Mock(side_effect=[None, first])
        oracle.click = Mock(side_effect=SemanticTargetMissing("source disappeared"))
        self.assertIs(adapter.click(NamedButton("RESHMENU_GOTO_RESEARCH")), first)
        adapter._research_entry_completed = Mock(return_value=None)
        oracle.input_dispatch_count = 0
        def uncertain(_):
            oracle.input_dispatch_count += 1
            raise SemanticTargetMissing("after input")
        oracle.click.side_effect = uncertain
        with self.assertRaises(SemanticTargetMissing):
            adapter.click(NamedButton("RESHMENU_GOTO_RESEARCH"))
        adapter._research_entry_completed.assert_called_once()

    def test_research_goto_main_is_idempotent_during_page_transition(self):
        adapter, oracle, _ = self.make_adapter()
        adapter.begin_research()
        oracle.exists_values["research/page/back"] = True
        oracle.enabled_values["research/page/back"] = True

        first = adapter.click(NamedButton("GOTO_MAIN"))
        duplicate = adapter.click(NamedButton("GOTO_MAIN"))

        self.assertEqual(duplicate, first)
        self.assertEqual(oracle.click_calls, ["research/page/back"])

    def test_research_queue_round_trips_do_not_reuse_opposite_navigation(self):
        adapter, oracle, _ = self.make_adapter()
        adapter.begin_research()
        for _ in range(2):
            entry = adapter.click(NamedButton("RESEARCH_GOTO_QUEUE"))
            self.assertIs(adapter.click(NamedButton("RESEARCH_GOTO_QUEUE")), entry)
            back = adapter.click(NamedButton("BACK_ARROW"))
            self.assertIs(adapter.click(NamedButton("BACK_ARROW")), back)
        self.assertEqual(oracle.click_calls, [
            "research/queue/enter", "research/page/back",
            "research/queue/enter", "research/page/back",
        ])

    def test_research_queue_snapshot_is_bounded_across_queue_exit(self):
        adapter, oracle, _ = self.make_adapter()
        adapter.begin_research()

        self.assertEqual(adapter.research_queue_empty_slots(), 5)
        oracle.research_queue_visible_value = False

        self.assertEqual(adapter.research_queue_empty_slots(), 5)
        self.assertFalse(adapter.appear(NamedButton("QUEUE_CHECK")))
        adapter._research_context.last_queue_observed_at = time.monotonic() - 31.0
        with self.assertRaisesRegex(SemanticGateClosed, "identity is not proven"):
            adapter.research_queue_empty_slots()

    def test_research_queue_exit_caches_the_last_typed_capacity(self):
        adapter, oracle, _ = self.make_adapter()
        adapter.begin_research()
        oracle.research_queue_visible_value = True

        adapter.click(NamedButton("BACK_ARROW"))
        oracle.research_queue_visible_value = False

        self.assertEqual(adapter.research_queue_empty_slots(), 5)

    def test_research_fill_slots_are_limited_by_current_run_budget(self):
        oracle = FakeOracle()
        oracle.enabled_values["research/queue/enter"] = False
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            research_start_budget=1,
        )
        adapter.begin_research()

        self.assertEqual(adapter.research_queue_fill_slots(), 5)
        gated = AlasSemanticAdapter(oracle, lambda: None)
        gated.begin_research()
        oracle.research_queue_visible_value = False
        self.assertEqual(gated.research_queue_fill_slots(), 0)

    def test_research_fill_reads_card_page_markers_after_queue_reward(self):
        adapter, oracle, _ = self.make_adapter(research_start_budget=1)
        adapter.begin_research()
        oracle.enabled_values["research/queue/enter"] = True
        oracle.research_queue_visible_value = False
        oracle.research_queue_indicator_empty_slots = lambda: 5

        self.assertEqual(adapter.research_queue_fill_slots(), 5)

    def test_research_detail_availability_is_false_before_selection(self):
        adapter, oracle, _ = self.make_adapter()
        adapter.begin_research()
        oracle.exists_values["research/page/back"] = True

        def absent_detail():
            raise SemanticGateClosed("research detail identity is not proven")

        oracle.research_detail_state = absent_detail

        self.assertFalse(adapter.research_detail_available())

    def test_research_detail_availability_includes_current_run_budget(self):
        oracle = FakeOracle()
        gated = AlasSemanticAdapter(oracle, lambda: None)
        gated.begin_research()

        self.assertFalse(gated.research_detail_available())
        self.assertTrue(gated.appear(NamedButton("RESEARCH_UNAVAILABLE")))

        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            research_start_budget=1,
        )
        adapter.begin_research()
        self.assertTrue(adapter.research_detail_available())
        self.assertFalse(adapter.appear(NamedButton("RESEARCH_UNAVAILABLE")))

    def test_research_project_snapshot_has_short_render_grace(self):
        adapter, oracle, _ = self.make_adapter()
        adapter.begin_research()

        self.assertEqual(adapter.research_projects(), ())
        oracle.research_projects_visible_value = False

        self.assertEqual(adapter.research_projects(), ())
        adapter._research_context.last_projects_observed_at = time.monotonic() - 6.0
        with self.assertRaisesRegex(SemanticGateClosed, "page identity is not proven"):
            adapter.research_projects()
