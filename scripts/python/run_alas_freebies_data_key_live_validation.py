#!/usr/bin/env python3
"""Run original Freebies through the typed full-capacity DataKey branch."""

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
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "python") not in sys.path:
    sys.path.insert(0, str(ROOT / "python"))


from alas_headless.semantic_sources import semantic_source_hashes


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
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


def validate(
    *,
    alas_root: Path,
    seed_config: str,
    driver_revision: str,
    force_collect: bool,
    recover_pending_limit_prompt: bool,
    postcondition_only: bool,
) -> Mapping[str, Any]:
    seed_path = alas_root / "config" / (seed_config + ".json")
    seed = json.loads(seed_path.read_text(encoding="utf-8"))
    serial = seed["Alas"]["Emulator"]["Serial"]
    package = seed["Alas"]["Emulator"]["PackageName"]
    if not _adb(serial, "shell", "pidof", package):
        raise RuntimeError("game package is not running")

    os.environ["ALAS_SEMANTIC_MODE"] = "1"
    os.environ["ALAS_SEMANTIC_DRIVER_REVISION"] = driver_revision
    os.environ["ALAS_SEMANTIC_ADB"] = "adb"
    for path in (ROOT / "python", alas_root):
        if str(path) not in sys.path:
            sys.path.insert(0, str(path))
    os.chdir(alas_root)
    from alas import AzurLaneAutoScript
    from module.config.config import name_to_function

    payload = copy.deepcopy(seed)
    payload["Alas"]["Error"].update({"HandleError": False, "SaveError": False})
    payload["Freebies"]["Scheduler"]["Enable"] = False
    payload["Freebies"]["BattlePass"]["Collect"] = False
    payload["Freebies"]["DataKey"].update(
        {"Collect": True, "ForceCollect": force_collect}
    )
    payload["Freebies"]["Mail"].update(
        {
            "ClaimMaintenance": False,
            "ClaimMerit": False,
            "ClaimTradeLicense": False,
            "DeleteCollected": False,
        }
    )
    payload["Freebies"]["SupplyPack"]["Collect"] = False
    config_name = "codex_freebies_data_key_" + uuid.uuid4().hex
    config_path = alas_root / "config" / (config_name + ".json")
    _write_json(config_path, payload)

    instance: object | None = None
    result: dict[str, Any] = {"passed": False}
    observations: list[dict[str, Any]] = []
    collect_calls: list[dict[str, Any]] = []
    limit_choices: list[dict[str, Any]] = []
    try:
        instance = AzurLaneAutoScript(config_name)
        instance.config.bind("Freebies")
        instance.config.task = name_to_function("Freebies")
        adapter = instance.device.semantic_adapter.open()
        oracle = adapter.oracle
        if recover_pending_limit_prompt:
            from module.handler.assets import POPUP_CANCEL

            instance.device.screenshot()
            adapter.begin_data_key(force_collect=False)
            try:
                if oracle.data_key_limit_prompt_visible():
                    receipt = instance.device.semantic_adapter.click(POPUP_CANCEL)
                    result["recovered_pending_limit_prompt"] = {
                        "semantic_id": receipt.semantic_id,
                        "generation": receipt.generation,
                        "path": receipt.path,
                    }
                else:
                    result["recovered_pending_limit_prompt"] = None
            finally:
                adapter.end_data_key()
        original_text = oracle.war_archives_data_key_text
        original_collected = oracle.war_archives_data_key_collected
        original_collect = oracle.click_war_archives_data_key_collect
        original_limit_choice = oracle.click_data_key_limit_choice

        def record_text() -> str:
            value = original_text()
            observations.append({"kind": "counter", "value": value})
            return value

        def record_collected() -> bool:
            value = original_collected()
            observations.append({"kind": "collected", "value": value})
            return value

        def record_collect() -> object:
            receipt = original_collect()
            collect_calls.append(
                {
                    "semantic_id": receipt.semantic_id,
                    "generation": receipt.generation,
                    "path": receipt.path,
                }
            )
            return receipt

        def record_limit_choice(*, confirm: bool) -> object:
            receipt = original_limit_choice(confirm=confirm)
            limit_choices.append(
                {
                    "confirm": confirm,
                    "semantic_id": receipt.semantic_id,
                    "generation": receipt.generation,
                    "path": receipt.path,
                }
            )
            return receipt

        oracle.war_archives_data_key_text = record_text
        oracle.war_archives_data_key_collected = record_collected
        oracle.click_war_archives_data_key_collect = record_collect
        oracle.click_data_key_limit_choice = record_limit_choice
        # Keep partial action evidence if the original task exits through a
        # classified semantic failure; the receipt must not erase the exact
        # mutation that preceded it.
        result["observations"] = observations
        result["collect_calls"] = collect_calls
        result["limit_choices"] = limit_choices
        started = time.monotonic()
        result["task_result"] = instance.run("freebies")
        result["elapsed_seconds"] = round(time.monotonic() - started, 3)
        result["scheduler_next_run"] = str(instance.config.Scheduler_NextRun)
        if result["task_result"] is not True:
            raise AssertionError("original ALAS Freebies task did not return success")
        counters = [item["value"] for item in observations if item["kind"] == "counter"]
        collected = [item["value"] for item in observations if item["kind"] == "collected"]
        if postcondition_only:
            final_collected = original_collected()
            result["post_collected"] = final_collected
            result["post_counter"] = original_text()
            if not collected or collected[0] is not True or final_collected is not True:
                raise AssertionError("confirmed DataKey postcondition is absent")
            if result["post_counter"] != "300/300":
                raise AssertionError("full-capacity DataKey counter changed")
            if collect_calls or limit_choices:
                raise AssertionError("postcondition-only run attempted a mutation")
        elif "300/300" not in counters or not collected or collected[0] is not False:
            raise AssertionError("full-capacity uncollected DataKey precondition was absent")
        if not postcondition_only and force_collect:
            final_collected = original_collected()
            result["post_collected"] = final_collected
            result["post_counter"] = original_text()
            if len(collect_calls) != 1:
                raise AssertionError("forced full-capacity branch needs one exact claim")
            if [item["semantic_id"] for item in limit_choices] != [
                "archive/key-limit/confirm"
            ]:
                raise AssertionError("forced full-capacity confirmation was not exact")
            if final_collected is not True:
                raise AssertionError("forced DataKey claim postcondition is absent")
        elif not postcondition_only:
            if True in collected:
                raise AssertionError("safe full-capacity branch changed collected state")
            if collect_calls or limit_choices:
                raise AssertionError("safe full-capacity branch attempted a claim")
        result["passed"] = True
    except BaseException as exc:
        result["error"] = type(exc).__name__ + ": " + str(exc)
        result["traceback"] = traceback.format_exc()
        if instance is not None:
            try:
                diagnostic_oracle = instance.device.semantic_adapter.open().oracle
                state = diagnostic_oracle.read_state()
                ui_state = diagnostic_oracle.read_ui_state()
                fragments = ("AwardInfo", "LevelRemasterView", "Msgbox")
                result["failure_surface"] = {
                    "generation": state.generation,
                    "buttons": [
                        {
                            "name": button.name,
                            "path": button.path,
                            "active": button.active_in_hierarchy,
                            "enabled": button.active_and_enabled,
                            "interactable": button.interactable,
                            "raycast_top": button.raycast_top,
                        }
                        for button in state.buttons
                        if any(fragment in button.path for fragment in fragments)
                    ],
                    "texts": [
                        {"path": item.path, "text": item.text}
                        for item in ui_state.texts
                        if any(fragment in item.path for fragment in fragments)
                    ],
                    "images": [
                        {
                            "path": item.path,
                            "sprite": item.sprite,
                            "active": item.active_in_hierarchy,
                            "enabled": item.active_and_enabled,
                        }
                        for item in ui_state.images
                        if "LevelRemasterView(Clone)/getBtn" in item.path
                    ],
                }
            except BaseException as diagnostic_exc:
                result["failure_surface_error"] = (
                    type(diagnostic_exc).__name__ + ": " + str(diagnostic_exc)
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
        "schema": "alas-headless.freebies-data-key-live-validation/v1",
        "serial": serial,
        "package": package,
        "driver_revision": driver_revision,
        "seed_config": seed_config,
        "seed_config_sha256": _sha256(seed_path),
        "validation_mode": (
            "postcondition-only" if postcondition_only else "full-branch"
        ),
        "configured": {
            "BattlePass.Collect": False,
            "DataKey.Collect": True,
            "DataKey.ForceCollect": force_collect,
            "Mail.ClaimMaintenance": False,
            "Mail.ClaimMerit": False,
            "Mail.ClaimTradeLicense": False,
            "Mail.DeleteCollected": False,
            "SupplyPack.Collect": False,
        },
        "source_sha256": {
            **semantic_source_hashes(ROOT),
            "freebies": _sha256(alas_root / "module/freebies/freebies.py"),
            "data_key": _sha256(alas_root / "module/freebies/data_key.py"),
            "adapter": _sha256(ROOT / "python/alas_headless/alas_adapter.py"),
            "oracle": _sha256(ROOT / "python/alas_headless/semantic_oracle.py"),
        },
        **result,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--alas-root", type=Path, required=True)
    parser.add_argument("--seed-config", default="semantic_e2e")
    parser.add_argument("--driver-revision", required=True)
    parser.add_argument("--force-collect", action="store_true")
    parser.add_argument("--recover-pending-limit-prompt", action="store_true")
    parser.add_argument("--postcondition-only", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    output = arguments.output.resolve()
    result = validate(
        alas_root=arguments.alas_root.resolve(),
        seed_config=arguments.seed_config,
        driver_revision=arguments.driver_revision,
        force_collect=arguments.force_collect,
        recover_pending_limit_prompt=arguments.recover_pending_limit_prompt,
        postcondition_only=arguments.postcondition_only,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    _write_json(output, result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
