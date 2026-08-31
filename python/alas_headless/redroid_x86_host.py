"""Qualification-host checks for the x86 Redroid FBE runtime."""

from __future__ import annotations

import gzip
import os
import platform
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence, Set, Tuple


PROBE_SCHEMA = "alas-headless.redroid-x86-host-probe/v1"
_DIGEST_REFERENCE = re.compile(r"^[^\s@]+@sha256:[0-9a-f]{64}$")
_UEVENT_IO_ERROR = re.compile(
    r"ueventd: (?:Error reading from Uevent Fd: I/O error|[^\r\n]*\bEIO\b)"
)
_NETLINK_IO_ERROR = re.compile(
    r"NetlinkListener: recvmsg (?:failed \(I/O error\)|[^\r\n]*\bEIO\b)"
)

_CAPABILITIES = {
    "CONFIG_ANDROID_BINDER_IPC": "binder_linux",
    "CONFIG_DM_CRYPT": "dm_crypt",
    "CONFIG_DM_VERITY": "dm_verity",
    "CONFIG_IP_NF_FILTER": "iptable_filter",
    "CONFIG_NF_CONNTRACK": "nf_conntrack",
    "CONFIG_QFMT_V2": "quota_v2",
}


def _config_value(kernel_config: Optional[str], name: str) -> Optional[str]:
    if kernel_config is None:
        return None
    match = re.search(
        r"^{0}=([^\r\n]+)$".format(re.escape(name)), kernel_config, re.MULTILINE
    )
    return match.group(1) if match is not None else None


def classify_kernel_event_errors(kernel_log: str) -> Mapping[str, Any]:
    """Recognize both spellings observed during the host-impacting failure."""

    uevent_count = len(_UEVENT_IO_ERROR.findall(kernel_log))
    netlink_count = len(_NETLINK_IO_ERROR.findall(kernel_log))
    total = uevent_count + netlink_count
    return {
        "outcome": "repeated-eio" if total >= 3 else "clear",
        "uevent_io_error_count": uevent_count,
        "netlink_io_error_count": netlink_count,
        "total_io_error_count": total,
    }


def probe_redroid_x86_host(
    *,
    architecture: str,
    ctr_cli_present: bool,
    cgroup_v2_present: bool,
    image: str,
    kernel_release: str,
    kernel_config_source: Optional[str],
    kernel_config: Optional[str],
    dm_targets: Sequence[str],
    available_modules: Sequence[str],
    loaded_modules: Sequence[str],
    recovery_default_kernel: Optional[str],
) -> Mapping[str, Any]:
    """Evaluate only capabilities needed before an experimental FBE boot."""

    failures = []
    if architecture not in ("amd64", "x86_64"):
        failures.append("host-architecture-is-not-x86-64")
    if not ctr_cli_present:
        failures.append("containerd-cli-missing")
    if not cgroup_v2_present:
        failures.append("cgroup-v2-missing")
    if _DIGEST_REFERENCE.fullmatch(image) is None:
        failures.append("ALAS_REDROID_IMAGE-must-use-content-digest")
    if kernel_config is None:
        failures.append("x86-kernel-config-unavailable")
    else:
        dm_default_key = _config_value(kernel_config, "CONFIG_DM_DEFAULT_KEY")
        if dm_default_key not in ("y", "m"):
            failures.append("x86-dm-default-key-config-unavailable")
        module_set = set(available_modules)
        loaded_module_set = set(loaded_modules)
        for config_name, module_name in _CAPABILITIES.items():
            value = _config_value(kernel_config, config_name)
            if value not in ("y", "m"):
                failures.append(config_name.lower() + "-unavailable")
            elif value == "m" and module_name not in module_set:
                failures.append(module_name + "-module-unavailable")
            elif value == "m" and module_name not in loaded_module_set:
                failures.append(module_name + "-module-not-loaded")
    if "default-key" not in set(dm_targets):
        failures.append("x86-dm-default-key-target-unavailable")
    experimental_dm_kernel = _config_value(kernel_config, "CONFIG_DM_DEFAULT_KEY") in (
        "y",
        "m",
    )
    if not recovery_default_kernel:
        failures.append("stock-recovery-default-kernel-unavailable")
    elif experimental_dm_kernel and recovery_default_kernel == kernel_release:
        failures.append("experimental-kernel-is-recovery-default")

    return {
        "schema": PROBE_SCHEMA,
        "outcome": "blocked" if failures else "pass",
        "host_architecture": architecture,
        "image": image,
        "kernel_release": kernel_release,
        "kernel_config_source": kernel_config_source,
        "dm_targets": sorted(set(dm_targets)),
        "recovery_default_kernel": recovery_default_kernel,
        "failures": failures,
    }


def read_running_kernel_config(
    kernel_release: str,
) -> Tuple[Optional[str], Optional[str]]:
    proc_config = Path("/proc/config.gz")
    if proc_config.is_file():
        try:
            with gzip.open(str(proc_config), "rt", encoding="utf-8") as handle:
                return str(proc_config), handle.read()
        except (OSError, UnicodeError):
            pass
    boot_config = Path("/boot") / ("config-" + kernel_release)
    try:
        return str(boot_config), boot_config.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return None, None


def _output(argv: Sequence[str]) -> str:
    try:
        result = subprocess.run(
            list(argv), check=False, capture_output=True, text=True, timeout=15
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return result.stdout if result.returncode == 0 else ""


def _available_modules(kernel_config: Optional[str]) -> Set[str]:
    modules = set()
    for config_name, module_name in _CAPABILITIES.items():
        if _config_value(kernel_config, config_name) == "m" and _output(
            ("modinfo", "-F", "filename", module_name)
        ).strip():
            modules.add(module_name)
    return modules


def _recovery_default_kernel() -> Optional[str]:
    grub_default = Path("/etc/default/grub")
    grub_config = Path("/boot/grub/grub.cfg")
    try:
        defaults = grub_default.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        defaults = _output(("sudo", "-n", "cat", str(grub_default)))
    try:
        menu = grub_config.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        menu = _output(("sudo", "-n", "cat", str(grub_config)))
    if re.search(r"^GRUB_DEFAULT=0$", defaults, re.MULTILINE) is None:
        return None
    first_entry = re.search(
        r"^menuentry .*?^\s*linux\s+/vmlinuz-([^\s]+)",
        menu,
        re.MULTILINE | re.DOTALL,
    )
    return first_entry.group(1) if first_entry is not None else None


def probe_running_host(
    environ: Optional[Mapping[str, str]] = None,
) -> Mapping[str, Any]:
    env = os.environ if environ is None else environ
    kernel_release = platform.release()
    config_source, kernel_config = read_running_kernel_config(kernel_release)
    dm_targets = []
    for line in _output(("sudo", "-n", "dmsetup", "targets")).splitlines():
        fields = line.split()
        if fields:
            dm_targets.append(fields[0])
    return probe_redroid_x86_host(
        architecture=platform.machine(),
        ctr_cli_present=shutil.which("ctr") is not None,
        cgroup_v2_present=Path("/sys/fs/cgroup/cgroup.controllers").is_file(),
        image=env.get("ALAS_REDROID_IMAGE", ""),
        kernel_release=kernel_release,
        kernel_config_source=config_source,
        kernel_config=kernel_config,
        dm_targets=dm_targets,
        available_modules=sorted(_available_modules(kernel_config)),
        loaded_modules=sorted(
            module_name
            for module_name in _CAPABILITIES.values()
            if (Path("/sys/module") / module_name).is_dir()
        ),
        recovery_default_kernel=_recovery_default_kernel(),
    )


__all__: Sequence[str] = (
    "PROBE_SCHEMA",
    "classify_kernel_event_errors",
    "probe_redroid_x86_host",
    "probe_running_host",
    "read_running_kernel_config",
)
