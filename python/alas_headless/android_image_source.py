"""Immutable source locks and host preflight for self-maintained Redroid builds."""

from __future__ import annotations

import hashlib
import json
import platform
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence


SOURCE_LOCK_SCHEMA = "alas-headless.android-image-source-lock/v1"
GIT_COMMIT = re.compile(r"^[0-9a-f]{40}$")
TARGETS = {
    "x86_64": ("redroid_x86_64_only-userdebug", "redroid_x86_64_only"),
    "arm64-v8a": ("redroid_arm64_only-userdebug", "redroid_arm64_only"),
}


class AndroidImageSourceError(ValueError):
    """Raised when source or build-host identity is not release-grade."""


def _canonical(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def _mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise AndroidImageSourceError("{0} must be an object".format(name))
    return value


def _commit(value: Any, name: str) -> str:
    text = str(value or "")
    if GIT_COMMIT.fullmatch(text) is None:
        raise AndroidImageSourceError("{0} must be a full immutable Git commit".format(name))
    return text


@dataclass(frozen=True)
class AndroidImageSourceLock:
    document: Mapping[str, Any]
    sha256: str

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "AndroidImageSourceLock":
        document = dict(value)
        if document.get("schema") != SOURCE_LOCK_SCHEMA:
            raise AndroidImageSourceError("source lock schema mismatch")

        platform_source = _mapping(document.get("platform"), "platform")
        if platform_source.get("manifest_url") != (
            "https://android.googlesource.com/platform/manifest"
        ):
            raise AndroidImageSourceError("platform manifest must use the canonical HTTPS URL")
        revision = str(platform_source.get("revision", ""))
        if re.fullmatch(r"android-[0-9]+\.[0-9]+\.[0-9]+_r[0-9]+", revision) is None:
            raise AndroidImageSourceError("platform revision must be an immutable AOSP tag")
        _commit(platform_source.get("commit"), "platform.commit")

        redroid = _mapping(document.get("redroid"), "redroid")
        expected_urls = {
            "local_manifests_url": "https://github.com/remote-android/local_manifests.git",
            "patches_url": "https://github.com/remote-android/redroid-patches.git",
        }
        for field, expected in expected_urls.items():
            if redroid.get(field) != expected:
                raise AndroidImageSourceError("{0} must use {1}".format(field, expected))
        _commit(redroid.get("local_manifests_commit"), "redroid.local_manifests_commit")
        _commit(redroid.get("patches_commit"), "redroid.patches_commit")
        if redroid.get("patch_set") != revision:
            raise AndroidImageSourceError("Redroid patch_set must exactly match AOSP revision")

        products = document.get("products")
        if not isinstance(products, Sequence) or isinstance(products, (str, bytes)):
            raise AndroidImageSourceError("products must be an array")
        observed = {}
        for item in products:
            product = _mapping(item, "product")
            abi = str(product.get("abi", ""))
            if abi in observed:
                raise AndroidImageSourceError("duplicate product ABI: {0}".format(abi))
            observed[abi] = (
                str(product.get("lunch", "")), str(product.get("product_out", ""))
            )
        if observed != TARGETS:
            raise AndroidImageSourceError("products must be exact 64-bit x86_64 and arm64 Redroid targets")

        build = _mapping(document.get("build"), "build")
        if build.get("host_os") != "linux" or build.get("host_arch") != "x86_64":
            raise AndroidImageSourceError("AOSP builder must be Linux x86_64")
        if int(build.get("minimum_free_disk_gib", 0)) < 400:
            raise AndroidImageSourceError("build disk floor cannot be below AOSP's 400 GiB reference")
        if int(build.get("minimum_ram_gib", 0)) < 64:
            raise AndroidImageSourceError("build RAM floor cannot be below AOSP's 64 GiB reference")
        if build.get("commands") != ["m", "m sbom"]:
            raise AndroidImageSourceError("build must produce the product and official AOSP SBOM")
        if build.get("resolved_manifest_required") is not True:
            raise AndroidImageSourceError("resolved repo manifest is mandatory")
        if build.get("game_artifact_allowed") is not False:
            raise AndroidImageSourceError("game artifacts must remain external to the image")

        return cls(document=document, sha256=hashlib.sha256(_canonical(document)).hexdigest())

    @classmethod
    def from_path(cls, path: Path) -> "AndroidImageSourceLock":
        value = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(value, Mapping):
            raise AndroidImageSourceError("source lock must be a JSON object")
        return cls.from_mapping(value)


def host_preflight(lock: AndroidImageSourceLock, root: Path = Path("/")) -> Mapping[str, Any]:
    """Return an evidence record; callers must require outcome=pass before sync/build."""
    build = _mapping(lock.document["build"], "build")
    disk = shutil.disk_usage(root)
    memory_bytes = 0
    meminfo = Path("/proc/meminfo")
    if meminfo.exists():
        for line in meminfo.read_text(encoding="utf-8").splitlines():
            if line.startswith("MemTotal:"):
                memory_bytes = int(line.split()[1]) * 1024
                break
    checks = {
        "host_os_linux": platform.system().lower() == "linux",
        "host_arch_x86_64": platform.machine().lower() in ("x86_64", "amd64"),
        "disk_floor": disk.free >= int(build["minimum_free_disk_gib"]) * 1024 ** 3,
        "ram_floor": memory_bytes >= int(build["minimum_ram_gib"]) * 1024 ** 3,
        "git_available": shutil.which("git") is not None,
        "repo_available": shutil.which("repo") is not None,
    }
    tools = {}
    for name, command in (
        ("git", ("git", "--version")),
        ("repo", ("repo", "--version")),
        ("python", ("python3", "--version")),
    ):
        if shutil.which(command[0]) is None:
            tools[name] = None
            continue
        result = subprocess.run(
            command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
            encoding="utf-8", errors="replace", check=False,
        )
        tools[name] = result.stdout.strip() if result.returncode == 0 else None
    return {
        "schema": "alas-headless.android-image-build-host-preflight/v1",
        "source_lock_sha256": lock.sha256,
        "root": str(root.resolve()),
        "free_disk_bytes": disk.free,
        "memory_bytes": memory_bytes,
        "checks": checks,
        "tools": tools,
        "kernel": platform.release(),
        "outcome": "pass" if all(checks.values()) else "blocked",
        "blockers": sorted(name for name, passed in checks.items() if not passed),
    }


def verify_remote_refs(lock: AndroidImageSourceLock) -> Mapping[str, Any]:
    """Verify that every human-readable upstream ref still names the locked commit."""
    platform_source = lock.document["platform"]
    redroid = lock.document["redroid"]
    refs = (
        (
            "platform-manifest",
            platform_source["manifest_url"],
            "refs/tags/{0}".format(platform_source["revision"]),
            platform_source["commit"],
        ),
        (
            "redroid-local-manifests",
            redroid["local_manifests_url"],
            "refs/heads/{0}".format(redroid["local_manifests_revision"]),
            redroid["local_manifests_commit"],
        ),
        (
            "redroid-patches",
            redroid["patches_url"],
            "refs/heads/{0}".format(redroid["patches_revision"]),
            redroid["patches_commit"],
        ),
    )
    records = []
    blockers = []
    for name, url, ref, expected in refs:
        result = subprocess.run(
            ["git", "ls-remote", url, ref], stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace",
            check=False,
        )
        observed = ""
        if result.returncode == 0 and result.stdout.strip():
            observed = result.stdout.split()[0]
        outcome = "pass" if observed == expected else "blocked"
        if outcome != "pass":
            blockers.append("{0}-ref-mismatch".format(name))
        records.append({
            "name": name, "url": url, "ref": ref, "expected_commit": expected,
            "observed_commit": observed or None, "outcome": outcome,
        })
    return {
        "schema": "alas-headless.android-image-source-remote-verification/v1",
        "source_lock_sha256": lock.sha256,
        "refs": records,
        "outcome": "pass" if not blockers else "blocked",
        "blockers": sorted(blockers),
    }
