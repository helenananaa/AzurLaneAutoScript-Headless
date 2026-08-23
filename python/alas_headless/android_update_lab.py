"""Synthetic package and resource update qualification helpers."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple


UPDATE_LAB_PACKAGE = "io.github.alasheadless.updatelab"
UPDATE_LAB_COMPONENT = UPDATE_LAB_PACKAGE + "/.MainActivity"
UPDATE_LAB_STATUS_PATH = (
    "/sdcard/Android/data/" + UPDATE_LAB_PACKAGE + "/files/status.json"
)
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class AndroidUpdateLabError(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_deterministic_payload(path: Path, size_bytes: int, seed: str) -> str:
    if size_bytes < 1:
        raise AndroidUpdateLabError("payload size must be positive")
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    remaining = size_bytes
    counter = 0
    with destination.open("wb") as handle:
        while remaining:
            block_seed = hashlib.sha256(
                (seed + ":" + str(counter)).encode("utf-8")
            ).digest()
            block = (block_seed * ((1024 * 1024 // len(block_seed)) + 1))[: 1024 * 1024]
            chunk = block[: min(len(block), remaining)]
            handle.write(chunk)
            digest.update(chunk)
            remaining -= len(chunk)
            counter += 1
    return digest.hexdigest()


def parse_range_header(value: Optional[str], total_size: int) -> Optional[Tuple[int, int]]:
    if value is None:
        return None
    match = re.fullmatch(r"bytes=(\d+)-(\d*)", value.strip())
    if match is None:
        raise AndroidUpdateLabError("unsupported HTTP Range header")
    start = int(match.group(1))
    end = int(match.group(2)) if match.group(2) else total_size - 1
    if start < 0 or start >= total_size or end < start or end >= total_size:
        raise AndroidUpdateLabError("HTTP Range is outside the payload")
    return start, end


@dataclass(frozen=True)
class AdbResult:
    returncode: int
    stdout: str
    stderr: str
    duration_ms: int


class AdbClient:
    def __init__(self, adb: Path, serial: str) -> None:
        self.adb = str(Path(adb))
        if not serial or any(character.isspace() for character in serial):
            raise AndroidUpdateLabError("ADB serial must be a non-empty token")
        self.serial = serial

    def run(
        self,
        arguments: Sequence[str],
        timeout_seconds: float = 60.0,
        check: bool = True,
    ) -> AdbResult:
        command = [self.adb, "-s", self.serial] + list(arguments)
        started = time.monotonic()
        completed = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_seconds,
            check=False,
        )
        result = AdbResult(
            completed.returncode,
            completed.stdout.strip(),
            completed.stderr.strip(),
            int((time.monotonic() - started) * 1000),
        )
        if check and result.returncode != 0:
            raise AndroidUpdateLabError(
                "ADB command failed: {0}".format(" ".join(arguments[:3]))
            )
        return result

    def shell(self, arguments: Sequence[str], **kwargs: Any) -> AdbResult:
        return self.run(["shell"] + list(arguments), **kwargs)

    def wait_boot(self, timeout_seconds: float = 300.0) -> Mapping[str, str]:
        self.run(["wait-for-device"], timeout_seconds=timeout_seconds)
        deadline = time.monotonic() + timeout_seconds
        last = ""
        while time.monotonic() < deadline:
            boot = self.shell(
                ["getprop", "sys.boot_completed"], timeout_seconds=10, check=False
            )
            package = self.shell(
                ["service", "check", "package"], timeout_seconds=10, check=False
            )
            last = boot.stdout + " / " + package.stdout
            if boot.stdout.strip() == "1" and "found" in package.stdout.lower():
                return {"boot_completed": "1", "package_service": package.stdout}
            time.sleep(1.0)
        raise AndroidUpdateLabError("Android boot readiness timed out: " + last)

    def start_operation(self, operation: str, extras: Mapping[str, Any]) -> AdbResult:
        arguments: List[str] = [
            "am",
            "start",
            "-W",
            "-n",
            UPDATE_LAB_COMPONENT,
            "--es",
            "operation",
            operation,
        ]
        for key, value in extras.items():
            if isinstance(value, bool):
                arguments.extend(("--ez", key, "true" if value else "false"))
            elif isinstance(value, int):
                option = "--el" if abs(value) > 2147483647 else "--ei"
                arguments.extend((option, key, str(value)))
            else:
                arguments.extend(("--es", key, str(value)))
        return self.shell(arguments, timeout_seconds=30)

    def read_status(self, timeout_seconds: float = 30.0) -> Mapping[str, Any]:
        deadline = time.monotonic() + timeout_seconds
        last = ""
        while time.monotonic() < deadline:
            result = self.shell(
                ["cat", UPDATE_LAB_STATUS_PATH], timeout_seconds=10, check=False
            )
            last = result.stdout
            if result.returncode == 0 and result.stdout.startswith("{"):
                try:
                    value = json.loads(result.stdout)
                except json.JSONDecodeError:
                    value = None
                if isinstance(value, dict):
                    return value
            time.sleep(0.5)
        raise AndroidUpdateLabError("update-lab status timed out: " + last[:200])

    def wait_status(
        self,
        outcomes: Iterable[str],
        timeout_seconds: float = 120.0,
    ) -> Mapping[str, Any]:
        accepted = set(outcomes)
        deadline = time.monotonic() + timeout_seconds
        last: Mapping[str, Any] = {}
        while time.monotonic() < deadline:
            try:
                last = self.read_status(timeout_seconds=5.0)
            except AndroidUpdateLabError:
                time.sleep(0.5)
                continue
            if last.get("outcome") in accepted:
                return last
            time.sleep(0.5)
        raise AndroidUpdateLabError(
            "update-lab outcome timed out: " + json.dumps(last, sort_keys=True)
        )
    def package_paths(self) -> Tuple[str, ...]:
        result = self.shell(["pm", "path", UPDATE_LAB_PACKAGE])
        paths = tuple(
            line[len("package:") :]
            for line in result.stdout.splitlines()
            if line.startswith("package:")
        )
        if not paths:
            raise AndroidUpdateLabError("update-lab package has no installed APK paths")
        return paths

    def package_version_code(self) -> int:
        result = self.shell(["dumpsys", "package", UPDATE_LAB_PACKAGE])
        match = re.search(r"\bversionCode=(\d+)", result.stdout)
        if match is None:
            raise AndroidUpdateLabError("installed package versionCode was not reported")
        return int(match.group(1))


def require_status(
    value: Mapping[str, Any],
    *,
    version_code: int,
    data_schema: int,
    sentinel: str,
) -> None:
    expected = {
        "version_code": version_code,
        "data_schema": data_schema,
        "sentinel": sentinel,
        "internal_sentinel": sentinel,
        "external_sentinel": sentinel,
    }
    differences: Dict[str, Any] = {}
    for key, expected_value in expected.items():
        if value.get(key) != expected_value:
            differences[key] = {"expected": expected_value, "actual": value.get(key)}
    if differences:
        raise AndroidUpdateLabError(
            "update-lab persisted state differs: " + json.dumps(differences, sort_keys=True)
        )
