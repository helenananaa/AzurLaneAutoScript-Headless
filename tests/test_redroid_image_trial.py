import json
import os
from pathlib import Path
import shutil
import subprocess
from unittest.mock import Mock, patch

import pytest

from alas_headless.redroid_image_trial import RedroidImageTrial, TrialBackend
from alas_headless.runtime_backends import RuntimeBackendNotReady, RuntimeIdentityMismatch
from test_runtime_backend_redroid_wsl import setup_backend
from test_runtime_backends import make_lock, HASH


def make_trial(tmp_path):
    source, executor, info = setup_backend(tmp_path)
    trial = RedroidImageTrial(source, make_lock("redroid"), "sha256:" + "f" * 64, tmp_path / "evidence")
    return trial, source, executor, info


def test_plan_requires_real_image_content_change_and_no_mutation(tmp_path):
    trial, _, executor, _ = make_trial(tmp_path)
    base = {"Id": "sha256:" + HASH, "RootFS": {"Layers": ["layer-a"]}, "Architecture": "amd64", "Os": "linux"}
    candidate = dict(base, Id="sha256:" + "f" * 64)
    with patch.object(trial, "_docker", side_effect=lambda label, *args: json.dumps([candidate if "candidate" in label else base])), patch.object(trial, "_overlay") as overlay:
        with pytest.raises(RuntimeIdentityMismatch, match="distinct-image-content"):
            trial.plan()
        candidate["RootFS"] = {"Layers": ["layer-b"]}
        assert trial.plan()["image_layers_differ"]
        overlay.assert_called_once_with("check")
    assert not any(call.mutating for call in executor.calls)


@pytest.mark.parametrize("fail_stage,cleanup_fails", [(None, False), ("candidate", False), ("baseline", False), (None, True)])
def test_trial_rollback_and_failure_cleanup_order(tmp_path, fail_stage, cleanup_fails):
    trial, source, _, _ = make_trial(tmp_path)
    events = []

    def overlay(action):
        events.append("overlay:" + action)
        if action == "cleanup" and cleanup_fails:
            raise RuntimeBackendNotReady("busy-overlay")

    def stage(name, *args):
        events.append("stage:" + name)
        if name == fail_stage:
            raise RuntimeBackendNotReady("stage-boot-failed")

    with patch.object(trial, "plan", return_value={}), patch.object(trial, "_inspect_candidate_storage"), patch.object(source, "inspect_login_boundary", return_value={"android_account_count": 0}), \
        patch.object(source, "_stop_task", side_effect=lambda _: events.append("source-stop")), \
        patch.object(source, "_start_runtime", side_effect=lambda _: events.append("source-start")), \
        patch.object(trial, "_docker", return_value=""), patch.object(trial, "_witness", return_value={"file": HASH}), \
        patch.object(trial, "_overlay", side_effect=overlay), patch.object(trial, "_stage", side_effect=stage), \
        patch.object(trial, "_stop_lab", side_effect=lambda: events.append("lab-stop")), \
        patch.object(trial, "_exists", side_effect=[True, True, True, True, False]), \
        patch.object(trial, "_login"), patch("alas_headless.redroid_image_trial.subprocess.Popen", return_value=Mock()):
        report = trial.execute()
    assert events.index("source-stop") < events.index("overlay:base")
    assert events.index("lab-stop") < events.index("overlay:cleanup")
    if cleanup_fails:
        assert "source-start" not in events  # Never resume lowerdir writers under a live overlay.
        assert not report["passed"]
    else:
        assert events.index("overlay:cleanup") < events.index("source-start")
        assert report["passed"] == (fail_stage is None)
    if fail_stage is None:
        assert events.index("stage:baseline") < events.index("stage:candidate") < events.index("stage:rollback")
        assert report["baseline_state_restored"]
    assert "overlay:keepalive-stop" in events


def test_stop_failure_still_attempts_original_project_restore(tmp_path):
    trial, source, _, _ = make_trial(tmp_path)
    with patch.object(trial, "plan", return_value={}), patch.object(trial, "_inspect_candidate_storage"), patch.object(source, "inspect_login_boundary", return_value={}), \
        patch.object(source, "_stop_task", side_effect=RuntimeBackendNotReady("stop-response-lost")), \
        patch.object(source, "_start_runtime") as restore, patch.object(trial, "_login"), \
        patch.object(trial, "_overlay"), patch("alas_headless.redroid_image_trial.subprocess.Popen", return_value=Mock()):
        report = trial.execute()
    restore.assert_called_once()
    assert not report["passed"]


def test_trial_dynamic_port_uses_effective_loopback_binding(tmp_path):
    _, source, executor, info = make_trial(tmp_path)
    info["HostConfig"]["PortBindings"]["5555/tcp"][0]["HostPort"] = ""
    info["NetworkSettings"] = {"Ports": {"5555/tcp": [{"HostIp": "127.0.0.1", "HostPort": "5556"}]}}
    executor.results["wsl-container-inspect"] = (0, json.dumps([info]), "")
    backend = TrialBackend(source.config, executor)
    backend._validate_container_and_userdata()
    info["NetworkSettings"]["Ports"]["5555/tcp"][0]["HostIp"] = "0.0.0.0"
    executor.results["wsl-container-inspect"] = (0, json.dumps([info]), "")
    with pytest.raises(RuntimeIdentityMismatch, match="binding"):
        backend._validate_container_and_userdata()


def test_cleanup_cannot_remove_another_container(tmp_path):
    trial, _, _, _ = make_trial(tmp_path)
    trial.created_container = True
    with patch.object(trial, "_docker", return_value=json.dumps([{"Config": {"Labels": {}}}])) as docker:
        with pytest.raises(RuntimeIdentityMismatch, match="ownership"):
            trial._stop_lab()
    assert all(call.args[0] != "trial-container-remove" for call in docker.call_args_list)


def test_retired_storage_rejected_without_stopping_project(tmp_path):
    trial, source, _, _ = make_trial(tmp_path)
    with patch.object(trial, "plan", return_value={}), \
        patch.object(trial, "_inspect_candidate_storage", side_effect=RuntimeBackendNotReady("candidate-requires-retired-block-or-fbe-storage")), \
        patch.object(source, "_stop_task") as stop:
        report = trial.execute()
    stop.assert_not_called()
    assert not report["passed"] and "retired" in report["failure"]["code"]


@pytest.mark.parametrize("fstab,rejected", [
    ("/dev/block/alas_userdata /data ext4 noatime wait,fileencryption=aes-256-xts\n", True),
    ("/dev/block/alas_metadata /metadata ext4 noatime wait\n", True),
    ("# fileencryption= is historical, not enabled here\n", False),
])
def test_storage_inspection_rejects_active_layout_but_allows_comments(tmp_path, fstab, rejected):
    trial, _, _, _ = make_trial(tmp_path)
    trial.output.mkdir()
    (trial.output / "candidate-fstab.redroid").write_text(fstab, encoding="utf-8")
    with patch.object(trial, "_docker", return_value="temporary-inspection-id") as docker, patch.object(trial, "_run", return_value="/tmp/inspection-output"):
        if rejected:
            with pytest.raises(RuntimeBackendNotReady, match="retired"):
                trial._inspect_candidate_storage()
        else:
            trial._inspect_candidate_storage()
            assert not trial.report["candidate_storage"]["retired_block_or_fbe_layout"]
    assert docker.call_args_list[-1].args[:2] == ("trial-storage-remove", "rm")


@pytest.mark.parametrize("source,lab,success", [("/", "/rollback-labs/run-test", False), ("/tmp", "/tmp/wrong/run-test", False), ("/tmp", "/rollback-labs/run-test", True)])
def test_overlay_path_boundary_is_read_only(source, lab, success):
    helper = Path(__file__).resolve().parents[1] / "scripts/wsl/manage-redroid-rollback-overlay.sh"
    if os.name == "nt":
        if not shutil.which("wsl.exe"):
            pytest.skip("WSL unavailable")
        shell = ["wsl.exe", "-d", "Ubuntu-22.04", "--", "bash", "-s", "--"]
    else:
        shell = ["bash", "-s", "--"]
    result = subprocess.run(shell + ["check", source, lab], input=helper.read_bytes(), capture_output=True, timeout=15)
    assert (result.returncode == 0) is success
