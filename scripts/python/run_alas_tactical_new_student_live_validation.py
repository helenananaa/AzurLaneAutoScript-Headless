#!/usr/bin/env python3
"""Exercise the original ALAS Tactical new-student branch on one live client."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import subprocess
import sys
import time
import traceback
import uuid
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "python") not in sys.path:
    sys.path.insert(0, str(ROOT / "python"))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def _adb(serial: str, *arguments: str) -> str:
    completed = subprocess.run(
        ("adb", "-s", serial, *arguments),
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=90,
    )
    return completed.stdout.strip()


def _load_modules(
    alas_root: Path,
    driver_revision: str,
    *,
    allow_tactical_rewards: bool,
    tactical_assign_budget: int,
) -> SimpleNamespace:
    os.environ["ALAS_SEMANTIC_MODE"] = "1"
    os.environ["ALAS_SEMANTIC_DRIVER_REVISION"] = driver_revision
    os.environ["ALAS_SEMANTIC_ADB"] = "adb"
    os.environ["ALAS_SEMANTIC_ALLOW_TACTICAL_REWARDS"] = (
        "1" if allow_tactical_rewards else "0"
    )
    os.environ["ALAS_SEMANTIC_TACTICAL_ASSIGN_BUDGET"] = str(
        tactical_assign_budget
    )
    for path in (ROOT / "python", alas_root):
        value = str(path)
        if value not in sys.path:
            sys.path.insert(0, value)
    os.chdir(alas_root)
    from alas import AzurLaneAutoScript

    return SimpleNamespace(AzurLaneAutoScript=AzurLaneAutoScript)


def _close(instance: object | None) -> None:
    if instance is None:
        return
    device = getattr(instance, "__dict__", {}).get("device")
    session = getattr(device, "__dict__", {}).get("semantic_adapter")
    if session is not None:
        session.close()


def _receipt_value(receipt: object | None) -> dict[str, Any] | None:
    if receipt is None:
        return None
    point = getattr(receipt, "point", None)
    return {
        "semantic_id": getattr(receipt, "semantic_id", None),
        "generation": getattr(receipt, "generation", None),
        "path": getattr(receipt, "path", None),
        "point": (
            {"x": point.x, "y": point.y} if point is not None else None
        ),
    }


def _ensure_reward_page(oracle: Any) -> None:
    from alas_headless.semantic_oracle import SemanticGateClosed

    if oracle.exists("reward/page/back"):
        return
    try:
        course_cancel_available = oracle.enabled("tactical/course/cancel")
    except SemanticGateClosed:
        course_cancel_available = False
    if course_cancel_available:
        close_course = oracle.click("tactical/course/cancel")
        next_target, _ = oracle.wait_for_any(
            ("tactical/book/cancel", "tactical/page/back"),
            15,
            minimum_generation=close_course.generation,
        )
        if next_target == "tactical/book/cancel":
            close_book = oracle.click("tactical/book/cancel")
            oracle.wait_for(
                "tactical/page/back", 15, minimum_generation=close_book.generation
            )
    if oracle.enabled("tactical/book/cancel"):
        close_book = oracle.click("tactical/book/cancel")
        oracle.wait_for(
            "tactical/page/back", 15, minimum_generation=close_book.generation
        )
    if oracle.enabled("tactical/dock/cancel"):
        close_dock = oracle.click("tactical/dock/cancel")
        oracle.wait_for(
            "tactical/page/back", 15, minimum_generation=close_dock.generation
        )
    if oracle.exists("tactical/page/back"):
        exit_tactical = oracle.click("tactical/page/back")
        oracle.wait_for(
            "reward/page/back", 15, minimum_generation=exit_tactical.generation
        )
        return
    if oracle.enabled("overlay/bulletin/close"):
        dismissal = oracle.click("overlay/bulletin/close")
        oracle.wait_for("main/more", 10, minimum_generation=dismissal.generation)
    if not oracle.main_page_visible():
        raise AssertionError("Tactical validation has no reviewed main entry page")
    entry = oracle.click("main/more")
    oracle.wait_for("reward/page/back", 15, minimum_generation=entry.generation)


def _tactical_snapshot(serial: str, driver_revision: str) -> Mapping[str, Any]:
    """Read Tactical slots and restore the ordinary main page."""

    from alas_headless.alas_adapter import AlasSemanticSession

    with AlasSemanticSession(serial=serial, driver_revision=driver_revision) as session:
        oracle = session.oracle
        actions: list[dict[str, Any]] = []
        _ensure_reward_page(oracle)
        finish_available = oracle.enabled("reward/tactical/finish")
        go_available = oracle.enabled("reward/tactical/go")
        if not go_available:
            raise AssertionError(
                "Tactical page is not enterable; completed courses still require claim"
            )
        entry = oracle.click("reward/tactical/go")
        actions.append(_receipt_value(entry))
        oracle.wait_for("tactical/page/back", 15, minimum_generation=entry.generation)
        slots = tuple(asdict(slot) for slot in oracle.tactical_slots())
        back = oracle.click("tactical/page/back")
        actions.append(_receipt_value(back))
        oracle.wait_for("reward/page/back", 15, minimum_generation=back.generation)
        exit_receipt = oracle.click("reward/page/back")
        actions.append(_receipt_value(exit_receipt))
        time.sleep(1)
        if not oracle.main_page_visible():
            raise AssertionError("Tactical snapshot cleanup did not restore main")
        return {
            "finish_available": finish_available,
            "go_available": go_available,
            "slots": slots,
            "actions": actions,
            "main_page_visible": True,
        }


def validate(
    *,
    alas_root: Path,
    seed_config: str,
    driver_revision: str,
    enabled: bool,
    favorite: bool,
    min_level: int,
    allow_tactical_rewards: bool,
    tactical_assign_budget: int,
    expect_assignment: bool,
) -> Mapping[str, Any]:
    if not 1 <= min_level <= 125:
        raise ValueError("min_level must be in 1..125")
    if tactical_assign_budget < 0:
        raise ValueError("tactical_assign_budget must be non-negative")
    if not isinstance(expect_assignment, bool):
        raise TypeError("expect_assignment must be boolean")
    seed_path = alas_root / "config" / (seed_config + ".json")
    seed = _read_json(seed_path)
    serial = seed["Alas"]["Emulator"]["Serial"]
    package = seed["Alas"]["Emulator"]["PackageName"]
    if not isinstance(serial, str) or not serial:
        raise AssertionError("seed config has no emulator serial")
    if not isinstance(package, str) or not package:
        raise AssertionError("seed config has no package")
    if not _adb(serial, "shell", "pidof", package):
        raise RuntimeError("game package is not running")

    payload = copy.deepcopy(seed)
    payload["Alas"]["Error"].update({"HandleError": False, "SaveError": False})
    payload["Tactical"]["Scheduler"]["Enable"] = False
    payload["Tactical"]["AddNewStudent"].update(
        {"Enable": enabled, "Favorite": favorite, "MinLevel": min_level}
    )
    config_name = "codex_tactical_student_live_" + uuid.uuid4().hex
    config_path = alas_root / "config" / (config_name + ".json")
    _write_json(config_path, payload)

    result: dict[str, Any] = {"passed": False, "temporary_config": config_path.name}
    instance: object | None = None
    adapter: Any | None = None
    dispatches: list[dict[str, Any]] = []
    reward_clicks: list[dict[str, Any]] = []
    favorite_calls: list[dict[str, Any]] = []
    selected_ships: list[dict[str, Any]] = []
    before: Mapping[str, Any] | None = None
    prior_environment = {
        name: os.environ.get(name)
        for name in (
            "ALAS_SEMANTIC_ALLOW_TACTICAL_REWARDS",
            "ALAS_SEMANTIC_TACTICAL_ASSIGN_BUDGET",
        )
    }
    try:
        if not enabled or not expect_assignment:
            before = _tactical_snapshot(serial, driver_revision)
        modules = _load_modules(
            alas_root,
            driver_revision,
            allow_tactical_rewards=allow_tactical_rewards,
            tactical_assign_budget=tactical_assign_budget,
        )
        instance = modules.AzurLaneAutoScript(config_name)
        instance.config.bind("Tactical")
        semantic_session = instance.device.semantic_adapter
        adapter = semantic_session.open()
        _ensure_reward_page(adapter.oracle)
        original_dispatch = adapter._dispatch_mutation
        original_click = semantic_session.click
        original_favorite = adapter.oracle.set_enhancement_dock_favourite
        original_ship = adapter.oracle.click_tactical_ship

        def record_dispatch(capability: str, operation: object) -> object:
            receipt = original_dispatch(capability, operation)
            dispatches.append(
                {"capability": capability, "receipt": _receipt_value(receipt)}
            )
            return receipt

        def record_click(button: object) -> object:
            receipt = original_click(button)
            name = getattr(button, "name", None)
            if name in ("REWARD_2", "REWARD_2_WHITE"):
                reward_clicks.append({"button": name, "receipt": _receipt_value(receipt)})
            return receipt

        def record_favorite(value: bool) -> object:
            receipt = original_favorite(value)
            favorite_calls.append(
                {
                    "enabled": value,
                    "receipt": _receipt_value(receipt),
                    "candidates_after": [
                        asdict(candidate)
                        for candidate in adapter.oracle.tactical_candidate_ships()
                    ],
                }
            )
            return receipt

        def record_ship(ship_id: int) -> object:
            receipt = original_ship(ship_id)
            selected_ships.append(
                {"ship_id": ship_id, "receipt": _receipt_value(receipt)}
            )
            return receipt

        adapter._dispatch_mutation = record_dispatch
        semantic_session.click = record_click
        adapter.oracle.set_enhancement_dock_favourite = record_favorite
        adapter.oracle.click_tactical_ship = record_ship
        instance.device.screenshot()
        started = time.monotonic()
        instance.tactical()
        result["elapsed_seconds"] = round(time.monotonic() - started, 3)
        result["tactical_assign_grant_remaining"] = adapter._action_ledger.remaining(
            "tactical.assign"
        )
        if enabled:
            expected_favourite_action = "enhancement/dock/favourite/" + (
                "on" if favorite else "off"
            )
            if len(favorite_calls) != 1 or any(
                item["enabled"] is not favorite for item in favorite_calls
            ):
                raise AssertionError("configured favourite value was not applied in Dock")
            if expect_assignment:
                if len(dispatches) != 1 or any(
                    item["capability"] != "tactical.assign" for item in dispatches
                ):
                    raise AssertionError(
                        "enabled Tactical task did not start a typed course"
                    )
                if any(
                    item["receipt"] is None
                    or item["receipt"]["semantic_id"] != expected_favourite_action
                    for item in favorite_calls
                ):
                    raise AssertionError(
                        "Dock favourite action did not use its exact live layer"
                    )
                if len(selected_ships) != 1:
                    raise AssertionError(
                        "enabled Tactical task did not select exactly one ship"
                    )
            else:
                if dispatches or selected_ships:
                    raise AssertionError(
                        "min-level no-candidate run unexpectedly assigned a course"
                    )
                candidates = favorite_calls[0]["candidates_after"]
                if any(candidate["level"] >= min_level for candidate in candidates):
                    raise AssertionError(
                        "min-level no-candidate run still exposed an eligible ship"
                    )
        else:
            if dispatches or favorite_calls:
                raise AssertionError("disabled Tactical task unexpectedly entered assignment")
        if allow_tactical_rewards:
            if len(reward_clicks) != 1:
                raise AssertionError("Tactical reward claim was not exactly once")
        elif reward_clicks:
            raise AssertionError("Tactical reward claim occurred without its opt-in")
        result["dispatches"] = dispatches
        result["reward_clicks"] = reward_clicks
        result["favorite_calls"] = favorite_calls
        result["selected_ships"] = selected_ships
        result["before"] = before
        semantic_session.close()
        instance.device.semantic_adapter = None
        result["after"] = _tactical_snapshot(serial, driver_revision)
        if enabled and expect_assignment and not result["after"]["slots"]:
            raise AssertionError("enabled Tactical task left no typed running course")
        if not enabled or not expect_assignment:
            assert before is not None
            before_slots = tuple(
                (slot["slot"], slot["ship_id"]) for slot in before["slots"]
            )
            after_slots = tuple(
                (slot["slot"], slot["ship_id"])
                for slot in result["after"]["slots"]
            )
            if after_slots != before_slots:
                raise AssertionError("no-assignment Tactical task changed course identities")
        result["passed"] = True
    except BaseException as exc:
        result["error"] = type(exc).__name__ + ": " + str(exc)
        result["traceback"] = traceback.format_exc()
    finally:
        result["dispatches"] = dispatches
        result["reward_clicks"] = reward_clicks
        result["favorite_calls"] = favorite_calls
        result["selected_ships"] = selected_ships
        result["before"] = before
        if adapter is not None:
            result["tactical_assign_grant_remaining"] = adapter._action_ledger.remaining(
                "tactical.assign"
            )
        _close(instance)
        config_path.unlink(missing_ok=True)
        result["temporary_config_removed"] = not config_path.exists()
        for name, previous in prior_environment.items():
            if previous is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = previous

    return {
        "schema": "alas-headless.tactical-new-student-live-validation/v1",
        "serial": serial,
        "package": package,
        "driver_revision": driver_revision,
        "seed_config": seed_config,
        "seed_config_sha256": _sha256(seed_path),
        "configured": {
            "AddNewStudent.Enable": enabled,
            "AddNewStudent.Favorite": favorite,
            "AddNewStudent.MinLevel": min_level,
        },
        "allow_tactical_rewards": allow_tactical_rewards,
        "tactical_assign_budget": tactical_assign_budget,
        "expect_assignment": expect_assignment,
        "source_sha256": {
            "tactical": _sha256(alas_root / "module" / "tactical" / "tactical_class.py"),
            "adapter": _sha256(ROOT / "python" / "alas_headless" / "alas_adapter.py"),
            "oracle": _sha256(ROOT / "python" / "alas_headless" / "semantic_oracle.py"),
            "validator": _sha256(Path(__file__).resolve()),
        },
        **result,
    }


def validate_resumed_postcondition(
    *,
    alas_root: Path,
    seed_config: str,
    driver_revision: str,
    enabled: bool,
    favorite: bool,
    min_level: int,
    allow_tactical_rewards: bool,
    tactical_assign_budget: int,
    prior_receipt_path: Path,
    expected_ship_id: int,
) -> Mapping[str, Any]:
    """Close a known post-confirmation observer gap without another mutation."""

    seed_path = alas_root / "config" / (seed_config + ".json")
    seed = _read_json(seed_path)
    serial = seed["Alas"]["Emulator"]["Serial"]
    package = seed["Alas"]["Emulator"]["PackageName"]
    result: dict[str, Any] = {"passed": False}
    try:
        if not isinstance(serial, str) or not serial:
            raise AssertionError("seed config has no emulator serial")
        if not isinstance(package, str) or not package:
            raise AssertionError("seed config has no package")
        if not _adb(serial, "shell", "pidof", package):
            raise RuntimeError("game package is not running")
        prior = _read_json(prior_receipt_path)
        expected_configuration = {
            "AddNewStudent.Enable": enabled,
            "AddNewStudent.Favorite": favorite,
            "AddNewStudent.MinLevel": min_level,
        }
        if prior.get("configured") != expected_configuration:
            raise AssertionError("prior receipt does not have the requested config")
        if prior.get("passed") is not False or prior.get("error") != (
            "SemanticGateClosed: tactical slot identity is ambiguous"
        ):
            raise AssertionError("prior receipt is not the reviewed observer gap")
        dispatches = prior.get("dispatches")
        favorite_calls = prior.get("favorite_calls")
        selected_ships = prior.get("selected_ships")
        expected_scope = "enhancement/dock/favourite/" + (
            "on" if favorite else "off"
        )
        if not (
            isinstance(dispatches, list)
            and len(dispatches) == 1
            and dispatches[0].get("capability") == "tactical.assign"
            and dispatches[0].get("receipt", {}).get("semantic_id")
            == "tactical/course/confirm"
        ):
            raise AssertionError("prior receipt lacks one typed course confirmation")
        if not (
            isinstance(favorite_calls, list)
            and len(favorite_calls) == 1
            and favorite_calls[0].get("enabled") is favorite
            and favorite_calls[0].get("receipt", {}).get("semantic_id")
            == expected_scope
        ):
            raise AssertionError("prior receipt lacks the configured Dock scope action")
        if not (
            isinstance(selected_ships, list)
            and len(selected_ships) == 1
            and selected_ships[0].get("ship_id") == expected_ship_id
            and selected_ships[0].get("receipt", {}).get("semantic_id")
            == "tactical/dock/ship/" + str(expected_ship_id)
        ):
            raise AssertionError("prior receipt lacks the expected selected ship")
        if prior.get("reward_clicks"):
            raise AssertionError("prior receipt unexpectedly claimed Tactical rewards")

        after = _tactical_snapshot(serial, driver_revision)
        expected_slots = [
            slot
            for slot in after["slots"]
            if slot["ship_id"] == expected_ship_id
            and slot["status"] == "running"
            and slot["remaining_seconds"] is not None
            and slot["remaining_seconds"] > 0
        ]
        if len(expected_slots) != 1:
            raise AssertionError("postcondition has no unique running selected ship")
        result.update(
            {
                "prior_receipt": prior_receipt_path.name,
                "prior_receipt_sha256": _sha256(prior_receipt_path),
                "prior_source_sha256": prior.get("source_sha256"),
                "prior_observer_gap": prior["error"],
                "after": after,
                "expected_running_slot": expected_slots[0],
                "passed": True,
            }
        )
    except BaseException as exc:
        result["error"] = type(exc).__name__ + ": " + str(exc)
        result["traceback"] = traceback.format_exc()

    return {
        "schema": "alas-headless.tactical-new-student-postcondition-validation/v1",
        "serial": serial,
        "package": package,
        "driver_revision": driver_revision,
        "seed_config": seed_config,
        "seed_config_sha256": _sha256(seed_path),
        "configured": {
            "AddNewStudent.Enable": enabled,
            "AddNewStudent.Favorite": favorite,
            "AddNewStudent.MinLevel": min_level,
        },
        "allow_tactical_rewards": allow_tactical_rewards,
        "tactical_assign_budget": tactical_assign_budget,
        "expected_ship_id": expected_ship_id,
        "source_sha256": {
            "tactical": _sha256(alas_root / "module" / "tactical" / "tactical_class.py"),
            "adapter": _sha256(ROOT / "python" / "alas_headless" / "alas_adapter.py"),
            "oracle": _sha256(ROOT / "python" / "alas_headless" / "semantic_oracle.py"),
            "validator": _sha256(Path(__file__).resolve()),
        },
        **result,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--alas-root", type=Path, required=True)
    parser.add_argument("--seed-config", default="semantic_e2e")
    parser.add_argument("--enabled", choices=("true", "false"), required=True)
    parser.add_argument("--favorite", choices=("true", "false"), required=True)
    parser.add_argument("--min-level", type=int, required=True)
    parser.add_argument(
        "--allow-tactical-rewards", choices=("true", "false"), required=True
    )
    parser.add_argument("--tactical-assign-budget", type=int, required=True)
    parser.add_argument(
        "--expect-assignment", choices=("true", "false"), default="true"
    )
    parser.add_argument("--driver-revision", required=True)
    parser.add_argument("--resume-from", type=Path)
    parser.add_argument("--expected-ship-id", type=int)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    output = arguments.output.resolve()
    common = {
        "alas_root": arguments.alas_root.resolve(),
        "seed_config": arguments.seed_config,
        "driver_revision": arguments.driver_revision,
        "enabled": arguments.enabled == "true",
        "favorite": arguments.favorite == "true",
        "min_level": arguments.min_level,
        "allow_tactical_rewards": arguments.allow_tactical_rewards == "true",
        "tactical_assign_budget": arguments.tactical_assign_budget,
    }
    if arguments.resume_from is None:
        result = validate(
            **common, expect_assignment=arguments.expect_assignment == "true"
        )
    else:
        if arguments.expected_ship_id is None:
            parser.error("--resume-from requires --expected-ship-id")
        result = validate_resumed_postcondition(
            **common,
            prior_receipt_path=arguments.resume_from.resolve(),
            expected_ship_id=arguments.expected_ship_id,
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    _write_json(output, result)
    print(json.dumps(result, ensure_ascii=False, indent=2), end="\n")
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
