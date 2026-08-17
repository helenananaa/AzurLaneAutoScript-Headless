#!/usr/bin/env python3
"""Run the original ALAS Reward resource-collection branch on one client."""

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
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "python") not in sys.path:
    sys.path.insert(0, str(ROOT / "python"))


RESOURCE_BUTTONS = {
    "Reward.CollectOil": "OIL",
    "Reward.CollectCoin": "COIN",
    "Reward.CollectExp": "EXP",
}
RESOURCE_TARGETS = {
    "Reward.CollectOil": "reward/resource/oil",
    "Reward.CollectCoin": "reward/resource/coin",
    "Reward.CollectExp": "reward/resource/exp",
}
RESOURCE_FIELDS = {
    "oil": "Reward.CollectOil",
    "coin": "Reward.CollectCoin",
    "exp": "Reward.CollectExp",
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
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


def _load_modules(alas_root: Path, driver_revision: str) -> SimpleNamespace:
    os.environ["ALAS_SEMANTIC_MODE"] = "1"
    os.environ["ALAS_SEMANTIC_DRIVER_REVISION"] = driver_revision
    os.environ["ALAS_SEMANTIC_ADB"] = "adb"
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


def _resource_state(oracle: object) -> dict[str, dict[str, Any]]:
    return {
        field: {
            "amount": oracle.reward_resource_amount(resource),
            "available": oracle.reward_resource_available(resource),
        }
        for resource, field in RESOURCE_FIELDS.items()
    }


def _ensure_reward_page(oracle: object) -> None:
    if oracle.exists("reward/page/back"):
        return
    if not oracle.main_page_visible():
        raise AssertionError("resource validation has no reviewed entry page")
    entry = oracle.click("main/more")
    oracle.wait_for("reward/page/back", 15, minimum_generation=entry.generation)


def _read_after_and_cleanup(serial: str) -> Mapping[str, Any]:
    """Read final reward flags and leave the client at the main page."""

    from alas_headless.alas_adapter import AlasSemanticSession

    with AlasSemanticSession.from_environment(serial=serial) as session:
        oracle = session.oracle
        if not oracle.main_page_visible():
            raise AssertionError("Reward resource run did not return to the main page")
        entry = oracle.click("main/more")
        oracle.wait_for("reward/page/back", 15, minimum_generation=entry.generation)
        states = _resource_state(oracle)
        back = oracle.click("reward/page/back")
        time.sleep(2)
        if not oracle.main_page_visible():
            raise AssertionError("Reward resource cleanup did not restore the main page")
        return {
            "resource_state": states,
            "entry": {
                "semantic_id": entry.semantic_id,
                "generation": entry.generation,
                "path": entry.path,
            },
            "cleanup": {
                "semantic_id": back.semantic_id,
                "generation": back.generation,
                "path": back.path,
            },
            "main_page_visible": True,
        }


def _receipt_value(receipt: object) -> dict[str, Any]:
    point = getattr(receipt, "point", None)
    return {
        "semantic_id": getattr(receipt, "semantic_id", None),
        "generation": getattr(receipt, "generation", None),
        "path": getattr(receipt, "path", None),
        "point": (
            {"x": point.x, "y": point.y}
            if point is not None
            else None
        ),
    }


def validate(
    *,
    alas_root: Path,
    seed_config: str,
    driver_revision: str,
    resources_enabled: bool,
    resource_names: tuple[str, ...],
) -> Mapping[str, Any]:
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
    selected_fields = {RESOURCE_FIELDS[name] for name in resource_names}
    payload["Reward"]["Reward"].update(
        {
            "CollectOil": resources_enabled and "Reward.CollectOil" in selected_fields,
            "CollectCoin": resources_enabled and "Reward.CollectCoin" in selected_fields,
            "CollectExp": resources_enabled and "Reward.CollectExp" in selected_fields,
            "CollectMission": False,
            "CollectWeeklyMission": False,
        }
    )
    config_name = "codex_reward_resource_live_" + uuid.uuid4().hex
    config_path = alas_root / "config" / (config_name + ".json")
    _write_json(config_path, payload)
    instance: object | None = None
    result: dict[str, Any] = {"temporary_config": config_path.name, "passed": False}
    try:
        modules = _load_modules(alas_root, driver_revision)
        instance = modules.AzurLaneAutoScript(config_name)
        instance.config.bind("Reward")
        semantic_session = instance.device.semantic_adapter
        adapter = semantic_session.open()
        _ensure_reward_page(adapter.oracle)
        result["resource_state_before"] = _resource_state(adapter.oracle)
        if resources_enabled and not all(
            result["resource_state_before"][field]["available"]
            for field in selected_fields
        ):
            raise AssertionError("not every configured resource reward has a positive amount")

        resource_dispatches: list[dict[str, Any]] = []
        original_click = semantic_session.click

        def record_click(button: object) -> object:
            receipt = original_click(button)
            name = getattr(button, "name", None)
            if name in RESOURCE_BUTTONS.values():
                resource_dispatches.append(
                    {"button": name, **_receipt_value(receipt)}
                )
            return receipt

        semantic_session.click = record_click
        started = time.monotonic()
        instance.reward()
        result["elapsed_seconds"] = round(time.monotonic() - started, 3)
        result["resource_dispatches"] = resource_dispatches
        expected_buttons = (
            {
                RESOURCE_BUTTONS[field]
                for field in selected_fields
            }
            if resources_enabled
            else set()
        )
        actual_buttons = [entry["button"] for entry in resource_dispatches]
        if len(actual_buttons) != len(expected_buttons) or set(actual_buttons) != expected_buttons:
            raise AssertionError("Reward resource run dispatched an unexpected input set")
        expected_pairs = (
            {
                (RESOURCE_BUTTONS[field], RESOURCE_TARGETS[field])
                for field in selected_fields
            }
            if resources_enabled
            else set()
        )
        actual_pairs = {
            (entry["button"], entry["semantic_id"])
            for entry in resource_dispatches
        }
        if len(actual_pairs) != len(resource_dispatches) or actual_pairs != expected_pairs:
            raise AssertionError("Reward resource run did not use exact typed targets")

        semantic_session.close()
        instance.device.semantic_adapter = None
        after = _read_after_and_cleanup(serial)
        result["resource_state_after"] = after["resource_state"]
        result["cleanup"] = {key: value for key, value in after.items() if key != "resource_state"}
        if resources_enabled and any(
            result["resource_state_after"][field]["available"]
            for field in selected_fields
        ):
            raise AssertionError("Reward resource amount remained positive after collection")
        result["passed"] = True
    except BaseException as exc:
        result["error"] = type(exc).__name__ + ": " + str(exc)
        result["traceback"] = traceback.format_exc()
    finally:
        _close(instance)
        config_path.unlink(missing_ok=True)
        result["temporary_config_removed"] = not config_path.exists()
    return {
        "schema": "alas-headless.reward-resource-live-validation/v1",
        "serial": serial,
        "package": package,
        "driver_revision": driver_revision,
        "seed_config": seed_config,
        "seed_config_sha256": _sha256(seed_path),
        "configured": {
            field: resources_enabled and field in selected_fields
            for field in RESOURCE_TARGETS
        }
        | {
            "Reward.CollectMission": False,
            "Reward.CollectWeeklyMission": False,
        },
        "source_sha256": {
            "reward": _sha256(alas_root / "module" / "reward" / "reward.py"),
            "adapter": _sha256(ROOT / "python" / "alas_headless" / "alas_adapter.py"),
            "oracle": _sha256(ROOT / "python" / "alas_headless" / "semantic_oracle.py"),
            "native_probe": _sha256(
                ROOT
                / "overlays"
                / "angle-g3"
                / "src"
                / "libANGLE"
                / "renderer"
                / "null"
                / "Il2CppNamespaceProbe.cpp"
            ),
            "validator": _sha256(Path(__file__).resolve()),
        },
        **result,
    }


def audit_attempt(*, attempt_path: Path, driver_revision: str) -> Mapping[str, Any]:
    """Prove the final state after one already-recorded consumptive run."""

    os.environ["ALAS_SEMANTIC_MODE"] = "1"
    os.environ["ALAS_SEMANTIC_DRIVER_REVISION"] = driver_revision
    os.environ["ALAS_SEMANTIC_ADB"] = "adb"
    attempt = _read_json(attempt_path)
    configured = attempt.get("configured")
    expected_configured = {
        field: True for field in RESOURCE_TARGETS
    } | {
        "Reward.CollectMission": False,
        "Reward.CollectWeeklyMission": False,
    }
    if configured != expected_configured:
        raise AssertionError("recorded resource attempt used the wrong configuration")
    dispatches = attempt.get("resource_dispatches")
    if not isinstance(dispatches, list):
        raise AssertionError("recorded resource attempt has no dispatch list")
    expected_pairs = {
        (RESOURCE_BUTTONS[field], RESOURCE_TARGETS[field])
        for field in RESOURCE_TARGETS
    }
    actual_pairs = {
        (entry.get("button"), entry.get("semantic_id"))
        for entry in dispatches
        if isinstance(entry, dict)
    }
    if len(dispatches) != len(expected_pairs) or actual_pairs != expected_pairs:
        raise AssertionError("recorded resource attempt did not cover all typed inputs")
    serial = attempt.get("serial")
    package = attempt.get("package")
    if not isinstance(serial, str) or not serial:
        raise AssertionError("recorded resource attempt has no serial")
    if not isinstance(package, str) or not package:
        raise AssertionError("recorded resource attempt has no package")
    if not _adb(serial, "shell", "pidof", package):
        raise RuntimeError("game package is not running for postcondition audit")
    after = _read_after_and_cleanup(serial)
    state = after["resource_state"]
    if any(value["available"] for value in state.values()):
        raise AssertionError("a collected resource amount remains positive")
    return {
        "schema": "alas-headless.reward-resource-live-postcondition-audit/v1",
        "serial": serial,
        "package": package,
        "driver_revision": driver_revision,
        "execution_attempt": attempt_path.name,
        "execution_source_sha256": attempt.get("source_sha256"),
        "execution_elapsed_seconds": attempt.get("elapsed_seconds"),
        "execution_dispatches": dispatches,
        "execution_harness_error": attempt.get("error"),
        "resource_state_after": state,
        "cleanup": {
            key: value for key, value in after.items() if key != "resource_state"
        },
        "auditor_sha256": _sha256(Path(__file__).resolve()),
        "passed": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--alas-root", type=Path, required=True)
    parser.add_argument("--seed-config", default="semantic_e2e")
    parser.add_argument(
        "--resources-enabled",
        choices=("true", "false"),
        default="true",
    )
    parser.add_argument(
        "--resource-names",
        default="oil,coin,exp",
        help="comma-separated subset of oil,coin,exp to enable when requested",
    )
    parser.add_argument("--driver-revision", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--audit-attempt",
        type=Path,
        help="audit the postcondition of an already-recorded consumptive attempt",
    )
    arguments = parser.parse_args()
    output = arguments.output.resolve()
    resource_names = tuple(
        name.strip() for name in arguments.resource_names.split(",") if name.strip()
    )
    if not resource_names or set(resource_names) - set(RESOURCE_FIELDS):
        parser.error("--resource-names must be a non-empty subset of oil,coin,exp")
    if len(set(resource_names)) != len(resource_names):
        parser.error("--resource-names must not contain duplicates")
    if arguments.audit_attempt is not None:
        result = audit_attempt(
            attempt_path=arguments.audit_attempt.resolve(),
            driver_revision=arguments.driver_revision,
        )
    else:
        result = validate(
            alas_root=arguments.alas_root.resolve(),
            seed_config=arguments.seed_config,
            driver_revision=arguments.driver_revision,
            resources_enabled=arguments.resources_enabled == "true",
            resource_names=resource_names,
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    _write_json(output, result)
    print(json.dumps(result, ensure_ascii=False, indent=2), end="\n")
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
