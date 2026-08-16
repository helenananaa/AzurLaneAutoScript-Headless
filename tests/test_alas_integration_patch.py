import unittest
from pathlib import Path

from scripts.python.build_alas_patch_series import check_generated_patch


class AlasIntegrationPatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).resolve().parents[1]
        manifest = root / "integration" / "alas" / "series" / "series.json"
        generated = root / "integration" / "alas" / "0001-semantic-oracle-hooks.patch"
        check_generated_patch(manifest, generated, root=root)
        cls.patch_text = generated.read_text(encoding="utf-8")

    def test_reward_hook_brackets_instead_of_replacing_alas_state_machine(self):
        self.assertIn("semantic_adapter.begin_mission_reward", self.patch_text)
        self.assertIn("semantic_adapter.end_mission_reward", self.patch_text)
        self.assertIn("semantic_adapter.mission_reward_active", self.patch_text)
        self.assertIn("semantic_adapter.mission_claim_allowed", self.patch_text)
        self.assertIn("Semantic mode uses typed text, skip early_ocr_import", self.patch_text)
        self.assertIn("+        try:", self.patch_text)
        self.assertIn("+        finally:", self.patch_text)
        self.assertIn("+                self._reward_mission_all()", self.patch_text)
        self.assertIn("+                self._reward_mission_weekly()", self.patch_text)
        self.assertNotIn("semantic_adapter.run_mission_reward", self.patch_text)

    def test_all_reward_observation_primitives_route_to_semantic_adapter(self):
        self.assertIn("appear = semantic_adapter.appear(button)", self.patch_text)
        self.assertIn(
            "appear = semantic_adapter.match_template_color(button)",
            self.patch_text,
        )
        self.assertIn("return semantic_adapter.image_color_count(", self.patch_text)

    def test_raw_input_fallbacks_remain_rejected(self):
        for operation in (
            "low-level click",
            "multi_click",
            "long_click",
            "swipe",
            "drag",
        ):
            self.assertIn(operation, self.patch_text)

    def test_retirement_keeps_alas_scheduler_and_replaces_official_transaction(self):
        self.assertIn(
            "diff --git a/module/retire/retirement.py",
            self.patch_text,
        )
        self.assertIn(
            "return semantic_session.retire_ships_one_click(",
            self.patch_text,
        )
        self.assertIn(
            "self.config.OneClickRetire_KeepLimitBreak",
            self.patch_text,
        )
        self.assertIn("logger.hr('Retirement')", self.patch_text)
        self.assertIn(
            "Official one-click retirement found no eligible ships",
            self.patch_text,
        )
        self.assertIn("raise RequestHumanTakeover", self.patch_text)
        self.assertNotIn("-            total += 10", self.patch_text)

    def test_enhancement_keeps_detailed_config_and_replaces_pixel_transaction(self):
        self.assertIn(
            "diff --git a/module/retire/enhancement.py",
            self.patch_text,
        )
        self.assertIn("return semantic_session.enhance_ships(", self.patch_text)
        self.assertIn("self.config.Enhance_ShipToEnhance", self.patch_text)
        self.assertIn("self.config.Enhance_CheckPerCategory", self.patch_text)
        self.assertIn("self.config.Enhance_Filter", self.patch_text)
        self.assertIn("Invalid filter tokens fail", self.patch_text)
        self.assertNotIn("-        if favourite is None:", self.patch_text)

    def test_semantic_screenshot_refreshes_after_alas_interval_ownership(self):
        self.assertIn(
            "diff --git a/module/device/screenshot.py b/module/device/screenshot.py",
            self.patch_text,
        )
        wait = self.patch_text.index("self._screenshot_interval.wait()")
        reset = self.patch_text.index("self._screenshot_interval.reset()", wait)
        refresh = self.patch_text.index("semantic_session.refresh_frame()", reset)
        guard = self.patch_text.index("semantic_session.pixel_guard(frame)", refresh)
        native_loop = self.patch_text.index("for _ in range(2):", refresh)
        self.assertLess(wait, reset)
        self.assertLess(reset, refresh)
        self.assertLess(refresh, guard)
        self.assertLess(guard, native_loop)
        self.assertIn(
            "if semantic_session is not None:\n+            return False\n"
            "         if GET_MISSION.match",
            self.patch_text,
        )

    def test_campaign_viewport_replaces_only_final_swipe_dispatch(self):
        self.assertIn(
            "else semantic_adapter.begin_campaign_map_swipe_vector",
            self.patch_text,
        )
        self.assertIn("semantic_intent = begin_swipe(", self.patch_text)
        self.assertIn(
            "p1, p2 = random_rectangle_vector_opted(",
            self.patch_text,
        )
        self.assertIn(
            "receipt = semantic_adapter.swipe(",
            self.patch_text,
        )
        self.assertIn(
            "else semantic_adapter.end_campaign_map_swipe_vector",
            self.patch_text,
        )
        self.assertIn("end_swipe(semantic_intent)", self.patch_text)
        self.assertIn("distance_check=distance_check", self.patch_text)
        self.assertNotIn(
            "+            semantic_adapter.reject_raw_input('swipe')",
            self.patch_text,
        )

    def test_campaign_camera_update_keeps_alas_loop_and_replaces_only_view_input(self):
        self.assertIn("diff --git a/module/map/camera.py", self.patch_text)
        self.assertIn(
            "state = semantic_session.campaign_camera_state()",
            self.patch_text,
        )
        self.assertIn(
            "observation = install_alas_campaign_camera_view(",
            self.patch_text,
        )
        self.assertIn("self._view_init()", self.patch_text)
        self.assertNotIn("def update(self, camera=True", self.patch_text)

    def test_login_hook_brackets_original_handler_state_machine(self):
        self.assertIn(
            "diff --git a/module/handler/login.py",
            self.patch_text,
        )
        self.assertIn("semantic_adapter.begin_login()", self.patch_text)
        self.assertIn("semantic_adapter.end_login()", self.patch_text)
        self.assertIn("+                self._handle_app_login()", self.patch_text)

    def test_ocr_layer_uses_context_bound_typed_text(self):
        self.assertIn("diff --git a/module/ocr/ocr.py", self.patch_text)
        self.assertIn("bind_semantic_session", self.patch_text)
        self.assertIn("current_semantic_session", self.patch_text)
        self.assertIn("semantic_session.ocr_text(", self.patch_text)
        self.assertIn("direct OCR without screen areas", self.patch_text)
        self.assertNotIn(
            "-        result_list = self.cnocr.atomic_ocr_for_single_lines",
            self.patch_text,
        )

    def test_mail_hook_brackets_instead_of_replacing_alas_state_machine(self):
        self.assertIn("diff --git a/module/freebies/mail_white.py", self.patch_text)
        self.assertIn("semantic_adapter.begin_mail()", self.patch_text)
        self.assertIn("semantic_adapter.end_mail()", self.patch_text)
        self.assertIn("+            self.mail_claim(", self.patch_text)

    def test_commission_hook_brackets_instead_of_replacing_alas_state_machine(self):
        self.assertIn("diff --git a/module/commission/commission.py", self.patch_text)
        self.assertIn("diff --git a/module/commission/project.py", self.patch_text)
        self.assertIn("semantic_adapter.begin_commission()", self.patch_text)
        self.assertIn("semantic_adapter.end_commission()", self.patch_text)
        self.assertIn("Commission.from_semantic", self.patch_text)
        self.assertIn("list_mode=list_mode", self.patch_text)
        self.assertIn("self.semantic_row_key = (list_mode, state.index)", self.patch_text)
        self.assertIn("getattr(self, 'semantic_row_key', None)", self.patch_text)
        self.assertIn("semantic_adapter.commission_scroll_state()", self.patch_text)
        self.assertIn("semantic_adapter.commission_scroll_next()", self.patch_text)
        self.assertIn("semantic_adapter.commission_scroll_to_top()", self.patch_text)
        self.assertIn("semantic_adapter.commission_start_allowed()", self.patch_text)
        self.assertIn("semantic_adapter.commission_start_proof()", self.patch_text)
        self.assertIn("semantic_adapter.close_started_commission_detail()", self.patch_text)
        self.assertIn("semantic_adapter.commission_reward_pending()", self.patch_text)
        self.assertIn("semantic_adapter.confirm_commission_reward()", self.patch_text)
        self.assertIn("skip mode reset", self.patch_text)
        self.assertIn("+            self.commission_receive()", self.patch_text)
        self.assertIn("+            self.commission_start()", self.patch_text)

    def test_research_pixel_helpers_route_to_typed_project_model(self):
        self.assertIn("diff --git a/module/research/project.py", self.patch_text)
        self.assertIn("semantic_session.research_finished_index()", self.patch_text)
        self.assertIn("semantic_session.research_series()", self.patch_text)
        self.assertIn("semantic_session.research_statuses()", self.patch_text)
        self.assertIn("semantic_session.research_projects_for_alas", self.patch_text)
        self.assertIn("semantic_session.validate_research_filter", self.patch_text)

    def test_tactical_state_machine_uses_typed_countdowns_and_safe_cancel(self):
        self.assertIn("diff --git a/module/tactical/tactical_class.py", self.patch_text)
        self.assertIn("semantic_adapter.begin_tactical()", self.patch_text)
        self.assertIn("semantic_adapter.end_tactical()", self.patch_text)
        self.assertIn("semantic_session.tactical_remaining_seconds()", self.patch_text)
        self.assertIn(
            "semantic_session.cancel_tactical_continue_if_present()",
            self.patch_text,
        )

    def test_dorm_scheduler_uses_typed_occupied_slot_count(self):
        self.assertIn("diff --git a/module/dorm/dorm.py", self.patch_text)
        self.assertIn("semantic_session.dorm_state().occupied_slots", self.patch_text)

    def test_dorm_scheduler_recovers_the_exact_empty_food_modal(self):
        self.assertIn(
            "from module.ui.assets import DORM_CHECK, DORM_FEED_CANCEL",
            self.patch_text,
        )
        self.assertIn("except SemanticGateClosed:", self.patch_text)
        self.assertIn(
            "self.appear_then_click(DORM_FEED_CANCEL, offset=(30, 30))",
            self.patch_text,
        )
        self.assertIn(
            'semantic_adapter.open().oracle.enabled("dorm/empty-food/cancel")',
            self.patch_text,
        )
        self.assertIn("self.device.click(DORM_FEED_CANCEL)", self.patch_text)
        self.assertIn(
            'semantic_adapter.open().oracle.enabled("dorm/feed")',
            self.patch_text,
        )
        self.assertIn("self.device.click(DORM_FEED_ENTER)", self.patch_text)

    def test_shared_scheduler_is_validated_before_original_queueing(self):
        self.assertIn("diff --git a/module/config/config.py", self.patch_text)
        gate = self.patch_text.index("validate_alas_scheduler_config(self.data)")
        queue = self.patch_text.index("pending = []", gate)
        self.assertLess(gate, queue)

    def test_five_new_flows_preserve_alas_state_machine_ownership(self):
        for begin, end in (
            ("begin_tactical()", "end_tactical()"),
            ("begin_research()", "end_research()"),
            ("begin_dorm()", "end_dorm()"),
            ("begin_build()", "end_build()"),
        ):
            self.assertIn("semantic_adapter." + begin, self.patch_text)
            self.assertIn("semantic_adapter." + end, self.patch_text)
        self.assertGreaterEqual(
            self.patch_text.count("def _run_alas_state_machine(self):"),
            3,
        )
        self.assertIn("return self._run_alas_state_machine()", self.patch_text)
        self.assertIn("self.tactical_class_receive()", self.patch_text)
        self.assertIn("semantic_session.research_projects_for_alas", self.patch_text)
        self.assertIn("semantic_session.research_detail_available()", self.patch_text)
        self.assertIn("semantic_session.research_detail_can_queue()", self.patch_text)
        self.assertIn("semantic_session.research_queue_fill_slots()", self.patch_text)
        self.assertIn("Book.from_semantic", self.patch_text)
        self.assertIn("semantic_session.tactical_select_book", self.patch_text)
        self.assertIn("semantic_session.dorm_feed_food(index, count)", self.patch_text)
        self.assertIn("semantic_session.build_submit_state()", self.patch_text)
        self.assertIn(
            "ALAS still owns selection, queue filling, retry, and scheduling.",
            self.patch_text,
        )
        self.assertIn(
            "ALAS still owns feed filtering, collect loop, and scheduling.",
            self.patch_text,
        )
        self.assertIn(
            "ALAS still owns pool choice, affordability, and submit scheduling.",
            self.patch_text,
        )

    def test_campaign_fleet_preparation_preserves_alas_state_machine(self):
        self.assertIn(
            "diff --git a/module/map/map_fleet_preparation.py",
            self.patch_text,
        )
        self.assertIn(
            "semantic_adapter.authorize_campaign_fleet_preparation(",
            self.patch_text,
        )
        self.assertIn(
            "+                                self.fleet_preparation()",
            self.patch_text,
        )
        self.assertIn(
            "semantic_adapter.confirm_campaign_fleet_selection()",
            self.patch_text,
        )
        self.assertIn(
            "semantic_adapter.close_campaign_fleet_dropdown_for_rollback()",
            self.patch_text,
        )
        self.assertIn(
            "semantic_adapter.confirm_campaign_fleet_preparation()",
            self.patch_text,
        )
        self.assertIn(
            "semantic_adapter.campaign_fleet_selected_indices(",
            self.patch_text,
        )
        self.assertIn(
            "semantic_adapter.authorize_campaign_sortie(",
            self.patch_text,
        )
        self.assertIn(
            "+                                    self.device.click(FLEET_PREPARATION)",
            self.patch_text,
        )
        self.assertIn(
            "semantic_adapter.campaign_sortie_committed()",
            self.patch_text,
        )
        self.assertIn(
            "semantic_adapter.confirm_campaign_sortie()",
            self.patch_text,
        )
        self.assertIn(
            "+                                self.handle_2x_book_setting(mode='prep')",
            self.patch_text,
        )
        self.assertIn(
            "+                                self.handle_auto_search_setting()",
            self.patch_text,
        )
        self.assertIn(
            "semantic_adapter.campaign_map_preparation_committed()",
            self.patch_text,
        )
        self.assertIn(
            "self.handle_auto_search()",
            self.patch_text,
        )

    def test_campaign_map_model_replaces_only_the_read_only_input_boundary(self):
        self.assertIn("semantic_adapter.campaign_map_state(", self.patch_text)
        self.assertIn("columns=campaign_map.shape[0] + 1", self.patch_text)
        self.assertIn("grid.location for grid in campaign_map", self.patch_text)
        self.assertIn("if grid.is_land", self.patch_text)
        self.assertIn("expected_fleet_count=sum((", self.patch_text)
        self.assertIn("semantic_map_resume = True", self.patch_text)
        self.assertIn("logger.info('Already in map, retreating.')", self.patch_text)

    def test_campaign_stop_conditions_use_typed_progress_and_levels(self):
        self.assertIn(
            "diff --git a/module/handler/fast_forward.py",
            self.patch_text,
        )
        self.assertIn(
            "achievement = semantic_session.campaign_map_achievement_state()",
            self.patch_text,
        )
        self.assertIn(
            "self.map_is_threat_safe = achievement.threat_safe",
            self.patch_text,
        )
        self.assertIn(
            "diff --git a/module/combat/level.py",
            self.patch_text,
        )
        self.assertIn(
            "self.lv = list(semantic_session.campaign_fleet_levels())",
            self.patch_text,
        )
        self.assertIn(
            "+            self.lv_reset()\n+            self.lv_get()\n+            state =",
            self.patch_text,
        )

    def test_campaign_map_projection_delegates_to_alas_without_movement(self):
        self.assertIn(
            "synchronize_alas_campaign_map,",
            self.patch_text,
        )
        self.assertIn(
            "synchronize_alas_campaign_map(",
            self.patch_text,
        )
        self.assertIn("synchronize_alas_campaign_map(self, state)", self.patch_text)
        self.assertNotIn("semantic_map_projection.goto", self.patch_text)
        self.assertNotIn("semantic_map_projection.map_control_init", self.patch_text)

    def test_campaign_decision_runs_alas_branch_but_intercepts_goto(self):
        self.assertIn(
            "preview_alas_campaign_decision,",
            self.patch_text,
        )
        self.assertIn(
            "decision = preview_alas_campaign_decision(",
            self.patch_text,
        )
        self.assertIn("preview_alas_campaign_decision(self, projection)", self.patch_text)
        self.assertIn("decision.branch_name", self.patch_text)
        self.assertIn("decision.fleet_index", self.patch_text)
        self.assertIn("decision.target_node", self.patch_text)
        self.assertIn("decision.route_nodes", self.patch_text)
        self.assertNotIn("self.campaign.goto(decision", self.patch_text)
        self.assertNotIn("self.campaign._goto(decision", self.patch_text)

    def test_campaign_combat_admission_keeps_native_goto_as_the_input_owner(self):
        self.assertIn(
            "semantic_adapter.authorize_campaign_combat(",
            self.patch_text,
        )
        self.assertIn(
            "raise ScriptEnd('Semantic campaign combat budget is zero')",
            self.patch_text,
        )
        self.assertIn(
            "receipt = semantic_adapter.click(button)",
            self.patch_text,
        )
        self.assertNotIn("-            self.device.click(grid)", self.patch_text)
        self.assertIn("semantic_adapter.campaign_combat_active()", self.patch_text)
        self.assertIn(
            "semantic_adapter.recheck_campaign_combat_target_after_camera_view(",
            self.patch_text,
        )
        self.assertIn("self.semantic_prepare_a_battle()", self.patch_text)
        self.assertIn("complete_campaign_combat_round(", self.patch_text)
        self.assertIn("Already in semantic campaign map, resuming ALAS.", self.patch_text)
        self.assertNotIn("commit_alas_campaign_goto_input_for_evidence", self.patch_text)
        self.assertNotIn("Semantic ALAS combat input committed", self.patch_text)
        self.assertNotIn(
            "Semantic ALAS goto input preview validation complete",
            self.patch_text,
        )
        self.assertNotIn("self.campaign.goto(decision", self.patch_text)
        self.assertNotIn("self.campaign._goto(decision", self.patch_text)
        self.assertNotIn(
            "canonical_alas_campaign_combat_replay", self.patch_text
        )
        self.assertNotIn(
            "replay_alas_campaign_combat_state_machine", self.patch_text
        )


if __name__ == "__main__":
    unittest.main()
