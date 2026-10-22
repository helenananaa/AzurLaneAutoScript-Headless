"""Windows/WSL Docker host adapter for the retained local Project instance.

Game, ADB, observer and recovery ownership remain in the common Redroid backend.
The existing Project manager owns container creation and persistent storage.
"""

from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from .runtime_backend import BackendKind, RuntimeProbeResult
from .runtime_backend_adb import AdbAttachedBackend, ExternalAdbConfig, RuntimeBackendNotReady, RuntimeIdentityMismatch
from .runtime_backend_redroid import RedroidBackend, _normalized_architecture, _validate_private_adb_serial, _validate_narrow_path, _CONTAINER_NAME_PATTERN, _MANIFEST_DIGEST_PATTERN
from .oracle.transport import AdbObserverBridge, encode_adb_shell_string_extra, request_observer_state, observer_snapshot_semantic_ready
from .oracle.errors import ObserverTransportError
from .semantic_oracle import OBSERVER_SCHEMA, BUTTON_SCHEMA


@dataclass(frozen=True)
class WslRedroidRuntimeConfig:
    serial: str
    package: str
    component: str
    host_class: str
    container_id: str
    image_manifest_digest: str
    userdata_path: str
    manager_script: str
    project_artifact_directory: str
    project_instance: str = "projectlocal"
    distro: str = "Ubuntu-22.04"
    wsl: str = "wsl.exe"
    powershell: str = "powershell.exe"
    adb: str = "adb"
    adb_server_port: int = 5037
    angle_package: str = "org.chromium.angle"
    unity_command_line: str = "-force-gfx-st"
    launch_game: bool = True
    manage_angle_routing: bool = False
    allow_game_restart: bool = True
    allow_android_restart: bool = True
    stop_container_on_cleanup: bool = True
    poll_interval_seconds: float = 1.0
    allow_sdk_activity_reentry: bool = True
    # Project never disables SystemUI; its manager confirms the immersive hint.
    disable_system_ui_for_headless = False
    stop_script = None
    storage_layout = "host-directory-v1"

    @property
    def image_reference(self) -> str:
        return self.image_manifest_digest

    def __post_init__(self) -> None:
        # Reuse the existing package, transport, launch and storage contracts.
        ExternalAdbConfig(
            serial=self.serial, package=self.package, component=self.component,
            host_class=self.host_class,
            adb=self.adb, adb_server_port=self.adb_server_port,
            angle_package=self.angle_package,
            unity_command_line=self.unity_command_line, launch_game=self.launch_game,
            manage_angle_routing=self.manage_angle_routing,
            allow_game_restart=self.allow_game_restart,
            allow_android_restart=self.allow_android_restart,
            poll_interval_seconds=self.poll_interval_seconds,
        )
        _validate_private_adb_serial(self.serial)
        _validate_narrow_path("userdata_path", self.userdata_path)
        if not _CONTAINER_NAME_PATTERN.fullmatch(self.container_id) or not _MANIFEST_DIGEST_PATTERN.fullmatch(self.image_manifest_digest):
            raise ValueError("WSL container/image identity is malformed")
        if not isinstance(self.stop_container_on_cleanup, bool):
            raise ValueError("WSL cleanup switch must be boolean")
        if not re.fullmatch(r"[A-Za-z0-9._-]+", self.distro) or self.distro.lower() == "docker-desktop":
            raise ValueError("a local development WSL distribution is required")
        for value in (self.manager_script, self.project_artifact_directory, self.wsl, self.powershell):
            if not isinstance(value, str) or not value.strip():
                raise ValueError("WSL Project command/path is missing")
        if not isinstance(self.allow_sdk_activity_reentry, bool):
            raise ValueError("SDK Activity recovery switch must be boolean")
        if not re.fullmatch(r"[a-z][a-z0-9-]{0,47}", self.project_instance):
            raise ValueError("WSL Project instance name is malformed")


class WslRedroidBackend(RedroidBackend):
    """Reuse Redroid lifecycle with local WSL Docker host operations."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._sdk_reentry_attempted = set()

    def _prepare_game_cold_launch(self, instance):
        self._sdk_reentry_attempted.discard(str(instance["instance_id"]))

    def _foreground(self):
        activity = self._require_success(self._adb("wsl-game-activity", ("shell", "dumpsys", "activity", "activities")), "wsl-activity-unavailable")
        pid = self._require_success(self._adb("wsl-game-pid", ("shell", "pidof", self.package)), "wsl-game-pid-unavailable")
        match = AdbObserverBridge._FOREGROUND_PATTERN.search(activity)
        if not pid.isdigit() or match is None:
            raise RuntimeBackendNotReady("wsl-game-identity-unavailable")
        return int(pid), match.group(1), activity

    def inspect_login_boundary(self) -> Mapping[str, Any]:
        """Read native SDK controls; never admits this surface as Unity-ready."""
        pid, component, _ = self._foreground()
        expected = self.package + "/com.gsc.phone_login.PhoneLoginActivity"
        if component != expected:
            raise RuntimeBackendNotReady("sdk-login-not-foreground")
        result = self._require_success(self._adb("wsl-login-ui", ("exec-out", "uiautomator", "dump", "/dev/tty")), "sdk-login-ui-unavailable")
        try:
            root = ET.fromstring(result[result.index("<?xml"):result.rindex("</hierarchy>") + len("</hierarchy>")])
        except (ValueError, ET.ParseError) as exc:
            raise RuntimeBackendNotReady("sdk-login-ui-malformed") from exc
        nodes = [node for node in root.iter("node") if node.get("package") == self.package]
        fields = [node for node in nodes if node.get("class") == "android.widget.EditText"]
        next_controls = [node for node in nodes if node.get("text") == "下一步"]
        # Android's UI dump may put an empty EditText's hint in its text field.
        empty = len(fields) == 1 and fields[0].get("text", "") in ("", "请输入手机号", "请输入手机号码")
        if not empty or len(next_controls) != 1 or next_controls[0].get("enabled") != "false":
            raise RuntimeBackendNotReady("sdk-login-boundary-not-empty")
        accounts = self._require_success(self._adb("wsl-android-accounts", ("shell", "dumpsys", "account")), "sdk-account-state-unavailable")
        counts = re.findall(r"^\s*Accounts:\s*(\d+)\s*$", accounts, re.M)
        if not counts or any(int(count) != 0 for count in counts):
            raise RuntimeBackendNotReady("sdk-account-boundary-not-empty")
        if self._foreground()[:2] != (pid, component):
            raise RuntimeIdentityMismatch("sdk-login-identity-changed")
        return {"state": "account-input-required", "pid": pid, "component": component, "empty_phone_field": True, "next_disabled": True, "android_account_count": 0, "observer_ready": False}

    def _observer_progress(self, instance, timeout_seconds):
        state = super().wait_observer_ready(instance, timeout_seconds)
        bridge = self._bridges[str(instance["instance_id"])]

        def progressed():
            try:
                snapshot, buttons, atomic = request_observer_state(bridge.request)
            except ObserverTransportError:
                return None
            if any(value.get("package") != self.package or value.get("pid") != state["pid"] for value in (snapshot, buttons)):
                raise RuntimeIdentityMismatch("observer-pid-or-package-changed")
            if (any(value.get("protocol_schema") != OBSERVER_SCHEMA or value.get("status") != "ok" for value in (snapshot, buttons))
                    or snapshot.get("snapshot_schema") != 1
                    or buttons.get("semantic_schema") != BUTTON_SCHEMA or buttons.get("schema") != 1):
                raise RuntimeBackendNotReady("observer-state-contract-mismatch")
            if self._foreground()[:2] != (state["pid"], self.component):
                raise RuntimeBackendNotReady("observer-main-activity-not-foreground")
            generation = snapshot.get("generation")
            button_generation = buttons.get("generation")
            if any(value.get("driver_revision") != self._runtime_lock.document["angle"]["revision"] for value in (snapshot, buttons)):
                raise RuntimeIdentityMismatch("observer-driver-revision-mismatch")
            if (isinstance(generation, int) and not isinstance(generation, bool)
                    and generation > state["generation"]
                    and isinstance(button_generation, int) and not isinstance(button_generation, bool)
                    and (button_generation == generation if atomic else generation <= button_generation <= generation + 2)
                    and isinstance(snapshot.get("age_ms"), (int, float))
                    and not isinstance(snapshot.get("age_ms"), bool)
                    and 0 <= snapshot["age_ms"] <= 2500
                    and observer_snapshot_semantic_ready(snapshot)):
                return dict(state, generation=generation, initial_generation=state["generation"], age_ms=snapshot["age_ms"])
            return None

        return self._wait_for(timeout_seconds, progressed, "observer-progress-timeout")

    def _recover_sdk_pause(self, instance) -> Mapping[str, Any]:
        pid, component, activity = self._foreground()
        if component != self.component or not re.search(r"mLastPausedActivity:.*" + re.escape(self.package + "/com.gsc.announcement.AnnouncementActivity"), activity):
            raise RuntimeBackendNotReady("sdk-reentry-preconditions-not-met")
        bridge = self.bridge_factory(self.serial, self.package, adb=self.adb, adb_server_port=self.adb_server_port, command_timeout_seconds=5)
        try:
            bridge.open()
            snapshot = bridge.request("GET /v1/snapshot\n")
        finally:
            bridge.close()
        if snapshot.get("pid") != pid or snapshot.get("package") != self.package:
            raise RuntimeIdentityMismatch("sdk-reentry-observer-identity-mismatch")
        stale = snapshot.get("status") == "unavailable" or (snapshot.get("status") == "ok" and isinstance(snapshot.get("age_ms"), (int, float)) and snapshot["age_ms"] > 2500)
        if not stale:
            raise RuntimeBackendNotReady("sdk-reentry-observer-not-stale")
        log = self._require_success(self._adb("wsl-game-fatal-probe", ("shell", "logcat", "-d", "--pid=" + str(pid))), "sdk-reentry-log-unavailable")
        if re.search(r"Fatal signal|FATAL EXCEPTION|destroyed mutex|Abort message", log):
            raise RuntimeBackendNotReady("sdk-reentry-game-fatal")
        home = self._require_success(self._adb("wsl-home-resolve", ("shell", "cmd", "package", "resolve-activity", "--brief", "-a", "android.intent.action.MAIN", "-c", "android.intent.category.HOME")), "sdk-home-unavailable")
        components = [line for line in home.splitlines() if re.fullmatch(r"[A-Za-z0-9._]+/[A-Za-z0-9._$]+", line)]
        if len(components) != 1 or self._foreground()[:2] != (pid, component):
            raise RuntimeBackendNotReady("sdk-reentry-identity-changed")
        self._require_success(self._adb("wsl-sdk-home", ("shell", "am", "start", "-W", "-n", components[0]), mutating=True), "sdk-home-start-failed")
        self._wait_for(10, lambda: {"home": True} if self._foreground()[:2] == (pid, components[0]) else None, "sdk-home-not-foreground")
        self._require_success(self._adb("wsl-sdk-reentry", ("shell", "am", "start", "-W", "--es", "unity", encode_adb_shell_string_extra(self.unity_command_line), "-n", self.component), mutating=True), "sdk-reentry-failed")
        self._wait_for(10, lambda: {"returned": True} if self._foreground()[:2] == (pid, component) else None, "sdk-reentry-postcondition-failed")
        return {"pid_preserved": True, "pid": pid, "home_component": components[0]}

    def wait_observer_ready(self, instance, timeout_seconds):
        self._close_observer(instance)
        try:
            return self._observer_progress(instance, min(timeout_seconds, 15))
        except Exception as exc:
            self._close_observer(instance)
            if not self.config.allow_sdk_activity_reentry or not isinstance(exc, RuntimeBackendNotReady) or exc.code not in ("observer-ready-timeout", "observer-progress-timeout", "observer-bridge-open-failed"):
                raise
        instance_id = str(instance["instance_id"])
        if instance_id in self._sdk_reentry_attempted:
            raise RuntimeBackendNotReady("sdk-reentry-already-attempted")
        self._sdk_reentry_attempted.add(instance_id)
        recovery = self._recover_sdk_pause(instance)
        try:
            state = self._observer_progress(instance, min(timeout_seconds, 30))
        except Exception:
            self._close_observer(instance)
            raise
        return dict(state, sdk_activity_reentry=recovery)

    def _wsl(self, label: str, *argv: str):
        return self._command(label, (self.config.wsl, "-d", self.config.distro, "--") + argv)

    def _docker(self, label: str, *argv: str):
        # Explicit socket prevents DOCKER_HOST or an active Docker context from
        # silently selecting Docker Desktop or a remote daemon.
        return self._wsl(label, "docker", "--host", "unix:///var/run/docker.sock", *argv)

    def _json(self, result, code: str):
        try:
            return json.loads(self._require_success(result, code))
        except (ValueError, TypeError) as exc:
            raise RuntimeIdentityMismatch(code + "-malformed") from exc

    def _container_info(self) -> Mapping[str, Any]:
        value = self._json(self._docker("wsl-container-inspect", "container", "inspect", self.config.container_id), "wsl-container-inspect-failed")
        if not isinstance(value, list) or len(value) != 1 or not isinstance(value[0], dict):
            raise RuntimeIdentityMismatch("wsl-container-inspect-malformed")
        return value[0]

    def _task_running(self) -> bool:
        state = self._container_info().get("State", {})
        if not isinstance(state, dict) or not isinstance(state.get("Running"), bool):
            raise RuntimeIdentityMismatch("wsl-container-state-malformed")
        return state["Running"]

    def _validate_image_and_container(self) -> Mapping[str, Any]:
        info = self._container_info()
        image = self._json(self._docker("wsl-image-inspect", "image", "inspect", self.config.image_manifest_digest), "wsl-image-inspect-failed")
        if not isinstance(image, list) or len(image) != 1 or not isinstance(image[0], dict):
            raise RuntimeIdentityMismatch("wsl-image-inspect-malformed")
        if info.get("Name") != "/" + self.config.container_id or not image[0].get("Id") or info.get("Image") != image[0]["Id"]:
            raise RuntimeIdentityMismatch("wsl-container-image-mismatch")
        if image[0].get("Architecture") not in ("amd64", "x86_64"):
            raise RuntimeIdentityMismatch("wsl-image-architecture-mismatch")
        mounts = info.get("Mounts")
        if not isinstance(mounts, list) or any(not isinstance(item, dict) for item in mounts):
            raise RuntimeIdentityMismatch("wsl-userdata-mount-mismatch")
        data = [item for item in mounts if item.get("Destination") == "/data"]
        if len(data) != 1 or data[0].get("Source") != self.config.userdata_path or data[0].get("Type") != "bind" or data[0].get("RW") is not True:
            raise RuntimeIdentityMismatch("wsl-userdata-mount-mismatch")
        host = info.get("HostConfig", {})
        if not isinstance(host, dict):
            raise RuntimeIdentityMismatch("wsl-container-host-config-malformed")
        bindings = host.get("PortBindings", {})
        expected = [{"HostIp": "127.0.0.1", "HostPort": self.serial.rsplit(":", 1)[1]}]
        if host.get("NetworkMode") == "host" or bindings != {"5555/tcp": expected} or not self.serial.startswith("127.0.0.1:"):
            raise RuntimeIdentityMismatch("wsl-adb-binding-mismatch")
        return info

    def _validate_container_and_userdata(self) -> None:
        self._validate_image_and_container()

    def _host_architecture(self):
        result = self._wsl("wsl-host-architecture", "uname", "-m")
        return _normalized_architecture(result.stdout) if result.succeeded else None

    def probe_host(self) -> RuntimeProbeResult:
        docker = self._docker("wsl-docker-probe", "info", "--format", "{{.OSType}}")
        binder = self._wsl("wsl-binder-probe", "test", "-c", "/dev/binderfs/binder")
        available = docker.succeeded and docker.stdout.strip() == "linux" and binder.succeeded and self._host_architecture() == "x86_64"
        return RuntimeProbeResult(available, BackendKind.REDROID, "ready" if available else "wsl-docker-host-unavailable", {"host_class": self.host_class, "distro": self.config.distro, "container_engine": "wsl-docker"})

    def provision(self, artifacts: Mapping[str, Any]) -> Mapping[str, Any]:
        provisioned = dict(AdbAttachedBackend.provision(self, artifacts))
        if self._runtime_lock.document["android"]["abi"] != "x86_64":
            raise RuntimeIdentityMismatch("redroid-host-architecture-mismatch")
        if not Path(self.config.manager_script).is_file():
            raise RuntimeBackendNotReady("wsl-project-manager-missing")
        identity = Path(self.config.project_artifact_directory) / "redroid-x86_64.oci-build.json"
        try:
            candidate = json.loads(identity.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError) as exc:
            raise RuntimeBackendNotReady("wsl-project-candidate-unavailable") from exc
        if not isinstance(candidate, dict) or candidate.get("manifest_digest") != self.config.image_manifest_digest:
            raise RuntimeIdentityMismatch("wsl-project-candidate-mismatch")
        self._validate_container_and_userdata()
        provisioned["initially_running"] = self._task_running()
        return provisioned

    def _manager(self, label: str, action: str) -> None:
        # Recheck immediately before either mutation: the manager controls the
        # retained Project profile and must still name the selected instance.
        self._validate_container_and_userdata()
        argv = (
            self.config.powershell, "-NoProfile", "-NonInteractive", "-File",
            self.config.manager_script, "-Profile", "Project",
            "-Distro", self.config.distro, "-ProjectArtifactDirectory",
            self.config.project_artifact_directory,
            "-ProjectInstance", self.config.project_instance,
            "-ProjectAdbPort", self.serial.rsplit(":", 1)[1],
        )
        selected = self._json(self._command("wsl-project-config", argv + ("-Action", "Config")), "wsl-project-config-failed")
        if not isinstance(selected, dict) or any(selected.get(name) != getattr(self.config, name) for name in ("container_id", "serial", "userdata_path", "image_manifest_digest")):
            raise RuntimeIdentityMismatch("wsl-project-manager-target-mismatch")
        self._require_success(self._command(label, argv + ("-Action", action), timeout_seconds=240, mutating=True), "wsl-project-" + action.lower() + "-failed")

    def _start_runtime(self, label: str) -> None:
        self._manager(label, "Start")
        self._validate_container_and_userdata()
        if not self._task_running():
            raise RuntimeBackendNotReady("wsl-container-not-running")

    def _stop_task(self, label_prefix: str) -> None:
        if self._task_running():
            self._manager(label_prefix, "Stop")
        if self._task_running():
            raise RuntimeBackendNotReady("wsl-container-stop-failed")

    def _stop_host_runtime(self, label: str) -> None:
        # Project manager already handles the WSL keepalive lifecycle.
        pass

    def qualification_plan(self, runtime_lock: Mapping[str, Any]) -> Mapping[str, Any]:
        plan = dict(super().qualification_plan(runtime_lock))
        plan["container_engine"] = "wsl-docker"
        plan["state_changes"] = [item.replace("containerd", "wsl-docker") for item in plan["state_changes"]]
        return plan
