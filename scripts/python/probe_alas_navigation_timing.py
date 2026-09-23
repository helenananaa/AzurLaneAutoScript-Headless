"""Profile bounded native ALAS main/settings navigation with typed input only."""

from __future__ import annotations

import argparse
import copy
import json
import os
import sys
import time
import uuid
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--alas-root", type=Path, required=True)
    parser.add_argument("--serial", required=True)
    parser.add_argument("--driver-revision", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--pairs", type=int, choices=(1, 2, 3), default=3)
    args = parser.parse_args()
    alas_root, output = args.alas_root.resolve(), args.output.resolve()
    previous_cwd = Path.cwd()
    seed = json.loads((alas_root / "config/semantic_e2e.json").read_text(encoding="utf-8"))
    config = copy.deepcopy(seed)
    config["Alas"]["Emulator"]["Serial"] = args.serial
    config["Alas"]["Error"].update(HandleError=False, SaveError=False)
    name = "codex_navigation_timing_" + uuid.uuid4().hex
    config_path = alas_root / "config" / (name + ".json")
    config_path.write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")
    sys.path[:0] = [str(ROOT / "python"), str(alas_root)]
    environment = {
        "ALAS_SEMANTIC_MODE": "1", "ALAS_SEMANTIC_ADB": "adb",
        "ALAS_SEMANTIC_DRIVER_REVISION": args.driver_revision,
    }
    result = dict(serial=args.serial, driver_revision=args.driver_revision,
                  package=config["Alas"]["Emulator"]["PackageName"],
                  pairs=args.pairs, maximum_taps=2 * args.pairs + 2,
                  phases=[], spans=[], passed=False)
    session = None
    phase = "setup"
    origin = time.perf_counter()
    taps = 0

    def instrument(owner, method, category):
        original = getattr(owner, method)

        def measured(*a, **kw):
            nonlocal taps
            kind = category(*a, **kw) if callable(category) else category
            if kind == "adb.tap":
                if taps >= result["maximum_taps"]:
                    raise RuntimeError("navigation probe tap budget exhausted")
                taps += 1
            started = time.perf_counter()
            success = False
            try:
                value = original(*a, **kw)
                success = True
                return value
            finally:
                result["spans"].append(dict(phase=phase, kind=kind,
                    start_seconds=started-origin, seconds=time.perf_counter()-started,
                    success=success))
        return patch.object(owner, method, measured)

    def run_phase(label, operation):
        nonlocal phase
        phase = label
        started = time.perf_counter()
        try:
            return operation()
        finally:
            result["phases"].append(dict(name=label, seconds=time.perf_counter()-started))

    def adb_category(_bridge, arguments, **_kw):
        if tuple(arguments[:3]) == ("shell", "dumpsys", "activity"):
            return "adb.foreground"
        if tuple(arguments[:3]) == ("shell", "input", "tap"):
            return "adb.tap"
        return "adb.other"

    try:
        with patch.dict(os.environ, environment), ExitStack() as stack:
            os.chdir(alas_root)
            from alas import AzurLaneAutoScript
            from module.daemon.benchmark import Benchmark
            from alas_headless.adapter.frame import SemanticFrameClock
            from alas_headless.oracle.actions import ActionsOracle
            from alas_headless.oracle.transport import AdbObserverBridge, TcpObserverTransport

            stack.enter_context(instrument(AdbObserverBridge, "_run", adb_category))
            stack.enter_context(instrument(TcpObserverTransport, "request",
                lambda _self, request_line: "observer." + request_line.split()[1]))
            stack.enter_context(instrument(SemanticFrameClock, "acquire", "frame.acquire"))
            stack.enter_context(instrument(ActionsOracle, "wait_for", "postcondition.wait"))
            stack.enter_context(instrument(time, "sleep", "sleep"))
            instance = AzurLaneAutoScript(name)
            instance.config.bind("Benchmark")
            task = Benchmark(instance.config, device=instance.device, task="Benchmark")
            session = instance.device.semantic_adapter
            session.refresh_frame()
            oracle = session.open().oracle
            # CoreOracle captures its default sleep callable at import time,
            # before time.sleep instrumentation above is installed.
            stack.enter_context(instrument(oracle, "_sleep", "oracle.sleep"))
            reader = session._frame_reader.oracle()
            if reader.observation_target_present("shop/home") and reader.recommendation_shop_visible():
                result["start_page"] = "shop"
                run_phase("prepare.shop_to_main", oracle.click_recommendation_shop_home)
                run_phase("prepare.wait_main", lambda: oracle.wait_for("main/settings", 5.0))
            elif reader.main_page_visible():
                result["start_page"] = "main"
            else:
                raise RuntimeError("probe requires a proven main or shop page")
            result["pid"] = session.runtime_handle.pid
            for index in range(2 * args.pairs):
                run_phase("sample." + str(index + 1), task.semantic_reversible_input)
            run_phase("verify.main", task.semantic_ensure_main)
            if result["start_page"] == "shop":
                def restore():
                    session.refresh_frame()
                    oracle.click("main/shop")
                    # Shop home is a reviewed image-backed control; generic
                    # Button.actionable is not its page-identity contract.
                    deadline = time.monotonic() + 5.0
                    while time.monotonic() < deadline:
                        session.refresh_frame()
                        if session._frame_reader.oracle().recommendation_shop_visible():
                            return
                        time.sleep(0.1)
                    raise RuntimeError("shop restoration was not confirmed")
                run_phase("restore.shop", restore)
            result["restored"] = True
            result["passed"] = True
    except Exception as exc:
        result["error"] = type(exc).__name__ + ": " + str(exc)
    finally:
        if session is not None:
            session.close()
        os.chdir(previous_cwd)
        config_path.unlink(missing_ok=True)
        result["taps_attempted"] = taps
        result["temporary_config_removed"] = not config_path.exists()
        result["timing_note"] = "Spans are inclusive and nested; frame/wait must not be added to their ADB/observer children."
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k != "spans"}, ensure_ascii=False))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
