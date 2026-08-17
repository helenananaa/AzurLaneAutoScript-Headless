#!/usr/bin/env python3
"""Exercise every declared ``Enhance.Filter`` ship type on a live Dock."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
import traceback
from dataclasses import asdict
from pathlib import Path
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[2]
SHIP_TYPES = {
    "dd": "3",
    "cl": "4",
    "ca": "5",
    "bb": "6",
    "cv": "7",
    "repair": "8",
    "ss": "9",
    "others": "10",
}

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


def _receipt_value(receipt: object) -> dict[str, Any]:
    point = getattr(receipt, "point", None)
    return {
        "semantic_id": getattr(receipt, "semantic_id", None),
        "generation": getattr(receipt, "generation", None),
        "path": getattr(receipt, "path", None),
        "point": {"x": point.x, "y": point.y} if point is not None else None,
    }


def _ensure_dock(oracle: Any) -> dict[str, Any]:
    try:
        oracle._enhancement_dock_records()
    except Exception:
        if not oracle.main_page_visible():
            raise AssertionError("filter qualifier is neither on Dock nor main")
        entry = oracle.click("main/dock")
        for _ in range(30):
            try:
                oracle._enhancement_dock_records()
                return {"already_in_dock": False, "entry": _receipt_value(entry)}
            except Exception:
                time.sleep(0.1)
        raise AssertionError("main/dock did not reach a typed Dock")
    return {"already_in_dock": True, "entry": None}


def validate(*, seed_config: Path, driver_revision: str) -> Mapping[str, Any]:
    from alas_headless import AlasSemanticSession

    seed = _read_json(seed_config)
    serial = seed["Alas"]["Emulator"]["Serial"]
    package = seed["Alas"]["Emulator"]["PackageName"]
    if not isinstance(serial, str) or not serial:
        raise AssertionError("seed config has no emulator serial")
    if not isinstance(package, str) or not package:
        raise AssertionError("seed config has no package")
    if not _adb(serial, "shell", "pidof", package):
        raise RuntimeError("game package is not running")

    result: dict[str, Any] = {
        "schema": "alas-headless.enhancement-filter-matrix-live-validation/v1",
        "serial": serial,
        "package": package,
        "driver_revision": driver_revision,
        "seed_config": seed_config.name,
        "seed_config_sha256": _sha256(seed_config),
        "source_sha256": {
            "oracle": _sha256(ROOT / "python" / "alas_headless" / "semantic_oracle.py"),
            "runner": _sha256(Path(__file__).resolve()),
        },
        "passed": False,
        "filters": [],
        "reset": None,
    }
    os.environ["ALAS_SEMANTIC_MODE"] = "1"
    os.environ["ALAS_SEMANTIC_DRIVER_REVISION"] = driver_revision
    os.environ["ALAS_SEMANTIC_ADB"] = "adb"
    try:
        with AlasSemanticSession(
            serial=serial, driver_revision=driver_revision
        ) as adapter:
            oracle = adapter.oracle
            result["dock_entry"] = _ensure_dock(oracle)
            for ship_type, index in SHIP_TYPES.items():
                receipts = oracle.set_enhancement_dock_filter(ship_type)
                semantic_ids = tuple(item.semantic_id for item in receipts)
                if "enhancement/dock/filter/index/" + index not in semantic_ids:
                    raise AssertionError(
                        "live filter did not select exact index for " + ship_type
                    )
                if semantic_ids[-1] != "enhancement/dock/filter/confirm":
                    raise AssertionError("live filter did not confirm " + ship_type)
                try:
                    candidates = [asdict(item) for item in oracle.enhancement_dock_candidates()]
                except Exception as exc:
                    candidates = None
                    candidate_error = type(exc).__name__ + ": " + str(exc)
                else:
                    candidate_error = None
                result["filters"].append(
                    {
                        "ship_type": ship_type,
                        "index": index,
                        "receipts": [_receipt_value(item) for item in receipts],
                        "candidate_count": len(candidates) if candidates is not None else None,
                        "candidates": candidates,
                        "candidate_read_error": candidate_error,
                    }
                )
            reset = oracle.reset_enhancement_dock()
            reset_ids = tuple(item.semantic_id for item in reset)
            if "enhancement/dock/reset/no-limit" not in reset_ids:
                raise AssertionError("Dock reset did not restore no-limit filter")
            oracle._enhancement_dock_records()
            result["reset"] = {"receipts": [_receipt_value(item) for item in reset]}
            result["passed"] = True
    except BaseException as exc:
        result["error"] = type(exc).__name__ + ": " + str(exc)
        result["traceback"] = traceback.format_exc()
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--alas-root", type=Path, required=True)
    parser.add_argument("--seed-config", default="semantic_e2e")
    parser.add_argument("--driver-revision", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    result = validate(
        seed_config=args.alas_root.resolve() / "config" / (args.seed_config + ".json"),
        driver_revision=args.driver_revision,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    _write_json(output, result)
    print(json.dumps(result, ensure_ascii=False, indent=2), end="\n")
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
