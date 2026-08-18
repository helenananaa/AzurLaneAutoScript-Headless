#!/usr/bin/env python3
"""Prove one configured Tactical book filter through the original live task."""

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
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "python") not in sys.path:
    sys.path.insert(0, str(ROOT / "python"))

from scripts.python.run_alas_tactical_new_student_live_validation import (
    _close,
    _ensure_reward_page,
    _load_modules,
    _receipt_value,
    _read_json,
    _tactical_snapshot,
    _write_json,
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


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


def _book_value(book: object) -> Mapping[str, Any]:
    return {
        "position": getattr(book, "semantic_position", None),
        "book": str(book),
        "tier": getattr(book, "tier", None),
        "exp_value": getattr(book, "exp_value", None),
    }


def validate(
    *,
    alas_root: Path,
    seed_config: str,
    driver_revision: str,
    tactical_filter: str,
    overflow_enabled: bool | None = None,
    overflow_limits: tuple[int, int, int, int] | None = None,
    min_level: int = 1,
) -> Mapping[str, Any]:
    if not isinstance(tactical_filter, str) or not tactical_filter.strip():
        raise ValueError("tactical_filter must be a non-empty string")
    if not 1 <= min_level <= 125:
        raise ValueError("min_level must be in 1..125")
    if (overflow_enabled is None) != (overflow_limits is None):
        raise ValueError("overflow enabled and limits must be configured together")
    if overflow_limits is not None and any(
        not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= 5800
        for value in overflow_limits
    ):
        raise ValueError("overflow limits must be exact integers in 0..5800")
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
    payload["Tactical"]["Tactical"]["TacticalFilter"] = tactical_filter
    if overflow_limits is not None:
        payload["Tactical"]["ControlExpOverflow"].update(
            {
                "Enable": overflow_enabled,
                "T1Allow": overflow_limits[0],
                "T2Allow": overflow_limits[1],
                "T3Allow": overflow_limits[2],
                "T4Allow": overflow_limits[3],
            }
        )
    # The filter is exercised only through an original book-selection task.
    # One free course slot was preflighted immediately before this qualifier.
    payload["Tactical"]["AddNewStudent"].update(
        {"Enable": True, "Favorite": False, "MinLevel": min_level}
    )
    config_name = "codex_tactical_filter_live_" + uuid.uuid4().hex
    config_path = alas_root / "config" / (config_name + ".json")
    _write_json(config_path, payload)

    result: dict[str, Any] = {
        "passed": False,
        "temporary_config": config_path.name,
        "filter_loads": [],
        "filter_applications": [],
        "overflow_filter_applications": [],
        "book_selection_calls": [],
        "dispatches": [],
    }
    instance: object | None = None
    adapter: Any | None = None
    semantic_session: Any | None = None
    tactical_module: Any | None = None
    original_load: Any | None = None
    original_apply: Any | None = None
    original_select_book: Any | None = None
    original_dispatch: Any | None = None
    original_overflow_filter: Any | None = None
    prior_environment = {
        name: os.environ.get(name)
        for name in (
            "ALAS_SEMANTIC_ALLOW_TACTICAL_REWARDS",
            "ALAS_SEMANTIC_TACTICAL_ASSIGN_BUDGET",
        )
    }
    try:
        result["before"] = _tactical_snapshot(serial, driver_revision)
        empty_before = [
            slot
            for slot in result["before"]["slots"]
            if slot["status"] == "empty"
        ]
        if not empty_before and len(result["before"]["slots"]) >= 4:
            raise AssertionError("Tactical filter qualifier requires an empty course slot")

        modules = _load_modules(
            alas_root,
            driver_revision,
            allow_tactical_rewards=False,
            tactical_assign_budget=1,
        )
        instance = modules.AzurLaneAutoScript(config_name)
        instance.config.bind("Tactical")
        semantic_session = instance.device.semantic_adapter
        adapter = semantic_session.open()
        _ensure_reward_page(adapter.oracle)

        import module.tactical.tactical_class as tactical_module

        book_filter = tactical_module.BOOK_FILTER
        original_load = book_filter.load
        original_apply = book_filter.apply
        original_select_book = semantic_session.tactical_select_book
        original_dispatch = adapter._dispatch_mutation
        original_overflow_filter = tactical_module.RewardTacticalClass._tactical_books_filter_exp

        def record_load(value: str) -> object:
            result["filter_loads"].append(value)
            return original_load(value)

        def record_apply(books: object) -> object:
            applied = original_apply(books)
            selected = [_book_value(book) for book in applied]
            result["filter_applications"].append(
                {
                    "input": [_book_value(book) for book in books],
                    "selected": selected,
                }
            )
            return applied

        def record_select_book(position: int) -> object:
            before = [asdict(book) for book in adapter.tactical_books()]
            receipt = original_select_book(position)
            result["book_selection_calls"].append(
                {
                    "position": position,
                    "before": before,
                    "receipt": _receipt_value(receipt),
                }
            )
            return receipt

        def record_dispatch(capability: str, operation: object) -> object:
            receipt = original_dispatch(capability, operation)
            result["dispatches"].append(
                {"capability": capability, "receipt": _receipt_value(receipt)}
            )
            return receipt

        def record_overflow_filter(host: object) -> object:
            before = [_book_value(book) for book in host.books]
            progress = adapter.oracle.tactical_book_skill_progress()
            selected_before = [
                book.position for book in adapter.tactical_books() if book.selected
            ]
            value = original_overflow_filter(host)
            result["overflow_filter_applications"].append(
                {
                    "progress": progress,
                    "before": before,
                    "after": [_book_value(book) for book in host.books],
                    "selected_before": selected_before,
                }
            )
            return value

        book_filter.load = record_load
        book_filter.apply = record_apply
        semantic_session.tactical_select_book = record_select_book
        adapter._dispatch_mutation = record_dispatch
        tactical_module.RewardTacticalClass._tactical_books_filter_exp = record_overflow_filter

        instance.device.screenshot()
        started = time.monotonic()
        instance.tactical()
        result["elapsed_seconds"] = round(time.monotonic() - started, 3)
        result["tactical_assign_grant_remaining"] = adapter._action_ledger.remaining(
            "tactical.assign"
        )

        if result["filter_loads"] != [tactical_filter]:
            raise AssertionError("original Tactical task did not load the exact filter")
        if len(result["filter_applications"]) != 1:
            raise AssertionError("original Tactical task did not apply its book filter")
        selected = result["filter_applications"][0]["selected"]
        if not selected:
            raise AssertionError("configured filter selected no typed tactical book")
        expected_position = selected[0]["position"]
        if expected_position is None and selected[0]["book"] == "first":
            inputs = result["filter_applications"][0]["input"]
            if not inputs:
                raise AssertionError("first preset has no filtered tactical book")
            expected_position = inputs[0]["position"]
        if expected_position is None:
            raise AssertionError("configured filter selected no typed tactical book")
        selected_positions = [
            call["position"] for call in result["book_selection_calls"]
        ]
        already_selected = any(
            expected_position in application.get("selected_before", [])
            for application in result["overflow_filter_applications"]
        )
        if expected_position not in selected_positions and not already_selected:
            raise AssertionError("original task did not select its filtered book")
        if len(result["dispatches"]) != 1 or result["dispatches"][0][
            "capability"
        ] != "tactical.assign":
            raise AssertionError("original Tactical task did not confirm one course")
        if result["dispatches"][0]["receipt"] is None or result["dispatches"][0][
            "receipt"
        ]["semantic_id"] != "tactical/course/confirm":
            raise AssertionError("Tactical course confirmation was not semantic")
        if result["tactical_assign_grant_remaining"] != 0:
            raise AssertionError("Tactical task did not consume its one assignment grant")
        if overflow_limits is not None:
            applications = result["overflow_filter_applications"]
            if len(applications) != 1 or not applications[0]["progress"].endswith(
                "/5800"
            ):
                raise AssertionError(
                    "overflow qualifier did not exercise one level-9 skill"
                )

        semantic_session.close()
        instance.device.semantic_adapter = None
        result["after"] = _tactical_snapshot(serial, driver_revision)
        running_after = [
            slot for slot in result["after"]["slots"] if slot["status"] == "running"
        ]
        if len(running_after) <= len(result["before"]["slots"]):
            raise AssertionError("confirmed Tactical course has no new running slot")
        result["filtered_book_position"] = expected_position
        result["passed"] = True
    except BaseException as exc:
        result["error"] = type(exc).__name__ + ": " + str(exc)
        result["traceback"] = traceback.format_exc()
    finally:
        if tactical_module is not None:
            if original_load is not None:
                tactical_module.BOOK_FILTER.load = original_load
            if original_apply is not None:
                tactical_module.BOOK_FILTER.apply = original_apply
            if original_overflow_filter is not None:
                tactical_module.RewardTacticalClass._tactical_books_filter_exp = (
                    original_overflow_filter
                )
        if semantic_session is not None and original_select_book is not None:
            semantic_session.tactical_select_book = original_select_book
        if adapter is not None and original_dispatch is not None:
            adapter._dispatch_mutation = original_dispatch
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
        "schema": "alas-headless.tactical-filter-live-validation/v1",
        "serial": serial,
        "package": package,
        "driver_revision": driver_revision,
        "seed_config": seed_config,
        "seed_config_sha256": _sha256(seed_path),
        "configured": {
            "Tactical.TacticalFilter": tactical_filter,
            "AddNewStudent.Enable": True,
            "AddNewStudent.Favorite": False,
            "AddNewStudent.MinLevel": min_level,
            "ControlExpOverflow.Enable": overflow_enabled,
            "ControlExpOverflow.T1Allow": None if overflow_limits is None else overflow_limits[0],
            "ControlExpOverflow.T2Allow": None if overflow_limits is None else overflow_limits[1],
            "ControlExpOverflow.T3Allow": None if overflow_limits is None else overflow_limits[2],
            "ControlExpOverflow.T4Allow": None if overflow_limits is None else overflow_limits[3],
        },
        "source_sha256": {
            "tactical": _sha256(alas_root / "module" / "tactical" / "tactical_class.py"),
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
    parser.add_argument("--filter", required=True)
    parser.add_argument("--min-level", type=int, default=1)
    parser.add_argument("--overflow-enabled", choices=("true", "false"))
    parser.add_argument("--t1-allow", type=int)
    parser.add_argument("--t2-allow", type=int)
    parser.add_argument("--t3-allow", type=int)
    parser.add_argument("--t4-allow", type=int)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    overflow_values = (
        arguments.t1_allow,
        arguments.t2_allow,
        arguments.t3_allow,
        arguments.t4_allow,
    )
    overflow_limits = None
    if arguments.overflow_enabled is not None or any(
        value is not None for value in overflow_values
    ):
        if arguments.overflow_enabled is None or any(
            value is None for value in overflow_values
        ):
            parser.error("overflow mode requires --overflow-enabled and all four limits")
        overflow_limits = overflow_values
    output = arguments.output.resolve()
    result = validate(
        alas_root=arguments.alas_root.resolve(),
        seed_config=arguments.seed_config,
        driver_revision=arguments.driver_revision,
        tactical_filter=arguments.filter,
        overflow_enabled=(
            None
            if arguments.overflow_enabled is None
            else arguments.overflow_enabled == "true"
        ),
        overflow_limits=overflow_limits,
        min_level=arguments.min_level,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    _write_json(output, result)
    print(json.dumps(result, ensure_ascii=False, indent=2), end="\n")
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
