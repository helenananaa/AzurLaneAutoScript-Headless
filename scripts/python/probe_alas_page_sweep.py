#!/usr/bin/env python3
"""Time ALAS' read-only page enumeration on the current semantic frame."""

from __future__ import annotations

import argparse
import copy
import cProfile
import json
import os
import sys
import time
import uuid
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--alas-root", type=Path, required=True)
    parser.add_argument("--serial", required=True)
    parser.add_argument("--driver-revision", required=True)
    parser.add_argument("--expected-page", required=True)
    parser.add_argument("--only-page")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--profile", type=Path, help="Profile only the page scan, excluding frame acquisition")
    args = parser.parse_args()

    alas_root = args.alas_root.resolve()
    seed = json.loads((alas_root / "config/semantic_e2e.json").read_text(encoding="utf-8"))
    config = copy.deepcopy(seed)
    config["Alas"]["Emulator"]["Serial"] = args.serial
    config["Alas"]["Error"].update({"HandleError": False, "SaveError": False})
    name = "codex_page_sweep_" + uuid.uuid4().hex
    config_path = alas_root / "config" / (name + ".json")
    config_path.write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")
    output = args.output.resolve()
    profile_path = args.profile.resolve() if args.profile else None
    profiler = cProfile.Profile() if profile_path else None
    prior_cwd = Path.cwd()
    previous_env = {key: os.environ.get(key) for key in (
        "ALAS_SEMANTIC_MODE", "ALAS_SEMANTIC_DRIVER_REVISION", "ALAS_SEMANTIC_ADB"
    )}
    os.environ.update({
        "ALAS_SEMANTIC_MODE": "1",
        "ALAS_SEMANTIC_DRIVER_REVISION": args.driver_revision,
        "ALAS_SEMANTIC_ADB": "adb",
    })
    sys.path.insert(0, str(alas_root))
    instance = None
    result = {
        "schema": "alas-headless.page-sweep-probe/v1",
        "serial": args.serial,
        "expected_page": args.expected_page,
        "input_injected": False,
        "pages": [],
    }
    try:
        os.chdir(alas_root)
        from alas import AzurLaneAutoScript
        from module.freebies.battle_pass import BattlePass
        from module.ui.page import Page

        instance = AzurLaneAutoScript(name)
        instance.config.bind("Freebies")
        session = instance.device.semantic_adapter
        session.begin_battle_pass()
        instance.device.screenshot()
        ui = BattlePass(instance.config, instance.device)
        if profiler is not None:
            profiler.enable()
        start = time.monotonic()
        for page in Page.iter_pages():
            if page.check_button is None:
                continue
            if args.only_page is not None and page.name != args.only_page:
                continue
            page_start = time.monotonic()
            visible = ui.ui_page_appear(page)
            result["pages"].append({
                "name": page.name,
                "visible": visible,
                "elapsed_seconds": round(time.monotonic() - page_start, 3),
            })
            if visible:
                break
        result["elapsed_seconds"] = round(time.monotonic() - start, 3)
        result["passed"] = bool(result["pages"] and (
            (args.only_page is not None and result["pages"][-1]["name"] == args.only_page)
            or (
                args.only_page is None
                and result["pages"][-1]["name"] == args.expected_page
                and result["pages"][-1]["visible"] is True
            )
        ))
    except BaseException as exc:
        result["error"] = type(exc).__name__ + ": " + str(exc)
        result["passed"] = False
    finally:
        if profiler is not None:
            profiler.disable()
            profile_path.parent.mkdir(parents=True, exist_ok=True)
            profiler.dump_stats(str(profile_path))
        if instance is not None:
            device = instance.__dict__.get("device")
            session = getattr(device, "__dict__", {}).get("semantic_adapter")
            if session is not None:
                session.close()
        os.chdir(prior_cwd)
        config_path.unlink(missing_ok=True)
        result["temporary_config_removed"] = not config_path.exists()
        for key, value in previous_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in result.items() if key != "pages"}, ensure_ascii=False))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
