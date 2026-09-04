#!/usr/bin/env python3
"""Validate Daemon's bounded manual or official-auto-search sortie handoff."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import subprocess
import sys
import time
import uuid
from dataclasses import asdict
from pathlib import Path
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "python") not in sys.path:
    sys.path.insert(0, str(ROOT / "python"))


from alas_headless.semantic_sources import semantic_source_hashes


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("expected JSON object: {0}".format(path))
    return value


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
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
    auto_search_completion: bool = False,
) -> Mapping[str, Any]:
    alas_root = alas_root.resolve()
    seed_path = alas_root / "config" / (seed_config + ".json")
    seed = _read_json(seed_path)
    serial = seed["Alas"]["Emulator"]["Serial"]
    package = seed["Alas"]["Emulator"]["PackageName"]
    pid_before = _adb(serial, "shell", "pidof", package)
    if not pid_before:
        raise RuntimeError("game package is not running")

    payload = copy.deepcopy(seed)
    payload["Alas"]["Error"].update({"HandleError": False, "SaveError": False})
    payload["Daemon"]["Daemon"]["EnterMap"] = True
    config_name = "codex_daemon_sortie_" + uuid.uuid4().hex
    config_path = alas_root / "config" / (config_name + ".json")
    _write_json(config_path, payload)
    prior_cwd = Path.cwd()
    prior_env = {
        key: os.environ.get(key)
        for key in (
            "ALAS_SEMANTIC_MODE",
            "ALAS_SEMANTIC_DRIVER_REVISION",
            "ALAS_SEMANTIC_ADB",
            "ALAS_SEMANTIC_CAMPAIGN_STAGE_ENTRY_BUDGET",
            "ALAS_SEMANTIC_CAMPAIGN_FLEET_MUTATION_BUDGET",
            "ALAS_SEMANTIC_CAMPAIGN_SORTIE_BUDGET",
        )
    }
    os.environ.update(
        {
            "ALAS_SEMANTIC_MODE": "1",
            "ALAS_SEMANTIC_DRIVER_REVISION": driver_revision,
            "ALAS_SEMANTIC_ADB": "adb",
            "ALAS_SEMANTIC_CAMPAIGN_STAGE_ENTRY_BUDGET": "1",
            "ALAS_SEMANTIC_CAMPAIGN_FLEET_MUTATION_BUDGET": (
                "6" if auto_search_completion else "0"
            ),
            "ALAS_SEMANTIC_CAMPAIGN_SORTIE_BUDGET": "1",
        }
    )
    for path in (ROOT / "python", alas_root):
        if str(path) not in sys.path:
            sys.path.insert(0, str(path))

    instance: object | None = None
    result: dict[str, Any] = {"passed": False, "temporary_config": config_path.name}
    try:
        os.chdir(alas_root)
        from alas_headless import SemanticGateClosed, SemanticTargetMissing
        from module.campaign.assets import CHAPTER_PREV
        from module.daemon.daemon import AzurLaneDaemon

        stage_code = "12-4" if auto_search_completion else "1-1"
        fleet2 = 2 if auto_search_completion else 0
        fleet_order = (
            "fleet1_mob_fleet2_boss"
            if auto_search_completion
            else "fleet1_all_fleet2_standby"
        )
        instance = AzurLaneDaemon(config_name, task="Daemon")
        instance.config.override(
            Campaign_Name=stage_code,
            Campaign_Event="campaign_main",
            Campaign_Mode="normal",
            Campaign_UseAutoSearch=auto_search_completion,
            Campaign_Use2xBook=False,
            Fleet_Fleet1=1,
            Fleet_Fleet2=fleet2,
            Fleet_FleetOrder=fleet_order,
            Submarine_Fleet=0,
            Submarine_Mode="do_not_use",
        )
        session = instance.device.semantic_adapter
        adapter = session.open()
        if not adapter.oracle.main_page_visible():
            raise SemanticGateClosed("Daemon sortie validation requires main page")

        taps: list[list[int]] = []
        dispatches: list[str] = []
        original_tap = adapter.oracle._tap
        original_dispatch = adapter._dispatch_mutation

        def record_tap(x: int, y: int) -> None:
            taps.append([x, y])
            original_tap(x, y)

        def record_dispatch(capability: str, operation: object) -> object:
            dispatches.append(capability)
            return original_dispatch(capability, operation)

        adapter.oracle._tap = record_tap
        adapter._dispatch_mutation = record_dispatch
        fleet_setup = None
        daemon_dispatch_offset = 0
        adapter.begin_campaign_pre_sortie(stage_code, mode="normal")
        try:
            if auto_search_completion:
                instance.ensure_campaign_ui(stage_code, mode="normal")
                chapter_inputs = None
            else:
                try:
                    instance.ui_goto_campaign()
                except SemanticGateClosed:
                    # The original page graph may probe an unrelated optional
                    # surface during the final Unity remount.  Continue only
                    # when the exact campaign page itself is coherent.
                    adapter.oracle.campaign_page_state()
                chapter_inputs = 0
                for _ in range(20):
                    chapter = adapter.oracle.campaign_page_state()
                    if any(
                        stage.stage_code == stage_code for stage in chapter.stages
                    ):
                        break
                    previous_generation = chapter.generation
                    instance.device.click(CHAPTER_PREV)
                    chapter_inputs += 1
                    adapter.oracle._retry_transition_read(
                        lambda: adapter.oracle.campaign_page_state()
                        if adapter.oracle.campaign_page_state().generation
                        > previous_generation
                        else (_ for _ in ()).throw(
                            SemanticGateClosed("campaign chapter did not advance")
                        ),
                        attempts=40,
                        interval_seconds=0.2,
                    )
                else:
                    raise SemanticGateClosed(
                        "1-1 chapter navigation exceeded its bound"
                    )

            entrance = copy.copy(instance.ENTRANCE)
            entrance.name = stage_code
            entrance.semantic_campaign_stage_code = stage_code
            oil_before = adapter.oracle.campaign_oil()
            instance.device.click(entrance)
            adapter.oracle._retry_transition_read(
                lambda: adapter.oracle.campaign_map_preparation_state(stage_code),
                attempts=60,
                interval_seconds=0.2,
            )
            if (
                adapter.oracle.campaign_auto_search_selected()
                is not auto_search_completion
            ):
                adapter.oracle.click_toggle("campaign/map-preparation/auto-search")
                deadline = time.monotonic() + 8.0
                while (
                    adapter.oracle.campaign_auto_search_selected()
                    is not auto_search_completion
                ):
                    if time.monotonic() >= deadline:
                        raise SemanticGateClosed(
                            "auto-search setting did not reach the requested state"
                        )
                    time.sleep(0.2)

            map_outcome = instance.run_once()
            initial_fleet = adapter.oracle._retry_transition_read(
                lambda: adapter.oracle.campaign_fleet_selection_state(stage_code),
                attempts=60,
                interval_seconds=0.2,
            )
            fleet_outcome = instance.run_once()
            sortie = adapter.confirm_daemon_campaign_sortie()
            completion = session.last_campaign_auto_search_completion()
            if auto_search_completion:
                if completion is None:
                    raise SemanticGateClosed(
                        "Daemon official auto-search completion proof is absent"
                    )
                restored = adapter.oracle._retry_transition_read(
                    adapter.oracle.campaign_page_state,
                    attempts=80,
                    interval_seconds=0.25,
                )
            else:
                adapter.oracle._retry_transition_read(
                    adapter.oracle.open_campaign_withdraw_confirmation,
                    attempts=80,
                    interval_seconds=0.25,
                )
                adapter.oracle._retry_transition_read(
                    lambda: True
                    if adapter.oracle.confirm_campaign_withdrawal_if_present()
                    else (_ for _ in ()).throw(
                        SemanticGateClosed("campaign withdrawal prompt was absent")
                    ),
                    attempts=80,
                    interval_seconds=0.25,
                )
                restored = adapter.oracle._retry_transition_read(
                    adapter.oracle.campaign_page_state,
                    attempts=80,
                    interval_seconds=0.25,
                )
            oil_after = adapter.oracle.campaign_oil()
        finally:
            adapter.end_campaign_pre_sortie()

        for _ in range(3):
            if adapter.oracle.main_page_visible():
                break
            if not adapter.oracle.enabled("campaign-menu/page/back"):
                raise SemanticGateClosed("campaign cleanup back target is absent")
            try:
                receipt = adapter.oracle.click("campaign-menu/page/back")
            except SemanticTargetMissing:
                if adapter.oracle.main_page_visible():
                    break
                raise
            adapter.oracle._retry_transition_read(
                lambda: adapter.oracle.read_state()
                if adapter.oracle.read_state().generation > receipt.generation
                else (_ for _ in ()).throw(
                    SemanticGateClosed("campaign cleanup did not advance")
                ),
                attempts=80,
                interval_seconds=0.25,
            )
        if not adapter.oracle.main_page_visible():
            raise SemanticGateClosed("campaign cleanup did not restore main")
        pid_after = _adb(serial, "shell", "pidof", package)
        expected_fleet_outcome = (
            "auto_search_complete"
            if auto_search_completion
            else "fleet_preparation"
        )
        if (
            map_outcome != "map_preparation"
            or fleet_outcome != expected_fleet_outcome
        ):
            raise AssertionError("Daemon did not own both preparation branches")
        daemon_dispatches = dispatches[daemon_dispatch_offset:]
        if (
            not daemon_dispatches
            or daemon_dispatches[0] != "campaign.stage_entry"
            or daemon_dispatches[-1] != "campaign.sortie"
            or any(
                capability != "campaign.fleet_mutation"
                for capability in daemon_dispatches[1:-1]
            )
        ):
            raise AssertionError("Daemon used an unexpected mutation capability")
        if pid_after != pid_before:
            raise AssertionError("game PID changed during Daemon sortie validation")
        oil_consumed = oil_before - oil_after
        if auto_search_completion:
            # Pinned 12-4 charges the same 10-oil map entry proven by the
            # manual pre-combat withdrawal run, then has six mob battles
            # followed by one boss battle.
            # CampaignSortieProof.required_oil is the one-mob-plus-boss
            # admission floor, not the full-map total.  Requiring the exact
            # fixed clear cost also rejects an accidental second map repeat.
            expected_oil_consumed = (
                10
                + 6 * initial_fleet.mob_oil_cost
                + initial_fleet.boss_oil_cost
            )
            if oil_consumed != expected_oil_consumed:
                raise AssertionError(
                    "Daemon 12-4 auto-search oil delta did not match one full clear"
                )
        else:
            expected_oil_consumed = None
            if not 0 < oil_consumed <= sortie.required_oil:
                raise AssertionError(
                    "Daemon withdrawal oil delta exceeded the proven sortie budget"
                )
        if not adapter.oracle.main_page_visible():
            raise AssertionError("Daemon sortie validation did not restore main")
        result.update(
            {
                "passed": True,
                "pid_before": pid_before,
                "pid_after": pid_after,
                "oil_before": oil_before,
                "oil_after": oil_after,
                "oil_consumed": oil_consumed,
                "expected_oil_consumed": expected_oil_consumed,
                "sortie_admission_oil_floor": sortie.required_oil,
                "chapter_navigation_taps": chapter_inputs,
                "fleet_setup": fleet_setup,
                "map_outcome": map_outcome,
                "fleet_outcome": fleet_outcome,
                "auto_search_completion": (
                    asdict(completion) if completion is not None else None
                ),
                "initial_fleet_selection": {
                    "stage_code": initial_fleet.stage_code,
                    "fleets": [
                        int(row.selected_fleet or 0)
                        for row in initial_fleet.rows
                    ],
                    "generation": initial_fleet.generation,
                },
                "prepared_fleet_selection": {
                    "stage_code": sortie.stage_code,
                    "fleets": list(sortie.prepared_fleets),
                },
                "sortie_proof": asdict(sortie),
                "restored_generation": restored.generation,
                "typed_taps": taps,
                "mutation_dispatches": dispatches,
                "daemon_mutation_dispatches": daemon_dispatches,
                "withdrawn_before_combat": not auto_search_completion,
                "main_page_visible_after_cleanup": True,
            }
        )
    finally:
        if instance is not None:
            device = getattr(instance, "__dict__", {}).get("device")
            session = getattr(device, "__dict__", {}).get("semantic_adapter")
            if session is not None:
                session.close()
        os.chdir(prior_cwd)
        for key, value in prior_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        config_path.unlink(missing_ok=True)
        result["temporary_config_removed"] = not config_path.exists()

    return {
        "schema": "alas-headless.daemon-sortie-live-validation/v1",
        "serial": serial,
        "package": package,
        "driver_revision": driver_revision,
        "seed_config": seed_config,
        "seed_config_sha256": _sha256(seed_path),
        "configured": {
            "Daemon.EnterMap": True,
            "stage": "12-4" if auto_search_completion else "1-1",
            "fleets": [1, 2 if auto_search_completion else 0, 0],
            "auto_search": auto_search_completion,
            "use_2x_book": False,
        },
        **result,
        "source_sha256": {
            **semantic_source_hashes(ROOT),
            "daemon": _sha256(alas_root / "module" / "daemon" / "daemon.py"),
            "adapter": _sha256(ROOT / "python" / "alas_headless" / "alas_adapter.py"),
            "oracle": _sha256(ROOT / "python" / "alas_headless" / "semantic_oracle.py"),
            "runner": _sha256(Path(__file__)),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--alas-root", type=Path, required=True)
    parser.add_argument("--seed-config", default="semantic_e2e")
    parser.add_argument("--driver-revision", required=True)
    parser.add_argument("--auto-search-completion", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = validate(
        alas_root=args.alas_root,
        seed_config=args.seed_config,
        driver_revision=args.driver_revision,
        auto_search_completion=args.auto_search_completion,
    )
    text = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.resolve().write_text(text, encoding="utf-8")
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
