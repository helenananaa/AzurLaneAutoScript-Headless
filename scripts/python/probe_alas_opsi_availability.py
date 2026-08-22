#!/usr/bin/env python3
"""Read the currently visible Operation Siren/META surface without input."""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
from pathlib import Path
from typing import Any, Callable


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))

from alas_headless import (  # noqa: E402
    AdbObserverBridge,
    OracleFingerprint,
    SemanticGateClosed,
    SemanticOracle,
)


def _json_value(value: Any) -> Any:
    if dataclasses.is_dataclass(value):
        return dataclasses.asdict(value)
    if isinstance(value, tuple):
        return list(value)
    return value


def _probe(call: Callable[[], Any]) -> dict[str, Any]:
    try:
        return {"available": True, "value": _json_value(call())}
    except SemanticGateClosed as exc:
        return {"available": False, "reason": str(exc)}


def _reject_input(_x: int, _y: int) -> None:
    raise RuntimeError("availability probe forbids all Android input")


def collect_availability(oracle: SemanticOracle) -> dict[str, Any]:
    """Collect passive facts from whichever reviewed surface is already open."""

    state = oracle.read_state()
    ui_state = oracle.read_ui_state()
    return {
        "generation": {"buttons": state.generation, "ui": ui_state.generation},
        "scene_handle": state.scene_handle,
        "button_count": len(state.buttons),
        "text_count": len(ui_state.texts),
        "operation_siren": {
            "local_map": _probe(oracle.operation_siren_state),
            "globe": _probe(oracle.operation_siren_globe_state),
            "storage": _probe(oracle.operation_siren_storage_state),
            "mission_overview_visible": oracle.operation_siren_mission_overview_visible(),
            "mission_list_visible": oracle.operation_siren_mission_list_visible(),
            "mission_checkout_excluding_monthly_boss": _probe(
                lambda: oracle.operation_siren_mission_checkout_available(
                    exclude_monthly_boss=True
                )
            ),
            "mission_finish": _probe(
                oracle.operation_siren_mission_finish_available
            ),
        },
        "meta": {
            "landing": _probe(oracle.meta_entrance_state),
            "current_empty": _probe(oracle.meta_current_empty_points),
            "current_detail": _probe(oracle.meta_current_detail_state),
            "assist": _probe(oracle.meta_assist_state),
        },
        "input_injected": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--serial", required=True)
    parser.add_argument("--driver-revision", required=True)
    parser.add_argument("--package", default="com.bilibili.azurlane")
    parser.add_argument(
        "--component",
        default="com.bilibili.azurlane/com.manjuu.azurlane.MainActivity",
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    with AdbObserverBridge(args.serial, args.package) as bridge:
        oracle = SemanticOracle(
            bridge.request,
            bridge.foreground_component,
            _reject_input,
            OracleFingerprint(
                package=args.package,
                component=args.component,
                driver_revision=args.driver_revision,
                expected_pid=bridge.pid,
            ),
        )
        payload = {
            "schema": "alas-headless.operation-siren-availability-probe/v1",
            "serial": args.serial,
            "package": args.package,
            "pid": bridge.pid,
            "driver_revision": args.driver_revision,
            **collect_availability(oracle),
            "passed": True,
        }

    rendered = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
