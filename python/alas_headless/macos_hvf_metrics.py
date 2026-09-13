"""Optional account-free macOS metrics; unavailable values are never zero-filled."""

from __future__ import annotations

import math
import re
from typing import Any, Mapping, Optional

from .runtime_command import RuntimeCommandExecutor, RuntimeCommandSpec


def parse_processes(output: str, root_pid: int) -> Mapping[str, Any]:
    rows = {}
    for line in output.splitlines():
        parts = line.split()
        if len(parts) != 4:
            raise ValueError("malformed process row")
        pid, parent, cpu, rss = int(parts[0]), int(parts[1]), float(parts[2]), int(parts[3])
        if pid <= 0 or parent < 0 or rss < 0 or not math.isfinite(cpu) or cpu < 0:
            raise ValueError("invalid process values")
        rows[pid] = (parent, cpu, rss)
    if root_pid not in rows:
        raise ValueError("emulator process absent")
    selected = {root_pid}
    while True:
        children = {pid for pid, row in rows.items() if row[0] in selected}
        expanded = selected | children
        if expanded == selected:
            break
        selected = expanded
    return {
        "root_pid": root_pid,
        "process_count": len(selected),
        "cpu_percent_ps": sum(rows[pid][1] for pid in selected),
        "rss_bytes_sum": sum(rows[pid][2] * 1024 for pid in selected),
    }


def collect_metrics(executor: RuntimeCommandExecutor, root_pid: Optional[int]) -> Mapping[str, Any]:
    values: dict[str, Any] = {"schema": "alas-headless.macos-hvf-metrics/v1"}
    errors = {}

    def read(name, argv, parse):
        try:
            result = executor.run(RuntimeCommandSpec("macos-hvf-metrics-" + name, argv, timeout_seconds=5.0, environment={"LC_ALL": "C"}))
            if not result.succeeded:
                raise ValueError("command unavailable")
            values[name] = parse(result.stdout)
        except (ValueError, OSError, RuntimeError):
            values[name] = None
            errors[name] = "unavailable-or-malformed"

    def swap(text):
        match = re.search(r"used\s*=\s*([0-9.]+)([KMGT])", text)
        if match is None:
            raise ValueError("swap used missing")
        value = float(match[1])
        if not math.isfinite(value) or value < 0:
            raise ValueError("invalid swap used")
        return int(value * 1024 ** ("KMGT".index(match[2]) + 1))

    def vm(text):
        match = re.search(r"page size of (\d+) bytes", text)
        if match is None:
            raise ValueError("page size missing")
        counters = {key: int(value) for key, value in re.findall(r"^([^:\n]+):\s+(\d+)\.", text, re.M)}
        if not counters:
            raise ValueError("VM counters missing")
        return {"page_size_bytes": int(match[1]), "counters_pages": counters}

    read("host_memory_bytes", ("/usr/sbin/sysctl", "-n", "hw.memsize"), lambda text: int(text.strip()))
    read("host_swap_used_bytes", ("/usr/sbin/sysctl", "-n", "vm.swapusage"), swap)
    read("host_vm", ("/usr/bin/vm_stat",), vm)
    if root_pid is None:
        values["emulator"] = None
        errors["emulator"] = "no-owned-process"
    else:
        read("emulator", ("/bin/ps", "-axo", "pid=,ppid=,%cpu=,rss="), lambda text: parse_processes(text, root_pid))
    values["errors"] = errors
    return values
