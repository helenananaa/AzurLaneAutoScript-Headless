"""Core for the typed ALAS boundary."""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
import threading
import time
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple
from .blockers import DEFAULT_BLOCKERS
from .button_targets import DEFAULT_TARGETS
from .contracts import (
    ActionReceipt,
    BUTTON_SCHEMA,
    BlockerRule,
    Bounds,
    ButtonState,
    GemsFarmingEquipmentLoadout,
    ImageState,
    IndexedTextGroup,
    OBSERVER_SCHEMA,
    OracleFingerprint,
    OracleState,
    Point,
    SemanticImageTarget,
    SemanticTarget,
    SemanticTextTarget,
    SemanticToggleTarget,
    TextState,
    ToggleState,
    UI_SCHEMA,
    UiState,
)
from .errors import ObserverTransportError, SemanticGateClosed, SemanticOracleError
from .surfaces import ObservationSurface, observation_surface_present, observation_prompt_kind
from .transport import observer_snapshot_semantic_ready, request_observer_state
from .ui_targets import (
    DEFAULT_IMAGE_TARGETS,
    DEFAULT_TEXT_TARGETS,
    DEFAULT_TOGGLE_TARGETS,
)


class CoreOracle:
    """Core operations sharing the oracle frame and input boundary."""

    def __init__(
        self,
        request: Callable[[str], Mapping[str, Any]],
        foreground_component: Callable[[], str],
        tap: Callable[[int, int], None],
        fingerprint: OracleFingerprint,
        targets: Iterable[SemanticTarget] = DEFAULT_TARGETS,
        image_targets: Iterable[SemanticImageTarget] = DEFAULT_IMAGE_TARGETS,
        toggle_targets: Iterable[SemanticToggleTarget] = DEFAULT_TOGGLE_TARGETS,
        text_targets: Iterable[SemanticTextTarget] = DEFAULT_TEXT_TARGETS,
        blockers: Iterable[BlockerRule] = DEFAULT_BLOCKERS,
        monotonic: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
        swipe: Optional[Callable[[int, int, int, int, int], None]] = None,
    ) -> None:
        self._request = request
        self._foreground_component = foreground_component
        self._tap_backend = tap
        self._input_dispatch_lock = threading.Lock()
        self._input_dispatch_count = 0
        self._tap = self._dispatch_tap
        self.fingerprint = fingerprint
        self._targets = self._index_targets(targets)
        self._image_targets = self._index_image_targets(image_targets)
        self._toggle_targets = self._index_toggle_targets(toggle_targets)
        self._text_targets = self._index_text_targets(text_targets)
        self._blockers = tuple(blockers)
        self._monotonic = monotonic
        self._sleep = sleep
        self._swipe_backend = swipe
        self._swipe = self._dispatch_swipe if swipe is not None else None
        self._last_generation: Optional[int] = None
        self._login_update_seen = False
        self._login_update_retry_attempted = False
        self._login_update_restart_consumed = False
        self._gems_farming_equipment_loadouts: Dict[
            str, GemsFarmingEquipmentLoadout
        ] = {}
        self._gems_farming_open_slot_context: Optional[Tuple[str, str, int]] = None
        self._gems_farming_hard_open_slot_context: Optional[
            Tuple[str, int, str, Tuple[str, ...]]
        ] = None

    @property
    def input_dispatch_count(self) -> int:
        with self._input_dispatch_lock:
            return self._input_dispatch_count

    def _mark_input_dispatched(self) -> None:
        with self._input_dispatch_lock:
            self._input_dispatch_count += 1

    def _dispatch_tap(self, x: int, y: int) -> None:
        self._mark_input_dispatched()
        self._tap_backend(x, y)

    def _dispatch_swipe(
        self, x1: int, y1: int, x2: int, y2: int, duration_ms: int
    ) -> None:
        self._mark_input_dispatched()
        assert self._swipe_backend is not None
        self._swipe_backend(x1, y1, x2, y2, duration_ms)

    def _retry_transition_read(
        self,
        reader: Callable[[], Any],
        *,
        attempts: int = 4,
        interval_seconds: float = 0.25,
    ) -> Any:
        """Retry a read-only typed view while a Unity transition settles.

        A generation can briefly expose a newly active Button tree before all
        Images on that page have settled. Retrying the complete typed read does
        not relax a gate: the final attempt must still satisfy every original
        exactness check. The helper never injects input, and callers that act
        re-read the actionable Button immediately before the tap.
        """

        if attempts < 1:
            raise ValueError("transition read attempts must be positive")
        last_error: Optional[SemanticOracleError] = None
        for attempt in range(attempts):
            try:
                return reader()
            except (SemanticGateClosed, ObserverTransportError) as exc:
                last_error = exc
                if attempt + 1 < attempts:
                    self._sleep(interval_seconds)
        assert last_error is not None
        raise last_error

    @staticmethod
    def _index_targets(
        targets: Iterable[SemanticTarget],
    ) -> Dict[str, SemanticTarget]:
        indexed: Dict[str, SemanticTarget] = {}
        for target in targets:
            if target.semantic_id in indexed:
                raise ValueError(
                    "duplicate semantic target id: {0}".format(target.semantic_id)
                )
            if not target.name or not target.path_suffix:
                raise ValueError("semantic target mappings must be non-empty")
            indexed[target.semantic_id] = target
        return indexed

    @staticmethod
    def _index_image_targets(
        targets: Iterable[SemanticImageTarget],
    ) -> Dict[str, SemanticImageTarget]:
        indexed: Dict[str, SemanticImageTarget] = {}
        for target in targets:
            if target.semantic_id in indexed:
                raise ValueError(
                    "duplicate semantic image target id: {0}".format(target.semantic_id)
                )
            if (
                not target.path_parent_suffix
                or not target.selected_sprite
                or not target.inactive_sprite
            ):
                raise ValueError("semantic image target mappings must be non-empty")
            indexed[target.semantic_id] = target
        return indexed

    @staticmethod
    def _index_toggle_targets(
        targets: Iterable[SemanticToggleTarget],
    ) -> Dict[str, SemanticToggleTarget]:
        indexed: Dict[str, SemanticToggleTarget] = {}
        for target in targets:
            if target.semantic_id in indexed:
                raise ValueError(
                    "duplicate semantic toggle target id: {0}".format(
                        target.semantic_id
                    )
                )
            if not target.semantic_id or not target.name or not target.path_suffix:
                raise ValueError("semantic toggle target mappings must be non-empty")
            indexed[target.semantic_id] = target
        return indexed

    @staticmethod
    def _index_text_targets(
        targets: Iterable[SemanticTextTarget],
    ) -> Dict[str, SemanticTextTarget]:
        indexed: Dict[str, SemanticTextTarget] = {}
        for target in targets:
            if target.semantic_id in indexed:
                raise ValueError(
                    "duplicate semantic text target id: {0}".format(target.semantic_id)
                )
            if (
                not target.semantic_id
                or not target.path_suffix
                or not target.expected_texts
                or any(not value for value in target.expected_texts)
            ):
                raise ValueError("semantic text target mappings must be non-empty")
            indexed[target.semantic_id] = target
        return indexed

    @staticmethod
    def _integer(value: Any, field: str) -> int:
        if isinstance(value, bool) or not isinstance(value, int):
            raise SemanticGateClosed("invalid integer field: {0}".format(field))
        return value

    @staticmethod
    def _finite_number(value: Any, field: str) -> float:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise SemanticGateClosed("invalid numeric field: {0}".format(field))
        result = float(value)
        if not math.isfinite(result):
            raise SemanticGateClosed("non-finite numeric field: {0}".format(field))
        return result

    def _validate_identity(
        self,
        value: Mapping[str, Any],
        semantic_schema: Optional[str] = None,
        *,
        allow_stale: bool = False,
    ) -> None:
        if value.get("protocol_schema") != OBSERVER_SCHEMA:
            raise SemanticGateClosed("observer protocol schema mismatch")
        if (
            semantic_schema is not None
            and value.get("semantic_schema") != semantic_schema
        ):
            raise SemanticGateClosed("semantic schema mismatch")
        if value.get("status") != "ok":
            raise SemanticGateClosed("observer status is not ok")
        if value.get("package") != self.fingerprint.package:
            raise SemanticGateClosed("observer package mismatch")
        if value.get("driver_revision") != self.fingerprint.driver_revision:
            raise SemanticGateClosed(
                "observer driver revision mismatch: observed={0!r}, "
                "expected={1!r}".format(
                    value.get("driver_revision"),
                    self.fingerprint.driver_revision,
                )
            )
        if (
            self._integer(value.get("peer_uid"), "peer_uid")
            != self.fingerprint.peer_uid
        ):
            raise SemanticGateClosed("observer peer credential mismatch")
        if (
            self.fingerprint.expected_pid is not None
            and self._integer(value.get("pid"), "pid") != self.fingerprint.expected_pid
        ):
            raise SemanticGateClosed("observer PID mismatch")
        if (
            not allow_stale
            and self._integer(value.get("age_ms"), "age_ms")
            > self.fingerprint.max_age_ms
        ):
            raise SemanticGateClosed("observer snapshot is stale")

    def _parse_button(self, raw: Any) -> ButtonState:
        if not isinstance(raw, Mapping):
            raise SemanticGateClosed("button record is not an object")
        name = raw.get("name")
        path = raw.get("path")
        if (
            not isinstance(name, str)
            or not isinstance(path, str)
            or not name
            or not path
        ):
            raise SemanticGateClosed("button identity is incomplete")
        flags = self._integer(raw.get("flags", 0), "button flags")
        if flags & 0x200:
            raise SemanticGateClosed("button identity is truncated")

        point_value = raw.get("adb_point")
        bounds_value = raw.get("adb_bounds")
        point = None
        bounds = None
        if point_value is not None:
            if not isinstance(point_value, Mapping):
                raise SemanticGateClosed("button point is malformed")
            point = Point(
                self._finite_number(point_value.get("x"), "adb_point.x"),
                self._finite_number(point_value.get("y"), "adb_point.y"),
            )
        if bounds_value is not None:
            if not isinstance(bounds_value, Mapping):
                raise SemanticGateClosed("button bounds are malformed")
            candidate_bounds = Bounds(
                self._finite_number(bounds_value.get("left"), "adb_bounds.left"),
                self._finite_number(bounds_value.get("top"), "adb_bounds.top"),
                self._finite_number(bounds_value.get("right"), "adb_bounds.right"),
                self._finite_number(bounds_value.get("bottom"), "adb_bounds.bottom"),
            )
            # Some active Unity Buttons are layout sentinels with a zero-area
            # RectTransform. They remain observable but are never actionable.
            if (
                candidate_bounds.left < candidate_bounds.right
                and candidate_bounds.top < candidate_bounds.bottom
            ):
                bounds = candidate_bounds
        raycast_top = raw.get("raycast_top")
        if raycast_top is not None and not isinstance(raycast_top, bool):
            raise SemanticGateClosed("button raycast state is malformed")
        return ButtonState(
            name=name,
            path=path,
            active_in_hierarchy=raw.get("active_in_hierarchy") is True,
            active_and_enabled=raw.get("active_and_enabled") is True,
            interactable=raw.get("interactable") is True,
            raycast_top=raycast_top,
            point=point,
            bounds=bounds,
            raw=raw,
        )

    def _parse_toggle(self, raw: Any) -> ToggleState:
        button = self._parse_button(raw)
        checked = raw.get("checked") if isinstance(raw, Mapping) else None
        if not isinstance(checked, bool):
            raise SemanticGateClosed("toggle state is malformed")
        return ToggleState(
            name=button.name,
            path=button.path,
            active_in_hierarchy=button.active_in_hierarchy,
            active_and_enabled=button.active_and_enabled,
            interactable=button.interactable,
            checked=checked,
            raycast_top=button.raycast_top,
            point=button.point,
            bounds=button.bounds,
            raw=raw,
        )

    def _parse_text(self, raw: Any) -> TextState:
        if not isinstance(raw, Mapping):
            raise SemanticGateClosed("text record is not an object")
        kind = raw.get("kind")
        name = raw.get("name")
        path = raw.get("path")
        value = raw.get("text")
        if kind not in ("ugui-text", "tmp-text"):
            raise SemanticGateClosed("text kind is not supported")
        if (
            not isinstance(name, str)
            or not isinstance(path, str)
            or not isinstance(value, str)
            or not name
            or not path
        ):
            raise SemanticGateClosed("text identity is incomplete")
        flags = self._integer(raw.get("flags"), "text flags")
        bounds_value = raw.get("adb_bounds")
        bounds = None
        if bounds_value is not None:
            if not isinstance(bounds_value, Mapping):
                raise SemanticGateClosed("text bounds are malformed")
            candidate = Bounds(
                self._finite_number(bounds_value.get("left"), "text bounds.left"),
                self._finite_number(bounds_value.get("top"), "text bounds.top"),
                self._finite_number(bounds_value.get("right"), "text bounds.right"),
                self._finite_number(bounds_value.get("bottom"), "text bounds.bottom"),
            )
            if candidate.left < candidate.right and candidate.top < candidate.bottom:
                bounds = candidate
        return TextState(
            kind=kind,
            name=name,
            path=path,
            text=value,
            active_in_hierarchy=raw.get("active_in_hierarchy") is True,
            active_and_enabled=raw.get("active_and_enabled") is True,
            truncated=bool(flags & 0x10),
            bounds=bounds,
            raw=raw,
        )

    def _parse_image(self, raw: Any) -> ImageState:
        if not isinstance(raw, Mapping) or raw.get("kind") != "image":
            raise SemanticGateClosed("image record is not supported")
        name = raw.get("name")
        path = raw.get("path")
        sprite = raw.get("sprite")
        if (
            not isinstance(name, str)
            or not isinstance(path, str)
            or not isinstance(sprite, str)
            or not name
            or not path
        ):
            raise SemanticGateClosed("image identity is incomplete")
        raycast_target = raw.get("raycast_target")
        raycast_top = raw.get("raycast_top")
        color_value = raw.get("color")
        if (
            not isinstance(raycast_target, bool)
            or (raycast_top is not None and not isinstance(raycast_top, bool))
            or not isinstance(color_value, Mapping)
        ):
            raise SemanticGateClosed("image state is malformed")
        color = tuple(
            self._finite_number(color_value.get(channel), "image color." + channel)
            for channel in ("red", "green", "blue", "alpha")
        )
        bounds_value = raw.get("adb_bounds")
        bounds = None
        if bounds_value is not None:
            if not isinstance(bounds_value, Mapping):
                raise SemanticGateClosed("image bounds are malformed")
            candidate = Bounds(
                self._finite_number(bounds_value.get("left"), "image bounds.left"),
                self._finite_number(bounds_value.get("top"), "image bounds.top"),
                self._finite_number(bounds_value.get("right"), "image bounds.right"),
                self._finite_number(bounds_value.get("bottom"), "image bounds.bottom"),
            )
            if candidate.left < candidate.right and candidate.top < candidate.bottom:
                bounds = candidate
        flags = self._integer(raw.get("flags"), "image flags")
        return ImageState(
            name=name,
            path=path,
            sprite=sprite,
            active_in_hierarchy=raw.get("active_in_hierarchy") is True,
            active_and_enabled=raw.get("active_and_enabled") is True,
            raycast_target=raycast_target,
            raycast_top=raycast_top,
            color=color,
            fill_amount=self._finite_number(raw.get("fill_amount"), "fill_amount"),
            truncated=bool(flags & 0x10),
            bounds=bounds,
            raw=raw,
        )

    def read_state(self, *, check_foreground: bool = True) -> OracleState:
        """Read live state; frame capture may defer its foreground check to closure."""
        if check_foreground and self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("game activity is not top-resumed")
        snapshot, buttons_snapshot, combined_response = request_observer_state(
            self._request
        )
        if not isinstance(snapshot, Mapping) or not isinstance(buttons_snapshot, Mapping):
            raise ObserverTransportError("observer response is not a mapping")
        self._validate_identity(snapshot)
        self._validate_identity(buttons_snapshot, BUTTON_SCHEMA)

        if snapshot.get("snapshot_schema") != 1 or buttons_snapshot.get("schema") != 1:
            raise SemanticGateClosed("observer snapshot schema mismatch")
        if not observer_snapshot_semantic_ready(snapshot):
            raise SemanticGateClosed("typed main-thread UI probe is incomplete")
        if (
            self._integer(snapshot.get("width"), "width") != self.fingerprint.width
            or self._integer(snapshot.get("height"), "height")
            != self.fingerprint.height
        ):
            raise SemanticGateClosed("logical screen size mismatch")
        if snapshot.get("pid") != buttons_snapshot.get("pid"):
            raise SemanticGateClosed("observer endpoints disagree on PID")

        generation = self._integer(snapshot.get("generation"), "generation")
        button_generation = self._integer(
            buttons_snapshot.get("generation"), "button generation"
        )
        if combined_response and button_generation != generation:
            raise SemanticGateClosed("combined observer state is not generation-atomic")
        if not combined_response and (
            button_generation < generation or button_generation > generation + 2
        ):
            raise SemanticGateClosed("observer endpoints are not generation-coherent")
        if self._last_generation is not None and generation < self._last_generation:
            raise SemanticGateClosed("observer generation moved backwards")
        self._last_generation = generation

        if buttons_snapshot.get("truncated") is not False:
            raise SemanticGateClosed("button snapshot is truncated")
        if self._integer(buttons_snapshot.get("error_count"), "error_count") != 0:
            raise SemanticGateClosed("button snapshot contains extraction errors")
        raw_buttons = buttons_snapshot.get("buttons")
        if not isinstance(raw_buttons, (list, tuple)):
            raise SemanticGateClosed("button list is malformed")
        if self._integer(buttons_snapshot.get("button_count"), "button_count") != len(
            raw_buttons
        ):
            raise SemanticGateClosed("button count does not match the record list")
        buttons = tuple(self._parse_button(raw) for raw in raw_buttons)
        return OracleState(
            generation=button_generation,
            scene_handle=self._integer(snapshot.get("scene_handle"), "scene_handle"),
            snapshot=snapshot,
            buttons_snapshot=buttons_snapshot,
            buttons=buttons,
        )

    def read_ui_state(self, *, check_foreground: bool = True,
                      _preserve_partial_toggles: bool = False) -> UiState:
        """Read UI; frame capture may retain, but never clear, a partial flag.

        Ordinary observation/input consumers retain the strict default. A
        capability-local reader must independently prove its complete slice.
        """
        if (
            check_foreground
            and self._foreground_component() != self.fingerprint.component
        ):
            raise SemanticGateClosed("game activity is not top-resumed")
        ui_snapshot = self._request("GET /v1/ui\n")
        if not isinstance(ui_snapshot, Mapping):
            raise ObserverTransportError("UI observer response is not a mapping")
        self._validate_identity(ui_snapshot, UI_SCHEMA)
        if ui_snapshot.get("schema") != 1:
            raise SemanticGateClosed("UI snapshot schema mismatch")
        if (ui_snapshot.get("toggle_truncated") is not False
                and not (_preserve_partial_toggles is True
                         and ui_snapshot.get("toggle_truncated") is True)):
            raise SemanticGateClosed("toggle snapshot is truncated")
        if ui_snapshot.get("text_truncated") is not False:
            raise SemanticGateClosed("text snapshot is truncated")
        if self._integer(ui_snapshot.get("error_count"), "UI error_count") != 0:
            raise SemanticGateClosed("UI snapshot contains extraction errors")

        image_truncated = ui_snapshot.get("image_truncated")
        if not isinstance(image_truncated, bool):
            raise SemanticGateClosed("image truncation state is malformed")
        image_source_count = ui_snapshot.get("image_source_count")
        image_source_capacity = ui_snapshot.get("image_source_capacity")
        if (image_source_count is None) != (image_source_capacity is None):
            raise SemanticGateClosed("image source metadata is incomplete")
        if image_source_count is not None:
            image_source_count = self._integer(image_source_count, "image_source_count")
            image_source_capacity = self._integer(
                image_source_capacity, "image_source_capacity"
            )
            if (
                image_source_count < 0
                or image_source_capacity <= 0
                or (not image_truncated and image_source_count > image_source_capacity)
            ):
                raise SemanticGateClosed("image source metadata is inconsistent")
        raw_toggles = ui_snapshot.get("toggles")
        raw_texts = ui_snapshot.get("texts")
        raw_images = ui_snapshot.get("images")
        if (
            not isinstance(raw_toggles, (list, tuple))
            or not isinstance(raw_texts, (list, tuple))
            or not isinstance(raw_images, (list, tuple))
        ):
            raise SemanticGateClosed("UI record lists are malformed")
        if self._integer(ui_snapshot.get("toggle_count"), "toggle_count") != len(
            raw_toggles
        ):
            raise SemanticGateClosed("toggle count does not match the record list")
        if self._integer(ui_snapshot.get("text_count"), "text_count") != len(raw_texts):
            raise SemanticGateClosed("text count does not match the record list")
        if self._integer(ui_snapshot.get("image_count"), "image_count") != len(
            raw_images
        ):
            raise SemanticGateClosed("image count does not match the record list")
        method_mask = self._integer(ui_snapshot.get("method_mask"), "UI method_mask")
        skipped_count = self._integer(
            ui_snapshot.get("skipped_count"), "UI skipped_count"
        )
        if skipped_count < 0:
            raise SemanticGateClosed("UI skipped_count is negative")
        if method_mask & 0x6 == 0:
            raise SemanticGateClosed("no typed Unity text accessor is available")
        generation = self._integer(ui_snapshot.get("generation"), "UI generation")
        if self._last_generation is not None and generation < self._last_generation:
            raise SemanticGateClosed("observer generation moved backwards")
        self._last_generation = generation
        return UiState(
            generation=generation,
            method_mask=method_mask,
            skipped_count=skipped_count,
            image_truncated=image_truncated,
            snapshot=ui_snapshot,
            toggles=tuple(self._parse_toggle(raw) for raw in raw_toggles),
            texts=tuple(self._parse_text(raw) for raw in raw_texts),
            images=tuple(self._parse_image(raw) for raw in raw_images),
            image_source_count=image_source_count,
            image_source_capacity=image_source_capacity,
        )

    def read_text_state(self) -> UiState:
        """Read a complete text slice while ignoring unrelated UI-type caps."""

        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("game activity is not top-resumed")
        ui_snapshot = self._request("GET /v1/ui\n")
        if not isinstance(ui_snapshot, Mapping):
            raise ObserverTransportError("UI observer response is not a mapping")
        self._validate_identity(ui_snapshot, UI_SCHEMA)
        if ui_snapshot.get("schema") != 1:
            raise SemanticGateClosed("UI snapshot schema mismatch")
        if ui_snapshot.get("text_truncated") is not False:
            raise SemanticGateClosed("text snapshot is truncated")
        if self._integer(ui_snapshot.get("error_count"), "UI error_count") != 0:
            raise SemanticGateClosed("UI snapshot contains extraction errors")
        raw_texts = ui_snapshot.get("texts")
        if not isinstance(raw_texts, (list, tuple)) or self._integer(
            ui_snapshot.get("text_count"), "text_count"
        ) != len(raw_texts):
            raise SemanticGateClosed("text record list is malformed")
        method_mask = self._integer(ui_snapshot.get("method_mask"), "UI method_mask")
        if method_mask & 0x6 == 0:
            raise SemanticGateClosed("no typed Unity text accessor is available")
        generation = self._integer(ui_snapshot.get("generation"), "UI generation")
        if self._last_generation is not None and generation < self._last_generation:
            raise SemanticGateClosed("observer generation moved backwards")
        self._last_generation = generation
        skipped_count = self._integer(
            ui_snapshot.get("skipped_count"), "UI skipped_count"
        )
        if skipped_count < 0:
            raise SemanticGateClosed("UI skipped_count is negative")
        return UiState(
            generation=generation,
            method_mask=method_mask,
            skipped_count=skipped_count,
            image_truncated=bool(ui_snapshot.get("image_truncated")),
            snapshot=ui_snapshot,
            toggles=(),
            texts=tuple(self._parse_text(raw) for raw in raw_texts),
            images=(),
        )

    @staticmethod
    def _bounds_overlap(left: Bounds, right: Bounds) -> float:
        width = max(0.0, min(left.right, right.right) - max(left.left, right.left))
        height = max(0.0, min(left.bottom, right.bottom) - max(left.top, right.top))
        return width * height

    def texts_in_bounds(
        self,
        bounds: Bounds,
        minimum_overlap_ratio: float = 0.5,
    ) -> Tuple[TextState, ...]:
        if not 0.0 < minimum_overlap_ratio <= 1.0:
            raise ValueError("text overlap ratio must be in (0, 1]")
        state = self.read_ui_state()
        return self._texts_in_state_bounds(state, bounds, minimum_overlap_ratio)

    def _texts_in_state_bounds(
        self,
        state: UiState,
        bounds: Bounds,
        minimum_overlap_ratio: float,
    ) -> Tuple[TextState, ...]:
        matches = []
        for text_state in state.texts:
            text_bounds = text_state.bounds
            if (
                not text_state.active_in_hierarchy
                or not text_state.active_and_enabled
                or text_bounds is None
            ):
                continue
            text_area = (text_bounds.right - text_bounds.left) * (
                text_bounds.bottom - text_bounds.top
            )
            if text_area <= 0:
                continue
            overlap = self._bounds_overlap(bounds, text_bounds)
            if overlap / text_area >= minimum_overlap_ratio:
                matches.append(text_state)
        matches.sort(
            key=lambda item: (
                item.bounds.top if item.bounds is not None else math.inf,
                item.bounds.left if item.bounds is not None else math.inf,
                item.path,
            )
        )
        return tuple(matches)

    def text_groups_in_bounds(
        self,
        bounds: Iterable[Bounds],
        minimum_overlap_ratio: float = 0.5,
    ) -> Tuple[Tuple[TextState, ...], ...]:
        if not 0.0 < minimum_overlap_ratio <= 1.0:
            raise ValueError("text overlap ratio must be in (0, 1]")
        state = self.read_ui_state()
        return tuple(
            self._texts_in_state_bounds(state, area, minimum_overlap_ratio)
            for area in bounds
        )

    def text_state(self, semantic_id: str) -> TextState:
        try:
            target = self._text_targets[semantic_id]
        except KeyError as exc:
            raise SemanticGateClosed(
                "semantic text target is not mapped: {0}".format(semantic_id)
            ) from exc
        state = self.read_ui_state()
        matches = tuple(
            item
            for item in state.texts
            if item.path.endswith(target.path_suffix)
            and item.text in target.expected_texts
        )
        if len(matches) != 1:
            raise SemanticGateClosed(
                "semantic text target is absent or ambiguous: {0}".format(semantic_id)
            )
        item = matches[0]
        if (
            item.truncated
            or not item.active_in_hierarchy
            or not item.active_and_enabled
            or item.bounds is None
        ):
            raise SemanticGateClosed("semantic text target is incomplete")
        return item

    def text_exists(self, semantic_id: str) -> bool:
        try:
            self.text_state(semantic_id)
        except SemanticGateClosed:
            return False
        return True

    def indexed_text_groups(self, path_prefix: str) -> Tuple[IndexedTextGroup, ...]:
        """Group live text below exact ``path_prefix/<numeric-index>`` nodes."""

        if not path_prefix or path_prefix.endswith("/"):
            raise ValueError(
                "indexed text path prefix must be non-empty and normalized"
            )
        state = self.read_ui_state()
        pattern = re.compile(r"(?:^|/)" + re.escape(path_prefix) + r"/([0-9]+)(?:/|$)")
        groups: Dict[int, List[TextState]] = {}
        roots: Dict[int, str] = {}
        for item in state.texts:
            if (
                item.truncated
                or not item.active_in_hierarchy
                or not item.active_and_enabled
                or item.bounds is None
            ):
                continue
            match = pattern.search(item.path)
            if match is None:
                continue
            index = int(match.group(1))
            root_end = match.end(1)
            root = item.path[:root_end]
            if index in roots and roots[index] != root:
                raise SemanticGateClosed(
                    "indexed text group root is ambiguous: {0}".format(index)
                )
            roots[index] = root
            groups.setdefault(index, []).append(item)
        result = []
        for index in sorted(groups):
            values = sorted(
                groups[index],
                key=lambda item: (
                    item.bounds.top if item.bounds is not None else math.inf,
                    item.bounds.left if item.bounds is not None else math.inf,
                    item.path,
                ),
            )
            result.append(IndexedTextGroup(index, roots[index], tuple(values)))
        return tuple(result)

    @staticmethod
    def parse_countdown_seconds(value: str) -> int:
        """Parse a strict ``MM:SS`` or ``HH:MM:SS`` typed Unity countdown."""

        if not isinstance(value, str):
            raise SemanticGateClosed("countdown text is not a string")
        match = re.fullmatch(r"(?:(\d{1,3}):)?([0-5]\d):([0-5]\d)", value.strip())
        if match is None:
            raise SemanticGateClosed("typed countdown has an unsupported format")
        hours = int(match.group(1) or 0)
        minutes = int(match.group(2))
        seconds = int(match.group(3))
        return hours * 3600 + minutes * 60 + seconds

    def main_gold(self) -> int:
        """Read the exact main-screen coin counter before entering Build."""

        button_state = self.read_state()
        build = self._unique(button_state, "main/build")
        if not build.actionable or self._blocking_rules(button_state, "main/build"):
            raise SemanticGateClosed("main build entry identity is not proven")
        ui_state = self.read_ui_state()
        matches = tuple(
            item
            for item in ui_state.texts
            if item.path.endswith("NewMainMellowTheme(Clone)/frame/top/res/gold/Text")
            and item.active_in_hierarchy
            and item.active_and_enabled
            and not item.truncated
            and item.bounds is not None
        )
        if (
            len(matches) != 1
            or re.fullmatch(r"[0-9]+", matches[0].text.strip()) is None
        ):
            raise SemanticGateClosed("main coin counter is absent or malformed")
        return int(matches[0].text.strip())

    def main_red_dot(self, semantic_id: str) -> bool:
        """Read a reviewed main-menu ``reddot`` marker without using pixels."""

        suffixes = {
            "main/task": "NewMainMellowTheme(Clone)/frame/bottom/frame/task/tip",
            "main/build": "NewMainMellowTheme(Clone)/frame/bottom/frame/build/tip",
            "main/live": "NewMainMellowTheme(Clone)/frame/bottom/frame/live/tip",
        }
        try:
            suffix = suffixes[semantic_id]
        except KeyError as exc:
            raise SemanticGateClosed("main red-dot target is not mapped") from exc
        button_state = self.read_state()
        if not self._matches(button_state, semantic_id):
            raise SemanticGateClosed("main red-dot parent identity is absent")
        ui_state = self.read_ui_state()
        matches = tuple(
            image
            for image in ui_state.images
            if image.name == "tip"
            and image.path.endswith(suffix)
            and image.sprite == "reddot"
            and image.active_in_hierarchy
            and image.active_and_enabled
            and not image.truncated
            and image.bounds is not None
        )
        if len(matches) > 1:
            raise SemanticGateClosed("main red-dot marker is ambiguous")
        return bool(matches)

    def observation_surface_present(self, surface: ObservationSurface) -> bool:
        """Identify an observation owner without invoking its task parser."""
        return observation_surface_present(self, surface)

    def observation_target_present(self, semantic_id: str) -> bool:
        """Check a mapped owner anchor without invoking feature-specific reads."""
        return any(
            button.active_in_hierarchy and button.active_and_enabled
            for button in self._matches(self.read_state(), semantic_id)
        )

    def observation_prompt_kind(self):
        return observation_prompt_kind(self)

    def main_page_visible(self) -> bool:
        state = self.read_state()
        battle = self._matches(state, "main/battle")
        formation = self._matches(state, "main/formation")
        return bool(
            len(battle) == 1
            and len(formation) == 1
            and battle[0].active_in_hierarchy
            and formation[0].active_in_hierarchy
        )

    def main_page_receipt(self) -> ActionReceipt:
        if not self.main_page_visible():
            raise SemanticGateClosed("main page identity is absent")
        state = self.read_state()
        target = self._unique(state, "main/battle")
        if target.point is None or target.bounds is None:
            raise SemanticGateClosed("main page identity geometry is absent")
        return ActionReceipt(
            semantic_id="main/already",
            generation=state.generation,
            point=target.point,
            bounds=target.bounds,
            path=target.path,
        )

    def academy_page_visible(self) -> bool:
        """Identify the exact Naval Academy map and its reviewed landmarks."""

        state = self.read_state()
        ui_state = self.read_ui_state()
        if (
            ui_state.generation < state.generation
            or ui_state.generation > state.generation + 2
        ):
            raise SemanticGateClosed("academy snapshots are not coherent")
        required_buttons = {
            "back": "NavalAcademyUI/blur_container/adapt/top/title/back",
            "supplyShop": "NavalAcademyUI/academyMap/map/supplyShop",
            "tacticRoom": "NavalAcademyUI/academyMap/map/tacticRoom",
            "minigamehall": "NavalAcademyUI/academyMap/map/minigamehall",
        }
        for name, suffix in required_buttons.items():
            matches = tuple(
                button
                for button in state.buttons
                if button.name == name
                and button.path.endswith(suffix)
                and button.active_in_hierarchy
                and button.active_and_enabled
                and button.bounds is not None
            )
            if len(matches) != 1:
                return False
        required_text = {
            "NavalAcademyUI/academyMap/map/supplyShop/name/Text": "补给商店",
            "NavalAcademyUI/academyMap/map/tacticRoom/name/Text": "战术学院",
            "NavalAcademyUI/academyMap/map/minigamehall/name/Text": "游戏屋",
        }
        for suffix, expected in required_text.items():
            matches = tuple(
                text
                for text in ui_state.texts
                if text.path.endswith(suffix)
                and text.active_in_hierarchy
                and text.active_and_enabled
                and not text.truncated
                and text.bounds is not None
                and text.text.strip() == expected
            )
            if len(matches) != 1:
                return False
        return True

    def click_event_battle_mode(self) -> ActionReceipt:
        """Switch the current event story selector back to combat stages."""

        if not self.event_campaign_page_visible():
            raise SemanticGateClosed("event campaign page identity is absent")
        state = self.read_state()
        target = self._unique(state, "event/mode/battle")
        if not (
            target.active_in_hierarchy
            and target.active_and_enabled
            and target.interactable
            and target.raycast_top is None
            and target.bounds is not None
        ):
            raise SemanticGateClosed("event battle selector is not actionable")
        point = Point(
            (target.bounds.left + target.bounds.right) / 2.0,
            (target.bounds.top + target.bounds.bottom) / 2.0,
        )
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("game activity changed before event mode input")
        self._tap(int(round(point.x)), int(round(point.y)))
        return ActionReceipt(
            semantic_id="event/mode/battle",
            generation=state.generation,
            point=point,
            bounds=target.bounds,
            path=target.path,
        )

    def _click_exact_image(
        self,
        state: OracleState,
        image: ImageState,
        semantic_id: str,
    ) -> ActionReceipt:
        """Tap one exact image-only control after the common input gates."""

        if (
            not image.active_in_hierarchy
            or not image.active_and_enabled
            or not image.raycast_target
            or image.truncated
            or image.bounds is None
        ):
            raise SemanticGateClosed(semantic_id + " is not safely actionable")
        point = Point(
            (image.bounds.left + image.bounds.right) / 2.0,
            (image.bounds.top + image.bounds.bottom) / 2.0,
        )
        if not image.bounds.contains(point) or self._blocking_rules(state, semantic_id):
            raise SemanticGateClosed(semantic_id + " input is blocked")
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("game activity changed before Dock input")
        self._tap(int(round(point.x)), int(round(point.y)))
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("game activity changed after Dock input")
        return ActionReceipt(
            semantic_id=semantic_id,
            generation=state.generation,
            point=point,
            bounds=image.bounds,
            path=image.path,
        )

    def _click_exact_toggle(
        self,
        state: OracleState,
        toggle: ToggleState,
        semantic_id: str,
    ) -> ActionReceipt:
        """Tap one exact typed toggle at its exported semantic point."""

        if (
            not toggle.active_in_hierarchy
            or not toggle.active_and_enabled
            or not toggle.interactable
            or toggle.bounds is None
        ):
            raise SemanticGateClosed(semantic_id + " toggle is incomplete")
        point = toggle.point
        if point is None:
            raise SemanticGateClosed(semantic_id + " toggle has no input point")
        if not toggle.bounds.contains(point) or self._blocking_rules(
            state, semantic_id
        ):
            raise SemanticGateClosed(semantic_id + " input is blocked")
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("game activity changed before toggle input")
        self._tap(int(round(point.x)), int(round(point.y)))
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("game activity changed after toggle input")
        return ActionReceipt(
            semantic_id=semantic_id,
            generation=state.generation,
            point=point,
            bounds=toggle.bounds,
            path=toggle.path,
        )
