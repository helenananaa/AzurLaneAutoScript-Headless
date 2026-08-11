"""Fail-closed Android foundation capability and idle-metric helpers."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, Mapping, Sequence, Tuple

from .android_image_policy import REQUIRED_PROTECTED_CAPABILITIES
from .android_update_lab import AdbClient, AndroidUpdateLabError


AUDIT_SCHEMA = "alas-headless.android-foundation-audit/v1"
CPU_LINE = re.compile(r"^cpu\s+((?:\d+\s+){3,}\d+)", re.MULTILINE)
TOTAL_PSS = re.compile(r"^\s*Total RAM:\s+([\d,]+)K", re.MULTILINE)
RAM_VALUE = re.compile(r"^\s*(Used|Free) RAM:\s+([\d,]+)K", re.MULTILINE)


@dataclass(frozen=True)
class CapabilityProbe:
    capability: str
    command: Tuple[str, ...]
    required_text: Tuple[str, ...] = ()
    forbidden_text: Tuple[str, ...] = ()


PROBES = (
    CapabilityProbe("android-framework", ("getprop", "sys.boot_completed"), ("1",)),
    CapabilityProbe("art-runtime", ("ls", "-l", "/system/bin/app_process64"), ("app_process64",)),
    CapabilityProbe("audio-framework", ("service", "check", "audio"), ("found",), ("not found",)),
    CapabilityProbe("credential-encrypted-storage", ("dumpsys", "user"), ("RUNNING_UNLOCKED",)),
    CapabilityProbe("device-encrypted-storage", ("getprop", "ro.crypto.type"), ("file",)),
    CapabilityProbe("dns", ("service", "list"), ("dnsresolver:",)),
    CapabilityProbe("download-provider", ("pm", "path", "com.android.providers.downloads"), ("package:",)),
    CapabilityProbe("hwui-egl", ("service", "check", "SurfaceFlinger"), ("found",), ("not found",)),
    CapabilityProbe("input", ("service", "check", "input"), ("found",), ("not found",)),
    CapabilityProbe("keystore", ("service", "check", "android.system.keystore2.IKeystoreService/default"), ("found",), ("not found",)),
    CapabilityProbe("logging-crash-evidence", ("logcat", "-d", "-t", "1")),
    CapabilityProbe("low-storage-signals", ("dumpsys", "devicestoragemonitor"), ("lowBytes=", "fullBytes=")),
    CapabilityProbe("network", ("service", "check", "connectivity"), ("found",), ("not found",)),
    CapabilityProbe("package-installer", ("pm", "path", "com.android.packageinstaller"), ("package:",)),
    CapabilityProbe("package-manager", ("service", "check", "package"), ("found",), ("not found",)),
    CapabilityProbe("settings-provider", ("settings", "get", "global", "auto_time")),
    CapabilityProbe("surfaceflinger", ("service", "check", "SurfaceFlinger"), ("found",), ("not found",)),
    CapabilityProbe("time-sync", ("settings", "get", "global", "auto_time"), ("1",)),
    CapabilityProbe("tls-ca-store", ("ls", "/system/etc/security/cacerts"), (".0",)),
    CapabilityProbe("webview", ("dumpsys", "webviewupdate"), ("Current WebView package",), ("null",)),
)


def parse_cpu_totals(text: str) -> Tuple[int, int]:
    match = CPU_LINE.search(text)
    if match is None:
        raise AndroidUpdateLabError("/proc/stat does not contain an aggregate CPU line")
    values = [int(item) for item in match.group(1).split()]
    total = sum(values)
    idle = values[3] + (values[4] if len(values) > 4 else 0)
    return total, idle


def cpu_busy_percent(before: str, after: str) -> float:
    total_before, idle_before = parse_cpu_totals(before)
    total_after, idle_after = parse_cpu_totals(after)
    total_delta = total_after - total_before
    idle_delta = idle_after - idle_before
    if total_delta <= 0 or idle_delta < 0 or idle_delta > total_delta:
        raise AndroidUpdateLabError("invalid /proc/stat sample delta")
    return round(100.0 * (total_delta - idle_delta) / total_delta, 3)


def parse_total_ram_kib(text: str) -> int:
    match = TOTAL_PSS.search(text)
    if match is None:
        raise AndroidUpdateLabError("dumpsys meminfo Total RAM was not found")
    return int(match.group(1).replace(",", ""))


def parse_ram_breakdown_kib(text: str) -> Mapping[str, int]:
    values = {
        name.lower() + "_ram_kib": int(amount.replace(",", ""))
        for name, amount in RAM_VALUE.findall(text)
    }
    if set(values) != {"used_ram_kib", "free_ram_kib"}:
        raise AndroidUpdateLabError("dumpsys meminfo Used/Free RAM was not found")
    return values


def audit_capabilities(adb: AdbClient, update_evidence: Mapping[str, Any]) -> Mapping[str, Any]:
    results: Dict[str, Any] = {}
    for probe in PROBES:
        result = adb.shell(probe.command, timeout_seconds=30, check=False)
        combined = (result.stdout + "\n" + result.stderr).strip()
        passed = result.returncode == 0
        passed = passed and all(item.lower() in combined.lower() for item in probe.required_text)
        passed = passed and all(item.lower() not in combined.lower() for item in probe.forbidden_text)
        results[probe.capability] = {
            "outcome": "pass" if passed else "fail",
            "command": list(probe.command),
            "returncode": result.returncode,
            "evidence": combined[:10000],
        }

    phases = update_evidence.get("phases", [])
    phase_names = {
        phase.get("name")
        for phase in phases
        if isinstance(phase, dict) and phase.get("outcome") == "pass"
    }
    external_ok = (
        update_evidence.get("outcome") == "pass"
        and "single-apk-upgrade" in phase_names
        and "resource-android-restart-resume" in phase_names
    )
    results["external-app-storage"] = {
        "outcome": "pass" if external_ok else "fail",
        "evidence": "synthetic update lab preserved external sentinel and resources across upgrade/restart",
    }
    if set(results) != set(REQUIRED_PROTECTED_CAPABILITIES):
        raise AndroidUpdateLabError("capability probe set differs from policy protected capabilities")
    return results


def collect_identity(adb: AdbClient) -> Mapping[str, str]:
    properties = {
        "abi_list": "ro.product.cpu.abilist",
        "api_level": "ro.build.version.sdk",
        "build_fingerprint": "ro.build.fingerprint",
        "security_patch": "ro.build.version.security_patch",
        "verified_boot_state": "ro.boot.verifiedbootstate",
    }
    return {
        key: adb.shell(("getprop", prop)).stdout.strip()
        for key, prop in properties.items()
    }


def collect_idle_metrics(adb: AdbClient, sample_seconds: float) -> Mapping[str, Any]:
    if sample_seconds <= 0:
        raise AndroidUpdateLabError("idle sample duration must be positive")
    before = adb.shell(("cat", "/proc/stat")).stdout
    import time

    time.sleep(sample_seconds)
    after = adb.shell(("cat", "/proc/stat")).stdout
    meminfo = adb.shell(("dumpsys", "meminfo")).stdout
    result = {
        "sample_seconds": sample_seconds,
        "device_cpu_busy_percent": cpu_busy_percent(before, after),
        "total_ram_kib": parse_total_ram_kib(meminfo),
        "loadavg": adb.shell(("cat", "/proc/loadavg")).stdout.strip(),
        "uptime": adb.shell(("cat", "/proc/uptime")).stdout.strip(),
        "filesystems": adb.shell(("df", "-k", "/system", "/vendor", "/product", "/data")).stdout.strip(),
        "scope": "no-game-no-alas-idle-baseline",
    }
    result.update(parse_ram_breakdown_kib(meminfo))
    return result
