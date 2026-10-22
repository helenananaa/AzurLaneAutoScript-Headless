"""Opsi for the typed ALAS boundary."""

from __future__ import annotations

import math
from numbers import Real
import re
import time
from dataclasses import replace
from typing import Any, Optional, Tuple
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
    SemanticTargetMissing,
)
from .contracts import _OperationSirenGlobeSwipeIntent, AlasSemanticActionDeferred, AlasSemanticUnmapped
from .dispatch_result import UNHANDLED
from ...oracle.opsi_map import OperationSirenMapSwipeIntent
from ...oracle.opsi_map import reviewed_logging_tower, reviewed_scanning_device
from ...oracle.contracts import Point


class OpsiAdapterPorts:
    """Opsi ports on the shared adapter context."""

    @staticmethod
    def _operation_siren_camera_grid(button):
        return (getattr(button, 'semantic_os_cell', None) is not None
                and (getattr(button, 'is_logging_tower', False) is True
                     or getattr(button, 'is_scanning_device', False) is True))

    def click_operation_siren_camera_grid(self, grid):
        """Adapt original reviewed map-event clicks, preserving native wait loops."""
        self._package_gate()
        cell = getattr(grid, 'semantic_os_cell', None)
        dimensions = getattr(grid, 'semantic_os_dimensions', None)
        if (not isinstance(cell, tuple) or len(cell) != 2
                or any(type(v) is not int or v < 0 for v in cell)
                or not isinstance(dimensions, tuple) or len(dimensions) != 2
                or not self._operation_siren_camera_grid(grid)):
            raise SemanticGateClosed('operation siren camera grid has no reviewed event input')
        state = self.oracle.operation_siren_map_geometry(
            getattr(grid, 'semantic_os_zone', None), rows=dimensions[0], columns=dimensions[1])
        targets = [c for c in state.cells if (c.column-1, c.row-1) == cell]
        attachments = [a for a in state.attachments if (a.column-1, a.row-1) == cell]
        reviewed_event = (reviewed_logging_tower if getattr(grid, 'is_logging_tower', False) is True
                          else reviewed_scanning_device)
        if (len(targets) != 1 or targets[0].button_path != getattr(grid, 'semantic_path', None)
                or len(attachments) != 1 or not reviewed_event(attachments[0])):
            raise SemanticGateClosed('operation siren camera event identity changed before input')
        centers = [c for c in state.cells if c.bounds.contains(Point(640.0, 360.0))]
        if len(centers) != 1:
            raise SemanticGateClosed('operation siren camera center is absent or ambiguous')
        target, center = targets[0], centers[0]
        return self.oracle.click_operation_siren_relative_grid(
            (target.column-center.column, target.row-center.row), expected_path=target.button_path)

    def operation_siren_map_geometry(self, zone_name: str, *, rows: int, columns: int):
        self._package_gate()
        state = self._frame_or_live_observation_oracle().operation_siren_map_geometry(
            zone_name, rows=rows, columns=columns)
        self._operation_siren_camera_geometry = state
        return state

    def operation_siren_map_swipe_owned(self):
        return (self._campaign_context is None and self._operation_siren_camera_geometry is not None
                and self._operation_siren_allows_passive_probe())

    def begin_operation_siren_map_swipe_vector(self, vector, *, box, random_range, padding,
            duration, whitelist_area, blacklist_area, name, distance_check):
        self._package_gate()
        if not self.operation_siren_map_swipe_owned() or self._operation_siren_map_swipe_intent is not None:
            raise SemanticGateClosed('operation siren camera swipe is not owned or already armed')
        if not isinstance(name,str) or re.fullmatch(r'MAP_SWIPE_-?[0-9]+_-?[0-9]+',name) is None:
            raise SemanticGateClosed('operation siren camera gesture name is malformed')
        vector=self._campaign_swipe_pair(vector,'operation siren camera vector')
        bounds=self._campaign_swipe_box(box,'operation siren camera box')
        timing=self._campaign_swipe_pair(duration,'operation siren camera duration')
        self._campaign_swipe_areas(whitelist_area,'operation siren preferred areas')
        blacklist=self._campaign_swipe_areas(blacklist_area,'operation siren forbidden areas')
        # Padding chooses the original sampler's placement, not the input
        # target. Final endpoints still must match this intent, remain in its
        # box and pass the Oracle's fresh typed drag/movement proof. Likewise,
        # keep the original call's duration range instead of a baseline tuple.
        if (isinstance(padding,bool) or not isinstance(padding,Real)
                or not math.isfinite(padding) or padding<0
                or not 0<timing[0]<=timing[1]):
            raise SemanticGateClosed('operation siren camera selection arguments are malformed')
        if not 0<=bounds[0]<bounds[2]<=1280 or not 0<=bounds[1]<bounds[3]<=720:
            raise SemanticGateClosed('operation siren camera box left the semantic screen')
        if tuple(random_range)!=(0,0,0,0) or distance_check is not True:
            # These sampler modes need a different final-vector relationship.
            # No input has occurred; defer only this port's task until its mode
            # is understood, rather than terminating unrelated native tasks.
            raise AlasSemanticUnmapped('operation siren camera sampler mode is unsupported')
        intent=OperationSirenMapSwipeIntent(name,vector,bounds,timing,self._operation_siren_camera_geometry,blacklist)
        self._operation_siren_map_swipe_intent=intent
        return intent

    def end_operation_siren_map_swipe_vector(self,intent):
        if self._operation_siren_map_swipe_intent is not intent:
            raise SemanticGateClosed('operation siren camera swipe token changed')
        self._operation_siren_map_swipe_intent=None

    def _dispatch_operation_siren_map_swipe(self,p1,p2,*,duration,name,distance_check):
        intent=self._operation_siren_map_swipe_intent
        if intent is None or name!=intent.name or distance_check is not True:
            raise SemanticGateClosed('operation siren camera swipe final arguments changed')
        start=self._campaign_swipe_pair(p1,'operation siren camera start')
        end=self._campaign_swipe_pair(p2,'operation siren camera end')
        if any(not v.is_integer() for v in (*start,*end)):
            raise SemanticGateClosed('operation siren camera endpoints are not integral')
        start=tuple(map(int,start));end=tuple(map(int,end))
        left,top,right,bottom=intent.box
        if any(not left<=x<=right or not top<=y<=bottom for x,y in (start,end)):
            raise SemanticGateClosed('operation siren camera endpoint left original ALAS box')
        actual_vector=tuple(b-a for a,b in zip(start,end))
        # ALAS random_rectangle_vector_opted applies point_limit to both
        # endpoints. A requested vector can therefore shorten at the native
        # box boundary; interior changes, reversal and extension still differ
        # from that original gesture. The Oracle proves the actual drag path
        # and resulting native map movement below.
        for a,b,delta,requested,lower,upper in zip(
                start,end,actual_vector,map(round,intent.pixel_vector),
                (left,top),(right,bottom)):
            if delta==requested:
                continue
            if not ((requested<0 and requested<=delta<=0 and (a==upper or b==lower))
                    or (requested>0 and 0<=delta<=requested and (a==lower or b==upper))):
                # No input was sent: an unrecognized native sampler result
                # is a local port incompatibility. Reuse ALAS' task failure
                # interval instead of terminating unrelated scheduled tasks.
                raise AlasSemanticUnmapped('operation siren camera vector changed beyond native boundary clipping')
        if (isinstance(duration,bool) or not isinstance(duration,(int,float)) or not math.isfinite(duration)
                or not (intent.duration_range[0]<=duration<=intent.duration_range[1]
                        or intent.duration_range[0]*2.5<=duration<=intent.duration_range[1]*2.5)):
            raise SemanticGateClosed('operation siren camera swipe duration changed')
        # ALAS tests continuous path samples with threshold=0: only the
        # rectangle interior is forbidden. Rounding an intermediate point
        # onto an edge invents an intersection the native sampler rejected.
        count=int(math.hypot(*map(round,intent.pixel_vector))//70)+1
        for index in range(count+1):
            x,y=(b-v*index/count for b,v in zip(end,actual_vector))
            if any(area[0]<x<area[2] and area[1]<y<area[3]
                    for area in intent.blacklist_areas):
                # Native sampling can exhaust its bounded attempts and return
                # a rejected candidate. No input occurred: defer this port's
                # task while independent scheduled work remains usable.
                raise AlasSemanticUnmapped(
                    'operation siren camera sampler produced an ALAS forbidden path; no input submitted')
        return self.oracle.operation_siren_map_swipe(intent.geometry,start,end,round(duration*1000))

    def _operation_siren_allows_passive_probe(self) -> bool:
        now = time.monotonic()
        if self._meta_beacon_active or self._meta_assist_active:
            return True
        if self._operation_siren_combat_active:
            return True
        if self._operation_siren_auto_search_active:
            return True
        if (now <= self._operation_siren_entry_transition_until
                and getattr(self.oracle, 'daily_entry_visible', lambda: False)()):
            # An exact unobscured Daily page ends the old OpSi entry/exit
            # observation lease. Otherwise its blanket passive misses hide
            # Daily's own detail check and repeat an already completed entry.
            self._operation_siren_entry_transition_until = 0.0
        if now <= max(
            self._operation_siren_entry_transition_until,
            self._operation_siren_auto_search_transition_until,
            self._operation_siren_page_remount_until,
        ):
            return True
        if (
            getattr(
                self.oracle,
                "operation_siren_local_map_visible",
                lambda: False,
            )()
            or getattr(
                self.oracle,
                "operation_siren_globe_visible",
                lambda: False,
            )()
        ):
            return True
        if self.oracle.exists("os/voucher/back"):
            return True
        return False

    def begin_operation_siren_startup_recovery(
        self,
        timeout_seconds: float = 300.0,
    ) -> None:
        """Own one bounded Operation Siren resume transition.

        ALAS can be restarted while an already-enabled Siren auto-search is
        loading or fighting. During that interval neither the local-map nor
        globe hierarchy is mounted, so a fresh adapter cannot infer the owner
        from UI alone. The Operation Siren task entry supplies that missing
        provenance explicitly and only for this bounded startup interval.
        Exact map/globe observations clear the lease early.
        """

        self._package_gate()
        if (
            isinstance(timeout_seconds, bool)
            or not isinstance(timeout_seconds, (int, float))
            or not math.isfinite(float(timeout_seconds))
            or float(timeout_seconds) <= 0.0
            or float(timeout_seconds) > 600.0
        ):
            raise ValueError(
                "Operation Siren startup recovery timeout must be in (0, 600]"
            )
        self._operation_siren_entry_transition_until = (
            time.monotonic() + float(timeout_seconds)
        )
        # A fresh process cannot distinguish a resumed long-running search
        # from a short page transition until the official switch is readable.
        # Keep only passive probes owned; operation_siren_auto_search_state()
        # clears this provisional owner as soon as exact OFF is observed.
        self._operation_siren_auto_search_active = True
        self._operation_siren_startup_search_provisional = True
        self._operation_siren_auto_search_completed_empty = False

    def begin_operation_siren_page_remount(
        self,
        timeout_seconds: float = 300.0,
    ) -> None:
        """Own one bounded OS map -> main -> OS lifecycle remount."""

        self._package_gate()
        if (
            isinstance(timeout_seconds, bool)
            or not isinstance(timeout_seconds, (int, float))
            or not math.isfinite(float(timeout_seconds))
            or float(timeout_seconds) <= 0.0
            or float(timeout_seconds) > 600.0
        ):
            raise ValueError(
                "Operation Siren page remount timeout must be in (0, 600]"
            )
        self._operation_siren_page_remount_until = (
            time.monotonic() + float(timeout_seconds)
        )

    def end_operation_siren_page_remount(self) -> None:
        self._operation_siren_page_remount_until = 0.0

    def operation_siren_state(self) -> OperationSirenState:
        self._package_gate()
        state = self.oracle.operation_siren_state()
        self._operation_siren_entry_transition_until = 0.0
        self._operation_siren_entry_receipt = None
        self._operation_siren_globe_map_receipt = None
        return state

    def operation_siren_mission_entry_available(self) -> bool:
        """Prove the local-map mission-list entrance is actionable now."""

        # The button remains mounted below some OS panels, so raw existence
        # is insufficient. ``enabled`` preserves the unique target, raycast,
        # bounds, blocker, foreground, and fresh-frame gates at this boundary.
        self._package_gate()
        if self.oracle.operation_siren_mission_list_visible():
            return False
        self.oracle.operation_siren_state()
        return self.oracle.enabled("os/map/mission-list")

    def operation_siren_stronghold_percentage(self) -> int:
        self._package_gate()
        return self.oracle.operation_siren_stronghold_percentage()

    def operation_siren_auto_search_state(self) -> str:
        self._package_gate()
        if time.monotonic() <= self._operation_siren_auto_search_transition_until:
            # The exact OFF control was just committed.  Its post-click route
            # legitimately unmounts the local-map shell while loading battle,
            # so map-option bookkeeping must not reinterpret that transition
            # as a second OFF state or an unknown page.
            return "on"
        state = self.oracle.operation_siren_auto_search_state()
        if state == "on":
            self._operation_siren_auto_search_transition_until = 0.0
            self._operation_siren_startup_search_provisional = False
        else:
            if (
                self._operation_siren_auto_search_active
                and not self._operation_siren_startup_search_provisional
            ):
                self._operation_siren_auto_search_completed_empty = True
            self._operation_siren_auto_search_active = False
            self._operation_siren_startup_search_provisional = False
        return state

    def operation_siren_auto_search_completed_empty(self) -> bool:
        """Whether an exact enable attempt naturally returned to OFF."""

        self._package_gate()
        return self._operation_siren_auto_search_completed_empty

    def mark_operation_siren_auto_search_completed_empty(self) -> None:
        """Record the original ALAS loop's exact settled-OFF conclusion."""

        self._package_gate()
        if self._operation_siren_auto_search_active:
            # The original loop owns a separate bounded unchanged-OFF timer.
            # It can therefore prove the no-event result before our longer
            # post-click loading allowance expires.  Re-read the exact typed
            # switch here and collapse that transition only for settled OFF.
            if self.oracle.operation_siren_auto_search_state() != "off":
                raise SemanticGateClosed(
                    "cannot complete auto search while its transition is active"
                )
            self._operation_siren_auto_search_transition_until = 0.0
            self._operation_siren_auto_search_active = False
            self._operation_siren_startup_search_provisional = False
        self._operation_siren_auto_search_completed_empty = True

    def operation_siren_auto_search_transition_active(self) -> bool:
        """Report the bounded post-enable transition separately from ON."""

        self._package_gate()
        return (
            time.monotonic()
            <= self._operation_siren_auto_search_transition_until
        )

    def operation_siren_auto_search_info_count(self) -> int:
        self._package_gate()
        return self.oracle.operation_siren_auto_search_info_count()

    def operation_siren_current_fleet(self) -> int:
        self._package_gate()
        return self.oracle.operation_siren_current_fleet()

    def operation_siren_current_fleet_defeated(self) -> bool:
        self._package_gate()
        fleet = self.oracle.operation_siren_current_fleet()
        # Skip only a fleet that already lost its own Month Boss attempt.
        # Map-chibi ``marks/damage/1`` can appear on a stacked neighbour
        # while another fleet walks, and is not original ALAS' left HUD.
        return self.operation_siren_fleet_already_defeated(fleet)

    def operation_siren_fleet_already_defeated(self, fleet: int) -> bool:
        """Return whether this exact fleet already lost its own Month Boss attempt.

        Boss-room clicks can remount the left ``fleet_bar`` onto a stacked
        neighbour.  Callers that already know the turn's fleet must not read
        that HUD number.
        """

        if type(fleet) is not int or fleet not in {1, 2, 3, 4}:
            raise SemanticGateClosed(
                "operation siren defeated-fleet index is malformed"
            )
        return fleet in self._operation_siren_defeated_fleets

    def operation_siren_current_fleet_needs_repair(self) -> bool:
        self._package_gate()
        return self.oracle.operation_siren_current_fleet_needs_repair()

    def operation_siren_precombat_visible(self) -> bool:
        self._package_gate()
        return self.oracle.operation_siren_precombat_visible()

    def operation_siren_precombat_info_visible(self) -> bool:
        self._package_gate()
        return self.oracle.operation_siren_precombat_info_visible()

    def operation_siren_low_resolve_prompt_visible(self) -> bool:
        self._package_gate()
        return self.oracle.operation_siren_low_resolve_prompt_visible()

    def click_operation_siren_low_resolve_cancel(self) -> ActionReceipt:
        self._package_gate()
        # The prompt belongs to the fleet the client currently has selected.
        # A stacked neighbour can remount fleet_bar after a boss click; using
        # a stale combat-fleet snapshot would mark the next turn as already
        # lost.
        fleet = self.oracle.operation_siren_current_fleet()
        receipt = self.oracle.click_operation_siren_low_resolve_cancel()
        self._operation_siren_defeated_fleets.add(fleet)
        return receipt

    def click_operation_siren_precombat_info(self) -> ActionReceipt:
        self._package_gate()
        return self.oracle.click_operation_siren_precombat_info()

    def click_operation_siren_precombat_start(self) -> ActionReceipt:
        self._package_gate()
        receipt = self.oracle.click_operation_siren_precombat_start()
        self._operation_siren_combat_active = True
        return receipt

    def operation_siren_combat_committed(self) -> bool:
        return self._operation_siren_combat_active

    def operation_siren_battle_result_visible(self) -> bool:
        self._package_gate()
        return self.oracle.operation_siren_battle_result_visible()

    def operation_siren_battle_result_grade(self) -> str:
        self._package_gate()
        return self.oracle.operation_siren_battle_result_grade()

    def click_operation_siren_battle_result(self) -> ActionReceipt:
        self._package_gate()
        if not self.oracle.operation_siren_battle_result_visible():
            raise SemanticGateClosed("operation siren battle result is absent")
        return self.oracle.click_daily_battle_result()

    def complete_operation_siren_combat_if_map_restored(self) -> bool:
        """Release combat ownership on an exact unobstructed OS map."""

        if (not self._operation_siren_combat_active
                or self._meta_beacon_active or self._meta_assist_active):
            # META shares the legacy combat-active latch, but its native
            # expected_end owns return to WorldBoss, never an OS map probe.
            return False
        # The map hierarchy remains mounted under grade and reward overlays.
        # Do not release ownership until those exact result surfaces are gone.
        if self.oracle.daily_battle_result_visible():
            return False
        if getattr(self.oracle, 'operation_siren_battle_statistics_visible', lambda: False)():
            return False
        if self.oracle.award_info_page_visible():
            return False
        if not self.oracle.operation_siren_local_map_visible():
            return False
        self._operation_siren_combat_active = False
        return True

    def begin_operation_siren_boss_combat(self) -> None:
        """Own a boss encounter reached directly from the local map.

        Operation Siren bosses can enter CombatUI without mounting a
        pre-combat start button.  Require an exact typed boss radar target
        before arming result ownership so the shared combat result hierarchy
        cannot fall through to the Daily task handler.
        """

        self._package_gate()
        if not self.oracle.operation_siren_radar_targets("boss"):
            raise SemanticGateClosed(
                "operation siren boss combat requires an exact boss target"
            )
        self._operation_siren_combat_fleet = self.oracle.operation_siren_current_fleet()
        self._operation_siren_combat_active = True

    def mark_operation_siren_combat_fleet_defeated(self) -> None:
        """Remember the fleet that just received a Month Boss D-rank result.

        Later fleets must still take their turn.  Approach-time map-chibi
        damage marks are not this signal.
        """

        fleet = self._operation_siren_combat_fleet
        if fleet is None:
            fleet = self.oracle.operation_siren_current_fleet()
        self._operation_siren_defeated_fleets.add(fleet)

    def operation_siren_reward_visible(self) -> bool:
        """Return whether a standalone exact AwardInfo stack covers the map."""

        self._package_gate()
        return self._frame_or_live_observation_oracle().award_info_page_visible()

    def click_operation_siren_reward_close(self) -> ActionReceipt:
        """Close one exact standalone boss reward without pixel fallbacks."""

        return self._click_operation_siren_reward_close(self._fresh_input_oracle())

    def try_click_operation_siren_reward_close(self) -> Optional[ActionReceipt]:
        """Let the native map loop re-observe an unmounted or mounting reward."""

        return self._click_operation_siren_reward_close(
            self._fresh_input_oracle(), allow_passive=True
        )

    def _click_operation_siren_reward_close(self, reader, allow_passive=False):
        self._package_gate()
        if not self._operation_siren_allows_passive_probe():
            raise SemanticGateClosed("operation siren reward owner is absent")
        if not reader.award_info_page_visible():
            if allow_passive:
                return None
            raise SemanticGateClosed("operation siren reward page is absent")
        if (allow_passive
                and getattr(reader, 'reward_item_info_visible', lambda: False)()):
            # A map event can expose an item's description above AwardInfo.
            # Reuse its complete existing live action/postcondition parser;
            # this is only the description close, not an award completion.
            return self.oracle.click('reward/item-info/close')
        targets = tuple(
            semantic_id
            for semantic_id in (
                "reward/award-info/close",
                "reward/award-info1/close",
            )
            if reader.enabled(semantic_id)
        )
        if not targets and allow_passive:
            # AwardInfo ownership can precede its actionable close Button.
            # No input or completion receipt is produced; ALAS owns polling.
            return None
        if len(targets) != 1:
            raise SemanticGateClosed(
                "operation siren reward close target is absent or ambiguous"
            )
        receipt = replace(
            reader.click(targets[0]),
            semantic_id="os/combat/reward/close",
        )
        if self._meta_beacon_active or self._meta_assist_active:
            self._meta_reward_close_receipt = receipt
        else:
            self._operation_siren_reward_close_receipt = receipt
        return receipt

    def _operation_siren_reward_return_completed(self, reader):
        previous = self._operation_siren_reward_close_receipt
        if (previous is None
                or reader.observation_target_present('reward/award-info/close')
                or reader.observation_target_present('reward/award-info1/close')
                or not reader.operation_siren_local_map_visible()
                or reader.operation_siren_map_overlay_present()):
            return None
        state = reader.read_state()
        if state.generation <= previous.generation:
            return None
        # Original ALAS can repeat GET_ITEMS from its retained screenshot
        # after our exact reward close has returned to the map. Hand off the
        # accepted edge once; this acknowledgement sends no second input.
        self._package_gate()
        self._operation_siren_reward_close_receipt = None
        return previous

    def operation_siren_radar_targets(
        self, target_kind: str
    ) -> Tuple[Tuple[int, int], ...]:
        self._package_gate()
        return self.oracle.operation_siren_radar_targets(target_kind)

    def operation_siren_month_boss_room_difficulty(self) -> str:
        self._package_gate()
        return self.oracle.operation_siren_month_boss_room_difficulty()

    def click_operation_siren_radar_guidepost(
        self, relative_position: Tuple[int, int]
    ) -> ActionReceipt:
        self._package_gate()
        return self.oracle.click_operation_siren_radar_guidepost(
            relative_position
        )

    def click_operation_siren_radar_boss(
        self, relative_position: Tuple[int, int]
    ) -> ActionReceipt:
        self._package_gate()
        return self.oracle.click_operation_siren_radar_boss(relative_position)

    def operation_siren_obscure_exit_passage_position(
        self,
    ) -> Optional[Tuple[int, int]]:
        return self.oracle.operation_siren_obscure_exit_passage_position()

    def operation_siren_post_search_loot_visible(self) -> bool:
        return self.oracle.operation_siren_post_search_loot_visible()

    def click_operation_siren_post_search_loot_back(self) -> ActionReceipt:
        return self.oracle.click_operation_siren_post_search_loot_back()

    def operation_siren_obscure_exit_camera_swipe(
        self,
    ) -> OperationSirenGlobeSwipeReceipt:
        return self.oracle.operation_siren_obscure_exit_camera_swipe()

    def click_operation_siren_obscure_exit_passage(self) -> ActionReceipt:
        return self.oracle.click_operation_siren_obscure_exit_passage()

    def operation_siren_abyssal_exit_available(self) -> bool:
        self._package_gate()
        return self.oracle.operation_siren_abyssal_exit_available()

    def click_operation_siren_abyssal_exit(self) -> ActionReceipt:
        self._package_gate()
        return self.oracle.click_operation_siren_abyssal_exit()

    def click_operation_siren_relative_grid(
        self,
        relative_position: Tuple[int, int],
        *,
        prefer_adjacent_event: bool = False,
        fleet_relative: bool = False,
    ) -> ActionReceipt:
        self._package_gate()
        return self.oracle.click_operation_siren_relative_grid(
            relative_position,
            prefer_adjacent_event=prefer_adjacent_event,
            fleet_relative=fleet_relative,
        )

    def operation_siren_daemon_move_allowed(self) -> bool:
        return self._action_ledger.allowed("operation_siren.daemon_move")

    def operation_siren_nearest_daemon_target(
        self,
    ) -> Optional[OperationSirenDaemonTarget]:
        self._package_gate()
        return self.oracle.operation_siren_nearest_daemon_target()

    def click_operation_siren_daemon_target(
        self, expected: OperationSirenDaemonTarget
    ) -> ActionReceipt:
        self._package_gate()
        return self._dispatch_mutation(
            "operation_siren.daemon_move",
            lambda: self.oracle.click_operation_siren_daemon_target(expected),
        )

    def click_operation_siren_fleet_bar(self) -> ActionReceipt:
        self._package_gate()
        return self.oracle.click_operation_siren_fleet_bar()

    def operation_siren_fleet_selector_open(self) -> bool:
        self._package_gate()
        return self.oracle.operation_siren_fleet_selector_open()

    def click_operation_siren_fleet_selector(
        self, fleet_index: int
    ) -> ActionReceipt:
        self._package_gate()
        return self.oracle.click_operation_siren_fleet_selector(fleet_index)

    def click_operation_siren_globe_zone_enter(self, expected_zone_name=None) -> ActionReceipt:
        """Keep passive map-event probes owned after the exact zone input."""
        self._package_gate()
        receipt = self.oracle.click_operation_siren_globe_zone_enter(expected_zone_name)
        self._operation_siren_entry_receipt = receipt
        self._operation_siren_entry_transition_until = time.monotonic() + 30.0
        return receipt

    def operation_siren_map_visible(self) -> bool:
        self._package_gate()
        reader = self._frame_or_live_observation_oracle()
        try:
            reader.operation_siren_state()
            # Resource texts remain mounted below inventory, order and reward
            # overlays. ALAS's is_in_map must not finish a UI transition from
            # that underlay before the foreground owner has gone away.
            if (reader.operation_siren_map_overlay_present()
                    or time.monotonic() <= self._event_story_transition_until):
                # Story choices remount their next dialogue asynchronously.
                # Use the same screenshot and passive transition as OS_CHECK,
                # so ALAS keeps processing map events during that handoff.
                return False
            self._operation_siren_entry_transition_until = 0.0
            self._operation_siren_entry_receipt = None
            self._operation_siren_globe_map_receipt = None
            return True
        except SemanticGateClosed:
            return False

    def operation_siren_globe_state(self) -> OperationSirenGlobeState:
        self._package_gate()
        last_error: Optional[SemanticGateClosed] = None
        for attempt in range(16):
            try:
                state = self.oracle.operation_siren_globe_state()
                self._operation_siren_entry_transition_until = 0.0
                self._operation_siren_entry_receipt = None
                return state
            except SemanticGateClosed as exc:
                last_error = exc
                if not self.oracle.operation_siren_globe_visible():
                    raise
                if attempt < 15:
                    time.sleep(0.25)
        assert last_error is not None
        raise last_error

    def operation_siren_globe_visible(self) -> bool:
        self._package_gate()
        visible = self.oracle.operation_siren_globe_visible()
        if visible:
            self._operation_siren_entry_transition_until = 0.0
        return visible

    def operation_siren_globe_unpin(self, *, precondition_oracle=None) -> OperationSirenGlobeSwipeReceipt:
        self._package_gate()
        if precondition_oracle is not None:
            return self.oracle.operation_siren_globe_unpin(
                precondition_oracle=precondition_oracle)
        return self.oracle.operation_siren_globe_unpin()

    def operation_siren_storage_visible(self) -> bool:
        self._package_gate()
        # StorageHandler ends its screenshot loop on this observation, then
        # reads inventory samples from that same immutable screenshot frame.
        return self._frame_or_live_observation_oracle().operation_siren_storage_visible()

    def operation_siren_storage_state(self) -> OperationSirenStorageState:
        self._package_gate()
        return self.oracle.operation_siren_storage_state()

    def click_operation_siren_storage_item(self, item_type: str) -> ActionReceipt:
        self._package_gate()
        return self.oracle.click_operation_siren_storage_item(item_type)

    def operation_siren_storage_scroll_for_abyssal(
        self,
    ) -> Optional[OperationSirenStorageScrollReceipt]:
        self._package_gate()
        return self.oracle.operation_siren_storage_scroll_for_abyssal()

    def click_operation_siren_storage_back(self) -> ActionReceipt:
        self._package_gate()
        return self.oracle.click_operation_siren_storage_back()

    def operation_siren_storage_detail(self) -> Optional[Tuple[str, str, int]]:
        self._package_gate()
        return self.oracle.operation_siren_storage_detail()

    def click_operation_siren_storage_detail_close(self) -> ActionReceipt:
        self._package_gate()
        return self.oracle.click_operation_siren_storage_detail_close()

    def operation_siren_coordinate_checkout_allowed(self) -> bool:
        return self._action_ledger.allowed("operation_siren.coordinate_checkout")

    def click_operation_siren_storage_detail_checkout(self) -> ActionReceipt:
        self._package_gate()
        return self._dispatch_mutation(
            "operation_siren.coordinate_checkout",
            self.oracle.click_operation_siren_storage_detail_checkout,
        )

    def operation_siren_storage_checkout_prompt_visible(self) -> bool:
        self._package_gate()
        return self.oracle.operation_siren_exit_prompt_visible()

    def click_operation_siren_storage_checkout_confirm(self) -> ActionReceipt:
        self._package_gate()
        receipt = self.oracle.click_operation_siren_exit(True)
        self._operation_siren_entry_transition_until = time.monotonic() + 30.0
        return receipt

    def operation_siren_map_exit_prompt_visible(self) -> bool:
        self._package_gate()
        return self.oracle.operation_siren_exit_prompt_visible()

    def click_operation_siren_map_exit_confirm(self) -> ActionReceipt:
        self._package_gate()
        receipt = self.oracle.click_operation_siren_exit(True)
        self._operation_siren_entry_transition_until = time.monotonic() + 30.0
        return receipt

    def try_click_operation_siren_map_exit_confirm(
        self,
    ) -> Optional[ActionReceipt]:
        """Atomically confirm the exact exit prompt, or report it absent."""

        try:
            return self.click_operation_siren_map_exit_confirm()
        except SemanticGateClosed as exc:
            if str(exc) == "operation siren exit prompt is absent":
                return None
            raise

    def operation_siren_globe_port_projection(self, zone_id: int):
        return self.oracle.operation_siren_globe_port_projection(zone_id)

    def operation_siren_globe_drag_owned(self, start, end):
        self._package_gate()
        return self.oracle.operation_siren_globe_drag_owned(start,end)

    def operation_siren_globe_drag_candidate(self, start, end, *, box):
        self._package_gate()
        intent = self._operation_siren_globe_swipe_intent
        bounds = self._campaign_swipe_box(box, 'operation siren globe swipe box')
        if intent is None or bounds != intent.box:
            raise SemanticGateClosed('globe candidate has no matching ALAS swipe intent')
        return self.oracle.operation_siren_globe_drag_candidate(start, end, box=bounds)

    def operation_siren_globe_map_projection(self, area_pos):
        self._package_gate()
        return self.oracle.operation_siren_globe_map_projection(area_pos)

    def click_operation_siren_globe_map_zone(self, expected_zone_name, area_pos):
        self._package_gate()
        return self.oracle.click_operation_siren_globe_map_zone(expected_zone_name, area_pos)

    def click_operation_siren_globe_port(self, expected_zone_name: str, zone_id: int, *, native_mask=False) -> ActionReceipt:
        if native_mask:
            return self.oracle.click_operation_siren_globe_port(expected_zone_name, zone_id, native_mask=True)
        return self.oracle.click_operation_siren_globe_port(expected_zone_name, zone_id)

    def click_operation_siren_globe_zone(
        self, expected_zone_name: str, point: Tuple[float, float]
    ) -> ActionReceipt:
        self._package_gate()
        return self.oracle.click_operation_siren_globe_zone(
            expected_zone_name, point
        )

    def click_operation_siren_globe_zone_switch(self) -> ActionReceipt:
        self._package_gate()
        return self.oracle.click_operation_siren_globe_zone_switch()

    def operation_siren_globe_zone_types(self) -> Tuple[str, ...]:
        self._package_gate()
        return self.oracle.operation_siren_globe_zone_types()

    def click_operation_siren_globe_zone_type(
        self, expected_type: str
    ) -> ActionReceipt:
        self._package_gate()
        return self.oracle.click_operation_siren_globe_zone_type(expected_type)

    def operation_siren_need_repair(self) -> Tuple[bool, ...]:
        self._package_gate()
        return self.oracle.operation_siren_need_repair()

    def operation_siren_action_point_state(
        self,
    ) -> OperationSirenActionPointState:
        self._package_gate()
        return self.oracle.operation_siren_action_point_state()

    def operation_siren_action_point_visible(self) -> bool:
        self._package_gate()
        return self.oracle.operation_siren_action_point_visible()

    def click_operation_siren_action_point_open(self) -> ActionReceipt:
        self._package_gate()
        return self.oracle.click_operation_siren_action_point_open()

    def click_operation_siren_action_point_item(
        self, item_index: int
    ) -> ActionReceipt:
        self._package_gate()
        return self.oracle.click_operation_siren_action_point_item(item_index)

    def click_operation_siren_action_point_control(
        self, use: bool
    ) -> ActionReceipt:
        self._package_gate()
        if not use:
            return self._fresh_input_oracle().click_operation_siren_action_point_control(False)
        return self._dispatch_mutation(
            "operation_siren.action_point_use",
            lambda: self._fresh_input_oracle().click_operation_siren_action_point_control(True),
        )

    def operation_siren_action_point_use_allowed(self) -> bool:
        return self._action_ledger.allowed("operation_siren.action_point_use")

    def operation_siren_port_repair_cost(self) -> Optional[int]:
        self._package_gate()
        return self._frame_or_live_observation_oracle().operation_siren_port_repair_cost()

    def click_operation_siren_port_repair(
        self, confirm: bool
    ) -> ActionReceipt:
        self._package_gate()
        if not confirm:
            return self._fresh_input_oracle().click_operation_siren_port_repair(False)
        return self._dispatch_mutation(
            "operation_siren.port_repair",
            lambda: self._fresh_input_oracle().click_operation_siren_port_repair(True),
        )

    def operation_siren_port_repair_allowed(self) -> bool:
        return self._action_ledger.allowed("operation_siren.port_repair")

    def operation_siren_low_resolve_visible(self) -> bool:
        self._package_gate()
        return self.oracle.operation_siren_low_resolve_visible()

    def begin_operation_siren_globe_swipe_vector(
        self,
        vector: Any,
        *,
        box: Any,
        random_range: Any,
        padding: Any,
        duration: Any,
        whitelist_area: Any,
        blacklist_area: Any,
        name: Any,
        distance_check: Any,
    ) -> _OperationSirenGlobeSwipeIntent:
        """Authorize one camera-only swipe selected by ALAS's globe logic."""

        self._package_gate()
        # Preparing an intent has not dispatched a gesture. A transient
        # publisher/loading edge may settle during the existing read-only
        # retry; retain the actual identity/blocker error if it does not.
        # The sampler and final swipe still prove the complete native path.
        self.oracle._retry_transition_read(
            self.oracle._require_operation_siren_globe_visible
        )
        if self._operation_siren_globe_swipe_intent is not None:
            raise SemanticGateClosed("operation siren globe swipe is already armed")
        if not isinstance(name, str) or re.fullmatch(
            r"GLOBE_SWIPE_-?[0-9]+_-?[0-9]+", name
        ) is None:
            raise SemanticGateClosed("operation siren globe swipe name is not canonical")
        pixel_vector = self._campaign_swipe_pair(
            vector, "operation siren globe pixel vector"
        )
        if not 10.0 <= math.hypot(*pixel_vector) <= 1200.0:
            raise SemanticGateClosed("operation siren globe swipe vector is outside limits")
        exact_box = self._campaign_swipe_box(box, "operation siren globe swipe box")
        # ALAS owns its sampling rectangle. Harmless upstream adjustments
        # remain compatible; every actual sampled path still needs the native
        # Plane proof, and final dispatch must stay inside this same box.
        if not (0 <= exact_box[0] < exact_box[2] <= 1280
                and 0 <= exact_box[1] < exact_box[3] <= 720):
            raise SemanticGateClosed("operation siren globe swipe box is outside the screen")
        if tuple(random_range) != (0, 0, 0, 0) or padding != 15:
            raise SemanticGateClosed("operation siren globe swipe selection changed")
        if whitelist_area is not None or blacklist_area is not None:
            raise SemanticGateClosed("operation siren globe swipe areas changed")
        duration_range = self._campaign_swipe_pair(
            duration, "operation siren globe swipe duration"
        )
        if duration_range != (0.1, 0.2) or distance_check is not True:
            raise SemanticGateClosed("operation siren globe swipe timing changed")
        intent = _OperationSirenGlobeSwipeIntent(
            name=name,
            pixel_vector=pixel_vector,
            box=exact_box,
            duration_range=duration_range,
        )
        self._operation_siren_globe_swipe_intent = intent
        return intent

    def end_operation_siren_globe_swipe_vector(
        self, intent: _OperationSirenGlobeSwipeIntent
    ) -> None:
        if self._operation_siren_globe_swipe_intent is not intent:
            raise SemanticGateClosed("operation siren globe swipe token changed")
        self._operation_siren_globe_swipe_intent = None

    def _appear_opsi_order(self, name, semantic_id):
        pending_order = self._operation_siren_pending_order
        order_confirm_names = (
            "POPUP_CONFIRM",
            f"POPUP_CONFIRM_ORDER_{pending_order.upper()}"
            if pending_order is not None
            else "",
        )
        order_cancel_names = (
            "POPUP_CANCEL",
            f"POPUP_CANCEL_ORDER_{pending_order.upper()}"
            if pending_order is not None
            else "",
        )
        if pending_order is not None and name in (
            order_confirm_names + order_cancel_names
        ):
            return self.oracle.operation_siren_order_confirmation_visible(
                pending_order
            )
        if name == "OS_CHECK" and semantic_id == "os/page/back":
            if self.oracle.operation_siren_exit_prompt_visible():
                return False
            visible = self.oracle.operation_siren_local_map_visible()
            if visible:
                self._operation_siren_entry_transition_until = 0.0
                self._operation_siren_entry_receipt = None
                self._operation_siren_globe_map_receipt = None
            return visible
        if semantic_id == "os/map/exit":
            return self.oracle.exists(semantic_id)
        if (
            name == "AUTO_SEARCH_REWARD"
            and self.oracle.operation_siren_world_overview_visible()
        ):
            return True
        if semantic_id in ("os/map/fleet-lock/on", "os/map/fleet-lock/off"):
            return self.oracle.operation_siren_fleet_lock_state() == semantic_id.rsplit("/", 1)[-1]
        return UNHANDLED

    def _appear_opsi(self, name, semantic_id):
        if semantic_id == "os/page/back":
            # Unity may retain the old LevelOrigin hierarchy briefly after
            # leaving Operation Siren.  A proven main page wins over that
            # stale back button so ALAS does not click it repeatedly.
            if self.oracle.operation_siren_exit_prompt_visible():
                return False
            if self.oracle.main_page_visible():
                return False
            try:
                self.oracle.operation_siren_state()
                return True
            except SemanticGateClosed:
                return False
        if semantic_id == "os/map/globe":
            if self.oracle.operation_siren_exit_prompt_visible():
                return False
            try:
                self.oracle.operation_siren_state()
                return self.oracle.exists("os/map/globe")
            except SemanticGateClosed:
                return False
        if semantic_id in (
            "os/port/supply",
            "os/port/back",
            "os/shop/back",
            "os/voucher/back",
        ):
            return self.oracle.exists(semantic_id)
        if semantic_id == "os/globe/map":
            if (
                self._operation_siren_globe_map_receipt is not None
                and time.monotonic()
                <= self._operation_siren_entry_transition_until
            ):
                return False
            return self.oracle.operation_siren_globe_visible()
        if semantic_id == "os/globe/voucher":
            try:
                self.oracle.operation_siren_globe_state()
                return self.oracle.exists("os/globe/voucher")
            except SemanticGateClosed:
                return False
        if semantic_id == "os/globe/mission-overview":
            try:
                self.oracle.operation_siren_globe_state()
                return self.oracle.exists("os/globe/mission-overview")
            except SemanticGateClosed:
                return False
        if semantic_id == "os/mission-overview/back":
            return self.oracle.operation_siren_mission_overview_visible()
        if name == "MISSION_OVERVIEW_EMPTY":
            return self.oracle.operation_siren_mission_overview_empty()
        if name == "MISSION_OVERVIEW_ACCEPT_SINGLE":
            return self.oracle.operation_siren_mission_overview_accept_available()
        if name == "MISSION_OVERVIEW_ACCEPT":
            # The current client exposes exact per-row accept Buttons.  Do not
            # guess that the unrelated title option is the legacy claim-all
            # pixel asset; the row path below remains the reviewed action.
            return False
        if semantic_id == "os/globe/zone-enter":
            try:
                self.oracle.operation_siren_globe_state()
                state = self.oracle.read_state()
                return sum(
                    len(self.oracle._matches(state, target))
                    for target in (
                        "os/globe/zone-enter",
                        "os/globe/zone-return",
                        "os/globe/zone-back",
                    )
                ) == 1
            except SemanticGateClosed:
                return False
        if semantic_id == "os/globe/zone-switch":
            try:
                self.oracle.operation_siren_globe_state()
                return self.oracle.exists("os/globe/zone-switch")
            except SemanticGateClosed:
                return False
        if semantic_id is not None and semantic_id.startswith("os/globe/zone-type/"):
            expected_type = semantic_id.rsplit("/", 1)[-1].upper()
            try:
                return expected_type in self.oracle.operation_siren_globe_zone_types()
            except SemanticGateClosed:
                return False
        if semantic_id == "os/map/order":
            try:
                self.oracle.operation_siren_state()
                return self.oracle.exists("os/map/order")
            except SemanticGateClosed:
                return False
        if semantic_id == "os/map/mission-list":
            try:
                self.oracle.operation_siren_state()
                return self.oracle.exists("os/map/mission-list")
            except SemanticGateClosed:
                return False
        if semantic_id == "os/mission-list/close":
            return self.oracle.operation_siren_mission_list_visible()
        if semantic_id == "os/storage/back":
            return self.oracle.operation_siren_storage_visible()
        if semantic_id == "os/storage/detail/checkout":
            return self.oracle.operation_siren_storage_detail() is not None
        if name == "MISSION_CHECK":
            if self.oracle.operation_siren_mission_list_visible():
                return True
        if name == "OS_MONTHBOSS_NORMAL":
            return self.oracle.operation_siren_month_boss_difficulty() == "normal"
        if name == "OS_MONTHBOSS_HARD":
            return self.oracle.operation_siren_month_boss_difficulty() == "hard"
        if name == "MISSION_FINISH":
            try:
                return self.oracle.operation_siren_mission_finish_available()
            except SemanticTargetMissing:
                return False
        if name == "MISSION_CHECKOUT":
            try:
                return self.oracle.operation_siren_mission_checkout_available()
            except SemanticTargetMissing:
                return False
        if semantic_id == "campaign-menu/os":
            if (
                self._operation_siren_entry_receipt is not None
                and time.monotonic()
                <= self._operation_siren_entry_transition_until
            ):
                return False
            return self.oracle.campaign_os_entrance_available()
        return UNHANDLED

    def _click_opsi_order(self, name):
        pending_order = self._operation_siren_pending_order
        order_confirm_names = (
            "POPUP_CONFIRM",
            f"POPUP_CONFIRM_ORDER_{pending_order.upper()}"
            if pending_order is not None
            else "",
        )
        order_cancel_names = (
            "POPUP_CANCEL",
            f"POPUP_CANCEL_ORDER_{pending_order.upper()}"
            if pending_order is not None
            else "",
        )
        if pending_order is not None and name in (
            order_confirm_names + order_cancel_names
        ):
            order_kind = pending_order
            receipt = self.oracle.click_operation_siren_order_confirmation(
                order_kind,
                confirm=name in order_confirm_names,
            )
            self._operation_siren_pending_order = None
            self._operation_siren_auto_search_transition_until = (
                time.monotonic() + 30.0
            )
            return receipt
        return UNHANDLED

    def _click_opsi_mission(self, name):
        if name == "MISSION_OVERVIEW_ACCEPT_SINGLE":
            return self.oracle.click_operation_siren_mission_overview_accept()
        if name == "MISSION_FINISH":
            return self.oracle.click_operation_siren_mission_finish()
        if name == "MISSION_CHECKOUT":
            return self.oracle.click_operation_siren_mission_checkout()
        return UNHANDLED
