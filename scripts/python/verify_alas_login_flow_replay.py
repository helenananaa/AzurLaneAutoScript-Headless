#!/usr/bin/env python3
"""Replay the pinned patched ALAS LoginHandler without Android input."""

from __future__ import annotations

import argparse
import hashlib
import importlib
import inspect
import json
import subprocess
import sys
import types
from dataclasses import dataclass
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
SCHEMA = "alas-headless.login-flow-replay/v1"
PATCHED_LOGIN_SHA256 = (
    "eea129c71f7bb7e9fd96fcc03ca295fcab43a4ec6f06e1e01cf0b13b66cb6cfe"
)


class LoginReplayError(RuntimeError):
    pass


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git(root: Path, *arguments: str, check: bool = True) -> str:
    completed = subprocess.run(
        ["git", "-C", str(root), *arguments],
        check=check,
        capture_output=True,
        text=True,
        timeout=30,
    )
    return completed.stdout.strip()


@dataclass
class ReplayButton:
    name: str


class ReplayTimer:
    def __init__(self, interval: float, count: int = 0) -> None:
        self.interval = interval
        self.count = count
        self._started = False

    def start(self) -> "ReplayTimer":
        self._started = True
        return self

    def reached(self) -> bool:
        return self.count == 4

    def reset(self) -> "ReplayTimer":
        self._started = True
        return self

    def clear(self) -> None:
        self._started = False

    def started(self) -> bool:
        return self._started

    def current_time(self) -> float:
        return 0.0


class ReplayLogger:
    def __init__(self) -> None:
        self.events: list[tuple[str, str]] = []

    def __getattr__(self, level: str):
        def record(message: Any = "") -> None:
            self.events.append((level, str(message)))

        return record


RESOURCE_NAMES = (
    "ANDROID_NO_RESPOND",
    "AVATAR_EXPIRED",
    "BACK_ARROW",
    "EVENT_LIST_CHECK",
    "GET_MISSION",
    "GOTO_MAIN",
    "LOGIN_ANNOUNCE",
    "LOGIN_ANNOUNCE_2",
    "LOGIN_CHECK",
    "LOGIN_GAME_UPDATE",
    "LOGIN_RETURN_INFO",
    "LOGIN_RETURN_SIGN",
    "MAINTENANCE_ANNOUNCE",
    "POPUP_CANCEL",
    "POPUP_CONFIRM",
    "POPUP_CONFIRM_WHITE",
)


def _module(name: str, **attributes: Any) -> types.ModuleType:
    module = types.ModuleType(name)
    for key, value in attributes.items():
        setattr(module, key, value)
    return module


def install_import_stubs(
    logger: ReplayLogger,
    upstream: Path,
) -> Mapping[str, ReplayButton]:
    """Stub only dependencies outside the exercised original login path."""

    for package, relative in (
        ("module", "module"),
        ("module.base", "module/base"),
        ("module.config", "module/config"),
        ("module.handler", "module/handler"),
        ("module.map", "module/map"),
        ("module.ui", "module/ui"),
    ):
        value = _module(package)
        value.__path__ = [str(upstream / relative)]
        sys.modules[package] = value

    scipy = _module("scipy")
    signal = _module("scipy.signal", find_peaks=lambda *args, **kwargs: ([], {}))
    scipy.signal = signal
    sys.modules["scipy"] = scipy
    sys.modules["scipy.signal"] = signal

    uiautomator = _module("uiautomator2", UiObject=type("UiObject", (), {}))
    exceptions = _module(
        "uiautomator2.exceptions",
        XPathElementNotFoundError=type("XPathElementNotFoundError", (Exception,), {}),
    )

    class XPathSelector:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

    xpath = _module(
        "uiautomator2.xpath",
        XPath=type("XPath", (), {}),
        XPathSelector=XPathSelector,
    )
    sys.modules["uiautomator2"] = uiautomator
    sys.modules["uiautomator2.exceptions"] = exceptions
    sys.modules["uiautomator2.xpath"] = xpath

    buttons = {name: ReplayButton(name) for name in RESOURCE_NAMES}
    asset_attributes = dict(buttons)
    asset_attributes["__all__"] = tuple(buttons)
    for name in ("module.handler.assets", "module.map.assets", "module.ui.assets"):
        sys.modules[name] = _module(name, **asset_attributes)

    sys.modules["module.base.timer"] = _module("module.base.timer", Timer=ReplayTimer)
    sys.modules["module.base.utils"] = _module(
        "module.base.utils",
        color_similarity_2d=lambda *args, **kwargs: None,
        crop=lambda value, *args, **kwargs: value,
    )
    server = _module("module.config.server", server="cn")
    sys.modules["module.config.server"] = server
    sys.modules["module.logger"] = _module("module.logger", logger=logger)
    sys.modules["module.ui.page"] = _module(
        "module.ui.page",
        page_campaign_menu=object(),
    )
    return buttons


class ReplayOracle:
    def __init__(self, scenario: str) -> None:
        self.scenario = scenario
        self.events: list[tuple[str, str]] = []
        self.enabled_values = {
            "login/enter": scenario == "entry",
            "overlay/bulletin/close": scenario == "bulletin",
            "overlay/network-reconnect/cancel": scenario == "expired",
            "overlay/login-data-expired/confirm": scenario == "expired",
            "overlay/network-reconnect/confirm": False,
            "main/battle": False,
            "main/formation": False,
        }

    def enabled(self, semantic_id: str) -> bool:
        self.events.append(("enabled", semantic_id))
        return self.enabled_values.get(semantic_id, False)

    def click(self, semantic_id: str):
        from alas_headless import ActionReceipt, Bounds, Point

        self.events.append(("click", semantic_id))
        self.enabled_values[semantic_id] = False
        self.enabled_values["main/battle"] = True
        return ActionReceipt(
            semantic_id=semantic_id,
            generation=7,
            point=Point(2, 3),
            bounds=Bounds(1, 2, 3, 4),
            path="replay/semantic-target",
        )

    def campaign_is_in_map(self) -> bool:
        self.events.append(("campaign_is_in_map", ""))
        return False

    def campaign_menu_is_entry(self) -> bool:
        return False

    def build_queue_timers(self):
        from alas_headless import SemanticGateClosed

        raise SemanticGateClosed("construction queue root is absent")

    def exists(self, semantic_id: str) -> bool:
        return False


class ReplayDevice:
    def __init__(self, adapter: Any) -> None:
        from alas_headless.adapter import (
            PixelAccessAudit,
            SemanticFrame,
            SemanticPixelGuard,
        )

        self.semantic_adapter = adapter
        self.events: list[tuple[Any, ...]] = []
        self.pixel_audit = PixelAccessAudit()
        self.image = SemanticPixelGuard(
            SemanticFrame(
                frame_id="login-replay-pixel-frame",
                pid=4242,
                generation=7,
                scene_handle=-76,
                captured_monotonic_ns=1_000_000_000,
                age_ms=20,
                fingerprint_sha256="a" * 64,
                raw_state_sha256="b" * 64,
                projections={"snapshot": {"generation": 7}},
            ),
            self.pixel_audit,
        )

    def screenshot_interval_set(self, value: float | None = None) -> None:
        self.events.append(("screenshot_interval_set", value))

    def stuck_record_clear(self) -> None:
        self.events.append(("stuck_record_clear",))

    def click_record_clear(self) -> None:
        self.events.append(("click_record_clear",))

    def get_orientation(self) -> None:
        self.events.append(("get_orientation",))

    def screenshot(self) -> None:
        self.events.append(("screenshot",))

    def click(self, button: ReplayButton, **kwargs: Any):
        self.events.append(("semantic_click", button.name))
        return self.semantic_adapter.click(button)


def make_ui_base(buttons: Mapping[str, ReplayButton]):
    class ReplayUI:
        def __init__(self, config: Any, device: ReplayDevice) -> None:
            self.config = config
            self.device = device
            self.fail_in_main = False

        def is_in_main(self) -> bool:
            if self.fail_in_main:
                raise RuntimeError("scripted login replay failure")
            return bool(
                self.appear(buttons["MAIN_GOTO_CAMPAIGN_WHITE"])
                or self.appear(buttons["MAIN_GOTO_FLEET"])
            )

        def match_template_color(self, button: ReplayButton, **kwargs: Any) -> bool:
            return self.device.semantic_adapter.match_template_color(button)

        def appear(self, button: ReplayButton, **kwargs: Any) -> bool:
            return self.device.semantic_adapter.appear(button)

        def appear_then_click(self, button: ReplayButton, **kwargs: Any) -> bool:
            if not self.appear(button, **kwargs):
                return False
            self.device.click(button)
            return True

        def handle_popup_confirm(self, name: str = "", **kwargs: Any) -> bool:
            cancel = buttons["POPUP_CANCEL"]
            confirm = buttons["POPUP_CONFIRM"]
            white = buttons["POPUP_CONFIRM_WHITE"]
            if self.appear(cancel) and self.appear(confirm):
                original = confirm.name
                confirm.name = original + "_" + name
                try:
                    self.device.click(confirm)
                finally:
                    confirm.name = original
                return True
            if self.appear(white):
                original = white.name
                white.name = original + "_" + name
                try:
                    self.device.click(white)
                finally:
                    white.name = original
                return True
            return False

        def handle_urgent_commission(self) -> bool:
            return self.appear(buttons["GET_MISSION"])

        def ui_page_main_popups(self, get_ship: bool = True) -> bool:
            del get_ship
            return False

    return ReplayUI


def load_patched_login_handler(upstream: Path):
    logger = ReplayLogger()
    buttons = install_import_stubs(logger, upstream)
    buttons["MAIN_GOTO_CAMPAIGN_WHITE"] = ReplayButton(
        "MAIN_GOTO_CAMPAIGN_WHITE"
    )
    buttons["MAIN_GOTO_FLEET"] = ReplayButton("MAIN_GOTO_FLEET")
    sys.modules["module.ui.ui"] = _module(
        "module.ui.ui",
        UI=make_ui_base(buttons),
    )
    sys.path.insert(0, str(upstream))
    module = importlib.import_module("module.handler.login")
    source_path = Path(inspect.getsourcefile(module.LoginHandler) or "").resolve()
    expected = (upstream / "module" / "handler" / "login.py").resolve()
    if source_path != expected:
        raise LoginReplayError("login handler did not load from the patched upstream")
    source = source_path.read_text(encoding="utf-8")
    if "semantic_adapter.begin_login()" not in source or "semantic_adapter.end_login()" not in source:
        raise LoginReplayError("login handler does not contain the semantic scope hooks")
    return module.LoginHandler, buttons, logger, source_path


def run_scenario(handler_class: Any, scenario: str) -> Mapping[str, Any]:
    from alas_headless import AlasSemanticAdapter
    from alas_headless.adapter import SemanticFrameIdentity

    oracle = ReplayOracle(scenario)
    gate_calls: list[bool] = []
    frame_identity = SemanticFrameIdentity(
        frame_id="login-replay-{0}".format(scenario),
        pid=4242,
        generation=7,
        scene_handle=-76,
        fingerprint_sha256="a" * 64,
        raw_state_sha256="b" * 64,
    )
    adapter = AlasSemanticAdapter(
        oracle,
        lambda: gate_calls.append(True),
        frame_observation_oracle=lambda: oracle,
        frame_identity_provider=lambda: frame_identity,
    )
    device = ReplayDevice(adapter)
    config = types.SimpleNamespace(SERVER="cn")
    handler = handler_class(config, device)
    handler.handle_app_login()
    if adapter._login_flow.active:
        raise LoginReplayError("login scope leaked after successful replay")
    if device.pixel_audit.records():
        raise LoginReplayError("login replay consumed framebuffer pixels")
    clicks = [event[1] for event in oracle.events if event[0] == "click"]
    expected = {
        "entry": ["login/enter"],
        "bulletin": ["overlay/bulletin/close"],
        "expired": ["overlay/login-data-expired/confirm"],
    }[scenario]
    if clicks != expected:
        raise LoginReplayError("login replay semantic action sequence changed")
    if device.events[0] != ("screenshot_interval_set", 1.0):
        raise LoginReplayError("login replay did not set the screenshot interval")
    if device.events[-1] != ("screenshot_interval_set", None):
        raise LoginReplayError("login replay did not restore the screenshot interval")
    return {
        "scenario": scenario,
        "semantic_actions": clicks,
        "package_gate_calls": len(gate_calls),
        "registry_dispatches": adapter._compat_observation_ordinal,
        "frame_id": frame_identity.frame_id,
        "scope_closed": not adapter._login_flow.active,
        "android_input_injected": False,
        "classified_pixel_accesses": 0,
        "unclassified_pixel_accesses": 0,
    }


def run_failure_scenario(handler_class: Any) -> Mapping[str, Any]:
    from alas_headless import AlasSemanticAdapter
    from alas_headless.adapter import SemanticFrameIdentity

    oracle = ReplayOracle("entry")
    gate_calls: list[bool] = []
    frame_identity = SemanticFrameIdentity(
        frame_id="login-replay-failure",
        pid=4242,
        generation=7,
        scene_handle=-76,
        fingerprint_sha256="a" * 64,
        raw_state_sha256="b" * 64,
    )
    adapter = AlasSemanticAdapter(
        oracle,
        lambda: gate_calls.append(True),
        frame_observation_oracle=lambda: oracle,
        frame_identity_provider=lambda: frame_identity,
    )
    device = ReplayDevice(adapter)
    handler = handler_class(types.SimpleNamespace(SERVER="cn"), device)
    handler.fail_in_main = True
    try:
        handler.handle_app_login()
    except RuntimeError as exc:
        if str(exc) != "scripted login replay failure":
            raise
    else:
        raise LoginReplayError("scripted login failure did not propagate")
    if adapter._login_flow.active:
        raise LoginReplayError("login scope leaked after failed replay")
    if device.events[-1] != ("screenshot_interval_set", None):
        raise LoginReplayError("failed login replay did not restore interval")
    if any(event[0] == "click" for event in oracle.events):
        raise LoginReplayError("failed login replay unexpectedly dispatched input")
    if device.pixel_audit.records():
        raise LoginReplayError("failed login replay consumed framebuffer pixels")
    return {
        "scenario": "failure",
        "exception": "scripted login replay failure",
        "package_gate_calls": len(gate_calls),
        "scope_closed": not adapter._login_flow.active,
        "frame_id": frame_identity.frame_id,
        "android_input_injected": False,
        "classified_pixel_accesses": 0,
        "unclassified_pixel_accesses": 0,
    }


def verify(upstream: Path) -> Mapping[str, Any]:
    check_generated_patch(SERIES_MANIFEST_PATH, PATCH_PATH, root=ROOT)
    upstream = upstream.resolve()
    login_source = upstream / "module" / "handler" / "login.py"
    if not login_source.is_file():
        raise LoginReplayError("patched upstream login source is missing")
    lock = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    expected_commit = lock["commit"]
    if _git(upstream, "rev-parse", "HEAD").lower() != expected_commit:
        raise LoginReplayError("patched upstream commit does not match the lock")
    reverse = subprocess.run(
        ["git", "-C", str(upstream), "apply", "--reverse", "--check", str(PATCH_PATH)],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if reverse.returncode != 0:
        raise LoginReplayError("canonical patch is not applied to the replay tree")
    if _sha256(login_source) != PATCHED_LOGIN_SHA256:
        raise LoginReplayError("patched upstream login source identity changed")

    handler_class, _, _, source_path = load_patched_login_handler(upstream)
    scenarios = tuple(
        run_scenario(handler_class, scenario)
        for scenario in ("entry", "bulletin", "expired")
    )
    failure = run_failure_scenario(handler_class)
    return {
        "schema": SCHEMA,
        "passed": True,
        "upstream_commit": expected_commit,
        "patch_sha256": _sha256(PATCH_PATH),
        "patch_series_manifest_sha256": _sha256(SERIES_MANIFEST_PATH),
        "patched_login_sha256": _sha256(source_path),
        "handler_module": "module.handler.login.LoginHandler",
        "scenarios": scenarios,
        "failure_scenario": failure,
        "scenario_count": len(scenarios) + 1,
        "android_input_injected": False,
        "classified_pixel_accesses": 0,
        "unclassified_pixel_accesses": 0,
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
