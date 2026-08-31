"""Stable public facade and strict runtime-backend configuration factory."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Optional

from .runtime_backend import BackendKind, RuntimeBackend
from .runtime_backend_adb import (
    AdbAttachedBackend,
    ExternalAdbBackend,
    ExternalAdbConfig,
    RuntimeBackendError,
    RuntimeBackendNotReady,
    RuntimeIdentityMismatch,
)
from .runtime_backend_deferred import DeferredRuntimeBackend
from .runtime_backend_kvm import KvmBackend, KvmRuntimeConfig, probe_linux_kvm
from .runtime_backend_redroid import RedroidBackend, RedroidRuntimeConfig
from .runtime_command import RuntimeCommandExecutor
from .runtime_trace import RuntimeTraceRecorder


def backend_from_config(
    value: Mapping[str, Any],
    executor: RuntimeCommandExecutor,
    trace: Optional[RuntimeTraceRecorder] = None,
    **kwargs: Any
) -> RuntimeBackend:
    if not isinstance(value, dict):
        raise ValueError("runtime backend config must be a JSON object")
    if value.get("schema") != "alas-headless.runtime-config/v1":
        raise ValueError("runtime backend config schema mismatch")

    def path_field(name: str, optional: bool = False) -> Optional[Path]:
        item = value.get(name)
        if optional and item is None:
            return None
        if not isinstance(item, str) or not item.strip():
            raise ValueError(
                "runtime backend config path is invalid: {0}".format(name)
            )
        return Path(item)

    try:
        kind = BackendKind(value.get("backend"))
    except (TypeError, ValueError) as exc:
        raise ValueError("runtime backend config kind is unsupported") from exc

    common_required = {"schema", "backend", "serial", "package", "component", "host_class"}
    if kind == BackendKind.EXTERNAL_ADB:
        allowed = common_required | {
            "adb",
            "adb_server_port",
            "connect_transport",
            "angle_package",
            "unity_command_line",
            "launch_game",
            "manage_angle_routing",
            "allow_game_restart",
            "allow_android_restart",
            "poll_interval_seconds",
        }
        missing = sorted(common_required - set(value))
        unknown = sorted(set(value) - allowed)
        if missing or unknown:
            raise ValueError(
                "external ADB config fields differ (missing={0}; unknown={1})".format(
                    ",".join(missing), ",".join(unknown)
                )
            )
        config = ExternalAdbConfig(
            serial=value["serial"],
            package=value["package"],
            component=value["component"],
            host_class=value["host_class"],
            adb=value.get("adb", "adb"),
            adb_server_port=value.get("adb_server_port", 5037),
            connect_transport=value.get("connect_transport", False),
            angle_package=value.get("angle_package", "org.chromium.angle"),
            unity_command_line=value.get("unity_command_line"),
            launch_game=value.get("launch_game", False),
            manage_angle_routing=value.get("manage_angle_routing", False),
            allow_game_restart=value.get("allow_game_restart", False),
            allow_android_restart=value.get("allow_android_restart", False),
            poll_interval_seconds=value.get("poll_interval_seconds", 1.0),
        )
        return ExternalAdbBackend(config, executor, trace=trace, **kwargs)

    if kind == BackendKind.KVM:
        required = common_required | {
            "emulator",
            "emulator_check",
            "adb",
            "avd_name",
            "avd_home",
            "console_port",
            "adb_server_port",
            "runtime_release_root",
        }
        allowed = required | {
            "sdk_root",
            "adb_server_port",
            "angle_package",
            "unity_command_line",
            "null_refresh_hz",
            "cpu_affinity",
            "numa_node",
            "launch_game",
            "manage_angle_routing",
            "poll_interval_seconds",
        }
        missing = sorted(required - set(value))
        unknown = sorted(set(value) - allowed)
        if missing or unknown:
            raise ValueError(
                "KVM config fields differ (missing={0}; unknown={1})".format(
                    ",".join(missing), ",".join(unknown)
                )
            )
        config = KvmRuntimeConfig(
            serial=value["serial"],
            package=value["package"],
            component=value["component"],
            host_class=value["host_class"],
            emulator=path_field("emulator"),
            emulator_check=path_field("emulator_check"),
            adb=path_field("adb"),
            avd_name=value["avd_name"],
            avd_home=path_field("avd_home"),
            console_port=value["console_port"],
            adb_server_port=value["adb_server_port"],
            runtime_release_root=path_field("runtime_release_root"),
            sdk_root=path_field("sdk_root", optional=True),
            angle_package=value.get("angle_package", "org.chromium.angle"),
            unity_command_line=value.get("unity_command_line", "-force-gfx-st"),
            null_refresh_hz=value.get("null_refresh_hz", 30),
            cpu_affinity=value.get("cpu_affinity"),
            numa_node=value.get("numa_node"),
            launch_game=value.get("launch_game", True),
            manage_angle_routing=value.get("manage_angle_routing", False),
            poll_interval_seconds=value.get("poll_interval_seconds", 1.0),
        )
        return KvmBackend(config, executor, trace=trace, **kwargs)

    if kind == BackendKind.REDROID:
        required = common_required | {
            "container_id",
            "image_reference",
            "image_manifest_digest",
            "userdata_image",
            "metadata_image",
            "start_script",
        }
        allowed = required | {
            "stop_script",
            "ctr",
            "sudo",
            "namespace",
            "adb",
            "adb_server_port",
            "angle_package",
            "unity_command_line",
            "launch_game",
            "manage_angle_routing",
            "allow_game_restart",
            "allow_android_restart",
            "stop_container_on_cleanup",
            "disable_system_ui_for_headless",
            "poll_interval_seconds",
            "storage_layout",
        }
        missing = sorted(required - set(value))
        unknown = sorted(set(value) - allowed)
        if missing or unknown:
            raise ValueError(
                "Redroid config fields differ (missing={0}; unknown={1})".format(
                    ",".join(missing), ",".join(unknown)
                )
            )
        config = RedroidRuntimeConfig(
            serial=value["serial"],
            package=value["package"],
            component=value["component"],
            host_class=value["host_class"],
            container_id=value["container_id"],
            image_reference=value["image_reference"],
            image_manifest_digest=value["image_manifest_digest"],
            userdata_image=value["userdata_image"],
            metadata_image=value["metadata_image"],
            start_script=value["start_script"],
            stop_script=value.get("stop_script"),
            ctr=value.get("ctr", "ctr"),
            sudo=value.get("sudo", "sudo"),
            namespace=value.get("namespace", "alas-headless"),
            adb=value.get("adb", "adb"),
            adb_server_port=value.get("adb_server_port", 5037),
            angle_package=value.get("angle_package", "org.chromium.angle"),
            unity_command_line=value.get("unity_command_line", "-force-gfx-st"),
            launch_game=value.get("launch_game", True),
            manage_angle_routing=value.get("manage_angle_routing", False),
            allow_game_restart=value.get("allow_game_restart", True),
            allow_android_restart=value.get("allow_android_restart", True),
            stop_container_on_cleanup=value.get("stop_container_on_cleanup", True),
            disable_system_ui_for_headless=value.get(
                "disable_system_ui_for_headless", False
            ),
            poll_interval_seconds=value.get("poll_interval_seconds", 1.0),
            storage_layout=value.get("storage_layout", "srv-v1"),
        )
        return RedroidBackend(config, executor, trace=trace, **kwargs)

    allowed = {"schema", "backend", "host_class"}
    missing = sorted(allowed - set(value))
    unknown = sorted(set(value) - allowed)
    if missing or unknown:
        raise ValueError(
            "deferred backend config fields differ (missing={0}; unknown={1})".format(
                ",".join(missing), ",".join(unknown)
            )
        )
    return DeferredRuntimeBackend(
        kind,
        "{0}-adapter-not-implemented".format(kind.value),
        value["host_class"],
    )

__all__ = [
    "AdbAttachedBackend",
    "DeferredRuntimeBackend",
    "ExternalAdbBackend",
    "ExternalAdbConfig",
    "KvmBackend",
    "KvmRuntimeConfig",
    "RedroidBackend",
    "RedroidRuntimeConfig",
    "RuntimeBackendError",
    "RuntimeBackendNotReady",
    "RuntimeIdentityMismatch",
    "backend_from_config",
    "probe_linux_kvm",
]
