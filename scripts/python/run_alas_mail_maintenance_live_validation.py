#!/usr/bin/env python3
"""Run the original ALAS maintenance-mail branch with two typed claim grants."""

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


def _load_modules(alas_root: Path, driver_revision: str) -> SimpleNamespace:
    os.environ["ALAS_SEMANTIC_MODE"] = "1"
    os.environ["ALAS_SEMANTIC_DRIVER_REVISION"] = driver_revision
    os.environ["ALAS_SEMANTIC_ADB"] = "adb"
    os.environ["ALAS_SEMANTIC_MAIL_MUTATION_BUDGET"] = "2"
    for path in (ROOT / "python", alas_root):
        value = str(path)
        if value not in sys.path:
            sys.path.insert(0, value)
    os.chdir(alas_root)
    from alas import AzurLaneAutoScript
    from module.config.config import name_to_function

    return SimpleNamespace(
        AzurLaneAutoScript=AzurLaneAutoScript,
        name_to_function=name_to_function,
    )


def _close(instance: object | None) -> None:
    if instance is None:
        return
    device = getattr(instance, "__dict__", {}).get("device")
    session = getattr(device, "__dict__", {}).get("semantic_adapter")
    if session is not None:
        session.close()


def _mail_snapshot(serial: str, driver_revision: str) -> Mapping[str, Any]:
    from alas_headless import AlasSemanticSession

    with AlasSemanticSession(serial=serial, driver_revision=driver_revision) as adapter:
        oracle = adapter.oracle
        entered = None
        if oracle.main_page_visible():
            entered = oracle.click("main/mail")
            oracle.wait_for("mail/page/back", 15, minimum_generation=entered.generation)
        elif not oracle.enabled("mail/page/back"):
            raise AssertionError("mail snapshot cannot prove main or MailUI page")

        used, capacity = oracle.mail_count()
        ui_state = oracle.read_ui_state()
        resources: dict[str, int] = {}
        for source_name, output_name in (
            ("oil", "oil"),
            ("gold", "coins"),
            ("gem", "gems"),
        ):
            suffix = "MailUI(Clone)/adapt/top/res/{0}/Text".format(source_name)
            matches = tuple(
                item
                for item in ui_state.texts
                if item.path.endswith(suffix)
                and item.active_in_hierarchy
                and item.active_and_enabled
                and not item.truncated
                and item.bounds is not None
                and item.text.strip().isdigit()
            )
            if len(matches) != 1:
                raise AssertionError("mail resource counter is absent or ambiguous: " + output_name)
            resources[output_name] = int(matches[0].text.strip())

        cleanup = None
        if oracle.enabled("mail/page/back"):
            cleanup = oracle.click("mail/page/back")
            oracle.wait_for("main/task", 15, minimum_generation=cleanup.generation)
        if not oracle.main_page_visible():
            raise AssertionError("mail snapshot cleanup did not restore the main page")
        return {
            "mail_count": {"used": used, "capacity": capacity},
            "resources": resources,
            "entry": None
            if entered is None
            else {"semantic_id": entered.semantic_id, "generation": entered.generation},
            "cleanup": None
            if cleanup is None
            else {"semantic_id": cleanup.semantic_id, "generation": cleanup.generation},
        }


def validate(*, alas_root: Path, seed_config: str, driver_revision: str) -> Mapping[str, Any]:
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

    before = _mail_snapshot(serial, driver_revision)
    payload = copy.deepcopy(seed)
    payload["Alas"]["Error"].update({"HandleError": False, "SaveError": False})
    payload["Freebies"]["Scheduler"]["Enable"] = False
    payload["Freebies"]["BattlePass"]["Collect"] = False
    payload["Freebies"]["DataKey"].update({"Collect": False, "ForceCollect": False})
    payload["Freebies"]["Mail"].update(
        {
            "ClaimMaintenance": True,
            "ClaimMerit": False,
            "ClaimTradeLicense": False,
            "DeleteCollected": False,
        }
    )
    payload["Freebies"]["SupplyPack"]["Collect"] = False
    config_name = "codex_mail_maintenance_live_" + uuid.uuid4().hex
    config_path = alas_root / "config" / (config_name + ".json")
    _write_json(config_path, payload)

    result: dict[str, Any] = {"passed": False, "before": before}
    instance: object | None = None
    prior_budget = os.environ.get("ALAS_SEMANTIC_MAIL_MUTATION_BUDGET")
    try:
        modules = _load_modules(alas_root, driver_revision)
        instance = modules.AzurLaneAutoScript(config_name)
        instance.config.bind("Freebies")
        instance.config.task = modules.name_to_function("Freebies")
        adapter = instance.device.semantic_adapter.open()
        dispatches: list[dict[str, Any]] = []
        original_dispatch = adapter._dispatch_mutation

        def record_dispatch(capability: str, operation: object) -> object:
            receipt = original_dispatch(capability, operation)
            dispatches.append(
                {
                    "capability": capability,
                    "semantic_id": getattr(receipt, "semantic_id", None),
                    "generation": getattr(receipt, "generation", None),
                    "path": getattr(receipt, "path", None),
                    "remaining_after_dispatch": getattr(
                        receipt, "remaining_after_dispatch", None
                    ),
                }
            )
            return receipt

        adapter._dispatch_mutation = record_dispatch
        started = time.monotonic()
        result["task_result"] = instance.run("freebies")
        result["elapsed_seconds"] = round(time.monotonic() - started, 3)
        result["dispatches"] = dispatches
        result["mail_mutation_grant_remaining"] = adapter._action_ledger.remaining(
            "mail.mutation"
        )
        if result["task_result"] is not True:
            raise AssertionError("original ALAS Freebies task did not return success")
        if len(dispatches) != 2 or any(
            item["capability"] != "mail.mutation"
            or item["semantic_id"] != "mail/manage/claim"
            for item in dispatches
        ):
            raise AssertionError("maintenance mail did not use exactly two typed claim grants")
        if result["mail_mutation_grant_remaining"] != 0:
            raise AssertionError("maintenance mail did not exhaust its two claim grants")
        instance.device.semantic_adapter.close()
        instance.device.semantic_adapter = None
        after = _mail_snapshot(serial, driver_revision)
        result["after"] = after
        result["mail_count_delta"] = (
            before["mail_count"]["used"] - after["mail_count"]["used"]
        )
        result["resource_delta"] = {
            name: after["resources"][name] - before["resources"][name]
            for name in before["resources"]
        }
        if result["mail_count_delta"] <= 0:
            raise AssertionError("maintenance mail run did not remove any mail")
        if any(value < 0 for value in result["resource_delta"].values()):
            raise AssertionError("mail collection reduced a tracked resource")
        if not any(value > 0 for value in result["resource_delta"].values()):
            raise AssertionError("maintenance mail run did not increase a tracked resource")
        result["passed"] = True
    except BaseException as exc:
        result["error"] = type(exc).__name__ + ": " + str(exc)
        result["traceback"] = traceback.format_exc()
    finally:
        _close(instance)
        config_path.unlink(missing_ok=True)
        result["temporary_config_removed"] = not config_path.exists()
        if prior_budget is None:
            os.environ.pop("ALAS_SEMANTIC_MAIL_MUTATION_BUDGET", None)
        else:
            os.environ["ALAS_SEMANTIC_MAIL_MUTATION_BUDGET"] = prior_budget

    return {
        "schema": "alas-headless.mail-maintenance-live-validation/v1",
        "serial": serial,
        "package": package,
        "driver_revision": driver_revision,
        "seed_config": seed_config,
        "seed_config_sha256": _sha256(seed_path),
        "configured": {
            "BattlePass.Collect": False,
            "DataKey.Collect": False,
            "DataKey.ForceCollect": False,
            "Mail.ClaimMaintenance": True,
            "Mail.ClaimMerit": False,
            "Mail.ClaimTradeLicense": False,
            "Mail.DeleteCollected": False,
            "SupplyPack.Collect": False,
        },
        "source_sha256": {
            "freebies": _sha256(alas_root / "module" / "freebies" / "freebies.py"),
            "mail": _sha256(alas_root / "module" / "freebies" / "mail_white.py"),
            "adapter": _sha256(ROOT / "python" / "alas_headless" / "alas_adapter.py"),
            "oracle": _sha256(ROOT / "python" / "alas_headless" / "semantic_oracle.py"),
        },
        **result,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--alas-root", type=Path, required=True)
    parser.add_argument("--seed-config", default="semantic_e2e")
    parser.add_argument("--driver-revision", required=True)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    output = arguments.output.resolve()
    result = validate(
        alas_root=arguments.alas_root.resolve(),
        seed_config=arguments.seed_config,
        driver_revision=arguments.driver_revision,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    _write_json(output, result)
    print(json.dumps(result, ensure_ascii=False, indent=2), end="\n")
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
