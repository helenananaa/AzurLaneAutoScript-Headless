#!/usr/bin/env python3
"""Run one bounded original-ALAS cognitive-awakening transaction live."""

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
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "python") not in sys.path:
    sys.path.insert(0, str(ROOT / "python"))


from alas_headless.semantic_sources import semantic_source_hashes


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
    return subprocess.run(
        ("adb", "-s", serial, *arguments),
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=90,
    ).stdout.strip()


def _close(instance: object | None) -> None:
    if instance is None:
        return
    device = getattr(instance, "__dict__", {}).get("device")
    session = getattr(device, "__dict__", {}).get("semantic_adapter")
    if session is not None:
        session.close()


def validate(
    *,
    alas_root: Path,
    seed_config: str,
    driver_revision: str,
    level_cap: str,
    favourite: bool,
    expect: str,
) -> Mapping[str, Any]:
    seed_path = alas_root / "config" / (seed_config + ".json")
    seed = _read_json(seed_path)
    serial = seed["Alas"]["Emulator"]["Serial"]
    package = seed["Alas"]["Emulator"]["PackageName"]
    if not _adb(serial, "shell", "pidof", package):
        raise RuntimeError("game package is not running")

    payload = copy.deepcopy(seed)
    payload["Alas"]["Error"].update({"HandleError": False, "SaveError": False})
    payload["Awaken"]["Scheduler"]["Enable"] = False
    payload["Awaken"]["Awaken"].update(
        {"LevelCap": level_cap, "Favourite": favourite}
    )
    config_name = "codex_awaken_live_" + uuid.uuid4().hex
    config_path = alas_root / "config" / (config_name + ".json")
    _write_json(config_path, payload)

    prior_budget = os.environ.get("ALAS_SEMANTIC_AWAKEN_BUDGET")
    result: dict[str, Any] = {"passed": False}
    instance: object | None = None
    adapter: Any = None
    try:
        os.environ.update(
            {
                "ALAS_SEMANTIC_MODE": "1",
                "ALAS_SEMANTIC_DRIVER_REVISION": driver_revision,
                "ALAS_SEMANTIC_ADB": "adb",
                "ALAS_SEMANTIC_AWAKEN_BUDGET": "1",
            }
        )
        for path in (ROOT / "python", alas_root):
            value = str(path)
            if value not in sys.path:
                sys.path.insert(0, value)
        os.chdir(alas_root)
        from alas import AzurLaneAutoScript
        from module.config.config import name_to_function

        instance = AzurLaneAutoScript(config_name)
        instance.config.bind("Awaken")
        instance.config.task = name_to_function("Awaken")
        adapter = instance.device.semantic_adapter.open()
        started = time.monotonic()
        # Dock can legitimately exceed the generic full-frame toggle cap.
        # Awaken immediately performs its own exact, bounded observations.
        result["task_result"] = instance.run(
            "awaken", skip_first_screenshot=True
        )
        result["elapsed_seconds"] = round(time.monotonic() - started, 3)
        receipts = adapter.awaken_receipts()
        observations = adapter.awaken_cost_observations()
        result["execution_receipts"] = [asdict(item) for item in receipts]
        result["cost_observations"] = [asdict(item) for item in observations]
        result["awaken_grant_remaining"] = adapter._action_ledger.remaining(
            "awaken.execute"
        )
        if result["task_result"] is not True:
            raise AssertionError("original ALAS Awaken task did not return success")
        if expect == "transaction":
            if len(receipts) != 1:
                raise AssertionError("Awaken task did not produce exactly one transaction")
            receipt = receipts[0]
            transition = (receipt.current_level, receipt.target_level)
            if level_cap == "level120":
                transition_allowed = transition == (115, 120)
            else:
                transition_allowed = (
                    transition == (120, 125)
                    or (
                        receipt.target_level <= 120
                        and receipt.target_level == receipt.current_level + 5
                    )
                )
            if not transition_allowed:
                raise AssertionError("Awaken task used the wrong level transition")
            if receipt.cost.use_array != (receipt.target_level == 125):
                raise AssertionError("Awaken task used the wrong resource mode")
            if receipt.capability_id != "awaken.execute" or not receipt.policy_sha256:
                raise AssertionError("Awaken receipt lacks action authority")
            if result["awaken_grant_remaining"] != 0:
                raise AssertionError("Awaken task did not exhaust its single-use grant")
        elif expect == "insufficient":
            if receipts or len(observations) != 1 or observations[0].sufficient:
                raise AssertionError("Awaken task did not prove one insufficient modal")
            if result["awaken_grant_remaining"] != 1:
                raise AssertionError("insufficient Awaken task consumed its grant")
        else:
            if receipts or observations:
                raise AssertionError("Awaken task did not prove an empty candidate set")
            if result["awaken_grant_remaining"] != 1:
                raise AssertionError("empty Awaken task consumed its grant")
        cleanup = adapter.oracle.return_from_awaken_dock_to_main()
        result["cleanup"] = {
            "semantic_id": cleanup.semantic_id,
            "generation": cleanup.generation,
            "main_page_visible": adapter.oracle.main_page_visible(),
        }
        if not result["cleanup"]["main_page_visible"]:
            raise AssertionError("Awaken cleanup did not restore main page")
        result["passed"] = True
    except BaseException as exc:
        result["error"] = type(exc).__name__ + ": " + str(exc)
        result["traceback"] = traceback.format_exc()
    finally:
        if adapter is not None:
            receipts = adapter.awaken_receipts()
            if receipts:
                result["execution_receipts"] = [asdict(item) for item in receipts]
            result["awaken_grant_remaining"] = adapter._action_ledger.remaining(
                "awaken.execute"
            )
            if not result["passed"]:
                cleanup_actions: list[str] = []
                try:
                    try:
                        adapter.oracle._enhancement_dock_records()
                    except Exception:
                        back = adapter.oracle.return_from_awaken_detail_to_dock()
                        cleanup_actions.append(back.semantic_id)
                    reset = adapter.oracle.reset_enhancement_dock()
                    cleanup_actions.extend(item.semantic_id for item in reset)
                    back = adapter.oracle.return_from_awaken_dock_to_main()
                    cleanup_actions.append(back.semantic_id)
                    result["failure_cleanup"] = {
                        "actions": cleanup_actions,
                        "main_page_visible": adapter.oracle.main_page_visible(),
                    }
                except Exception as cleanup_exc:
                    result["failure_cleanup_error"] = (
                        type(cleanup_exc).__name__ + ": " + str(cleanup_exc)
                    )
        _close(instance)
        config_path.unlink(missing_ok=True)
        result["temporary_config_removed"] = not config_path.exists()
        if prior_budget is None:
            os.environ.pop("ALAS_SEMANTIC_AWAKEN_BUDGET", None)
        else:
            os.environ["ALAS_SEMANTIC_AWAKEN_BUDGET"] = prior_budget

    return {
        "schema": "alas-headless.awaken-live-validation/v1",
        "serial": serial,
        "package": package,
        "driver_revision": driver_revision,
        "seed_config": seed_config,
        "seed_config_sha256": _sha256(seed_path),
        "configured": {
            "Awaken.LevelCap": level_cap,
            "Awaken.Favourite": favourite,
        },
        "expected_outcome": expect,
        "source_sha256": {
            **semantic_source_hashes(ROOT),
            "awaken": _sha256(alas_root / "module" / "awaken" / "awaken.py"),
            "adapter": _sha256(ROOT / "python" / "alas_headless" / "alas_adapter.py"),
            "oracle": _sha256(ROOT / "python" / "alas_headless" / "semantic_oracle.py"),
            "runner": _sha256(Path(__file__).resolve()),
        },
        **result,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--alas-root", type=Path, required=True)
    parser.add_argument("--seed-config", default="semantic_e2e")
    parser.add_argument("--driver-revision", required=True)
    parser.add_argument("--level-cap", choices=("level120", "level125"), required=True)
    parser.add_argument("--favourite", choices=("true", "false"), required=True)
    parser.add_argument(
        "--expect",
        choices=("transaction", "insufficient", "no-candidate"),
        default="transaction",
    )
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    output = arguments.output.resolve()
    result = validate(
        alas_root=arguments.alas_root.resolve(),
        seed_config=arguments.seed_config,
        driver_revision=arguments.driver_revision,
        level_cap=arguments.level_cap,
        favourite=arguments.favourite == "true",
        expect=arguments.expect,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    _write_json(output, result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
