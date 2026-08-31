"""Immutable source locks and host preflight for self-maintained Redroid builds."""

from __future__ import annotations

import hashlib
import json
import platform
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence


SOURCE_LOCK_SCHEMA = "alas-headless.android-image-source-lock/v1"
GIT_COMMIT = re.compile(r"^[0-9a-f]{40}$")
TARGETS = {
    "x86_64": (
        "redroid_x86_64_only-trunk_staging-userdebug",
        "redroid_x86_64_only",
    ),
    "arm64-v8a": (
        "redroid_arm64_only-trunk_staging-userdebug",
        "redroid_arm64_only",
    ),
}
REDROID_PROJECTS = {
    "device_redroid": "device/redroid",
    "device_redroid-prebuilts": "device/redroid-prebuilts",
    "redroid-c2": "hardware/redroid/c2",
    "redroid-omx": "hardware/redroid/omx",
    "vendor_redroid": "vendor/redroid",
}
WEBVIEW_PROJECTS = {
    "chromium-webview-stub": (
        "external/chromium-webview",
        "https://github.com/remote-android/chromium-webview-stub.git",
    ),
    "android_external_chromium-webview_prebuilt_arm": (
        "external/chromium-webview/prebuilt/arm",
        "https://github.com/LineageOS/android_external_chromium-webview_prebuilt_arm.git",
    ),
    "android_external_chromium-webview_prebuilt_arm64": (
        "external/chromium-webview/prebuilt/arm64",
        "https://github.com/LineageOS/android_external_chromium-webview_prebuilt_arm64.git",
    ),
    "android_external_chromium-webview_prebuilt_x86": (
        "external/chromium-webview/prebuilt/x86",
        "https://github.com/LineageOS/android_external_chromium-webview_prebuilt_x86.git",
    ),
    "android_external_chromium-webview_prebuilt_x86_64": (
        "external/chromium-webview/prebuilt/x86_64",
        "https://github.com/LineageOS/android_external_chromium-webview_prebuilt_x86_64.git",
    ),
}
SHA256 = re.compile(r"^[0-9a-f]{64}$")


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
        tag_object = _commit(platform_source.get("tag_object"), "platform.tag_object")
        manifest_commit = _commit(platform_source.get("commit"), "platform.commit")
        if tag_object == manifest_commit:
            raise AndroidImageSourceError("annotated platform tag object and commit must differ")

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
        projects = redroid.get("projects")
        if not isinstance(projects, Sequence) or isinstance(projects, (str, bytes)):
            raise AndroidImageSourceError("redroid.projects must be an array")
        observed_projects = {}
        for item in projects:
            project = _mapping(item, "redroid project")
            name = str(project.get("name", ""))
            if name in observed_projects:
                raise AndroidImageSourceError("duplicate Redroid project: {0}".format(name))
            observed_projects[name] = str(project.get("path", ""))
            if not str(project.get("revision", "")).strip():
                raise AndroidImageSourceError("Redroid project revision is mandatory")
            _commit(project.get("commit"), "redroid.projects[{0}].commit".format(name))
        if observed_projects != REDROID_PROJECTS:
            raise AndroidImageSourceError("all Redroid local-manifest projects must be commit locked")
        webview_projects = redroid.get("webview_projects")
        if not isinstance(webview_projects, Sequence) or isinstance(webview_projects, (str, bytes)):
            raise AndroidImageSourceError("redroid.webview_projects must be an array")
        observed_webview = {}
        for item in webview_projects:
            project = _mapping(item, "WebView project")
            name = str(project.get("name", ""))
            if name in observed_webview:
                raise AndroidImageSourceError("duplicate WebView project: {0}".format(name))
            observed_webview[name] = (str(project.get("path", "")), str(project.get("url", "")))
            if not str(project.get("revision", "")).strip():
                raise AndroidImageSourceError("WebView project revision is mandatory")
            _commit(project.get("commit"), "redroid.webview_projects[{0}].commit".format(name))
        if observed_webview != WEBVIEW_PROJECTS:
            raise AndroidImageSourceError("all WebView local-manifest projects must be commit locked")

        project_patches = document.get("project_patches")
        if not isinstance(project_patches, Sequence) or isinstance(
            project_patches, (str, bytes)
        ) or not project_patches:
            raise AndroidImageSourceError("project_patches must be a non-empty array")
        observed_patch_paths = set()
        for item in project_patches:
            patch = _mapping(item, "project patch")
            project = str(patch.get("project", ""))
            path = str(patch.get("path", ""))
            digest = str(patch.get("sha256", ""))
            if project not in {
                "frameworks/base",
                "frameworks/native",
                "external/swiftshader",
                "build/make",
            }:
                raise AndroidImageSourceError("project patch target is not approved")
            if not path.startswith("integration/runtime/aosp-patches/") or (
                ".." in Path(path).parts
            ):
                raise AndroidImageSourceError(
                    "project patch path must stay under aosp-patches"
                )
            if path in observed_patch_paths:
                raise AndroidImageSourceError("duplicate project patch path: " + path)
            observed_patch_paths.add(path)
            if SHA256.fullmatch(digest) is None:
                raise AndroidImageSourceError("project patch sha256 must be immutable")
            if not str(patch.get("commit_message", "")).startswith("ALAS: "):
                raise AndroidImageSourceError("project patch commit_message must be locked")

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
        if int(build.get("source_date_epoch", 0)) <= 0:
            raise AndroidImageSourceError("source_date_epoch must be a positive locked timestamp")
        for field, expected in (
            ("build_number", "alas-android-14-r75"),
            ("build_username", "alas-builder"),
            ("build_hostname", "alas-builder"),
            ("timezone", "UTC"),
            ("locale", "C"),
        ):
            if build.get(field) != expected:
                raise AndroidImageSourceError("build.{0} must be deterministic".format(field))
        git_identity = _mapping(build.get("git_identity"), "build.git_identity")
        if (
            git_identity.get("name") != "ALAS Android Builder"
            or git_identity.get("email") != "alas-android-builder@invalid.example"
        ):
            raise AndroidImageSourceError("build.git_identity must be deterministic")
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


def disk_checks(
    filesystem_free_bytes: int,
    minimum_bytes: int,
    kernel_release: str,
    backing_free_bytes: int | None,
) -> Mapping[str, bool]:
    is_wsl = "microsoft" in kernel_release.lower()
    return {
        "backing_disk_verified": not is_wsl or backing_free_bytes is not None,
        "disk_floor": (
            filesystem_free_bytes >= minimum_bytes
            and (not is_wsl or (backing_free_bytes or 0) >= minimum_bytes)
        ),
    }


def host_preflight(
    lock: AndroidImageSourceLock,
    root: Path = Path("/"),
    backing_free_bytes: int | None = None,
    evidence_root: Path | None = None,
    require_non_root_device: bool = False,
) -> Mapping[str, Any]:
    """Return an evidence record; callers must require outcome=pass before sync/build."""
    build = _mapping(lock.document["build"], "build")
    root = root.resolve()
    evidence_root = evidence_root.resolve() if evidence_root is not None else None
    disk = shutil.disk_usage(root)
    work_stat = root.stat()
    system_root_stat = Path("/").stat()
    evidence_stat = evidence_root.stat() if evidence_root is not None else None
    memory_bytes = 0
    meminfo = Path("/proc/meminfo")
    if meminfo.exists():
        for line in meminfo.read_text(encoding="utf-8").splitlines():
            if line.startswith("MemTotal:"):
                memory_bytes = int(line.split()[1]) * 1024
                break
    minimum_disk_bytes = int(build["minimum_free_disk_gib"]) * 1024 ** 3
    checks = {
        "host_os_linux": platform.system().lower() == "linux",
        "host_arch_x86_64": platform.machine().lower() in ("x86_64", "amd64"),
        "ram_floor": memory_bytes >= int(build["minimum_ram_gib"]) * 1024 ** 3,
        "git_available": shutil.which("git") is not None,
        "repo_available": shutil.which("repo") is not None,
        "work_path_exists": root.is_dir(),
        "evidence_path_exists": evidence_root is None or evidence_root.is_dir(),
        "work_and_evidence_same_device": (
            evidence_stat is None or work_stat.st_dev == evidence_stat.st_dev
        ),
        "work_device_not_system_root": (
            not require_non_root_device or work_stat.st_dev != system_root_stat.st_dev
        ),
    }
    checks.update(disk_checks(
        disk.free, minimum_disk_bytes, platform.release(), backing_free_bytes
    ))
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
        "evidence_root": str(evidence_root) if evidence_root is not None else None,
        "work_device": int(work_stat.st_dev),
        "evidence_device": int(evidence_stat.st_dev) if evidence_stat is not None else None,
        "system_root_device": int(system_root_stat.st_dev),
        "require_non_root_device": require_non_root_device,
        "free_disk_bytes": disk.free,
        "backing_free_bytes": backing_free_bytes,
        "memory_bytes": memory_bytes,
        "checks": checks,
        "tools": tools,
        "kernel": platform.release(),
        "outcome": "pass" if all(checks.values()) else "blocked",
        "blockers": sorted(name for name, passed in checks.items() if not passed),
    }


def webview_projects_for_abi(
    projects: Sequence[Mapping[str, Any]], abi: str,
) -> Sequence[Mapping[str, Any]]:
    """Return the WebView source refs that can affect the selected product ABI."""
    if abi == "all":
        return projects
    suffixes = {
        "x86_64": ("/x86", "/x86_64"),
        "arm64-v8a": ("/arm", "/arm64"),
    }
    if abi not in suffixes:
        raise AndroidImageSourceError("unsupported remote-verification ABI: " + abi)
    return tuple(
        project for project in projects
        if project["name"] == "chromium-webview-stub"
        or str(project["path"]).endswith(suffixes[abi])
    )


def verify_remote_refs(
    lock: AndroidImageSourceLock, abi: str = "all",
) -> Mapping[str, Any]:
    """Verify upstream refs shared by, or directly consumed by, the selected ABI."""
    platform_source = lock.document["platform"]
    redroid = lock.document["redroid"]
    refs = [
        (
            "platform-manifest-tag-object",
            platform_source["manifest_url"],
            "refs/tags/{0}".format(platform_source["revision"]),
            platform_source["tag_object"],
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
    ]
    for project in redroid["projects"]:
        refs.append((
            "redroid-project:{0}".format(project["name"]),
            "https://github.com/remote-android/{0}.git".format(project["name"]),
            "refs/heads/{0}".format(project["revision"]),
            project["commit"],
        ))
    for project in webview_projects_for_abi(redroid["webview_projects"], abi):
        refs.append((
            "webview-project:{0}".format(project["name"]),
            project["url"],
            "refs/heads/{0}".format(project["revision"]),
            project["commit"],
        ))
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
    with tempfile.TemporaryDirectory(prefix="alas-platform-tag-") as raw:
        subprocess.run(["git", "init", "-q", raw], check=True)
        fetched = subprocess.run(
            ["git", "-C", raw, "fetch", "-q", "--depth=1",
             platform_source["manifest_url"],
             "refs/tags/{0}".format(platform_source["revision"])],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            encoding="utf-8", errors="replace", check=False,
        )
        peeled = ""
        if fetched.returncode == 0:
            result = subprocess.run(
                ["git", "-C", raw, "rev-parse", "FETCH_HEAD^{commit}"],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                encoding="utf-8", errors="replace", check=False,
            )
            if result.returncode == 0:
                peeled = result.stdout.strip()
        peeled_outcome = "pass" if peeled == platform_source["commit"] else "blocked"
        if peeled_outcome != "pass":
            blockers.append("platform-manifest-peeled-commit-mismatch")
        records.append({
            "name": "platform-manifest-peeled-commit",
            "url": platform_source["manifest_url"],
            "ref": "refs/tags/{0}^{{commit}}".format(platform_source["revision"]),
            "expected_commit": platform_source["commit"],
            "observed_commit": peeled or None,
            "outcome": peeled_outcome,
        })
    return {
        "schema": "alas-headless.android-image-source-remote-verification/v1",
        "source_lock_sha256": lock.sha256,
        "abi": abi,
        "refs": records,
        "outcome": "pass" if not blockers else "blocked",
        "blockers": sorted(blockers),
    }
