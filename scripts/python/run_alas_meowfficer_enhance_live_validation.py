#!/usr/bin/env python3
"""Validate one typed Meowfficer enhancement decision on the live game."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import subprocess
import sys
import uuid
from dataclasses import asdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "python") not in sys.path:
    sys.path.insert(0, str(ROOT / "python"))


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _adb(serial: str, *arguments: str) -> str:
    return subprocess.run(
        ("adb", "-s", serial, *arguments),
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=90,
    ).stdout.strip()


def validate(
    *,
    alas_root: Path,
    seed_config: str,
    driver_revision: str,
    index: int,
    max_feed_level: int,
) -> dict[str, Any]:
    seed_path = alas_root / "config" / (seed_config + ".json")
    seed = _read_json(seed_path)
    serial = seed["Alas"]["Emulator"]["Serial"]
    package = seed["Alas"]["Emulator"]["PackageName"]
    if not _adb(serial, "shell", "pidof", package):
        raise RuntimeError("game package is not running")

    payload = copy.deepcopy(seed)
    payload["Alas"]["Error"].update({"HandleError": False, "SaveError": False})
    config_name = "codex_meowfficer_enhance_live_" + uuid.uuid4().hex
    config_path = alas_root / "config" / (config_name + ".json")
    _write_json(config_path, payload)
    instance: object | None = None
    os.environ.update(
        {
            "ALAS_SEMANTIC_MODE": "1",
            "ALAS_SEMANTIC_DRIVER_REVISION": driver_revision,
            "ALAS_SEMANTIC_ADB": "adb",
        }
    )
    for path in (ROOT / "python", alas_root):
        if str(path) not in sys.path:
            sys.path.insert(0, str(path))
    os.chdir(alas_root)
    result: dict[str, Any] = {"passed": False, "temporary_config": config_path.name}
    try:
        from alas import AzurLaneAutoScript
        from alas_headless import SemanticGateClosed
        from module.config.config import name_to_function
        from module.handler.login import LoginHandler
        from module.meowfficer.meowfficer import RewardMeowfficer
        from module.ui.page import page_meowfficer

        instance = AzurLaneAutoScript(config_name)
        task = name_to_function("Meowfficer")
        instance.config.task = task
        instance.config.bind(task)
        session = instance.device.semantic_adapter
        adapter = session.open()
        meowfficer = RewardMeowfficer(config=instance.config, device=instance.device)
        try:
            before = adapter.oracle.meowfficer_dock_state()
        except SemanticGateClosed:
            LoginHandler(config=instance.config, device=instance.device).handle_app_login()
            meowfficer.ui_ensure(page_meowfficer)
            meowfficer.wait_meowfficer_buttons()
            before = adapter.oracle.meowfficer_dock_state()
        cats = adapter.oracle.meowfficer_dock_cats()
        dispatches: list[str] = []
        taps: list[list[int]] = []
        original_dispatch = adapter._dispatch_mutation
        original_tap = adapter.oracle._tap

        def record_dispatch(capability: str, operation: object) -> object:
            dispatches.append(capability)
            return original_dispatch(capability, operation)

        def record_tap(x: int, y: int) -> None:
            taps.append([x, y])
            original_tap(x, y)

        adapter._dispatch_mutation = record_dispatch
        adapter.oracle._tap = record_tap
        decision = adapter.enhance_meowfficer(
            index=index, max_feed_level=max_feed_level
        )
        after = adapter.oracle.meowfficer_dock_state()
        if decision == "leveled_max":
            if taps or dispatches:
                raise AssertionError("level-max enhancement decision injected input")
            if before != after:
                raise AssertionError("level-max enhancement decision changed dock state")
        result.update(
            {
                "passed": True,
                "decision": decision,
                "before": asdict(before),
                "after": asdict(after),
                "visible_cats": [asdict(cat) for cat in cats],
                "selected_target": asdict(cats[index - 1]) if index <= len(cats) else None,
                "typed_taps": taps,
                "mutation_dispatches": dispatches,
            }
        )
    finally:
        if instance is not None:
            device = getattr(instance, "__dict__", {}).get("device")
            session = getattr(device, "__dict__", {}).get("semantic_adapter")
            if session is not None:
                session.close()
        config_path.unlink(missing_ok=True)
        result["temporary_config_removed"] = not config_path.exists()

    return {
        "schema": "alas-headless.meowfficer-enhance-live-validation/v1",
        "serial": serial,
        "package": package,
        "driver_revision": driver_revision,
        "seed_config": seed_config,
        "seed_config_sha256": _sha256(seed_path),
        "configured": {"index": index, "max_feed_level": max_feed_level},
        **result,
        "source_sha256": {
            "adapter": _sha256(ROOT / "python" / "alas_headless" / "alas_adapter.py"),
            "oracle": _sha256(ROOT / "python" / "alas_headless" / "semantic_oracle.py"),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--alas-root", type=Path, required=True)
    parser.add_argument("--seed-config", default="semantic_e2e")
    parser.add_argument("--driver-revision", required=True)
    parser.add_argument("--index", type=int, default=1)
    parser.add_argument("--max-feed-level", type=int, default=5)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    output = args.output.resolve() if args.output else None
    result = validate(
        alas_root=args.alas_root,
        seed_config=args.seed_config,
        driver_revision=args.driver_revision,
        index=args.index,
        max_feed_level=args.max_feed_level,
    )
    text = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if output:
        output.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
