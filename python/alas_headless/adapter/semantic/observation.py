"""Observation for the typed ALAS boundary."""

from __future__ import annotations

import math
import re
import statistics
import time
from dataclasses import replace
from numbers import Real
from typing import Any, List, Optional, Sequence, Tuple, Union
from ...semantic_oracle import (
    Bounds,
    CampaignMapViewportSwipeProof,
    OperationSirenGlobeSwipeReceipt,
    SemanticGateClosed,
)
from .contracts import AlasSemanticUnmapped
from ...oracle.surfaces import ObservationSurface
from ...oracle.errors import SemanticViewportReanchorRequired, SemanticTargetNotActionable
from ..errors import ExpiredFrameError
from .resources import (
    BUILD_POOL_NAVBAR_ACTIVE_COLOR,
    BUILD_POOL_NAVBAR_INACTIVE_COLOR,
    BUILD_POOL_NAVBAR_PATTERN,
    BUILD_POOL_NAVBAR_TARGETS,
    BUILD_SIDE_NAVBAR_ACTIVE_COLOR,
    BUILD_SIDE_NAVBAR_INACTIVE_COLOR,
    BUILD_SIDE_NAVBAR_PATTERN,
    BUILD_SIDE_NAVBAR_TARGETS,
    MAIL_TOGGLE_TARGETS,
    MISSION_NAVBAR_ACTIVE_COLOR,
    MISSION_NAVBAR_INACTIVE_COLOR,
    MISSION_NAVBAR_PATTERN,
    MISSION_NAVBAR_TARGETS,
)


class ObservationAdapterPorts:
    """Observation ports on the shared adapter context."""

    def _inherited_login_allows_passive_probe(self) -> bool:
        oracle = self._frame_or_live_observation_oracle()
        if not oracle.observation_target_present('login/enter'):
            return False
        blockers = oracle._blocking_rules(oracle.read_state(), 'ui/absence-probe')
        if any(rule.blocker_id != 'loading' for rule in blockers):
            return False
        # Generic ALAS navigation can inherit LoginUI2 after a cold start or
        # an accepted SDK login, without an explicit LoginHandler context.
        # Only unrelated presence probes become absent. The existing login
        # input port still owns actionable targets and loading rejection.
        return bool(blockers) or oracle.enabled('login/enter')

    def _meta_dossier_allows_passive_page_probe(self):
        oracle = self._frame_or_live_observation_oracle()
        if oracle.observation_target_present('meta/dossier/sync/back'):
            return oracle.meta_dossier_sync_page_visible()
        if oracle.observation_target_present('meta/dossier/empty/list'):
            # A completed beacon can leave the empty archive page for the next
            # task. Its existing full counter/control parser identifies that
            # page without borrowing the ended META task's ownership flags.
            oracle.meta_dossier_empty_points()
            return not oracle._blocking_rules(oracle.read_state(), 'ui/absence-probe')
        return (oracle.observation_target_present('meta/dossier/list')
                and oracle.meta_dossier_detail_visible()
                and not oracle._blocking_rules(oracle.read_state(), 'ui/absence-probe'))

    def _new_year_challenge_surface_visible(self) -> bool:
        try:
            self.oracle.new_year_challenge_ticket_count()
            return True
        except SemanticGateClosed:
            pass
        try:
            self.oracle.new_year_challenge_attack_state()
            return True
        except SemanticGateClosed:
            return False

    def _active_flow_allows_passive_probe(self) -> bool:
        now = time.monotonic()
        if (self._inherited_dorm_overlay_return() == 'dorm/feed/shop/cancel'
                or self._inherited_dorm_page_visible()):
            # The original UI graph can inherit CourtYard after another task.
            # Its exact unobscured identity owns unrelated passive probes,
            # while optional task inputs retain their own context and grants.
            return True
        if now <= self._research_menu_return_transition_until:
            self._package_gate()
            blockers = self.oracle._blocking_rules(
                self.oracle.read_state(), 'ui/absence-probe'
            )
            if not any(rule.blocker_id not in ('research-page', 'research-menu')
                       for rule in blockers):
                return True
        if self._operation_siren_allows_passive_probe():
            return True
        if self._login_flow.allows_passive_probe():
            return True
        if self._inherited_login_allows_passive_probe():
            return True
        if (
            self._mission_context is not None
            and (
                now <= self._mission_context.passive_transition_until
                or self._known_mission_surface_exists()
            )
        ):
            return True
        if (
            self._mail_context is not None
            and (
                now <= self._mail_context.passive_transition_until
                or self._known_mail_surface_exists()
            )
        ):
            return True
        if (
            self._commission_context is not None
            and (
                now <= self._commission_context.passive_transition_until
                or self._known_commission_surface_exists()
            )
        ):
            return True
        if (
            self._research_context is not None
            and (
                now <= self._research_context.passive_transition_until
                or self._known_research_surface_exists()
            )
        ):
            return True
        if (
            self._dorm_context is not None
            and (
                now <= self._dorm_context.passive_transition_until
                or self._known_dorm_surface_exists()
            )
        ):
            return True
        if (
            self._build_context is not None
            and (
                now <= self._build_context.passive_transition_until
                or self._known_build_surface_exists()
            )
        ):
            return True
        if (
            self._minigame_context is not None
            and (
                now <= self._minigame_context.passive_transition_until
                or self._known_minigame_surface_exists()
            )
        ):
            return True
        if (
            self._campaign_context is not None
            and (
                now <= self._campaign_context.passive_transition_until
                or self._known_campaign_surface_exists()
            )
        ):
            return True
        if (
            self._data_key_context is not None
        ):
            # DataKey.ui_ensure enumerates the complete upstream page registry
            # and its duration depends on observer latency.  The active task
            # context is the bounded owner: unknown presence probes are safe
            # absences, while every click remains explicitly mapped.
            return True
        if self._battle_pass_context is not None:
            # BattlePass.ui_ensure uses the same complete page registry.  Its
            # task context owns passive enumeration regardless of observer
            # speed; all input remains restricted to reviewed resources.
            return True
        return False

    def _award_close_target(self) -> Optional[str]:
        targets = tuple(
            semantic_id
            for semantic_id in (
                "reward/award-info/close",
                "reward/award-info1/close",
            )
            if self.oracle.enabled(semantic_id)
        )
        if len(targets) > 1:
            raise SemanticGateClosed("reward popup close target is ambiguous")
        return targets[0] if targets else None

    def _retained_commission_detail_visible(self, oracle) -> bool:
        context = self._commission_context
        if context is not None and context.selected_signature is not None:
            # A current native selection owns this detail. Generic recovery
            # must not discard it or repeat a submitted start.
            return False
        if not oracle.observation_target_present('commission/detail/back'):
            return False
        # Several unrelated pages share this generic blur-panel back path.
        # Dispatch the Commission parser only for its distinctive detail controls.
        if not any(oracle.observation_target_present(target) for target in (
                'commission/detail/recommend', 'commission/detail/start')):
            return False
        oracle.commission_detail_state()
        return oracle.enabled('commission/detail/back')

    def _goto_main_target(self) -> Optional[str]:
        oracle = self._frame_or_live_observation_oracle()
        if self._retained_commission_detail_visible(oracle):
            # Use ALAS' unknown-page recovery edge to dismiss one inherited
            # detail, then let its page graph rediscover the Commission list.
            return 'commission/detail/back'
        if (oracle.observation_target_present('tactical/book/cancel')
                and oracle.enabled('tactical/book/cancel')):
            # A retained lesson dialog covers its classroom back button.
            # Original unknown-page recovery closes this reviewed cancel
            # target first, then ALAS rediscovers the underlying page.
            return 'tactical/book/cancel'
        if (oracle.observation_target_present('mail/manage/back')
                and oracle.enabled('mail/manage/back')):
            return 'mail/manage/back'
        if (oracle.observation_target_present('guild/report/close')
                and oracle.enabled('guild/report/close')):
            return 'guild/report/close'
        targets = []
        # Discover only atomic mapped anchors first. A failure in an absent
        # shop, guild or combat parser must not break another page's exit.
        readers = (
            ("academy/page/back", lambda: oracle.academy_page_visible()),
            ("daily/page/back", lambda: oracle.daily_page_visible()),
            ("raid/page/home", lambda: oracle.raid_page_visible(event=oracle.current_raid_event())),
            ("guild/page/back", lambda: oracle.guild_page_visible()),
            ("os/page/back", lambda: oracle.operation_siren_page_visible()),
            ("os/globe/map", lambda: oracle.operation_siren_globe_visible()),
            ("meta/home", lambda: oracle.meta_page_visible()),
            ("meta/character/back", lambda: oracle.meta_character_page_visible() or oracle.meta_character_menu_visible()),
            ("private-quarters/home", lambda: oracle.private_quarters_page_visible()),
            ("game-room/home", lambda: oracle.game_room_page_visible()),
            ("minigame/new-year/back", lambda: oracle.new_year_challenge_prepare_visible()),
            ("minigame/poke/back", lambda: oracle.poke_minigame_prepare_visible()),
            ("minigame/shooting/back", lambda: oracle.shooting_minigame_prepare_visible()),
            ("battle-pass/home", lambda: oracle.battle_pass_page_visible()),
            ("shop/home", lambda: oracle.recommendation_shop_visible()),
        )
        for target, reader in readers:
            present = (
                oracle.observation_surface_present(ObservationSurface.CURRENT_RAID)
                if target == "raid/page/home"
                else oracle.observation_target_present(target)
            )
            if not present:
                continue
            if reader():
                targets.append(target)
        for identity, target in (
            ("settings/back", "settings/back"),
            ("player/profile/back", "player/profile/back"),
            ("archive/activity-list/home", "archive/activity-list/home"),
            ("event-list/page/back", "event-list/page/back"),
            ("campaign-menu/page/back", "campaign-menu/page/back"),
            ("task/page/back", "task/page/back"),
            ("commission/page/back", "commission/page/back"),
            ("tactical/page/back", "tactical/page/back"),
            ("build/page/back", "build/page/back"),
            ("research-menu/page/back", "research-menu/page/back"),
            ("research/page/back", "research/page/back"),
            ("shipyard/page/root", "shipyard/page/back"),
        ):
            if oracle.observation_target_present(identity) and oracle.enabled(target):
                targets.append(target)
        unique = tuple(dict.fromkeys(targets))
        if len(unique) > 1:
            raise SemanticGateClosed("GOTO_MAIN target is ambiguous")
        return unique[0] if unique else None

    def appear(self, button: Any) -> bool:
        """Run one presence probe with a bounded render-transition grace."""

        try:
            result = self._appear_once(button)
        except SemanticGateClosed as exc:
            if self._login_flow.active:
                result, stale_since = self._login_flow.handle_presence_failure(
                    exc,
                    self._observer_stale_since,
                )
                self._observer_stale_since = stale_since
                return result
            message = str(exc)
            if (
                message == "game activity is not top-resumed"
                and self._operation_siren_allows_passive_probe()
            ):
                # Bilibili's welcome/announcement activities temporarily own
                # the foreground during an explicitly owned OpSi cold start.
                # Presence scans are passive; every mutation remains closed
                # until the pinned game activity is top-resumed again.
                return False
            transient = message in (
                "observer snapshot is stale",
                "observer endpoints are not generation-coherent",
                "Msgbox snapshots are not coherent",
                "current Raid button and UI snapshots are incoherent",
                "guild page snapshots are not coherent",
                "reward resource page close is temporarily covered",
                "reward resource page identity is not proven: blockers=loading",
            )
            if not transient:
                raise
            now = time.monotonic()
            if self._observer_stale_since is None:
                self._observer_stale_since = now
            if (
                self._campaign_context is not None
                and now <= self._campaign_context.passive_transition_until
            ):
                return False
            if now - self._observer_stale_since <= 5.0:
                return False
            raise
        self._observer_stale_since = None
        return result

    def bounds(self, button: Any) -> Bounds:
        semantic_id = self.semantic_id_for(button)
        self._package_gate()
        return self.oracle.bounds(semantic_id)

    @staticmethod
    def _ocr_bounds(areas: Sequence[Any]) -> Tuple[Bounds, ...]:
        result = []
        for area in areas:
            if not isinstance(area, (tuple, list)) or len(area) != 4:
                raise SemanticGateClosed("semantic OCR area is malformed")
            if any(isinstance(value, bool) or not isinstance(value, Real) for value in area):
                raise SemanticGateClosed("semantic OCR area is not numeric")
            left, top, right, bottom = (float(value) for value in area)
            if not (0 <= left < right <= 1280 and 0 <= top < bottom <= 720):
                raise SemanticGateClosed("semantic OCR area is outside the logical screen")
            result.append(Bounds(left, top, right, bottom))
        if not result:
            raise SemanticGateClosed("semantic OCR requires at least one reviewed area")
        return tuple(result)

    @staticmethod
    def _normalize_typed_text(value: str) -> str:
        # Unity Text/TMP expose source text, which can contain rich-text tags
        # that an image OCR engine would never see.
        value = re.sub(r"<[^<>]{1,128}>", "", value)
        value = value.replace("\u00a0", " ").replace("\u3000", " ")
        return "".join(value.split())

    def ocr_text(
        self,
        areas: Sequence[Any],
        alphabet: Optional[str] = None,
    ) -> Union[str, List[str]]:
        """Return typed Unity text for ALAS OCR rectangles.

        The bridge requires an observed Text/TMP component substantially inside
        every OCR rectangle.  Missing, overlapping, truncated, or out-of-
        alphabet records close the gate instead of falling back to pixels.
        """

        self._package_gate()
        bounds = self._ocr_bounds(areas)
        if (self._dorm_context is not None and len(bounds) == 1
                and bounds[0] == Bounds(653.0, 374.0, 706.0, 395.0)
                and self._frame_or_live_observation_oracle().dorm_food_shop_visible()):
            value = str(self._frame_or_live_observation_oracle().dorm_food_shop_state().quantity)
            if alphabet is not None and any(character not in alphabet for character in value):
                raise SemanticGateClosed('typed text violates the ALAS OCR alphabet contract')
            return value
        if (
            len(bounds) == 1
            and bounds[0] == Bounds(1153.0, 140.0, 1178.0, 165.0)
            and self.oracle.exercise_page_visible()
        ):
            value = str(self.oracle.exercise_remaining())
            if alphabet is not None and any(
                character not in alphabet for character in value
            ):
                raise SemanticGateClosed(
                    "typed text violates the ALAS OCR alphabet contract"
                )
            return value
        if (
            len(bounds) == 1
            and bounds[0] == Bounds(1089.0, 105.0, 1209.0, 129.0)
            and self.oracle.exercise_page_visible()
        ):
            return self.oracle.exercise_period_remaining_text()
        for index in range(4):
            exercise_power_bounds = tuple(
                Bounds(float(222 + 244 * index), float(257 + 30 * row),
                       float(294 + 244 * index), float(285 + 30 * row))
                for row in range(2)
            )
            if (
                len(bounds) == 2
                and tuple(bounds) == exercise_power_bounds
                and self.oracle.exercise_page_visible()
            ):
                return [
                    str(value)
                    for value in self.oracle.exercise_opponent_power(index + 1)
                ]
        exercise_level_bounds = tuple(
            Bounds(float(origin + 168 * index), 259.0,
                   float(origin + 168 * index + 58), 280.0)
            for origin in (130, 832) for index in range(3)
        )
        if (
            len(bounds) == len(exercise_level_bounds)
            and tuple(bounds) == exercise_level_bounds
            and self.oracle.exercise_opponent_detail_visible()
        ):
            return [str(value) for value in self.oracle.exercise_opponent_levels()]
        if len(bounds) == 1 and bounds[0] == Bounds(133.0, 39.0, 250.0, 72.0):
            value = self.oracle.war_archives_data_key_text()
            if alphabet is not None and any(character not in alphabet for character in value):
                raise SemanticGateClosed(
                    "typed text violates the ALAS OCR alphabet contract"
                )
            return value
        if (
            self._commission_context is not None
            and self._commission_context.flow_kind == "tactical"
            and len(bounds) == 1
            and bounds[0] == Bounds(771.0, 191.0, 951.0, 209.0)
        ):
            value = self.oracle.tactical_book_skill_progress()
            if alphabet is not None and any(character not in alphabet for character in value):
                raise SemanticGateClosed(
                    "typed text violates the ALAS OCR alphabet contract"
                )
            return value
        if (
            self._supply_pack_context is not None
            and len(bounds) == 1
            and bounds[0] == Bounds(700.0, 23.0, 785.0, 47.0)
        ):
            context = self._supply_pack_context
            if context.cached_oil is None:
                context.cached_oil = self.oracle.shop_oil()
            return str(context.cached_oil)
        if (
            self._minigame_context is not None
            and len(bounds) == 1
            and bounds[0] == Bounds(1093.0, 24.0, 1133.0, 51.0)
        ):
            return str(self.oracle.minigame_coin_amount())
        if (
            self._minigame_context is not None
            and len(bounds) == 1
            and bounds[0] == Bounds(377.0, 636.0, 408.0, 669.0)
        ):
            return str(self.minigame_prepare_selected_tickets())
        groups = self.oracle.text_groups_in_bounds(bounds)
        values: List[str] = []
        for group in groups:
            observed = []
            seen = set()
            for text_state in group:
                if text_state.bounds is None:
                    continue
                if text_state.truncated:
                    raise SemanticGateClosed(
                        "semantic OCR target text is truncated"
                    )
                value = self._normalize_typed_text(text_state.text)
                identity = (
                    value,
                    round(text_state.bounds.left, 1),
                    round(text_state.bounds.top, 1),
                    round(text_state.bounds.right, 1),
                    round(text_state.bounds.bottom, 1),
                )
                if identity in seen:
                    continue
                seen.add(identity)
                observed.append((text_state, value))
            if not observed:
                raise SemanticGateClosed("semantic OCR area has no typed text")

            for index, (left_state, _) in enumerate(observed):
                for right_state, _ in observed[index + 1 :]:
                    if left_state.bounds is None or right_state.bounds is None:
                        raise SemanticGateClosed("semantic OCR text has no bounds")
                    overlap = self.oracle._bounds_overlap(
                        left_state.bounds, right_state.bounds
                    )
                    left_area = (
                        left_state.bounds.right - left_state.bounds.left
                    ) * (left_state.bounds.bottom - left_state.bounds.top)
                    right_area = (
                        right_state.bounds.right - right_state.bounds.left
                    ) * (right_state.bounds.bottom - right_state.bounds.top)
                    if overlap > 0.1 * min(left_area, right_area):
                        raise SemanticGateClosed(
                            "semantic OCR area contains overlapping text records"
                        )
            value = "".join(item[1] for item in observed)
            if alphabet is not None and any(
                character not in alphabet for character in value
            ):
                raise SemanticGateClosed(
                    "typed text violates the ALAS OCR alphabet contract"
                )
            values.append(value)
        return values[0] if len(values) == 1 else values

    def swipe(
        self,
        p1: Any,
        p2: Any,
        *,
        duration: Any,
        name: Any,
        distance_check: Any,
    ) -> Union[CampaignMapViewportSwipeProof, OperationSirenGlobeSwipeReceipt]:
        """Replace only the final dispatch of one armed ALAS map swipe."""

        self._package_gate()
        if self._operation_siren_map_swipe_intent is not None:
            return self._dispatch_operation_siren_map_swipe(p1,p2,duration=duration,name=name,distance_check=distance_check)
        globe_intent = self._operation_siren_globe_swipe_intent
        if globe_intent is not None:
            if name != globe_intent.name or distance_check is not True:
                raise SemanticGateClosed("operation siren globe final input changed")
            start_pair = self._campaign_swipe_pair(
                p1, "operation siren globe swipe start"
            )
            end_pair = self._campaign_swipe_pair(
                p2, "operation siren globe swipe end"
            )
            if any(not float(item).is_integer() for item in (*start_pair, *end_pair)):
                raise SemanticGateClosed("operation siren globe endpoints are not integral")
            start = tuple(int(item) for item in start_pair)
            end = tuple(int(item) for item in end_pair)
            left, top, right, bottom = globe_intent.box
            if any(
                not (left <= point[0] <= right and top <= point[1] <= bottom)
                for point in (start, end)
            ):
                raise SemanticGateClosed("operation siren globe endpoint left its box")
            expected_delta = tuple(
                int(round(value)) for value in globe_intent.pixel_vector
            )
            if (end[0] - start[0], end[1] - start[1]) != expected_delta:
                raise SemanticGateClosed("operation siren globe selected vector changed")
            duration_value = float(duration) if isinstance(duration, (int, float)) else 0.0
            raw_duration = (
                globe_intent.duration_range[0]
                <= duration_value
                <= globe_intent.duration_range[1]
            )
            adb_duration = (
                globe_intent.duration_range[0] * 2.5
                <= duration_value
                <= globe_intent.duration_range[1] * 2.5
            )
            if (
                isinstance(duration, bool)
                or not isinstance(duration, (int, float))
                or not (raw_duration or adb_duration)
            ):
                raise SemanticGateClosed("operation siren globe final duration changed")
            # Native Control.swipe already refreshes the real input frame.
            # A slow path proof can still outlive that lease; retain its final
            # age check and classify only a proven pre-dispatch expiry below.
            input_count = getattr(self.oracle, 'input_dispatch_count', None)
            try:
                return self.oracle.operation_siren_globe_swipe(
                    start,
                    end,
                    int(round(float(duration) * 1000.0)),
                )
            except ExpiredFrameError as exc:
                # The final guard still rejects expiry during a slow proof.
                # Only a proven pre-dispatch refusal belongs to ALAS' task
                # failure interval. Identity/invalidated-frame errors and any
                # uncertain accepted input retain their original failure.
                if (type(input_count) is not int
                        or self.oracle.input_dispatch_count != input_count):
                    raise
                raise SemanticTargetNotActionable('os/globe/swipe', exc.generation) from exc
        context = self._require_campaign_context()
        intent = context.viewport_swipe_intent
        if intent is None:
            self.reject_raw_input("swipe")
        assert intent is not None
        if name != intent.name or distance_check is not True:
            raise SemanticGateClosed("campaign map viewport final input changed")
        start_pair = self._campaign_swipe_pair(p1, "campaign map viewport start")
        end_pair = self._campaign_swipe_pair(p2, "campaign map viewport end")
        if any(not float(item).is_integer() for item in (*start_pair, *end_pair)):
            raise SemanticGateClosed("campaign map viewport endpoints are not integral")
        start = tuple(int(item) for item in start_pair)
        end = tuple(int(item) for item in end_pair)
        left, top, right, bottom = intent.box
        if any(
            not (left <= point[0] <= right and top <= point[1] <= bottom)
            for point in (start, end)
        ):
            raise SemanticGateClosed("campaign map viewport endpoint left its box")
        expected_delta = tuple(int(round(value)) for value in intent.pixel_vector)
        if (end[0] - start[0], end[1] - start[1]) != expected_delta:
            raise SemanticGateClosed("campaign map viewport selected vector changed")
        # ``random_rectangle_vector_opted`` treats whitelist areas as preferred
        # candidates, not as a mandatory final constraint: if no clipped area
        # produces a blacklist-safe point it deliberately falls back to the
        # padded box.  Validate that exact ALAS fallback domain here, then keep
        # the original segment-wise blacklist check below.
        endpoint_area = self._campaign_swipe_endpoint_area(intent)
        if (
            endpoint_area[0] > endpoint_area[2]
            or endpoint_area[1] > endpoint_area[3]
            or not self._campaign_point_in_area(end, endpoint_area)
        ):
            raise SemanticGateClosed(
                "campaign map viewport endpoint left ALAS selection domain"
            )
        blacklist_areas = intent.blacklist_areas
        # Device.swipe_vector refreshes the immutable semantic frame after
        # ALAS has calculated its gesture.  Unity may still finish a small,
        # uniform camera easing step during that boundary.  Rebase only this
        # geometry-only input frame after the full logical map contract has
        # been re-proven, and retain both the original and translated hazard
        # areas so the fresher view cannot make the sampled path less safe.
        if self._input_frame_refresher is not None and context.map_state is not None:
            prior_state = context.map_state
            prior_cells = {cell.node: cell for cell in prior_state.cells}
            easing_dx = 0.0
            easing_dy = 0.0
            for attempt in range(3):
                self._input_frame_refresher()
                fresh_state = self.campaign_camera_state()
                fresh_cells = {cell.node: cell for cell in fresh_state.cells}
                if set(prior_cells) != set(fresh_cells):
                    raise SemanticGateClosed(
                        "campaign map viewport easing changed the cell set"
                    )
                geometry_deltas = tuple(
                    (
                        fresh_cells[node].point.x - prior_cells[node].point.x,
                        fresh_cells[node].point.y - prior_cells[node].point.y,
                    )
                    for node in sorted(prior_cells)
                )
                easing_dx = float(
                    statistics.median(delta[0] for delta in geometry_deltas)
                )
                easing_dy = float(
                    statistics.median(delta[1] for delta in geometry_deltas)
                )
                if not intent.blacklist_areas or all(
                    math.hypot(dx - easing_dx, dy - easing_dy) <= 3.0
                    for dx, dy in geometry_deltas
                ):
                    break
                if attempt == 2:
                    raise SemanticViewportReanchorRequired(
                        "campaign map viewport easing is not a uniform shift"
                    )
            else:  # pragma: no cover - the bounded loop always breaks or raises
                raise SemanticGateClosed(
                    "campaign map viewport easing is not a uniform shift"
                )
            if math.hypot(easing_dx, easing_dy) > 1.0:
                blacklist_areas = blacklist_areas + tuple(
                    (
                        area[0] + easing_dx,
                        area[1] + easing_dy,
                        area[2] + easing_dx,
                        area[3] + easing_dy,
                    )
                    for area in intent.blacklist_areas
                )
        segment_count = int(math.hypot(*expected_delta) // 70) + 1
        for index in range(segment_count + 1):
            point = (
                int(round(end[0] - expected_delta[0] * index / segment_count)),
                int(round(end[1] - expected_delta[1] * index / segment_count)),
            )
            if any(
                self._campaign_point_in_area(point, area)
                for area in blacklist_areas
            ):
                raise SemanticViewportReanchorRequired("campaign map viewport path entered its blacklist")
        duration_value = (
            float(duration)
            if isinstance(duration, (int, float)) and not isinstance(duration, bool)
            else float("nan")
        )
        # ALAS passes the sampled 0.1-0.2s duration unchanged to MaaTouch,
        # minitouch, scrcpy, nemu_ipc, and uiautomator2.  Its ADB branch alone
        # multiplies the same sampled value by 2.5 before final dispatch.  Bind
        # the semantic input to exactly those two source-derived intervals;
        # the gap between them and every other timing remain closed.
        direct_duration = (
            intent.duration_range[0]
            <= duration_value
            <= intent.duration_range[1]
        )
        adb_duration = (
            intent.duration_range[0] * 2.5
            <= duration_value
            <= intent.duration_range[1] * 2.5
        )
        if not math.isfinite(duration_value) or not (
            direct_duration or adb_duration
        ):
            raise SemanticGateClosed("campaign map viewport final duration changed")
        positioning = context.camera_positioning_admission
        combat = context.combat_admission
        post_combat = bool(
            combat is not None
            and context.combat_receipt is not None
            and context.map_state is not None
            and self._campaign_post_combat_state_proven(context, context.map_state)
        )
        if (
            context.map_state is None
            or context.map_columns is None
            or context.map_rows is None
            or context.map_expected_fleet_count is None
            or (positioning is None) == (combat is None)
        ):
            raise SemanticGateClosed("campaign map viewport lease is incomplete")

        if positioning is not None:
            self._require_action_grant("campaign.camera_positioning")
            capability = "campaign.camera_positioning"
            target_node = positioning.target_node
        else:
            self._require_action_grant("campaign.viewport_swipe")
            assert combat is not None
            capability = "campaign.viewport_swipe"
            if context.submarine_move_entry is not None:
                target_node = context.submarine_planned_destination
                if target_node is None:
                    raise SemanticGateClosed('submarine viewport requires original planned destination')
            elif post_combat:
                fleets = tuple(
                    fleet
                    for fleet in context.map_state.fleets
                    if fleet.marker == combat.fleet_marker
                )
                if len(fleets) != 1:
                    raise SemanticGateClosed(
                        "campaign post-combat refocus fleet is ambiguous"
                    )
                target_node = fleets[0].node
            else:
                target_node = combat.input_nodes[
                    len(context.combat_route_receipts)
                ]
            # One ALAS in_sight() call can legitimately require more than one
            # clamped camera gesture.  Each gesture is independently budgeted
            # and proven; the next proof replaces the previous one for the
            # still-uncommitted grid input.
            context.viewport_swipe_proof = None
            context.target_recheck_proof = None
        proof = self._dispatch_mutation(
            capability,
            lambda: self.oracle.campaign_map_viewport_swipe(
                context.map_state,
                target_node,
                intent,
                start=start,
                end=end,
                duration_ms=int(round(duration_value * 1000.0)),
                columns=context.map_columns,
                rows=context.map_rows,
                land_cells=context.map_land_cells,
                expected_fleet_count=context.map_expected_fleet_count,
                allow_enemy_additions=post_combat,
                **({'allow_deployment': True} if context.submarine_move_entry is not None else {}),
            ),
        )
        context.map_state = proof.post_state
        if context.submarine_move_entry is not None:
            context.submarine_viewport_proofs.append(proof)
        elif positioning is not None:
            context.camera_positioning_proofs.append(proof)
        else:
            assert combat is not None
            context.viewport_swipe_proof = proof
            context.viewport_swipe_required = False
            if post_combat:
                context.post_combat_viewport_proofs.append(proof)
            if not post_combat:
                context.combat_admission = replace(
                    combat,
                    input_generation=proof.post_generation,
                    point=(
                        proof.target_after_point
                        if target_node == combat.target_node
                        else combat.point
                    ),
                    bounds=(
                        proof.target_after_bounds
                        if target_node == combat.target_node
                        else combat.bounds
                    ),
                )
        return proof

    def match_template_color(self, button: Any) -> bool:
        if self._button_name(button) == "MEOWFFICER_CHECK":
            self._package_gate()
            return self.oracle.enabled("meowfficer/page/back")
        return self.appear(button)

    def image_color_count(
        self,
        button: Any,
        color: Tuple[int, int, int],
        threshold: int,
        count: int,
    ) -> bool:
        del threshold, count
        name = self._button_name(button)
        self._package_gate()
        if name in ("MISSION_NOTICE_WHITE", "MISSION_WEEKLY_RED_DOT"):
            return self._mission_resource_appears(name)

        mail_toggle = MAIL_TOGGLE_TARGETS.get(name)
        if mail_toggle is not None:
            if self._mail_context is None:
                raise AlasSemanticUnmapped(
                    "ALAS mail option used outside mail flow: {0}".format(name)
                )
            return self.oracle.toggle_selected(mail_toggle)

        build_side_match = BUILD_SIDE_NAVBAR_PATTERN.fullmatch(name)
        if build_side_match is not None:
            if self._build_context is None:
                raise AlasSemanticUnmapped(
                    "ALAS construction navbar used outside build flow"
                )
            index = int(build_side_match.group(1))
            if index >= len(BUILD_SIDE_NAVBAR_TARGETS):
                return False
            selected = self.oracle.toggle_selected(
                BUILD_SIDE_NAVBAR_TARGETS[index]
            )
            normalized_color = tuple(color)
            if normalized_color == BUILD_SIDE_NAVBAR_ACTIVE_COLOR:
                return selected
            if normalized_color == BUILD_SIDE_NAVBAR_INACTIVE_COLOR:
                return not selected
            raise SemanticGateClosed(
                "unexpected construction side-navbar color contract"
            )

        build_pool_match = BUILD_POOL_NAVBAR_PATTERN.fullmatch(name)
        if build_pool_match is not None:
            if self._build_context is None:
                raise AlasSemanticUnmapped(
                    "ALAS construction pool navbar used outside build flow"
                )
            index = int(build_pool_match.group(1))
            target = BUILD_POOL_NAVBAR_TARGETS.get(index)
            if target is None:
                return False
            normalized_color = tuple(color)
            if index == 0 and not self.oracle.toggle_present(target):
                # Check optional seasonal presence before requesting a unique
                # selection state. Missing seasonal tabs have no selection.
                if normalized_color not in (BUILD_POOL_NAVBAR_ACTIVE_COLOR,
                                             BUILD_POOL_NAVBAR_INACTIVE_COLOR):
                    raise SemanticGateClosed("unexpected construction pool-navbar color contract")
                return False
            selected = self.oracle.toggle_selected(target)
            if normalized_color == BUILD_POOL_NAVBAR_ACTIVE_COLOR:
                return selected
            if normalized_color == BUILD_POOL_NAVBAR_INACTIVE_COLOR:
                return not selected
            raise SemanticGateClosed(
                "unexpected construction pool-navbar color contract"
            )

        match = MISSION_NAVBAR_PATTERN.fullmatch(name)
        if match is None:
            raise AlasSemanticUnmapped(
                "ALAS color resource is not semantically mapped: {0}".format(name)
            )
        context = self._require_mission_context()
        normalized_color = tuple(color)
        if normalized_color not in (MISSION_NAVBAR_ACTIVE_COLOR, MISSION_NAVBAR_INACTIVE_COLOR):
            raise SemanticGateClosed("unexpected mission navbar color contract")
        if not context.entry_clicked:
            raise SemanticGateClosed("default mission tab identity is not proven")
        observation = self._frame_or_live_observation_oracle()
        if not observation.enabled("task/page/back"):
            state = observation.read_state()
            back = observation._unique(state, "task/page/back")
            blockers = observation._blocking_rules(state, "task/page/back")
            if (back.active_in_hierarchy and back.active_and_enabled
                    and back.interactable and back.point is not None
                    and back.bounds is not None and back.bounds.contains(back.point)
                    and blockers and all(rule.blocker_id == 'loading' for rule in blockers)):
                # Both color probes are absent while the exact task shell is
                # loading. ALAS Navbar.get_info then returns no active item;
                # its original loop waits and acquires the next screenshot.
                return False
            raise SemanticGateClosed("default mission tab identity is not proven")
        index = int(match.group(1))
        selected = observation.image_selected(MISSION_NAVBAR_TARGETS[index])
        if normalized_color == MISSION_NAVBAR_ACTIVE_COLOR:
            return selected
        if normalized_color == MISSION_NAVBAR_INACTIVE_COLOR:
            return not selected
        raise SemanticGateClosed("unexpected mission navbar color contract")
