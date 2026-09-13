"""Local image A/B/A rehearsal with a frozen Project /data lower directory.

The image trial owns only temporary containers and overlay mounts. All game
launch and semantic checks reuse the normal WSL runtime backend.
"""
from __future__ import annotations

from dataclasses import replace
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import time
import uuid

from .runtime_backend_adb import AdbAttachedBackend, RuntimeBackendNotReady, RuntimeIdentityMismatch
from .runtime_backend_redroid_wsl import WslRedroidBackend


class TrialBackend(WslRedroidBackend):
    """The harness preprovisions this temporary container, not Project manager."""

    def _container_info(self):
        info = dict(super()._container_info())
        # Docker records an empty requested HostPort for dynamic publication;
        # validate the effective runtime binding discovered after start instead.
        host = dict(info.get("HostConfig", {}))
        requested = host.get("PortBindings", {}).get("5555/tcp")
        if requested == [{"HostIp": "127.0.0.1", "HostPort": ""}]:
            effective = info.get("NetworkSettings", {}).get("Ports", {}).get("5555/tcp")
            host["PortBindings"] = dict(host["PortBindings"], **{"5555/tcp": effective})
            info["HostConfig"] = host
        return info

    def provision(self, artifacts):
        result = dict(AdbAttachedBackend.provision(self, artifacts))
        self._validate_container_and_userdata()
        result["initially_running"] = self._task_running()
        return result

    def _manager(self, label, action):
        raise RuntimeBackendNotReady("trial-container-lifecycle-owned-by-harness")

    def supports_recovery(self, recovery):
        return recovery == "game" and self.config.allow_game_restart


class RedroidImageTrial:
    def __init__(self, source: WslRedroidBackend, runtime_lock, candidate_image: str, output: Path):
        if not re.fullmatch(r"sha256:[0-9a-f]{64}", candidate_image):
            raise ValueError("trial candidate must be an exact cached Docker image ID")
        self.source = source
        self.lock = runtime_lock
        self.candidate = candidate_image
        self.output = output
        self.run_id = "run-" + uuid.uuid4().hex[:12]
        self.container = "alas-redroid-rollback-" + self.run_id
        self.lab = str(PurePosixPath(source.config.userdata_path).parent / "rollback-labs" / self.run_id)
        self.label = "io.github.alas-headless.rollback-run"
        self.root = Path(__file__).resolve().parents[2]
        self.helper = str(self.root / "scripts/wsl/manage-redroid-rollback-overlay.sh")
        self.helper_wsl = None
        self.created_container = False
        self.source_stopped = False
        self.overlay_started = False
        self.keepalive = None
        self.report = {"schema": "alas-headless.redroid-wsl-image-trial/v1", "run_id": self.run_id,
            "scope": "local-wsl-overlay-image-rollback-rehearsal", "passed": False,
            "candidate_image": candidate_image, "source_image": source.config.image_manifest_digest,
            "source_userdata": source.config.userdata_path, "lab_root": self.lab,
            "account_input_injected": False, "gameplay_inputs": 0, "stages": []}

    def _run(self, label, argv, *, mutating=False, timeout=60):
        result = self.source._command(label, argv, timeout, mutating)
        return self.source._require_success(result, label + "-failed")

    def _docker(self, label, *argv, mutating=False, timeout=60):
        return self._run(label, (self.source.config.wsl, "-d", self.source.config.distro,
            "--", "docker", "--host", "unix:///var/run/docker.sock") + argv, mutating=mutating, timeout=timeout)

    def _overlay(self, action):
        if self.helper_wsl is None:
            self.helper_wsl = self._run("trial-helper-path", (self.source.config.wsl, "-d", self.source.config.distro,
                "--", "wslpath", "-a", "-u", self.helper.replace("\\", "/")))
        root_args = () if action in ("check", "keepalive-stop") else ("-u", "root")
        return self._run("trial-overlay-" + action, (self.source.config.wsl, "-d", self.source.config.distro) + root_args +
            ("--", "bash", self.helper_wsl, action, self.source.config.userdata_path, self.lab),
            mutating=action != "check")

    def _checkpoint(self):
        self.output.mkdir(parents=True, exist_ok=True)
        (self.output / "manifest.json").write_text(json.dumps(self.report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    def plan(self):
        source = self.source._validate_image_and_container()
        candidate = json.loads(self._docker("trial-candidate-inspect", "image", "inspect", self.candidate))[0]
        baseline = json.loads(self._docker("trial-baseline-inspect", "image", "inspect", self.source.config.image_manifest_digest))[0]
        if candidate["Id"] == baseline["Id"] or candidate["RootFS"]["Layers"] == baseline["RootFS"]["Layers"]:
            raise RuntimeIdentityMismatch("rollback-trial-needs-distinct-image-content")
        if candidate.get("Architecture") != "amd64" or candidate.get("Os") != "linux":
            raise RuntimeIdentityMismatch("rollback-trial-image-platform-mismatch")
        self._overlay("check")
        return {"source_container": source["Name"], "source_image": baseline["Id"], "candidate_image": candidate["Id"],
            "candidate_kind": "controlled-fixture" if candidate.get("Config", {}).get("Labels", {}).get("io.github.alas-headless.qualification-fixture") == "rollback-only" else "retained-image",
            "image_layers_differ": True, "lab_root": self.lab, "source_userdata_read_only_during_trial": True,
            "full_resource_copy": False, "download_images": False, "build_images": False,
            "sequence": ["stop-project", "current-image-on-base-overlay", "candidate-on-child-overlay", "rollback-to-base-overlay", "restore-project"]}

    def _lab_info(self):
        info = json.loads(self._docker("trial-container-inspect", "container", "inspect", self.container))[0]
        if info.get("Config", {}).get("Labels", {}).get(self.label) != self.run_id:
            raise RuntimeIdentityMismatch("trial-container-ownership-mismatch")
        return info

    def _inspect_candidate_storage(self):
        """Reject the known retired block/FBE layout before stopping Project.

        A stopped metadata-only container lets Docker read one small file;
        Android never starts and no userdata is attached to this inspection.
        """
        inspect_id = self._docker("trial-storage-create", "create", "--name", self.container + "-inspect",
            "--pull=never", self.candidate, mutating=True)
        try:
            self.output.mkdir(parents=True, exist_ok=True)
            target = self.output / "candidate-fstab.redroid"
            target_wsl = self._run("trial-storage-output", (self.source.config.wsl, "-d", self.source.config.distro,
                "--", "wslpath", "-a", "-u", str(target.resolve()).replace("\\", "/")))
            result = self.source._command("trial-storage-copy", (self.source.config.wsl, "-d", self.source.config.distro,
                "--", "docker", "--host", "unix:///var/run/docker.sock", "cp", inspect_id + ":/vendor/etc/fstab.redroid", target_wsl), mutating=True)
            if result.succeeded:
                text = target.read_text(encoding="utf-8")
                entries = "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))
                legacy = any(token in entries for token in ("fileencryption=", "metadata_encryption", "/dev/block/alas_userdata", "/dev/block/alas_metadata"))
                self.report["candidate_storage"] = {"fstab_present": True, "retired_block_or_fbe_layout": legacy}
                if legacy:
                    raise RuntimeBackendNotReady("candidate-requires-retired-block-or-fbe-storage")
            elif "Could not find the file" in result.stderr:
                self.report["candidate_storage"] = {"fstab_present": False, "retired_block_or_fbe_layout": False}
            else:
                raise RuntimeBackendNotReady("candidate-storage-inspection-failed")
        finally:
            self._docker("trial-storage-remove", "rm", inspect_id, mutating=True)

    def _stop_lab(self):
        if not self.created_container:
            return
        info = self._lab_info()
        if info["State"]["Running"]:
            self._docker("trial-container-stop", "stop", "--time", "10", self.container, mutating=True)
        self._docker("trial-container-remove", "rm", self.container, mutating=True)
        self.created_container = False

    def _diagnose_lab(self):
        """Retain failure context before the temporary container is removed."""
        if not self.created_container:
            return
        diagnostics = {}
        try:
            info = self._lab_info()
            diagnostics["container"] = {key: info.get(key) for key in ("State", "Image", "Mounts", "NetworkSettings")}
        except Exception as exc:
            diagnostics["inspect_error"] = str(exc)
        for name, argv in (
            ("boot_completed", ("exec", self.container, "/system/bin/getprop", "sys.boot_completed")),
            ("adbd_state", ("exec", self.container, "/system/bin/getprop", "init.svc.adbd")),
            ("android_log", ("exec", self.container, "/system/bin/logcat", "-d", "-b", "main", "-b", "system", "-t", "60")),
            ("init_log", ("logs", "--tail", "100", self.container)),
        ):
            try:
                # Docker may write init errors to stderr; preserve both streams.
                result = self.source._command("trial-diagnose-" + name, (self.source.config.wsl, "-d", self.source.config.distro,
                    "--", "docker", "--host", "unix:///var/run/docker.sock") + argv, timeout_seconds=10)
                diagnostics[name] = {"returncode": result.returncode, "stdout": result.stdout, "stderr": result.stderr}
            except Exception as exc:
                diagnostics[name] = {"error": str(exc)}
        self.report["failure_diagnostics"] = diagnostics

    def _witness(self):
        # Small existing control files witness lowerdir preservation without
        # rescanning or hashing the entire public-resource tree.
        paths = ("system/packages.xml", "system/users/0/settings_secure.xml",
            "media/0/Android/data/" + self.source.package + "/files/version.txt")
        result = {}
        for relative in paths:
            result[relative] = self._run("trial-source-witness", (self.source.config.wsl, "-d", self.source.config.distro,
                "-u", "root", "--", "sha256sum", self.source.config.userdata_path + "/" + relative)).split()[0]
        return result

    def _login(self, backend, instance, stage):
        backend.wait_adb(instance, 30)
        backend.wait_android_ready(instance, 90)
        backend.wait_game_ready(instance, 60)
        deadline = time.monotonic() + 100
        while True:
            try:
                observer = dict(backend.wait_observer_ready(instance, 30))
                stage.setdefault("observer_samples", []).append(observer)
            except RuntimeBackendNotReady as exc:
                if exc.code != "observer-main-activity-not-foreground":
                    raise
            try:
                boundary = dict(backend.inspect_login_boundary())
                if not stage.get("observer_samples"):
                    raise RuntimeBackendNotReady("trial-observer-not-observed-before-login")
                stage["login_boundary"] = boundary
                return
            except RuntimeBackendNotReady as exc:
                if exc.code != "sdk-login-not-foreground" or time.monotonic() >= deadline:
                    raise
            time.sleep(4)

    def _stage(self, name, image, data):
        started = time.monotonic()
        self._docker("trial-container-create", "create", "--name", self.container,
            "--label", self.label + "=" + self.run_id, "--privileged", "--restart", "no", "--pull=never",
            "--mount", "type=bind,src=" + data + ",dst=/data", "-p", "127.0.0.1::5555", image,
            "androidboot.redroid_width=1280", "androidboot.redroid_height=720", "androidboot.redroid_dpi=240",
            "androidboot.redroid_gpu_mode=guest", mutating=True)
        self.created_container = True
        self._docker("trial-container-start", "start", self.container, mutating=True)
        info = self._lab_info()
        bindings = info.get("NetworkSettings", {}).get("Ports", {}).get("5555/tcp")
        if not isinstance(bindings, list) or len(bindings) != 1 or bindings[0].get("HostIp") != "127.0.0.1":
            raise RuntimeIdentityMismatch("trial-adb-binding-mismatch")
        serial = "127.0.0.1:" + bindings[0]["HostPort"]
        config = replace(self.source.config, container_id=self.container, image_manifest_digest=image, userdata_path=data,
            serial=serial, allow_android_restart=False)
        backend = TrialBackend(config, self.source.executor)
        instance = backend.start(backend.provision(backend.resolve_artifacts(self.lock)))
        stage = {"name": name, "image": image, "serial": serial, "data_overlay": data}
        self.report["stages"].append(stage)
        self._checkpoint()
        try:
            self._login(backend, instance, stage)
            upper = str(PurePosixPath(data).parent / "upper")
            stage["scratch_upper_kib"] = int(self._run("trial-scratch-size", (self.source.config.wsl, "-d", self.source.config.distro,
                "-u", "root", "--", "du", "-sk", upper)).split()[0])
            if self.report["plan"]["candidate_kind"] == "controlled-fixture":
                present = self._exists("/system/etc/alas-rollback-fixture.txt")
                stage["controlled_image_marker_present"] = present
                if present != (name == "candidate"):
                    raise RuntimeIdentityMismatch("trial-image-marker-mismatch")
            stage["elapsed_seconds"] = round(time.monotonic() - started, 3)
            print(name + ": semantic observer and empty login passed", flush=True)
            self._checkpoint()
        finally:
            backend.stop(instance)
            self._run("trial-adb-disconnect", (config.adb, "-P", str(config.adb_server_port), "disconnect", serial), mutating=True)

    def _exists(self, path):
        result = self.source._command("trial-sentinel-read", (self.source.config.wsl, "-d", self.source.config.distro,
            "--", "docker", "--host", "unix:///var/run/docker.sock", "exec", self.container, "/system/bin/test", "-f", path))
        if result.returncode not in (0, 1):
            raise RuntimeBackendNotReady("trial-sentinel-observation-failed")
        return result.returncode == 0

    def execute(self):
        implementation = (Path(__file__).resolve(), Path(self.helper).resolve())
        self.report["implementation_sha256"] = {str(path.relative_to(self.root)): hashlib.sha256(path.read_bytes()).hexdigest() for path in implementation}
        baseline_marker = "/data/local/tmp/" + self.run_id + "-baseline"
        candidate_marker = "/data/local/tmp/" + self.run_id + "-candidate"
        try:
            self.report["plan"] = self.plan()
            self._inspect_candidate_storage()
            self.report["initial_login_boundary"] = dict(self.source.inspect_login_boundary())
            # Own the keepalive separately: stopping Project may release its own.
            self.keepalive = subprocess.Popen([self.source.config.wsl, "-d", self.source.config.distro,
                "--", "bash", self.helper_wsl, "keepalive", self.source.config.userdata_path, self.lab],
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            self.source_stopped = True
            self.source._stop_task("image-trial-project-stop")
            if self._docker("trial-lowerdir-users", "ps", "--filter", "volume=" + self.source.config.userdata_path, "-q"):
                raise RuntimeBackendNotReady("trial-source-userdata-still-in-use")
            self.report["source_witness_before"] = self._witness()
            self._overlay("base")
            self.overlay_started = True
            self._stage("baseline", self.source.config.image_manifest_digest, self.lab + "/base/merged")
            self._docker("trial-baseline-marker", "exec", self.container, "/system/bin/touch", baseline_marker, mutating=True)
            if not self._exists(baseline_marker):
                raise RuntimeBackendNotReady("trial-baseline-marker-missing")
            self._stop_lab()
            self._overlay("candidate")
            self._stage("candidate", self.candidate, self.lab + "/candidate/merged")
            if not self._exists(baseline_marker):
                raise RuntimeBackendNotReady("trial-candidate-lost-baseline-state")
            self._docker("trial-candidate-marker", "exec", self.container, "/system/bin/touch", candidate_marker, mutating=True)
            if not self._exists(candidate_marker):
                raise RuntimeBackendNotReady("trial-candidate-marker-missing")
            self._stop_lab()
            self._overlay("rollback")
            self._stage("rollback", self.source.config.image_manifest_digest, self.lab + "/base/merged")
            self.report["baseline_state_restored"] = self._exists(baseline_marker) and not self._exists(candidate_marker)
            if not self.report["baseline_state_restored"]:
                raise RuntimeBackendNotReady("trial-snapshot-state-not-restored")
            self._stop_lab()
            self.report["source_witness_after"] = self._witness()
            if self.report["source_witness_after"] != self.report["source_witness_before"]:
                raise RuntimeIdentityMismatch("trial-source-witness-changed")
            self.report["passed"] = True
        except Exception as exc:
            self.report["failure"] = {"type": type(exc).__name__, "code": getattr(exc, "code", str(exc))}
            self._diagnose_lab()
            print("trial failed: " + str(self.report["failure"]), flush=True)
        finally:
            try:
                self._stop_lab()
                if self.overlay_started:
                    self._overlay("cleanup")
                self.report["lab_cleaned"] = True
                if self.source_stopped:
                    self.source._start_runtime("image-trial-project-restore")
                    instance = self.source.start(self.source.provision(self.source.resolve_artifacts(self.lock)))
                    try:
                        restored = {"name": "original-project-restored"}
                        self._login(self.source, instance, restored)
                        self.report["original_project_restored"] = restored
                    finally:
                        self.source.stop(instance)
            except Exception as exc:
                self.report["passed"] = False
                self.report["cleanup_failure"] = {"type": type(exc).__name__, "code": getattr(exc, "code", str(exc))}
            if self.keepalive is not None:
                try:
                    self._overlay("keepalive-stop")
                    self.keepalive.wait(timeout=10)
                except Exception as exc:
                    self.report["passed"] = False
                    self.report["keepalive_cleanup_error"] = str(exc)
                    self.keepalive.terminate()
            self.report["implementation_unchanged_during_run"] = all(hashlib.sha256(path.read_bytes()).hexdigest() == self.report["implementation_sha256"][str(path.relative_to(self.root))] for path in implementation)
            if not self.report["implementation_unchanged_during_run"]:
                self.report["passed"] = False
            self._checkpoint()
        return self.report
