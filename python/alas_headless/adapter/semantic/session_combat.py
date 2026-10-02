"""Session combat for the typed ALAS boundary."""

from __future__ import annotations

import time
from dataclasses import replace
from pathlib import Path
from typing import Any, List, Optional, Tuple
from ...adapter import StaleFrameError
from ...alas_combat_action import commit_alas_combat_resource_action_for_evidence
from ...alas_combat_admission import (
    AlasCampaignCombatAdmission,
    AlasCampaignCombatProof,
)
from ...alas_combat_observer import (
    AlasCombatObserverManifest,
    alas_combat_visible_resource_names,
    load_alas_combat_observer_manifest,
)
from ...alas_combat_state_replay import ALAS_COMBAT_RESOURCE_ACTION_TARGETS
from ...alas_combat_trace import build_alas_combat_trace_frame
from ...alas_decision_preview import AlasCampaignDecisionPreview
from ...semantic_oracle import (
    ActionReceipt,
    CampaignMapState,
    ObserverTransportError,
    SemanticGateClosed,
    request_observer_state,
)
from .adapter import AlasSemanticAdapter
from .contracts import CampaignMapTargetRecheckProof


class SessionCombatPorts:
    """Session combat on the shared immutable frame."""

    def _live_combat_manifest(self) -> AlasCombatObserverManifest:
        if self._combat_manifest is None:
            path = (
                Path(__file__).resolve().parents[4]
                / "integration"
                / "alas"
                / "combat-observer-manifest.json"
            )
            manifest = load_alas_combat_observer_manifest(path)
            if manifest.driver_revision != self.driver_revision:
                compatibility = (
                    manifest.driver_revision,
                    self.driver_revision,
                )
                if compatibility not in self._LIVE_COMBAT_DRIVER_COMPATIBILITY:
                    raise SemanticGateClosed(
                        "combat observer manifest is not qualified for the "
                        "active driver revision"
                    )
                # 506b is the reviewed image-capacity successor of the G27
                # driver.  It retains the endpoint schemas and Unity selector
                # contract, while increasing the rolling image reserve needed
                # by large Operation Siren maps.  Rebind only this exact,
                # checked compatibility edge so raw endpoint identity remains
                # pinned to the active runtime below.
                manifest = replace(
                    manifest,
                    driver_revision=self.driver_revision,
                )
            self._combat_manifest = manifest
        return self._combat_manifest

    def _live_combat_snapshot(self) -> Any:
        adapter = self.open()
        if not (
            adapter.campaign_combat_committed()
            or adapter.operation_siren_combat_committed()
        ):
            raise SemanticGateClosed(
                "live combat observation requires one committed ALAS grid input"
            )
        handle = self._runtime_handle
        if handle is None:
            raise SemanticGateClosed("semantic runtime handle is unavailable")
        snapshot_payload, button_payload, _ = request_observer_state(
            handle.observer_request
        )
        ui_payload = handle.observer_request("GET /v1/ui\n")
        _, snapshot = build_alas_combat_trace_frame(
            snapshot_payload,
            button_payload,
            ui_payload,
            self._live_combat_manifest(),
        )
        return snapshot

    def _live_combat_visible(self) -> Tuple[str, ...]:
        try:
            return alas_combat_visible_resource_names(
                self._live_combat_snapshot(), self._live_combat_manifest()
            )
        except SemanticGateClosed as exc:
            adapter = self.open()
            result_path = ('OverlayCamera/Overlay/UIMain/NewBattleResultEmptyUI(Clone)/'
                           'NewBattleResultStatisticsPage(Clone)/bottom/confirmBtn')
            if (adapter.meta_beacon_active() and str(exc) ==
                    'combat action control is not exact top-raycast actionable: '
                    + result_path + ', raycast_top=False'):
                state = adapter.oracle.read_state()
                results = [b for b in state.buttons if b.path == result_path]
                if (len(results) == 1 and results[0].active_in_hierarchy
                        and results[0].active_and_enabled
                        and results[0].raycast_top is False
                        and results[0].point is not None and results[0].bounds is not None
                        and results[0].bounds.contains(results[0].point)):
                    # A covered/mounting statistics control is absent for this
                    # passive poll. The original loop waits; input still needs
                    # the independent actionable result proof.
                    return ()
                if len(results) == 1 and results[0].actionable:
                    return alas_combat_visible_resource_names(
                        self._live_combat_snapshot(), self._live_combat_manifest()
                    )
                if not results and adapter.oracle.meta_page_visible():
                    return ()
            raise

    def _campaign_combat_transition_error(self, exc: Exception) -> bool:
        adapter = self.adapter
        context = None if adapter is None else adapter._campaign_context
        message = str(exc)
        transient_observer_read = bool(
            message.startswith(
                "combat action control is not exact top-raycast actionable:"
            )
            or message
            in (
                "observer snapshot is stale",
                "observer endpoints are not generation-coherent",
                "campaign startup surface is not reviewed",
                "combat fixture endpoint completeness changed",
                "combat fixture endpoint generations disagree",
            )
        )
        return bool(
            transient_observer_read
            and context is not None
            and adapter.campaign_combat_committed()
            and time.monotonic() <= context.passive_transition_until
        )

    def _operation_siren_combat_observer_gap(self, exc: Exception) -> bool:
        adapter = self.adapter
        committed = getattr(
            adapter, "operation_siren_combat_committed", lambda: False
        )
        if adapter is None or not committed():
            return False
        if isinstance(exc, (StaleFrameError, ObserverTransportError)):
            return True
        return str(exc) in self._OPERATION_SIREN_COMBAT_OBSERVER_GAP_MESSAGES

    def campaign_is_in_map_after_combat(self) -> Optional[bool]:
        """Return map presence, or ``None`` for one bounded mount gap."""

        adapter = self.open()
        try:
            return adapter.oracle.campaign_is_in_map()
        except SemanticGateClosed as exc:
            if self._campaign_combat_transition_error(exc):
                return None
            raise

    def combat_is_loading(self) -> bool:
        adapter = self.open()
        oracle = adapter.oracle
        if getattr(
            oracle,
            "daily_battle_result_visible",
            lambda: False,
        )():
            return False
        if oracle.daily_combat_visible():
            return True
        if adapter.campaign_combat_committed():
            try:
                if not oracle.campaign_is_in_map():
                    return True
            except SemanticGateClosed as exc:
                if self._campaign_combat_transition_error(exc):
                    return True
                raise
        if not (
            adapter.campaign_combat_committed()
            or adapter.operation_siren_combat_committed()
        ):
            return False
        try:
            visible = set(self._live_combat_visible())
        except (SemanticGateClosed, StaleFrameError, ObserverTransportError) as exc:
            if (
                isinstance(exc, SemanticGateClosed)
                and self._campaign_combat_transition_error(exc)
            ):
                # The target grid input is committed and ChapterPreCombatUI
                # exists, but its start control is still mounting. Report the
                # bounded state as loading so ALAS enters its own preparation
                # loop instead of re-reading the covered map underneath it.
                return True
            if self._operation_siren_combat_observer_gap(exc):
                # Month-boss CombatLoadUI and long boss effects can stall
                # observer completeness before PAUSE is published. Keep the
                # original ALAS loading loop instead of aborting the battle.
                return True
            raise
        return bool(
            visible.intersection(
                {
                    "AUTOMATION_CONFIRM_CHECK",
                    "BATTLE_PREPARATION",
                    "BATTLE_PREPARATION_WITH_OVERLAY",
                    "PAUSE",
                }
            )
        )

    def combat_is_executing(self) -> bool:
        try:
            adapter = self.open()
            if getattr(adapter, "_exercise_execution_active", False):
                # Exercise's native HP daemon follows the pause probe from
                # this screenshot. Both observations must use its immutable
                # frame even if the live client has entered result loading.
                return adapter._frame_or_live_observation_oracle().daily_combat_visible()
            if getattr(
                self.open().oracle,
                "daily_battle_result_visible",
                lambda: False,
            )():
                return False
            if self.open().oracle.daily_combat_visible():
                return True
            if not (
                self.open().campaign_combat_committed()
                or self.open().operation_siren_combat_committed()
            ):
                return False
            return "PAUSE" in self._live_combat_visible()
        except (SemanticGateClosed, StaleFrameError, ObserverTransportError) as exc:
            if (
                isinstance(exc, SemanticGateClosed)
                and self._campaign_combat_transition_error(exc)
            ):
                return False
            if self._operation_siren_combat_observer_gap(exc):
                # Unity can stop publishing fresh hierarchy snapshots during
                # long Operation Siren boss effects.  The committed battle is
                # still executing until a fresh typed result/map surface says
                # otherwise; do not abort the owning combat loop on that gap.
                return True
            raise

    def combat_enemy_searching(self) -> bool:
        if not self.open().campaign_combat_committed():
            return False
        return "MAP_ENEMY_SEARCHING" in self._live_combat_visible()

    def _live_combat_click(
        self,
        resource_name: str,
        *,
        action_name: Optional[str] = None,
    ) -> ActionReceipt:
        adapter = self.open()
        if not (
            adapter.campaign_combat_committed()
            or adapter.operation_siren_combat_committed()
        ):
            raise SemanticGateClosed(
                "live combat input requires one committed ALAS grid input"
            )
        if adapter.meta_beacon_active() and resource_name == 'BATTLE_STATUS_S':
            # META's shared grade/Worldboss statistics stack has a reviewed
            # typed result port; its artwork is not the campaign grade asset.
            self.refresh_tactical_input_frame()
            oracle = self.open().oracle
            receipt = oracle.click_daily_battle_result()
            self._combat_last_generation = receipt.generation
            self._combat_last_result_receipt = receipt
            self._arm_combat_result_transition(adapter)
            return receipt
        handle = self._runtime_handle
        if handle is None:
            raise SemanticGateClosed("semantic runtime handle is unavailable")
        targets = ALAS_COMBAT_RESOURCE_ACTION_TARGETS.get(resource_name, ())
        if action_name is None and resource_name in targets:
            action_name = resource_name
        commit = commit_alas_combat_resource_action_for_evidence(
            self,
            self._live_combat_manifest(),
            resource_name,
            action_name=action_name,
            expected_pid=handle.pid,
            minimum_generation=self._combat_last_generation,
            action_budget=1,
        )
        self._combat_last_generation = commit.commit_generation
        if commit.action_name in ("AUTOMATION_SWITCH", "BATTLE_PREPARATION"):
            context = adapter._campaign_context
            if context is not None:
                transition_seconds = (
                    12.0
                    if commit.action_name == "AUTOMATION_SWITCH"
                    else 30.0
                )
                context.passive_transition_until = max(
                    context.passive_transition_until,
                    time.monotonic() + transition_seconds,
                )
        if commit.action_name in (
            "BATTLE_STATUS_S",
            "GET_ITEMS_1",
            "GET_ITEMS_1_RETIREMENT_SAVE",
            "EXP_INFO_S",
        ):
            self._combat_last_result_receipt = commit.receipt
            self._arm_combat_result_transition(adapter)
        return commit.receipt

    def _arm_combat_result_transition(
        self,
        adapter: AlasSemanticAdapter,
        transition_seconds: float = 12.0,
    ) -> None:
        """Allow only the brief observer gap after an exact result action."""

        deadline = time.monotonic() + transition_seconds
        self._combat_result_transition_until = max(
            self._combat_result_transition_until,
            deadline,
        )
        context = adapter._campaign_context
        if context is not None:
            context.passive_transition_until = max(
                context.passive_transition_until,
                deadline,
            )

    def _click_live_combat_automation_switch(self) -> ActionReceipt:
        resource_name = self._combat_automation_source
        if resource_name not in ("AUTOMATION_OFF", "AUTOMATION_ON"):
            raise SemanticGateClosed(
                "combat automation switch requires a preceding exact state probe"
            )
        try:
            return self._live_combat_click(
                resource_name,
                action_name="AUTOMATION_SWITCH",
            )
        finally:
            # The action commit revalidates the same source resource on two
            # increasing snapshots. Never reuse that prior ALAS observation
            # for a second toggle, whether the commit succeeds or fails.
            self._combat_automation_source = None

    def operation_siren_precombat_visible(self) -> bool:
        return self.open().operation_siren_precombat_visible()

    def operation_siren_precombat_info_visible(self) -> bool:
        return self.open().operation_siren_precombat_info_visible()

    def click_operation_siren_precombat_info(self) -> ActionReceipt:
        return self.open().click_operation_siren_precombat_info()

    def click_operation_siren_precombat_start(self) -> ActionReceipt:
        return self.open().click_operation_siren_precombat_start()

    def operation_siren_combat_committed(self) -> bool:
        return self.open().operation_siren_combat_committed()

    def handle_operation_siren_combat_interrupt(self) -> bool:
        """Advance one exact pause/leave/confirm step during task handoff."""

        adapter = self.open()
        if not adapter.operation_siren_combat_committed():
            return False
        oracle = adapter.oracle
        if oracle.exercise_combat_quit_confirm_visible():
            oracle.click_exercise_combat_quit_confirm()
            return True
        if oracle.exercise_combat_pause_menu_visible():
            oracle.click_exercise_combat_leave()
            return True
        if oracle.combat_pause_visible():
            oracle.click_combat_pause()
            return True
        return False

    def begin_operation_siren_boss_combat(self) -> None:
        self.open().begin_operation_siren_boss_combat()

    def mark_operation_siren_combat_fleet_defeated(self) -> None:
        self.open().mark_operation_siren_combat_fleet_defeated()

    def meta_precombat_visible(self) -> bool:
        return self.open().meta_precombat_visible()

    def click_meta_precombat_start(self) -> ActionReceipt:
        return self.open().click_meta_precombat_start()

    def click_meta_precombat_back(self) -> ActionReceipt:
        return self.open().click_meta_precombat_back()

    def authorize_campaign_combat(
        self,
        decision: AlasCampaignDecisionPreview,
        state: CampaignMapState,
    ) -> Optional[AlasCampaignCombatAdmission]:
        return self.open().authorize_campaign_combat(decision, state)

    def campaign_combat_committed(self) -> bool:
        return self.open().campaign_combat_committed()

    def campaign_movement_completed(self) -> bool:
        return self.open().campaign_movement_completed()

    def finish_campaign_movement(self, battle_count: int):
        return self.open().finish_campaign_movement(battle_count)

    def campaign_combat_active(self) -> bool:
        return self.open().campaign_combat_active()

    def confirm_campaign_combat(
        self,
        battle_count_after: int,
    ) -> AlasCampaignCombatProof:
        return self.open().confirm_campaign_combat(battle_count_after)

    def complete_campaign_combat_round(
        self,
        battle_count_after: int,
    ) -> Optional[AlasCampaignCombatProof]:
        return self.open().complete_campaign_combat_round(battle_count_after)

    def campaign_post_combat_arrived(self, location: Any) -> bool:
        return self.open().campaign_post_combat_arrived(location)

    def recheck_campaign_combat_target_after_camera_view(
        self, state: CampaignMapState
    ) -> CampaignMapTargetRecheckProof:
        return self.open().recheck_campaign_combat_target_after_camera_view(
            state
        )

    def _combat_result_action_oracle(
        self, adapter: AlasSemanticAdapter
    ) -> Any:
        """Return a current immutable frame oracle for one result action."""

        if not isinstance(adapter, AlasSemanticAdapter):
            return adapter.oracle
        try:
            frame_clock = self._frame_clock
            if frame_clock is not None:
                frame_clock.borrow(require_fresh=True)
            return adapter._require_frame_observation_oracle()
        except StaleFrameError:
            # Some ALAS result handlers probe the next overlay immediately
            # after the previous exact click, before their loop takes another
            # screenshot. That prior click intentionally invalidated its
            # lease; acquire a new immutable frame and re-prove the next exact
            # target instead of extending or reusing the expired lease.
            self.refresh_frame()
            return adapter._require_frame_observation_oracle()

    def daily_precombat_visible(self) -> bool:
        return self.open().daily_precombat_visible()

    def click_daily_precombat_start(self) -> ActionReceipt:
        self.refresh_tactical_input_frame()
        adapter = self.open()
        if getattr(self, '_meta_assist_active', False):
            if not adapter._meta_assist_active:
                adapter.begin_meta_assist()
            return adapter.click_meta_precombat_start()
        if self._meta_beacon_active:
            if not adapter.meta_beacon_active():
                adapter.begin_meta_beacon()
            return adapter.click_meta_precombat_start()
        return adapter.click_daily_precombat_start()

    def orphan_combat_result_visible(self) -> bool:
        """Detect an exact result stack that has no surviving task owner."""

        adapter = self.open()
        if (
            adapter.daily_execution_active()
            or adapter.campaign_combat_committed()
            or adapter.operation_siren_combat_committed()
            or getattr(adapter, "_exercise_execution_active", False)
        ):
            return False
        oracle = adapter.oracle
        return bool(
            oracle.daily_battle_result_visible()
            or oracle.campaign_battle_reward_visible()
        )

    def recover_orphan_combat_result(
        self,
        timeout_seconds: float = 45.0,
        current_raid_event: Optional[str] = None,
    ) -> Tuple[ActionReceipt, ...]:
        """Drain one exact ownerless result stack to a reviewed stable page."""

        if not self.orphan_combat_result_visible():
            raise SemanticGateClosed("orphan combat result is absent")
        deadline = time.monotonic() + timeout_seconds
        self._combat_result_transition_until = max(
            self._combat_result_transition_until,
            deadline,
        )
        receipts: List[ActionReceipt] = []
        while time.monotonic() < deadline:
            self.refresh_frame()
            adapter = self.open()
            oracle = adapter._require_frame_observation_oracle()
            if oracle.daily_battle_result_visible():
                receipts.append(oracle.click_daily_battle_result())
                time.sleep(0.75)
                continue
            if oracle.campaign_battle_reward_visible():
                target = (
                    "reward/award-info/close"
                    if oracle.enabled("reward/award-info/close")
                    else "reward/award-info1/close"
                )
                receipts.append(oracle.click(target))
                time.sleep(0.75)
                continue
            if (
                oracle.operation_siren_page_visible()
                or oracle.daily_page_visible()
                or oracle.main_page_visible()
                or oracle.event_campaign_page_visible()
                or (adapter.meta_beacon_active() and oracle.meta_page_visible())
            ):
                return tuple(receipts)
            if current_raid_event is not None:
                try:
                    if oracle.raid_page_visible(current_raid_event):
                        return tuple(receipts)
                except SemanticGateClosed as exc:
                    if str(exc) not in {
                        "current Raid stage identity is absent or ambiguous",
                        "current Raid stage sprites are absent or ambiguous",
                        "current Raid stage sprite does not cover its button",
                    }:
                        raise
            try:
                if oracle.campaign_is_in_map():
                    return tuple(receipts)
            except SemanticGateClosed as exc:
                if str(exc) not in {
                    "campaign startup surface is not reviewed",
                    "campaign map-scene identity is absent",
                }:
                    raise
            time.sleep(0.25)
        raise SemanticGateClosed(
            "orphan combat result did not return to a reviewed stable page"
        )

    def click_daily_precombat_back(self) -> ActionReceipt:
        self.refresh_frame()
        return self.open().click_daily_precombat_back()

    def raid_precombat_visible(self, event: str) -> bool:
        return self.open().raid_precombat_visible(event=event)

    def raid_precombat_multiple_visible(self, event: str) -> bool:
        return self.open().raid_precombat_multiple_visible(event=event)

    def click_raid_precombat_multiple(self, event: str) -> ActionReceipt:
        return self.open().click_raid_precombat_multiple(event=event)

    def raid_precombat_notice_visible(self, event: str) -> bool:
        return self.open().raid_precombat_notice_visible(event=event)

    def click_raid_precombat_notice(self, event: str) -> ActionReceipt:
        return self.open().click_raid_precombat_notice(event=event)

    def click_raid_precombat_start(self, event: str) -> ActionReceipt:
        return self.open().click_raid_precombat_start(event=event)

    def click_raid_precombat_back(self, event: str) -> ActionReceipt:
        return self.open().click_raid_precombat_back(event=event)
