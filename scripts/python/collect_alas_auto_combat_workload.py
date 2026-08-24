#!/usr/bin/env python3
"""Collect one official-auto campaign run without screenshot polling.

The collector reuses the bounded Main live runner and attaches the repository's
existing asynchronous runtime trace to the semantic session.  It samples host
and guest process counters on a separate, low-frequency thread.  It does not
capture screenshots or add observer requests beyond those issued by ALAS.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import subprocess
import sys
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path
from types import ModuleType
from typing import Any, Callable, Mapping, Optional, Sequence

import psutil


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "python") not in sys.path:
    sys.path.insert(0, str(ROOT / "python"))

from alas_headless import (  # noqa: E402
    AlasSemanticSession,
    RuntimeProcessSample,
    RuntimeTraceRecorder,
    SemanticOracle,
    summarize_runtime_trace,
)
from alas_headless.adb_device import resolve_adb_serial  # noqa: E402


SCHEMA = "alas-headless.auto-combat-workload-capture/v1"
PACKAGE = "com.bilibili.azurlane"
_SERIAL_PORT = re.compile(r"^emulator-([1-9][0-9]*)$")
_MEMINFO_TOTAL = re.compile(
    r"TOTAL PSS:\s*([0-9]+)\s+TOTAL RSS:\s*([0-9]+)\s+TOTAL SWAP PSS:\s*([0-9]+)"
)
_TRACED_ACTION_METHODS = (
    "click",
    "click_toggle",
    "click_campaign_mode_switch",
    "click_campaign_chapter",
    "click_campaign_map_preparation",
    "cancel_campaign_map_preparation",
    "click_campaign_hard_recommend",
    "cancel_campaign_fleet_preparation",
    "click_campaign_sortie",
    "click_campaign_auto_search_sortie",
    "click_campaign_stage",
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _load_main_runner() -> ModuleType:
    path = ROOT / "scripts" / "python" / "run_alas_main_task_live_validation.py"
    spec = importlib.util.spec_from_file_location("alas_main_live_runner", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Main live runner could not be loaded")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run_command(
    command: Sequence[str], *, timeout_seconds: float = 5.0
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(command),
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
    )


def _git_identity() -> Mapping[str, Any]:
    commit = _run_command(("git", "rev-parse", "HEAD"))
    status = _run_command(("git", "status", "--porcelain"))
    return {
        "commit": commit.stdout.strip() if commit.returncode == 0 else None,
        "dirty": bool(status.stdout.strip()) if status.returncode == 0 else None,
    }


def _emulator_port(serial: str) -> Optional[int]:
    match = _SERIAL_PORT.fullmatch(serial)
    return int(match.group(1)) if match is not None else None


def discover_host_runtime_pid(serial: str) -> Optional[int]:
    """Find the qemu process that owns the explicitly selected emulator port."""

    port = _emulator_port(serial)
    if port is None:
        return None
    matches = []
    for process in psutil.process_iter(("pid", "name", "cmdline")):
        try:
            name = (process.info.get("name") or "").lower()
            arguments = tuple(process.info.get("cmdline") or ())
        except (psutil.AccessDenied, psutil.NoSuchProcess):
            continue
        if not name.startswith("qemu-system-"):
            continue
        for index, argument in enumerate(arguments[:-1]):
            if argument == "-port" and arguments[index + 1] == str(port):
                matches.append(int(process.info["pid"]))
                break
    return matches[0] if len(matches) == 1 else None


def parse_guest_process_sample(
    output: str, *, clock_ticks: int, page_size: int
) -> tuple[int, RuntimeProcessSample, Mapping[str, int]]:
    """Parse one bounded /proc sample emitted by the collector's ADB shell."""

    lines = [line.strip() for line in output.splitlines() if line.strip()]
    if len(lines) < 2 or not lines[0].startswith("PID:"):
        raise ValueError("guest process sample has no PID")
    pid_text = lines[0][4:].strip()
    if not pid_text.isdigit():
        raise ValueError("guest process sample PID is malformed")
    stat_line = lines[1]
    close = stat_line.rfind(")")
    if close < 0:
        raise ValueError("guest process stat is malformed")
    fields = stat_line[close + 2 :].split()
    if len(fields) < 22:
        raise ValueError("guest process stat is truncated")
    user_ticks = int(fields[11])
    system_ticks = int(fields[12])
    rss_pages = int(fields[21])
    details: dict[str, int] = {}
    for line in lines[2:]:
        if ":" not in line:
            continue
        key, raw = line.split(":", 1)
        token = raw.strip().split()[0]
        if token.isdigit():
            details[key] = int(token)
    rss_bytes = details.get("VmRSS", rss_pages * page_size // 1024) * 1024
    cpu_time_ns = (user_ticks + system_ticks) * 1_000_000_000 // clock_ticks
    return (
        int(pid_text),
        RuntimeProcessSample(
            scope="game",
            cpu_time_ns=cpu_time_ns,
            rss_bytes=rss_bytes,
        ),
        details,
    )


def parse_meminfo_totals(output: str) -> Mapping[str, int]:
    match = _MEMINFO_TOTAL.search(output)
    if match is None:
        raise ValueError("game meminfo totals are unavailable")
    pss_kib, rss_kib, swap_pss_kib = (int(item) for item in match.groups())
    return {
        "pss_bytes": pss_kib * 1024,
        "rss_bytes": rss_kib * 1024,
        "swap_pss_bytes": swap_pss_kib * 1024,
    }


@dataclass
class ProcessSamplerSummary:
    host_runtime_pid: Optional[int]
    samples: int = 0
    guest_failures: int = 0
    host_failures: int = 0
    controller_failures: int = 0

    def fields(self) -> Mapping[str, Any]:
        return {
            "host_runtime_pid": self.host_runtime_pid,
            "samples": self.samples,
            "guest_failures": self.guest_failures,
            "host_failures": self.host_failures,
            "controller_failures": self.controller_failures,
        }


class ProcessSampler:
    def __init__(
        self,
        *,
        trace: RuntimeTraceRecorder,
        serial: str,
        adb: str,
        package: str,
        interval_seconds: float,
        command_runner: Callable[..., subprocess.CompletedProcess[str]] = _run_command,
    ) -> None:
        self.trace = trace
        self.serial = serial
        self.adb = adb
        self.package = package
        self.interval_seconds = interval_seconds
        self.command_runner = command_runner
        self.summary = ProcessSamplerSummary(discover_host_runtime_pid(serial))
        self._stop = threading.Event()
        self._thread = threading.Thread(
            target=self._loop, name="alas-workload-process-sampler", daemon=True
        )
        self._clock_ticks = self._guest_constant("CLK_TCK")
        self._page_size = self._guest_constant("PAGESIZE")
        self._host_process = (
            psutil.Process(self.summary.host_runtime_pid)
            if self.summary.host_runtime_pid is not None
            else None
        )
        self._controller_process = psutil.Process(os.getpid())

    def _guest_constant(self, name: str) -> int:
        completed = self.command_runner(
            (self.adb, "-s", self.serial, "shell", "getconf", name),
            timeout_seconds=5.0,
        )
        value = completed.stdout.strip()
        if completed.returncode != 0 or not value.isdigit() or int(value) <= 0:
            raise RuntimeError("guest process constant is unavailable: " + name)
        return int(value)

    @staticmethod
    def _psutil_fields(process: psutil.Process) -> Mapping[str, int]:
        cpu = process.cpu_times()
        memory = process.memory_info()
        fields: dict[str, int] = {
            "cpu_time_ns": int((cpu.user + cpu.system) * 1_000_000_000),
            "rss_bytes": int(memory.rss),
        }
        try:
            io = process.io_counters()
        except (psutil.AccessDenied, psutil.NoSuchProcess):
            return fields
        fields["read_bytes"] = int(io.read_bytes)
        fields["write_bytes"] = int(io.write_bytes)
        return fields

    def _sample_host(self) -> None:
        if self._host_process is None:
            return
        fields = self._psutil_fields(self._host_process)
        self.trace.process_sample(
            RuntimeProcessSample(scope="host-runtime", **fields)
        )

    def _sample_controller(self) -> None:
        self.trace.emit(
            "runtime.controller.process.sample",
            fields=self._psutil_fields(self._controller_process),
        )

    def _sample_guest(self) -> None:
        # The command string is passed as one argument to `adb shell`; it is not
        # interpreted by the Windows host shell.
        shell_command = (
            "p=$(pidof "
            + self.package
            + "); test -n \"$p\" || exit 3; "
            + "echo PID:$p; cat /proc/$p/stat; "
            + "grep -E '^(VmRSS|VmHWM|Threads):' /proc/$p/status"
        )
        completed = self.command_runner(
            (self.adb, "-s", self.serial, "shell", shell_command),
            timeout_seconds=min(10.0, max(3.0, self.interval_seconds * 2.0)),
        )
        if completed.returncode != 0:
            raise RuntimeError("guest process sample command failed")
        pid, sample, details = parse_guest_process_sample(
            completed.stdout,
            clock_ticks=self._clock_ticks,
            page_size=self._page_size,
        )
        self.trace.process_sample(sample)
        self.trace.emit(
            "runtime.game.process.identity",
            fields={
                "pid": pid,
                "threads": details.get("Threads"),
                "vm_hwm_bytes": (
                    details["VmHWM"] * 1024 if "VmHWM" in details else None
                ),
            },
        )

    def _loop(self) -> None:
        while not self._stop.is_set():
            started = time.monotonic()
            try:
                self._sample_host()
            except (psutil.Error, OSError, ValueError):
                self.summary.host_failures += 1
            try:
                self._sample_controller()
            except (psutil.Error, OSError, ValueError):
                self.summary.controller_failures += 1
            try:
                self._sample_guest()
            except (OSError, RuntimeError, ValueError, subprocess.SubprocessError):
                self.summary.guest_failures += 1
            self.summary.samples += 1
            remaining = self.interval_seconds - (time.monotonic() - started)
            self._stop.wait(max(0.0, remaining))

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> Mapping[str, Any]:
        self._stop.set()
        self._thread.join(max(5.0, self.interval_seconds * 3.0))
        return self.summary.fields()

    def capture_meminfo(self, phase: str) -> Optional[Mapping[str, int]]:
        pid = self.command_runner(
            (self.adb, "-s", self.serial, "shell", "pidof", self.package),
            timeout_seconds=5.0,
        ).stdout.strip()
        if not pid.isdigit():
            return None
        completed = self.command_runner(
            (self.adb, "-s", self.serial, "shell", "dumpsys", "meminfo", pid),
            timeout_seconds=30.0,
        )
        if completed.returncode != 0:
            return None
        try:
            fields = dict(parse_meminfo_totals(completed.stdout))
        except ValueError:
            return None
        fields.update({"pid": int(pid), "phase": phase})
        self.trace.emit("runtime.game.meminfo", fields=fields)
        return fields


def _install_trace_hooks(trace: RuntimeTraceRecorder) -> Callable[[], None]:
    original_from_environment = AlasSemanticSession.__dict__["from_environment"]
    original_factory = original_from_environment.__func__
    original_action_methods = {
        name: getattr(SemanticOracle, name) for name in _TRACED_ACTION_METHODS
    }
    original_auto_start = AlasSemanticSession.confirm_campaign_auto_search_started
    original_auto_completion = AlasSemanticSession.wait_campaign_auto_search_completion

    def traced_from_environment(
        cls: type[AlasSemanticSession],
        serial: str,
        *,
        run_policy: Any = None,
        trace: Optional[RuntimeTraceRecorder] = None,
    ) -> AlasSemanticSession:
        del trace
        return original_factory(
            cls,
            serial,
            run_policy=run_policy,
            trace=collector_trace,
        )

    def action_wrapper(
        method_name: str, original: Callable[..., Any]
    ) -> Callable[..., Any]:
        @wraps(original)
        def traced_action(oracle: SemanticOracle, *args: Any, **kwargs: Any) -> Any:
            started = time.monotonic_ns()
            try:
                receipt = original(oracle, *args, **kwargs)
            except BaseException as exc:
                fields = {
                    "method": "SemanticOracle." + method_name,
                    "exception_type": type(exc).__name__,
                }
                if method_name in ("click", "click_toggle") and args:
                    fields["requested_semantic_id"] = str(args[0])
                trace.emit(
                    "alas.action",
                    outcome="error",
                    duration_ns=max(0, time.monotonic_ns() - started),
                    fields=fields,
                )
                raise
            trace.emit(
                "alas.action",
                duration_ns=max(0, time.monotonic_ns() - started),
                fields={
                    "method": "SemanticOracle." + method_name,
                    "semantic_id": receipt.semantic_id,
                    "receipt_generation": receipt.generation,
                },
            )
            return receipt

        return traced_action

    @wraps(original_auto_start)
    def traced_auto_start(session: AlasSemanticSession, *args: Any, **kwargs: Any) -> Any:
        proof = original_auto_start(session, *args, **kwargs)
        trace.emit(
            "alas.phase",
            fields={
                "phase": "official-auto-start",
                "stage_code": proof.stage_code,
                "sortie_generation": proof.sortie_generation,
                "map_generation": proof.map_generation,
                "map_root_path": proof.map_root_path,
            },
        )
        return proof

    @wraps(original_auto_completion)
    def traced_auto_completion(
        session: AlasSemanticSession, *args: Any, **kwargs: Any
    ) -> Any:
        proof = original_auto_completion(session, *args, **kwargs)
        trace.emit(
            "alas.phase",
            fields={
                "phase": "official-auto-complete",
                "stage_code": proof.stage_code,
                "result_generation": proof.result_generation,
                "result_path": proof.result_path,
                "waited_seconds": proof.waited_seconds,
            },
        )
        return proof

    collector_trace = trace
    AlasSemanticSession.from_environment = classmethod(traced_from_environment)
    for method_name, original in original_action_methods.items():
        setattr(SemanticOracle, method_name, action_wrapper(method_name, original))
    AlasSemanticSession.confirm_campaign_auto_search_started = traced_auto_start
    AlasSemanticSession.wait_campaign_auto_search_completion = (
        traced_auto_completion
    )

    def restore() -> None:
        AlasSemanticSession.from_environment = original_from_environment
        for method_name, original in original_action_methods.items():
            setattr(SemanticOracle, method_name, original)
        AlasSemanticSession.confirm_campaign_auto_search_started = original_auto_start
        AlasSemanticSession.wait_campaign_auto_search_completion = (
            original_auto_completion
        )

    return restore


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def collect(args: argparse.Namespace) -> Mapping[str, Any]:
    output = args.output_directory.resolve()
    output.mkdir(parents=True, exist_ok=False)
    run_id = uuid.uuid4().hex
    trace_path = output / "runtime-trace.jsonl"
    trace = RuntimeTraceRecorder(trace_path, enabled=True, run_id=run_id)
    sampler = ProcessSampler(
        trace=trace,
        serial=args.serial,
        adb=args.adb,
        package=PACKAGE,
        interval_seconds=args.sample_interval_seconds,
    )
    restore = _install_trace_hooks(trace)
    main_runner = _load_main_runner()
    runner_args = argparse.Namespace(
        alas_root=args.alas_root.resolve(),
        serial=args.serial,
        driver_revision=args.driver_revision,
        adb=args.adb,
        seed_config=args.seed_config,
        task="Main",
        stage="12-4",
        use_auto_search=True,
        fleet_order="fleet1_mob_fleet2_boss",
        combat_budget=0,
        viewport_swipe_budget=0,
        output=None,
    )
    started_at = _utc_now()
    started_monotonic_ns = time.monotonic_ns()
    pre_meminfo = sampler.capture_meminfo("before")
    sampler.start()
    runner_result: Optional[Mapping[str, Any]] = None
    failure: Optional[BaseException] = None
    sampler_summary: Mapping[str, Any] = {}
    try:
        runner_result = main_runner.run(runner_args)
    except BaseException as exc:
        failure = exc
    finally:
        sampler_summary = sampler.stop()
        post_meminfo = sampler.capture_meminfo("after")
        restore()
        trace_summary_before_close = trace.summary()
        trace_close = trace.close()

    result = {
        "schema": SCHEMA,
        "passed": bool(runner_result and runner_result.get("passed")) and failure is None,
        "run_id": run_id,
        "started_at": started_at,
        "finished_at": _utc_now(),
        "duration_ns": max(0, time.monotonic_ns() - started_monotonic_ns),
        "source": _git_identity(),
        "workload": {
            "task": "Main",
            "stage": "12-4",
            "event": "campaign_main",
            "mode": "normal",
            "use_auto_search": True,
            "fleet_order": "fleet1_mob_fleet2_boss",
        },
        "device": {
            "serial": args.serial,
            "package": PACKAGE,
            "driver_revision": args.driver_revision,
        },
        "sampling": {
            "interval_seconds": args.sample_interval_seconds,
            "observer_sidecar_used": False,
            "screenshots_captured": False,
            "pre_meminfo": pre_meminfo,
            "post_meminfo": post_meminfo,
            "process_sampler": sampler_summary,
        },
        "runner_result": runner_result,
        "failure": (
            {"type": type(failure).__name__, "message": str(failure)[:500]}
            if failure is not None
            else None
        ),
        "trace": {
            "path": str(trace_path),
            "before_close": trace_summary_before_close,
            "after_close": trace_close,
            "summary": summarize_runtime_trace(trace_path),
        },
        "raw_input_fallback_used": False,
    }
    _write_json(output / "result.json", result)
    if failure is not None:
        raise failure
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--alas-root", required=True, type=Path)
    parser.add_argument("--output-directory", required=True, type=Path)
    parser.add_argument("--serial")
    parser.add_argument("--driver-revision", required=True)
    parser.add_argument("--adb", default="adb")
    parser.add_argument("--seed-config", default="semantic_e2e")
    parser.add_argument("--sample-interval-seconds", type=float, default=1.0)
    args = parser.parse_args()
    if not 0.5 <= args.sample_interval_seconds <= 10.0:
        parser.error("sample interval must be in [0.5, 10]")
    if not (args.alas_root / "alas.py").is_file():
        parser.error("ALAS root is invalid")
    args.serial = resolve_adb_serial(args.adb, args.serial)
    return args


def main() -> int:
    args = parse_args()
    result = collect(args)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
