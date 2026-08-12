"""Run the H05 G36 setup once and two unchanged-map, input-free preflights.

The setup phase delegates stage entry, fleet preparation, and sortie to the
pinned ALAS ``CampaignRun``.  It is deliberately excluded from the H05 runs.
The two H05 runs use fresh campaign contexts on one zero-input semantic
session, let original ALAS select the target and execute its ``_goto()``
prefix, capture the exact ``device.click(grid)`` boundary, and perform a fresh
top-raycast recheck.
"""

from __future__ import annotations

import argparse
import hashlib
import inspect
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from types import MethodType
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))

from alas_headless import (  # noqa: E402
    AlasSemanticSession,
    ObserverTransportError,
    PINNED_CN_GAME_FINGERPRINT,
    SemanticGateClosed,
    alas_campaign_combat_map_state_to_json,
    load_alas_combat_observer_manifest,
    preview_alas_campaign_decision,
    preview_alas_campaign_goto_input,
    synchronize_alas_campaign_map,
)
from alas_headless.adapter import build_g36_live_preflight_bundle  # noqa: E402
import alas_headless.semantic_oracle as semantic_oracle_module  # noqa: E402


RUN_SCHEMA = "alas-headless.g36-live-preflight-run/v1"
STOP_BOUNDARY = "original-device-click-grid"
ANGLE_PACKAGE = "org.chromium.angle"
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--serial", required=True)
    parser.add_argument("--alas-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--setup-output", type=Path)
    parser.add_argument("--config", default="semantic_e2e")
    parser.add_argument(
        "--profile",
        type=Path,
        default=(
            ROOT
            / "integration"
            / "alas"
            / "profiles"
            / "g36-12-4-normal-one-battle.zero-input.json"
        ),
    )
    parser.add_argument(
        "--defensive-preflight",
        type=Path,
        default=ROOT / "integration" / "alas" / "g36-defensive-preflight.json",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=ROOT / "integration" / "alas" / "combat-observer-manifest.json",
    )
    parser.add_argument("--adb", default="adb")
    parser.add_argument("--adb-command-timeout-seconds", type=int, default=10)
    parser.add_argument("--startup-timeout-seconds", type=int, default=180)
    return parser.parse_args()


def canonical_sha256(value: Any) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def utc_now() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


def read_json(path: Path) -> Mapping[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, Mapping):
        raise SystemExit("qualification JSON root is not an object: " + str(path))
    return value


def write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(str(temporary), str(path))


def run_adb(adb: str, serial: str, *arguments: str) -> str:
    completed = subprocess.run(
        [adb, "-s", serial, *arguments],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        timeout=30,
    )
    if completed.returncode != 0:
        raise SystemExit("ADB identity query failed: " + completed.stdout.strip())
    return completed.stdout.strip()


def installed_angle_sha256(adb: str, serial: str) -> str:
    output = run_adb(adb, serial, "shell", "pm", "path", ANGLE_PACKAGE)
    paths = [
        line.removeprefix("package:").strip()
        for line in output.splitlines()
        if line.startswith("package:")
    ]
    if len(paths) != 1:
        raise SystemExit("expected exactly one installed ANGLE base APK")
    digest_output = run_adb(
        adb, serial, "shell", "sha256sum", paths[0]
    ).split()
    if not digest_output or SHA256_PATTERN.fullmatch(digest_output[0]) is None:
        raise SystemExit("installed ANGLE APK hash is malformed")
    return digest_output[0]


def map_kwargs(campaign: Any) -> Mapping[str, Any]:
    return {
        "columns": campaign.MAP.shape[0] + 1,
        "rows": campaign.MAP.shape[1] + 1,
        "land_cells": tuple(grid.location for grid in campaign.MAP if grid.is_land),
        "expected_fleet_count": sum(
            (bool(campaign.config.Fleet_Fleet1), bool(campaign.config.Fleet_Fleet2))
        ),
    }


def decision_identity(decision: Any) -> tuple[Any, ...]:
    return (
        decision.stage_code,
        decision.battle_count,
        decision.branch_name,
        decision.fleet_index,
        decision.fleet_marker,
        decision.origin_node,
        decision.target_node,
        decision.target_kind,
        decision.expected,
        decision.cost,
        decision.weight,
        decision.route_nodes,
        decision.goto_nodes,
        decision.step_optimize,
        decision.turning_optimize,
    )


def point_json(value: Any) -> Mapping[str, float]:
    return {"x": float(value.x), "y": float(value.y)}


def bounds_json(value: Any) -> Mapping[str, float]:
    return {
        "left": float(value.left),
        "top": float(value.top),
        "right": float(value.right),
        "bottom": float(value.bottom),
    }


def wait_for_new_map_state(
    session: AlasSemanticSession,
    campaign: Any,
    generation: int,
    timeout_seconds: float,
) -> Any:
    deadline = time.monotonic() + timeout_seconds
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            state = session.campaign_map_state(**map_kwargs(campaign))
            if state.generation > generation:
                return state
        except (ObserverTransportError, SemanticGateClosed) as exc:
            last_error = exc
        time.sleep(0.05)
    detail = "" if last_error is None else ": " + str(last_error)
    raise SystemExit("fresh target-recheck generation did not arrive" + detail)


def make_session(args: argparse.Namespace, driver_revision: str, *, setup: bool):
    return AlasSemanticSession(
        serial=args.serial,
        driver_revision=driver_revision,
        adb=args.adb,
        package="com.bilibili.azurlane",
        campaign_stage_entry_budget=1 if setup else 0,
        campaign_fleet_mutation_budget=3 if setup else 0,
        campaign_sortie_budget=1 if setup else 0,
        campaign_combat_budget=1 if not setup else 0,
        campaign_viewport_swipe_budget=0,
        campaign_camera_positioning_budget=0,
        adb_command_timeout_seconds=args.adb_command_timeout_seconds,
    )


def configure_alas(alas: Any, profile: Mapping[str, Any], serial: str) -> None:
    values = dict(profile["alas_config"])
    values["Emulator_Serial"] = serial
    alas.config.bind("Main")
    writable = {}
    readonly = {}
    for name, value in values.items():
        descriptor = inspect.getattr_static(type(alas.config), name, None)
        if isinstance(descriptor, property) and descriptor.fset is None:
            readonly[name] = value
        else:
            writable[name] = value
    alas.config.override(**writable)
    for name, expected in readonly.items():
        actual = getattr(alas.config, name)
        if isinstance(actual, tuple) and isinstance(expected, list):
            actual = list(actual)
        if actual != expected:
            raise SemanticGateClosed(
                "H05 read-only ALAS profile field changed: " + name
            )


def stable_campaign_page(session: AlasSemanticSession) -> Any:
    last_error: Exception | None = None
    for _ in range(8):
        try:
            return session.campaign_page_state()
        except SemanticGateClosed as exc:
            last_error = exc
            if str(exc) not in (
                "observer endpoints are not generation-coherent",
                "campaign snapshots are not coherent",
                "observer snapshot is stale",
            ):
                raise
        time.sleep(0.05)
    assert last_error is not None
    raise last_error


def install_typed_chapter_bootstrap(
    runner: Any,
    session: AlasSemanticSession,
    campaign_page: Any,
    startup_records: list[Mapping[str, Any]],
) -> None:
    from module.ui.page import page_campaign

    expected_stage = runner.config.Campaign_Name.replace("campaign_", "").replace(
        "_", "-"
    )
    visible = tuple(item.stage_code for item in campaign_page.stages)
    if expected_stage not in visible:
        raise SemanticGateClosed("configured stage is absent from typed chapter page")
    original_load_campaign = runner.load_campaign

    def load_campaign_with_bootstrap(self: Any, name: str, folder="campaign_main"):
        loaded = original_load_campaign(name, folder=folder)
        original_get_current_page = self.campaign.ui_get_current_page
        used = False

        def typed_first_page(campaign_self: Any, *unused: Any, **unused_kw: Any):
            nonlocal used
            del unused, unused_kw
            if used:
                return original_get_current_page()
            confirmed = stable_campaign_page(session)
            if expected_stage not in tuple(item.stage_code for item in confirmed.stages):
                raise SemanticGateClosed("typed chapter page changed before ALAS use")
            used = True
            campaign_self.ui_current = page_campaign
            campaign_self.ui_get_current_page = original_get_current_page
            original_state = session.campaign_page_state
            reads_remaining = 4

            def cached_state():
                nonlocal reads_remaining
                if reads_remaining <= 0:
                    return original_state()
                reads_remaining -= 1
                context = session.open()._campaign_context
                if context is not None:
                    context.passive_transition_until = time.monotonic() + 90.0
                return confirmed

            session.campaign_page_state = cached_state
            startup_records.append(
                {
                    "owner": "typed-qualification-bootstrap-once",
                    "generation": confirmed.generation,
                    "chapter_name": confirmed.chapter_name,
                    "stage_codes": list(visible),
                    "cached_read_budget": 4,
                }
            )
            return page_campaign

        self.campaign.ui_get_current_page = MethodType(
            typed_first_page, self.campaign
        )
        return loaded

    runner.load_campaign = MethodType(load_campaign_with_bootstrap, runner)


def install_readonly_screenshot_retry(device: Any) -> None:
    """Retry only transient observer joins; every accepted frame stays strict."""

    original = device.screenshot
    transient = (
        "semantic frame mixes UI and state generations",
        "semantic frame mixes observer generations",
        "observer endpoints are not generation-coherent",
        "observer snapshot is stale",
    )

    def coherent_screenshot(self: Any, *args: Any, **kwargs: Any):
        del self
        last_error: Exception | None = None
        for _ in range(40):
            try:
                return original(*args, **kwargs)
            except SemanticGateClosed as exc:
                if str(exc) not in transient:
                    raise
                last_error = exc
                time.sleep(0.05)
        assert last_error is not None
        raise last_error

    device.screenshot = MethodType(coherent_screenshot, device)


def install_setup_click_frame_refresh(
    device: Any, session: AlasSemanticSession
) -> None:
    """Refresh the strict frame immediately before each setup-only ALAS click."""

    original = device.click

    def refreshed_click(self: Any, *args: Any, **kwargs: Any):
        frame = session.refresh_frame()
        self.image = session.pixel_guard(frame)
        return original(*args, **kwargs)

    device.click = MethodType(refreshed_click, device)


def prepare_map_with_original_alas(
    args: argparse.Namespace,
    profile: Mapping[str, Any],
    manifest: Any,
    AzurLaneAutoScript: Any,
    CampaignRun: Any,
    ScriptEnd: type[BaseException],
) -> tuple[Any, list[Mapping[str, Any]], Mapping[str, Any]]:
    session = make_session(args, manifest.driver_revision, setup=True)
    from module.handler.auto_search import AutoSearchHandler
    from module.handler.info_handler import InfoHandler

    original_factory = AlasSemanticSession.__dict__["from_environment"]
    original_request_observer_state = semantic_oracle_module.request_observer_state
    original_auto_search_probe = AutoSearchHandler.is_in_auto_search_menu
    original_story_skip = InfoHandler.handle_story_skip
    setup_ui_cache: list[Mapping[str, Any]] = []
    startup_records: list[Mapping[str, Any]] = []

    def factory(cls: Any, serial: str):
        del cls
        if serial != args.serial:
            raise RuntimeError("H05 setup serial changed")
        return session

    AlasSemanticSession.from_environment = classmethod(factory)
    # The rendered ANGLE backend can advance once between the atomic
    # snapshot/buttons response and the following UI response.  Setup-only
    # ALAS screenshots therefore use the observer's reviewed legacy triple,
    # whose exact-generation coherence is still enforced by SemanticFrameClock.
    # The H05 runs below never inherit this compatibility path.
    def exact_legacy_state(request: Any):
        for _ in range(200):
            snapshot = request("GET /v1/snapshot\n")
            buttons = request("GET /v1/buttons\n")
            ui = request("GET /v1/ui\n")
            generations = {
                snapshot.get("generation"),
                buttons.get("generation"),
                ui.get("generation"),
            }
            if len(generations) == 1 and None not in generations:
                setup_ui_cache.append(ui)
                return snapshot, buttons, False
        raise SemanticGateClosed(
            "setup observer did not publish an exact-generation triple"
        )

    semantic_oracle_module.request_observer_state = exact_legacy_state

    def reviewed_manual_campaign_entry(self: Any) -> bool:
        if self.config.Campaign_UseAutoSearch is not False:
            raise SemanticGateClosed(
                "H05 setup auto-search configuration changed"
            )
        return False

    AutoSearchHandler.is_in_auto_search_menu = reviewed_manual_campaign_entry

    def reviewed_non_story_surface(self: Any, drop: Any = None) -> bool:
        del drop
        oracle = session.open().oracle
        typed_checks = (
            oracle.campaign_page_state,
            lambda: oracle.campaign_map_preparation_state(
                profile["qualification"]["campaign_name"]
            ),
            lambda: oracle.campaign_fleet_preparation_state(
                profile["qualification"]["campaign_name"]
            ),
        )
        for check in typed_checks:
            try:
                check()
                frame = session.refresh_frame()
                self.device.image = session.pixel_guard(frame)
                return False
            except (ObserverTransportError, SemanticGateClosed):
                pass
        try:
            if oracle.campaign_is_in_map():
                frame = session.refresh_frame()
                self.device.image = session.pixel_guard(frame)
                return False
        except (ObserverTransportError, SemanticGateClosed):
            pass
        raise SemanticGateClosed(
            "H05 setup reached an unqualified possible story surface"
        )

    InfoHandler.handle_story_skip = reviewed_non_story_surface
    try:
        alas = AzurLaneAutoScript(config_name=args.config)
        configure_alas(alas, profile, args.serial)
        install_readonly_screenshot_retry(alas.device)
        install_setup_click_frame_refresh(alas.device, session)
        runner = CampaignRun(config=alas.config, device=alas.device)
        oracle = session.open().oracle
        original_oracle_request = oracle._request

        def setup_cached_ui_request(request_line: str):
            if request_line == "GET /v1/ui\n" and setup_ui_cache:
                return setup_ui_cache.pop(0)
            return original_oracle_request(request_line)

        oracle._request = setup_cached_ui_request
        stage_code = profile["qualification"]["campaign_name"]
        for _ in range(3):
            try:
                reconnect = oracle.enabled("overlay/network-reconnect/confirm")
            except (ObserverTransportError, SemanticGateClosed):
                reconnect = False
            if not reconnect:
                break
            receipt = oracle.click("overlay/network-reconnect/confirm")
            startup_records.append(
                {
                    "owner": "typed-setup-network-recovery",
                    "semantic_id": receipt.semantic_id,
                    "generation": receipt.generation,
                    "path": receipt.path,
                    "setup_input_injected": True,
                    "excluded_from_h05_runs": True,
                }
            )
            time.sleep(3.0)
        else:
            raise SystemExit("setup network recovery budget was exhausted")
        recovery = None
        try:
            oracle.campaign_map_preparation_state(stage_code)
            recovery = oracle.cancel_campaign_map_preparation(stage_code)
        except (ObserverTransportError, SemanticGateClosed):
            try:
                oracle.campaign_fleet_preparation_state(stage_code)
                recovery = oracle.cancel_campaign_fleet_preparation(stage_code)
            except (ObserverTransportError, SemanticGateClosed):
                pass
        if recovery is not None:
            startup_records.append(
                {
                    "owner": "typed-setup-recovery",
                    "semantic_id": recovery.semantic_id,
                    "generation": recovery.generation,
                    "path": recovery.path,
                    "setup_input_injected": True,
                    "excluded_from_h05_runs": True,
                }
            )
            deadline = time.monotonic() + args.startup_timeout_seconds
            while time.monotonic() < deadline:
                try:
                    stable_campaign_page(session)
                    break
                except (ObserverTransportError, SemanticGateClosed):
                    time.sleep(0.1)
            else:
                raise SystemExit("setup recovery did not restore the chapter page")
        in_map = oracle.campaign_is_in_map()
        if not in_map:
            startup_records.append(
                {
                    "owner": "original-alas-stage-fleet-sortie-setup",
                    "setup_input_injected": True,
                    "excluded_from_h05_runs": True,
                }
            )
            page = stable_campaign_page(session)
            install_typed_chapter_bootstrap(runner, session, page, startup_records)
        setup_pid = session.runtime_handle.pid
        setup_fingerprint = session.runtime_handle.fingerprint_sha256
        try:
            runner.run(
                name=alas.config.Campaign_Name,
                folder=alas.config.Campaign_Event,
                mode=alas.config.Campaign_Mode,
            )
        except ScriptEnd as exc:
            if str(exc) not in (
                "Semantic campaign sortie validation complete",
                "Semantic ALAS goto input preview validation complete",
            ):
                raise
        deadline = time.monotonic() + args.startup_timeout_seconds
        while time.monotonic() < deadline:
            try:
                if session.open().oracle.campaign_is_in_map():
                    state = session.open().oracle.campaign_map_state(
                        profile["qualification"]["campaign_name"],
                        **map_kwargs(runner.campaign),
                    )
                    if state.enemies:
                        startup_records.append(
                            {
                                "owner": "original-alas-setup-handoff",
                                "generation": state.generation,
                                "enemy_nodes": [item.node for item in state.enemies],
                                "setup_input_injected": False,
                                "excluded_from_h05_runs": True,
                            }
                        )
                        return runner.campaign, startup_records, {
                            "pid": setup_pid,
                            "fingerprint_sha256": setup_fingerprint,
                        }
            except (ObserverTransportError, SemanticGateClosed):
                pass
            time.sleep(0.1)
        raise SystemExit("original ALAS setup did not hand off a stable 12-4 map")
    finally:
        InfoHandler.handle_story_skip = original_story_skip
        AutoSearchHandler.is_in_auto_search_menu = original_auto_search_probe
        semantic_oracle_module.request_observer_state = (
            original_request_observer_state
        )
        AlasSemanticSession.from_environment = original_factory
        try:
            session.close()
        except ObserverTransportError:
            pass


def run_zero_input_preflight(
    args: argparse.Namespace,
    campaign: Any,
    manifest: Any,
    defensive_sha256: str,
    angle_sha256: str,
    expected_identity: Mapping[str, Any],
    session: AlasSemanticSession | None = None,
) -> Mapping[str, Any]:
    owns_session = session is None
    if session is None:
        session = make_session(args, manifest.driver_revision, setup=False)
    stage_code = campaign.MAP.name
    try:
        session.begin_campaign_pre_sortie(stage_code)
        state = session.campaign_map_state(**map_kwargs(campaign))
        handle = session.runtime_handle
        if handle is None:
            raise SemanticGateClosed("H05 runtime handle is unavailable")
        if (
            handle.pid != expected_identity["pid"]
            or handle.fingerprint_sha256 != expected_identity["fingerprint_sha256"]
        ):
            raise SemanticGateClosed("H05 setup runtime identity changed")
        projection = synchronize_alas_campaign_map(campaign, state)
        decision = preview_alas_campaign_decision(campaign, projection)
        admission = session.authorize_campaign_combat(decision, state)
        if admission is None:
            raise SemanticGateClosed("H05 combat admission is absent")
        preview = preview_alas_campaign_goto_input(
            campaign, projection, decision, admission, state
        )
        fresh_state = wait_for_new_map_state(
            session,
            campaign,
            preview.input_generation,
            args.startup_timeout_seconds,
        )
        if fresh_state.signature != state.signature:
            raise SemanticGateClosed("H05 logical map changed before target recheck")
        fresh_projection = synchronize_alas_campaign_map(campaign, fresh_state)
        fresh_decision = preview_alas_campaign_decision(campaign, fresh_projection)
        if decision_identity(fresh_decision) != decision_identity(decision):
            raise SemanticGateClosed("H05 original ALAS decision changed on recheck")
        target = session.open().oracle.campaign_map_cell_input(
            fresh_state, decision.target_node
        )
        if (
            target.path != preview.cell_path
            or target.point != preview.point
            or target.bounds != preview.bounds
            or target.raycast_top is not True
        ):
            raise SemanticGateClosed("H05 exact target geometry changed on recheck")
        fingerprint = session.open().oracle.fingerprint
        if (fingerprint.width, fingerprint.height) != (1280, 720):
            raise SemanticGateClosed("H05 rendered surface is not 1280x720")
        logical_json = alas_campaign_combat_map_state_to_json(state)
        stable_map_json = dict(logical_json)
        stable_map_json.pop("generation", None)
        game_hash = canonical_sha256(asdict(PINNED_CN_GAME_FINGERPRINT))
        record = {
            "schema": RUN_SCHEMA,
            "captured_at_utc": utc_now(),
            "runtime_identity": {
                "fingerprint_sha256": handle.fingerprint_sha256,
                "game_fingerprint_sha256": game_hash,
                "observer_apk_sha256": angle_sha256,
                "package": session.package,
                "component": session.component,
                "serial": args.serial,
                "pid": handle.pid,
                "driver_revision": manifest.driver_revision,
                "surface": {"width": fingerprint.width, "height": fingerprint.height},
            },
            "generations": {
                "map": state.generation,
                "decision": decision.generation,
                "target_recheck": fresh_state.generation,
            },
            "map_signature_sha256": canonical_sha256(stable_map_json),
            "logical_state_sha256": canonical_sha256(state.signature),
            "decision": {
                "stage_code": decision.stage_code,
                "battle_count": decision.battle_count,
                "branch_name": decision.branch_name,
                "fleet_index": decision.fleet_index,
                "fleet_marker": decision.fleet_marker,
                "origin_node": decision.origin_node,
                "target_node": decision.target_node,
                "target_kind": decision.target_kind,
                "expected": decision.expected,
                "cost": decision.cost,
                "route_nodes": list(decision.route_nodes),
                "goto_nodes": list(decision.goto_nodes),
            },
            "camera_branch": {"required": False, "owner": "original-alas"},
            "target_recheck": {
                "node": decision.target_node,
                "path": target.path,
                "top_raycast": target.raycast_top,
                "point": point_json(target.point),
                "bounds": bounds_json(target.bounds),
            },
            "original_goto_call_order": list(preview.call_order),
            "capability_recovery_closure": {
                "defensive_preflight_sha256": defensive_sha256,
                "closure_complete": True,
                "grid_click_allowed": False,
                "recovery_policy": "qualification-stop",
            },
            "stop_boundary": STOP_BOUNDARY,
            "unknown_calls": [],
            "grid_input_injected": False,
            "android_input_injected": False,
            "camera_input_injected": False,
            "input_injected": False,
        }
        return record
    finally:
        session.end_campaign_pre_sortie()
        if owns_session:
            try:
                session.close()
            except ObserverTransportError:
                pass


def run_repeated_zero_input_preflights(
    args: argparse.Namespace,
    campaign: Any,
    manifest: Any,
    defensive_sha256: str,
    angle_sha256: str,
    expected_identity: Mapping[str, Any],
) -> list[Mapping[str, Any]]:
    """Use one verified handle but two fresh, uncommitted campaign contexts."""

    session = make_session(args, manifest.driver_revision, setup=False)
    try:
        return [
            run_zero_input_preflight(
                args,
                campaign,
                manifest,
                defensive_sha256,
                angle_sha256,
                expected_identity,
                session=session,
            )
            for _ in range(2)
        ]
    finally:
        try:
            session.close()
        except ObserverTransportError:
            pass


def position_for_bounded_preflight(
    args: argparse.Namespace,
    campaign: Any,
    manifest: Any,
    expected_identity: Mapping[str, Any],
) -> list[Mapping[str, Any]]:
    """Spend at most one setup-only exact intermediate ALAS goto movement."""

    session = make_session(args, manifest.driver_revision, setup=False)
    records: list[Mapping[str, Any]] = []
    try:
        session.begin_campaign_pre_sortie(campaign.MAP.name)
        state = session.campaign_map_state(**map_kwargs(campaign))
        handle = session.runtime_handle
        if handle is None or (
            handle.pid != expected_identity["pid"]
            or handle.fingerprint_sha256 != expected_identity["fingerprint_sha256"]
        ):
            raise SemanticGateClosed("H05 positioning runtime identity changed")
        projection = synchronize_alas_campaign_map(campaign, state)
        decision = preview_alas_campaign_decision(campaign, projection)
        try:
            admission = session.authorize_campaign_combat(decision, state)
        except SemanticGateClosed as exc:
            if "same-cell or three-step route" not in str(exc):
                raise
            admission = None
        if admission is not None:
            return records
        if (
            len(decision.goto_nodes) < 2
            or decision.goto_nodes[-1] != decision.target_node
        ):
            raise SemanticGateClosed(
                "H05 setup has no original ALAS intermediate goto"
            )
        intermediate = decision.goto_nodes[0]
        if (
            intermediate == decision.target_node
            or intermediate not in decision.route_nodes[1:-1]
            or intermediate in {item.node for item in state.enemies}
            or intermediate in {item.node for item in state.fleets}
            or intermediate in {item.node for item in state.pickups}
        ):
            raise SemanticGateClosed(
                "H05 setup intermediate goto is not one empty route cell"
            )
        target = session.open().oracle.campaign_map_cell_input(
            state, intermediate
        )
        if target.point is None or target.bounds is None or target.raycast_top is not True:
            raise SemanticGateClosed(
                "H05 setup intermediate goto is not exact top-raycast"
            )
        if handle.foreground_component() != session.component:
            raise SemanticGateClosed("H05 setup foreground changed before movement")
        handle.tap(int(round(target.point.x)), int(round(target.point.y)))

        old_fleet = next(
            item for item in state.fleets if item.marker == decision.fleet_marker
        )
        deadline = time.monotonic() + args.startup_timeout_seconds
        moved = None
        while time.monotonic() < deadline:
            try:
                candidate = session.campaign_map_state(**map_kwargs(campaign))
                current = next(
                    item
                    for item in candidate.fleets
                    if item.marker == decision.fleet_marker
                )
                if candidate.generation > state.generation and current.node == intermediate:
                    moved = candidate
                    new_fleet = current
                    break
            except (ObserverTransportError, SemanticGateClosed, StopIteration):
                pass
            time.sleep(0.1)
        if moved is None:
            raise SemanticGateClosed(
                "H05 setup intermediate movement was not proven"
            )
        if (
            new_fleet.ammo != old_fleet.ammo
            or new_fleet.ammo_capacity != old_fleet.ammo_capacity
            or tuple(
                (item.node, item.object_id, item.fighting)
                for item in moved.enemies
            )
            != tuple(
                (item.node, item.object_id, item.fighting)
                for item in state.enemies
            )
            or tuple((item.node, item.kind) for item in moved.pickups)
            != tuple((item.node, item.kind) for item in state.pickups)
        ):
            raise SemanticGateClosed(
                "H05 setup intermediate movement changed combat state"
            )
        records.append(
            {
                "owner": "original-alas-intermediate-goto-setup",
                "generation_before": state.generation,
                "generation_after": moved.generation,
                "origin_node": decision.origin_node,
                "intermediate_node": intermediate,
                "final_target_node": decision.target_node,
                "original_goto_nodes": list(decision.goto_nodes),
                "path": target.path,
                "point": point_json(target.point),
                "bounds": bounds_json(target.bounds),
                "top_raycast": True,
                "ammo_unchanged": True,
                "enemies_unchanged": True,
                "setup_input_injected": True,
                "excluded_from_h05_runs": True,
            }
        )
        return records
    finally:
        session.end_campaign_pre_sortie()
        try:
            session.close()
        except ObserverTransportError:
            pass


def main() -> int:
    args = parse_args()
    args.alas_root = args.alas_root.resolve()
    args.output = args.output.resolve()
    args.setup_output = (
        args.setup_output.resolve()
        if args.setup_output is not None
        else args.output.with_name(args.output.stem + ".setup.json")
    )
    args.profile = args.profile.resolve()
    args.defensive_preflight = args.defensive_preflight.resolve()
    args.manifest = args.manifest.resolve()
    if not (args.alas_root / "alas.py").is_file():
        raise SystemExit("ALAS root does not contain alas.py")
    if args.output.exists() or args.setup_output.exists():
        raise SystemExit("H05 output or setup receipt already exists")
    if not 1 <= args.adb_command_timeout_seconds <= 120:
        raise SystemExit("ADB timeout must be in [1, 120]")
    if not 20 <= args.startup_timeout_seconds <= 360:
        raise SystemExit("startup timeout must be in [20, 360]")

    profile = read_json(args.profile)
    defensive = read_json(args.defensive_preflight)
    manifest = load_alas_combat_observer_manifest(args.manifest)
    if profile.get("upstream_alas_commit") != "81ccf63b4540f00241628c82a58c02c7a2bb11af":
        raise SystemExit("H05 profile does not pin the reviewed ALAS commit")
    angle_sha256 = installed_angle_sha256(args.adb, args.serial)
    sys.path.insert(0, str(args.alas_root))
    from alas import AzurLaneAutoScript
    from module.campaign.run import CampaignRun
    from module.exception import ScriptEnd

    os.environ["ALAS_SEMANTIC_MODE"] = "1"
    os.environ["ALAS_SEMANTIC_DRIVER_REVISION"] = manifest.driver_revision
    previous_cwd = Path.cwd()
    try:
        os.chdir(str(args.alas_root))
        campaign, setup_records, expected_identity = prepare_map_with_original_alas(
            args,
            profile,
            manifest,
            AzurLaneAutoScript,
            CampaignRun,
            ScriptEnd,
        )
        setup_records.extend(
            position_for_bounded_preflight(
                args, campaign, manifest, expected_identity
            )
        )
        defensive_sha256 = canonical_sha256(defensive)
        runs = run_repeated_zero_input_preflights(
            args,
            campaign,
            manifest,
            defensive_sha256,
            angle_sha256,
            expected_identity,
        )
    finally:
        os.chdir(str(previous_cwd))

    bundle = build_g36_live_preflight_bundle(
        profile=profile,
        defensive_preflight=defensive,
        runs=runs,
    )
    write_json(args.output, bundle)
    write_json(
        args.setup_output,
        {
            "schema": "alas-headless.g36-live-preflight-setup/v1",
            "captured_at_utc": utc_now(),
            "owner": "original-alas",
            "excluded_from_h05_runs": True,
            "input_injected": any(
                item.get("setup_input_injected") is True
                for item in setup_records
            ),
            "records": setup_records,
            "qualification_bundle_sha256": bundle["bundle_sha256"],
        },
    )
    print(json.dumps(bundle, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
