"""Session regression cases for the adapter."""

import unittest
from contextlib import nullcontext
from alas_headless import (
    AlasCombatObserverManifest,
    AlasSemanticSession,
    AlasSemanticUnmapped,
    SemanticGateClosed,
)
from tests.semantic_support.adapter_cases import AlasSemanticAdapterTestsSupport
from tests.semantic_support.adapter_fixtures import NamedButton
from unittest.mock import Mock, patch


class AlasSemanticAdapterTests(AlasSemanticAdapterTestsSupport, unittest.TestCase):
    def test_session_safe_area_alias_requires_meta_owner_and_exact_award(self):
        adapter = Mock()
        adapter._meta_beacon_active = True
        adapter._meta_assist_active = False
        adapter._meta_reward_close_receipt = None
        adapter._exercise_execution_active = False
        frame = adapter._require_frame_observation_oracle.return_value
        frame.exercise_reward_item_info_visible.return_value = False
        frame.daily_battle_result_visible.return_value = False
        frame.operation_siren_battle_result_visible.return_value = False
        frame.enabled.return_value = False
        adapter.campaign_combat_committed.return_value = False
        adapter.operation_siren_combat_committed.return_value = False
        adapter.oracle.award_info_page_visible.return_value = True
        adapter.prepared_input_frame.side_effect = lambda provider: nullcontext()
        session = AlasSemanticSession.__new__(AlasSemanticSession)
        session.adapter = adapter
        session._opsi_sample_use = None
        session._combat_result_action_oracle = lambda _adapter: frame
        session._combat_result_observation = None
        session.open = lambda: adapter
        session.refresh_frame = Mock()
        session.click(NamedButton('CLICK_SAFE_AREA'))
        self.assertEqual(adapter.click.call_count, 1, adapter.mock_calls)
        adapter.oracle.award_info_page_visible.return_value = False
        with self.assertRaises(AlasSemanticUnmapped):
            session.click(NamedButton('CLICK_SAFE_AREA'))
        adapter.oracle.award_info_page_visible.return_value = True
        adapter._meta_beacon_active = False
        with self.assertRaises(AlasSemanticUnmapped):
            session.click(NamedButton('CLICK_SAFE_AREA'))
        self.assertEqual(adapter.click.call_count, 1)

    def test_lazy_session_rejects_unmapped_before_opening_adb(self):
        session = AlasSemanticSession(
            "emulator-test", "be80ce591a481c12d60c50d6040d40c035b40a2b"
        )

        with self.assertRaises(AlasSemanticUnmapped):
            session.click(NamedButton("UNREVIEWED_CLICK"))

        self.assertIsNone(session.runtime_handle)

    def test_session_routes_data_key_collect_to_reviewed_adapter_action(self):
        adapter = Mock()
        receipt = Mock()
        adapter.campaign_combat_committed.return_value = False
        adapter.operation_siren_combat_committed.return_value = False
        adapter.click.return_value = receipt
        adapter.prepared_input_frame.side_effect = lambda provider: nullcontext()
        session = AlasSemanticSession.__new__(AlasSemanticSession)
        session.adapter = adapter
        session.open = lambda: adapter
        session.refresh_frame = Mock()

        self.assertIs(session.click(NamedButton("DATA_KEY_COLLECT")), receipt)
        self.assertIs(
            session.click(NamedButton("POPUP_CONFIRM_DATA_KEY_LIMIT")), receipt
        )
        self.assertEqual(session.refresh_frame.call_count, 2)
        self.assertEqual(adapter.click.call_count, 2)

    def test_live_combat_manifest_rebinds_only_reviewed_capacity_successor(self):
        base_revision = "be80ce591a481c12d60c50d6040d40c035b40a2b"
        live_revision = "506b76f698b5089aaa29c4e7908b48edb8532a44"
        manifest = AlasCombatObserverManifest(
            package="com.bilibili.azurlane",
            driver_revision=base_revision,
            game_fingerprint="reviewed-game",
            resources=(),
        )
        session = AlasSemanticSession("emulator-test", live_revision)

        with patch(
            "alas_headless.adapter.semantic.session_combat.load_alas_combat_observer_manifest",
            return_value=manifest,
        ):
            rebound = session._live_combat_manifest()

        self.assertEqual(rebound.driver_revision, live_revision)
        self.assertEqual(manifest.driver_revision, base_revision)
        self.assertIs(session._live_combat_manifest(), rebound)

    def test_live_combat_manifest_rejects_unknown_driver_transition(self):
        manifest = AlasCombatObserverManifest(
            package="com.bilibili.azurlane",
            driver_revision="be80ce591a481c12d60c50d6040d40c035b40a2b",
            game_fingerprint="reviewed-game",
            resources=(),
        )
        session = AlasSemanticSession("emulator-test", "a" * 40)

        with patch(
            "alas_headless.adapter.semantic.session_combat.load_alas_combat_observer_manifest",
            return_value=manifest,
        ):
            with self.assertRaisesRegex(
                SemanticGateClosed,
                "not qualified",
            ):
                session._live_combat_manifest()

    def test_environment_factory_requires_explicit_opt_in(self):
        environment = {
            "ALAS_SEMANTIC_DRIVER_REVISION": (
                "be80ce591a481c12d60c50d6040d40c035b40a2b"
            )
        }
        with patch.dict("os.environ", environment, clear=True):
            with self.assertRaises(SemanticGateClosed):
                AlasSemanticSession.from_environment("emulator-test")

    def test_environment_factory_captures_one_claim_budget_opt_in(self):
        environment = {
            "ALAS_SEMANTIC_MODE": "1",
            "ALAS_SEMANTIC_DRIVER_REVISION": (
                "be80ce591a481c12d60c50d6040d40c035b40a2b"
            ),
            "ALAS_SEMANTIC_ALLOW_MISSION_CLAIM_ONCE": "1",
        }
        with patch.dict("os.environ", environment, clear=True):
            session = AlasSemanticSession.from_environment("emulator-test")

        self.assertTrue(session.allow_mission_claim_once)

    def test_environment_factory_bounds_explicit_adb_timeout(self):
        environment = {
            "ALAS_SEMANTIC_MODE": "1",
            "ALAS_SEMANTIC_DRIVER_REVISION": (
                "be80ce591a481c12d60c50d6040d40c035b40a2b"
            ),
            "ALAS_SEMANTIC_ADB_COMMAND_TIMEOUT_SECONDS": "30",
        }
        with patch.dict("os.environ", environment, clear=True):
            session = AlasSemanticSession.from_environment("emulator-test")
        self.assertEqual(
            session._runtime_handle_factory.command_timeout_seconds,
            30.0,
        )

        for malformed in ("030", "0", "121"):
            environment["ALAS_SEMANTIC_ADB_COMMAND_TIMEOUT_SECONDS"] = malformed
            with self.subTest(value=malformed):
                with patch.dict("os.environ", environment, clear=True):
                    with self.assertRaises((SemanticGateClosed, ValueError)):
                        AlasSemanticSession.from_environment("emulator-test")

    def test_session_bounds_observer_freshness_and_process_lease_types(self):
        revision = "be80ce591a481c12d60c50d6040d40c035b40a2b"
        session = AlasSemanticSession(
            "emulator-test",
            revision,
            observer_max_age_ms=300000,
        )
        self.assertEqual(session.observer_max_age_ms, 300000)

        for malformed in (True, 0, 300001):
            with self.subTest(value=malformed):
                with self.assertRaisesRegex(ValueError, "observer max age"):
                    AlasSemanticSession(
                        "emulator-test",
                        revision,
                        observer_max_age_ms=malformed,
                    )
        with self.assertRaisesRegex(ValueError, "package lease"):
            AlasSemanticSession(
                "emulator-test",
                revision,
                package_process_lease=object(),
            )

    def test_environment_factory_rejects_removed_boolean_reward_opt_in(self):
        environment = {
            "ALAS_SEMANTIC_MODE": "1",
            "ALAS_SEMANTIC_DRIVER_REVISION": (
                "be80ce591a481c12d60c50d6040d40c035b40a2b"
            ),
            "ALAS_SEMANTIC_ALLOW_COMMISSION_REWARDS": "1",
        }
        with patch.dict("os.environ", environment, clear=True):
            with self.assertRaises(SemanticGateClosed):
                AlasSemanticSession.from_environment("emulator-test")

    def test_environment_factory_parses_new_bounded_mutation_budgets(self):
        environment = {
            "ALAS_SEMANTIC_MODE": "1",
            "ALAS_SEMANTIC_DRIVER_REVISION": (
                "be80ce591a481c12d60c50d6040d40c035b40a2b"
            ),
            "ALAS_SEMANTIC_TACTICAL_ASSIGN_BUDGET": "1",
            "ALAS_SEMANTIC_RESEARCH_REWARD_BUDGET": "2",
            "ALAS_SEMANTIC_RESEARCH_START_BUDGET": "3",
            "ALAS_SEMANTIC_DORM_COLLECT_BUDGET": "4",
            "ALAS_SEMANTIC_DORM_FEED_BUDGET": "5",
            "ALAS_SEMANTIC_BUILD_SUBMIT_BUDGET": "6",
            "ALAS_SEMANTIC_CAMPAIGN_STAGE_ENTRY_BUDGET": "7",
            "ALAS_SEMANTIC_CAMPAIGN_FLEET_MUTATION_BUDGET": "8",
            "ALAS_SEMANTIC_CAMPAIGN_SORTIE_BUDGET": "9",
            "ALAS_SEMANTIC_CAMPAIGN_COMBAT_BUDGET": "10",
            "ALAS_SEMANTIC_CAMPAIGN_VIEWPORT_SWIPE_BUDGET": "11",
        }
        with patch.dict("os.environ", environment, clear=True):
            session = AlasSemanticSession.from_environment("emulator-test")

        self.assertEqual(session.tactical_assign_budget, 1)
        self.assertEqual(session.research_reward_budget, 2)
        self.assertEqual(session.research_start_budget, 3)
        self.assertEqual(session.dorm_collect_budget, 4)
        self.assertEqual(session.dorm_feed_budget, 5)
        self.assertEqual(session.build_submit_budget, 6)
        self.assertEqual(session.campaign_stage_entry_budget, 7)
        self.assertEqual(session.campaign_fleet_mutation_budget, 8)
        self.assertEqual(session.campaign_sortie_budget, 9)
        self.assertEqual(session.campaign_combat_budget, 10)
        self.assertEqual(session.campaign_viewport_swipe_budget, 11)
        self.assertEqual(session.campaign_camera_positioning_budget, 0)

        environment["ALAS_SEMANTIC_DORM_FEED_BUDGET"] = "05"
        with patch.dict("os.environ", environment, clear=True):
            with self.assertRaises(SemanticGateClosed):
                AlasSemanticSession.from_environment("emulator-test")
