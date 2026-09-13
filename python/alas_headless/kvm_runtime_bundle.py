"""Publish and verify immutable KVM emulator runtime releases.

The build output is owned by the KVM build domain.  A running emulator consumes
an immutable release copied under that domain's runtime root, so later builds
cannot change a live KVM runtime underneath it.
"""

from __future__ import annotations

import contextlib
import ctypes
import errno
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, ContextManager, Iterator, Mapping, Sequence

from alas_headless.android_build_domain import AndroidBuildDomain
from alas_headless.android_build_domain_migration import (
    AndroidBuildDomainMigrationError,
)
from alas_headless.android_build_domain_migration import require_output_buildable
from alas_headless.android_kvm_image import KvmImageBuildProfile


RUNTIME_RELEASE_SCHEMA = "alas-headless.kvm-runtime-release/v1"
RUNTIME_RELEASE_ROOT_MODE = 0o755
SDK_PLATFORMS_MODE = 0o755
RELEASE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
SYSTEMD_UNIT = re.compile(r"^[A-Za-z0-9_.@:-]+\.service$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
REQUIRED_IMAGES = (
    "system.img",
    "vendor.img",
    "ramdisk.img",
    "kernel-ranchu",
    "config.ini",
)
RUNTIME_COMPONENT_TARGETS = {
    "emulator": Path("emulator"),
    "adb": Path("sdk") / "platform-tools" / "adb",
    "images": Path("images"),
}


class KvmRuntimeBundleError(RuntimeError):
    """Raised when a runtime release cannot be proven complete and immutable."""


@dataclass(frozen=True)
class RuntimeBundleInputs:
    source_root: Path
    output_root: Path
    runtime_root: Path
    domain_sha256: str
    profile_sha256: str
    source_lock_sha256: str
    emulator_relative: Path
    adb_relative: Path
    image_relative: Path
    domain: AndroidBuildDomain | None = None
    peer_domain: AndroidBuildDomain | None = None

    @classmethod
    def from_contracts(
        cls,
        domain: AndroidBuildDomain,
        profile: KvmImageBuildProfile,
        peer_domain: AndroidBuildDomain | None = None,
    ) -> "RuntimeBundleInputs":
        if domain.document["backend"] != "kvm":
            raise KvmRuntimeBundleError("runtime release domain must belong to kvm")
        if profile.document["backend"] != "kvm":
            raise KvmRuntimeBundleError("runtime release profile must belong to kvm")

        runtime = profile.document["runtime"]
        emulator_relative = _safe_relative(
            Path(str(runtime["emulator"])).parent, "emulator bundle"
        )
        adb_relative = _safe_relative(Path(str(runtime["adb"])), "adb executable")
        product = str(profile.document["product"]["product_out"])
        image_relative = _safe_relative(
            Path("target") / "product" / product / "emulator" / "x86_64",
            "Goldfish image sysdir",
        )
        paths = domain.document["paths"]
        return cls(
            source_root=Path(str(paths["source_root"])),
            output_root=Path(str(paths["output_root"])),
            runtime_root=Path(str(paths["runtime_root"])),
            domain_sha256=domain.sha256,
            profile_sha256=profile.sha256,
            source_lock_sha256=str(profile.document["source_lock_sha256"]),
            emulator_relative=emulator_relative,
            adb_relative=adb_relative,
            image_relative=image_relative,
            domain=domain,
            peer_domain=peer_domain,
        )


def load_runtime_bundle_inputs(
    domain_path: Path,
    profile_path: Path,
    peer_domain_path: Path | None = None,
) -> RuntimeBundleInputs:
    domain = AndroidBuildDomain.from_path(domain_path, expected_backend="kvm")
    profile = KvmImageBuildProfile.from_mapping(
        json.loads(profile_path.read_text(encoding="utf-8"))
    )
    peer_domain = (
        AndroidBuildDomain.from_path(peer_domain_path, expected_backend="redroid")
        if peer_domain_path is not None
        else None
    )
    return RuntimeBundleInputs.from_contracts(domain, profile, peer_domain)


def _safe_relative(path: Path, label: str) -> Path:
    if path.is_absolute() or not path.parts or ".." in path.parts:
        raise KvmRuntimeBundleError(f"{label} must be a safe relative path")
    return path


def _validate_release_id(release_id: str) -> None:
    if RELEASE_ID.fullmatch(release_id) is None:
        raise KvmRuntimeBundleError("release id contains unsupported characters")


def _lexists(path: Path) -> bool:
    return os.path.lexists(os.fspath(path))


def _read_release_root_mode(path: Path) -> int:
    # Windows does not expose POSIX directory execute bits. Publication and
    # production verification run on Linux; Windows uses the contract value so
    # the platform-independent content tests can still exercise the workflow.
    if os.name == "nt":
        return RUNTIME_RELEASE_ROOT_MODE
    return stat.S_IMODE(path.stat().st_mode)


def _read_sdk_platforms_mode(path: Path) -> int:
    if os.name == "nt":
        return SDK_PLATFORMS_MODE
    return stat.S_IMODE(path.stat().st_mode)


def _require_release_root_mode(mode: int) -> None:
    if stat.S_IMODE(mode) != RUNTIME_RELEASE_ROOT_MODE:
        raise KvmRuntimeBundleError("runtime release root mode must be exactly 0755")


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _sha256_file(path: Path) -> tuple[int, str]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(8 * 1024 * 1024), b""):
            size += len(chunk)
            digest.update(chunk)
    return size, digest.hexdigest()


def _snapshot_digest(entries: Sequence[Mapping[str, Any]]) -> str:
    canonical = json.dumps(
        list(entries), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def snapshot_tree(root: Path) -> dict[str, Any]:
    """Hash every file/link and record enough structure to detect extra entries."""

    if root.is_symlink() or not root.is_dir():
        raise KvmRuntimeBundleError(
            f"runtime component is not a real directory: {root}"
        )
    resolved_root = root.resolve(strict=True)
    raw_entries: list[dict[str, Any]] = []
    inode_paths: dict[tuple[int, int], list[str]] = {}

    def visit(directory: Path, relative: Path) -> None:
        with os.scandir(directory) as iterator:
            children = sorted(iterator, key=lambda item: item.name)
        for child in children:
            child_path = directory / child.name
            child_relative = relative / child.name
            relative_text = child_relative.as_posix()
            info = child.stat(follow_symlinks=False)
            mode = stat.S_IMODE(info.st_mode)
            if stat.S_ISDIR(info.st_mode):
                raw_entries.append(
                    {"path": relative_text, "kind": "directory", "mode": mode}
                )
                visit(child_path, child_relative)
                continue
            if stat.S_ISREG(info.st_mode):
                size, digest = _sha256_file(child_path)
                raw_entries.append(
                    {
                        "path": relative_text,
                        "kind": "file",
                        "mode": mode,
                        "bytes": size,
                        "sha256": digest,
                        "_inode": (info.st_dev, info.st_ino),
                    }
                )
                if info.st_nlink > 1:
                    inode_paths.setdefault((info.st_dev, info.st_ino), []).append(
                        relative_text
                    )
                continue
            if stat.S_ISLNK(info.st_mode):
                target = os.readlink(child_path)
                if os.path.isabs(target):
                    raise KvmRuntimeBundleError(
                        f"runtime component contains an absolute symlink: {child_path}"
                    )
                try:
                    resolved_target = (child_path.parent / target).resolve(strict=True)
                except FileNotFoundError as exc:
                    raise KvmRuntimeBundleError(
                        f"runtime component contains a broken symlink: {child_path}"
                    ) from exc
                if not _is_within(resolved_target, resolved_root):
                    raise KvmRuntimeBundleError(
                        f"runtime component symlink escapes its bundle: {child_path}"
                    )
                encoded = os.fsencode(target)
                raw_entries.append(
                    {
                        "path": relative_text,
                        "kind": "symlink",
                        "mode": mode,
                        "bytes": len(encoded),
                        "sha256": hashlib.sha256(encoded).hexdigest(),
                        "target": target,
                    }
                )
                continue
            raise KvmRuntimeBundleError(
                f"runtime component contains an unsupported filesystem entry: {child_path}"
            )

    visit(root, Path())
    hardlink_groups = {
        inode: f"hardlink-{index}"
        for index, (inode, paths) in enumerate(
            sorted(inode_paths.items(), key=lambda item: item[1][0]), start=1
        )
        if len(paths) > 1
    }
    entries: list[dict[str, Any]] = []
    for raw in sorted(raw_entries, key=lambda item: str(item["path"])):
        entry = dict(raw)
        inode = entry.pop("_inode", None)
        if inode in hardlink_groups:
            entry["hardlink_group"] = hardlink_groups[inode]
        entries.append(entry)
    return {"tree_sha256": _snapshot_digest(entries), "entries": entries}


def snapshot_component(path: Path) -> dict[str, Any]:
    """Snapshot either a complete directory component or one pinned file."""

    if path.is_symlink():
        raise KvmRuntimeBundleError(f"runtime component must not be a symlink: {path}")
    if path.is_dir():
        return snapshot_tree(path)
    if not path.is_file():
        raise KvmRuntimeBundleError(f"runtime component is unavailable: {path}")
    info = path.stat()
    size, digest = _sha256_file(path)
    entries = [
        {
            "path": path.name,
            "kind": "file",
            "mode": stat.S_IMODE(info.st_mode),
            "bytes": size,
            "sha256": digest,
        }
    ]
    return {"tree_sha256": _snapshot_digest(entries), "entries": entries}


def _component_sources(inputs: RuntimeBundleInputs) -> dict[str, tuple[Path, Path]]:
    return {
        "emulator": (
            inputs.source_root / inputs.emulator_relative,
            RUNTIME_COMPONENT_TARGETS["emulator"],
        ),
        "adb": (
            inputs.source_root / inputs.adb_relative,
            RUNTIME_COMPONENT_TARGETS["adb"],
        ),
        "images": (
            inputs.output_root / inputs.image_relative,
            RUNTIME_COMPONENT_TARGETS["images"],
        ),
    }


def _validate_source_contract(inputs: RuntimeBundleInputs) -> None:
    marker = inputs.source_root / ".alas-kvm-build-source-lock"
    if marker.is_symlink() or not marker.is_file():
        raise KvmRuntimeBundleError(f"KVM source lock marker is unavailable: {marker}")
    if marker.read_text(encoding="utf-8").strip() != inputs.source_lock_sha256:
        raise KvmRuntimeBundleError("KVM source lock marker differs from build profile")
    sources = _component_sources(inputs)
    emulator_root = sources["emulator"][0]
    for relative in (
        Path("emulator"),
        Path("emulator-check"),
    ):
        if not (emulator_root / relative).is_file():
            raise KvmRuntimeBundleError(
                f"complete emulator bundle is missing {relative.as_posix()}"
            )
    adb = sources["adb"][0]
    if adb.is_symlink() or not adb.is_file():
        raise KvmRuntimeBundleError("profile-pinned adb must be a regular file")
    image_root = sources["images"][0]
    for name in REQUIRED_IMAGES:
        if not (image_root / name).is_file():
            raise KvmRuntimeBundleError(f"Goldfish image sysdir is missing {name}")


@contextlib.contextmanager
def publish_snapshot_scope(_inputs: RuntimeBundleInputs) -> Iterator[None]:
    """Keep publication injectable without introducing a build lock.

    Source stability is established by before/after content snapshots.  The
    KVM and Redroid domains have disjoint mutable roots, so a cross-backend
    advisory lock would not protect an additional correctness boundary.
    """

    yield


def require_publish_output(inputs: RuntimeBundleInputs) -> Mapping[str, Any]:
    """Require a backend-owned KVM output and a disjoint Redroid peer."""

    if inputs.domain is None or inputs.peer_domain is None:
        raise KvmRuntimeBundleError(
            "publishing requires both KVM and Redroid build-domain contracts"
        )
    try:
        return require_output_buildable(
            inputs.domain,
            inputs.peer_domain,
            backend="kvm",
            for_build=False,
        )
    except PermissionError:
        # Separate build accounts cannot traverse the peer's private roots.
        # Elevate only the read-only inspection, never the publisher/copy.
        check = """
import json, sys
from alas_headless.android_build_domain import AndroidBuildDomain
from alas_headless.android_build_domain_migration import require_output_buildable
documents = json.load(sys.stdin)
domain = AndroidBuildDomain.from_mapping(documents[0], expected_backend='kvm')
peer = AndroidBuildDomain.from_mapping(documents[1], expected_backend='redroid')
print(json.dumps(require_output_buildable(domain, peer, backend='kvm', for_build=False)))
"""
        result = subprocess.run(
            ["sudo", "-n", "env", f"PYTHONPATH={Path(__file__).resolve().parents[1]}",
             sys.executable, "-c", check],
            input=json.dumps([dict(inputs.domain.document), dict(inputs.peer_domain.document)]),
            text=True, capture_output=True, check=False, timeout=60,
        )
        if result.returncode:
            raise KvmRuntimeBundleError(
                f"read-only output ownership inspection failed: {result.stderr.strip()}"
            )
        return json.loads(result.stdout)
    except AndroidBuildDomainMigrationError as exc:
        raise KvmRuntimeBundleError(
            f"build output ownership check failed: {exc}"
        ) from exc


def rsync_component(source: Path, target: Path) -> None:
    if source.is_dir() and not source.is_symlink():
        source_argument = os.fspath(source) + os.sep
        target_argument = os.fspath(target) + os.sep
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
        source_argument = os.fspath(source)
        target_argument = os.fspath(target)
    command = [
        "rsync",
        "-aHAX",
        "--sparse",
        "--",
        source_argument,
        target_argument,
    ]
    try:
        completed = subprocess.run(command, check=False)
    except FileNotFoundError as exc:
        raise KvmRuntimeBundleError(
            "rsync is required to publish a runtime release"
        ) from exc
    if completed.returncode != 0:
        raise KvmRuntimeBundleError(
            f"rsync failed for runtime component {source} with exit {completed.returncode}"
        )


def _fsync_directory(path: Path) -> None:
    try:
        descriptor = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _rename_noreplace(source: Path, target: Path) -> None:
    if _lexists(target):
        raise KvmRuntimeBundleError(f"runtime release already exists: {target}")
    if sys.platform == "linux":
        libc = ctypes.CDLL(None, use_errno=True)
        renameat2 = getattr(libc, "renameat2", None)
        if renameat2 is None:
            raise KvmRuntimeBundleError(
                "renameat2 is required for atomic no-overwrite release publication"
            )
        renameat2.argtypes = [
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_uint,
        ]
        renameat2.restype = ctypes.c_int
        at_fdcwd = -100
        rename_noreplace = 1
        result = renameat2(
            at_fdcwd,
            os.fsencode(source),
            at_fdcwd,
            os.fsencode(target),
            rename_noreplace,
        )
        if result != 0:
            error = ctypes.get_errno()
            if error == errno.EEXIST:
                raise KvmRuntimeBundleError(f"runtime release already exists: {target}")
            raise KvmRuntimeBundleError(
                f"atomic runtime release rename failed: {os.strerror(error)}"
            )
        return
    # Unit tests run on Windows. os.rename refuses an existing directory there;
    # Linux publication always takes the race-safe renameat2 path above.
    try:
        os.rename(source, target)
    except FileExistsError as exc:
        raise KvmRuntimeBundleError(
            f"runtime release already exists: {target}"
        ) from exc


def _write_manifest(path: Path, value: Mapping[str, Any]) -> None:
    temporary = path.with_name(".manifest.json.tmp")
    payload = (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")
    descriptor = os.open(
        temporary,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL,
        0o644,
    )
    try:
        with os.fdopen(descriptor, "wb") as output:
            output.write(payload)
            output.flush()
            os.fsync(output.fileno())
    except BaseException:
        with contextlib.suppress(FileNotFoundError):
            temporary.unlink()
        raise
    os.replace(temporary, path)
    _fsync_directory(path.parent)


def publish_runtime_release(
    inputs: RuntimeBundleInputs,
    release_id: str,
    *,
    copy_tree: Callable[[Path, Path], None] = rsync_component,
    snapshot_scope_factory: Callable[
        [RuntimeBundleInputs], ContextManager[None]
    ] = publish_snapshot_scope,
    output_check: Callable[
        [RuntimeBundleInputs], Mapping[str, Any] | None
    ] = require_publish_output,
    rename_release: Callable[[Path, Path], None] = _rename_noreplace,
    created_epoch: int | None = None,
) -> Path:
    _validate_release_id(release_id)
    with snapshot_scope_factory(inputs):
        output_check(inputs)
        _validate_source_contract(inputs)
        releases = inputs.runtime_root / "releases"
        if releases.is_symlink():
            raise KvmRuntimeBundleError(
                "runtime releases directory must not be a symlink"
            )
        releases.mkdir(parents=True, exist_ok=True)
        target = releases / release_id
        if _lexists(target):
            raise KvmRuntimeBundleError(f"runtime release already exists: {target}")
        stage = Path(tempfile.mkdtemp(prefix=f".{release_id}.staging.", dir=releases))
        try:
            components: dict[str, Any] = {}
            for name, (source, relative_target) in _component_sources(inputs).items():
                before = snapshot_component(source)
                staged_target = stage / relative_target
                copy_tree(source, staged_target)
                after = snapshot_component(source)
                copied = snapshot_component(staged_target)
                if before != after:
                    raise KvmRuntimeBundleError(
                        f"runtime component source changed during publish: {name}"
                    )
                if before != copied:
                    raise KvmRuntimeBundleError(
                        f"copied runtime component differs from its source: {name}"
                    )
                components[name] = {
                    "source": os.fspath(source),
                    "target": relative_target.as_posix(),
                    "source_before": before,
                    "source_after": after,
                    "target_snapshot": copied,
                }
            sdk_platforms = stage / "sdk" / "platforms"
            sdk_platforms.mkdir(mode=SDK_PLATFORMS_MODE)
            os.chmod(sdk_platforms, SDK_PLATFORMS_MODE)
            _fsync_directory(sdk_platforms)
            _fsync_directory(sdk_platforms.parent)
            manifest = {
                "schema": RUNTIME_RELEASE_SCHEMA,
                "backend": "kvm",
                "release_id": release_id,
                "created_epoch": int(
                    time.time() if created_epoch is None else created_epoch
                ),
                "contracts": {
                    "domain_sha256": inputs.domain_sha256,
                    "profile_sha256": inputs.profile_sha256,
                    "source_lock_sha256": inputs.source_lock_sha256,
                },
                "output_residency": "backend-owned",
                "components": components,
            }
            _write_manifest(stage / "manifest.json", manifest)
            os.chmod(stage, RUNTIME_RELEASE_ROOT_MODE)
            _fsync_directory(stage)
            verify_release_directory(inputs, release_id, stage)
            rename_release(stage, target)
            _fsync_directory(releases)
            return target
        finally:
            if _lexists(stage):
                shutil.rmtree(stage)


def _validate_recorded_snapshot(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != {"tree_sha256", "entries"}:
        raise KvmRuntimeBundleError(f"{label} snapshot fields differ")
    entries = value["entries"]
    if not isinstance(entries, list):
        raise KvmRuntimeBundleError(f"{label} snapshot entries must be a list")
    previous = ""
    for entry in entries:
        if not isinstance(entry, Mapping):
            raise KvmRuntimeBundleError(f"{label} snapshot entry must be an object")
        path = str(entry.get("path", ""))
        if (
            not path
            or path <= previous
            or Path(path).is_absolute()
            or ".." in Path(path).parts
        ):
            raise KvmRuntimeBundleError(f"{label} snapshot paths are not canonical")
        previous = path
        kind = entry.get("kind")
        if kind == "directory":
            allowed = {"path", "kind", "mode"}
        elif kind == "file":
            allowed = {"path", "kind", "mode", "bytes", "sha256", "hardlink_group"}
            required = allowed - {"hardlink_group"}
            if not required.issubset(entry) or not set(entry).issubset(allowed):
                raise KvmRuntimeBundleError(f"{label} file snapshot fields differ")
            if SHA256.fullmatch(str(entry.get("sha256", ""))) is None:
                raise KvmRuntimeBundleError(f"{label} file digest is malformed")
            continue
        elif kind == "symlink":
            allowed = {"path", "kind", "mode", "bytes", "sha256", "target"}
            if (
                set(entry) != allowed
                or SHA256.fullmatch(str(entry.get("sha256", ""))) is None
            ):
                raise KvmRuntimeBundleError(f"{label} symlink snapshot fields differ")
            continue
        else:
            raise KvmRuntimeBundleError(f"{label} snapshot entry kind is unsupported")
        if set(entry) != allowed:
            raise KvmRuntimeBundleError(f"{label} directory snapshot fields differ")
    if value["tree_sha256"] != _snapshot_digest(entries):
        raise KvmRuntimeBundleError(f"{label} snapshot tree digest differs")
    return value


def _verify_release_content(
    release: Path, expected_release_id: str
) -> Mapping[str, Any]:
    _validate_release_id(expected_release_id)
    if release.is_symlink() or not release.is_dir():
        raise KvmRuntimeBundleError(f"runtime release is unavailable: {release}")
    _require_release_root_mode(_read_release_root_mode(release))
    manifest_path = release / "manifest.json"
    if manifest_path.is_symlink() or not manifest_path.is_file():
        raise KvmRuntimeBundleError("runtime release manifest is unavailable")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise KvmRuntimeBundleError("runtime release manifest is malformed") from exc
    if not isinstance(manifest, Mapping) or set(manifest) != {
        "schema",
        "backend",
        "release_id",
        "created_epoch",
        "contracts",
        "output_residency",
        "components",
    }:
        raise KvmRuntimeBundleError("runtime release manifest fields differ")
    if (
        manifest.get("schema") != RUNTIME_RELEASE_SCHEMA
        or manifest.get("backend") != "kvm"
    ):
        raise KvmRuntimeBundleError("runtime release manifest identity differs")
    if manifest.get("release_id") != expected_release_id:
        raise KvmRuntimeBundleError("runtime release id differs from its directory")
    if not isinstance(manifest.get("created_epoch"), int):
        raise KvmRuntimeBundleError("runtime release creation time is malformed")
    if manifest.get("output_residency") != "backend-owned":
        raise KvmRuntimeBundleError("runtime release output residency differs")
    contracts = manifest.get("contracts")
    if (
        not isinstance(contracts, Mapping)
        or set(contracts)
        != {
            "domain_sha256",
            "profile_sha256",
            "source_lock_sha256",
        }
        or any(SHA256.fullmatch(str(value)) is None for value in contracts.values())
    ):
        raise KvmRuntimeBundleError("runtime release contracts are malformed")
    components = manifest.get("components")
    if not isinstance(components, Mapping) or set(components) != set(
        RUNTIME_COMPONENT_TARGETS
    ):
        raise KvmRuntimeBundleError("runtime release components differ")
    for name, relative_target in RUNTIME_COMPONENT_TARGETS.items():
        component = components[name]
        if not isinstance(component, Mapping) or set(component) != {
            "source",
            "target",
            "source_before",
            "source_after",
            "target_snapshot",
        }:
            raise KvmRuntimeBundleError(f"runtime component manifest differs: {name}")
        if (
            not isinstance(component["source"], str)
            or not Path(component["source"]).is_absolute()
        ):
            raise KvmRuntimeBundleError(
                f"runtime component source is malformed: {name}"
            )
        if component["target"] != relative_target.as_posix():
            raise KvmRuntimeBundleError(f"runtime component target differs: {name}")
        before = _validate_recorded_snapshot(
            component["source_before"], f"{name} before"
        )
        after = _validate_recorded_snapshot(component["source_after"], f"{name} after")
        recorded_target = _validate_recorded_snapshot(
            component["target_snapshot"], f"{name} target"
        )
        if before != after or before != recorded_target:
            raise KvmRuntimeBundleError(f"runtime component snapshots differ: {name}")
        actual = snapshot_component(release / relative_target)
        if actual != recorded_target:
            raise KvmRuntimeBundleError(f"runtime component is damaged: {name}")

    if {path.name for path in release.iterdir()} != {
        "emulator",
        "sdk",
        "images",
        "manifest.json",
    }:
        raise KvmRuntimeBundleError(
            "runtime release contains unexpected top-level entries"
        )
    sdk = release / "sdk"
    if (
        sdk.is_symlink()
        or not sdk.is_dir()
        or {item.name for item in sdk.iterdir()} != {"platform-tools", "platforms"}
    ):
        raise KvmRuntimeBundleError("runtime release SDK layout differs")
    platform_tools = sdk / "platform-tools"
    if (
        platform_tools.is_symlink()
        or not platform_tools.is_dir()
        or {item.name for item in platform_tools.iterdir()} != {"adb"}
    ):
        raise KvmRuntimeBundleError("runtime release platform-tools layout differs")
    platforms = sdk / "platforms"
    if platforms.is_symlink() or not platforms.is_dir():
        raise KvmRuntimeBundleError(
            "runtime release SDK platforms must be a real directory"
        )
    if any(platforms.iterdir()):
        raise KvmRuntimeBundleError("runtime release SDK platforms must be empty")
    if stat.S_IMODE(_read_sdk_platforms_mode(platforms)) != SDK_PLATFORMS_MODE:
        raise KvmRuntimeBundleError(
            "runtime release SDK platforms mode must be exactly 0755"
        )
    return manifest


def verify_pinned_runtime_release(release_root: Path) -> Path:
    """Verify a release without consulting mutable build source or output roots."""

    release = Path(release_root)
    _validate_release_id(release.name)
    if release.parent.is_symlink():
        raise KvmRuntimeBundleError("runtime releases directory must not be a symlink")
    _verify_release_content(release, release.name)
    return release.resolve(strict=True)


def verify_release_directory(
    inputs: RuntimeBundleInputs,
    release_id: str,
    release: Path,
) -> Path:
    manifest = _verify_release_content(release, release_id)
    expected_contracts = {
        "domain_sha256": inputs.domain_sha256,
        "profile_sha256": inputs.profile_sha256,
        "source_lock_sha256": inputs.source_lock_sha256,
    }
    if manifest["contracts"] != expected_contracts:
        raise KvmRuntimeBundleError("runtime release contracts differ")
    expected_sources = _component_sources(inputs)
    for name, (source, _relative_target) in expected_sources.items():
        if manifest["components"][name]["source"] != os.fspath(source):
            raise KvmRuntimeBundleError(f"runtime component source differs: {name}")
    return release


def verify_runtime_release(inputs: RuntimeBundleInputs, release_id: str) -> Path:
    _validate_release_id(release_id)
    release = inputs.runtime_root / "releases" / release_id
    return verify_release_directory(inputs, release_id, release)


def _service_is_inactive(unit: str) -> None:
    if SYSTEMD_UNIT.fullmatch(unit) is None:
        raise KvmRuntimeBundleError("emulator systemd service name is invalid")
    completed = subprocess.run(
        ["systemctl", "show", "--property=ActiveState", "--value", "--", unit],
        check=False,
        capture_output=True,
        text=True,
    )
    state = completed.stdout.strip()
    if completed.returncode != 0:
        detail = completed.stderr.strip() or "systemctl show failed"
        raise KvmRuntimeBundleError(f"cannot inspect emulator service: {detail}")
    if state != "inactive":
        raise KvmRuntimeBundleError(
            f"emulator service must already be inactive; observed {state or 'unknown'}"
        )


def _replace_image_sysdir(config: bytes, image_sysdir: str) -> bytes:
    try:
        text = config.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise KvmRuntimeBundleError("AVD config.ini is not UTF-8") from exc
    lines = text.splitlines(keepends=True)
    indices = [
        index for index, line in enumerate(lines) if line.startswith("image.sysdir.1=")
    ]
    if len(indices) != 1:
        raise KvmRuntimeBundleError(
            "AVD config must contain exactly one image.sysdir.1"
        )
    index = indices[0]
    line = lines[index]
    ending = "\r\n" if line.endswith("\r\n") else "\n" if line.endswith("\n") else ""
    lines[index] = f"image.sysdir.1={image_sysdir}{ending}"
    return "".join(lines).encode("utf-8")


def switch_avd_runtime_release(
    inputs: RuntimeBundleInputs,
    release_id: str,
    avd_home: Path,
    avd_name: str,
    emulator_service: str,
    *,
    require_service_inactive: Callable[[str], None] = _service_is_inactive,
    action: str = "switch",
) -> Mapping[str, Any]:
    if action not in {"switch", "rollback"}:
        raise KvmRuntimeBundleError("AVD release action must be switch or rollback")
    if RELEASE_ID.fullmatch(avd_name) is None:
        raise KvmRuntimeBundleError("AVD name contains unsupported characters")
    release = verify_runtime_release(inputs, release_id)
    require_service_inactive(emulator_service)

    avd_directory = avd_home / f"{avd_name}.avd"
    config = avd_directory / "config.ini"
    if config.is_symlink() or not config.is_file():
        raise KvmRuntimeBundleError(f"AVD config is unavailable: {config}")
    source_info = config.stat()
    current = config.read_bytes()
    image_sysdir = os.fspath(release / "images") + os.sep
    updated = _replace_image_sysdir(current, image_sysdir)
    if updated == current:
        return {
            "action": action,
            "changed": False,
            "release_id": release_id,
            "config": os.fspath(config),
            "backup": None,
            "image_sysdir": image_sysdir,
        }

    backups = avd_directory / "config.ini.alas-backups"
    if backups.is_symlink():
        raise KvmRuntimeBundleError("AVD config backup directory must not be a symlink")
    backups.mkdir(mode=0o700, exist_ok=True)
    original_sha = hashlib.sha256(current).hexdigest()
    backup = backups / f"{time.time_ns()}-{action}-{release_id}-{original_sha[:12]}.ini"
    descriptor = os.open(backup, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as output:
            output.write(current)
            output.flush()
            os.fsync(output.fileno())
        if os.name == "posix":
            os.chown(backup, source_info.st_uid, source_info.st_gid)
        shutil.copystat(config, backup, follow_symlinks=False)
        if os.name == "posix":
            backup_descriptor = os.open(backup, os.O_RDONLY)
            try:
                os.fsync(backup_descriptor)
            finally:
                os.close(backup_descriptor)
        backup_info = backup.stat()
        if (
            backup_info.st_uid != source_info.st_uid
            or backup_info.st_gid != source_info.st_gid
            or stat.S_IMODE(backup_info.st_mode) != stat.S_IMODE(source_info.st_mode)
        ):
            raise KvmRuntimeBundleError(
                "AVD config backup did not preserve ownership and mode"
            )
        _fsync_directory(backups)
    except BaseException:
        with contextlib.suppress(FileNotFoundError):
            backup.unlink()
        raise

    temporary_descriptor, temporary_name = tempfile.mkstemp(
        prefix=".config.ini.", suffix=".tmp", dir=avd_directory
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(temporary_descriptor, "wb") as output:
            output.write(updated)
            output.flush()
            os.fsync(output.fileno())
        if os.name == "posix":
            os.chown(temporary, source_info.st_uid, source_info.st_gid)
        shutil.copystat(config, temporary, follow_symlinks=False)
        if os.name == "posix":
            temporary_descriptor = os.open(temporary, os.O_RDONLY)
            try:
                os.fsync(temporary_descriptor)
            finally:
                os.close(temporary_descriptor)
        os.replace(temporary, config)
        _fsync_directory(avd_directory)
        result_info = config.stat()
        if (
            result_info.st_uid != source_info.st_uid
            or result_info.st_gid != source_info.st_gid
            or stat.S_IMODE(result_info.st_mode) != stat.S_IMODE(source_info.st_mode)
        ):
            raise KvmRuntimeBundleError("AVD config switch changed ownership or mode")
    finally:
        with contextlib.suppress(FileNotFoundError):
            temporary.unlink()
    return {
        "action": action,
        "changed": True,
        "release_id": release_id,
        "config": os.fspath(config),
        "backup": os.fspath(backup),
        "image_sysdir": image_sysdir,
    }
