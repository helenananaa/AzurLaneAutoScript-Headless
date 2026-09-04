"""Opsi globe for the typed ALAS boundary."""

from __future__ import annotations

import re
from typing import Tuple
from .contracts import (
    ActionReceipt,
    Bounds,
    OperationSirenGlobeState,
    OperationSirenGlobeSwipeReceipt,
    Point,
    UiState,
)
from .errors import SemanticGateClosed, SemanticTargetMissing


class OpsiGlobeOracle:
    """Opsi globe operations sharing the oracle frame and input boundary."""

    def click_operation_siren_globe(self) -> ActionReceipt:
        """Open the world map from a proven Operation Siren local map."""

        self.operation_siren_state()
        state = self.read_state()
        target = self._unique(state, "os/map/globe")
        if not (
            target.active_in_hierarchy
            and target.active_and_enabled
            and target.interactable
            and target.raycast_top is None
            and target.point is not None
            and target.bounds is not None
            and target.bounds.contains(target.point)
            and not self._blocking_rules(state, "os/map/globe")
        ):
            raise SemanticGateClosed("operation siren globe entrance is not actionable")
        self._tap(int(round(target.point.x)), int(round(target.point.y)))
        return ActionReceipt(
            semantic_id="os/map/globe",
            generation=state.generation,
            point=target.point,
            bounds=target.bounds,
            path=target.path,
        )

    @staticmethod
    def _operation_siren_globe_zone_name_from_ui(ui_state: UiState) -> str:
        path = "SVFloatPanel(Clone)/point/line/bg/title/name/subText"
        matches = tuple(
            text
            for text in ui_state.texts
            if text.path.endswith(path)
            and text.active_in_hierarchy
            and text.active_and_enabled
            and not text.truncated
            and text.bounds is not None
        )
        if len(matches) != 1:
            raise SemanticGateClosed(
                "operation siren selected-zone title is absent or ambiguous"
            )
        decorated = re.sub(r"<[^>]*>", "", matches[0].text).strip()
        zone_name = re.split(r"\s*[-—–－]\s*", decorated, maxsplit=1)[0].strip()
        if not zone_name:
            raise SemanticGateClosed("operation siren selected-zone title is empty")
        return zone_name

    def operation_siren_globe_state(self) -> OperationSirenGlobeState:
        """Read the selected zone and global exploration summary."""

        button_state = self.read_state()
        back = self._unique(button_state, "os/globe/map")
        if not (
            back.active_in_hierarchy
            and back.active_and_enabled
            and back.interactable
            and back.raycast_top is None
            and back.point is not None
            and back.bounds is not None
            and back.bounds.contains(back.point)
        ):
            raise SemanticGateClosed("operation siren globe identity is absent")
        # ``read_state`` just proved the foreground component and package-pinned
        # observer identity.  Read the adjacent UI projection without another
        # expensive dumpsys call, then enforce generation coherence below.
        ui_state = self.read_ui_state(check_foreground=False)
        if not (
            button_state.generation
            <= ui_state.generation
            <= button_state.generation + 2
        ):
            raise SemanticGateClosed("operation siren globe snapshots are not coherent")

        def suffix(path: str) -> str:
            matches = tuple(
                text
                for text in ui_state.texts
                if text.path.endswith(path)
                and text.active_in_hierarchy
                and text.active_and_enabled
                and not text.truncated
                and text.bounds is not None
            )
            if len(matches) != 1:
                raise SemanticGateClosed(
                    "operation siren globe text is absent or ambiguous: " + path
                )
            return re.sub(r"<[^>]*>", "", matches[0].text).strip()

        zone_name = self._operation_siren_globe_zone_name_from_ui(ui_state)
        # The globe pin decorates the canonical zone name with its current
        # state (for example ``NA海域西北D-安全海域``).  ALAS owns
        # zone resolution and its Zone table contains the undecorated name,
        # just like the local-map OCR path after it removes the same suffix.
        # Keep the typed boundary equivalent by exposing only that base name.
        zone_type = suffix("SVFloatPanel(Clone)/point/line/bg/icon/marking/Text")
        danger = suffix("SVFloatPanel(Clone)/point/line/bg/danger_text")
        zone_progress = suffix(
            "SVFloatPanel(Clone)/point/line/bg/title/achievement/number"
        )
        world_root = "top/adapt/right_chapter/line/display_panel/world_info/"
        world_progress = suffix(world_root + "explore/achievement/number")
        suppression = suffix(world_root + "explore/pressing/number")
        mileage = suffix(world_root + "explore/mileage/number")
        fleet_power = suffix(world_root + "power/bg/Number")
        offense = suffix(world_root + "buff/buff_damage/Text")
        survival = suffix(world_root + "buff/buff_health/Text")
        tactical = suffix(world_root + "buff/buff_attack/Text")
        reset = suffix("top/adapt/top_chapter/reset_coutdown/Text")

        def fraction(value: str, label: str) -> Tuple[int, int]:
            match = re.fullmatch(r"([0-9]+)/([0-9]+)", value)
            if match is None:
                raise SemanticGateClosed("operation siren " + label + " is malformed")
            actual, capacity = map(int, match.groups())
            if actual > capacity:
                raise SemanticGateClosed(
                    "operation siren " + label + " is inconsistent"
                )
            return actual, capacity

        zone_actual, zone_capacity = fraction(zone_progress, "zone progress")
        world_actual, world_capacity = fraction(world_progress, "world progress")
        reset_match = re.fullmatch(r"距离大型作战重置\s*([0-9]+)\s*天", reset)
        integer_values = (
            danger,
            suppression,
            mileage,
            fleet_power,
            offense,
            survival,
            tactical,
        )
        if (
            not zone_name
            or zone_type
            not in {
                "危险海域",
                "普通海域",
                "安全海域",
                "隐秘海域",
                "深渊海域",
                "塞壬要塞",
                "档案海域",
                "未知海域",
            }
            or world_capacity == 0
            or reset_match is None
            or any(re.fullmatch(r"[0-9]+", value) is None for value in integer_values)
        ):
            raise SemanticGateClosed("operation siren globe summary is malformed")
        if zone_type == "塞壬要塞":
            stronghold_images = {
                "SVFloatPanel(Clone)/point/line/bg/icon": "daxuanwo",
                "SVFloatPanel(Clone)/point/line/bg/icon/marking": "mark_danger",
                "SVFloatPanel(Clone)/point/line/bg/icon/marking/mark_bg": (
                    "mark_bg_danger"
                ),
                "SVFloatPanel(Clone)/point/line/bg/sairen": "sairen_mask",
                "SVFloatPanel(Clone)/point/line/bg": "bg_danger",
                "SVFloatPanel(Clone)/point/line": "click_point_danger",
                "SVFloatPanel(Clone)/point": "click_point_danger",
            }
            for path, sprite in stronghold_images.items():
                matches = tuple(
                    image
                    for image in ui_state.images
                    if image.path.endswith(path)
                    and image.sprite == sprite
                    and image.active_in_hierarchy
                    and image.active_and_enabled
                    and not image.truncated
                    and image.bounds is not None
                )
                if len(matches) != 1:
                    raise SemanticGateClosed(
                        "operation siren stronghold marker is absent or ambiguous"
                    )
        return OperationSirenGlobeState(
            zone_name=zone_name,
            zone_type=zone_type,
            danger_level=int(danger),
            zone_achievement=zone_actual,
            zone_achievement_capacity=zone_capacity,
            world_achievement=world_actual,
            world_achievement_capacity=world_capacity,
            suppression=int(suppression),
            mileage=int(mileage),
            fleet_power=int(fleet_power),
            offense_adaptability=int(offense),
            survival_adaptability=int(survival),
            tactical_adaptability=int(tactical),
            reset_days=int(reset_match.group(1)),
        )

    def operation_siren_globe_visible(self) -> bool:
        """Recognize the ready globe, including an unpinned detail panel."""

        try:
            state = self.read_state()
            back = self._unique(state, "os/globe/map")
        except (SemanticGateClosed, SemanticTargetMissing):
            return False
        return bool(
            back.active_in_hierarchy
            and back.active_and_enabled
            and back.bounds is not None
            and not self._blocking_rules(state, "os/globe/map")
        )

    def operation_siren_globe_unpin(self) -> OperationSirenGlobeSwipeReceipt:
        """Dismiss one exact selected-zone pin with its required short drag."""

        self.operation_siren_globe_state()
        ui_state = self.read_ui_state(check_foreground=False)
        pin_path = "SVFloatPanel(Clone)/point"
        pins = tuple(
            image
            for image in ui_state.images
            if image.name == "point"
            and image.path.endswith(pin_path)
            and image.sprite
            in {"click_point_safe", "click_point_danger", "click_point_normal"}
            and image.active_in_hierarchy
            and image.active_and_enabled
            and not image.truncated
            and image.bounds is not None
        )
        if len(pins) != 1:
            raise SemanticGateClosed(
                "operation siren selected-zone pin is absent or ambiguous"
            )
        if self._swipe is None:
            raise SemanticGateClosed("operation siren globe swipe backend is absent")
        initial_generation = ui_state.generation
        for delta_x, delta_y in (
            (-32, -24),
            (32, -24),
            (-32, 24),
            (32, 24),
        ):
            candidate = self.read_ui_state()
            current_pins = tuple(
                image
                for image in candidate.images
                if image.name == "point"
                and image.path.endswith(pin_path)
                and image.sprite
                in {"click_point_safe", "click_point_danger", "click_point_normal"}
                and image.active_in_hierarchy
                and image.active_and_enabled
                and not image.truncated
                and image.bounds is not None
            )
            if len(current_pins) != 1:
                raise SemanticGateClosed(
                    "operation siren selected-zone pin changed before unpin"
                )
            bounds = current_pins[0].bounds
            assert bounds is not None
            start = (
                int(round((bounds.left + bounds.right) / 2.0)),
                int(round((bounds.top + bounds.bottom) / 2.0)),
            )
            end = (start[0] + delta_x, start[1] + delta_y)
            if not Bounds(20.0, 220.0, 980.0, 620.0).contains(Point(*end)):
                continue
            if self._foreground_component() != self.fingerprint.component:
                raise SemanticGateClosed(
                    "foreground changed before operation siren selected-zone unpin"
                )
            if self._blocking_rules(self.read_state(), "os/globe/map"):
                raise SemanticGateClosed("operation siren globe is obscured before unpin")
            self._swipe(start[0], start[1], end[0], end[1], 150)
            post_generation = None
            # Do not issue another drag before a slow observer has had time
            # to publish the first drag's outcome.
            for _ in range(16):
                self._sleep(0.25)
                try:
                    after = self.read_ui_state(check_foreground=False)
                except SemanticGateClosed:
                    continue
                remaining = tuple(
                    image
                    for image in after.images
                    if image.path.endswith(pin_path)
                    and image.active_in_hierarchy
                )
                if (
                    after.generation > candidate.generation
                    and not remaining
                ):
                    post_generation = after.generation
                    break
            if post_generation is not None:
                if not self.operation_siren_globe_visible():
                    raise SemanticGateClosed(
                        "operation siren globe disappeared after selected-zone unpin"
                    )
                return OperationSirenGlobeSwipeReceipt(
                    semantic_id="os/globe/zone/unpin",
                    pre_generation=initial_generation,
                    post_generation=post_generation,
                    start=start,
                    end=end,
                    duration_ms=150,
                )
        raise SemanticGateClosed(
            "operation siren selected-zone unpin was not proven"
        )

    def click_operation_siren_globe_map(self) -> ActionReceipt:
        """Return from the proven world map to its selected local zone."""

        if not self.operation_siren_globe_visible():
            raise SemanticGateClosed("operation siren globe identity is absent")
        state = self.read_state()
        target = self._unique(state, "os/globe/map")
        assert target.point is not None and target.bounds is not None
        self._tap(int(round(target.point.x)), int(round(target.point.y)))
        return ActionReceipt(
            semantic_id="os/globe/map",
            generation=state.generation,
            point=target.point,
            bounds=target.bounds,
            path=target.path,
        )

    def click_operation_siren_globe_zone(
        self,
        expected_zone_name: str,
        point: Tuple[float, float],
    ) -> ActionReceipt:
        """Select one ALAS-resolved globe zone and prove the typed pin changed."""

        if not self.operation_siren_globe_visible():
            raise SemanticGateClosed("operation siren globe identity is absent")
        before_ui = self.read_ui_state(check_foreground=False)
        before_name = None
        try:
            before_name = self._operation_siren_globe_zone_name_from_ui(before_ui)
        except SemanticGateClosed:
            # A camera drag intentionally unpins the previous zone.  The new
            # target is still proven below by its exact typed detail title.
            pass
        if not expected_zone_name or expected_zone_name == before_name:
            raise SemanticGateClosed("operation siren globe zone intent is invalid")
        if (
            not isinstance(point, tuple)
            or len(point) != 2
            or any(
                isinstance(value, bool) or not isinstance(value, (int, float))
                for value in point
            )
        ):
            raise SemanticGateClosed("operation siren globe zone point is malformed")
        x, y = (int(round(point[0])), int(round(point[1])))
        safe = Bounds(20.0, 220.0, 980.0, 620.0)
        target_point = Point(float(x), float(y))
        if not safe.contains(target_point):
            raise SemanticGateClosed(
                "operation siren globe zone point is outside the map"
            )

        if self._blocking_rules(self.read_state(), "os/globe/map"):
            raise SemanticGateClosed("operation siren globe is obscured before selection")
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("foreground changed before operation siren globe selection")
        self._tap(x, y)
        selected_name = None
        selected_generation = None
        previous_candidate = None
        # Wait through the observer's two-second publication cadence before
        # ALAS may try another probe. Otherwise a late pin from the previous
        # tap can be incorrectly attributed to the next one.
        for _ in range(24):
            self._sleep(0.25)
            try:
                candidate = self.read_ui_state(check_foreground=False)
                candidate_name = self._operation_siren_globe_zone_name_from_ui(
                    candidate
                )
            except SemanticGateClosed:
                continue
            if candidate.generation <= before_ui.generation:
                continue
            if candidate_name != before_name:
                # The float panel animates its map anchor after selection.
                # Re-observe the same title in the following publication so
                # ALAS does not calibrate its camera from a moving pin.
                if (previous_candidate is not None
                        and previous_candidate[0] == candidate_name
                        and candidate.generation > previous_candidate[1]):
                    selected_generation = candidate.generation
                    selected_name = None if candidate_name == expected_zone_name else candidate_name
                    break
                if previous_candidate is None or previous_candidate[0] != candidate_name:
                    previous_candidate = (candidate_name, candidate.generation)
        if selected_generation is None:
            raise SemanticGateClosed(
                "operation siren globe zone selection was not proven"
            )
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed(
                "game activity changed after operation siren globe zone input"
            )
        return ActionReceipt(
            semantic_id=(
                "os/globe/zone/select"
                if selected_name is None
                else "os/globe/zone/select-mismatch"
            ),
            generation=selected_generation,
            point=target_point,
            bounds=Bounds(float(x - 8), float(y - 8), float(x + 8), float(y + 8)),
            path="operation-siren/globe/zone/" + expected_zone_name,
        )

    def operation_siren_globe_swipe(
        self,
        start: Tuple[int, int],
        end: Tuple[int, int],
        duration_ms: int,
    ) -> OperationSirenGlobeSwipeReceipt:
        """Dispatch one bounded globe-camera gesture and prove the globe survived."""

        if self._swipe is None:
            raise SemanticGateClosed("operation siren globe swipe backend is absent")
        state = self.read_state()
        back = self._unique(state, "os/globe/map")
        if not (
            back.active_in_hierarchy
            and back.active_and_enabled
            and back.bounds is not None
        ):
            raise SemanticGateClosed("operation siren globe identity is absent")
        if self._blocking_rules(state, "os/globe/map"):
            raise SemanticGateClosed("operation siren globe is obscured before swipe")
        pre_generation = self._last_generation or 0
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed(
                "foreground changed before operation siren globe swipe"
            )
        self._swipe(start[0], start[1], end[0], end[1], duration_ms)
        post_generation = None
        for _ in range(12):
            self._sleep(0.25)
            try:
                candidate = self.read_state()
                candidate_back = self._unique(candidate, "os/globe/map")
            except (SemanticGateClosed, SemanticTargetMissing):
                continue
            if (
                candidate.generation > pre_generation
                and candidate_back.active_in_hierarchy
                and candidate_back.active_and_enabled
                and candidate_back.bounds is not None
            ):
                post_generation = candidate.generation
                break
        if post_generation is None:
            raise SemanticGateClosed(
                "operation siren globe swipe post-state was not proven"
            )
        return OperationSirenGlobeSwipeReceipt(
            semantic_id="os/globe/swipe",
            pre_generation=pre_generation,
            post_generation=post_generation,
            start=start,
            end=end,
            duration_ms=duration_ms,
        )

    def click_operation_siren_globe_zone_enter(self, expected_zone_name=None) -> ActionReceipt:
        """Enter the exact currently pinned Operation Siren zone."""

        pinned = self.operation_siren_globe_state()
        if expected_zone_name is not None and pinned.zone_name != expected_zone_name:
            raise SemanticGateClosed('operation siren pinned zone changed before entrance')
        state = self.read_state()
        targets = tuple(
            semantic_id
            for semantic_id in (
                "os/globe/zone-enter",
                "os/globe/zone-return",
                "os/globe/zone-back",
            )
            if len(self._matches(state, semantic_id)) == 1
        )
        if len(targets) != 1:
            raise SemanticGateClosed(
                "operation siren globe zone entrance is absent or ambiguous"
            )
        semantic_id = targets[0]
        target = self._unique(state, semantic_id)
        if not (
            target.active_in_hierarchy
            and target.active_and_enabled
            and target.interactable
            and target.raycast_top is None
            and target.bounds is not None
        ):
            raise SemanticGateClosed(
                "operation siren globe zone entrance is not actionable"
            )
        point = Point(
            (target.bounds.left + target.bounds.right) / 2.0,
            (target.bounds.top + target.bounds.bottom) / 2.0,
        )
        self._tap(int(round(point.x)), int(round(point.y)))
        return ActionReceipt(
            semantic_id=semantic_id,
            generation=state.generation,
            point=point,
            bounds=target.bounds,
            path=target.path,
        )

    def operation_siren_globe_zone_locked(self) -> bool:
        self.operation_siren_globe_state()
        ui = self.read_ui_state()
        values = [v for v in ui.texts if v.active_in_hierarchy and v.active_and_enabled
                  and v.path.endswith('SVFloatPanel(Clone)/point/line/bg/lock/Text')]
        if not values:
            return False
        if len(values) != 1 or values[0].truncated or values[0].text != '周边海域未压制':
            raise SemanticGateClosed('operation siren zone lock reason is unsupported')
        return True

    def click_operation_siren_globe_zone_switch(self) -> ActionReceipt:
        """Open the exact zone-type selector on the currently pinned zone."""

        self.operation_siren_globe_state()
        state = self.read_state()
        target = self._unique(state, "os/globe/zone-switch")
        if not (
            target.active_in_hierarchy
            and target.active_and_enabled
            and target.interactable
            and target.point is not None
            and target.bounds is not None
            and target.bounds.contains(target.point)
        ):
            raise SemanticGateClosed(
                "operation siren globe zone switch is not actionable"
            )
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("game activity changed before zone switch input")
        self._tap(int(round(target.point.x)), int(round(target.point.y)))
        return ActionReceipt(
            semantic_id="os/globe/zone-switch",
            generation=state.generation,
            point=target.point,
            bounds=target.bounds,
            path=target.path,
        )

    def operation_siren_globe_zone_types(self) -> Tuple[str, ...]:
        """Return the exact ALAS zone types offered by the open selector."""

        state = self.read_state()
        mask = self._unique(state, "os/globe/zone-type-mask")
        if not (
            mask.active_in_hierarchy
            and mask.active_and_enabled
            and mask.interactable
            and mask.bounds is not None
        ):
            raise SemanticGateClosed("operation siren zone-type selector is absent")
        ui_state = self.read_ui_state()
        root = "SVFloatPanel(Clone)/select_mask/marking/toggles/"
        display_to_type = {
            "普通海域": "DANGEROUS",
            "危险海域": "DANGEROUS",
            "安全海域": "SAFE",
            "隐秘海域": "OBSCURE",
            "深渊海域": "ABYSSAL",
            "塞壬要塞": "STRONGHOLD",
            "档案海域": "ARCHIVE",
            "未知海域": "UNKNOWN",
        }
        labels = tuple(
            text
            for text in ui_state.texts
            if root in text.path
            and text.path.endswith("/Text")
            and text.active_in_hierarchy
            and text.active_and_enabled
            and not text.truncated
            and text.bounds is not None
        )
        if not labels or any(text.text.strip() not in display_to_type for text in labels):
            raise SemanticGateClosed("operation siren zone-type label is unknown")
        normalized = tuple(display_to_type[text.text.strip()] for text in labels)
        if len(set(normalized)) != len(normalized):
            raise SemanticGateClosed("operation siren zone-type selector is ambiguous")
        return normalized

    def click_operation_siren_globe_zone_type(
        self, expected_type: str
    ) -> ActionReceipt:
        """Select one exact typed alternative from the open zone selector."""

        if expected_type not in {
            "DANGEROUS", "SAFE", "OBSCURE", "ABYSSAL", "STRONGHOLD", "ARCHIVE"
        }:
            raise SemanticGateClosed("operation siren zone type is malformed")
        if expected_type not in self.operation_siren_globe_zone_types():
            raise SemanticGateClosed("operation siren zone type is unavailable")
        ui_state = self.read_ui_state()
        type_to_labels = {
            "DANGEROUS": {"普通海域", "危险海域"},
            "SAFE": {"安全海域"},
            "OBSCURE": {"隐秘海域"},
            "ABYSSAL": {"深渊海域"},
            "STRONGHOLD": {"塞壬要塞"},
            "ARCHIVE": {"档案海域"},
        }
        root = "SVFloatPanel(Clone)/select_mask/marking/toggles/"
        targets = tuple(
            text
            for text in ui_state.texts
            if root in text.path
            and text.path.endswith("/Text")
            and text.text.strip() in type_to_labels[expected_type]
            and text.active_in_hierarchy
            and text.active_and_enabled
            and not text.truncated
            and text.bounds is not None
        )
        if len(targets) != 1:
            raise SemanticGateClosed("operation siren zone-type target is ambiguous")
        target = targets[0]
        assert target.bounds is not None
        point = Point(
            (target.bounds.left + target.bounds.right) / 2.0,
            (target.bounds.top + target.bounds.bottom) / 2.0,
        )
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("game activity changed before zone-type input")
        self._tap(int(round(point.x)), int(round(point.y)))
        for _ in range(12):
            self._sleep(0.25)
            try:
                after = self.operation_siren_globe_state()
            except SemanticGateClosed:
                continue
            if after.zone_type in type_to_labels[expected_type]:
                break
        else:
            raise SemanticGateClosed(
                "operation siren zone-type selection was not proven"
            )
        return ActionReceipt(
            semantic_id="os/globe/zone-type/" + expected_type.lower(),
            generation=ui_state.generation,
            point=point,
            bounds=target.bounds,
            path=target.path,
        )
