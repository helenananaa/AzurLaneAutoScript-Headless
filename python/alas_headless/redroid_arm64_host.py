"""Product-scoped host checks for running Azur Lane in ARM64 Redroid."""

from __future__ import annotations

import gzip
import os
import platform
import re
import shutil
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence, Tuple


PROBE_SCHEMA = "alas-headless.redroid-arm64-host-probe/v1"
_VA_BITS = re.compile(r"^CONFIG_ARM64_VA_BITS=(\d+)$", re.MULTILINE)


def evaluate_game_va_window(kernel_config: Optional[str]) -> Mapping[str, Any]:
    """Classify whether every userspace pointer fits old LuaJIT lightuserdata."""

    if kernel_config is None:
        return {
            "outcome": "blocked",
            "va_bits": None,
            "failure": "arm64-kernel-config-unavailable",
        }
    match = _VA_BITS.search(kernel_config)
    if match is None:
        return {
            "outcome": "blocked",
            "va_bits": None,
            "failure": "arm64-kernel-va-bits-unavailable",
        }
    va_bits = int(match.group(1))
    if va_bits > 47:
        return {
            "outcome": "blocked",
            "va_bits": va_bits,
            "failure": "arm64-game-lightuserdata-va-window-exceeds-47-bits",
        }
    return {"outcome": "pass", "va_bits": va_bits, "failure": None}


def probe_redroid_arm64_host(
    *,
    architecture: str,
    docker_cli_present: bool,
    cgroup_v2_present: bool,
    binder_present: bool,
    image: str,
    kernel_release: str,
    kernel_config_source: Optional[str],
    kernel_config: Optional[str],
) -> Mapping[str, Any]:
    """Return the base Redroid checks plus the game-specific VA capability."""

    failures = []
    is_arm64 = architecture in ("aarch64", "arm64")
    if not is_arm64:
        failures.append("host-architecture-is-not-arm64")
    if not docker_cli_present:
        failures.append("docker-cli-missing")
    if not cgroup_v2_present:
        failures.append("cgroup-v2-missing")
    if not binder_present:
        failures.append("binder-device-or-binderfs-missing")
    if "@sha256:" not in image:
        failures.append("ALAS_REDROID_IMAGE-must-use-content-digest")

    if is_arm64:
        game_va = evaluate_game_va_window(kernel_config)
        if game_va["failure"] is not None:
            failures.append(str(game_va["failure"]))
    else:
        game_va = {"outcome": "not-applicable", "va_bits": None, "failure": None}

    return {
        "schema": PROBE_SCHEMA,
        "outcome": "blocked" if failures else "pass",
        "host_architecture": architecture,
        "image": image,
        "kernel_release": kernel_release,
        "kernel_config_source": kernel_config_source,
        "kernel_va_bits": game_va["va_bits"],
        "game_lightuserdata_va_outcome": game_va["outcome"],
        "failures": failures,
    }


def read_running_kernel_config(
    kernel_release: str,
) -> Tuple[Optional[str], Optional[str]]:
    """Read the running kernel config without guessing another release."""

    proc_config = Path("/proc/config.gz")
    if proc_config.is_file():
        try:
            with gzip.open(str(proc_config), "rt", encoding="utf-8") as handle:
                return str(proc_config), handle.read()
        except (OSError, UnicodeError):
            pass

    boot_config = Path("/boot") / "config-{0}".format(kernel_release)
    if boot_config.is_file():
        try:
            return str(boot_config), boot_config.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            pass
    return None, None


def probe_running_host(environ: Optional[Mapping[str, str]] = None) -> Mapping[str, Any]:
    env = os.environ if environ is None else environ
    kernel_release = platform.release()
    config_source, kernel_config = read_running_kernel_config(kernel_release)
    binder_present = any(
        path.exists()
        for path in (
            Path("/dev/binderfs"),
            Path("/dev/binder"),
            Path("/dev/hwbinder"),
            Path("/dev/vndbinder"),
        )
    )
    return probe_redroid_arm64_host(
        architecture=platform.machine(),
        docker_cli_present=shutil.which("docker") is not None,
        cgroup_v2_present=Path("/sys/fs/cgroup/cgroup.controllers").is_file(),
        binder_present=binder_present,
        image=env.get("ALAS_REDROID_IMAGE", ""),
        kernel_release=kernel_release,
        kernel_config_source=config_source,
        kernel_config=kernel_config,
    )


__all__: Sequence[str] = (
    "PROBE_SCHEMA",
    "evaluate_game_va_window",
    "probe_redroid_arm64_host",
    "probe_running_host",
    "read_running_kernel_config",
)
