"""Immutable semantic frames acquired from the atomic observer endpoint."""

from __future__ import annotations

import hashlib
import json
import math
import time
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Callable, Mapping

from ..semantic_oracle import SemanticGateClosed, SemanticOracle
from .errors import StaleFrameError
from .ports import RuntimeHandlePort, SemanticFrameIdentity


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        frozen = {}
        for key, child in value.items():
            if not isinstance(key, str) or not key:
                raise SemanticGateClosed("semantic frame mapping key is malformed")
            frozen[key] = _freeze(child)
        return MappingProxyType(frozen)
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(child) for child in value)
    if isinstance(value, float) and not math.isfinite(value):
        raise SemanticGateClosed("semantic frame contains a non-finite value")
    if isinstance(value, (str, int, float, bool, type(None))):
        return value
    raise SemanticGateClosed("semantic frame contains a mutable projection value")


def _thaw(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _thaw(child) for key, child in value.items()}
    if isinstance(value, tuple):
        return [_thaw(child) for child in value]
    return value


def _canonical_sha256(value: Mapping[str, Any]) -> str:
    try:
        encoded = json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise SemanticGateClosed("semantic frame payload is not canonical JSON") from exc
    return hashlib.sha256(encoded).hexdigest()


def _integer(value: Any, field: str, *, minimum: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise SemanticGateClosed("semantic frame integer is malformed: {0}".format(field))
    if minimum is not None and value < minimum:
        raise SemanticGateClosed("semantic frame integer is out of range: {0}".format(field))
    return value


def _age(value: Any, field: str, maximum_age_ms: int) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SemanticGateClosed("semantic frame age is malformed: {0}".format(field))
    age_ms = float(value)
    if not math.isfinite(age_ms) or age_ms < 0.0 or age_ms > maximum_age_ms:
        raise SemanticGateClosed("semantic frame age is outside the admitted bound")
    return age_ms


@dataclass(frozen=True)
class SemanticFrame:
    frame_id: str
    pid: int
    generation: int
    scene_handle: int
    captured_monotonic_ns: int
    age_ms: float
    fingerprint_sha256: str
    raw_state_sha256: str
    projections: Mapping[str, Any]

    def __post_init__(self) -> None:
        identity = SemanticFrameIdentity(
            frame_id=self.frame_id,
            pid=self.pid,
            generation=self.generation,
            scene_handle=self.scene_handle,
            fingerprint_sha256=self.fingerprint_sha256,
            raw_state_sha256=self.raw_state_sha256,
        )
        if (
            isinstance(self.captured_monotonic_ns, bool)
            or not isinstance(self.captured_monotonic_ns, int)
            or self.captured_monotonic_ns <= 0
        ):
            raise ValueError("captured_monotonic_ns must be positive")
        if (
            isinstance(self.age_ms, bool)
            or not isinstance(self.age_ms, (int, float))
            or not math.isfinite(float(self.age_ms))
            or float(self.age_ms) < 0.0
        ):
            raise ValueError("semantic frame age must be finite and non-negative")
        if not isinstance(self.projections, Mapping) or not self.projections:
            raise ValueError("semantic frame projections must be a non-empty mapping")
        object.__setattr__(self, "age_ms", float(self.age_ms))
        object.__setattr__(self, "projections", _freeze(self.projections))
        object.__setattr__(self, "_identity", identity)

    @property
    def identity(self) -> SemanticFrameIdentity:
        return self._identity


class SemanticFrameClock:
    """Acquire and lease one current frame without hidden refreshes."""

    def __init__(
        self,
        runtime_handle: RuntimeHandlePort,
        oracle: SemanticOracle,
        *,
        monotonic_ns: Callable[[], int] = time.monotonic_ns,
    ) -> None:
        if not isinstance(runtime_handle, RuntimeHandlePort):
            raise TypeError("semantic frame clock requires a runtime handle")
        if not isinstance(oracle, SemanticOracle):
            raise TypeError("semantic frame clock requires a SemanticOracle")
        if not callable(monotonic_ns):
            raise TypeError("semantic frame clock requires a monotonic clock")
        self._runtime_handle = runtime_handle
        self._oracle = oracle
        self._monotonic_ns = monotonic_ns
        self._fingerprint_sha256 = runtime_handle.fingerprint_sha256
        self._maximum_age_ms = oracle.fingerprint.max_age_ms
        self._current: SemanticFrame | None = None
        self._invalidated_generation: int | None = None
        self._ordinal = 0
        self._closed = False

    @property
    def closed(self) -> bool:
        return self._closed

    @property
    def current_frame_id(self) -> str | None:
        return self._current.frame_id if self._current is not None else None

    def _runtime_identity(self) -> tuple[str, int]:
        fingerprint = self._runtime_handle.fingerprint_sha256
        pid = self._runtime_handle.pid
        if fingerprint != self._fingerprint_sha256:
            raise StaleFrameError()
        if self._oracle.fingerprint.expected_pid != pid:
            raise StaleFrameError()
        return fingerprint, pid

    def acquire(self, *, include_ui: bool = False) -> SemanticFrame:
        if self._closed:
            raise StaleFrameError()
        try:
            fingerprint_before, pid_before = self._runtime_identity()
            state = self._oracle.read_state()
            ui_state = self._oracle.read_ui_state() if include_ui else None
            fingerprint_after, pid_after = self._runtime_identity()
            if (
                fingerprint_after != fingerprint_before
                or pid_after != pid_before
            ):
                raise StaleFrameError()
            snapshot = state.snapshot
            buttons = state.buttons_snapshot
            if snapshot.get("pid") != buttons.get("pid") or snapshot.get("pid") != pid_after:
                raise SemanticGateClosed("semantic frame endpoints disagree on PID")
            generation = _integer(snapshot.get("generation"), "generation", minimum=0)
            button_generation = _integer(
                buttons.get("generation"),
                "button generation",
                minimum=0,
            )
            if generation != button_generation or state.generation != generation:
                raise SemanticGateClosed("semantic frame mixes observer generations")
            scene_handle = _integer(snapshot.get("scene_handle"), "scene_handle")
            ages = [
                _age(snapshot.get("age_ms"), "snapshot", self._maximum_age_ms),
                _age(buttons.get("age_ms"), "buttons", self._maximum_age_ms),
            ]
            if (
                self._invalidated_generation is not None
                and generation <= self._invalidated_generation
            ):
                raise StaleFrameError()
            raw_payload = {"buttons": buttons, "snapshot": snapshot}
            if ui_state is not None:
                if ui_state.generation != generation:
                    raise SemanticGateClosed(
                        "semantic frame mixes UI and state generations"
                    )
                ui_snapshot = ui_state.snapshot
                if ui_snapshot.get("pid") != pid_after:
                    raise SemanticGateClosed(
                        "semantic frame UI disagrees on PID"
                    )
                ages.append(
                    _age(
                        ui_snapshot.get("age_ms"),
                        "UI",
                        self._maximum_age_ms,
                    )
                )
                raw_payload["ui"] = ui_snapshot
            age_ms = max(ages)
            raw_state_sha256 = _canonical_sha256(raw_payload)
            captured = self._monotonic_ns()
            if isinstance(captured, bool) or not isinstance(captured, int) or captured <= 0:
                raise SemanticGateClosed("semantic frame monotonic clock is invalid")
            self._ordinal += 1
            frame = SemanticFrame(
                frame_id="frame-{0}-{1}".format(generation, self._ordinal),
                pid=pid_after,
                generation=generation,
                scene_handle=scene_handle,
                captured_monotonic_ns=captured,
                age_ms=age_ms,
                fingerprint_sha256=fingerprint_after,
                raw_state_sha256=raw_state_sha256,
                projections=raw_payload,
            )
        except Exception:
            self._current = None
            raise
        self._current = frame
        self._invalidated_generation = None
        return frame

    def borrow(self, frame_id: str | None = None) -> SemanticFrame:
        if self._closed or self._current is None:
            raise StaleFrameError()
        frame = self._current
        if frame_id is not None and frame_id != frame.frame_id:
            raise StaleFrameError()
        try:
            fingerprint, pid = self._runtime_identity()
            now = self._monotonic_ns()
        except Exception:
            self._current = None
            raise
        if fingerprint != frame.fingerprint_sha256 or pid != frame.pid:
            self._current = None
            raise StaleFrameError()
        elapsed_ns = now - frame.captured_monotonic_ns
        if elapsed_ns < 0:
            self._current = None
            raise StaleFrameError()
        if frame.age_ms + elapsed_ns / 1_000_000.0 > self._maximum_age_ms:
            self._current = None
            raise StaleFrameError()
        return frame

    def invalidate(self, frame_id: str | None = None) -> None:
        if self._closed or self._current is None:
            raise StaleFrameError()
        if frame_id is not None and frame_id != self._current.frame_id:
            raise StaleFrameError()
        self._invalidated_generation = self._current.generation
        self._current = None

    def close(self) -> None:
        self._current = None
        self._invalidated_generation = None
        self._closed = True


class _FrameBoundSemanticOracle(SemanticOracle):
    """Disable transition retry loops for one immutable frame."""

    def _retry_transition_read(
        self,
        reader: Callable[[], Any],
        *,
        attempts: int = 1,
        interval_seconds: float = 0.0,
    ) -> Any:
        del attempts, interval_seconds
        return reader()


class SemanticFrameReader:
    """Expose SemanticOracle reads backed only by the currently borrowed frame."""

    def __init__(
        self,
        clock: SemanticFrameClock,
        live_oracle: SemanticOracle,
    ) -> None:
        if not isinstance(clock, SemanticFrameClock):
            raise TypeError("semantic frame reader requires a frame clock")
        if not isinstance(live_oracle, SemanticOracle):
            raise TypeError("semantic frame reader requires a SemanticOracle")
        self._clock = clock
        self._live_oracle = live_oracle
        self._frame_id: str | None = None
        self._oracle: SemanticOracle | None = None

    def identity(self) -> SemanticFrameIdentity:
        return self._clock.borrow().identity

    def oracle(self) -> SemanticOracle:
        frame = self._clock.borrow()
        if self._oracle is not None and self._frame_id == frame.frame_id:
            return self._oracle
        frame_id = frame.frame_id

        def request(request_line: str) -> Mapping[str, Any]:
            current = self._clock.borrow(frame_id)
            projections = current.projections
            if request_line == "GET /v1/state\n":
                return {
                    "protocol_schema": "alas-headless.observer/v1",
                    "status": "ok",
                    "snapshot": _thaw(projections["snapshot"]),
                    "buttons": _thaw(projections["buttons"]),
                }
            if request_line == "GET /v1/snapshot\n":
                return _thaw(projections["snapshot"])
            if request_line == "GET /v1/buttons\n":
                return _thaw(projections["buttons"])
            if request_line == "GET /v1/ui\n" and "ui" in projections:
                return _thaw(projections["ui"])
            raise StaleFrameError()

        live = self._live_oracle
        self._oracle = _FrameBoundSemanticOracle(
            request,
            live._foreground_component,
            live._tap,
            live.fingerprint,
            targets=live._targets.values(),
            image_targets=live._image_targets.values(),
            toggle_targets=live._toggle_targets.values(),
            text_targets=live._text_targets.values(),
            blockers=live._blockers,
            monotonic=live._monotonic,
            sleep=lambda _: None,
            swipe=live._swipe,
        )
        self._frame_id = frame_id
        return self._oracle
