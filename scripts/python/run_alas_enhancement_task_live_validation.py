#!/usr/bin/env python3
"""Run the original ALAS enhancement task once against a live CN client.

This qualifier intentionally invokes ``Enhancement.enhance_ships`` rather than
calling the headless adapter directly.  It grants the configured number of
semantic transactions, records ALAS's forwarded detailed configuration, and
requires every official recommendation plus confirmation to consume ships.
"""

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
from dataclasses import asdict, is_dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Mapping, Optional


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
    enhancement_budget: int,
) -> SimpleNamespace:
    os.environ["ALAS_SEMANTIC_MODE"] = "1"
    os.environ["ALAS_SEMANTIC_DRIVER_REVISION"] = driver_revision
    os.environ["ALAS_SEMANTIC_ADB"] = "adb"
    os.environ["ALAS_SEMANTIC_ENHANCEMENT_BUDGET"] = str(enhancement_budget)
    for path in (ROOT / "python", alas_root):
        value = str(path)
        if value not in sys.path:
            sys.path.insert(0, value)
    os.chdir(alas_root)
    from alas import AzurLaneAutoScript
    from module.retire.enhancement import Enhancement

    return SimpleNamespace(
        AzurLaneAutoScript=AzurLaneAutoScript,
        Enhancement=Enhancement,
    )


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


def _value(value: object) -> object:
    """Serialize typed receipt state without discarding its proof fields."""

    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, tuple):
        return [_value(item) for item in value]
    if isinstance(value, list):
        return [_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _value(item) for key, item in value.items()}
    return value


def _ensure_enhancement_dock(adapter: Any) -> dict[str, Any]:
    """Enter the only reviewed starting page for ``Enhancement.enhance_ships``."""

    oracle = adapter.oracle
    try:
        candidates = oracle.enhancement_dock_candidates()
    except Exception:
        candidates = ()
    if candidates:
        return {
            "already_in_dock": True,
            "entry": None,
            "candidate_count": len(candidates),
        }
    try:
        # A normal, unfiltered Dock can contain several copies of the same
        # ship template at different levels.  That is a valid Dock identity
        # but deliberately not a safe candidate list; the task's explicit DD
        # filter below resolves it before any ship input.
        oracle._enhancement_dock_records()
    except Exception:
        pass
    else:
        return {
            "already_in_dock": True,
            "entry": None,
            "candidate_count": None,
        }
    if not oracle.main_page_visible():
        raise AssertionError("Enhancement qualifier is neither on Dock nor main")
    entry = oracle.click("main/dock")
    deadline = time.monotonic() + 15.0
    while time.monotonic() < deadline:
        try:
            candidates = oracle.enhancement_dock_candidates()
        except Exception:
            candidates = ()
        if candidates:
            return {
                "already_in_dock": False,
                "entry": _receipt_value(entry),
                "candidate_count": len(candidates),
            }
        time.sleep(0.1)
    raise AssertionError("semantic main/dock entry did not expose Dock cards")


def _execution_value(receipt: object) -> dict[str, Any]:
    value = _value(receipt)
    if not isinstance(value, dict):
        raise TypeError("enhancement receipt is not a typed dataclass")
    value["receipt_type"] = type(receipt).__name__
    consumed_count = getattr(receipt, "consumed_count", None)
    if consumed_count is not None:
        value["consumed_count"] = consumed_count
    return value


def validate(
    *,
    alas_root: Path,
    seed_config: str,
    driver_revision: str,
    ship_to_enhance: str,
    filter_expression: Optional[str],
    check_per_category: int,
    favourite_target_id: Optional[int],
) -> Mapping[str, Any]:
    if ship_to_enhance not in ("all", "favourite"):
        raise ValueError("ship_to_enhance must be all or favourite")
    if not isinstance(filter_expression, str) or not filter_expression.strip():
        raise ValueError("live qualifier requires one explicit supported filter")
    if check_per_category < 1:
        raise ValueError("check_per_category must be positive")
    if favourite_target_id is not None and favourite_target_id <= 0:
        raise ValueError("favourite_target_id must be positive when provided")
    if ship_to_enhance == "favourite" and favourite_target_id is None:
        raise ValueError(
            "favourite live qualification requires one explicit reversible target"
        )

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
    payload["General"]["Retirement"]["RetireMode"] = "enhance"
    configured = {
        "ShipToEnhance": ship_to_enhance,
        "Filter": filter_expression,
        "CheckPerCategory": check_per_category,
    }
    payload["General"]["Enhance"].update(configured)
    config_name = "codex_enhancement_live_" + uuid.uuid4().hex
    config_path = alas_root / "config" / (config_name + ".json")
    _write_json(config_path, payload)

    result: dict[str, Any] = {
        "passed": False,
        "temporary_config": config_path.name,
        "forwarded": [],
        "dispatches": [],
        "dock_scopes": [],
        "dock_filters": [],
        "favourite_bootstrap": None,
        "favourite_bootstrap_filter": None,
        "favourite_cleanup": None,
    }
    instance: object | None = None
    adapter: Any | None = None
    original_adapter_enhance: Any | None = None
    original_dispatch: Any | None = None
    original_scope: Any | None = None
    original_filter: Any | None = None
    favourite_target: Any | None = None
    favourite_bootstrapped = False
    prior_budget = os.environ.get("ALAS_SEMANTIC_ENHANCEMENT_BUDGET")
    try:
        modules = _load_modules(
            alas_root,
            driver_revision,
            enhancement_budget=check_per_category,
        )
        instance = modules.AzurLaneAutoScript(config_name)
        instance.config.bind("General")
        # Creating the device binds the same context-local session that the
        # upstream method consults.  Screenshot is deliberately avoided here:
        # the original enhancement port must not need a legacy framebuffer.
        semantic_session = instance.device.semantic_adapter
        adapter = semantic_session.open()
        result["dock_entry"] = _ensure_enhancement_dock(adapter)
        if favourite_target_id is not None:
            bootstrap_filter = adapter.oracle.set_enhancement_dock_filter(
                filter_expression
            )
            result["favourite_bootstrap_filter"] = {
                "ship_type": filter_expression,
                "receipts": [_receipt_value(item) for item in bootstrap_filter],
                "candidates_after": [
                    _value(candidate)
                    for candidate in adapter.oracle.enhancement_dock_candidates()
                ],
            }
            candidates = adapter.oracle.enhancement_dock_candidates()
            matches = [
                candidate
                for candidate in candidates
                if candidate.ship_id == favourite_target_id
            ]
            if len(matches) != 1:
                raise AssertionError(
                    "favourite bootstrap target is absent or ambiguous in Dock"
                )
            favourite_target = matches[0]
            bootstrap = adapter.oracle.set_enhancement_dock_candidate_favourite(
                favourite_target.position,
                favourite_target.ship_id,
                favourite_target.ship_name,
                favourite_target.level,
                True,
            )
            if "enhancement/detail/favourite/on" not in {
                receipt.semantic_id for receipt in bootstrap
            }:
                raise AssertionError(
                    "favourite bootstrap target was already marked common"
                )
            favourite_bootstrapped = True
            result["favourite_bootstrap"] = {
                "target": _value(favourite_target),
                "receipts": [_receipt_value(item) for item in bootstrap],
            }

        original_adapter_enhance = semantic_session.enhance_ships
        original_dispatch = adapter._dispatch_mutation
        original_scope = adapter.oracle.set_enhancement_dock_favourite
        original_filter = adapter.oracle.set_enhancement_dock_filter

        def record_adapter_enhance(
            ship_to_enhance: str,
            check_per_category: int,
            filter_expression: Optional[str],
        ) -> int:
            result["forwarded"].append(
                {
                    "ship_to_enhance": ship_to_enhance,
                    "check_per_category": check_per_category,
                    "filter_expression": filter_expression,
                }
            )
            return original_adapter_enhance(
                ship_to_enhance,
                check_per_category,
                filter_expression,
            )

        def record_dispatch(capability: str, operation: object) -> object:
            receipt = original_dispatch(capability, operation)
            result["dispatches"].append(
                {
                    "capability": capability,
                    "receipt": _execution_value(receipt),
                }
            )
            return receipt

        def record_scope(enabled: bool) -> object:
            receipt = original_scope(enabled)
            result["dock_scopes"].append(
                {"enabled": enabled, "receipt": _receipt_value(receipt)}
            )
            return receipt

        def record_filter(ship_type: Optional[str]) -> object:
            receipts = original_filter(ship_type)
            result["dock_filters"].append(
                {
                    "ship_type": ship_type,
                    "receipts": [_receipt_value(item) for item in receipts],
                    "candidates_after": [
                        _value(candidate)
                        for candidate in adapter.oracle.enhancement_dock_candidates()
                    ],
                }
            )
            return receipts

        semantic_session.enhance_ships = record_adapter_enhance
        adapter._dispatch_mutation = record_dispatch
        adapter.oracle.set_enhancement_dock_favourite = record_scope
        adapter.oracle.set_enhancement_dock_filter = record_filter

        task = modules.Enhancement(config=instance.config, device=instance.device)
        started = time.monotonic()
        result["original_task_result"] = task.enhance_ships()
        result["elapsed_seconds"] = round(time.monotonic() - started, 3)
        result["enhancement_grant_remaining"] = adapter._action_ledger.remaining(
            "enhancement.execute"
        )
        result["execution_receipts"] = [
            _execution_value(receipt) for receipt in adapter.enhancement_receipts()
        ]
        result["dock_after"] = {
            "candidate_count": len(adapter.oracle.enhancement_dock_candidates()),
            "main_page_visible": adapter.oracle.main_page_visible(),
        }

        expected_forward = {
            "ship_to_enhance": ship_to_enhance,
            "check_per_category": check_per_category,
            "filter_expression": filter_expression,
        }
        if result["forwarded"] != [expected_forward]:
            raise AssertionError("original Enhancement task did not forward exact config")
        if len(result["dispatches"]) != check_per_category or any(
            item["capability"] != "enhancement.execute"
            for item in result["dispatches"]
        ):
            raise AssertionError(
                "original Enhancement task did not make its configured executions"
            )
        if result["enhancement_grant_remaining"] != 0:
            raise AssertionError(
                "original Enhancement task did not consume its configured grants"
            )
        execution_receipts = result["execution_receipts"]
        if len(execution_receipts) != check_per_category or any(
            item["receipt_type"] != "EnhancementExecutionReceipt"
            for item in execution_receipts
        ):
            raise AssertionError(
                "official recommendation did not produce configured real enhancements"
            )
        consumed = sum(int(item["consumed_count"]) for item in execution_receipts)
        if consumed < check_per_category or result["original_task_result"] != consumed:
            raise AssertionError("original task result does not match confirmed materials")
        if not result["dock_scopes"] or result["dock_scopes"][0]["enabled"] != (
            ship_to_enhance == "favourite"
        ):
            raise AssertionError("original task did not apply configured Dock scope")
        if not result["dock_filters"] or result["dock_filters"][0]["ship_type"] != "dd":
            raise AssertionError("original task did not apply configured DD filter")
        if not result["dock_filters"][0]["candidates_after"]:
            raise AssertionError("configured DD filter exposed no candidate before confirmation")
        if favourite_target is not None:
            favourite_ids = [
                item["ship_id"]
                for item in result["dock_filters"][0]["candidates_after"]
            ]
            if favourite_ids != [favourite_target.ship_id]:
                raise AssertionError(
                    "favourite scope did not expose exactly the seeded target"
                )
        if result["dock_filters"][-1]["ship_type"] is not None:
            raise AssertionError("original task did not restore the normal Dock filter")
        result["passed"] = True
    except BaseException as exc:
        result["error"] = type(exc).__name__ + ": " + str(exc)
        result["traceback"] = traceback.format_exc()
    finally:
        if favourite_bootstrapped and adapter is not None and favourite_target is not None:
            try:
                if original_filter is not None:
                    adapter.oracle.set_enhancement_dock_filter = original_filter
                if original_scope is not None:
                    adapter.oracle.set_enhancement_dock_favourite = original_scope
                cleanup_scope = adapter.oracle.set_enhancement_dock_favourite(True)
                cleanup_filter = adapter.oracle.set_enhancement_dock_filter(
                    filter_expression, enhanceable_only=False
                )
                cleanup_matches = [
                    candidate
                    for candidate in adapter.oracle.enhancement_dock_candidates()
                    if candidate.ship_id == favourite_target.ship_id
                    and candidate.ship_name == favourite_target.ship_name
                ]
                if len(cleanup_matches) > 1:
                    raise AssertionError(
                        "favourite cleanup target is ambiguous in Dock"
                    )
                cleanup_target = cleanup_matches[0] if cleanup_matches else None
                cleanup = ()
                cleanup_changed_common = False
                if cleanup_target is not None:
                    cleanup = adapter.oracle.set_enhancement_dock_candidate_favourite(
                        cleanup_target.position,
                        cleanup_target.ship_id,
                        cleanup_target.ship_name,
                        cleanup_target.level,
                        False,
                    )
                    cleanup_changed_common = "enhancement/detail/favourite/off" in {
                        receipt.semantic_id for receipt in cleanup
                    }
                cleanup_reset = adapter.oracle.reset_enhancement_dock()
                result["favourite_cleanup"] = {
                    "target": (
                        _value(cleanup_target)
                        if cleanup_target is not None
                        else None
                    ),
                    "scope_receipt": _receipt_value(cleanup_scope),
                    "filter_receipts": [
                        _receipt_value(item) for item in cleanup_filter
                    ],
                    "receipts": [_receipt_value(item) for item in cleanup],
                    "changed_common": cleanup_changed_common,
                    "target_absent_from_common_scope": cleanup_target is None,
                    "reset_receipts": [
                        _receipt_value(item) for item in cleanup_reset
                    ],
                }
            except BaseException as cleanup_exc:
                result["passed"] = False
                result["favourite_cleanup_error"] = (
                    type(cleanup_exc).__name__ + ": " + str(cleanup_exc)
                )
                result["favourite_cleanup_traceback"] = traceback.format_exc()
        if semantic_session := (
            getattr(getattr(instance, "__dict__", {}).get("device"), "semantic_adapter", None)
            if instance is not None
            else None
        ):
            if original_adapter_enhance is not None:
                semantic_session.enhance_ships = original_adapter_enhance
        if adapter is not None:
            if original_dispatch is not None:
                adapter._dispatch_mutation = original_dispatch
            if original_scope is not None:
                adapter.oracle.set_enhancement_dock_favourite = original_scope
            if original_filter is not None:
                adapter.oracle.set_enhancement_dock_filter = original_filter
            result["enhancement_grant_remaining"] = adapter._action_ledger.remaining(
                "enhancement.execute"
            )
        _close(instance)
        config_path.unlink(missing_ok=True)
        result["temporary_config_removed"] = not config_path.exists()
        if prior_budget is None:
            os.environ.pop("ALAS_SEMANTIC_ENHANCEMENT_BUDGET", None)
        else:
            os.environ["ALAS_SEMANTIC_ENHANCEMENT_BUDGET"] = prior_budget

    return {
        "schema": "alas-headless.enhancement-task-live-validation/v1",
        "serial": serial,
        "package": package,
        "driver_revision": driver_revision,
        "seed_config": seed_config,
        "seed_config_sha256": _sha256(seed_path),
        "configured": {"Enhance." + key: value for key, value in configured.items()},
        "favourite_target_id": favourite_target_id,
        "source_sha256": {
            "enhancement": _sha256(
                alas_root / "module" / "retire" / "enhancement.py"
            ),
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
    parser.add_argument("--ship-to-enhance", choices=("all", "favourite"), required=True)
    parser.add_argument("--filter", default="dd")
    parser.add_argument("--check-per-category", type=int, default=1)
    parser.add_argument("--favourite-target-id", type=int)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    output = arguments.output.resolve()
    result = validate(
        alas_root=arguments.alas_root.resolve(),
        seed_config=arguments.seed_config,
        driver_revision=arguments.driver_revision,
        ship_to_enhance=arguments.ship_to_enhance,
        filter_expression=arguments.filter,
        check_per_category=arguments.check_per_category,
        favourite_target_id=arguments.favourite_target_id,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    _write_json(output, result)
    print(json.dumps(result, ensure_ascii=False, indent=2), end="\n")
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
