import json
import itertools
from dataclasses import asdict
from unittest.mock import patch

import pytest

from alas_headless.runtime_backend_redroid_wsl import WslRedroidBackend, WslRedroidRuntimeConfig
from alas_headless.runtime_backends import backend_from_config, RuntimeIdentityMismatch, RuntimeBackendNotReady
from alas_headless.runtime_backend_adb import AdbAttachedBackend
from test_runtime_backends import ScriptedExecutor, FakeBridge, make_lock, PACKAGE, COMPONENT, HASH


def setup_backend(tmp_path, running=True):
    manager = tmp_path / "manager.ps1"
    manager.write_text("# test manager")
    (tmp_path / "redroid-x86_64.oci-build.json").write_text(json.dumps({"manifest_digest": "sha256:" + HASH}))
    config = WslRedroidRuntimeConfig(serial="127.0.0.1:5556", package=PACKAGE,
        component=COMPONENT, host_class="windows-wsl2-x86_64-redroid",
        container_id="alas-redroid-wsl-projectlocal", image_manifest_digest="sha256:" + HASH,
        userdata_path="/home/test/projectlocal-data", manager_script=str(manager),
        project_artifact_directory=str(tmp_path))
    info = {"Name": "/" + config.container_id, "Image": "sha256:" + HASH,
        "State": {"Running": running}, "Mounts": [{"Source": config.userdata_path,
        "Destination": "/data", "Type": "bind", "RW": True}],
        "HostConfig": {"NetworkMode": "bridge", "PortBindings": {"5555/tcp": [{"HostIp": "127.0.0.1", "HostPort": "5556"}]}}}
    executor = ScriptedExecutor({"wsl-container-inspect": (0, json.dumps([info]), ""),
        "wsl-image-inspect": (0, json.dumps([{"Id": "sha256:" + HASH, "Architecture": "amd64"}]), ""),
        "wsl-project-config": (0, json.dumps(asdict(config)), "")})
    backend = WslRedroidBackend(config, executor)
    backend.resolve_artifacts(make_lock("redroid"))
    return backend, executor, info


def test_factory_and_additive_docker_metadata(tmp_path):
    backend, executor, info = setup_backend(tmp_path)
    info["Labels"] = {"unrelated": "changed"}
    executor.results["wsl-container-inspect"] = (0, json.dumps([info]), "")
    value = dict(asdict(backend.config), schema="alas-headless.runtime-config/v1", backend="redroid", container_engine="wsl-docker")
    assert isinstance(backend_from_config(value, executor), WslRedroidBackend)
    prepared = backend.provision(backend.resolve_artifacts(make_lock("redroid")))
    instance = backend.start(prepared)
    assert instance["owned"] is False
    backend.stop(instance)
    assert not any(call.mutating for call in executor.calls)
    assert all("unix:///var/run/docker.sock" in call.argv for call in executor.calls if "docker" in call.argv)


@pytest.mark.parametrize("damage,code", [("image", "image"), ("data", "userdata"), ("port", "binding"), ("network", "binding")])
def test_wrong_instance_rejected_before_mutation(tmp_path, damage, code):
    backend, executor, info = setup_backend(tmp_path)
    if damage == "image": info["Image"] = "sha256:" + "f" * 64
    if damage == "data": info["Mounts"][0]["Source"] = "/home/test/other-data"
    if damage == "port": info["HostConfig"]["PortBindings"]["5555/tcp"][0]["HostIp"] = "0.0.0.0"
    if damage == "network": info["HostConfig"]["NetworkMode"] = "host"
    executor.results["wsl-container-inspect"] = (0, json.dumps([info]), "")
    with pytest.raises(RuntimeIdentityMismatch, match=code): backend._manager("start", "Start")
    assert not any(call.mutating for call in executor.calls)


def test_manager_target_must_match_selected_container(tmp_path):
    backend, executor, _ = setup_backend(tmp_path)
    other = dict(asdict(backend.config), container_id="another-container")
    executor.results["wsl-project-config"] = (0, json.dumps(other), "")
    with pytest.raises(RuntimeIdentityMismatch, match="manager-target"):
        backend._manager("start", "Start")
    assert not any(call.mutating for call in executor.calls)


def test_restart_uses_stop_offline_start_order(tmp_path):
    backend, executor, info = setup_backend(tmp_path)
    instance = backend.start({"initially_running": True, "image_manifest_digest": backend.config.image_manifest_digest})
    with patch.object(backend, "_stop_task") as stop, patch.object(backend, "_start_runtime") as start:
        backend.restart_android(instance)
        stop.assert_called_once()
        start.assert_not_called()
        executor.results["adb-restart-boundary"] = (1, "", "offline")
        assert backend.wait_android_offline(instance, 1)["adb_offline_observed"]
        start.assert_called_once()
    assert backend.supports_recovery("game") and backend.supports_recovery("android")


def test_native_empty_login_is_not_observer_ready(tmp_path):
    backend, executor, _ = setup_backend(tmp_path)
    native = PACKAGE + "/com.gsc.phone_login.PhoneLoginActivity"
    xml = '<?xml version="1.0"?><hierarchy><node package="%s" class="android.widget.EditText" text="请输入手机号"/><node package="%s" text="下一步" enabled="false"/></hierarchy>' % (PACKAGE, PACKAGE)
    executor.results.update({"wsl-login-ui": (0, xml, ""), "wsl-android-accounts": (0, "Accounts: 0", "")})
    with patch.object(backend, "_foreground", return_value=(123, native, "")):
        assert backend.inspect_login_boundary()["observer_ready"] is False
        executor.results["wsl-login-ui"] = (0, xml.replace('enabled="false"', 'enabled="true"'), "")
        with pytest.raises(RuntimeBackendNotReady, match="not-empty"): backend.inspect_login_boundary()
    assert not any(call.mutating for call in executor.calls)


@pytest.mark.parametrize("component,history", [(COMPONENT, ""), (PACKAGE + "/OtherActivity", "mLastPausedActivity: " + PACKAGE + "/com.gsc.announcement.AnnouncementActivity")])
def test_sdk_recovery_rejects_unrelated_activity(tmp_path, component, history):
    backend, executor, _ = setup_backend(tmp_path)
    with patch.object(backend, "_foreground", return_value=(1234, component, history)):
        with pytest.raises(RuntimeBackendNotReady, match="preconditions"):
            backend._recover_sdk_pause({"instance_id": "one"})
    assert not any(call.mutating for call in executor.calls)


def test_sdk_recovery_preserves_pid_and_unity_extra(tmp_path):
    backend, executor, _ = setup_backend(tmp_path)
    class UnavailableBridge(FakeBridge):
        def request(self, _): return {"package": PACKAGE, "pid": 1234, "status": "unavailable"}
    backend.bridge_factory = UnavailableBridge
    history = "mLastPausedActivity: " + PACKAGE + "/com.gsc.announcement.AnnouncementActivity"
    home = "com.android.launcher3/.Launcher"
    executor.results["wsl-home-resolve"] = (0, home, "")
    states = [(1234, COMPONENT, history), (1234, COMPONENT, history), (1234, home, ""), (1234, COMPONENT, history)]
    with patch.object(backend, "_foreground", side_effect=states):
        assert backend._recover_sdk_pause({"instance_id": "one"})["pid_preserved"]
    mutations = [call for call in executor.calls if call.mutating]
    assert [call.label for call in mutations] == ["wsl-sdk-home", "wsl-sdk-reentry"]
    assert "\\-force-gfx-st" in mutations[-1].argv


@pytest.mark.parametrize("fatal,live", [(True, False), (False, True)])
def test_sdk_recovery_never_reenters_fatal_or_healthy_game(tmp_path, fatal, live):
    backend, executor, _ = setup_backend(tmp_path)
    class SnapshotBridge(FakeBridge):
        def request(self, _):
            return {"package": PACKAGE, "pid": 1234, "status": "ok" if live else "unavailable", "age_ms": 20}
    backend.bridge_factory = SnapshotBridge
    executor.results["wsl-game-fatal-probe"] = (0, "FATAL EXCEPTION: main" if fatal else "", "")
    history = "mLastPausedActivity: " + PACKAGE + "/com.gsc.announcement.AnnouncementActivity"
    with patch.object(backend, "_foreground", return_value=(1234, COMPONENT, history)):
        with pytest.raises(RuntimeBackendNotReady, match="fatal|not-stale"):
            backend._recover_sdk_pause({"instance_id": "one"})
    assert not any(call.mutating for call in executor.calls)


def test_reentry_is_once_per_cold_launch(tmp_path):
    backend, executor, _ = setup_backend(tmp_path)
    instance = {"instance_id": "one"}
    with patch.object(backend, "_observer_progress", side_effect=RuntimeBackendNotReady("observer-ready-timeout")), patch.object(backend, "_recover_sdk_pause", return_value={}) as recover:
        with pytest.raises(RuntimeBackendNotReady): backend.wait_observer_ready(instance, 1)
        with pytest.raises(RuntimeBackendNotReady, match="already-attempted"): backend.wait_observer_ready(instance, 1)
        assert recover.call_count == 1
        backend._prepare_game_cold_launch(instance)
        with pytest.raises(RuntimeBackendNotReady): backend.wait_observer_ready(instance, 1)
        assert recover.call_count == 2


@pytest.mark.parametrize("damage", [None, "pid", "schema", "stale"])
def test_observer_progress_rechecks_live_contract(tmp_path, damage):
    backend, executor, _ = setup_backend(tmp_path)
    class ProgressBridge(FakeBridge):
        def request(self, request):
            response = super().request(request)
            response["snapshot"].update(generation=11, age_ms=10, extra_harmless_field=True)
            response["buttons"]["generation"] = 11
            if damage == "pid": response["buttons"]["pid"] = 999
            if damage == "schema": response["buttons"]["semantic_schema"] = "unknown"
            if damage == "stale": response["snapshot"]["age_ms"] = 10000
            return response
    backend._bridges["one"] = ProgressBridge(backend.serial, PACKAGE)
    ticks = itertools.count(step=0.1)
    backend.monotonic = lambda: next(ticks)
    backend.sleep = lambda _: None
    initial = {"pid": 1234, "generation": 10, "atomic": True}
    with patch.object(AdbAttachedBackend, "wait_observer_ready", return_value=initial), patch.object(backend, "_foreground", return_value=(1234, COMPONENT, "")):
        if damage is None:
            assert backend._observer_progress({"instance_id": "one"}, 1)["generation"] == 11
        else:
            with pytest.raises((RuntimeIdentityMismatch, RuntimeBackendNotReady)):
                backend._observer_progress({"instance_id": "one"}, 1)
