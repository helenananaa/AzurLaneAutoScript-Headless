#!/usr/bin/env python3
"""Run package, resource, persistence, restart, and rollback update-lab gates."""

from __future__ import annotations

import argparse
import functools
import http.server
import json
import shutil
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, Mapping, Sequence

from alas_headless.android_update_lab import AdbClient
from alas_headless.android_update_lab import AndroidUpdateLabError
from alas_headless.android_update_lab import UPDATE_LAB_PACKAGE
from alas_headless.android_update_lab import parse_range_header
from alas_headless.android_update_lab import require_status
from alas_headless.android_update_lab import sha256_file
from alas_headless.android_update_lab import write_deterministic_payload


class RangeRequestHandler(http.server.SimpleHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    chunk_delay_seconds = 0.01

    def log_message(self, format: str, *args: Any) -> None:
        return

    def send_head(self):  # type: ignore[no-untyped-def]
        path = self.translate_path(self.path)
        file_path = Path(path)
        if not file_path.is_file():
            self.send_error(404)
            return None
        total = file_path.stat().st_size
        try:
            requested = parse_range_header(self.headers.get("Range"), total)
        except AndroidUpdateLabError:
            self.send_error(416)
            return None
        if requested is None:
            start, end, response = 0, total - 1, 200
        else:
            start, end = requested
            response = 206
        handle = file_path.open("rb")
        handle.seek(start)
        self.send_response(response)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(end - start + 1))
        if response == 206:
            self.send_header("Content-Range", "bytes {0}-{1}/{2}".format(start, end, total))
        self.end_headers()
        self._range_remaining = end - start + 1
        return handle

    def copyfile(self, source, outputfile):  # type: ignore[no-untyped-def]
        remaining = getattr(self, "_range_remaining", None)
        if remaining is None:
            return super().copyfile(source, outputfile)
        while remaining:
            chunk = source.read(min(64 * 1024, remaining))
            if not chunk:
                break
            try:
                outputfile.write(chunk)
            except (BrokenPipeError, ConnectionResetError):
                break
            remaining -= len(chunk)
            # Make the failure-injection point deterministic even on a fast
            # loopback interface. This server is qualification-only.
            time.sleep(self.chunk_delay_seconds)


class QuietThreadingHTTPServer(http.server.ThreadingHTTPServer):
    def handle_error(self, request, client_address):  # type: ignore[no-untyped-def]
        # Process kills and Android reboot intentionally reset active sockets.
        return


def write_json_atomic(path: Path, value: Mapping[str, Any]) -> None:
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def main(argv: Sequence[str] = ()) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--serial", required=True)
    parser.add_argument("--adb", required=True, type=Path)
    parser.add_argument("--java", required=True, type=Path)
    parser.add_argument("--bundletool", required=True, type=Path)
    parser.add_argument("--artifacts", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--host-port", type=int, default=0)
    parser.add_argument("--skip-android-restart", action="store_true")
    parser.add_argument("--restart-program", type=Path)
    parser.add_argument("--restart-arg", action="append", default=[])
    arguments = parser.parse_args(list(argv) if argv else None)
    if arguments.restart_arg and arguments.restart_program is None:
        parser.error("--restart-arg requires --restart-program")
    if arguments.restart_program is not None and not arguments.restart_program.is_file():
        parser.error("--restart-program must be a file")

    output = arguments.output.resolve()
    if output.exists():
        parser.error("--output must not already exist")
    output.mkdir(parents=True)
    payload_root = output / "payloads"
    payload_root.mkdir()
    artifacts = arguments.artifacts.resolve()
    required = {
        "v1": artifacts / "update-lab-v1.apk",
        "v2": artifacts / "update-lab-v2.apk",
        "wrong": artifacts / "update-lab-v2-wrong-signer.apk",
        "apks": artifacts / "update-lab-v2.apks",
    }
    for name, path in required.items():
        if not path.is_file():
            parser.error("missing update-lab artifact: {0}={1}".format(name, path))
    if not arguments.bundletool.is_file() or not arguments.java.is_file():
        parser.error("bundletool and Java paths must be files")

    epoch1 = payload_root / "epoch-1.bin"
    epoch2 = payload_root / "epoch-2.bin"
    epoch1_hash = write_deterministic_payload(epoch1, 24 * 1024 * 1024, "epoch-1")
    epoch2_hash = write_deterministic_payload(epoch2, 28 * 1024 * 1024, "epoch-2")

    handler = functools.partial(RangeRequestHandler, directory=str(payload_root))
    server = QuietThreadingHTTPServer(("127.0.0.1", arguments.host_port), handler)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    port = server.server_address[1]
    adb = AdbClient(arguments.adb, arguments.serial)
    reverse_endpoint = "tcp:{0}".format(port)
    adb.run(["reverse", reverse_endpoint, reverse_endpoint])
    phases = []

    def phase(name: str, action: Callable[[], Mapping[str, Any]]) -> Mapping[str, Any]:
        started = time.monotonic()
        record: Dict[str, Any] = {"name": name}
        try:
            details = dict(action())
            record.update(
                {
                    "outcome": "pass",
                    "duration_ms": int((time.monotonic() - started) * 1000),
                    "details": details,
                }
            )
            phases.append(record)
            write_json_atomic(output / "partial-manifest.json", {"phases": phases})
            return details
        except Exception as error:
            record.update(
                {
                    "outcome": "fail",
                    "duration_ms": int((time.monotonic() - started) * 1000),
                    "failure": error.__class__.__name__,
                }
            )
            phases.append(record)
            write_json_atomic(output / "partial-manifest.json", {"phases": phases})
            raise

    def install_v1_and_initialize(sentinel: str) -> Mapping[str, Any]:
        adb.run(["uninstall", UPDATE_LAB_PACKAGE], check=False)
        adb.run(["install", str(required["v1"])], timeout_seconds=120)
        adb.start_operation("initialize", {"sentinel": sentinel})
        status = adb.wait_status(("initialized",), 30)
        require_status(status, version_code=1, data_schema=1, sentinel=sentinel)
        return {"version_code": adb.package_version_code(), "status": status}

    try:
        phase("android-ready", lambda: adb.wait_boot())

        mono_sentinel = "single-apk-preserved"
        phase("single-install-v1", lambda: install_v1_and_initialize(mono_sentinel))

        def wrong_signer() -> Mapping[str, Any]:
            result = adb.run(
                ["install", "-r", str(required["wrong"])],
                timeout_seconds=120,
                check=False,
            )
            if result.returncode == 0 or "UPDATE_INCOMPATIBLE" not in (
                result.stdout + result.stderr
            ):
                raise AndroidUpdateLabError("wrong signer was not rejected")
            adb.start_operation("status", {})
            status = adb.wait_status(("status",), 30)
            require_status(status, version_code=1, data_schema=1, sentinel=mono_sentinel)
            return {"rejected": True, "version_code": adb.package_version_code()}

        phase("wrong-signer-negative", wrong_signer)

        def monolithic_upgrade() -> Mapping[str, Any]:
            adb.run(["install", "-r", str(required["v2"])], timeout_seconds=120)
            adb.start_operation("status", {})
            status = adb.wait_status(("status",), 30)
            require_status(status, version_code=2, data_schema=2, sentinel=mono_sentinel)
            if status.get("migration") != "schema-1-to-2":
                raise AndroidUpdateLabError("monolithic upgrade migration was not recorded")
            return {"paths": adb.package_paths(), "status": status}

        phase("single-apk-upgrade", monolithic_upgrade)

        split_sentinel = "split-apk-preserved"
        phase("split-install-v1", lambda: install_v1_and_initialize(split_sentinel))

        def split_upgrade() -> Mapping[str, Any]:
            command = [
                str(arguments.java),
                "-jar",
                str(arguments.bundletool),
                "install-apks",
                "--apks=" + str(required["apks"]),
                "--adb=" + str(arguments.adb),
                "--device-id=" + arguments.serial,
            ]
            completed = subprocess.run(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=180,
                check=False,
            )
            if completed.returncode != 0:
                raise AndroidUpdateLabError("bundletool split install failed")
            adb.start_operation("status", {})
            status = adb.wait_status(("status",), 30)
            require_status(status, version_code=2, data_schema=2, sentinel=split_sentinel)
            paths = adb.package_paths()
            if len(paths) < 2:
                raise AndroidUpdateLabError("bundletool did not install a split APK set")
            return {"paths": paths, "status": status}

        phase("split-apk-upgrade", split_upgrade)

        def interrupted_epoch1() -> Mapping[str, Any]:
            url = "http://127.0.0.1:{0}/{1}".format(port, epoch1.name)
            adb.start_operation(
                "download",
                {
                    "url": url,
                    "sha256": epoch1_hash,
                    "epoch": 1,
                    "chunk_delay_ms": 40,
                },
            )
            deadline = time.monotonic() + 60
            observed = 0
            while time.monotonic() < deadline:
                status = adb.read_status(5)
                if status.get("epoch") == 1 and status.get("complete") is False:
                    observed = int(status.get("bytes", 0))
                    if observed >= 2 * 1024 * 1024:
                        break
                time.sleep(0.5)
            if observed < 2 * 1024 * 1024:
                raise AndroidUpdateLabError("download interruption point was not observed")
            adb.shell(["am", "force-stop", UPDATE_LAB_PACKAGE])
            partial = adb.read_status(10)
            if partial.get("complete") is not False:
                raise AndroidUpdateLabError("partial download evidence was not retained")
            adb.start_operation(
                "download",
                {"url": url, "sha256": epoch1_hash, "epoch": 1},
            )
            complete = adb.wait_status(("downloaded", "failed"), 120)
            if complete.get("outcome") != "downloaded":
                raise AndroidUpdateLabError("epoch 1 resume failed")
            adb.start_operation("promote", {"epoch": 1, "sha256": epoch1_hash})
            promoted = adb.wait_status(("promoted",), 30)
            return {"interrupted_bytes": observed, "promoted": promoted}

        phase("resource-process-resume", interrupted_epoch1)

        def low_space() -> Mapping[str, Any]:
            url = "http://127.0.0.1:{0}/{1}".format(port, epoch2.name)
            adb.start_operation(
                "download",
                {
                    "url": url,
                    "sha256": epoch2_hash,
                    "epoch": 2,
                    "required_free_bytes": 9_000_000_000_000_000_000,
                },
            )
            status = adb.wait_status(("failed",), 30)
            if status.get("failure") != "low-space":
                raise AndroidUpdateLabError("low-space gate returned the wrong failure")
            return {"failure": "low-space"}

        phase("resource-low-space-negative", low_space)

        if not arguments.skip_android_restart:
            def restart_resume() -> Mapping[str, Any]:
                url = "http://127.0.0.1:{0}/{1}".format(port, epoch2.name)
                adb.start_operation(
                    "download",
                    {
                        "url": url,
                        "sha256": epoch2_hash,
                        "epoch": 2,
                        "chunk_delay_ms": 40,
                    },
                )
                deadline = time.monotonic() + 60
                observed = 0
                while time.monotonic() < deadline:
                    status = adb.read_status(5)
                    if status.get("epoch") == 2 and status.get("complete") is False:
                        observed = int(status.get("bytes", 0))
                        if observed >= 2 * 1024 * 1024:
                            break
                    time.sleep(0.5)
                if observed < 2 * 1024 * 1024:
                    raise AndroidUpdateLabError("restart interruption point was not observed")
                firstboot_before = adb.shell(["getprop", "ro.runtime.firstboot"]).stdout.strip()
                restart_method = "adb-reboot"
                if arguments.restart_program is None:
                    try:
                        adb.run(["reboot"], timeout_seconds=20)
                    except subprocess.TimeoutExpired:
                        # Some container Android backends close neither side of the ADB
                        # transport while processing reboot.  The firstboot identity below
                        # remains the authoritative proof that a restart actually occurred.
                        pass
                else:
                    restart_method = "external-program"
                    restart_command = [str(arguments.restart_program)] + list(
                        arguments.restart_arg
                    )
                    subprocess.run(
                        restart_command,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                        encoding="utf-8",
                        errors="replace",
                        timeout=120,
                        check=True,
                    )
                if ":" in arguments.serial:
                    subprocess.run(
                        [str(arguments.adb), "disconnect", arguments.serial],
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                        encoding="utf-8",
                        errors="replace",
                        timeout=10,
                        check=False,
                    )
                    connect_deadline = time.monotonic() + 120
                    while time.monotonic() < connect_deadline:
                        connected = subprocess.run(
                            [str(arguments.adb), "connect", arguments.serial],
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE,
                            text=True,
                            encoding="utf-8",
                            errors="replace",
                            timeout=10,
                            check=False,
                        )
                        if connected.returncode == 0:
                            state = adb.run(["get-state"], timeout_seconds=10, check=False)
                            if state.stdout.strip() == "device":
                                break
                        time.sleep(1)
                    else:
                        raise AndroidUpdateLabError("ADB TCP transport did not reconnect")
                adb.wait_boot(300)
                firstboot_after = adb.shell(
                    ["getprop", "ro.runtime.firstboot"]
                ).stdout.strip()
                if (
                    not firstboot_before
                    or not firstboot_after
                    or firstboot_after == firstboot_before
                ):
                    raise AndroidUpdateLabError(
                        "Android restart identity did not change"
                    )
                adb.run(["reverse", reverse_endpoint, reverse_endpoint])
                reverse_list = adb.run(["reverse", "--list"])
                if reverse_endpoint not in reverse_list.stdout:
                    raise AndroidUpdateLabError("ADB reverse was not restored after reboot")
                adb.start_operation(
                    "download", {"url": url, "sha256": epoch2_hash, "epoch": 2}
                )
                status = adb.wait_status(("downloaded", "failed"), 120)
                if status.get("outcome") != "downloaded":
                    raise AndroidUpdateLabError("epoch 2 restart resume failed")
                adb.start_operation("promote", {"epoch": 2, "sha256": epoch2_hash})
                promoted = adb.wait_status(("promoted",), 30)
                return {
                    "interrupted_bytes": observed,
                    "restart_method": restart_method,
                    "restart_command": (
                        restart_command
                        if arguments.restart_program is not None
                        else [str(arguments.adb), "-s", arguments.serial, "reboot"]
                    ),
                    "firstboot_before": firstboot_before,
                    "firstboot_after": firstboot_after,
                    "transport_ready": reverse_list.stdout,
                    "promoted": promoted,
                }

            phase("resource-android-restart-resume", restart_resume)

        def rollback_pointer() -> Mapping[str, Any]:
            adb.start_operation("promote", {"epoch": 1, "sha256": epoch1_hash})
            status = adb.wait_status(("promoted",), 30)
            active = status.get("active_resource")
            if not isinstance(active, dict) or active.get("epoch") != 1:
                raise AndroidUpdateLabError("resource pointer rollback did not select epoch 1")
            return {"active_resource": active}

        phase("resource-pointer-rollback", rollback_pointer)

        manifest = {
            "schema": "alas-headless.android-update-lab-qualification/v1",
            "outcome": "pass",
            "serial": arguments.serial,
            "package": UPDATE_LAB_PACKAGE,
            "artifacts": {
                name: {"sha256": sha256_file(path), "bytes": path.stat().st_size}
                for name, path in required.items()
            },
            "resources": {
                "epoch_1_sha256": epoch1_hash,
                "epoch_2_sha256": epoch2_hash,
                "server_port": port,
                "transport": "adb-reverse-test-fixture",
            },
            "phases": phases,
            "input_scope": "synthetic-update-lab-only",
            "game_installed": False,
            "alas_workload_used": False,
        }
        write_json_atomic(output / "manifest.json", manifest)
        partial = output / "partial-manifest.json"
        if partial.exists():
            partial.unlink()
        print(str((output / "manifest.json").resolve()))
        return 0
    except Exception:
        failure_manifest = {
            "schema": "alas-headless.android-update-lab-qualification/v1",
            "outcome": "fail",
            "serial": arguments.serial,
            "phases": phases,
            "game_installed": False,
            "alas_workload_used": False,
        }
        write_json_atomic(output / "manifest.json", failure_manifest)
        raise
    finally:
        server.shutdown()
        server.server_close()
        server_thread.join(timeout=5)


if __name__ == "__main__":
    raise SystemExit(main())
