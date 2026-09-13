#!/usr/bin/env python3
"""Qualify the Bluetooth-free hardware profile using isolated A/B/A overlays.

Reuses the existing image trial's game lifecycle and empty-login boundary.
Only the temporary baseline overlay has Bluetooth enabled, proving that the
candidate does not rely on the original Project's persisted OFF setting.
"""
import argparse
import hashlib
import json
from pathlib import Path

from alas_headless.redroid_image_trial import RedroidImageTrial
from alas_headless.runtime_artifacts import RuntimeLock
from alas_headless.runtime_backends import backend_from_config, WslRedroidBackend
from alas_headless.runtime_command import RuntimeCommandExecutor, RuntimeExecutionPolicy


def verify_candidate(observation):
    features = set(observation["features"].splitlines())
    if features & {"feature:android.hardware.bluetooth", "feature:android.hardware.bluetooth_le"}:
        raise ValueError("candidate still advertises Bluetooth hardware")
    if "bluetooth_manager" in observation["services"]:
        raise ValueError("candidate still starts BluetoothManagerService")
    if any(token in observation["processes"] for token in (
        "com.android.bluetooth", "android.hardware.bluetooth@1.1-service.sim")):
        raise ValueError("candidate still starts Bluetooth process or HAL")
    if observation["hal_init_state"].strip():
        raise ValueError("candidate still registers Bluetooth HAL init service")
    if observation["persisted_switch"].strip() != "1":
        raise ValueError("trial did not retain the baseline ON setting")


class BluetoothTrimTrial(RedroidImageTrial):
    def _login(self, backend, instance, stage):
        if stage["name"] == "candidate":
            backend.wait_adb(instance, 30)
            backend.wait_android_ready(instance, 90)
            result = backend._adb("trial-angle-reinstall", ("install", "-r", str(self.angle_apk)),
                                  timeout_seconds=90, mutating=True)
            stage["external_apk_reinstall"] = backend._require_success(result, "trial-angle-reinstall-failed")
            if "Success" not in stage["external_apk_reinstall"]:
                raise ValueError("candidate APK installation did not report success")
        super()._login(backend, instance, stage)

        def adb(label, *args, mutating=False):
            result = backend._adb(label, args, mutating=mutating)
            return backend._require_success(result, label + "-failed")

        if stage["name"] == "baseline":
            # Only this stopped/frozen-after-stage trial overlay will retain ON.
            # The candidate must omit the service even when userdata requests ON.
            adb("trial-enable-baseline-bluetooth", "shell", "svc", "bluetooth", "enable", mutating=True)
        observation = {
            "features": adb("trial-bluetooth-features", "shell", "pm", "list", "features"),
            "services": adb("trial-bluetooth-services", "shell", "service", "list"),
            "processes": adb("trial-bluetooth-processes", "shell", "ps", "-A", "-o", "PID,NAME"),
            "hal_init_state": adb("trial-bluetooth-init", "shell", "getprop", "init.svc.vendor.bluetooth-1-1"),
            "persisted_switch": adb("trial-bluetooth-switch", "shell", "settings", "get", "global", "bluetooth_on"),
        }
        stage["bluetooth"] = observation
        if stage["name"] == "candidate":
            verify_candidate(observation)
            stage["bluetooth_hardware_removal_passed"] = True
        elif stage["name"] in ("baseline", "rollback"):
            if ("feature:android.hardware.bluetooth" not in observation["features"].splitlines()
                    or "bluetooth_manager" not in observation["services"]):
                raise ValueError("baseline Bluetooth capability was not restored")
        self._checkpoint()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--lock", type=Path, required=True)
    parser.add_argument("--candidate-image", required=True)
    parser.add_argument("--angle-apk", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    if not args.execute:
        parser.error("--execute is required for the isolated runtime trial")
    config = json.loads(args.config.read_text(encoding="utf-8-sig"))
    lock = RuntimeLock.from_mapping(json.loads(args.lock.read_text(encoding="utf-8-sig")))
    if hashlib.sha256(args.angle_apk.read_bytes()).hexdigest() != lock.document["angle"]["apk_sha256"]:
        parser.error("ANGLE APK differs from the pinned qualification input")
    backend = backend_from_config(config, RuntimeCommandExecutor(RuntimeExecutionPolicy(True, True)))
    if not isinstance(backend, WslRedroidBackend):
        parser.error("WSL Project backend required")
    args.output.mkdir(parents=True, exist_ok=False)
    trial = BluetoothTrimTrial(backend, lock, args.candidate_image, args.output)
    trial.angle_apk = args.angle_apk.resolve()
    trial.report["qualification_script_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    return 0 if trial.execute()["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
