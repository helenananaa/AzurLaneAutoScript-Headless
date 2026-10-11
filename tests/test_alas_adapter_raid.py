"""Raid regression cases for the adapter."""

import time
import unittest
from alas_headless import AlasSemanticAdapter, AlasSemanticSession, SemanticGateClosed
from alas_headless.adapter import StaleFrameError
from alas_headless.adapter.semantic.contracts import AlasSemanticActionDeferred
from tests.semantic_support.adapter_cases import AlasSemanticAdapterTestsSupport
from tests.semantic_support.adapter_fixtures import FakeOracle, NamedButton
from unittest.mock import Mock, patch


class AlasSemanticAdapterTests(AlasSemanticAdapterTestsSupport, unittest.TestCase):
    def test_main_raid_aliases_preserve_the_original_alas_page_edge(self):
        adapter, oracle, gate_calls = self.make_adapter()

        self.assertTrue(adapter.appear(NamedButton("MAIN_GOTO_RAID_WHITE")))
        receipt = adapter.click(NamedButton("MAIN_GOTO_RAID"))

        self.assertIn("main/raid", oracle.enabled_calls)
        self.assertEqual(oracle.click_calls, ["main/raid"])
        self.assertEqual(receipt.semantic_id, "main/raid")
        self.assertEqual(len(gate_calls), 2)

    def test_current_raid_fleet_start_is_navigation_not_sortie_commit(self):
        adapter, oracle, gate_calls = self.make_adapter(campaign_sortie_budget=0)

        receipt = adapter.click_raid_fleet_start("raid_20260827")

        self.assertEqual(receipt.semantic_id, "raid/fleet/start")
        self.assertIsNone(receipt.capability_id)
        self.assertEqual(oracle.click_calls, ["raid/fleet/start:raid_20260827"])
        self.assertEqual(gate_calls, [True])

    def test_current_raid_advanced_entry_is_navigation_not_ex_or_sortie(self):
        adapter, oracle, gate_calls = self.make_adapter(campaign_sortie_budget=0)

        receipt = adapter.click_raid_advanced_challenge("raid_20260827")

        self.assertEqual(receipt.semantic_id, "raid/advanced/entry")
        self.assertIsNone(receipt.capability_id)
        self.assertEqual(
            oracle.click_calls, ["raid/advanced/entry:raid_20260827"]
        )
        self.assertEqual(gate_calls, [True])
        self.assertEqual(adapter._action_ledger.remaining("campaign.sortie"), 0)

    def test_current_raid_multiple_sortie_navigation_uses_no_sortie_grant(self):
        adapter, oracle, gate_calls = self.make_adapter(campaign_sortie_budget=0)
        oracle.raid_precombat_multiple_visible_value = True
        oracle.raid_multiple_sortie_visible_value = True

        self.assertTrue(adapter.raid_precombat_multiple_visible("raid_20260827"))
        entry = adapter.click_raid_precombat_multiple("raid_20260827")
        self.assertTrue(adapter.raid_multiple_sortie_visible("raid_20260827"))
        state = adapter.raid_multiple_sortie_state("raid_20260827")
        back = adapter.click_raid_multiple_sortie_back("raid_20260827")

        self.assertEqual(entry.semantic_id, "raid/precombat/multiple")
        self.assertEqual(back.semantic_id, "raid/multiple-sortie/back")
        self.assertIsNone(entry.capability_id)
        self.assertIsNone(back.capability_id)
        self.assertEqual((state.ticket_selected, state.ticket_owned), (0, 0))
        self.assertEqual(
            oracle.click_calls,
            [
                "raid/precombat/multiple:raid_20260827",
                "raid/multiple-sortie/back:raid_20260827",
            ],
        )
        self.assertEqual(gate_calls, [True, True, True, True, True])
        self.assertEqual(adapter._action_ledger.remaining("campaign.sortie"), 0)

    def test_current_raid_precombat_start_reuses_bounded_sortie_grant(self):
        adapter, oracle, gate_calls = self.make_adapter(campaign_sortie_budget=1)

        receipt = adapter.click_raid_precombat_start("raid_20260827")

        self.assertEqual(receipt.semantic_id, "raid/precombat/start")
        self.assertEqual(receipt.capability_id, "campaign.sortie")
        self.assertEqual(
            oracle.click_calls, ["raid/precombat/start:raid_20260827"]
        )
        self.assertEqual(adapter._current_raid_result_event, "raid_20260827")
        self.assertEqual(gate_calls, [True])
        with self.assertRaises(AlasSemanticActionDeferred):
            adapter.click_raid_precombat_start("raid_20260827")
        self.assertEqual(
            oracle.click_calls, ["raid/precombat/start:raid_20260827"]
        )

    def test_current_raid_result_is_owned_by_session_battle_status_probe(self):
        adapter, oracle, _ = self.make_adapter(campaign_sortie_budget=1)
        adapter.click_raid_precombat_start("raid_20260827")
        oracle.daily_battle_result_visible = Mock(return_value=True)

        session = AlasSemanticSession.__new__(AlasSemanticSession)
        session.adapter = adapter
        session.open = lambda: adapter
        session._combat_result_transition_until = 0.0
        session._combat_result_observation = None

        self.assertTrue(session.current_raid_result_active())
        self.assertTrue(session.appear(NamedButton("BATTLE_STATUS_S")))
        self.assertFalse(session.appear(NamedButton("BATTLE_STATUS_D")))
        self.assertIsNotNone(session._combat_result_observation)

    def test_current_raid_page_makes_legacy_rewards_probe_a_passive_miss(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.raid_page_visible_value = True
        session = AlasSemanticSession.__new__(AlasSemanticSession)
        session.adapter = adapter
        session.open = lambda: adapter
        session.refresh_frame = lambda: None

        self.assertFalse(session.appear(NamedButton("RAID_REWARDS")))

    def test_current_raid_recommend_reuses_bounded_fleet_mutation_grant(self):
        adapter, oracle, gate_calls = self.make_adapter(
            campaign_fleet_mutation_budget=1
        )

        receipt = adapter.click_raid_fleet_recommend("raid_20260827")

        self.assertEqual(receipt.semantic_id, "raid/fleet/recommend")
        self.assertEqual(receipt.capability_id, "campaign.fleet_mutation")
        self.assertEqual(
            oracle.click_calls, ["raid/fleet/recommend:raid_20260827"]
        )
        self.assertEqual(gate_calls, [True])
        with self.assertRaises(AlasSemanticActionDeferred):
            adapter.click_raid_fleet_recommend("raid_20260827")
        self.assertEqual(
            oracle.click_calls, ["raid/fleet/recommend:raid_20260827"]
        )

    def test_current_raid_entry_waits_through_card_animation_without_reclick(self):
        adapter, oracle, gate_calls = self.make_adapter()
        oracle.main_page_visible_value = True
        oracle.raid_page_visible_value = True
        oracle.raid_page_visible_errors = [
            SemanticGateClosed("current Raid stage sprite does not cover its button")
        ]

        with patch("alas_headless.alas_adapter.time.sleep") as sleep:
            receipt = adapter.enter_raid_page("raid_20260827")

        self.assertEqual(receipt.semantic_id, "main/raid")
        self.assertEqual(oracle.click_calls, ["main/raid"])
        self.assertEqual(gate_calls, [True])
        sleep.assert_called_once_with(0.25)

    def test_current_raid_stage_waits_for_unobscured_card_without_reclick(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.raid_stage_errors = [
            SemanticGateClosed("Raid stage input is blocked")
        ]

        with patch("alas_headless.alas_adapter.time.sleep") as sleep:
            receipt = adapter.click_raid_stage("raid_20260827", "ex")

        self.assertEqual(receipt.semantic_id, "raid/stage/ex")
        self.assertEqual(oracle.click_calls, ["raid/stage/ex"])
        sleep.assert_called_once_with(0.25)

    def test_current_raid_home_reproves_input_on_fresh_frame(self):
        refresh = Mock()
        adapter, oracle, _ = self.make_adapter(input_frame_refresher=refresh)

        receipt = adapter.click_raid_home("raid_20260827")

        self.assertEqual(receipt.semantic_id, "raid/page/home")
        refresh.assert_called_once_with()
        self.assertEqual(
            oracle.click_calls, ["raid/page/home:raid_20260827"]
        )

    def test_current_raid_page_makes_unrelated_page_probe_absent(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.raid_page_visible_value = True

        self.assertFalse(adapter.appear(NamedButton("FLEET_CHECK")))
        self.assertFalse(adapter.appear(NamedButton("EXERCISE_CHECK")))
        self.assertFalse(adapter.appear(NamedButton("EVENT_LIST_CHECK")))
        self.assertTrue(adapter.appear(NamedButton("RAID_CHECK")))

    def test_current_raid_page_scan_uses_immutable_screenshot_frame(self):
        live_oracle = FakeOracle()
        frame_oracle = FakeOracle()
        live_oracle.raid_page_visible_errors = [
            SemanticGateClosed("current Raid button and UI snapshots are incoherent")
        ]
        frame_oracle.raid_page_visible_value = True
        adapter = AlasSemanticAdapter(
            live_oracle,
            lambda: None,
            frame_observation_oracle=lambda: frame_oracle,
            frame_identity_provider=self.frame_identity,
        )

        self.assertFalse(adapter.appear(NamedButton("EXERCISE_CHECK")))
        self.assertTrue(adapter.appear(NamedButton("RAID_CHECK")))
        self.assertEqual(len(live_oracle.raid_page_visible_errors), 1)
        self.assertEqual(live_oracle.click_calls, [])
        self.assertEqual(frame_oracle.click_calls, [])

    def test_current_raid_page_scan_falls_back_read_only_without_frame(self):
        live_oracle = FakeOracle()
        live_oracle.raid_page_visible_value = True
        adapter = AlasSemanticAdapter(
            live_oracle,
            lambda: None,
            frame_observation_oracle=lambda: (_ for _ in ()).throw(
                StaleFrameError()
            ),
            frame_identity_provider=self.frame_identity,
        )

        self.assertTrue(adapter.appear(NamedButton("RAID_CHECK")))
        self.assertEqual(live_oracle.click_calls, [])

    def test_current_raid_direct_visibility_uses_immutable_screenshot_frame(self):
        live_oracle = FakeOracle()
        frame_oracle = FakeOracle()
        live_oracle.raid_page_visible_errors = [
            SemanticGateClosed("current Raid button and UI snapshots are incoherent")
        ]
        frame_oracle.raid_page_visible_value = True
        adapter = AlasSemanticAdapter(
            live_oracle,
            lambda: None,
            frame_observation_oracle=lambda: frame_oracle,
            frame_identity_provider=self.frame_identity,
        )

        self.assertTrue(adapter.raid_page_visible("raid_20260827"))
        self.assertEqual(len(live_oracle.raid_page_visible_errors), 1)
        self.assertEqual(live_oracle.click_calls, [])
        self.assertEqual(frame_oracle.click_calls, [])

    def test_current_raid_recovery_probe_uses_immutable_screenshot_frame(self):
        live_oracle = FakeOracle()
        frame_oracle = FakeOracle()
        live_oracle.raid_fleet_selection_visible = Mock(
            side_effect=SemanticGateClosed(
                "Raid fleet-selection snapshots are incoherent"
            )
        )
        frame_oracle.raid_fleet_selection_visible = Mock(return_value=False)
        adapter = AlasSemanticAdapter(
            live_oracle,
            lambda: None,
            frame_observation_oracle=lambda: frame_oracle,
            frame_identity_provider=self.frame_identity,
        )

        self.assertFalse(adapter.raid_fleet_selection_visible("raid_20260827"))
        frame_oracle.raid_fleet_selection_visible.assert_called_once_with(
            event="raid_20260827"
        )
        live_oracle.raid_fleet_selection_visible.assert_not_called()

    def test_current_raid_page_scan_tolerates_only_bounded_endpoint_skew(self):
        adapter, oracle, _ = self.make_adapter()
        message = "current Raid button and UI snapshots are incoherent"
        oracle.raid_page_visible_errors = [
            SemanticGateClosed(message),
            SemanticGateClosed(message),
            SemanticGateClosed(message),
        ]

        # Earlier page probes and RAID_CHECK are passive observations.  A
        # short independent-endpoint skew is absence for this frame only and
        # never authorizes an input.
        self.assertFalse(adapter.appear(NamedButton("EXERCISE_CHECK")))
        self.assertFalse(adapter.appear(NamedButton("RAID_CHECK")))
        self.assertEqual(oracle.click_calls, [])

        # The grace is bounded: an unchanged incoherent surface remains
        # fail-closed instead of being promoted to the Raid page.
        adapter._observer_stale_since = time.monotonic() - 6.0
        with self.assertRaisesRegex(SemanticGateClosed, message):
            adapter.appear(NamedButton("RAID_CHECK"))

    def test_current_raid_page_scan_keeps_structural_errors_fail_closed(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.raid_page_visible_errors = [
            SemanticGateClosed("current Raid stage sprite does not cover its button")
        ]

        self.assertFalse(adapter.appear(NamedButton("EXERCISE_CHECK")))
        self.assertEqual(len(oracle.raid_page_visible_errors), 1)
        with self.assertRaisesRegex(SemanticGateClosed, "does not cover"):
            adapter.appear(NamedButton("RAID_CHECK"))
        self.assertEqual(oracle.click_calls, [])

    def test_current_raid_story_hides_unmapped_page_probes_for_alas_handler(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.event_story_dialogue_visible_value = True

        self.assertFalse(adapter.appear(NamedButton("FLEET_CHECK")))
        self.assertFalse(adapter.appear(NamedButton("EXERCISE_CHECK")))
        self.assertFalse(adapter.appear(NamedButton("EVENT_LIST_CHECK")))

    def test_current_raid_generic_back_uses_exact_home_target(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.raid_page_visible_value = True

        receipt = adapter.click(NamedButton("BACK_ARROW"))

        self.assertEqual(receipt.semantic_id, "raid/page/home")
        self.assertEqual(oracle.click_calls, ["raid/page/home:raid_20260827"])

    def test_goto_main_uses_exact_raid_owner_before_unrelated_shell_probes(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.raid_page_visible_value = True
        oracle.recommendation_shop_visible = Mock(
            side_effect=AssertionError("unrelated shop shell must not be probed")
        )

        receipt = adapter.click(NamedButton("GOTO_MAIN"))

        self.assertEqual(receipt.semantic_id, "raid/page/home")
        self.assertEqual(oracle.click_calls, ["raid/page/home:raid_20260827"])
        oracle.recommendation_shop_visible.assert_not_called()

    def test_orphan_current_raid_result_accepts_exact_raid_page_return(self):
        adapter, oracle, _ = self.make_adapter()
        session = AlasSemanticSession.__new__(AlasSemanticSession)
        session.adapter = adapter
        session.open = lambda: adapter
        session.refresh_frame = lambda: None
        session.orphan_combat_result_visible = lambda: True
        session._combat_result_transition_until = 0.0
        adapter._require_frame_observation_oracle = lambda: oracle
        oracle.daily_battle_result_visible = Mock(return_value=False)
        oracle.campaign_battle_reward_visible = Mock(return_value=False)
        oracle.event_campaign_page_visible_value = False
        oracle.operation_siren_page_visible = Mock(return_value=False)
        oracle.daily_page_visible = Mock(return_value=False)
        oracle.main_page_visible = Mock(return_value=False)
        oracle.raid_page_visible = Mock(return_value=True)

        self.assertEqual(
            session.recover_orphan_combat_result(
                current_raid_event="raid_20260827"
            ),
            (),
        )
        oracle.raid_page_visible.assert_called_once_with("raid_20260827")
