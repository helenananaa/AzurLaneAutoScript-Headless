"""Boundary regression cases for the adapter."""

import time
import unittest
from alas_headless import (
    AlasSemanticAdapter,
    AlasSemanticUnmapped,
    Bounds,
    MissionDisposition,
    Point,
    RetirementNoCandidateReceipt,
    RetirementSettingsState,
    SemanticGateClosed,
)
from alas_headless.semantic_oracle import ActionReceipt
from tests.semantic_support.adapter_cases import AlasSemanticAdapterTestsSupport
from tests.semantic_support.adapter_fixtures import FakeOracle, NamedButton
from tests.test_semantic_oracle import (
    make_live_eventsp_map_preparation_backend,
    make_oracle as make_real_oracle,
)
from types import SimpleNamespace
from unittest.mock import Mock


class AlasSemanticAdapterTests(AlasSemanticAdapterTestsSupport, unittest.TestCase):
    def test_legacy_appear_traversal_uses_only_the_leased_semantic_frame(self):
        live = FakeOracle()
        frame = FakeOracle()
        frame.enabled_values["main/formation"] = False
        live.enabled = Mock(side_effect=AssertionError("live oracle read"))
        adapter = AlasSemanticAdapter(
            live,
            lambda: None,
            frame_observation_oracle=lambda: frame,
        )

        self.assertFalse(adapter.appear(NamedButton("MAIN_GOTO_FLEET")))
        self.assertIn("main/formation", frame.enabled_calls)

    def test_confirmed_main_aliases_route_to_semantic_targets(self):
        adapter, oracle, gate_calls = self.make_adapter()

        self.assertTrue(adapter.appear(NamedButton("MAIN_GOTO_CAMPAIGN_WHITE")))
        receipt = adapter.click(NamedButton("MAIN_GOTO_FLEET"))

        self.assertEqual(
            oracle.enabled_calls,
            [
                "overlay/network-reconnect/confirm",
                "overlay/bulletin/close",
                "overlay/bulletin/close",
                "overlay/guild-message/close",
                "login/enter",
                "overlay/bulletin/close",
                "main/battle",
            ],
        )
        self.assertEqual(oracle.click_calls, ["main/formation"])
        self.assertEqual(receipt.semantic_id, "main/formation")
        self.assertEqual(len(gate_calls), 2)

    def test_os_check_requires_unobstructed_local_map(self):
        adapter, oracle, _ = self.make_adapter()

        oracle.enabled_values["os/page/back"] = True
        oracle.operation_siren_local_map_visible_value = False
        self.assertFalse(adapter.appear(NamedButton("OS_CHECK")))

        oracle.operation_siren_local_map_visible_value = True
        self.assertTrue(adapter.appear(NamedButton("OS_CHECK")))

        oracle.operation_siren_exit_prompt_visible = lambda: True
        self.assertFalse(adapter.appear(NamedButton("OS_CHECK")))

    def test_generic_page_scan_does_not_claim_month_sign_below_award_overlay(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.exists_values.update(
            {
                "event-list/page/back": True,
                "reward/award-info/close": True,
            }
        )

        with self.assertRaisesRegex(AlasSemanticUnmapped, "FLEET_CHECK"):
            adapter.appear(NamedButton("FLEET_CHECK"))

    def test_private_quarters_home_transition_only_leases_passive_page_scan(self):
        adapter, _, _ = self.make_adapter()
        adapter._private_quarters_home_transition_until = time.monotonic() + 30.0
        self.assertFalse(adapter.appear(NamedButton("FLEET_CHECK")))
        with self.assertRaises(AlasSemanticUnmapped):
            adapter.click(NamedButton("FLEET_CHECK"))
        adapter._private_quarters_home_transition_until = 0.0
        with self.assertRaisesRegex(AlasSemanticUnmapped, "FLEET_CHECK"):
            adapter.appear(NamedButton("FLEET_CHECK"))

    def test_network_reconnect_popup_uses_only_exact_semantic_targets(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.enabled_values.update(
            {
                "overlay/network-reconnect/cancel": True,
                "overlay/network-reconnect/confirm": True,
            }
        )

        self.assertTrue(adapter.appear(NamedButton("POPUP_CANCEL")))
        self.assertTrue(adapter.appear(NamedButton("POPUP_CONFIRM")))
        receipt = adapter.click(NamedButton("POPUP_CONFIRM_UI_ADDITIONAL"))

        self.assertEqual(receipt.semantic_id, "overlay/network-reconnect/confirm")
        self.assertEqual(oracle.click_calls, ["overlay/network-reconnect/confirm"])
        self.assertFalse(adapter.appear(NamedButton("DOCK_CHECK")))

        adapter._network_reconnect_transition_until = 0.0
        with self.assertRaises(AlasSemanticUnmapped):
            adapter.appear(NamedButton("DOCK_CHECK"))

    def test_official_no_candidate_result_is_receipted_and_not_retried(self):
        adapter, oracle, gate_calls = self.make_adapter(retirement_budget=1)
        oracle.retirement_receipt_value = RetirementNoCandidateReceipt(
            capacity_used=814,
            capacity_total=910,
            settings=RetirementSettingsState(
                generation=24,
                unique_ship_protection=True,
                priority=("R", "SR", "N"),
                full_star_policy="keep_none",
                no_full_star_policy="keep_needed",
            ),
            official_message="<color=white>没找到符合条件的舰船</color>",
            actions=(
                ActionReceipt(
                    semantic_id="retirement/one-click",
                    generation=23,
                    point=Point(725, 673),
                    bounds=Bounds(634, 639, 816, 707),
                    path="root/blur_panel/select_panel/quick_select",
                ),
            ),
        )

        retired = adapter.retire_ships_one_click(True)
        receipt = adapter.retirement_receipt()

        self.assertEqual(retired, 0)
        self.assertIsInstance(receipt, RetirementNoCandidateReceipt)
        assert isinstance(receipt, RetirementNoCandidateReceipt)
        self.assertEqual(receipt.capability_id, "retirement.execute")
        self.assertEqual(len(receipt.policy_sha256), 64)
        self.assertEqual(adapter._action_ledger.remaining("retirement.execute"), 0)
        self.assertEqual(len(gate_calls), 1)

    def test_goto_main_prioritizes_exact_network_reconnect_popup(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.enabled_values["overlay/network-reconnect/confirm"] = True

        receipt = adapter.click(NamedButton("GOTO_MAIN"))

        self.assertEqual(
            receipt.semantic_id, "overlay/network-reconnect/confirm"
        )
        self.assertEqual(
            oracle.click_calls, ["overlay/network-reconnect/confirm"]
        )

    def test_live_inherited_map_detail_follows_original_cancel_sequence(self):
        backend = make_live_eventsp_map_preparation_backend()
        oracle = make_real_oracle(backend)
        adapter = AlasSemanticAdapter(oracle, lambda: None)
        adapter.begin_campaign_pre_sortie("sp")
        context = adapter._campaign_context
        initial_context = dict(vars(context))
        ledger_before = dict(adapter._action_ledger._remaining)

        self.assertFalse(adapter.appear(NamedButton("EVENT_CHECK")))
        self.assertEqual(vars(context), initial_context)
        self.assertTrue(adapter.appear(NamedButton("MAP_PREPARATION")))
        self.assertEqual(vars(context), initial_context)
        passive_context = dict(vars(context))
        self.assertIsNone(context.entry_receipt)
        self.assertIsNone(context.map_preparation_receipt)
        self.assertIsNone(context.cancel_receipt)
        self.assertEqual(context.fleet_mutation_receipts, [])
        self.assertEqual(adapter._action_ledger._remaining, ledger_before)
        self.assertEqual(backend.taps, [])

        backend.on_tap = lambda: self._replace_with_real_event_page(backend)
        receipt = adapter.click(NamedButton("MAP_PREPARATION_CANCEL"))

        self.assertEqual(receipt.semantic_id, "campaign/map-preparation/cancel")
        self.assertEqual(len(backend.taps), 1)
        self.assertIsNone(context.entry_receipt)
        self.assertIsNone(context.map_preparation_receipt)
        self.assertIsNone(context.cancel_receipt)
        self.assertIs(context.inherited_cancel_receipt, receipt)
        self.assertEqual(context.inherited_cancel_kind, "map")
        self.assertEqual(context.inherited_cancel_stage_code, "sp")
        changed = {
            key for key, value in vars(context).items() if passive_context[key] != value
        }
        self.assertEqual(
            changed - {"passive_transition_until"},
            {
                "inherited_cancel_receipt",
                "inherited_cancel_kind",
                "inherited_cancel_stage_code",
            },
        )
        self.assertEqual(adapter._action_ledger._remaining, ledger_before)
        self.assertTrue(adapter.appear(NamedButton("EVENT_CHECK")))
        adapter.end_campaign_pre_sortie()

    def test_live_inherited_map_detail_retained_view_is_one_shot(self):
        backend = make_live_eventsp_map_preparation_backend()
        adapter = AlasSemanticAdapter(make_real_oracle(backend), lambda: None)
        adapter.begin_campaign_pre_sortie("sp")
        ledger_before = dict(adapter._action_ledger._remaining)

        self.assertFalse(adapter.appear(NamedButton("EVENT_CHECK")))
        self.assertTrue(adapter.appear(NamedButton("MAP_PREPARATION")))
        adapter.click(NamedButton("MAP_PREPARATION_CANCEL"))
        self.assertEqual(len(backend.taps), 1)

        self.assertFalse(adapter.appear(NamedButton("EVENT_CHECK")))
        with self.assertRaisesRegex(SemanticGateClosed, "single-use"):
            adapter.click(NamedButton("MAP_PREPARATION_CANCEL"))
        self.assertEqual(len(backend.taps), 1)
        self.assertEqual(adapter._action_ledger._remaining, ledger_before)
        adapter.end_campaign_pre_sortie()

    def test_live_inherited_map_detail_hostile_surface_is_observation_only(self):
        backend = make_live_eventsp_map_preparation_backend()
        target = next(
            image
            for image in backend.ui["images"]
            if image["path"]
            == "OverlayCamera/Overlay/UIMain/LevelInfoSPUI(Clone)/panel/line"
        )
        target["path"] += "/unreviewed"
        adapter = AlasSemanticAdapter(make_real_oracle(backend), lambda: None)
        adapter.begin_campaign_pre_sortie("sp")
        context = adapter._campaign_context
        context_before = dict(vars(context))
        ledger_before = dict(adapter._action_ledger._remaining)

        for operation in (
            lambda: adapter.appear(NamedButton("EVENT_CHECK")),
            lambda: adapter.appear(NamedButton("MAP_PREPARATION")),
            lambda: adapter.click(NamedButton("MAP_PREPARATION_CANCEL")),
        ):
            with self.assertRaises(SemanticGateClosed):
                operation()
            self.assertEqual(backend.taps, [])
            self.assertEqual(vars(context), context_before)
            self.assertEqual(adapter._action_ledger._remaining, ledger_before)
        adapter.end_campaign_pre_sortie()

    def test_live_inherited_map_detail_rejects_bidirectional_title_mismatch(self):
        overlay_title_path = (
            "OverlayCamera/Overlay/UIMain/LevelInfoSPUI(Clone)/"
            "panel/title_form/title"
        )
        underlay_title_path = (
            "UICamera/Canvas/UIMain/LevelMainScene(Clone)/"
            "LevelSelectSPFullUI(Clone)/Battle/Nodes/Chapter_2050041/"
            "main/info/bk/title_form/title"
        )
        cases = {}
        for case, path, value in (
            ("overlay-changed", overlay_title_path, "仅上层标题"),
            ("underlay-changed", underlay_title_path, "仅底层标题"),
        ):
            backend = make_live_eventsp_map_preparation_backend()
            next(item for item in backend.ui["texts"] if item["path"] == path)[
                "text"
            ] = value
            cases[case] = backend

        for case, backend in cases.items():
            with self.subTest(case=case):
                adapter = AlasSemanticAdapter(make_real_oracle(backend), lambda: None)
                adapter.begin_campaign_pre_sortie("sp")
                context = adapter._campaign_context
                context_before = dict(vars(context))
                ledger_before = dict(adapter._action_ledger._remaining)

                for operation in (
                    lambda: adapter.appear(NamedButton("EVENT_CHECK")),
                    lambda: adapter.appear(NamedButton("MAP_PREPARATION")),
                    lambda: adapter.click(NamedButton("MAP_PREPARATION_CANCEL")),
                ):
                    with self.assertRaisesRegex(
                        SemanticGateClosed, "title does not match underlay"
                    ):
                        operation()
                    self.assertEqual(backend.taps, [])
                    self.assertEqual(vars(context), context_before)
                    self.assertEqual(adapter._action_ledger._remaining, ledger_before)
                adapter.end_campaign_pre_sortie()

    def test_daemon_auto_search_sortie_proves_official_game_ownership(self):
        adapter, oracle, _ = self.make_adapter(
            campaign_stage_entry_budget=1,
            campaign_sortie_budget=1,
        )
        oracle.campaign_fleets["submarine"] = 0
        oracle.campaign_role_tab_selected = True
        oracle.campaign_roles = ["mob", "boss"]
        oracle.toggle_selected_values[
            "campaign/map-preparation/auto-search"
        ] = True
        oracle.campaign_state_value = SimpleNamespace(
            generation=12,
            chapter_name="chapter 12",
            stages=(
                SimpleNamespace(
                    stage_code="12-4",
                    button=SimpleNamespace(actionable=True),
                ),
            ),
        )
        entrance = NamedButton("12-4")
        entrance.semantic_campaign_stage_code = "12-4"

        adapter.begin_campaign_pre_sortie("12-4")
        adapter.click(entrance)
        self.assertTrue(adapter.arm_daemon_campaign_map_preparation())
        adapter.click(NamedButton("MAP_PREPARATION"))
        self.assertTrue(
            adapter.authorize_daemon_campaign_sortie(
                fleet1=1,
                fleet2=2,
                submarine=0,
                use_auto_search=True,
                use_2x_book=False,
                submarine_mode="do_not_use",
                fleet_order="fleet1_mob_fleet2_boss",
            )
        )
        adapter.click(NamedButton("FLEET_PREPARATION"))
        # Confirmation follows the final authorized fleet-panel setting, not
        # the value first observed on the preceding map-preparation overlay.
        adapter._campaign_context.daemon_auto_search_selected = False

        proof = adapter.confirm_daemon_campaign_sortie()

        self.assertIn("CombatUIStandard", proof.map_root_path)
        self.assertEqual(proof.prepared_fleets, (1, 2, 0))
        self.assertEqual(
            oracle.click_calls[-1], "campaign/fleet-preparation/sortie"
        )
        adapter.end_campaign_pre_sortie()

    def test_daemon_sortie_mismatch_and_zero_budget_are_observation_only(self):
        for sortie_budget, expected_error in ((0, None), (1, "differs")):
            with self.subTest(sortie_budget=sortie_budget):
                adapter, oracle, _ = self.make_adapter(
                    campaign_stage_entry_budget=1,
                    campaign_sortie_budget=sortie_budget,
                )
                oracle.campaign_fleets["submarine"] = 0
                oracle.toggle_selected_values[
                    "campaign/map-preparation/auto-search"
                ] = False
                oracle.campaign_state_value = SimpleNamespace(
                    generation=12,
                    chapter_name="chapter 12",
                    stages=(
                        SimpleNamespace(
                            stage_code="12-4",
                            button=SimpleNamespace(actionable=True),
                        ),
                    ),
                )
                entrance = NamedButton("12-4")
                entrance.semantic_campaign_stage_code = "12-4"
                adapter.begin_campaign_pre_sortie("12-4")
                adapter.click(entrance)
                self.assertFalse(adapter.arm_daemon_campaign_map_preparation())
                adapter.click(NamedButton("MAP_PREPARATION"))
                calls_before = list(oracle.click_calls)

                operation = lambda: adapter.authorize_daemon_campaign_sortie(
                    fleet1=1,
                    fleet2=0,
                    submarine=0,
                    use_auto_search=False,
                    use_2x_book=False,
                    submarine_mode="do_not_use",
                    fleet_order="fleet1_all_fleet2_standby",
                )
                if expected_error is None:
                    self.assertFalse(operation())
                else:
                    with self.assertRaisesRegex(SemanticGateClosed, expected_error):
                        operation()
                self.assertEqual(oracle.click_calls, calls_before)
                self.assertIsNone(adapter._campaign_context.initial_fleet_state)
                self.assertIsNone(adapter._campaign_context.prepared_fleet_state)
                self.assertIsNone(adapter._campaign_context.requested_fleets)
                adapter.end_campaign_pre_sortie()

    def test_daemon_preparation_hides_unrelated_probe_before_page_sampling(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.campaign_preparation_value = SimpleNamespace(kind="map")
        oracle.battle_pass_page_visible = Mock(
            side_effect=SemanticGateClosed(
                "Battle Pass page snapshots are not coherent"
            )
        )
        adapter.begin_campaign_pre_sortie("1-1")

        self.assertFalse(adapter.appear(NamedButton("GET_ITEMS_1")))
        oracle.battle_pass_page_visible.assert_not_called()

        with self.assertRaises(SemanticGateClosed):
            adapter.click(NamedButton("GET_ITEMS_1"))
        self.assertEqual(oracle.click_calls, [])
        adapter.end_campaign_pre_sortie()

    def test_hard_auto_search_rejects_unreviewed_main_stage(self):
        oracle = FakeOracle()
        oracle.campaign_hard_mode = True
        oracle.campaign_fleets["submarine"] = 0
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            campaign_stage_entry_budget=1,
            campaign_fleet_mutation_budget=1,
            campaign_sortie_budget=1,
        )
        entrance = NamedButton("11-1")
        entrance.semantic_campaign_stage_code = "11-1"
        adapter.begin_campaign_pre_sortie("11-1", mode="hard")
        adapter.click(entrance)
        adapter.click(NamedButton("MAP_PREPARATION"))
        adapter.authorize_campaign_fleet_preparation(1, 2, 0)
        adapter.confirm_campaign_fleet_selection()

        with self.assertRaisesRegex(SemanticGateClosed, "not qualified"):
            adapter.ensure_campaign_auto_search_roles(
                "fleet1_all_fleet2_standby"
            )
        adapter.end_campaign_pre_sortie()

    def test_unmapped_resource_fails_before_identity_or_input(self):
        adapter, oracle, gate_calls = self.make_adapter()

        with self.assertRaises(AlasSemanticUnmapped):
            adapter.click(NamedButton("BACK_ARROW"))

        self.assertEqual(gate_calls, [])
        self.assertEqual(oracle.click_calls, [])

    def test_month_boss_skip_ignores_stacked_neighbour_hud(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.operation_siren_radar_targets = Mock(return_value=((0, -1),))
        oracle.operation_siren_current_fleet = Mock(return_value=4)
        adapter.begin_operation_siren_boss_combat()
        adapter.mark_operation_siren_combat_fleet_defeated()

        oracle.operation_siren_current_fleet = Mock(return_value=4)
        self.assertTrue(adapter.operation_siren_current_fleet_defeated())
        self.assertFalse(adapter.operation_siren_fleet_already_defeated(2))
        self.assertFalse(adapter.operation_siren_fleet_already_defeated(3))
        self.assertFalse(adapter.operation_siren_fleet_already_defeated(1))

    def test_missing_stable_name_fails_closed(self):
        adapter, _, gate_calls = self.make_adapter()

        self.assertFalse(adapter.supports(object()))
        with self.assertRaises(AlasSemanticUnmapped):
            adapter.appear(object())
        self.assertEqual(gate_calls, [])

    def test_raw_coordinate_input_is_always_rejected(self):
        adapter, oracle, gate_calls = self.make_adapter()

        with self.assertRaises(SemanticGateClosed):
            adapter.reject_raw_input("swipe")

        self.assertEqual(gate_calls, [])
        self.assertEqual(oracle.click_calls, [])

    def test_semantic_ocr_reads_typed_unity_text_and_strips_markup(self):
        adapter, oracle, gate_calls = self.make_adapter()
        oracle.text_groups = (
            (
                SimpleNamespace(
                    text="<color=#fff>01:23:45</color>",
                    bounds=Bounds(100, 100, 200, 130),
                    truncated=False,
                ),
            ),
        )

        value = adapter.ocr_text([(90, 90, 210, 140)], alphabet="0123456789:")

        self.assertEqual(value, "01:23:45")
        self.assertEqual(oracle.last_text_bounds, (Bounds(90, 90, 210, 140),))
        self.assertEqual(len(gate_calls), 1)

    def test_semantic_ocr_rejects_missing_or_overlapping_text(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.text_groups = ((),)
        with self.assertRaises(SemanticGateClosed):
            adapter.ocr_text([(90, 90, 210, 140)])

        oracle.text_groups = (
            (
                SimpleNamespace(
                    text="123456", bounds=Bounds(100, 100, 180, 130), truncated=True
                ),
            ),
        )
        with self.assertRaises(SemanticGateClosed):
            adapter.ocr_text([(90, 90, 210, 140)])

        oracle.text_groups = (
            (
                SimpleNamespace(
                    text="12", bounds=Bounds(100, 100, 180, 130), truncated=False
                ),
                SimpleNamespace(
                    text="34", bounds=Bounds(110, 100, 190, 130), truncated=False
                ),
            ),
        )
        with self.assertRaises(SemanticGateClosed):
            adapter.ocr_text([(90, 90, 210, 140)])

    def test_alas_owned_state_machine_consumes_stable_semantic_inputs(self):
        oracle = FakeOracle()
        oracle.enabled_values = {
            "main/task": True,
            "task/page/back": True,
            "reward/award-info/close": False,
            "reward/award-info1/close": False,
        }
        oracle.exists_values["main/task"] = True
        oracle.mission_disposition = MissionDisposition.CLAIMABLE_ALL
        gate_calls = []
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: gate_calls.append(True),
            allow_mission_claim_once=True,
        )

        adapter.begin_mission_reward(daily=True, weekly=True)
        self.assertTrue(adapter.appear(NamedButton("MISSION_NOTICE")))
        adapter.click(NamedButton("MAIN_GOTO_MISSION"))
        self.assertTrue(
            adapter.image_color_count(
                NamedButton("REWARD_SIDE_NAVBAR_0_0"),
                color=(247, 255, 173),
                threshold=180,
                count=100,
            )
        )
        self.assertTrue(
            adapter.image_color_count(
                NamedButton("REWARD_SIDE_NAVBAR_0_1"),
                color=(140, 162, 181),
                threshold=180,
                count=50,
            )
        )
        self.assertFalse(adapter.appear(NamedButton("MISSION_MULTI")))
        self.assertTrue(adapter.appear(NamedButton("MISSION_MULTI")))

        receipt = adapter.click(NamedButton("MISSION_MULTI"))

        self.assertEqual(receipt.semantic_id, "task/claim/all")
        self.assertEqual(
            oracle.click_calls,
            ["main/task", "task/claim/all"],
        )
        with self.assertRaises(SemanticGateClosed):
            adapter.click(NamedButton("MISSION_MULTI"))
        self.assertEqual(oracle.click_calls.count("task/claim/all"), 1)
        adapter.end_mission_reward()
        with self.assertRaises(SemanticGateClosed):
            adapter.appear(NamedButton("MISSION_NOTICE"))
        self.assertGreaterEqual(len(gate_calls), 1)

    def test_alas_owned_claim_requires_separate_opt_in(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.mission_disposition = MissionDisposition.CLAIMABLE_ALL
        adapter.begin_mission_reward(daily=True, weekly=False)
        self.assertFalse(adapter.mission_claim_allowed())
        self.assertFalse(adapter.appear(NamedButton("MISSION_MULTI")))
        self.assertTrue(adapter.appear(NamedButton("MISSION_MULTI")))

        with self.assertRaises(SemanticGateClosed):
            adapter.click(NamedButton("MISSION_MULTI"))

        self.assertNotIn("task/claim/all", oracle.click_calls)

        opted_in = AlasSemanticAdapter(
            oracle,
            lambda: None,
            allow_mission_claim_once=True,
        )
        opted_in.begin_mission_reward(daily=True, weekly=False)
        self.assertTrue(opted_in.mission_claim_allowed())

    def test_weekly_only_and_numeric_row_paths_remain_closed(self):
        adapter, oracle, _ = self.make_adapter()
        adapter.begin_mission_reward(daily=False, weekly=True)

        self.assertFalse(adapter.appear(NamedButton("MISSION_NOTICE")))
        self.assertFalse(
            adapter.image_color_count(
                NamedButton("MISSION_WEEKLY_RED_DOT"),
                color=(206, 81, 66),
                threshold=221,
                count=20,
            )
        )
        oracle.mission_disposition = MissionDisposition.CLAIMABLE_ROW
        self.assertFalse(adapter.match_template_color(NamedButton("MISSION_SINGLE")))
        self.assertTrue(adapter.match_template_color(NamedButton("MISSION_SINGLE")))
        with self.assertRaises(SemanticGateClosed):
            adapter.click(NamedButton("MISSION_SINGLE"))
        self.assertEqual(oracle.click_calls, [])

    def test_weekly_progress_claim_uses_one_typed_input_and_acknowledgement(self):
        adapter, oracle, _ = self.make_adapter(allow_mission_claim_once=True)
        oracle.weekly_mission_progress_claim_available_value = True
        oracle.wait_any_results = [
            (
                "reward/award-info/close",
                SimpleNamespace(path="root/AwardInfoUI(Clone)/items/close"),
            ),
            SemanticGateClosed("semantic wait timed out"),
        ]
        adapter.begin_mission_reward(daily=False, weekly=True)

        receipt = adapter.claim_weekly_mission_progress_once()

        self.assertEqual(receipt.semantic_id, "task/weekly-progress/claim")
        self.assertEqual(
            oracle.click_calls,
            ["task/weekly-progress/claim", "reward/award-info/close"],
        )
        self.assertFalse(adapter.mission_claim_allowed())

    def test_render_transition_staleness_has_bounded_presence_grace(self):
        for message in (
            "observer snapshot is stale",
            "observer endpoints are not generation-coherent",
            "Msgbox snapshots are not coherent",
        ):
            with self.subTest(message=message):
                adapter, oracle, _ = self.make_adapter()

                def stale(_semantic_id):
                    raise SemanticGateClosed(message)

                oracle.enabled = stale
                self.assertFalse(adapter.appear(NamedButton("REWARD_CHECK")))
                adapter._observer_stale_since = time.monotonic() - 6.0
                with self.assertRaisesRegex(SemanticGateClosed, message):
                    adapter.appear(NamedButton("REWARD_CHECK"))

    def test_bounded_task_flows_allow_passive_scan_on_proven_surface(self):
        cases = (
            ("begin_research", "reward/page/back"),
            ("begin_dorm", "dorm/page/back"),
            ("begin_build", "build/page/start"),
        )
        for begin_name, semantic_id in cases:
            with self.subTest(flow=begin_name):
                adapter, oracle, _ = self.make_adapter()
                getattr(adapter, begin_name)()
                oracle.exists_values[semantic_id] = True

                self.assertFalse(adapter.appear(NamedButton("FLEET_CHECK")))

    def test_war_archives_page_check_claim_state_and_key_ocr_are_typed(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.war_archives_visible_value = True

        self.assertFalse(adapter.appear(NamedButton("FLEET_CHECK")))
        self.assertTrue(adapter.appear(NamedButton("WAR_ARCHIVES_CHECK")))
        self.assertFalse(adapter.appear(NamedButton("DATA_KEY_COLLECTED")))
        self.assertTrue(adapter.appear(NamedButton("DATA_KEY_COLLECT")))

        self.assertEqual(
            adapter.ocr_text([(133, 39, 250, 72)], alphabet="0123456789/IDSB"),
            "300/300",
        )
        receipt = adapter.click(NamedButton("DATA_KEY_COLLECT"))
        self.assertEqual(receipt.semantic_id, "archive/key/collect")
        with self.assertRaisesRegex(SemanticGateClosed, "already collected"):
            adapter.click(NamedButton("DATA_KEY_COLLECT"))

    def test_bounded_task_flows_begin_with_page_discovery_grace(self):
        for begin_name in (
            "begin_commission",
            "begin_tactical",
            "begin_research",
            "begin_dorm",
            "begin_build",
        ):
            with self.subTest(flow=begin_name):
                adapter, _, _ = self.make_adapter()
                getattr(adapter, begin_name)()
                self.assertFalse(adapter.appear(NamedButton("FLEET_CHECK")))

    def test_cross_flow_virtual_probe_is_false_but_input_stays_forbidden(self):
        adapter, oracle, _ = self.make_adapter()
        adapter.begin_research()
        oracle.exists_values["reward/page/back"] = True

        self.assertFalse(adapter.appear(NamedButton("DOCK_CHECK")))
        with self.assertRaises(AlasSemanticUnmapped):
            adapter.click(NamedButton("DOCK_CHECK"))

    def test_alas_owned_row_claim_uses_one_exact_typed_row(self):
        adapter, oracle, _ = self.make_adapter(allow_mission_claim_once=True)
        oracle.mission_disposition = MissionDisposition.CLAIMABLE_ROW
        adapter.begin_mission_reward(daily=True, weekly=False)

        self.assertFalse(adapter.appear(NamedButton("MISSION_SINGLE")))
        self.assertTrue(adapter.appear(NamedButton("MISSION_SINGLE")))
        receipt = adapter.click(NamedButton("MISSION_SINGLE"))

        self.assertEqual(receipt.semantic_id, "task/claim/row/0")
        self.assertEqual(oracle.click_calls, ["task/claim/row/0"])
        self.assertFalse(adapter.mission_claim_allowed())
