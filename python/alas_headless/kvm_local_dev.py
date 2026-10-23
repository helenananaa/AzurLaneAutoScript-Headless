"""Local KVM lifecycle CLI; ALAS continues to own all game task execution."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import shlex
import socket
import subprocess
import sys
import time

from .runtime_backends import backend_from_config
from .runtime_command import RuntimeCommandExecutor, RuntimeExecutionPolicy
from .oracle.transport import AdbObserverBridge, observer_snapshot_semantic_ready
from .oracle.contracts import OBSERVER_SCHEMA

ROOT = Path(__file__).resolve().parents[2]


class LocalKvm:
    def __init__(self, config: Path, domain: Path, profile: Path):
        self.path = config.resolve()
        self.backend = backend_from_config(
            json.loads(self.path.read_text(encoding="utf-8")),
            RuntimeCommandExecutor(RuntimeExecutionPolicy(True, True)),
            sleep=self._sleep_while_running,
        )
        if self.backend.profile.backend.value != "kvm":
            raise ValueError("local manager requires a KVM config")
        self.config = self.backend.config
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", self.config.avd_name):
            raise ValueError("AVD name is not a valid systemd unit identifier")
        self.unit = "alas-kvm-dev-" + self.config.avd_name + ".service"
        self.domain, self.profile = domain.resolve(), profile.resolve()
        self.control = self.config.runtime_release_root.parent.parent / "control" / self.config.avd_name

    @staticmethod
    def command(argv, timeout=30, check=True):
        result = subprocess.run(argv, text=True, capture_output=True, timeout=timeout)
        if check and result.returncode:
            raise RuntimeError(result.stderr.strip() or result.stdout.strip() or f"command failed: {argv[0]}")
        return result

    def service(self):
        value = self.command([
            "systemctl", "show", self.unit, "--property=LoadState,ActiveState,SubState,Result,MainPID,ExecMainStatus,Environment",
        ], check=False)
        fields = dict(line.split("=", 1) for line in value.stdout.splitlines() if "=" in line)
        if not fields:
            raise RuntimeError(value.stderr.strip() or "systemd state unavailable")
        return fields

    def require_owned_service(self, fields):
        if f"ALAS_KVM_CONFIG={self.path}" not in shlex.split(fields.get("Environment", "")):
            raise RuntimeError("service belongs to a different runtime config; refusing to control it")

    def require_running_service(self):
        service = self.service()
        if int(service.get("MainPID", "0")) == 0:
            raise RuntimeError(
                f"KVM service is not running (result={service.get('Result')}, "
                f"exit={service.get('ExecMainStatus')}); see journalctl -u {self.unit}"
            )
        self.require_owned_service(service)
        return service

    def _sleep_while_running(self, seconds):
        # Reuse backend readiness loops, but do not wait minutes after their
        # owning VM service has already failed. No extra game workflow exists.
        self.require_running_service()
        time.sleep(seconds)

    def require_runtime_mount(self):
        # This local build domain is on the VHDX required by AGENTS.md. Check
        # inside the selected distribution before creating any control files;
        # mounting it in another WSL distribution is insufficient.
        observed = self.command([
            "findmnt", "-rn", "-o", "UUID", "--target",
            str(self.config.runtime_release_root.parent.parent),
        ]).stdout.strip()
        if observed != "7febc493-864e-4e35-a01c-3090515de95e":
            raise RuntimeError("KVM VHDX is not mounted in this distribution; no runtime files were created")

    def adb(self, *args, device=True, check=True, timeout=15):
        argv = [str(self.config.adb), "-P", str(self.config.adb_server_port)]
        if device:
            argv += ["-s", self.backend.serial]
        return self.command(argv + list(args), timeout=timeout, check=check)

    def close_unused_adb_server(self):
        inventory = self.adb("devices", device=False, check=False)
        if inventory.returncode == 0 and not inventory.stdout.strip().splitlines()[1:]:
            self.adb("kill-server", device=False, check=False)

    def cleanup_failed_service_adb(self):
        service = self.service()
        if int(service.get("MainPID", "0")) == 0 and service.get("ActiveState") == "failed":
            self.require_owned_service(service)
            self.adb("disconnect", self.backend.serial, device=False, check=False)
            self.close_unused_adb_server()

    def status(self, inspect_guest=True):
        service = self.service()
        running = int(service.get("MainPID", "0")) > 0
        failed = (service.get("ActiveState") == "failed"
                  or service.get("Result", "success") not in ("", "success")
                  or service.get("ExecMainStatus", "0") not in ("", "0"))
        result = {"unit": self.unit, "avd": self.config.avd_name,
                  "release": self.config.runtime_release_root.name,
                  "running": running, "service": {k:v for k,v in service.items() if k!="Environment"},
                  "state": "starting" if running else ("failed" if failed else "stopped")}
        if failed:
            result["failure_log"] = str(self.control / "launcher.log")
            result["journal_unit"] = self.unit
        if service.get("ActiveState") == "deactivating":
            return {**result, "state":"stopping"}
        if not running or not inspect_guest:
            return result
        self.require_owned_service(service)
        try:
            inventory = self.adb("devices", "-l", device=False, check=False, timeout=5)
            result["devices"] = inventory.stdout.strip()
            result["serial"] = self.backend.serial
            transport = self.adb("get-state", check=False, timeout=5)
            if transport.returncode != 0 or transport.stdout.strip() != "device":
                return {**result, "state":"adb-disconnected", "android_ready":False,
                        "transport_error":transport.stderr.strip() or transport.stdout.strip(),
                        "recovery":"Reconnect"}
            boot = self.adb("shell", "getprop", "sys.boot_completed", check=False, timeout=5)
        except (subprocess.TimeoutExpired, OSError) as exc:
            return {**result, "state":"adb-unavailable", "android_ready":False,
                    "observation_error":str(exc), "recovery":"Reconnect"}
        result["android_ready"] = boot.returncode == 0 and boot.stdout.strip() == "1"
        if not result["android_ready"]:
            return result
        bridge = AdbObserverBridge(self.backend.serial, self.config.package,
                                   adb=str(self.config.adb), adb_server_port=self.config.adb_server_port,
                                   command_timeout_seconds=5)
        try:
            foreground = bridge.foreground_component()
            result["foreground"] = foreground
            if foreground == self.config.package + "/com.gsc.phone_login.PhoneLoginActivity":
                result.update(state="login-required", observer="paused-at-native-login")
            elif foreground != self.config.component:
                result.update(state="android-ready", observer="game-not-foreground")
            else:
                bridge.open()
                value = bridge.request("GET /v1/state\n")
                snap, buttons = value.get("snapshot", {}), value.get("buttons", {})
                healthy = (value.get("status") == "ok" and observer_snapshot_semantic_ready(snap)
                           and all(part.get("protocol_schema") == OBSERVER_SCHEMA for part in (value, snap, buttons))
                           and snap.get("status") == buttons.get("status") == "ok"
                           and snap.get("package") == self.config.package
                           and buttons.get("package") == self.config.package
                           and snap.get("pid") == bridge.pid == buttons.get("pid")
                           and snap.get("generation") == buttons.get("generation")
                           and 0 <= snap.get("age_ms", 9999) <= 2500
                           and 0 <= buttons.get("age_ms", 9999) <= 2500
                           and not buttons.get("truncated", True) and buttons.get("error_count") == 0)
                result.update(state="semantic-ready" if healthy else "observer-not-ready",
                              game_pid=bridge.pid, generation=snap.get("generation"), age_ms=snap.get("age_ms"))
        except Exception as exc:
            result.update(state="android-ready", observation_error=str(exc))
        finally:
            bridge.close()
        return result

    def start(self, wait=False):
        service = self.service()
        if int(service.get("MainPID", "0")) > 0:
            self.require_owned_service(service)
            state = self.status()
            if state["state"] in ("adb-disconnected", "adb-unavailable"):
                return self.reconnect()
            return state
        self.require_runtime_mount()
        for port in (self.config.console_port, self.config.console_port + 1):
            with socket.socket() as sock:
                sock.settimeout(.3)
                if sock.connect_ex(("127.0.0.1", port)) == 0:
                    raise RuntimeError(f"port {port} is occupied by another runtime; it was not stopped")
        if service.get("LoadState") == "loaded":
            self.require_owned_service(service)
            self.command(["sudo", "-n", "systemctl", "reset-failed", self.unit])
        self.control.mkdir(parents=True, exist_ok=True)
        # Start ADB outside the emulator cgroup; it must not delay unit exit.
        self.adb("start-server", device=False)
        command = ["sudo", "-n", "systemd-run", "--unit="+self.unit,
                   "--uid="+str(os.getuid()), "--gid="+str(os.getgid()),
                   "--property=KillMode=control-group", "--property=TimeoutStopSec=45", "--property=Restart=no",
                   "--setenv=ALAS_PYTHON="+sys.executable, "--setenv=ALAS_KVM_CONFIG="+str(self.path),
                   "/bin/bash", str(ROOT/"scripts/wsl/run-kvm-avd.sh"), str(self.domain), str(self.profile),
                   self.config.runtime_release_root.name, str(self.path)]
        if wait:
            command.insert(3, "--wait")
            # This foreground WSL client owns the lifetime while Windows hides it.
            with (self.control/"launcher.log").open("a") as log:
                code = subprocess.call(command, stdout=log, stderr=log)
            (self.control/"last-exit.json").write_text(json.dumps({"returncode":code,"time":time.time()}))
            if code:
                try:
                    self.close_unused_adb_server()
                except (RuntimeError, OSError, subprocess.TimeoutExpired):
                    pass  # Keep the original startup/exit error authoritative.
                raise RuntimeError(f"emulator service exited abnormally ({code}); see {self.control}")
            return {"state":"stopped","exit_code":code}
        self.command(command)
        return self.status(inspect_guest=False)

    def ready(self, launch_game=True):
        started = time.monotonic()
        timings = {}
        service = self.service()
        if int(service.get("MainPID", "0")) == 0:
            raise RuntimeError("KVM is stopped; run Start first")
        self.require_owned_service(service)
        instance = {"instance_id": self.unit, "serial": self.backend.serial, "owned": False}
        phase = time.monotonic()
        self.backend.wait_adb(instance, 180)
        timings["adb_seconds"] = time.monotonic() - phase
        phase = time.monotonic()
        android = self.backend.wait_android_ready(instance, 180)
        timings["android_seconds"] = time.monotonic() - phase
        timings.update(android.get("timings_seconds", {}))
        phase = time.monotonic()
        if launch_game:
            self.backend.restart_game(instance)
        timings["game_launch_seconds"] = time.monotonic() - phase
        phase = time.monotonic()
        deadline = time.monotonic()+90
        while time.monotonic()<deadline:
            self.require_running_service()
            result = self.status()
            if result["state"] in ("semantic-ready", "login-required") or not launch_game:
                timings["surface_seconds"] = time.monotonic() - phase
                timings["total_seconds"] = time.monotonic() - started
                return {**result, "timings_seconds": timings}
            self._sleep_while_running(1)
        raise RuntimeError(f"game readiness timeout: {result}")

    def reconnect(self):
        before = self.require_running_service()
        started = time.monotonic()
        self.backend.wait_adb({"instance_id":self.unit}, 60)
        after = self.require_running_service()
        if after["MainPID"] != before["MainPID"]:
            raise RuntimeError("VM changed during reconnect; inspect its new state")
        state = self.status()
        if not state["running"] or state["state"] in ("adb-disconnected", "adb-unavailable"):
            raise RuntimeError(f"ADB connection did not remain available: {state}")
        return {**state, "recovery":"adb-reconnected", "game_restart_requested":False,
                "reconnect_seconds":time.monotonic()-started}

    def stop(self):
        service = self.service()
        if int(service.get("MainPID", "0")) == 0:
            return self.status(inspect_guest=False)
        self.require_owned_service(service)
        self.backend.request_emulator_stop()
        deadline = time.monotonic()+45
        while time.monotonic()<deadline:
            service = self.service()
            if (int(service.get("MainPID", "0")) == 0
                    and service.get("ActiveState") not in ("active", "activating", "deactivating")):
                break
            time.sleep(.5)
        else:
            self.command(["sudo","-n","systemctl","stop",self.unit], timeout=60)
            raise RuntimeError("emulator did not exit after console stop; fallback service stop used")
        self.adb("disconnect", self.backend.serial, device=False, check=False)
        self.close_unused_adb_server()
        if service.get("Result", "success") != "success" or service.get("ExecMainStatus", "0") != "0":
            raise RuntimeError(f"emulator exited abnormally: {service}")
        return {"state":"stopped", "unit":self.unit, "exit_code":0, "userdata":"retained"}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("start","serve","status","ready","stop","reconnect"))
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--domain", type=Path, default=Path('/mnt/e/Runtime/ALAS/android-build-domain.kvm.local.json'))
    parser.add_argument("--profile", type=Path, default=ROOT/'integration/runtime/kvm-image-build-profile.example.json')
    parser.add_argument("--android-only", action="store_true")
    parser.add_argument("--service-only", action="store_true",
                        help="Status: inspect systemd without querying the guest")
    args=parser.parse_args(argv)
    if args.service_only and args.action != "status":
        parser.error("--service-only requires status")
    try:
        manager=LocalKvm(args.config,args.domain,args.profile)
        if os.getuid()==0:
            raise RuntimeError("run the local manager as the KVM build account")
        if args.action in ("start","serve"):
            result=manager.start(wait=args.action=="serve")
        elif args.action=="ready":
            result=manager.ready(launch_game=not args.android_only)
        elif args.action=="status":
            result=manager.status(inspect_guest=not args.service_only)
        else:
            result=getattr(manager,args.action)()
        print(json.dumps(result,ensure_ascii=False))
        return 0
    except Exception as exc:
        # A readiness probe can recreate ADB just after the failed launcher
        # cleaned it up. Reap it once more from the caller, without touching
        # a running VM or an ADB server that still has other devices.
        if args.action in ("ready", "reconnect") and "manager" in locals():
            try:
                manager.cleanup_failed_service_adb()
            except (RuntimeError, OSError, subprocess.TimeoutExpired):
                pass
        print(json.dumps({"error":str(exc)},ensure_ascii=False),file=sys.stderr)
        return 1
