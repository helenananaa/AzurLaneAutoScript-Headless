#!/usr/bin/env python3
"""Read-only, account-free resource sampling of an identified WSL container.

CPU percentages use one logical CPU = 100%; memory.current includes file cache.
No launch, navigation, settings changes, or observer requests are performed.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import time


SNAPSHOT = r'''cat /proc/uptime
echo CPU
cat /sys/fs/cgroup/cpu.stat
echo MEMORY
cat /sys/fs/cgroup/memory.current /sys/fs/cgroup/memory.stat
echo IO
cat /sys/fs/cgroup/io.stat
echo PROCESSES
for p in /proc/[0-9]*/stat; do
    if read -r line < "$p" 2>/dev/null; then printf '%s\n' "$line"; fi
done
'''


def parse_snapshot(raw):
    uptime, rest = raw.split("\nCPU\n", 1)
    cpu, rest = rest.split("\nMEMORY\n", 1)
    memory, rest = rest.split("\nIO\n", 1)
    io, processes = rest.split("PROCESSES\n", 1)
    memory_lines = memory.splitlines()
    parsed = {}
    for line in processes.splitlines():
        # comm can contain spaces and parentheses. Fields after the final ')'
        # begin at Linux proc_pid_stat field 3 (state).
        try:
            left, fields = line.rsplit(") ", 1)
            pid, name = left.split(" (", 1)
            fields = fields.split()
            parsed[pid] = {"name": name, "ticks": int(fields[11]) + int(fields[12]),
                           "start_ticks": int(fields[19]), "rss_pages": int(fields[21])}
        except (ValueError, IndexError):
            continue  # A process may exit during the read.
    return {"uptime": float(uptime.split()[0]),
            "cpu": {k: int(v) for k, v in (line.split() for line in cpu.splitlines())},
            "memory_bytes": int(memory_lines[0]),
            "memory": {k: int(v) for k, v in (line.split() for line in memory_lines[1:])},
            "io_raw": io, "processes": parsed}


def interval(before, after, hz):
    elapsed = after["uptime"] - before["uptime"]
    if elapsed <= 0:
        raise ValueError("non-increasing sample time")
    processes = []
    for pid, current in after["processes"].items():
        previous = before["processes"].get(pid)
        if previous is None or previous["start_ticks"] != current["start_ticks"]:
            continue  # Partial lifetimes are not comparable; container CPU includes them.
        processes.append({"pid": pid, "name": current["name"],
                          "cpu_percent": 100 * (current["ticks"] - previous["ticks"]) / hz / elapsed})
    return {"seconds": elapsed,
            "cpu_percent": (after["cpu"]["usage_usec"] - before["cpu"]["usage_usec"]) / elapsed / 10000,
            "top_processes": sorted(processes, key=lambda p: p["cpu_percent"], reverse=True)[:12]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--phase", required=True)
    parser.add_argument("--seconds", type=int, default=60)
    parser.add_argument("--interval", type=int, default=10)
    args = parser.parse_args()
    if args.seconds < 1 or args.interval < 1:
        parser.error("sampling duration and interval must be positive")
    config = json.loads(args.config.read_text(encoding="utf-8-sig"))
    from alas_headless.runtime_backends import backend_from_config, WslRedroidBackend
    from alas_headless.runtime_command import RuntimeCommandExecutor, RuntimeExecutionPolicy
    backend = backend_from_config(config, RuntimeCommandExecutor(RuntimeExecutionPolicy(True, False)))
    if not isinstance(backend, WslRedroidBackend):
        parser.error("WSL Redroid configuration required")
    backend._validate_container_and_userdata()
    identity = backend._container_info()
    if not identity["State"]["Running"]:
        parser.error("selected container is stopped")
    command = [config.get("wsl", "wsl.exe"), "-d", config["distro"], "--", "docker",
               "--host", "unix:///var/run/docker.sock", "exec", config["container_id"]]

    def run(tail, script=None):
        argv = command + tail if script is None else command[:-1] + ["-i", command[-1]] + tail
        result = subprocess.run(argv, input=None if script is None else script.encode("utf-8"),
                                capture_output=True, timeout=30)
        if result.returncode:
            raise RuntimeError(result.stderr.decode("utf-8", errors="replace"))
        return result.stdout.decode("utf-8")

    args.output.mkdir(parents=True, exist_ok=False)
    hz = int(run(["getconf", "CLK_TCK"]).strip())
    report = {"schema": "alas-headless.redroid-resource-sample/v1", "phase": args.phase,
              "captured_at_utc": datetime.now(timezone.utc).isoformat(),
              "sampler_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              "container_id": identity["Id"], "image": identity["Image"],
              "started_at": identity["State"]["StartedAt"], "clock_ticks": hz,
              "cpu_convention": "100 percent equals one logical CPU",
              "account_inputs": 0, "samples": [], "intervals": [], "complete": False}
    deadline = None
    while True:
        raw = run(["sh"], SNAPSHOT)
        index = len(report["samples"])
        (args.output / f"sample-{index:03}.txt").write_text(raw, encoding="utf-8")
        current = parse_snapshot(raw)
        if deadline is None:
            deadline = time.monotonic() + args.seconds
        if report["samples"]:
            report["intervals"].append(interval(report["samples"][-1], current, hz))
        report["samples"].append(current)
        (args.output / "manifest.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        if time.monotonic() >= deadline:
            break
        time.sleep(min(args.interval, max(0, deadline - time.monotonic())))
    after = backend._container_info()
    if (after["Id"], after["State"]["StartedAt"], after["State"]["Running"]) != (
            identity["Id"], identity["State"]["StartedAt"], True):
        raise RuntimeError("container changed during sampling")
    report["complete"] = True
    report["whole_window"] = interval(report["samples"][0], report["samples"][-1], hz)
    (args.output / "manifest.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report["whole_window"], indent=2), flush=True)


if __name__ == "__main__":
    main()
