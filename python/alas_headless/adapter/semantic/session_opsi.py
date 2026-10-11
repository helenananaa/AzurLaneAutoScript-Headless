"""Session opsi for the typed ALAS boundary."""

from __future__ import annotations

import time
from typing import Any, List, Optional, Tuple
from ...semantic_oracle import (
    ActionReceipt,
    OperationSirenActionPointState,
    OperationSirenDaemonTarget,
    OperationSirenGlobeState,
    OperationSirenGlobeSwipeReceipt,
    OperationSirenState,
    OperationSirenStorageScrollReceipt,
    OperationSirenStorageState,
    SemanticGateClosed,
)
from .contracts import _OperationSirenGlobeSwipeIntent


class SessionOpsiPorts:
    """Session opsi on the shared immutable frame."""

    def operation_siren_map_swipe_owned(self):
        return self.open().operation_siren_map_swipe_owned()

    def begin_operation_siren_map_swipe_vector(self,vector,**options):
        return self.open().begin_operation_siren_map_swipe_vector(vector,**options)

    def end_operation_siren_map_swipe_vector(self,intent):
        self.open().end_operation_siren_map_swipe_vector(intent)

    def operation_siren_shop_items(self):
        for attempt in range(8):
            try:
                return self.open().oracle.operation_siren_shop_items()
            except SemanticGateClosed as exc:
                if (
                    str(exc) != "Operation Siren shop snapshots are not coherent"
                    or attempt == 7
                ):
                    raise
                time.sleep(0.2)
        raise AssertionError("unreachable Operation Siren shop retry")

    def operation_siren_shop_currency(self) -> int:
        for attempt in range(8):
            try:
                return self.open().oracle.operation_siren_shop_currency()
            except SemanticGateClosed as exc:
                if (
                    str(exc) != "Operation Siren shop snapshots are not coherent"
                    or attempt == 7
                ):
                    raise
                time.sleep(0.2)
        raise AssertionError("unreachable Operation Siren shop retry")

    def purchase_operation_siren_shop_item_once(
        self, index: int, expected_name: str, expected_price: int
    ) -> ActionReceipt:
        self.refresh_frame()
        return self.open().purchase_operation_siren_shop_item_once(
            index, expected_name, expected_price
        )

    def resume_operation_siren_shop_purchase_once(
        self,
        index: int,
        expected_name: str,
        expected_display_name: str,
        expected_price: int,
        before_remaining: int,
        before_currency: int,
    ) -> ActionReceipt:
        self.refresh_frame()
        return self.open().resume_operation_siren_shop_purchase_once(
            index,
            expected_name,
            expected_display_name,
            expected_price,
            before_remaining,
            before_currency,
        )

    def operation_siren_voucher_items(self):
        return self.open().oracle.operation_siren_voucher_items()

    def operation_siren_voucher_currency(self) -> int:
        return self.open().oracle.operation_siren_voucher_currency()

    def purchase_operation_siren_voucher_item_once(
        self,
        index: int,
        expected_name: str,
        expected_price: int,
        expected_currency: str = "Voucher",
    ) -> ActionReceipt:
        self.refresh_frame()
        return self.open().purchase_operation_siren_voucher_item_once(
            index,
            expected_name,
            expected_price,
            expected_currency,
        )

    def operation_siren_state(self) -> OperationSirenState:
        return self.open().operation_siren_state()

    def operation_siren_map_geometry(self, zone_name: str, *, rows: int, columns: int):
        return self.open().operation_siren_map_geometry(zone_name, rows=rows, columns=columns)

    def operation_siren_mission_entry_available(self) -> bool:
        return self.open().operation_siren_mission_entry_available()

    def operation_siren_stronghold_percentage(self) -> int:
        return self.open().operation_siren_stronghold_percentage()

    def operation_siren_auto_search_state(self) -> str:
        return self.open().operation_siren_auto_search_state()

    def operation_siren_strategic_search_state(self) -> str:
        return self.open().oracle.operation_siren_strategic_search_state()

    def start_operation_siren_strategic_search(self) -> Tuple[ActionReceipt, ...]:
        """Configure and start the reviewed secured-zone strategic search."""

        receipts: List[ActionReceipt] = []
        for _attempt in range(3):
            self.refresh_frame()
            oracle = self.open().oracle
            state = oracle.operation_siren_strategic_search_state()
            if state == "on":
                adapter = self.open()
                adapter._operation_siren_auto_search_transition_until = (
                    time.monotonic() + 30.0
                )
                adapter._operation_siren_auto_search_active = True
                adapter._operation_siren_startup_search_provisional = False
                adapter._operation_siren_auto_search_completed_empty = False
                return tuple(receipts)
            if state == "off":
                receipts.append(oracle.click("os/map/strategic-search/off"))
            for _ in range(24):
                time.sleep(0.25)
                self.refresh_frame()
                if (
                    self.open().oracle.operation_siren_strategic_search_state()
                    == "configuring"
                ):
                    break
            else:
                continue
            break
        else:
            raise SemanticGateClosed(
                "operation siren strategic-search popup did not open"
            )

        for semantic_id in (
            "os/strategic-search/tab/secured",
            "os/strategic-search/zone-mode/repeat",
            "os/strategic-search/merchant/stop",
            "os/strategic-search/device/stop",
            "os/strategic-search/auto-submit/on",
        ):
            selected = False
            for _attempt in range(3):
                self.refresh_frame()
                oracle = self.open().oracle
                toggle = oracle.toggle_state(semantic_id)
                if toggle.checked:
                    selected = True
                    break
                if (
                    semantic_id == "os/strategic-search/auto-submit/on"
                    and (
                        toggle.point is None
                        or not 0 <= toggle.point.x < oracle.fingerprint.width
                        or not 0 <= toggle.point.y < oracle.fingerprint.height
                    )
                ):
                    receipts.append(
                        oracle.operation_siren_strategic_search_scroll_to_bottom()
                    )
                    continue
                receipts.append(oracle.click_toggle(semantic_id))
                for _ in range(16):
                    time.sleep(0.25)
                    self.refresh_frame()
                    try:
                        if self.open().oracle.toggle_selected(semantic_id):
                            selected = True
                            break
                    except SemanticGateClosed:
                        continue
                if selected:
                    break
            if not selected:
                raise SemanticGateClosed(
                    "operation siren strategic-search option did not settle: "
                    + semantic_id
                )

        self.refresh_frame()
        oracle = self.open().oracle
        if oracle.operation_siren_strategic_search_state() != "configuring":
            raise SemanticGateClosed(
                "operation siren strategic-search popup disappeared before confirm"
            )
        receipts.append(oracle.click("os/strategic-search/confirm"))
        adapter = self.open()
        adapter._operation_siren_auto_search_transition_until = (
            time.monotonic() + 30.0
        )
        adapter._operation_siren_auto_search_active = True
        adapter._operation_siren_startup_search_provisional = False
        adapter._operation_siren_auto_search_completed_empty = False
        for _ in range(40):
            time.sleep(0.25)
            self.refresh_frame()
            try:
                if (
                    self.open().oracle.operation_siren_strategic_search_state()
                    == "on"
                ):
                    return tuple(receipts)
            except SemanticGateClosed:
                continue
        raise SemanticGateClosed(
            "operation siren strategic-search did not reach exact on state"
        )

    def begin_operation_siren_startup_recovery(
        self,
        timeout_seconds: float = 300.0,
    ) -> None:
        self.open().begin_operation_siren_startup_recovery(timeout_seconds)

    def begin_operation_siren_page_remount(
        self,
        timeout_seconds: float = 300.0,
    ) -> None:
        self.open().begin_operation_siren_page_remount(timeout_seconds)

    def end_operation_siren_page_remount(self) -> None:
        if self.adapter is not None:
            self.adapter.end_operation_siren_page_remount()

    def operation_siren_auto_search_transition_active(self) -> bool:
        return self.open().operation_siren_auto_search_transition_active()

    def operation_siren_auto_search_completed_empty(self) -> bool:
        return self.open().operation_siren_auto_search_completed_empty()

    def mark_operation_siren_auto_search_completed_empty(self) -> None:
        self.open().mark_operation_siren_auto_search_completed_empty()

    def operation_siren_auto_search_info_count(self) -> int:
        return self.open().operation_siren_auto_search_info_count()

    def operation_siren_current_fleet(self) -> int:
        return self.open().operation_siren_current_fleet()

    def operation_siren_current_fleet_defeated(self) -> bool:
        return self.open().operation_siren_current_fleet_defeated()

    def operation_siren_fleet_already_defeated(self, fleet: int) -> bool:
        return self.open().operation_siren_fleet_already_defeated(fleet)

    def operation_siren_current_fleet_needs_repair(self) -> bool:
        return self.open().operation_siren_current_fleet_needs_repair()

    def operation_siren_low_resolve_prompt_visible(self) -> bool:
        return self.open().operation_siren_low_resolve_prompt_visible()

    def click_operation_siren_low_resolve_cancel(self) -> ActionReceipt:
        self.refresh_frame()
        return self.open().click_operation_siren_low_resolve_cancel()

    def operation_siren_battle_result_visible(self) -> bool:
        return self.open().operation_siren_battle_result_visible()

    def operation_siren_battle_result_grade(self) -> str:
        return self.open().operation_siren_battle_result_grade()

    def click_operation_siren_battle_result(self) -> ActionReceipt:
        self.refresh_frame()
        return self.open().click_operation_siren_battle_result()

    def operation_siren_reward_visible(self) -> bool:
        return self.open().operation_siren_reward_visible()

    def click_operation_siren_reward_close(self) -> ActionReceipt:
        self.refresh_frame()
        adapter = self.open()
        with adapter.prepared_input_frame(adapter._require_frame_observation_oracle):
            return adapter.click_operation_siren_reward_close()

    def try_click_operation_siren_reward_close(self) -> Optional[ActionReceipt]:
        """Atomically re-observe and close, or accept a passive unmount."""

        self.refresh_frame()
        adapter = self.open()
        with adapter.prepared_input_frame(adapter._require_frame_observation_oracle):
            return adapter.try_click_operation_siren_reward_close()

    def operation_siren_radar_targets(
        self, target_kind: str
    ) -> Tuple[Tuple[int, int], ...]:
        return self.open().operation_siren_radar_targets(target_kind)

    def operation_siren_month_boss_room_difficulty(self) -> str:
        return self.open().operation_siren_month_boss_room_difficulty()

    def click_operation_siren_radar_boss(
        self, relative_position: Tuple[int, int]
    ) -> ActionReceipt:
        return self.open().click_operation_siren_radar_boss(relative_position)

    def click_operation_siren_radar_guidepost(
        self, relative_position: Tuple[int, int]
    ) -> ActionReceipt:
        return self.open().click_operation_siren_radar_guidepost(
            relative_position
        )

    def operation_siren_obscure_exit_passage_position(
        self,
    ) -> Optional[Tuple[int, int]]:
        return self.open().operation_siren_obscure_exit_passage_position()

    def operation_siren_post_search_loot_visible(self) -> bool:
        return self.open().operation_siren_post_search_loot_visible()

    def click_operation_siren_post_search_loot_back(self) -> ActionReceipt:
        return self.open().click_operation_siren_post_search_loot_back()

    def operation_siren_obscure_exit_camera_swipe(
        self,
    ) -> OperationSirenGlobeSwipeReceipt:
        return self.open().operation_siren_obscure_exit_camera_swipe()

    def click_operation_siren_obscure_exit_passage(self) -> ActionReceipt:
        return self.open().click_operation_siren_obscure_exit_passage()

    def operation_siren_abyssal_exit_available(self) -> bool:
        return self.open().operation_siren_abyssal_exit_available()

    def click_operation_siren_abyssal_exit(self) -> ActionReceipt:
        return self.open().click_operation_siren_abyssal_exit()

    def click_operation_siren_relative_grid(
        self,
        relative_position: Tuple[int, int],
        *,
        prefer_adjacent_event: bool = False,
        fleet_relative: bool = False,
    ) -> ActionReceipt:
        return self.open().click_operation_siren_relative_grid(
            relative_position,
            prefer_adjacent_event=prefer_adjacent_event,
            fleet_relative=fleet_relative,
        )

    def operation_siren_daemon_move_allowed(self) -> bool:
        return self.open().operation_siren_daemon_move_allowed()

    def operation_siren_nearest_daemon_target(
        self,
    ) -> Optional[OperationSirenDaemonTarget]:
        return self.open().operation_siren_nearest_daemon_target()

    def click_operation_siren_daemon_target(
        self, expected: OperationSirenDaemonTarget
    ) -> ActionReceipt:
        return self.open().click_operation_siren_daemon_target(expected)

    def click_operation_siren_fleet_bar(self) -> ActionReceipt:
        return self.open().click_operation_siren_fleet_bar()

    def operation_siren_fleet_selector_open(self) -> bool:
        return self.open().operation_siren_fleet_selector_open()

    def click_operation_siren_fleet_selector(
        self, fleet_index: int
    ) -> ActionReceipt:
        return self.open().click_operation_siren_fleet_selector(fleet_index)

    def click_operation_siren_globe_zone_enter(self, expected_zone_name=None) -> ActionReceipt:
        return self.open().click_operation_siren_globe_zone_enter(expected_zone_name)

    def operation_siren_map_visible(self) -> bool:
        return self.open().operation_siren_map_visible()

    def operation_siren_globe_state(self) -> OperationSirenGlobeState:
        return self.open().operation_siren_globe_state()

    def operation_siren_globe_visible(self) -> bool:
        return self.open().operation_siren_globe_visible()

    def operation_siren_globe_unpin(self) -> OperationSirenGlobeSwipeReceipt:
        return self.open().operation_siren_globe_unpin()

    def operation_siren_storage_visible(self) -> bool:
        return self.open().operation_siren_storage_visible()

    def operation_siren_storage_state(self) -> OperationSirenStorageState:
        return self.open().operation_siren_storage_state()

    def operation_siren_sample_buttons(self, template_name):
        self.open()._package_gate()
        return self.open()._frame_or_live_observation_oracle().operation_siren_sample_buttons(template_name)

    def operation_siren_sample_use(self, selected):
        from ...opsi_monthstart import sample_use
        return sample_use(self, selected)

    def click_operation_siren_storage_item(self, item_type: str) -> ActionReceipt:
        return self.open().click_operation_siren_storage_item(item_type)

    def operation_siren_storage_scroll_for_abyssal(
        self,
    ) -> Optional[OperationSirenStorageScrollReceipt]:
        return self.open().operation_siren_storage_scroll_for_abyssal()

    def click_operation_siren_storage_back(self) -> ActionReceipt:
        return self.open().click_operation_siren_storage_back()

    def operation_siren_storage_detail(self) -> Optional[Tuple[str, str, int]]:
        return self.open().operation_siren_storage_detail()

    def click_operation_siren_storage_detail_close(self) -> ActionReceipt:
        return self.open().click_operation_siren_storage_detail_close()

    def operation_siren_coordinate_checkout_allowed(self) -> bool:
        return self.open().operation_siren_coordinate_checkout_allowed()

    def click_operation_siren_storage_detail_checkout(self) -> ActionReceipt:
        return self.open().click_operation_siren_storage_detail_checkout()

    def operation_siren_storage_checkout_prompt_visible(self) -> bool:
        return self.open().operation_siren_storage_checkout_prompt_visible()

    def click_operation_siren_storage_checkout_confirm(self) -> ActionReceipt:
        return self.open().click_operation_siren_storage_checkout_confirm()

    def operation_siren_map_exit_prompt_visible(self) -> bool:
        return self.open().operation_siren_map_exit_prompt_visible()

    def click_operation_siren_map_exit_confirm(self) -> ActionReceipt:
        return self.open().click_operation_siren_map_exit_confirm()

    def try_click_operation_siren_map_exit_confirm(
        self,
    ) -> Optional[ActionReceipt]:
        return self.open().try_click_operation_siren_map_exit_confirm()

    def operation_siren_globe_port_projection(self, zone_id: int):
        return self.open().operation_siren_globe_port_projection(zone_id)

    def operation_siren_globe_drag_owned(self, start, end):
        return self.open().operation_siren_globe_drag_owned(start,end)

    def operation_siren_globe_map_projection(self, area_pos):
        return self.open().operation_siren_globe_map_projection(area_pos)

    def click_operation_siren_globe_map_zone(self, expected_zone_name, area_pos):
        # Native projection/focus follows a swipe or a passive wait. Refresh
        # its input lease before recomputing the full current zone proof;
        # never dispatch from the invalidated navigation screenshot.
        self.refresh_frame()
        return self.open().click_operation_siren_globe_map_zone(expected_zone_name, area_pos)

    def click_operation_siren_globe_port(self, expected_zone_name: str, zone_id: int, *, native_mask=False) -> ActionReceipt:
        if native_mask:
            return self.open().click_operation_siren_globe_port(expected_zone_name, zone_id, native_mask=True)
        return self.open().click_operation_siren_globe_port(expected_zone_name, zone_id)

    def click_operation_siren_globe_zone(
        self, expected_zone_name: str, point: Tuple[float, float]
    ) -> ActionReceipt:
        return self.open().click_operation_siren_globe_zone(
            expected_zone_name, point
        )

    def click_operation_siren_globe_zone_switch(self) -> ActionReceipt:
        return self.open().click_operation_siren_globe_zone_switch()

    def operation_siren_globe_zone_types(self) -> Tuple[str, ...]:
        return self.open().operation_siren_globe_zone_types()

    def click_operation_siren_globe_zone_type(
        self, expected_type: str
    ) -> ActionReceipt:
        return self.open().click_operation_siren_globe_zone_type(expected_type)

    def operation_siren_need_repair(self) -> Tuple[bool, ...]:
        return self.open().operation_siren_need_repair()

    def operation_siren_action_point_state(
        self,
    ) -> OperationSirenActionPointState:
        return self.open().operation_siren_action_point_state()

    def operation_siren_action_point_visible(self) -> bool:
        return self.open().operation_siren_action_point_visible()

    def click_operation_siren_action_point_open(self) -> ActionReceipt:
        receipt = None
        for _attempt in range(3):
            self.refresh_frame()
            if receipt is not None:
                try:
                    self.open().operation_siren_action_point_state()
                    return receipt
                except SemanticGateClosed:
                    pass
            receipt = self.open().click_operation_siren_action_point_open()
            for _ in range(16):
                time.sleep(0.25)
                self.refresh_frame()
                try:
                    self.open().operation_siren_action_point_state()
                    return receipt
                except SemanticGateClosed:
                    continue
        raise SemanticGateClosed("operation siren action point panel did not open")

    def click_operation_siren_action_point_item(
        self, item_index: int
    ) -> ActionReceipt:
        return self.open().click_operation_siren_action_point_item(item_index)

    def click_operation_siren_action_point_control(
        self, use: bool
    ) -> ActionReceipt:
        self.refresh_frame()
        adapter = self.open()
        with adapter.prepared_input_frame(adapter._require_frame_observation_oracle):
            receipt = adapter.click_operation_siren_action_point_control(use)
        if use:
            self.refresh_frame()
            return receipt
        for _ in range(16):
            time.sleep(0.25)
            self.refresh_frame()
            adapter = self.open()
            if not adapter.operation_siren_action_point_visible():
                if adapter.oracle.operation_siren_local_map_visible():
                    return receipt
                if adapter.oracle.operation_siren_globe_visible():
                    return receipt
        raise SemanticGateClosed("operation siren action point panel did not close")

    def operation_siren_action_point_use_allowed(self) -> bool:
        return self.open().operation_siren_action_point_use_allowed()

    def operation_siren_port_repair_cost(self) -> Optional[int]:
        return self.open().operation_siren_port_repair_cost()

    def click_operation_siren_port_repair(
        self, confirm: bool
    ) -> ActionReceipt:
        return self.open().click_operation_siren_port_repair(confirm)

    def operation_siren_port_repair_allowed(self) -> bool:
        return self.open().operation_siren_port_repair_allowed()

    def operation_siren_low_resolve_visible(self) -> bool:
        return self.open().operation_siren_low_resolve_visible()

    def begin_operation_siren_globe_swipe_vector(
        self, vector: Any, **kwargs: Any
    ) -> _OperationSirenGlobeSwipeIntent:
        return self.open().begin_operation_siren_globe_swipe_vector(
            vector, **kwargs
        )

    def end_operation_siren_globe_swipe_vector(
        self, intent: _OperationSirenGlobeSwipeIntent
    ) -> None:
        self.open().end_operation_siren_globe_swipe_vector(intent)
