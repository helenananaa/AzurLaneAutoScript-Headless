#!/usr/bin/env python3
"""Controlled fault -> original ALAS navigation -> original Reward task.

Reward collection is disabled because this experiment qualifies task boundaries,
not resource collection. All navigation and login belong to original ALAS.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import sys
import time
import traceback

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--alas-root", type=Path, required=True)
    parser.add_argument("--seed-config", type=Path, required=True)
    parser.add_argument("--serial", required=True)
    parser.add_argument("--driver-revision", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    source = args.alas_root.resolve()
    config = copy.deepcopy(json.loads(args.seed_config.read_text(encoding="utf-8")))
    config["Alas"]["Emulator"]["Serial"] = args.serial
    config["Alas"]["Error"].update(HandleError=False, SaveError=False)
    config["Reward"]["Reward"].update(
        CollectOil=False, CollectCoin=False, CollectExp=False,
        CollectMission=False, CollectWeeklyMission=False,
    )
    config_name = "codex_task_isolation_" + str(time.time_ns())
    config_path = source / "config" / (config_name + ".json")
    config_path.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    sys.path[:0] = [str(ROOT / "python"), str(source)]
    os.environ.update(ALAS_SEMANTIC_MODE="1", ALAS_SEMANTIC_DRIVER_REVISION=args.driver_revision,
                      ALAS_SEMANTIC_ADB="adb")
    os.chdir(source)
    from alas import AzurLaneAutoScript
    from module.config.config import name_to_function
    from module.handler.login import LoginHandler
    from module.ui.ui import UI
    from module.ui.page import page_mission
    from alas_headless import AlasSemanticUnmapped
    from alas_headless.semantic_sources import semantic_source_hashes

    app = AzurLaneAutoScript(config_name)
    task = name_to_function("Reward")
    app.config.task = task
    app.config.bind(task)
    result = {
        "schema": "alas-headless.task-isolation-live/v1", "passed": False,
        "serial": args.serial, "driver_revision": args.driver_revision,
        "reward_options": config["Reward"]["Reward"], "steps": [],
        "config_name": config_name, "resource_collection_qualified": False,
        "source_sha256": semantic_source_hashes(ROOT),
        "alas_py_sha256": hashlib.sha256((source / "alas.py").read_bytes()).hexdigest(),
        "patch_sha256": hashlib.sha256((ROOT / "integration/alas/0001-semantic-oracle-hooks.patch").read_bytes()).hexdigest(),
        "runner_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    }
    session = None
    started = time.monotonic()
    try:
        session = app.device.semantic_adapter
        adapter = session.open()
        oracle = adapter.oracle
        original_tap = oracle._tap
        def bounded_tap(x, y):
            # This live experiment needs about six navigation inputs. Stop a
            # routing regression from becoming an indefinite toggle loop.
            if oracle.input_dispatch_count >= 12:
                raise RuntimeError("task-isolation experiment reached 12 navigation inputs")
            return original_tap(x, y)
        oracle._tap = bounded_tap
        before = oracle.read_state()
        result["runtime"] = {key: before.snapshot[key] for key in ("package", "pid", "driver_revision", "abi")}
        ui = oracle.read_text_state()
        result["selected_server"] = [t.text for t in ui.texts if t.path.endswith("/current_server/server_name") and t.active_in_hierarchy]
        result["initial_generation"] = before.generation

        def step(name):
            initial_inputs = oracle.input_dispatch_count
            outcome = app.run(name, skip_first_screenshot=(name == "login_probe"))
            state = oracle.read_state()
            record = {
                "name": name, "return": outcome, "task_outcome": dict(session.last_task_outcome),
                "generation": state.generation, "pid": state.snapshot["pid"],
                "input_count": oracle.input_dispatch_count - initial_inputs,
                "main_visible": oracle.main_page_visible(),
                "mission_context_released": adapter._mission_context is None,
                "frame_released": session._frame_clock.current_frame_id is None,
            }
            result["steps"].append(record)
            return outcome

        app.login_probe = lambda: LoginHandler(app.config, device=app.device).handle_app_login()
        assert step("login_probe") is True

        def fault_probe():
            session.begin_mission_reward(daily=False, weekly=False)
            UI(app.config, device=app.device).ui_ensure(page_mission)
            result["fault_generation"] = oracle.read_state().generation
            raise AlasSemanticUnmapped("controlled optional-capability fault on a known mission page")
        app.fault_probe = fault_probe
        assert step("fault_probe") is None
        assert "fault_generation" in result, "the controlled fault was not reached"
        assert adapter._mission_context is None
        assert step("goto_main") is True
        assert oracle.main_page_visible()
        assert step("reward") is True
        assert oracle.main_page_visible()
        assert not oracle.enabled("reward/page/back")
        assert app.device.semantic_adapter is session and session.open() is adapter
        assert all(s["mission_context_released"] and s["frame_released"] for s in result["steps"])
        assert {s["pid"] for s in result["steps"]} == {result["runtime"]["pid"]}
        result["input_count"] = sum(s["input_count"] for s in result["steps"])
        result["same_session"] = True
        result["source_unchanged"] = semantic_source_hashes(ROOT) == result["source_sha256"]
        assert result["source_unchanged"]
        result["passed"] = True
    except BaseException as exc:
        result["error"] = {"type": type(exc).__name__, "message": str(exc), "traceback": traceback.format_exc()}
    finally:
        if session is not None:
            session.close()
        result["elapsed_seconds"] = round(time.monotonic() - started, 3)
        (output / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: result[key] for key in ("passed", "steps", "elapsed_seconds")}, ensure_ascii=False, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
