import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OPSI_PATCH = (
    ROOT / "integration" / "alas" / "series" /
    "0090-operation-siren-flow-ports.patch"
)
DAEMON_PATCH = (
    ROOT / "integration" / "alas" / "series" / "0100-tool-flow-ports.patch"
)
STRONGHOLD_RUNTIME_PATCH = (
    ROOT / "integration" / "alas" / "series" /
    "0098-operation-siren-stronghold-runtime.patch"
)
TRANSITION_RECOVERY_PATCH = (
    ROOT / "integration" / "alas" / "series" /
    "0105-operation-siren-auto-search-transition-recovery.patch"
)
EXPLORE_GLOBE_RECOVERY_PATCH = (
    ROOT / "integration" / "alas" / "series" /
    "0106-operation-siren-explore-globe-recovery.patch"
)
EXPLORE_INVENTORY_RECOVERY_PATCH = (
    ROOT / "integration" / "alas" / "series" /
    "0107-operation-siren-explore-inventory-and-anchor-recover.patch"
)
OBSCURE_SPECIAL_ZONE_RESCAN_PATCH = (
    ROOT / "integration" / "alas" / "series" /
    "0108-operation-siren-obscure-special-zone-rescan.patch"
)
COORDINATE_CHECKOUT_RECOVERY_PATCH = (
    ROOT / "integration" / "alas" / "series" /
    "0109-operation-siren-coordinate-checkout-recovery.patch"
)
SPECIAL_ZONE_EXIT_TRANSITION_PATCH = (
    ROOT / "integration" / "alas" / "series" /
    "0110-operation-siren-special-zone-exit-transition.patch"
)
GUIDEPOST_DIRECT_TARGET_PATCH = (
    ROOT / "integration" / "alas" / "series" /
    "0111-operation-siren-guidepost-direct-target.patch"
)
EXACT_MAP_EXIT_CONFIRM_PATCH = (
    ROOT / "integration" / "alas" / "series" /
    "0112-operation-siren-exact-map-exit-confirm.patch"
)
COORDINATE_PIN_TRANSITION_PATCH = (
    ROOT / "integration" / "alas" / "series" /
    "0113-operation-siren-coordinate-pin-transition.patch"
)
GUIDEPOST_RETRY_PATCH = (
    ROOT / "integration" / "alas" / "series" /
    "0114-operation-siren-guidepost-retry.patch"
)
GUIDEPOST_DELAYED_STORY_PATCH = (
    ROOT / "integration" / "alas" / "series" /
    "0116-operation-siren-guidepost-delayed-story.patch"
)
PAGE_REMOUNT_PATCH = (
    ROOT / "integration" / "alas" / "series" /
    "0118-operation-siren-page-remount.patch"
)
COORDINATE_CONFIRM_PROOF_PATCH = (
    ROOT / "integration" / "alas" / "series" /
    "0119-operation-siren-coordinate-confirm-proof.patch"
)
PAGE_REMOUNT_OWNER_PATCH = (
    ROOT / "integration" / "alas" / "series" /
    "0120-operation-siren-page-remount-owner.patch"
)
COORDINATE_CARD_RETRY_PATCH = (
    ROOT / "integration" / "alas" / "series" /
    "0121-operation-siren-coordinate-card-retry.patch"
)
DIRECT_COORDINATE_PIN_PATCH = (
    ROOT / "integration" / "alas" / "series" /
    "0122-operation-siren-direct-coordinate-pin.patch"
)
SPECIAL_PIN_AP_RECOVERY_PATCH = (
    ROOT / "integration" / "alas" / "series" /
    "0123-operation-siren-special-pin-ap-recovery.patch"
)
FARMING_SEARCH_COMPLETION_PATCH = (
    ROOT / "integration" / "alas" / "series" /
    "0125-operation-siren-farming-search-completion.patch"
)
INIT_OFFSCREEN_FLEET_PATCH = (
    ROOT / "integration" / "alas" / "series" /
    "0126-operation-siren-init-offscreen-fleet.patch"
)
MONTH_BOSS_ROUTE_EVENTS_PATCH = (
    ROOT / "integration" / "alas" / "series" /
    "0132-operation-siren-month-boss-route-events.patch"
)
MONTH_BOSS_FLEET_RESTORE_PATCH = (
    ROOT / "integration" / "alas" / "series" /
    "0133-operation-siren-month-boss-fleet-restore.patch"
)
MONTH_BOSS_RESULT_PATCH = (
    ROOT / "integration" / "alas" / "series" /
    "0134-operation-siren-month-boss-result.patch"
)
OBSCURE_EXIT_PASSAGE_PATCH = (
    EXACT_MAP_EXIT_CONFIRM_PATCH
)


class AlasOpsiAutoSearchContractTests(unittest.TestCase):
    def test_init_defers_only_the_exact_offscreen_fleet_state(self):
        source = INIT_OFFSCREEN_FLEET_PATCH.read_text(encoding="utf-8")
        self.assertIn("defer_if_offscreen=True", source)
        self.assertIn("selected-fleet map anchor is absent or '", source)
        self.assertIn("if not (", source)
        self.assertIn("raise", source)
        self.assertIn("return False", source)

    def test_off_state_is_probed_once_instead_of_declared_locked(self):
        source = (
            OPSI_PATCH.read_text(encoding="utf-8")
            + STRONGHOLD_RUNTIME_PATCH.read_text(encoding="utf-8")
        )
        self.assertIn("operation_siren_auto_search_state()", source)
        self.assertIn("_semantic_auto_search_enable_attempted", source)
        self.assertIn("Allow ALAS one natural enable attempt", source)
        self.assertIn("semantic_off_settled", source)
        self.assertIn("Timer(\n+                            2, count=4", source)
        self.assertIn("accepted and returned to '", source)
        self.assertIn("'off; no searchable event remains'", source)
        self.assertNotIn("auto search remains off after", source)
        self.assertNotIn("semantic_auto_search_locked", source)
        self.assertNotIn("auto search is locked; cannot run", source)
        self.assertNotIn("skip the initial clear", source)

    def test_tasks_and_daemon_no_longer_treat_off_as_locked(self):
        opsi = OPSI_PATCH.read_text(encoding="utf-8")
        daemon = DAEMON_PATCH.read_text(encoding="utf-8")
        self.assertIn("if not daily_config.do_mission:", opsi)
        self.assertNotIn("auto_search_locked", opsi)
        self.assertNotIn("auto_search_locked", daemon)
        self.assertNotIn("oracle.exists('os/map/auto-search/off')", daemon)

    def test_post_combat_map_projection_waits_for_exact_toggle_mount(self):
        source = TRANSITION_RECOVERY_PATCH.read_text(encoding="utf-8")
        self.assertIn("except SemanticGateClosed:", source)
        self.assertIn("transient non-actionable frame", source)
        self.assertIn("return False", source)
        self.assertNotIn("device.click", source)

    def test_farming_search_uses_typed_strategic_controls_and_exact_empty_end(self):
        source = FARMING_SEARCH_COMPLETION_PATCH.read_text(encoding="utf-8")
        self.assertIn("start_operation_siren_strategic_search()", source)
        self.assertIn("Strategic search configured through exact Unity controls", source)
        self.assertIn("operation_siren_auto_search_completed_empty()", source)
        self.assertIn("mark_operation_siren_auto_search_completed_empty()", source)
        self.assertIn("Skip pixel map rescan: exact strategic search returned", source)

    def test_explore_safe_zone_uses_typed_unpin_and_adaptive_reanchor(self):
        source = (
            EXPLORE_GLOBE_RECOVERY_PATCH.read_text(encoding="utf-8")
            + EXPLORE_INVENTORY_RECOVERY_PATCH.read_text(encoding="utf-8")
        )
        self.assertIn("semantic_adapter.operation_siren_globe_unpin()", source)
        self.assertIn("anchor_repeat_count", source)
        self.assertIn("rotated_recovery", source)
        self.assertIn("range(-160, 161, 32)", source)
        self.assertIn("probe_offsets = (center_offset,) + rotated_recovery", source)
        self.assertIn("probe_offsets[:16]", source)
        self.assertIn("global_recovery", source)
        self.assertIn("range(100, 901, 160)", source)
        self.assertNotIn("+                    unpin_vector", source)
        self.assertNotIn("+                    pixel_delta", source)
        self.assertIn("Reuse proven semantic globe camera", source)
        self.assertIn("if not hasattr(self, 'globe_camera')", source)
        self.assertIn("else:\n+                    self.ensure_no_zone_pinned()", source)
        self.assertNotIn("begin_campaign_map_swipe_vector", source)

    def test_explore_inventory_proves_no_samples_and_fails_closed_when_present(self):
        source = EXPLORE_INVENTORY_RECOVERY_PATCH.read_text(encoding="utf-8")
        self.assertIn("operation_siren_storage_state()", source)
        self.assertIn("state.sample_count", source)
        self.assertIn("typed tuning sample consumption is not qualified", source)
        self.assertNotIn("rgb2gray(self.device.image)", source)

    def test_obscure_typed_runtime_skips_campaign_rescan_only_in_special_zone(self):
        source = OBSCURE_SPECIAL_ZONE_RESCAN_PATCH.read_text(encoding="utf-8")
        self.assertIn("semantic_adapter = getattr(self.device, 'semantic_adapter', None)", source)
        self.assertIn("if not self.is_in_special_zone():", source)
        self.assertIn("raise SemanticGateClosed(", source)
        self.assertIn("rescan = False", source)
        self.assertIn("self.run_auto_search(rescan=rescan)", source)
        self.assertIn("rescan = 'current'", source)

    def test_coordinate_checkout_owns_exit_prompt_and_retries_exact_entry(self):
        source = (
            COORDINATE_CHECKOUT_RECOVERY_PATCH.read_text(encoding="utf-8")
            + COORDINATE_CARD_RETRY_PATCH.read_text(encoding="utf-8")
            + SPECIAL_PIN_AP_RECOVERY_PATCH.read_text(encoding="utf-8")
        )
        self.assertIn("operation_siren_storage_checkout_prompt_visible()", source)
        self.assertIn("click_operation_siren_storage_checkout_confirm()", source)
        self.assertIn("-                if self.handle_popup_confirm('STORAGE_CHECKOUT'):", source)
        self.assertIn("for attempt in range(80):", source)
        self.assertIn("attempt % 20 == 0", source)
        self.assertIn("Retry exact typed zone entrance", source)
        self.assertIn("detail_timeout = Timer(20, count=1).start()", source)
        self.assertIn("Re-prove the typed card before retrying", source)
        self.assertIn("click_operation_siren_storage_item(item)", source)
        self.assertIn("'OBSCURE': '隐秘海域'", source)
        self.assertIn("state.zone_type == special_types[pinned]", source)
        self.assertIn("Unable to restore typed {pinned} coordinate pin", source)

    def test_coordinate_checkout_rejects_a_stale_pin_of_the_wrong_type(self):
        source = (
            COORDINATE_PIN_TRANSITION_PATCH.read_text(encoding="utf-8")
            + DIRECT_COORDINATE_PIN_PATCH.read_text(encoding="utf-8")
        )
        self.assertIn("self.pinned_to_name(pinned) == item", source)
        self.assertIn("transition_timer = Timer(30, count=1).start()", source)
        self.assertIn("checkout did not produce an exact typed zone pin", source)
        self.assertIn("-                if self.is_zone_pinned():", source)
        self.assertIn("not semantic_adapter.operation_siren_storage_visible()", source)
        self.assertIn("semantic_adapter.operation_siren_globe_visible()", source)

    def test_special_zone_exit_confirmation_marks_transition_complete(self):
        source = SPECIAL_ZONE_EXIT_TRANSITION_PATCH.read_text(encoding="utf-8")
        self.assertIn("if self.handle_popup_confirm('MAP_EXIT'):", source)
        self.assertIn("self.interval_reset(MAP_EXIT)\n+                changed = True", source)

    def test_semantic_map_exit_owns_exact_confirmation(self):
        source = EXACT_MAP_EXIT_CONFIRM_PATCH.read_text(encoding="utf-8")
        self.assertIn("try_click_operation_siren_map_exit_confirm()", source)
        self.assertIn("if receipt is not None:", source)
        self.assertNotIn("operation_siren_map_exit_prompt_visible()", source)
        self.assertIn("semantic_adapter.refresh_frame()", source)
        self.assertIn("else:\n+                if self.handle_popup_confirm('MAP_EXIT'):", source)

    def test_guidepost_uses_exact_radar_event_without_campaign_camera(self):
        source = GUIDEPOST_DIRECT_TARGET_PATCH.read_text(encoding="utf-8")
        self.assertIn("(location, 'guidepost' if location in guideposts else 'port')", source)
        self.assertIn("click_operation_siren_radar_guidepost(target)", source)
        self.assertIn("prefer_adjacent_event=True", source)

    def test_month_boss_question_routes_click_the_owned_world_event(self):
        source = MONTH_BOSS_ROUTE_EVENTS_PATCH.read_text(encoding="utf-8")
        self.assertIn("prefer_adjacent_event=prefer_adjacent_event", source)
        self.assertIn("'is_question': 'question'", source)
        self.assertIn("operation_siren_radar_targets(\n+                            'switch'", source)
        self.assertIn("operation_siren_radar_targets('task')", source)
        self.assertIn("switches = set(", source)

    def test_guidepost_retries_only_while_the_exact_target_remains(self):
        source = GUIDEPOST_RETRY_PATCH.read_text(encoding="utf-8")
        self.assertIn("attempts = 3 if target_kind == 'guidepost' else 1", source)
        self.assertIn("operation_siren_radar_targets('guidepost')", source)
        self.assertIn("if target in remaining:", source)
        self.assertIn("Exact guidepost click was swallowed", source)

    def test_guidepost_waits_for_delayed_exact_story_before_retry(self):
        source = GUIDEPOST_DELAYED_STORY_PATCH.read_text(encoding="utf-8")
        self.assertIn("delayed_event_timer = Timer(12, count=1).start()", source)
        self.assertIn("event == 'story_skip'", source)
        self.assertIn("self.ensure_no_map_event()", source)
        self.assertIn("Handled delayed exact guidepost story event", source)

    def test_evicted_fleet_panel_remounts_complete_os_page_once(self):
        source = PAGE_REMOUNT_PATCH.read_text(encoding="utf-8")
        self.assertIn("fleet portraits are absent or incomplete", source)
        self.assertIn("self.ui_goto_main()", source)
        self.assertIn("self.ui_ensure(page_os)", source)
        self.assertIn("self.zone_init()", source)
        self.assertNotIn("fleet_reset_view", source)

    def test_coordinate_pin_is_accepted_only_after_exact_checkout_confirm(self):
        source = COORDINATE_CONFIRM_PROOF_PATCH.read_text(encoding="utf-8")
        self.assertIn("checkout_confirmed = False", source)
        self.assertIn("checkout_confirmed = True", source)
        self.assertIn("checkout_confirmed\n+                    and pinned is not None", source)

    def test_page_remount_declares_bounded_operation_siren_owner(self):
        source = PAGE_REMOUNT_OWNER_PATCH.read_text(encoding="utf-8")
        self.assertIn("begin_operation_siren_page_remount()", source)
        self.assertIn("finally:", source)
        self.assertIn("end_operation_siren_page_remount()", source)

    def test_obscure_exit_uses_exact_passage_before_map_exit(self):
        source = OBSCURE_EXIT_PASSAGE_PATCH.read_text(encoding="utf-8")
        self.assertIn(
            "operation_siren_obscure_exit_passage_position()", source
        )
        self.assertIn("handle_os_map_fleet_lock(enable=False)", source)
        self.assertIn("operation_siren_obscure_exit_camera_swipe()", source)
        self.assertIn("click_operation_siren_obscure_exit_passage()", source)
        self.assertIn("operation_siren_post_search_loot_visible()", source)
        self.assertIn("click_operation_siren_post_search_loot_back()", source)
        self.assertIn("try_click_operation_siren_map_exit_confirm()", source)
        self.assertIn("outside safe view", source)
        self.assertNotIn("click_operation_siren_obscure_exit_step", source)

    def test_opsi_startup_owns_interrupted_auto_search_and_fleet_states_split(self):
        source = STRONGHOLD_RUNTIME_PATCH.read_text(encoding="utf-8")
        self.assertIn("begin_operation_siren_startup_recovery()", source)
        self.assertIn("semantic_current_fleet_unavailable", source)
        self.assertIn("needs port repair", source)
        self.assertIn("has low resolve", source)
        self.assertIn("Stronghold is already 0%, skip initial auto search", source)
        self.assertIn("Recover retained Operation Siren order panel", source)
        self.assertIn(
            "not semantic_adapter.appear(ORDER_CHECK) and self.is_in_map()",
            source,
        )
        self.assertIn("if not in_order and self.is_in_map():", source)
        self.assertIn("Retry exact Operation Siren order back", source)
        self.assertIn("excluded_zone_ids", source)
        self.assertIn("Skip cleared stronghold zone", source)
        self.assertIn("No exact question mark above current fleet", source)
        self.assertIn("pinned_globe = self.globe.screen2globe([receipt.start])", source)
        self.assertIn("range(-64, 65, 8)", source)
        self.assertIn("BOSS clear before fleet rotation", source)
        self.assertIn("operation_siren_map_visible()", source)

    def test_month_boss_restores_turn_fleet_instead_of_stacked_hud_skip(self):
        source = MONTH_BOSS_FLEET_RESTORE_PATCH.read_text(encoding="utf-8")
        self.assertIn("intended_fleet = semantic_session.operation_siren_current_fleet()", source)
        self.assertIn("Covering fleet {current} stole the boss click", source)
        self.assertIn("semantic_month_boss_leave_boss_cell", source)
        self.assertIn("operation_siren_fleet_already_defeated(", source)
        self.assertIn("fleet.fleet_index", source)
        self.assertNotIn(
            "unavailable = any(\n+                            self.semantic_current_fleet_unavailable()",
            source,
        )

    def test_month_boss_result_clicks_event_trigger_continue(self):
        source = MONTH_BOSS_RESULT_PATCH.read_text(encoding="utf-8")
        self.assertIn("operation_siren_battle_result_visible()", source)
        self.assertIn("click_operation_siren_battle_result()", source)
        self.assertIn("Recover retained Operation Siren battle result", source)
        self.assertIn("Recover retained Operation Siren battle statistics", source)
        self.assertIn("grade == 'DEFEAT'", source)


if __name__ == "__main__":
    unittest.main()
