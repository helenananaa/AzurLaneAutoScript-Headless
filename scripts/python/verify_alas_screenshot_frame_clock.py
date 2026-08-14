#!/usr/bin/env python3
"""Execute the semantic screenshot clock from a pinned patched ALAS tree."""

from __future__ import annotations

import argparse
import ast
import copy
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any, Mapping, Sequence

try:
    from .build_alas_patch_series import check_generated_patch
except ImportError:  # Direct script execution.
    from build_alas_patch_series import check_generated_patch


ROOT = Path(__file__).resolve().parents[2]
LOCK_PATH = ROOT / "integration" / "alas" / "upstream-lock.json"
PATCH_PATH = ROOT / "integration" / "alas" / "0001-semantic-oracle-hooks.patch"
SERIES_MANIFEST_PATH = ROOT / "integration" / "alas" / "series" / "series.json"
SCHEMA = "alas-headless.screenshot-frame-clock-verification/v1"
REVISION = "be80ce591a481c12d60c50d6040d40c035b40a2b"
PACKAGE = "com.bilibili.azurlane"
COMPONENT = "com.bilibili.azurlane/com.manjuu.azurlane.MainActivity"
_SEMANTIC_INSERTION = (
    "        semantic_session = getattr(self, 'semantic_adapter', None)\n"
    "        if semantic_session is not None:\n"
    "            frame = semantic_session.refresh_frame()\n"
    "            self.image = semantic_session.pixel_guard(frame)\n"
    "            return self.image\n\n"
)
_DEVICE_OS_PATCHED = "import collections\nimport os\nfrom datetime"
_DEVICE_OS_PRISTINE = "import collections\nfrom datetime"
_DEVICE_SESSION_INSERTION = (
    "        self.semantic_adapter = None\n"
    "        if os.environ.get('ALAS_SEMANTIC_MODE') == '1':\n"
    "            from alas_headless import AlasSemanticSession, bind_semantic_session\n"
    "            self.semantic_adapter = AlasSemanticSession.from_environment(\n"
    "                serial=self.config.Emulator_Serial\n"
    "            )\n"
    "            self._semantic_session_token = bind_semantic_session(\n"
    "                self.semantic_adapter\n"
    "            )\n"
    "            self.__dict__.pop('click_methods', None)\n"
    "            logger.warning(\n"
    "                'ALAS semantic mode enabled; unmapped detection and raw input fail closed'\n"
    "            )\n\n"
)
_DEVICE_PIXEL_INSERTION = (
    "        semantic_session = getattr(self, 'semantic_adapter', None)\n"
    "        if semantic_session is not None:\n"
    "            return False\n"
)


class ScreenshotFrameClockVerificationError(RuntimeError):
    """The patched screenshot clock does not preserve its reviewed contract."""


def _git(repository: Path, *arguments: str) -> str:
    try:
        result = subprocess.run(
            ("git", "-C", str(repository), *arguments),
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise ScreenshotFrameClockVerificationError("Git verification failed") from exc
    return result.stdout.rstrip("\r\n")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _method(source: str, class_name: str, method_name: str) -> ast.FunctionDef:
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for child in node.body:
                if isinstance(child, ast.FunctionDef) and child.name == method_name:
                    return copy.deepcopy(child)
    raise ScreenshotFrameClockVerificationError(
        "patched ALAS method is missing: {0}.{1}".format(class_name, method_name)
    )


def load_patched_screenshot_classes(
    screenshot_source: str,
    device_source: str,
) -> tuple[type, type]:
    """Compile the two actual patched method ASTs into a dependency-free harness."""

    screenshot_class = ast.ClassDef(
        name="Screenshot",
        bases=[],
        keywords=[],
        body=[_method(screenshot_source, "Screenshot", "screenshot")],
        decorator_list=[],
    )
    device_class = ast.ClassDef(
        name="Device",
        bases=[ast.Name(id="Screenshot", ctx=ast.Load())],
        keywords=[],
        body=[
            _method(device_source, "Device", "handle_night_commission"),
            _method(device_source, "Device", "screenshot"),
        ],
        decorator_list=[],
    )
    module = ast.fix_missing_locations(
        ast.Module(body=[screenshot_class, device_class], type_ignores=[])
    )

    class RequestHumanTakeover(RuntimeError):
        pass

    namespace: dict[str, Any] = {"RequestHumanTakeover": RequestHumanTakeover}
    exec(compile(module, "<patched-alas-screenshot-clock>", "exec"), namespace)
    return namespace["Screenshot"], namespace["Device"]


def assert_normal_screenshot_source_preserved(
    pristine_source: str,
    patched_source: str,
) -> None:
    if patched_source.count(_SEMANTIC_INSERTION) != 1:
        raise ScreenshotFrameClockVerificationError(
            "semantic screenshot insertion is missing or duplicated"
        )
    if patched_source.replace(_SEMANTIC_INSERTION, "", 1) != pristine_source:
        raise ScreenshotFrameClockVerificationError(
            "normal ALAS screenshot source changed outside the semantic guard"
        )


def assert_normal_device_source_preserved(
    pristine_source: str,
    patched_source: str,
) -> None:
    replacements = (
        (_DEVICE_OS_PATCHED, _DEVICE_OS_PRISTINE),
        (_DEVICE_SESSION_INSERTION, ""),
        (_DEVICE_PIXEL_INSERTION, ""),
    )
    restored = patched_source
    for patched, pristine in replacements:
        if restored.count(patched) != 1:
            raise ScreenshotFrameClockVerificationError(
                "semantic Device insertion is missing or duplicated"
            )
        restored = restored.replace(patched, pristine, 1)
    if restored != pristine_source:
        raise ScreenshotFrameClockVerificationError(
            "normal ALAS Device source changed outside semantic guards"
        )


class _FrameRuntimeHandle:
    def __init__(self, fingerprint_sha256: str) -> None:
        self.fingerprint_sha256 = fingerprint_sha256
        self.pid = 4242
        self.generation = 10
        self.requests: list[str] = []
        self.taps: list[tuple[int, int]] = []

    def observer_request(self, request_line: str) -> Mapping[str, Any]:
        self.requests.append(request_line)
        identity = {
            "protocol_schema": "alas-headless.observer/v1",
            "status": "ok",
            "package": PACKAGE,
            "pid": self.pid,
            "peer_uid": 2000,
            "driver_revision": REVISION,
            "generation": self.generation,
            "age_ms": 20,
        }
        if request_line == "GET /v1/state\n":
            snapshot = dict(
                identity,
                snapshot_schema=1,
                main_thread=True,
                flags=15,
                ui_stage=100,
                ui_method_mask=15,
                width=1280,
                height=720,
                scene_handle=-76,
            )
            buttons = dict(
                identity,
                semantic_schema="alas-headless.buttons/v1",
                schema=1,
                button_count=1,
                truncated=False,
                error_count=0,
                buttons=[
                    {
                        "name": "LoginUI2(Clone)",
                        "path": "UICamera/Canvas/UIMain/LoginUI2(Clone)",
                        "active_in_hierarchy": True,
                        "active_and_enabled": True,
                        "interactable": True,
                        "raycast_top": True,
                        "adb_point": {"x": 640.0, "y": 360.0},
                        "adb_bounds": {
                            "left": 600.0,
                            "top": 330.0,
                            "right": 680.0,
                            "bottom": 390.0,
                        },
                    }
                ],
            )
            return {
                "protocol_schema": "alas-headless.observer/v1",
                "status": "ok",
                "snapshot": snapshot,
                "buttons": buttons,
            }
        if request_line == "GET /v1/ui\n":
            return dict(
                identity,
                semantic_schema="alas-headless.ui/v1",
                schema=1,
                method_mask=15,
                toggle_count=0,
                text_count=0,
                image_count=0,
                toggle_truncated=False,
                text_truncated=False,
                image_truncated=False,
                error_count=0,
                skipped_count=0,
                toggles=[],
                texts=[],
                images=[],
            )
        raise ScreenshotFrameClockVerificationError("unexpected observer request")

    def foreground_component(self) -> str:
        return COMPONENT

    def tap(self, x: int, y: int) -> None:
        self.taps.append((x, y))

    def swipe(
        self,
        x1: int,
        y1: int,
        x2: int,
        y2: int,
        duration_ms: int,
    ) -> None:
        raise ScreenshotFrameClockVerificationError("unexpected swipe")


class _RecordingTimer:
    def __init__(self, events: list[str]) -> None:
        self._events = events

    def wait(self) -> None:
        self._events.append("interval.wait")

    def reset(self) -> None:
        self._events.append("interval.reset")


class _RecordingSession:
    def __init__(self, session: Any, events: list[str]) -> None:
        self._session = session
        self._events = events

    def refresh_frame(self) -> Any:
        self._events.append("session.refresh_frame")
        return self._session.refresh_frame()

    def pixel_guard(self, frame: Any) -> Any:
        self._events.append("session.pixel_guard")
        return self._session.pixel_guard(frame)

    def reject_pixel_access(self, operation: str, consumer: str) -> None:
        self._events.append("session.reject_pixel_access")
        self._session.reject_pixel_access(operation, consumer)


def verify(patched_upstream: Path) -> Mapping[str, Any]:
    check_generated_patch(SERIES_MANIFEST_PATH, PATCH_PATH, root=ROOT)
    from alas_headless import (
        AlasSemanticSession,
        PINNED_CN_GAME_FINGERPRINT,
    )
    from alas_headless.adapter import (
        SemanticPixelGuard,
        StaleFrameError,
        UnsupportedPixelRead,
        semantic_runtime_fingerprint_sha256,
    )

    patched_upstream = patched_upstream.resolve()
    expected_commit = json.loads(LOCK_PATH.read_text(encoding="utf-8"))["commit"]
    if _git(patched_upstream, "rev-parse", "HEAD").lower() != expected_commit:
        raise ScreenshotFrameClockVerificationError("patched upstream HEAD drifted")
    reverse = subprocess.run(
        (
            "git",
            "-C",
            str(patched_upstream),
            "apply",
            "--reverse",
            "--check",
            str(PATCH_PATH),
        ),
        capture_output=True,
        text=True,
        timeout=30,
    )
    if reverse.returncode != 0:
        raise ScreenshotFrameClockVerificationError("canonical patch is not applied")

    screenshot_path = patched_upstream / "module" / "device" / "screenshot.py"
    device_path = patched_upstream / "module" / "device" / "device.py"
    screenshot_source = screenshot_path.read_text(encoding="utf-8")
    device_source = device_path.read_text(encoding="utf-8")
    pristine_source = _git(
        patched_upstream,
        "show",
        "HEAD:module/device/screenshot.py",
    ) + "\n"
    assert_normal_screenshot_source_preserved(pristine_source, screenshot_source)
    pristine_device_source = _git(
        patched_upstream,
        "show",
        "HEAD:module/device/device.py",
    ) + "\n"
    assert_normal_device_source_preserved(pristine_device_source, device_source)
    _, device_class = load_patched_screenshot_classes(
        screenshot_source,
        device_source,
    )

    fingerprint = semantic_runtime_fingerprint_sha256(
        package=PACKAGE,
        component=COMPONENT,
        driver_revision=REVISION,
        game_fingerprint=PINNED_CN_GAME_FINGERPRINT,
    )
    handle = _FrameRuntimeHandle(fingerprint)
    session = AlasSemanticSession(
        driver_revision=REVISION,
        runtime_handle=handle,
    )
    adapter = session.open()
    adapter.begin_login()
    events: list[str] = []
    device = device_class()
    device.semantic_adapter = _RecordingSession(session, events)
    device._screenshot_interval = _RecordingTimer(events)
    device.stuck_record_check = lambda: events.append("stuck_record_check")
    device.handle_night_commission = lambda: (
        events.append("handle_night_commission") or False
    )

    first = device.screenshot()
    expected_order = [
        "stuck_record_check",
        "interval.wait",
        "interval.reset",
        "session.refresh_frame",
        "session.pixel_guard",
        "handle_night_commission",
    ]
    if events != expected_order:
        raise ScreenshotFrameClockVerificationError("ALAS screenshot call order changed")
    if not isinstance(first, SemanticPixelGuard):
        raise ScreenshotFrameClockVerificationError("semantic image is not guarded")

    class _Timestamp:
        @staticmethod
        def timestamp() -> float:
            return 1_000.0

    class _DateTime:
        @staticmethod
        def now() -> _Timestamp:
            return _Timestamp()

    class _ForbiddenTemplate:
        @staticmethod
        def match(*args: Any, **kwargs: Any) -> bool:
            del args, kwargs
            raise ScreenshotFrameClockVerificationError(
                "template matcher ran after semantic pixel rejection"
            )

    handle_globals = device_class.handle_night_commission.__globals__
    handle_globals.update(
        {
            "GET_MISSION": _ForbiddenTemplate(),
            "datetime": _DateTime,
            "get_server_next_update": lambda daily_trigger: _Timestamp(),
        }
    )
    events.clear()
    if device_class.handle_night_commission(device) is not False:
        raise ScreenshotFrameClockVerificationError(
            "semantic night-commission branch did not stop before pixels"
        )
    if events:
        raise ScreenshotFrameClockVerificationError(
            "semantic night-commission branch dispatched an unexpected action"
        )
    pixel_records = session.pixel_access_records()
    if pixel_records:
        raise ScreenshotFrameClockVerificationError(
            "semantic night-commission branch consumed framebuffer pixels"
        )
    request_count = len(handle.requests)
    if not adapter.appear("LOGIN_CHECK") or len(handle.requests) != request_count:
        raise ScreenshotFrameClockVerificationError("observation refreshed the frame")

    events.clear()
    second = device.screenshot()
    if events != expected_order or first.frame_id == second.frame_id:
        raise ScreenshotFrameClockVerificationError("screenshot did not advance frame")

    adapter.click("LOGIN_CHECK")
    if handle.taps != [(640, 360)]:
        raise ScreenshotFrameClockVerificationError("reviewed login action changed")
    events.clear()
    try:
        device.screenshot()
    except StaleFrameError:
        pass
    else:
        raise ScreenshotFrameClockVerificationError(
            "same-generation post-action screenshot was accepted"
        )
    failed_refresh_order = expected_order[:-2]
    if events != failed_refresh_order:
        raise ScreenshotFrameClockVerificationError(
            "failed screenshot no longer owns interval timing"
        )

    handle.generation = second.generation + 1
    events.clear()
    third = device.screenshot()
    if events != expected_order or third.generation <= second.generation:
        raise ScreenshotFrameClockVerificationError(
            "newer post-action screenshot was not acquired"
        )
    frame_clock = session._frame_clock
    session.close()
    try:
        frame_clock.borrow()
    except StaleFrameError:
        pass
    else:
        raise ScreenshotFrameClockVerificationError("session close retained a frame")

    return {
        "schema": SCHEMA,
        "passed": True,
        "upstream_commit": expected_commit,
        "patch_sha256": _sha256(PATCH_PATH),
        "patch_series_manifest_sha256": _sha256(SERIES_MANIFEST_PATH),
        "patched_screenshot_sha256": _sha256(screenshot_path),
        "normal_screenshot_source_preserved": True,
        "normal_device_source_preserved": True,
        "successful_screenshot_call_order": expected_order,
        "failed_refresh_call_order": failed_refresh_order,
        "frame_ids": [first.frame_id, second.frame_id, third.frame_id],
        "frame_generations": [first.generation, second.generation, third.generation],
        "observer_requests": len(handle.requests),
        "observation_hidden_refreshes": 0,
        "classified_pixel_accesses": len(pixel_records),
        "classified_pixel_operations": [
            record.operation.value for record in pixel_records
        ],
        "unclassified_pixel_accesses": 0,
        "runtime_handle_taps": len(handle.taps),
        "android_input_injected": False,
        "post_action_newer_generation_required": True,
        "session_close_clears_frame": True,
    }


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--patched-upstream", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    result = verify(args.patched_upstream)
    text = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
