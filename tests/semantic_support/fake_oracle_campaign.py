"""Fake oracle campaign for the typed ALAS boundary."""

from __future__ import annotations

from alas_headless import (
    Bounds,
    ButtonState,
    CampaignMapViewportSwipeProof,
    Point,
    SemanticGateClosed,
    SemanticTargetMissing,
)
from alas_headless.semantic_oracle import ActionReceipt
from dataclasses import replace
from types import SimpleNamespace


class FakeCampaignOracle:
    def campaign_dock_full_visible(self, stage_code):
        return getattr(self, 'dock_full_visible_value', False)

    def campaign_2x_book_selected(self, mode=None):
        return getattr(self, "campaign_2x_book_value", False)

    def campaign_auto_search_selected(self):
        return self.toggle_selected_values.get(
            "campaign/map-preparation/auto-search", False
        )

    def event_campaign_page_visible(self):
        return self.event_campaign_page_visible_value

    def event_campaign_page_state(self):
        if self.event_campaign_page_error is not None:
            raise self.event_campaign_page_error
        if not self.event_campaign_page_visible_value:
            raise SemanticTargetMissing("event campaign page is absent")
        return self.campaign_state_value

    def current_raid_event(self):
        return "raid_20260827"

    def supports_raid_layout(self, event):
        return event == "raid_20260827"

    def raid_page_visible(self, event):
        if event != "raid_20260827":
            raise SemanticGateClosed("Raid page event is unsupported")
        if self.raid_page_visible_errors:
            raise self.raid_page_visible_errors.pop(0)
        return self.raid_page_visible_value

    def click_raid_stage(self, event, mode):
        if self.raid_stage_errors:
            raise self.raid_stage_errors.pop(0)
        semantic_id = "raid/stage/{0}".format(mode)
        self.click_calls.append(semantic_id)
        return self.click_receipt(semantic_id)

    def click_raid_advanced_challenge(self, event):
        self.click_calls.append("raid/advanced/entry:" + event)
        return self.click_receipt("raid/advanced/entry")

    def click_raid_home(self, event):
        self.click_calls.append("raid/page/home:" + event)
        self.main_page_visible_value = True
        return self.click_receipt("raid/page/home")

    def raid_fleet_ready(self, event):
        if event != "raid_20260827":
            raise SemanticGateClosed("Raid fleet-selection event is unsupported")
        return self.raid_fleet_ready_value

    def raid_precombat_visible(self, event):
        return self.raid_precombat_visible_value

    def raid_precombat_notice_visible(self, event):
        return self.raid_precombat_notice_visible_value

    def raid_precombat_multiple_visible(self, event):
        return self.raid_precombat_multiple_visible_value

    def raid_multiple_sortie_visible(self, event):
        return self.raid_multiple_sortie_visible_value

    def raid_multiple_sortie_state(self, event):
        if event != "raid_20260827":
            raise SemanticGateClosed("Raid multiple-sortie event is unsupported")
        return self.raid_multiple_sortie_state_value

    def event_story_dialogue_visible(self):
        return self.event_story_dialogue_visible_value

    def event_story_skip_prompt_visible(self):
        return self.event_story_skip_prompt_visible_value

    def click_event_story_skip_confirm(self):
        self.click_calls.append("story/skip/confirm")
        return ActionReceipt(
            semantic_id="story/skip/confirm",
            generation=12,
            point=Point(640, 360),
            bounds=Bounds(600, 320, 680, 400),
            path="root/story/skip/confirm",
        )

    def click_event_story_option(self, option_index):
        self.click_calls.append("story/option/{0}".format(option_index))
        return ActionReceipt(
            semantic_id="story/option/{0}".format(option_index),
            generation=12,
            point=Point(640, 360),
            bounds=Bounds(600, 320, 680, 400),
            path="root/story/option",
        )

    def click_event_story_skip(self):
        self.click_calls.append("story/skip")
        return ActionReceipt(
            semantic_id="story/skip",
            generation=12,
            point=Point(640, 80),
            bounds=Bounds(600, 40, 680, 120),
            path="root/story/skip",
        )

    def gems_farming_select_fleet_index(self, fleet_index):
        self.gems_calls.append(("fleet", fleet_index))
        return fleet_index

    def gems_farming_open_slot(self, role):
        self.gems_calls.append(("open", role))
        return self.click_receipt("gems-farming/formation/" + role + "/open")

    def gems_farming_hard_slot_occupied(self, stage_code, fleet_index, role):
        self.gems_calls.append(("hard-occupied", stage_code, fleet_index, role))
        return self.gems_hard_occupied[role]

    def gems_farming_hard_unmount(self, stage_code, fleet_index, role):
        self.gems_calls.append(("hard-unmount", stage_code, fleet_index, role))
        return self.click_receipt("gems-farming/hard/unmount")

    def gems_farming_hard_open_slot(self, stage_code, fleet_index, role):
        self.gems_calls.append(("hard-open", stage_code, fleet_index, role))
        return self.click_receipt("gems-farming/hard/open")

    def gems_farming_equipment_take_off(self, role):
        self.gems_calls.append(("equipment-off", role))
        return SimpleNamespace(role=role)

    def gems_farming_equipment_take_on(self, role):
        self.gems_calls.append(("equipment-on", role))
        return SimpleNamespace(role=role)

    def set_gems_farming_dock_sort(self, descending):
        self.gems_calls.append(("sort", descending))
        return None

    def set_gems_farming_dock_filter(self, role, factions):
        self.gems_calls.append(("filter", role, factions))
        if self.gems_filter_error is not None:
            raise self.gems_filter_error
        return ()

    def cancel_gems_farming_dock_filter_if_visible(self):
        self.gems_calls.append(("filter-cancel",))
        if self.gems_filter_cancel_error is not None:
            raise self.gems_filter_cancel_error
        return self.click_receipt("gems-farming/dock/filter/cancel")

    def gems_farming_dock_candidates(self):
        self.gems_calls.append(("candidates",))
        return self.gems_candidates

    def click_gems_farming_candidate(self, candidate):
        self.gems_calls.append(("select", candidate.ship_id))
        return self.click_receipt("gems-farming/dock/ship/{0}".format(candidate.ship_id))

    def cancel_gems_farming_candidate_selection(self):
        self.gems_calls.append(("cancel",))
        return self.click_receipt("gems-farming/dock/cancel")

    def confirm_gems_farming_candidate_selection(self, candidate, role):
        self.gems_calls.append(("confirm", candidate.ship_id, role))
        return self.click_receipt("gems-farming/dock/confirm")

    def war_archives_campaign_page_visible(self):
        return self.war_archives_campaign_visible_value

    def campaign_menu_is_entry(self):
        return self.campaign_menu_value

    def campaign_page_is_normal(self):
        if self.campaign_page_error is not None:
            raise self.campaign_page_error
        return self.campaign_page_value

    def campaign_page_state(self):
        if self.campaign_page_error is not None:
            raise self.campaign_page_error
        if not self.campaign_page_value:
            raise SemanticGateClosed("campaign page identity is not proven")
        return self.campaign_state_value

    def campaign_is_in_map(self):
        return self.campaign_in_map_value

    def campaign_map_entry_state(self):
        if not self.campaign_in_map_value:
            raise SemanticGateClosed("campaign map-scene identity is absent")
        return SimpleNamespace(
            generation=self.campaign_map_generation,
            root_path="LevelCamera/Canvas/UIMain/LevelGrid",
            button_paths=(
                "LevelCamera/Canvas/UIMain/LevelGrid/DragLayer/op1/retreat",
            ),
            image_paths=(
                "LevelCamera/Canvas/UIMain/LevelGrid/DragLayer/plane/"
                "display/mask/sea",
            ),
        )

    def campaign_auto_search_active_state(self):
        if not self.campaign_in_map_value:
            raise SemanticGateClosed(
                "campaign official auto-search surface is not proven"
            )
        return SimpleNamespace(
            generation=self.campaign_map_generation,
            root_path="UICamera/Canvas/UIMain/CombatUIStandard(Clone)",
        )

    def campaign_map_state(
        self,
        stage_code,
        *,
        columns,
        rows,
        land_cells,
        expected_fleet_count,
    ):
        self.campaign_map_state_calls.append(
            (
                stage_code,
                columns,
                rows,
                tuple(land_cells),
                expected_fleet_count,
            )
        )
        return self.campaign_map_state_value

    def campaign_map_cell_input(
        self, state, node, *, allow_expected_enemy_coverage=False
    ):
        self.campaign_map_cell_input_calls.append(
            (node, allow_expected_enemy_coverage)
        )
        cell = next(item for item in state.cells if item.node == node)
        return ButtonState(
            name="chapter_cell_quad_6_4",
            path=cell.button_path,
            active_in_hierarchy=True,
            active_and_enabled=True,
            interactable=True,
            raycast_top=True,
            point=cell.point,
            bounds=cell.bounds,
            raw={},
        )

    def campaign_map_cell_viewport_target(self, state, node):
        return replace(
            self.campaign_map_cell_input(state, node),
            raycast_top=self.campaign_map_target_raycast_top,
        )

    def campaign_map_viewport_swipe(
        self,
        state,
        target_node,
        intent,
        *,
        start,
        end,
        duration_ms,
        columns,
        rows,
        land_cells,
        expected_fleet_count,
        allow_enemy_additions=False,
    ):
        self.campaign_map_swipe_calls.append(
            (
                target_node,
                intent,
                start,
                end,
                duration_ms,
                columns,
                rows,
                tuple(land_cells),
                expected_fleet_count,
                allow_enemy_additions,
            )
        )
        target = next(cell for cell in state.cells if cell.node == target_node)
        after_point = Point(target.point.x + 200, target.point.y)
        after_bounds = Bounds(
            target.bounds.left + 200,
            target.bounds.top,
            target.bounds.right + 200,
            target.bounds.bottom,
        )
        post_state = replace(
            state,
            generation=state.generation + 2,
            cells=tuple(
                replace(cell, point=after_point, bounds=after_bounds)
                if cell.node == target_node
                else cell
                for cell in state.cells
            ),
        )
        self.campaign_map_state_value = post_state
        self.campaign_map_target_raycast_top = True
        return CampaignMapViewportSwipeProof(
            semantic_id="campaign/map/viewport/" + target_node,
            target_node=target_node,
            pre_generation=state.generation,
            input_generation=state.generation + 1,
            post_generation=post_state.generation,
            name=intent.name,
            grid_vector=intent.grid_vector,
            pixel_vector=intent.pixel_vector,
            start=start,
            end=end,
            duration_ms=duration_ms,
            coherent_cell_count=len(state.cells),
            median_cell_delta=(200.0, 0.0),
            maximum_delta_residual=0.0,
            target_path=target.button_path,
            target_before_point=target.point,
            target_after_point=after_point,
            target_after_bounds=after_bounds,
            post_state=post_state,
        )

    def click_campaign_map_cell(
        self, state, node, *, allow_expected_enemy_coverage=False
    ):
        self.campaign_map_cell_click_calls.append(
            (node, allow_expected_enemy_coverage)
        )
        target = self.campaign_map_cell_input(
            state,
            node,
            allow_expected_enemy_coverage=allow_expected_enemy_coverage,
        )
        semantic_id = "campaign/map/grid/" + node
        self.click_calls.append(semantic_id)
        return ActionReceipt(
            semantic_id=semantic_id,
            generation=state.generation + 1,
            point=target.point,
            bounds=target.bounds,
            path=target.path,
        )

    def campaign_mode_switch_state(self):
        return "hard"

    def campaign_oil(self):
        return self.campaign_oil_value

    def event_points(self):
        return self.event_points_value

    def event_coin(self, stage_code=None):
        return self.event_coin_value

    def campaign_map_achievement_state(self, stage_code):
        return self.campaign_achievement_value

    def campaign_fleet_levels(self):
        return self.campaign_fleet_levels_value

    def campaign_stage_actionable(self, stage_code):
        return any(
            stage.stage_code == stage_code and stage.button.actionable
            for stage in self.campaign_state_value.stages
        )

    def click_campaign_stage(self, stage_code):
        self.click_calls.append("campaign/stage/" + stage_code)
        self.campaign_preparation_value = SimpleNamespace(kind="map")
        return self.click_receipt("campaign/stage/" + stage_code, generation=7)

    def campaign_preparation_state(self, stage_code):
        if self.campaign_preparation_error is not None:
            raise self.campaign_preparation_error
        return self.campaign_preparation_value

    def click_campaign_map_preparation(self, stage_code):
        self.click_calls.append("campaign/map-preparation/proceed")
        self.campaign_preparation_value = SimpleNamespace(kind="fleet")
        return self.click_receipt(
            "campaign/map-preparation/proceed", generation=8
        )

    def cancel_campaign_map_preparation(self, stage_code):
        self.click_calls.append("campaign/map-preparation/cancel")
        self.campaign_preparation_value = None
        return self.click_receipt(
            "campaign/map-preparation/cancel", generation=9
        )

    def cancel_campaign_fleet_preparation(self, stage_code):
        self.click_calls.append("campaign/fleet-preparation/cancel")
        self.campaign_preparation_value = None
        return self.click_receipt(
            "campaign/fleet-preparation/cancel", generation=9
        )

    def campaign_fleet_selection_state(self, stage_code, fallback_oil_cost=None):
        rows = tuple(
            SimpleNamespace(
                row_key=row_key,
                selected_fleet=(selected or None),
                in_use=bool(selected),
                ship_levels=((100,) if selected else ()),
                available=True,
                select_button=SimpleNamespace(
                    generation=self.campaign_fleet_generation,
                    point=Point(2, 3),
                    bounds=Bounds(1, 2, 3, 4),
                    path="root/{0}/select".format(row_key),
                ),
                clear_button=SimpleNamespace(
                    generation=self.campaign_fleet_generation,
                    point=Point(2, 3),
                    bounds=Bounds(1, 2, 3, 4),
                    path="root/{0}/clear".format(row_key),
                ),
                hard_satisfied=(
                    bool(selected)
                    and self.campaign_empty_required_slots[row_key] == 0
                    if self.campaign_hard_mode and row_key != "submarine"
                    else None
                ),
                empty_required_slots=self.campaign_empty_required_slots[row_key],
            )
            for row_key, selected in self.campaign_fleets.items()
        )
        return SimpleNamespace(
            generation=self.campaign_fleet_generation,
            stage_code=stage_code,
            surface_fleets=(
                int(bool(self.campaign_fleets["fleet1"]))
                + int(bool(self.campaign_fleets["fleet2"])),
                2,
            ),
            submarine_fleets=(int(bool(self.campaign_fleets["submarine"])), 1),
            mob_oil_cost=42,
            boss_oil_cost=55,
            submarine_oil_cost=17,
            required_sortie_oil=97,
            oil_cost_source="observed-fleet-summary",
            rows=rows,
            sortie_button=SimpleNamespace(actionable=True),
            hard_mode=self.campaign_hard_mode,
            hard_requirements=(
                (SimpleNamespace(satisfied=True),)
                if self.campaign_hard_mode else ()
            ),
        )

    def campaign_fleet_dropdown_state(self):
        if self.campaign_fleet_dropdown_row is None:
            return None
        if self.campaign_fleet_dropdown_row == "submarine":
            selected = (self.campaign_fleets["submarine"],)
        else:
            selected = (
                self.campaign_fleets["fleet1"],
                self.campaign_fleets["fleet2"],
            )
        return SimpleNamespace(
            generation=self.campaign_fleet_generation,
            active_indices=tuple(
                sorted(set(value for value in selected if value))
            ),
        )

    def click_campaign_fleet_row(self, row_key, action):
        if action == "select":
            self.campaign_fleet_dropdown_row = row_key
        elif action == "clear":
            self.campaign_fleets[row_key] = 0
        else:
            raise AssertionError("unexpected fake campaign fleet action")
        self.campaign_fleet_generation += 1
        semantic_row = (
            "submarine/1"
            if row_key == "submarine"
            else row_key.replace("fleet", "fleet/")
        )
        semantic_id = "campaign/fleet-preparation/{0}/{1}".format(
            semantic_row, action
        )
        self.click_calls.append(semantic_id)
        return self.click_receipt(
            semantic_id, generation=self.campaign_fleet_generation
        )

    def click_campaign_fleet_option(self, index):
        if self.campaign_fleet_dropdown_row is None:
            raise AssertionError("fake campaign fleet dropdown is closed")
        if self.campaign_fleet_dropdown_row == "submarine":
            active = {self.campaign_fleets["submarine"]}
        else:
            active = {
                self.campaign_fleets["fleet1"],
                self.campaign_fleets["fleet2"],
            }
        active.discard(0)
        if index not in active:
            self.campaign_fleets[self.campaign_fleet_dropdown_row] = index
        self.campaign_fleet_dropdown_row = None
        self.campaign_fleet_generation += 1
        semantic_id = "campaign/fleet-preparation/option/{0}".format(index)
        self.click_calls.append(semantic_id)
        return self.click_receipt(
            semantic_id, generation=self.campaign_fleet_generation
        )

    def click_campaign_sortie(self, stage_code, fallback_oil_cost=None):
        self.click_calls.append("campaign/fleet-preparation/sortie")
        self.campaign_preparation_value = None
        self.campaign_in_map_value = True
        self.campaign_map_generation = self.campaign_fleet_generation + 3
        return self.click_receipt(
            "campaign/fleet-preparation/sortie",
            generation=self.campaign_fleet_generation,
        )

    def click_campaign_auto_search_sortie(self, stage_code):
        return self.click_campaign_sortie(stage_code)

    def click_raid_fleet_start(self, event):
        self.click_calls.append("raid/fleet/start:" + event)
        return self.click_receipt("raid/fleet/start")

    def click_raid_precombat_notice(self, event):
        self.click_calls.append("raid/precombat/notice:" + event)
        self.raid_precombat_notice_visible_value = False
        return self.click_receipt("raid/precombat/notice/acknowledge")

    def click_raid_precombat_start(self, event):
        self.click_calls.append("raid/precombat/start:" + event)
        return self.click_receipt("raid/precombat/start")

    def click_raid_precombat_multiple(self, event):
        self.click_calls.append("raid/precombat/multiple:" + event)
        return self.click_receipt("raid/precombat/multiple")

    def click_raid_multiple_sortie_back(self, event):
        self.click_calls.append("raid/multiple-sortie/back:" + event)
        return self.click_receipt("raid/multiple-sortie/back")

    def click_raid_fleet_recommend(self, event):
        self.click_calls.append("raid/fleet/recommend:" + event)
        return self.click_receipt("raid/fleet/recommend")

    def campaign_auto_search_role_state(self):
        if (
            self.campaign_hard_mode
            and "campaign/fleet-preparation/roles/tab"
            not in self.toggle_selected_values
        ):
            return SimpleNamespace(
                generation=self.campaign_fleet_generation,
                fleet1_role="game-managed",
                fleet2_role="game-managed",
            )
        if not self.campaign_role_tab_selected:
            raise SemanticGateClosed(
                "campaign auto-search role tab is not selected"
            )
        return SimpleNamespace(
            generation=self.campaign_fleet_generation,
            fleet1_role=self.campaign_roles[0],
            fleet2_role=self.campaign_roles[1],
        )
