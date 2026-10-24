"""Opsi globe for the typed ALAS boundary."""

from __future__ import annotations

import re
import math
from typing import Tuple
from .contracts import (
    ActionReceipt,
    Bounds,
    OperationSirenGlobeState,
    OperationSirenGlobeSwipeReceipt,
    Point,
    UiState,
)
from .errors import SemanticGateClosed, SemanticTargetMissing, SemanticViewportReanchorRequired, SemanticGlobeSelectionMissed, SemanticInputBlocked, SemanticTargetNotActionable


class OpsiGlobeOracle:
    """Opsi globe operations sharing the oracle frame and input boundary."""

    @staticmethod
    def _globe_reset_days(text: str) -> int:
        days = re.fullmatch(r"距离大型作战重置\s*([0-9]+)\s*天", text)
        if days is not None:
            return int(days.group(1))
        tomorrow = re.fullmatch(r"大型作战将于明日\s*([0-9]{1,2})\s*点重置", text)
        if tomorrow is not None and 0 <= int(tomorrow.group(1)) < 24:
            # This native calendar label explicitly identifies the next day;
            # do not infer a duration or synthesize it from the host clock.
            return 1
        raise SemanticGateClosed("operation siren globe reset text is malformed")

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
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("game activity is not top-resumed")
        self._tap(int(round(target.point.x)), int(round(target.point.y)))
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("game activity changed after globe entry")

        def ready_globe():
            if self.operation_siren_exit_prompt_visible():
                if self.read_state().generation <= state.generation:
                    raise SemanticGateClosed("globe entry prompt is not newer than input")
                # Native navigation handles the expected leave confirmation
                # on its next screenshot; this port must not wait for that
                # loop to confirm while blocking inside its first click.
                return
            # The back Button can mount before its selected-zone panel. ALAS'
            # subsequent globe_update requires that complete typed panel.
            self.operation_siren_globe_state()
            if self.read_state().generation <= state.generation:
                raise SemanticGateClosed("globe entry destination is not newer than input")

        # One input, followed only by complete typed reads. This publication
        # wait leaves task selection and navigation with the original ALAS.
        self._retry_transition_read(ready_globe, attempts=32)
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
        reset_days = self._globe_reset_days(reset)
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
            reset_days=reset_days,
        )

    def operation_siren_globe_visible(self) -> bool:
        """Recognize the ready globe, including an unpinned detail panel."""

        try:
            self._require_operation_siren_globe_visible()
        except (SemanticGateClosed, SemanticTargetMissing):
            return False
        return True

    def _require_operation_siren_globe_visible(self):
        """Keep the original identity failure visible at the input boundary."""
        state = self.read_state()
        back = self._unique(state, "os/globe/map")
        if not (
            back.active_in_hierarchy
            and back.active_and_enabled
            and back.bounds is not None
        ):
            raise SemanticGateClosed('globe drag identity is unavailable')
        blockers = self._blocking_rules(state, 'os/globe/map')
        if blockers:
            raise SemanticGateClosed('globe is obscured: ' + ','.join(rule.blocker_id for rule in blockers))
        return state

    def operation_siren_globe_unpin(self, *, precondition_oracle=None) -> OperationSirenGlobeSwipeReceipt:
        """Dismiss one exact selected-zone pin with its required short drag."""

        source = self if precondition_oracle is None else precondition_oracle
        # Camera/panel easing can briefly cover every exported native anchor.
        # Retry only complete observation before input. The gesture and its
        # postcondition stay outside this read helper and are not repeated.
        def prepare():
            nonlocal source
            try:
                ui_state, candidates = source._operation_siren_globe_unpin_targets()
            except SemanticGateClosed:
                # A screenshot acquired during panel easing cannot become
                # complete by rereading that same immutable frame. The existing
                # bounded preparation retry must observe the live publication.
                source = self
                raise
            # Re-read the complete native proof if foreground or easing changes
            # during preparation. No gesture has been dispatched at this point.
            foreground = self._foreground_component()
            if foreground != self.fingerprint.component:
                raise SemanticGateClosed('game activity is not top-resumed before globe unpin: ' + foreground)
            # The explicit check above owns this adjacent state read.
            blockers = self._blocking_rules(self.read_state(check_foreground=False), 'os/globe/map')
            if blockers:
                raise SemanticGateClosed(
                    'operation siren globe is obscured before unpin: foreground='
                    + foreground + '; blockers='
                    + ','.join(rule.blocker_id for rule in blockers))
            return ui_state, candidates

        ui_state, candidates = self._retry_transition_read(prepare)
        # Unknown path proofs remain outside the read retry. Each native
        # candidate must still own its complete segment before one gesture.
        for start, end in candidates:
            if self.operation_siren_globe_drag_owned(start, end):
                break
        else:
            raise SemanticGateClosed('globe unpin path is outside the owned plane')
        pin_path = "SVFloatPanel(Clone)/point"
        foreground = self._foreground_component()
        blockers = self._blocking_rules(self.read_state(check_foreground=False), 'os/globe/map')
        if foreground != self.fingerprint.component or blockers:
            raise SemanticGateClosed(
                'globe changed after unpin drag proof: foreground=' + foreground
                + '; blockers=' + ','.join(rule.blocker_id for rule in blockers))
        # Let the Unity input loop observe movement across multiple frames.
        # A 600ms gesture has also selected its anchor instead of dragging.
        duration_ms = 2000
        self._swipe(*start, *end, duration_ms)
        for _ in range(16):
            self._sleep(0.25)
            after = self.read_ui_state(check_foreground=False)
            remaining = tuple(image for image in after.images
                              if image.path.endswith(pin_path) and image.active_in_hierarchy)
            if after.generation > ui_state.generation and not remaining:
                # Selecting another zone can briefly hide this panel too.
                # Match ALAS' one-second absence confirmation, then require
                # another fresh generation rather than accepting that gap.
                self._sleep(1.0)
                settled = self.read_ui_state()
                if settled.generation <= after.generation or any(
                        image.path.endswith(pin_path) and image.active_in_hierarchy
                        for image in settled.images):
                    continue
                if not self.operation_siren_globe_visible():
                    # Pin and globe publication can settle on different ticks.
                    # Keep waiting within this existing postcondition budget;
                    # no second gesture or success receipt is authorized here.
                    continue
                return OperationSirenGlobeSwipeReceipt(
                    "os/globe/zone/unpin", ui_state.generation, settled.generation, start, end, duration_ms)
        raise SemanticGateClosed("operation siren selected-zone unpin was not proven; no repeated drag")

    def _operation_siren_globe_unpin_targets(self):
        """Read the exact pin and existing native anchors without input."""
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
        geometry = ui_state.snapshot.get("globe_geometry", {})
        if (geometry.get("status") != 1 or geometry.get("truncated") is not False
                or geometry.get("error_count") != 0
                or geometry.get("camera_path") != "WorldMap3D/Main Camera"):
            raise SemanticGateClosed("operation siren unpin plane observation is unavailable")
        candidates = []
        for marker in geometry.get("objects", []):
            point = marker.get("input_point")
            port_point = marker.get('name') == 'port'
            map_point = marker.get('name') == 'map-projection' and marker.get('path') == 'WorldMap3D/entity/Plane/PointerInfo/GetMapScreenPos'
            if (not (port_point or map_point) or marker.get("truncated") is not False
                    or marker.get("plane_hit") is not True or marker.get("ui_clear") is not True
                    or marker.get("ui_top_path") not in ("", "WorldMap3D/entity/Plane")
                    or not marker.get("plane_instance_id")
                    or not isinstance(point, (list, tuple)) or len(point) != 2
                    or any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in point)):
                continue
            start = tuple(int(round(v)) for v in point)
            # Preserve ALAS handle_zone_pinned's (50, -50) request. A shorter
            # gesture can be interpreted as selecting the anchor's zone.
            end = (start[0] + 50, start[1] - 50)
            if all(Bounds(20, 220, 980, 620).contains(Point(*p)) for p in (start, end)):
                candidates.append((start, end))
        if not candidates:
            raise SemanticGateClosed("operation siren unpin has no unobscured typed plane target")
        # Prefer a proven plane anchor away from the selected pin itself.
        # Its projection can coincide with the pin during recentering; other
        # exported anchors remain subject to the same complete drag proof.
        candidates.sort(key=lambda pair: any(
            pins[0].bounds.contains(Point(*point)) for point in pair))
        # A selected panel can cover the default gesture's end while the
        # native anchor itself remains clear. Keep every default path first,
        # then review the same-length reverse drag from those exact anchors.
        # The caller proves the full native path and sends at most one drag.
        for start, _ in tuple(candidates):
            end = (start[0] - 50, start[1] + 50)
            if Bounds(20, 220, 980, 620).contains(Point(*end)):
                candidates.append((start, end))
        if all(pins[0].bounds.contains(Point(*start)) for start, _ in candidates):
            # Recentering can leave the only native anchor inside the selected
            # marker. A short gesture there can reselect it (live r8). Move
            # the same reviewed 50/-50 gesture to its next segment, and prove
            # every input sample on the native plane before sending it. This
            # changes neither the original ALAS intent nor the one-drag limit.
            outside = []
            for start, end in candidates:
                next_end = tuple(2 * b - a for a, b in zip(start, end))
                if (all(Bounds(20, 220, 980, 620).contains(Point(*p))
                        and not pins[0].bounds.contains(Point(*p)) for p in (end, next_end))):
                    outside.append((end, next_end))
            candidates = outside + candidates
        return ui_state, candidates

    def click_operation_siren_globe_map(self) -> ActionReceipt:
        """Return from the proven world map to its selected local zone."""

        state = self._require_operation_siren_globe_visible()
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

    def operation_siren_globe_port_projection(self, zone_id: int) -> Point:
        """Observe the live port projection, including outside the viewport."""
        if isinstance(zone_id, bool) or not isinstance(zone_id, int) or not 0 <= zone_id <= 7:
            raise SemanticGateClosed("operation siren port mapping is unavailable for this zone")
        if not self.operation_siren_globe_visible():
            raise SemanticGateClosed("operation siren globe identity is absent")
        ui = self.read_ui_state()
        geometry = ui.snapshot.get("globe_geometry", {})
        if (geometry.get("status") != 1 or geometry.get("truncated") is not False
                or geometry.get("error_count") != 0
                or geometry.get("camera_path") != "WorldMap3D/Main Camera"):
            raise SemanticGateClosed("operation siren port geometry is unavailable or incomplete")
        prefix = f"WorldMap3D/entity/sprite_scene/port_{zone_id + 1}/"
        markers = [row for row in geometry.get("objects", [])
                   if row.get("name") == "port" and row.get("path", "").startswith(prefix)]
        if len(markers) != 1 or markers[0].get("truncated") is not False:
            raise SemanticGateClosed("operation siren port marker is absent or ambiguous")
        anchor = markers[0].get("port_anchor")
        if (not isinstance(anchor, list) or len(anchor) != 3
                or any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in anchor)):
            raise SemanticGateClosed("operation siren port root anchor is unavailable")
        projection = markers[0].get("screen")
        if (not isinstance(projection, list) or len(projection) != 3
                or any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in projection)
                or projection[2] <= 0):
            raise SemanticGateClosed("operation siren port projection is unavailable")
        return Point(projection[0], projection[1])

    def _operation_siren_globe_map_projection_record(self, area_pos, *, check_foreground_on_return=True):
        return self._retry_transition_read(
            lambda: self._operation_siren_globe_map_projection_record_once(
                area_pos, check_foreground_on_return=check_foreground_on_return))

    def _operation_siren_globe_map_projection_record_once(self, area_pos, *, check_foreground_on_return=True):
        """Ask the game's PointerInfo to project the original ALAS area intent."""
        if (not isinstance(area_pos, (tuple, list)) or len(area_pos) != 2
                or any(isinstance(v, bool) or not isinstance(v, (int, float))
                       or not math.isfinite(v) for v in area_pos)):
            raise SemanticGateClosed('operation siren map intent is malformed')
        if not self.operation_siren_globe_visible():
            raise SemanticGateClosed('operation siren globe identity is absent')
        before = self.read_ui_state(check_foreground=False)
        ack = self._request('GET /v1/globe-projection %.9g %.9g\n' % tuple(area_pos))
        if (ack.get('status') != 'ok'
                or ack.get('scope') != 'read-only-map-projection'):
            raise SemanticGateClosed('native map projection capability is unavailable')
        for _ in range(20):
            self._sleep(0.1)
            ui = self.read_ui_state(check_foreground=False)
            geometry = ui.snapshot.get('globe_geometry', {})
            if ui.generation <= before.generation:
                continue
            if (geometry.get('status') != 1 or geometry.get('truncated') is not False
                    or geometry.get('error_count') != 0
                    or geometry.get('camera_path') != 'WorldMap3D/Main Camera'):
                raise SemanticGateClosed('native map geometry is incomplete')
            records = [r for r in geometry.get('objects', [])
                       if r.get('name') == 'map-projection'
                       and r.get('path') == 'WorldMap3D/entity/Plane/PointerInfo/GetMapScreenPos'
                       and isinstance(r.get('world_center'), list) and len(r['world_center']) == 3
                       and all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)
                               for v in r['world_center'])
                       # Unity receives float32; nine-digit JSON publication
                       # may differ from the caller's decimal representation.
                       and all(math.isclose(v, expected, rel_tol=2**-23, abs_tol=1e-6)
                               for v, expected in zip(r['world_center'][:2], area_pos))]
            if not records:
                continue
            if len(records) != 1 or records[0].get('truncated') is not False:
                raise SemanticGateClosed('native map projection is ambiguous or truncated')
            screen = records[0].get('screen')
            if (not isinstance(screen, list) or len(screen) != 3
                    or any(isinstance(v, bool) or not isinstance(v, (int, float))
                           or not math.isfinite(v) for v in screen) or screen[2] <= 0):
                raise SemanticGateClosed('native map projection is invalid')
            # The globe read proved foreground before this adjacent async
            # query group. Recheck once on its accepted frame instead of a
            # dumpsys roundtrip on every poll; input checks again at dispatch.
            if (check_foreground_on_return
                    and self._foreground_component() != self.fingerprint.component):
                raise SemanticGateClosed('foreground changed during native map projection')
            return ui, records[0]
        raise SemanticGateClosed('fresh native map projection is unavailable for this intent')

    def operation_siren_globe_map_projection(self, area_pos) -> Point:
        _, record = self._operation_siren_globe_map_projection_record(area_pos)
        return Point(*record['screen'][:2])

    def click_operation_siren_globe_map_zone(self, expected_zone_name: str, area_pos) -> ActionReceipt:
        """Select a non-port through native projection, then prove its named panel."""
        if not expected_zone_name:
            raise SemanticGateClosed('operation siren zone intent is absent')
        for attempt in range(4):
            ui, record = self._operation_siren_globe_map_projection_record(
                area_pos, check_foreground_on_return=False)
            # Keep the accepted projection and blocker snapshot adjacent.
            # A foreground roundtrip here can advance three generations even
            # on an idle globe. Identity is checked before the projection;
            # the mandatory final foreground check remains below, before input.
            state = self.read_state(check_foreground=False)
            if ui.generation <= state.generation <= ui.generation + 2:
                loading_root = 'OverlayCamera/Overlay/UIOverlay/Loading(Clone)'
                top = record.get('ui_top_path')
                loading = bool(
                    record.get('plane_hit') is True and record.get('ui_clear') is False
                    and isinstance(top, str)
                    and (top == loading_root or top.startswith(loading_root + '/'))
                    and all(rule.blocker_id == 'loading' for rule in
                            self._blocking_rules(state, 'os/globe/map')))
                if not loading or attempt == 3:
                    break
                # A known Loading hit can precede the actionable projection.
                # Reuse this existing read window; never tap its covered point.
            if attempt == 3:
                raise SemanticGateClosed('native zone projection snapshots are not coherent')
            self._sleep(0.25)
        point = record.get('input_point')
        if (record.get('plane_hit') is not True or record.get('ui_clear') is not True
                or not record.get('plane_instance_id')
                or not isinstance(point, list) or len(point) != 2
                or any(isinstance(v, bool) or not isinstance(v, (int, float))
                       or not math.isfinite(v) for v in point)):
            # No zone input was dispatched. Keep this readiness refusal in
            # the affected native task's existing failure/re-entry interval.
            raise SemanticTargetNotActionable('os/globe/zone/select', state.generation) from SemanticGateClosed(
                'native zone projection is not actionable: ' + repr(record))
        x, y = point
        if not Bounds(20, 220, 980, 620).contains(Point(x, y)):
            raise SemanticViewportReanchorRequired('native zone projection moved outside map sight; no input sent')
        blockers = self._blocking_rules(state, 'os/globe/map')
        foreground = self._foreground_component()
        if blockers or foreground != self.fingerprint.component:
            raise SemanticGateClosed('native zone projection is obscured or foreground changed: '
                + repr({'generation': state.generation,
                        'blockers': [rule.blocker_id for rule in blockers],
                        'foreground': foreground}))
        self._tap(int(round(x)), int(round(y)))
        for _ in range(24):
            self._sleep(0.25)
            candidate = self.read_ui_state()
            if candidate.generation <= ui.generation:
                continue
            try:
                name = self._operation_siren_globe_zone_name_from_ui(candidate)
            except SemanticGateClosed:
                continue
            if name != expected_zone_name:
                raise SemanticGateClosed('native zone selection resolved a different zone: ' + name)
            return ActionReceipt('os/globe/zone/select', ui.generation,
                                 Point(x, y), Bounds(x, y, x, y), record['path'])
        proof_generation = self._prove_unselected_globe_after_input(ui.generation)
        raise SemanticGlobeSelectionMissed(
            'native zone input produced no pin: ' + repr({
                'zone': expected_zone_name, 'area_pos': list(area_pos),
                'input_generation': ui.generation, 'proof_generation': proof_generation,
                'input_point': [x, y]}))

    def _prove_unselected_globe_after_input(self, input_generation: int) -> int:
        # The original ALAS pin loop retries a missed selection. Only hand
        # that decision back after two complete newer unselected globe frames;
        # ambiguous titles, another pin, blockers and stale frames stay closed.
        previous = input_generation
        for _ in range(2):
            self._sleep(0.25)
            candidate = self.read_ui_state()
            current = self.read_state(check_foreground=False)
            back = self._unique(current, 'os/globe/map')
            if (candidate.generation <= previous or candidate.image_truncated
                    or candidate.method_mask & 0xF != 0xF
                    or not candidate.generation <= current.generation <= candidate.generation + 2
                    or not back.active_in_hierarchy or not back.active_and_enabled
                    or not back.interactable or back.bounds is None or back.point is None
                    or not back.bounds.contains(back.point)
                    or self._blocking_rules(current, 'os/globe/map')
                    or self._foreground_component() != self.fingerprint.component
                    or any(text.path.endswith('SVFloatPanel(Clone)/point/line/bg/title/name/subText')
                           for text in candidate.texts)
                    or any(image.path.endswith('SVFloatPanel(Clone)/point')
                           and image.active_in_hierarchy for image in candidate.images)):
                raise SemanticGateClosed('native zone selection postcondition is unavailable')
            previous = candidate.generation
        return previous

    def click_operation_siren_globe_port(self, expected_zone_name: str, zone_id: int, *, native_mask=False) -> ActionReceipt:
        """Select an ALAS-owned port ID through its exact live game marker."""
        if isinstance(zone_id, bool) or not isinstance(zone_id, int) or not 0 <= zone_id <= 7:
            raise SemanticGateClosed("operation siren port mapping is unavailable for this zone")
        if not expected_zone_name or not self.operation_siren_globe_visible():
            raise SemanticGateClosed("operation siren globe identity or port intent is absent")
        minimum_generation = 0
        if native_mask:
            minimum_generation = self.read_ui_state().generation
            ack = self._request('GET /v1/globe-port-input %d\n' % (zone_id + 1))
            if ack.get('status') != 'ok' or ack.get('scope') != 'read-only-port-input':
                self._prove_unselected_globe_after_input(minimum_generation)
                raise SemanticGlobeSelectionMissed('native port input identity capability is unavailable')
            self._sleep(0.1)
        state = self.read_state()
        ui = self.read_ui_state(check_foreground=False)
        if not state.generation <= ui.generation <= state.generation + 2:
            raise SemanticGateClosed("operation siren port frames are incoherent")
        geometry = ui.snapshot.get("globe_geometry", {})
        if (geometry.get("schema") != "alas-headless.globe-geometry/v1"
                or geometry.get("status") != 1 or geometry.get("truncated") is not False
                or geometry.get("error_count") != 0
                or geometry.get("camera_path") != "WorldMap3D/Main Camera"):
            raise SemanticGateClosed("operation siren port geometry is unavailable or incomplete")
        # ALAS port IDs are zero-based (NY=0); the game's port objects
        # use one-based IDs. ALAS retains the canonical name/map metadata.
        prefix = f"WorldMap3D/entity/sprite_scene/port_{zone_id + 1}/"
        markers = [row for row in geometry.get("objects", [])
                   if row.get("name") == ("port-mask-input" if native_mask else "port")
                   and row.get("path", "").startswith(prefix)]
        if native_mask and not markers:
            self._prove_unselected_globe_after_input(minimum_generation)
            raise SemanticGlobeSelectionMissed('no exact game-owned port input point is available')
        if len(markers) != 1:
            raise SemanticGateClosed("operation siren port marker is absent or ambiguous")
        marker = markers[0]
        if native_mask:
            identity = marker.get('game_input')
            if (ui.generation <= minimum_generation or not isinstance(identity, dict)
                    or type(identity.get('entrance_id')) is not int
                    or identity['entrance_id'] != zone_id + 1
                    or not isinstance(identity.get('mask_color'), str)
                    or re.fullmatch('[0-9A-F]{6}', identity['mask_color']) is None):
                raise SemanticGateClosed('native port input does not prove the requested entrance')
        anchor = marker.get("port_anchor")
        if (not isinstance(anchor, list) or len(anchor) != 3
                or any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in anchor)):
            raise SemanticGateClosed("operation siren port root anchor is unavailable")
        point = marker.get("input_point")
        precise = marker.get("precise_input")
        proof = marker
        if "precise_input" in marker:
            if (not isinstance(precise, dict)
                    or precise.get("plane_hit") is not True
                    or precise.get("ui_clear") is not True
                    or not precise.get("plane_instance_id")):
                raise SemanticGateClosed("operation siren precise port projection is not actionable")
            point = precise.get("point")
            proof = precise
        if (marker.get("truncated") is not False or proof.get("plane_hit") is not True
                or proof.get("ui_clear") is not True or not proof.get("plane_instance_id")
                or not isinstance(point, list) or len(point) != 2
                or any(isinstance(v, bool) or not isinstance(v, (int, float))
                       or not math.isfinite(v) for v in point)):
            raise SemanticGateClosed("operation siren port marker is not actionable")
        x, y = map(float, point)
        if not Bounds(20, 220, 980, 620).contains(Point(x, y)):
            raise SemanticGateClosed("operation siren port marker is outside the map sight")
        if self._blocking_rules(state, "os/globe/map") or self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("operation siren port is obscured or foreground changed")
        if "precise_input" in marker:
            self._tap(x, y)
        else:
            self._tap(int(round(x)), int(round(y)))
        for _ in range(24):
            self._sleep(0.25)
            candidate = self.read_ui_state(check_foreground=False)
            if candidate.generation <= ui.generation:
                continue
            try:
                name = self._operation_siren_globe_zone_name_from_ui(candidate)
            except SemanticGateClosed:
                continue
            if name != expected_zone_name:
                raise SemanticGateClosed("operation siren port selection resolved a different zone: " + name)
            if self._foreground_component() != self.fingerprint.component:
                raise SemanticGateClosed("foreground changed after operation siren port selection")
            return ActionReceipt("os/globe/port/select", ui.generation,
                                 Point(x, y), Bounds(x, y, x, y), marker["path"])
        proof_generation = self._prove_unselected_globe_after_input(ui.generation)
        raise SemanticGlobeSelectionMissed(
            'native port input produced no pin: ' + repr({
                'zone': expected_zone_name, 'zone_id': zone_id,
                'input_generation': ui.generation, 'proof_generation': proof_generation,
                'input_point': [x, y],
                'port_path': marker['path'], 'port_anchor': anchor}))

    def click_operation_siren_globe_zone(
        self,
        expected_zone_name: str,
        point: Tuple[float, float],
    ) -> ActionReceipt:
        """Reject projected probes; selection requires a typed target."""
        raise SemanticGateClosed("operation siren projected zone probes are unsupported; use an exact typed marker")


    def operation_siren_globe_drag_proof(self, start, end):
        """Observe the native Plane IDragHandler without dispatching input."""
        from numbers import Integral
        if any(not isinstance(p, (tuple,list)) or len(p)!=2 for p in (start,end)):
            raise SemanticGateClosed('globe drag endpoint shape is invalid')
        if any(isinstance(v,bool) or not isinstance(v,Integral) or not 0<=v<limit
               for p in (start,end) for v,limit in zip(p,(1280,720))):
            raise SemanticGateClosed('globe drag endpoints are invalid')
        start=tuple(int(v) for v in start);end=tuple(int(v) for v in end)
        self._require_operation_siren_globe_visible()
        # The identity read just proved the foreground. These publications
        # form one read-only group; prove its foreground again before returning
        # rather than issuing dumpsys for every adjacent UI poll.
        before=self.read_ui_state(check_foreground=False)
        ack=self._request('GET /v1/globe-map-drag %d %d %d %d\n' % (*start,*end))
        if ack.get('status')!='ok' or ack.get('scope')!='read-only-globe-map-drag':
            raise SemanticGateClosed('globe native drag proof is unavailable')
        for _ in range(20):
            self._sleep(.1)
            ui=self.read_ui_state(check_foreground=False);proof=ui.snapshot.get('operation_siren_globe_drag',{})
            if ui.generation<=before.generation or proof.get('endpoints')!=list((*start,*end)):
                continue
            root='WorldMap3D/entity/Plane'
            if (proof.get('status')!=1 or proof.get('handler_path')!=root
                    or isinstance(proof.get('handler_instance_id'),bool)
                    or not isinstance(proof.get('handler_instance_id'),int)
                    or proof['handler_instance_id']==0):
                raise SemanticGateClosed('globe enabled drag handler is unavailable')
            samples=proof.get('samples')
            if not isinstance(samples,list) or len(samples)!=33:
                raise SemanticGateClosed('globe drag proof is incomplete')
            for i,row in enumerate(samples):
                expected=(start[0]+(end[0]-start[0])*i/32,start[1]+(end[1]-start[1])*i/32)
                if (not isinstance(row,dict) or not isinstance(row.get('owned'),bool)
                        or not isinstance(row.get('top_path'),str)
                        or any(isinstance(row.get(k),bool) or not isinstance(row.get(k),(int,float))
                            or not math.isfinite(row[k]) or abs(row[k]-value)>.002
                            for k,value in zip(('x','y'),expected))
                        or (row['owned'] and not (row['top_path']==root or row['top_path'].startswith(root+'/')))):
                    raise SemanticGateClosed('globe drag proof is malformed')
            if self._foreground_component() != self.fingerprint.component:
                raise SemanticGateClosed('game activity changed during globe drag proof')
            return ui.generation,proof
        raise SemanticGateClosed('fresh globe drag proof did not arrive')

    def operation_siren_globe_drag_owned(self, start, end):
        proof = self._settled_globe_drag_proof(start, end)
        return all(row['owned'] for row in proof['samples'])

    def operation_siren_globe_drag_candidate(self, start, end, *, box):
        """Propose at most one translation, preserving ALAS' complete vector.

        A rejected edge is only a placement hint. The translated integer path
        needs a new complete native proof; final dispatch proves it yet again.
        """
        proof = self._settled_globe_drag_proof(start, end)
        rows = proof['samples']
        if all(row['owned'] for row in rows):
            return tuple(start), tuple(end)
        owned = [i for i, row in enumerate(rows) if row['owned']]
        if not owned or owned != list(range(owned[0], owned[-1] + 1)):
            return None
        if owned[0] == 0:
            edge, anchor = rows[owned[-1]], end
        elif owned[-1] == len(rows) - 1:
            edge, anchor = rows[owned[0]], start
        else:
            return None
        offset = tuple(round(edge[key]) - value for key, value in zip(('x', 'y'), anchor))
        proposed_start = tuple(int(a + d) for a, d in zip(start, offset))
        proposed_end = tuple(int(a + d) for a, d in zip(end, offset))
        left, top, right, bottom = box
        if any(not (left <= x <= right and top <= y <= bottom)
               for x, y in (proposed_start, proposed_end)):
            return None
        fresh = self._settled_globe_drag_proof(proposed_start, proposed_end)
        if all(row['owned'] for row in fresh['samples']):
            return proposed_start, proposed_end
        return None

    def _settled_globe_drag_proof(self, start, end):
        # A loading overlay can appear between ALAS sampling and the final
        # handler proof. Reuse the existing loading-only wait before input.
        for attempt in range(30):
            blocked=self._blocking_rules(self.read_state(),'os/globe/map')
            if blocked:
                if any(v.blocker_id!='loading' for v in blocked):
                    raise SemanticGateClosed('globe is obscured during drag proof')
                if attempt==29:break
                self._sleep(.1);continue
            try:
                _,proof=self.operation_siren_globe_drag_proof(start,end)
            except SemanticGateClosed:
                blocked=self._blocking_rules(self.read_state(),'os/globe/map')
                if not blocked or any(v.blocker_id!='loading' for v in blocked):raise
                if attempt==29:break
                self._sleep(.1);continue
            blocked=self._blocking_rules(self.read_state(),'os/globe/map')
            if not blocked:
                if all(row['owned'] for row in proof['samples']):
                    return proof
                loading_path = 'OverlayCamera/Overlay/UIOverlay/Loading(Clone)'
                if all(row['owned'] or row['top_path'] == loading_path
                       or row['top_path'].endswith('/' + loading_path)
                       for row in proof['samples']):
                    # The proof can contain Loading from a preceding frame
                    # even after the adjacent blocker read says it is gone.
                    # Re-prove the same path; never use that covered proof.
                    if attempt == 29:
                        break
                    self._sleep(.1)
                    continue
                return proof
            if any(v.blocker_id!='loading' for v in blocked):
                raise SemanticGateClosed('globe became obscured during drag proof')
            if attempt==29:break
            self._sleep(.1)
        raise SemanticGateClosed('globe loading did not settle during drag proof')

    def operation_siren_globe_swipe(
        self,
        start: Tuple[int, int],
        end: Tuple[int, int],
        duration_ms: int,
    ) -> OperationSirenGlobeSwipeReceipt:
        """Dispatch one bounded globe-camera gesture and prove the globe survived."""

        if self._swipe is None:
            raise SemanticGateClosed("operation siren globe swipe backend is absent")
        for attempt in range(30):
            state = self.read_state()
            blockers = self._blocking_rules(state, 'os/globe/map')
            if blockers:
                if attempt == 29 or any(rule.blocker_id != 'loading' for rule in blockers):
                    raise SemanticGateClosed('operation siren globe is obscured before swipe: '
                                             + ','.join(rule.blocker_id for rule in blockers))
                self._sleep(0.1)
                continue
            back = self._unique(state, "os/globe/map")
            if not (back.active_in_hierarchy and back.active_and_enabled and back.bounds is not None):
                raise SemanticGateClosed("operation siren globe identity is absent")
            if self._foreground_component() != self.fingerprint.component:
                raise SemanticGateClosed("foreground changed before operation siren globe swipe")
            if not self.operation_siren_globe_drag_owned(start,end):
                raise SemanticGateClosed('globe camera path is outside the owned plane')
            if self._foreground_component() != self.fingerprint.component:
                raise SemanticGateClosed('globe changed after camera drag proof')
            blockers = self._blocking_rules(self.read_state(), 'os/globe/map')
            if not blockers:
                break
            if attempt == 29 or any(rule.blocker_id != 'loading' for rule in blockers):
                raise SemanticGateClosed('globe changed after camera drag proof')
            # The same bounded loading wait also covers a layer mounting
            # during proof. No input occurred; re-prove the entire path after
            # it clears rather than using the earlier proof through a loader.
            self._sleep(0.1)
        pre_generation = self._last_generation or 0
        # Retain ALAS' exact path while giving Unity the same input-frame
        # exposure as the reviewed unpin gesture on this headless runtime.
        duration_ms = max(duration_ms, 2000)
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
        blockers = self._blocking_rules(state, semantic_id)
        if blockers:
            raise SemanticInputBlocked(semantic_id, state.generation, tuple(rule.blocker_id for rule in blockers))
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed('foreground changed before globe zone entrance')
        if not (0 <= point.x < self.fingerprint.width and 0 <= point.y < self.fingerprint.height):
            raise SemanticGateClosed('globe zone entrance is outside the screen')
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
