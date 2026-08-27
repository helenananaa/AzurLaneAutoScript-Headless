"""Fail-closed deployment of one immutable KVM runtime release.

Publishing a runtime bundle deliberately does not mutate the live AVD.  This
module owns the separate deployment boundary: a reproducible systemd unit, an
offline full-AVD snapshot, the image-sysdir switch, dedicated ADB startup, and
post-start proof that the emulator cgroup no longer consumes mutable Android
build state.

The module never restores userdata automatically after a new system image has
booted.  Guest startup can migrate persistent state in ways that a generic
host-side tool cannot safely reverse.  Receipts therefore retain the complete
offline snapshot and explicit recovery instructions.
"""

from __future__ import annotations

import contextlib
import base64
import ctypes
import errno
import hashlib
import ipaddress
import json
import os
import re
import shlex
import shutil
import stat
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

from .kvm_runtime_bundle import (
    RuntimeBundleInputs,
    load_runtime_bundle_inputs,
    snapshot_component,
    switch_avd_runtime_release,
    verify_runtime_release,
)
from .runtime_backend_kvm import KvmBackend, KvmRuntimeConfig
from .runtime_backends import backend_from_config
from .runtime_command import RuntimeCommandExecutor


UNIT_RECEIPT_SCHEMA = "alas-headless.kvm-systemd-unit-install-receipt/v1"
PREPARE_RECEIPT_SCHEMA = "alas-headless.kvm-live-cutover-prepare-receipt/v1"
ACTIVATION_RECEIPT_SCHEMA = "alas-headless.kvm-live-cutover-activation-receipt/v1"
SNAPSHOT_SCHEMA = "alas-headless.kvm-avd-offline-snapshot/v1"
PREVIOUS_UNIT_ARCHIVE_SCHEMA = "alas-headless.kvm-previous-systemd-unit-archive/v1"
PHASE_MARKER_SCHEMA = "alas-headless.kvm-live-cutover-phase/v1"
RECOVERY_PLAN_SCHEMA = "alas-headless.kvm-live-cutover-recovery-plan/v1"

UNIT_NAME = re.compile(r"^[A-Za-z0-9_.@:-]+[.]service$")
USER_NAME = re.compile(r"^[a-z_][a-z0-9_-]{0,31}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
EXACT_CONSOLE_PORT = 5588
EXACT_TRANSPORT_SERIAL = "127.0.0.1:5589"
EXACT_ADB_SERVER_PORT = 5043
DEFAULT_STOP_TIMEOUT_SECONDS = 90
DEFAULT_CUTOVER_LOCK = Path("/run/alas-headless/kvm-live-cutover.lock")
PF_KTHREAD = 0x00200000

CommandRunner = Callable[[Sequence[str], float], subprocess.CompletedProcess[str]]


class KvmLiveCutoverError(RuntimeError):
    """Raised when the formal live cutover cannot be proven safe."""


@dataclass(frozen=True)
class UserIdentity:
    name: str
    uid: int
    home: Path
    gid: int | None = None


@dataclass(frozen=True)
class CutoverContext:
    inputs: RuntimeBundleInputs
    release_id: str
    release_root: Path
    domain_path: Path
    profile_path: Path
    runtime_config_path: Path
    runtime_document: Mapping[str, Any]
    runtime_config: KvmRuntimeConfig
    archive_root: Path
    evidence_root: Path

    @property
    def avd_directory(self) -> Path:
        return self.runtime_config.avd_home / f"{self.runtime_config.avd_name}.avd"

    @property
    def avd_descriptor(self) -> Path:
        return self.runtime_config.avd_home / f"{self.runtime_config.avd_name}.ini"

    @property
    def avd_config(self) -> Path:
        return self.avd_directory / "config.ini"


@contextlib.contextmanager
def exclusive_cutover_lock(path: Path | None):
    """Serialize every formal cutover phase on this host.

    The Linux deployment path uses kernel flock, so an interrupted manager does
    not leave a false permanent lock.  The O_EXCL branch exists only for local
    non-Linux contract tests; the formal CLI itself requires Linux/root.
    """

    if path is None:
        yield
        return
    if not path.is_absolute():
        raise KvmLiveCutoverError("cutover lock path must be absolute")
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.parent.is_symlink() or path.is_symlink():
        raise KvmLiveCutoverError("cutover lock path must not traverse a symlink")
    if sys.platform == "linux":
        import fcntl

        handle = path.open("a+b")
        try:
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise KvmLiveCutoverError(
                    f"another KVM live cutover phase holds {path}"
                ) from exc
            yield
        finally:
            handle.close()
        return
    descriptor: int | None = None
    try:
        try:
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError as exc:
            raise KvmLiveCutoverError(
                f"another KVM live cutover phase holds {path}"
            ) from exc
        os.write(descriptor, f"pid={os.getpid()}\n".encode("ascii"))
        yield
    finally:
        if descriptor is not None:
            os.close(descriptor)
            with contextlib.suppress(FileNotFoundError):
                path.unlink()


def _run_command(
    argv: Sequence[str], timeout_seconds: float
) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            list(argv),
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        raise KvmLiveCutoverError(
            f"command timed out after {timeout_seconds:g}s: {argv[0]}"
        ) from exc
    except FileNotFoundError as exc:
        raise KvmLiveCutoverError(
            f"required command is unavailable: {argv[0]}"
        ) from exc
    except OSError as exc:
        raise KvmLiveCutoverError(
            f"cannot execute required command {argv[0]}: {exc}"
        ) from exc


def _require_success(
    completed: subprocess.CompletedProcess[str], label: str
) -> subprocess.CompletedProcess[str]:
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip() or "no diagnostic"
        raise KvmLiveCutoverError(
            f"{label} failed with exit {completed.returncode}: {detail}"
        )
    return completed


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _fsync_directory(path: Path) -> None:
    """Persist directory entries on the Linux deployment host."""

    if os.name != "posix":
        return
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    descriptor = os.open(path, flags)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _fsync_tree(root: Path) -> None:
    """Make a completed recovery tree durable before publishing its name."""

    if os.name != "posix":
        return
    directories: list[Path] = []
    for current, names, files in os.walk(root, topdown=True, followlinks=False):
        current_path = Path(current)
        directories.append(current_path)
        for name in [*names, *files]:
            path = current_path / name
            if path.is_symlink() or not path.is_file():
                continue
            descriptor = os.open(
                path,
                os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
            )
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
    for directory in reversed(directories):
        _fsync_directory(directory)


def _canonical_receipt_payload(value: Mapping[str, Any]) -> bytes:
    unsigned = {key: item for key, item in value.items() if key != "self_sha256"}
    return json.dumps(
        unsigned, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def _with_self_sha256(value: Mapping[str, Any]) -> dict[str, Any]:
    result = dict(value)
    result["self_sha256"] = _sha256_bytes(_canonical_receipt_payload(result))
    return result


def _validate_receipt(value: Any, schema: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or value.get("schema") != schema:
        raise KvmLiveCutoverError(f"receipt schema mismatch: expected {schema}")
    expected = value.get("self_sha256")
    if not isinstance(expected, str) or SHA256.fullmatch(expected) is None:
        raise KvmLiveCutoverError("receipt self hash is malformed")
    if expected != _sha256_bytes(_canonical_receipt_payload(value)):
        raise KvmLiveCutoverError("receipt self hash differs")
    return value


def _write_json_noreplace(path: Path, value: Mapping[str, Any]) -> Mapping[str, Any]:
    if not path.is_absolute():
        raise KvmLiveCutoverError("receipt path must be absolute")
    if os.path.lexists(path):
        raise KvmLiveCutoverError(f"refusing to overwrite receipt: {path}")
    parent_existed = path.parent.is_dir()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.parent.is_symlink():
        raise KvmLiveCutoverError("receipt parent must not be a symlink")
    document = _with_self_sha256(value)
    payload = (json.dumps(document, indent=2, sort_keys=True) + "\n").encode("utf-8")
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as output:
            output.write(payload)
            output.flush()
            os.fsync(output.fileno())
    except BaseException:
        with contextlib.suppress(FileNotFoundError):
            path.unlink()
        raise
    _fsync_directory(path.parent)
    if not parent_existed:
        _fsync_directory(path.parent.parent)
    return document


def _require_new_receipt_path(path: Path) -> None:
    if os.path.lexists(path):
        raise KvmLiveCutoverError(f"refusing to overwrite receipt: {path}")


def load_receipt(path: Path, schema: str) -> Mapping[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise KvmLiveCutoverError(
            f"receipt is unavailable or malformed: {path}"
        ) from exc
    return _validate_receipt(value, schema)


def _load_phase_marker(path: Path) -> Mapping[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise KvmLiveCutoverError(
            f"cutover phase marker is unavailable: {path}"
        ) from exc
    return _validate_receipt(value, PHASE_MARKER_SCHEMA)


def _update_phase_marker(
    path: Path | None,
    context: CutoverContext,
    unit: str,
    phase: str,
    *,
    expected_phases: set[str | None],
    previous_unit: str | None = None,
    evidence: Mapping[str, Any] | None = None,
    created_epoch: int | None = None,
) -> Mapping[str, Any] | None:
    if path is None:
        return None
    _require_within(path, context.evidence_root, "cutover phase marker")
    previous: Mapping[str, Any] | None = None
    if os.path.lexists(path):
        if path.is_symlink() or not path.is_file():
            raise KvmLiveCutoverError("cutover phase marker must be a regular file")
        previous = _load_phase_marker(path)
        if (
            previous.get("backend") != "kvm"
            or previous.get("release_id") != context.release_id
            or previous.get("release_root") != os.fspath(context.release_root)
            or previous.get("unit") != unit
        ):
            raise KvmLiveCutoverError(
                "cutover phase marker belongs to another deployment"
            )
        recorded_previous = previous.get("previous_unit")
        if (
            previous_unit is not None
            and recorded_previous is not None
            and recorded_previous != previous_unit
        ):
            raise KvmLiveCutoverError("cutover phase marker previous unit differs")
    observed = None if previous is None else str(previous.get("phase"))
    if observed not in expected_phases:
        expected = ", ".join(
            "absent" if item is None else item
            for item in sorted(expected_phases, key=str)
        )
        raise KvmLiveCutoverError(
            f"cutover phase must be {expected}; observed {observed or 'absent'}"
        )
    history = [] if previous is None else list(previous.get("history", []))
    event = {
        "phase": phase,
        "created_epoch": int(time.time() if created_epoch is None else created_epoch),
    }
    if evidence:
        event["evidence"] = dict(evidence)
    history.append(event)
    document = _with_self_sha256(
        {
            "schema": PHASE_MARKER_SCHEMA,
            "backend": "kvm",
            "release_id": context.release_id,
            "release_root": os.fspath(context.release_root),
            "unit": unit,
            "previous_unit": previous_unit
            if previous_unit is not None
            else (None if previous is None else previous.get("previous_unit")),
            "phase": phase,
            "history": history,
        }
    )
    parent_existed = path.parent.is_dir()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.parent.is_symlink():
        raise KvmLiveCutoverError("cutover phase marker parent must not be a symlink")
    _atomic_replace(
        path,
        (json.dumps(document, indent=2, sort_keys=True) + "\n").encode("utf-8"),
        0o600,
    )
    if not parent_existed:
        _fsync_directory(path.parent.parent)
    return document


def _require_phase_marker(
    path: Path | None,
    context: CutoverContext,
    unit: str,
    phase: str,
    *,
    previous_unit: str | None = None,
    evidence: Mapping[str, Any] | None = None,
) -> Mapping[str, Any] | None:
    if path is None:
        return None
    _require_within(path, context.evidence_root, "cutover phase marker")
    marker = _load_phase_marker(path)
    if (
        marker.get("backend") != "kvm"
        or marker.get("release_id") != context.release_id
        or marker.get("release_root") != os.fspath(context.release_root)
        or marker.get("unit") != unit
        or marker.get("phase") != phase
        or (previous_unit is not None and marker.get("previous_unit") != previous_unit)
    ):
        raise KvmLiveCutoverError(
            "cutover phase marker does not authorize this operation"
        )
    if evidence:
        latest = marker.get("history", [])[-1]
        recorded = latest.get("evidence") if isinstance(latest, Mapping) else None
        for key, expected in evidence.items():
            if not isinstance(recorded, Mapping) or recorded.get(key) != expected:
                raise KvmLiveCutoverError(
                    f"cutover phase marker evidence differs for {key}"
                )
    return marker


def _require_within(path: Path, root: Path, label: str) -> Path:
    resolved = path.resolve(strict=False)
    resolved_root = root.resolve(strict=False)
    try:
        resolved.relative_to(resolved_root)
    except ValueError as exc:
        raise KvmLiveCutoverError(f"{label} must stay inside {resolved_root}") from exc
    if resolved == resolved_root:
        raise KvmLiveCutoverError(f"{label} must name a child of {resolved_root}")
    return resolved


def _load_runtime_document(path: Path) -> Mapping[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise KvmLiveCutoverError(
            f"runtime config is unavailable or malformed: {path}"
        ) from exc
    if not isinstance(value, dict):
        raise KvmLiveCutoverError("runtime config must be a JSON object")
    return value


def load_cutover_context(
    domain_path: Path,
    profile_path: Path,
    release_id: str,
    runtime_config_path: Path,
) -> CutoverContext:
    domain_path = domain_path.resolve(strict=True)
    profile_path = profile_path.resolve(strict=True)
    runtime_config_path = runtime_config_path.resolve(strict=True)
    inputs = load_runtime_bundle_inputs(domain_path, profile_path)
    if inputs.domain is None:
        raise KvmLiveCutoverError("KVM build domain is unavailable")
    release = verify_runtime_release(inputs, release_id).resolve(strict=True)
    runtime_document = _load_runtime_document(runtime_config_path)
    backend = backend_from_config(
        dict(runtime_document),
        RuntimeCommandExecutor(),
        release_verifier=lambda selected: (
            release
            if selected.resolve(strict=False) == release
            else (_ for _ in ()).throw(
                KvmLiveCutoverError("runtime config selects a different release")
            )
        ),
    )
    if not isinstance(backend, KvmBackend):
        raise KvmLiveCutoverError("runtime config backend must be kvm")
    config = backend.config
    if config.runtime_release_root.resolve(strict=False) != release:
        raise KvmLiveCutoverError("runtime config release root differs")
    if config.console_port != EXACT_CONSOLE_PORT:
        raise KvmLiveCutoverError("formal KVM console port must be 5588")
    if config.serial != EXACT_TRANSPORT_SERIAL:
        raise KvmLiveCutoverError("formal KVM transport serial must be 127.0.0.1:5589")
    if config.adb_server_port != EXACT_ADB_SERVER_PORT:
        raise KvmLiveCutoverError("formal KVM ADB server port must be 5043")
    paths = inputs.domain.document["paths"]
    archive_root = Path(str(paths["archive_root"]))
    evidence_root = Path(str(paths["evidence_root"]))
    return CutoverContext(
        inputs=inputs,
        release_id=release_id,
        release_root=release,
        domain_path=domain_path,
        profile_path=profile_path,
        runtime_config_path=runtime_config_path,
        runtime_document=runtime_document,
        runtime_config=config,
        archive_root=archive_root,
        evidence_root=evidence_root,
    )


def _validate_unit_name(unit: str) -> None:
    if UNIT_NAME.fullmatch(unit) is None:
        raise KvmLiveCutoverError("systemd unit name is invalid")


def _validate_user_identity(identity: UserIdentity) -> None:
    if USER_NAME.fullmatch(identity.name) is None:
        raise KvmLiveCutoverError("systemd user name is invalid")
    if identity.name == "root" or identity.uid == 0:
        raise KvmLiveCutoverError("KVM systemd unit must use an explicit non-root user")
    if not identity.home.is_absolute():
        raise KvmLiveCutoverError("systemd user home must be absolute")
    if identity.gid is not None and identity.gid < 0:
        raise KvmLiveCutoverError("systemd user group id is invalid")


def resolve_user_identity(name: str) -> UserIdentity:
    if os.name != "posix":
        raise KvmLiveCutoverError("systemd user lookup requires a POSIX host")
    import pwd

    try:
        entry = pwd.getpwnam(name)
    except KeyError as exc:
        raise KvmLiveCutoverError(f"systemd user does not exist: {name}") from exc
    identity = UserIdentity(
        name=name,
        uid=int(entry.pw_uid),
        home=Path(entry.pw_dir),
        gid=int(entry.pw_gid),
    )
    _validate_user_identity(identity)
    return identity


def _require_unit_argument(path: Path, label: str) -> Path:
    if not path.is_absolute():
        raise KvmLiveCutoverError(f"{label} must be absolute")
    resolved = path.resolve(strict=True)
    forbidden_roots = (
        Path("/srv/android-build/src"),
        Path("/srv/android-cache/out"),
    )
    if os.name == "posix":
        for root in forbidden_roots:
            try:
                resolved.relative_to(root)
            except ValueError:
                continue
            raise KvmLiveCutoverError(
                f"{label} must not live in mutable Android build state"
            )
    if "redroid" in os.fspath(resolved).lower():
        raise KvmLiveCutoverError(f"{label} must not reference Redroid")
    if any(character.isspace() for character in os.fspath(resolved)):
        raise KvmLiveCutoverError(f"{label} cannot contain whitespace")
    return resolved


def _systemd_argument(value: str) -> str:
    if not value or any(character.isspace() for character in value):
        raise KvmLiveCutoverError(
            "systemd ExecStart arguments cannot be empty or contain whitespace"
        )
    unsafe = ['"', "'", "$", "%", ";"]
    if os.name == "posix":
        unsafe.append("\\")
    if any(character in value for character in unsafe):
        raise KvmLiveCutoverError(
            "systemd ExecStart argument contains unsafe characters"
        )
    return value


def _validate_alas_python(
    path: Path,
    identity: UserIdentity,
    runtime_root: Path,
) -> Mapping[str, Any]:
    if not path.is_absolute():
        raise KvmLiveCutoverError("ALAS Python interpreter must be absolute")
    logical = Path(os.path.abspath(os.fspath(path)))
    if any(character.isspace() for character in os.fspath(logical)):
        raise KvmLiveCutoverError("ALAS Python interpreter cannot contain whitespace")
    if "redroid" in os.fspath(logical).lower():
        raise KvmLiveCutoverError("ALAS Python interpreter must not reference Redroid")
    toolchains = (runtime_root.resolve(strict=False) / "toolchains").resolve(
        strict=False
    )
    try:
        logical_relative = logical.relative_to(toolchains)
    except ValueError as exc:
        raise KvmLiveCutoverError(
            "ALAS Python interpreter must live in the KVM runtime toolchains root"
        ) from exc
    if (
        len(logical_relative.parts) != 3
        or not logical_relative.parts[0].startswith("control-venv-")
        or logical_relative.parts[1:] != ("bin", "python")
    ):
        raise KvmLiveCutoverError(
            "ALAS Python interpreter must be a pinned control-venv bin/python"
        )
    if not os.path.lexists(logical):
        raise KvmLiveCutoverError("ALAS Python interpreter must be a regular file")
    try:
        canonical = logical.resolve(strict=True)
    except OSError as exc:
        raise KvmLiveCutoverError(
            "ALAS Python interpreter target is unavailable"
        ) from exc
    if not canonical.is_file():
        raise KvmLiveCutoverError(
            "ALAS Python interpreter target must be a regular file"
        )
    try:
        canonical.relative_to(toolchains)
    except ValueError as exc:
        raise KvmLiveCutoverError(
            "ALAS Python canonical target must remain in KVM runtime toolchains"
        ) from exc
    pyvenv_config = logical.parent.parent / "pyvenv.cfg"
    if pyvenv_config.is_symlink() or not pyvenv_config.is_file():
        raise KvmLiveCutoverError("pinned control venv pyvenv.cfg is unavailable")
    logical_info = logical.lstat()
    target_info = canonical.stat()
    config_info = pyvenv_config.stat()
    logical_mode = stat.S_IMODE(logical_info.st_mode)
    target_mode = stat.S_IMODE(target_info.st_mode)
    config_mode = stat.S_IMODE(config_info.st_mode)
    if os.name == "posix":
        if not os.access(logical, os.X_OK):
            raise KvmLiveCutoverError("ALAS Python interpreter must be executable")
        for label, info, mode in (
            ("logical interpreter", logical_info, logical_mode),
            ("canonical interpreter", target_info, target_mode),
            ("pyvenv.cfg", config_info, config_mode),
        ):
            if info.st_uid not in {0, identity.uid}:
                raise KvmLiveCutoverError(
                    f"ALAS Python {label} must be owned by root or the KVM run user"
                )
            if (
                not (label == "logical interpreter" and logical.is_symlink())
                and mode & 0o022
            ):
                raise KvmLiveCutoverError(
                    f"ALAS Python {label} must not be group/other writable"
                )
    return {
        "path": os.fspath(logical),
        "canonical_path": os.fspath(canonical),
        "logical_is_symlink": logical.is_symlink(),
        "logical_symlink_target": os.readlink(logical)
        if logical.is_symlink()
        else None,
        "logical_uid": int(getattr(logical_info, "st_uid", -1)),
        "logical_gid": int(getattr(logical_info, "st_gid", -1)),
        "logical_mode": logical_mode,
        "target_uid": int(getattr(target_info, "st_uid", -1)),
        "target_gid": int(getattr(target_info, "st_gid", -1)),
        "target_mode": target_mode,
        "sha256": _sha256_file(canonical),
        "pyvenv_config": os.fspath(pyvenv_config),
        "pyvenv_config_uid": int(getattr(config_info, "st_uid", -1)),
        "pyvenv_config_gid": int(getattr(config_info, "st_gid", -1)),
        "pyvenv_config_mode": config_mode,
        "pyvenv_config_sha256": _sha256_file(pyvenv_config),
    }


def render_systemd_unit(
    context: CutoverContext,
    unit: str,
    identity: UserIdentity,
    run_script: Path,
    alas_python: Path,
    *,
    timeout_stop_seconds: int = DEFAULT_STOP_TIMEOUT_SECONDS,
) -> bytes:
    _validate_unit_name(unit)
    _validate_user_identity(identity)
    if (
        isinstance(timeout_stop_seconds, bool)
        or not isinstance(timeout_stop_seconds, int)
        or not 15 <= timeout_stop_seconds <= 300
    ):
        raise KvmLiveCutoverError("TimeoutStopSec must be an integer in [15, 300]")
    run_script = _require_unit_argument(run_script, "run-kvm-avd.sh")
    if run_script.name != "run-kvm-avd.sh" or not run_script.is_file():
        raise KvmLiveCutoverError("systemd ExecStart must use run-kvm-avd.sh")
    if os.name == "posix" and not os.access(run_script, os.X_OK):
        raise KvmLiveCutoverError("run-kvm-avd.sh must be executable")
    python_contract = _validate_alas_python(
        alas_python, identity, context.inputs.runtime_root
    )
    domain_path = _require_unit_argument(context.domain_path, "KVM domain contract")
    profile_path = _require_unit_argument(context.profile_path, "KVM build profile")
    runtime_config_path = _require_unit_argument(
        context.runtime_config_path, "KVM runtime config"
    )
    arguments = (
        run_script,
        domain_path,
        profile_path,
        Path(context.release_id),
        runtime_config_path,
    )
    command = " ".join(_systemd_argument(os.fspath(item)) for item in arguments)
    content = (
        "[Unit]\n"
        f"Description=ALAS Headless KVM runtime {context.release_id}\n"
        "After=network-online.target\n"
        "Wants=network-online.target\n"
        "\n"
        "[Service]\n"
        "Type=simple\n"
        f"User={identity.name}\n"
        f"Environment=HOME={_systemd_argument(os.fspath(identity.home))}\n"
        f"Environment=ALAS_PYTHON={_systemd_argument(str(python_contract['path']))}\n"
        f"WorkingDirectory={_systemd_argument(os.fspath(context.release_root))}\n"
        f"ExecStart={command}\n"
        "KillMode=control-group\n"
        "Restart=no\n"
        f"TimeoutStopSec={timeout_stop_seconds}s\n"
        "\n"
        "[Install]\n"
        "WantedBy=multi-user.target\n"
    )
    return content.encode("utf-8")


def _systemctl_property(
    unit: str,
    property_name: str,
    *,
    runner: CommandRunner = _run_command,
    systemctl: str = "systemctl",
    allow_missing: bool = False,
) -> str:
    completed = runner(
        [systemctl, "show", f"--property={property_name}", "--value", "--", unit],
        15.0,
    )
    if completed.returncode != 0:
        if allow_missing:
            return "not-found"
        _require_success(completed, f"inspect systemd {property_name}")
    return completed.stdout.strip()


def _parse_systemd_execstart(value: str) -> list[str]:
    matches = re.findall(r"argv\[\]=([^;}]+)", value)
    if len(matches) != 1:
        raise KvmLiveCutoverError("systemd effective ExecStart is not a single argv")
    result = matches[0].strip().split()
    if not result:
        raise KvmLiveCutoverError("systemd effective ExecStart is empty")
    return result


def _parse_systemd_environment(value: str) -> Mapping[str, str]:
    """Parse the quoted/C-escaped word format emitted by systemctl show."""

    escape_values = {
        "a": "\a",
        "b": "\b",
        "f": "\f",
        "n": "\n",
        "r": "\r",
        "s": " ",
        "t": "\t",
        "v": "\v",
        "\\": "\\",
        '"': '"',
        "'": "'",
    }
    words: list[str] = []
    current: list[str] = []
    quote: str | None = None
    in_word = False
    index = 0
    while index < len(value):
        character = value[index]
        if quote is None and character.isspace():
            if in_word:
                words.append("".join(current))
                current = []
                in_word = False
            index += 1
            continue
        if character in {'"', "'"}:
            if quote is None:
                quote = character
                in_word = True
                index += 1
                continue
            if quote == character:
                quote = None
                index += 1
                continue
        if character != "\\":
            current.append(character)
            in_word = True
            index += 1
            continue
        if index + 1 >= len(value):
            raise KvmLiveCutoverError("systemd Environment has a trailing escape")
        escaped = value[index + 1]
        if escaped in escape_values:
            decoded = escape_values[escaped]
            index += 2
        elif escaped in {"x", "u", "U"}:
            digits = {"x": 2, "u": 4, "U": 8}[escaped]
            encoded = value[index + 2 : index + 2 + digits]
            if len(encoded) != digits or re.fullmatch(r"[0-9A-Fa-f]+", encoded) is None:
                raise KvmLiveCutoverError(
                    "systemd Environment contains a malformed numeric escape"
                )
            decoded = chr(int(encoded, 16))
            index += 2 + digits
        else:
            raise KvmLiveCutoverError(
                f"systemd Environment contains an unsupported escape: \\{escaped}"
            )
        if decoded == "\x00":
            raise KvmLiveCutoverError("systemd Environment contains NUL")
        current.append(decoded)
        in_word = True
    if quote is not None:
        raise KvmLiveCutoverError("systemd Environment has an unterminated quote")
    if in_word:
        words.append("".join(current))
    result: dict[str, str] = {}
    for word in words:
        if "=" not in word:
            raise KvmLiveCutoverError(
                "systemd Environment contains a malformed assignment"
            )
        name, item = word.split("=", 1)
        if not name or name in result:
            raise KvmLiveCutoverError(
                "systemd Environment contains an empty or duplicate name"
            )
        result[name] = item
    return result


def _parse_systemd_duration_seconds(value: str) -> float:
    value = value.strip()
    if value.isdigit():
        # systemd exposes *_USec as an integer on some versions.
        return int(value) / 1_000_000.0
    total = 0.0
    position = 0
    units = {
        "d": 86400.0,
        "h": 3600.0,
        "min": 60.0,
        "s": 1.0,
        "ms": 0.001,
        "us": 0.000001,
        "µs": 0.000001,
    }
    pattern = re.compile(r"\s*(\d+(?:[.]\d+)?)\s*(min|ms|us|µs|d|h|s)")
    for match in pattern.finditer(value):
        if match.start() != position and value[position : match.start()].strip():
            raise KvmLiveCutoverError("systemd TimeoutStopUSec is malformed")
        total += float(match.group(1)) * units[match.group(2)]
        position = match.end()
    if position == 0 or value[position:].strip():
        raise KvmLiveCutoverError("systemd TimeoutStopUSec is malformed")
    return total


def inspect_effective_systemd_unit(
    unit: str,
    *,
    runner: CommandRunner = _run_command,
    systemctl: str = "systemctl",
) -> Mapping[str, str]:
    _validate_unit_name(unit)
    names = (
        "LoadState",
        "ActiveState",
        "FragmentPath",
        "DropInPaths",
        "User",
        "Environment",
        "ExecStart",
        "KillMode",
        "Restart",
        "TimeoutStopUSec",
        "UnitFileState",
        "ControlGroup",
    )
    return {
        name: _systemctl_property(unit, name, runner=runner, systemctl=systemctl)
        for name in names
    }


def verify_effective_systemd_contract(
    unit: str,
    unit_path: Path,
    identity: UserIdentity,
    run_script: Path,
    alas_python: Path,
    expected_arguments: Sequence[str],
    timeout_stop_seconds: int,
    *,
    runner: CommandRunner = _run_command,
    systemctl: str = "systemctl",
    require_inactive: bool = True,
) -> Mapping[str, str]:
    effective = inspect_effective_systemd_unit(unit, runner=runner, systemctl=systemctl)
    if effective["LoadState"] != "loaded":
        raise KvmLiveCutoverError("installed systemd unit is not loaded")
    fragment = Path(effective["FragmentPath"])
    try:
        fragment_matches = os.path.samefile(fragment, unit_path)
    except OSError as exc:
        raise KvmLiveCutoverError("cannot verify systemd FragmentPath") from exc
    if not fragment_matches:
        raise KvmLiveCutoverError("systemd FragmentPath differs from installed unit")
    if effective["DropInPaths"]:
        raise KvmLiveCutoverError(
            "systemd DropInPaths must be empty for formal deployment"
        )
    if effective["User"] != identity.name:
        raise KvmLiveCutoverError("systemd effective User differs")
    expected_argv = [os.fspath(run_script.resolve(strict=True)), *expected_arguments]
    if _parse_systemd_execstart(effective["ExecStart"]) != expected_argv:
        raise KvmLiveCutoverError("systemd effective ExecStart differs")
    environment = _parse_systemd_environment(effective["Environment"])
    expected_python = os.path.abspath(os.fspath(alas_python))
    expected_home = os.fspath(identity.home)
    if environment != {"ALAS_PYTHON": expected_python, "HOME": expected_home}:
        raise KvmLiveCutoverError("systemd effective Environment differs")
    if effective["KillMode"] != "control-group":
        raise KvmLiveCutoverError("systemd effective KillMode differs")
    if effective["Restart"] != "no":
        raise KvmLiveCutoverError("systemd effective Restart differs")
    if (
        abs(
            _parse_systemd_duration_seconds(effective["TimeoutStopUSec"])
            - timeout_stop_seconds
        )
        > 0.001
    ):
        raise KvmLiveCutoverError("systemd effective TimeoutStopUSec differs")
    if effective["UnitFileState"] != "disabled":
        raise KvmLiveCutoverError(
            f"candidate systemd unit must be disabled; observed {effective['UnitFileState']}"
        )
    if require_inactive and effective["ActiveState"] != "inactive":
        raise KvmLiveCutoverError("candidate systemd unit must be inactive")
    return effective


def require_service_inactive(
    unit: str,
    *,
    runner: CommandRunner = _run_command,
    systemctl: str = "systemctl",
    allow_missing: bool = False,
) -> None:
    _validate_unit_name(unit)
    load_state = _systemctl_property(
        unit,
        "LoadState",
        runner=runner,
        systemctl=systemctl,
        allow_missing=allow_missing,
    )
    if load_state == "not-found" and allow_missing:
        return
    if load_state != "loaded":
        raise KvmLiveCutoverError(
            f"systemd unit must be loaded; observed {load_state or 'unknown'}"
        )
    active_state = _systemctl_property(
        unit, "ActiveState", runner=runner, systemctl=systemctl
    )
    if active_state != "inactive":
        raise KvmLiveCutoverError(
            f"systemd unit must already be inactive; observed {active_state or 'unknown'}"
        )


def archive_previous_systemd_unit(
    context: CutoverContext,
    previous_unit: str,
    archive_path: Path,
    *,
    runner: CommandRunner = _run_command,
    systemctl: str = "systemctl",
    created_epoch: int | None = None,
) -> Mapping[str, Any]:
    """Archive the effective old consumer before any stop/disable/mask mutation."""

    _validate_unit_name(previous_unit)
    _require_within(archive_path, context.evidence_root, "previous unit archive")
    _require_new_receipt_path(archive_path)
    effective = inspect_effective_systemd_unit(
        previous_unit, runner=runner, systemctl=systemctl
    )
    if effective["LoadState"] != "loaded" or not effective["FragmentPath"]:
        raise KvmLiveCutoverError(
            "previous systemd consumer must be loaded and inspectable"
        )
    is_enabled = runner([systemctl, "is-enabled", "--", previous_unit], 15.0)
    if is_enabled.returncode not in {0, 1}:
        _require_success(is_enabled, "inspect previous systemd enabled state")
    try:
        drop_ins = shlex.split(effective["DropInPaths"], posix=os.name == "posix")
    except ValueError as exc:
        raise KvmLiveCutoverError("previous systemd DropInPaths are malformed") from exc
    paths = [Path(effective["FragmentPath"]), *(Path(value) for value in drop_ins)]
    files: list[Mapping[str, Any]] = []
    for path in paths:
        if not path.is_absolute() or path.is_symlink() or not path.is_file():
            raise KvmLiveCutoverError(
                f"previous systemd unit file is unavailable or unsafe: {path}"
            )
        payload = path.read_bytes()
        info = path.stat()
        files.append(
            {
                "path": os.fspath(path.resolve(strict=True)),
                "mode": stat.S_IMODE(info.st_mode),
                "uid": int(getattr(info, "st_uid", -1)),
                "gid": int(getattr(info, "st_gid", -1)),
                "bytes": len(payload),
                "sha256": _sha256_bytes(payload),
                "content_base64": base64.b64encode(payload).decode("ascii"),
            }
        )
    document = {
        "schema": PREVIOUS_UNIT_ARCHIVE_SCHEMA,
        "backend": "kvm",
        "status": "archived-before-mutation",
        "created_epoch": int(time.time() if created_epoch is None else created_epoch),
        "release_candidate": context.release_id,
        "previous_unit": previous_unit,
        "effective_state": dict(effective),
        "is_enabled": {
            "returncode": is_enabled.returncode,
            "stdout": is_enabled.stdout.strip(),
            "stderr": is_enabled.stderr.strip(),
        },
        "files": files,
        "restore_policy": "dry-run-review-required-no-auto-overwrite",
    }
    return _write_json_noreplace(archive_path, document)


def stop_disable_mask_previous_unit(
    previous_unit: str,
    *,
    runner: CommandRunner = _run_command,
    systemctl: str = "systemctl",
) -> Mapping[str, Any]:
    _validate_unit_name(previous_unit)
    before_active = _systemctl_property(
        previous_unit, "ActiveState", runner=runner, systemctl=systemctl
    )
    if before_active not in {"active", "activating", "inactive", "failed"}:
        raise KvmLiveCutoverError(
            f"previous systemd consumer state is unsafe: {before_active or 'unknown'}"
        )
    if before_active != "inactive":
        _require_success(
            runner([systemctl, "stop", "--", previous_unit], 105.0),
            "stop previous KVM systemd consumer",
        )
    after_active = _systemctl_property(
        previous_unit, "ActiveState", runner=runner, systemctl=systemctl
    )
    if after_active != "inactive":
        raise KvmLiveCutoverError(
            f"previous KVM consumer remained {after_active or 'unknown'} after stop"
        )
    unit_file_state = _systemctl_property(
        previous_unit, "UnitFileState", runner=runner, systemctl=systemctl
    )
    if unit_file_state in {
        "enabled",
        "enabled-runtime",
        "linked",
        "linked-runtime",
        "alias",
    }:
        _require_success(
            runner(
                [systemctl, "disable", "--no-reload", "--", previous_unit],
                30.0,
            ),
            "disable previous KVM systemd consumer",
        )
    _require_success(
        runner([systemctl, "mask", "--runtime", "--", previous_unit], 30.0),
        "runtime-mask previous KVM systemd consumer",
    )
    _require_success(
        runner([systemctl, "daemon-reload"], 30.0), "systemd daemon-reload"
    )
    after_active = _systemctl_property(
        previous_unit, "ActiveState", runner=runner, systemctl=systemctl
    )
    if after_active != "inactive":
        raise KvmLiveCutoverError(
            f"masked previous KVM consumer remained {after_active or 'unknown'}"
        )
    after_state = _systemctl_property(
        previous_unit, "UnitFileState", runner=runner, systemctl=systemctl
    )
    if after_state not in {"masked", "masked-runtime"}:
        raise KvmLiveCutoverError(
            f"previous KVM consumer was not masked; observed {after_state or 'unknown'}"
        )
    return {
        "unit": previous_unit,
        "active_state_before": before_active,
        "unit_file_state_before": unit_file_state,
        "active_state_after": after_active,
        "unit_file_state_after": after_state,
        "mask_scope": "runtime",
    }


def _atomic_replace(path: Path, payload: bytes, mode: int) -> None:
    previous = None
    if os.path.lexists(path):
        if path.is_symlink() or not path.is_file():
            raise KvmLiveCutoverError(
                f"atomic replacement target must be a regular file: {path}"
            )
        previous = path.stat()
    temporary_descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(temporary_descriptor, "wb") as output:
            output.write(payload)
            output.flush()
            os.fsync(output.fileno())
        os.chmod(temporary, mode)
        if previous is not None and os.name == "posix":
            os.chown(temporary, previous.st_uid, previous.st_gid)
        os.replace(temporary, path)
        _fsync_directory(path.parent)
    finally:
        with contextlib.suppress(FileNotFoundError):
            temporary.unlink()


def _control_plane_manifest(run_script: Path) -> Mapping[str, Any]:
    run_script = run_script.resolve(strict=True)
    try:
        repo_root = run_script.parents[2]
    except IndexError as exc:
        raise KvmLiveCutoverError("KVM run script has no repository root") from exc
    package = repo_root / "python" / "alas_headless"
    resolver = (
        repo_root / "scripts" / "python" / "resolve_kvm_runtime_release_config.py"
    )
    manager = repo_root / "scripts" / "python" / "manage_kvm_live_cutover.py"
    wrapper = repo_root / "scripts" / "wsl" / "manage-kvm-live-cutover.sh"
    if (
        package.is_symlink()
        or not package.is_dir()
        or resolver.is_symlink()
        or not resolver.is_file()
    ):
        raise KvmLiveCutoverError("KVM control-plane Python sources are unavailable")
    files = sorted({run_script, resolver, manager, wrapper, *package.rglob("*.py")})
    entries: list[Mapping[str, Any]] = []
    for path in files:
        if path.is_symlink() or not path.is_file():
            raise KvmLiveCutoverError(f"KVM control-plane file is unavailable: {path}")
        try:
            relative = path.resolve(strict=True).relative_to(
                repo_root.resolve(strict=True)
            )
        except ValueError as exc:
            raise KvmLiveCutoverError(
                "KVM control-plane file escapes repository"
            ) from exc
        entries.append(
            {
                "path": relative.as_posix(),
                "bytes": path.stat().st_size,
                "sha256": _sha256_file(path),
            }
        )
    tree_sha256 = _sha256_bytes(
        json.dumps(entries, sort_keys=True, separators=(",", ":")).encode("utf-8")
    )
    return {
        "repo_root": os.fspath(repo_root.resolve(strict=True)),
        "tree_sha256": tree_sha256,
        "entries": entries,
    }


def _contract_hashes(
    context: CutoverContext, unit_path: Path, run_script: Path, alas_python: Path
) -> Mapping[str, str]:
    control_plane = _control_plane_manifest(run_script)
    return {
        "domain_document_sha256": context.inputs.domain_sha256,
        "domain_file_sha256": _sha256_file(context.domain_path),
        "profile_document_sha256": context.inputs.profile_sha256,
        "profile_file_sha256": _sha256_file(context.profile_path),
        "runtime_config_file_sha256": _sha256_file(context.runtime_config_path),
        "source_lock_sha256": context.inputs.source_lock_sha256,
        "release_manifest_sha256": _sha256_file(context.release_root / "manifest.json"),
        "systemd_unit_sha256": _sha256_file(unit_path),
        "run_script_sha256": _sha256_file(run_script),
        "alas_python_sha256": _sha256_file(alas_python),
        "alas_python_pyvenv_config_sha256": _sha256_file(
            alas_python.parent.parent / "pyvenv.cfg"
        ),
        "control_plane_tree_sha256": str(control_plane["tree_sha256"]),
    }


def _expected_unit_arguments(context: CutoverContext) -> list[str]:
    return [
        os.fspath(context.domain_path.resolve(strict=True)),
        os.fspath(context.profile_path.resolve(strict=True)),
        context.release_id,
        os.fspath(context.runtime_config_path.resolve(strict=True)),
    ]


def install_systemd_unit(
    context: CutoverContext,
    unit: str,
    identity: UserIdentity,
    run_script: Path,
    alas_python: Path,
    unit_directory: Path,
    receipt_path: Path,
    *,
    timeout_stop_seconds: int = DEFAULT_STOP_TIMEOUT_SECONDS,
    runner: CommandRunner = _run_command,
    systemctl: str = "systemctl",
    created_epoch: int | None = None,
    cutover_lock_path: Path | None = None,
    phase_marker_path: Path | None = None,
) -> Mapping[str, Any]:
    with exclusive_cutover_lock(cutover_lock_path):
        return _install_systemd_unit_locked(
            context,
            unit,
            identity,
            run_script,
            alas_python,
            unit_directory,
            receipt_path,
            timeout_stop_seconds=timeout_stop_seconds,
            runner=runner,
            systemctl=systemctl,
            created_epoch=created_epoch,
            phase_marker_path=phase_marker_path,
        )


def _install_systemd_unit_locked(
    context: CutoverContext,
    unit: str,
    identity: UserIdentity,
    run_script: Path,
    alas_python: Path,
    unit_directory: Path,
    receipt_path: Path,
    *,
    timeout_stop_seconds: int,
    runner: CommandRunner,
    systemctl: str,
    created_epoch: int | None,
    phase_marker_path: Path | None,
) -> Mapping[str, Any]:
    _validate_unit_name(unit)
    _require_within(receipt_path, context.evidence_root, "unit receipt")
    _require_new_receipt_path(receipt_path)
    if phase_marker_path is not None:
        _require_within(
            phase_marker_path, context.evidence_root, "cutover phase marker"
        )
        if os.path.lexists(phase_marker_path):
            raise KvmLiveCutoverError(
                "cutover phase marker already exists; review the existing deployment"
            )
    if not unit_directory.is_absolute() or unit_directory.is_symlink():
        raise KvmLiveCutoverError(
            "systemd unit directory must be an absolute real directory"
        )
    if not unit_directory.is_dir():
        raise KvmLiveCutoverError(
            f"systemd unit directory is unavailable: {unit_directory}"
        )
    content = render_systemd_unit(
        context,
        unit,
        identity,
        run_script,
        alas_python,
        timeout_stop_seconds=timeout_stop_seconds,
    )
    python_contract = _validate_alas_python(
        alas_python, identity, context.inputs.runtime_root
    )
    alas_python = Path(str(python_contract["path"]))
    unit_path = unit_directory / unit
    if unit_path.is_symlink():
        raise KvmLiveCutoverError("systemd unit file must not be a symlink")
    changed = True
    previous_payload: bytes | None = None
    previous_mode: int | None = None
    previous_enabled = False
    receipt_created = False
    if unit_path.is_file():
        current = unit_path.read_bytes()
        previous_payload = current
        previous_mode = stat.S_IMODE(unit_path.stat().st_mode)
        if current == content:
            changed = False
        else:
            require_service_inactive(unit, runner=runner, systemctl=systemctl)
        previous_enabled = _systemctl_property(
            unit, "UnitFileState", runner=runner, systemctl=systemctl
        ) in {"enabled", "enabled-runtime"}
    else:
        require_service_inactive(
            unit, runner=runner, systemctl=systemctl, allow_missing=True
        )
    try:
        if changed:
            _atomic_replace(unit_path, content, 0o644)
        _require_success(
            runner([systemctl, "daemon-reload"], 30.0), "systemd daemon-reload"
        )
        effective_state = inspect_effective_systemd_unit(
            unit, runner=runner, systemctl=systemctl
        )
        if effective_state["UnitFileState"] in {"enabled", "enabled-runtime"}:
            _require_success(
                runner([systemctl, "disable", "--no-reload", "--", unit], 30.0),
                "disable candidate KVM systemd unit",
            )
            _require_success(
                runner([systemctl, "daemon-reload"], 30.0),
                "systemd daemon-reload after disable",
            )
        effective_state = verify_effective_systemd_contract(
            unit,
            unit_path,
            identity,
            run_script,
            alas_python,
            _expected_unit_arguments(context),
            timeout_stop_seconds,
            runner=runner,
            systemctl=systemctl,
        )
        receipt = {
            "schema": UNIT_RECEIPT_SCHEMA,
            "backend": "kvm",
            "status": "installed-inactive",
            "created_epoch": int(
                time.time() if created_epoch is None else created_epoch
            ),
            "release_id": context.release_id,
            "release_root": os.fspath(context.release_root),
            "unit": unit,
            "unit_path": os.fspath(unit_path.resolve(strict=True)),
            "run_as_user": identity.name,
            "run_as_uid": identity.uid,
            "run_as_gid": identity.uid if identity.gid is None else identity.gid,
            "user_home": os.fspath(identity.home),
            "run_script": os.fspath(run_script.resolve(strict=True)),
            "alas_python": dict(python_contract),
            "timeout_stop_seconds": timeout_stop_seconds,
            "kill_mode": "control-group",
            "restart": "no",
            "enabled": False,
            "changed": changed,
            "effective_systemd": dict(effective_state),
            "control_plane": _control_plane_manifest(run_script),
            "contracts": dict(
                _contract_hashes(context, unit_path, run_script, alas_python)
            ),
        }
        written = _write_json_noreplace(receipt_path, receipt)
        receipt_created = True
        _update_phase_marker(
            phase_marker_path,
            context,
            unit,
            "unit-installed",
            expected_phases={None},
            evidence={"unit_receipt_sha256": written["self_sha256"]},
            created_epoch=created_epoch,
        )
        return written
    except BaseException:
        if receipt_created:
            with contextlib.suppress(FileNotFoundError):
                receipt_path.unlink()
        if changed:
            if previous_payload is None:
                with contextlib.suppress(FileNotFoundError):
                    unit_path.unlink()
            else:
                _atomic_replace(unit_path, previous_payload, previous_mode or 0o644)
            with contextlib.suppress(Exception):
                runner([systemctl, "daemon-reload"], 30.0)
        if previous_enabled:
            with contextlib.suppress(Exception):
                runner([systemctl, "enable", "--no-reload", "--", unit], 30.0)
                runner([systemctl, "daemon-reload"], 30.0)
        raise


def verify_unit_receipt(
    context: CutoverContext,
    unit: str,
    receipt_path: Path,
) -> Mapping[str, Any]:
    _require_within(receipt_path, context.evidence_root, "unit receipt")
    receipt = load_receipt(receipt_path, UNIT_RECEIPT_SCHEMA)
    if (
        receipt.get("backend") != "kvm"
        or receipt.get("status") != "installed-inactive"
        or receipt.get("release_id") != context.release_id
        or receipt.get("release_root") != os.fspath(context.release_root)
        or receipt.get("unit") != unit
        or receipt.get("kill_mode") != "control-group"
        or receipt.get("restart") != "no"
        or receipt.get("enabled") is not False
    ):
        raise KvmLiveCutoverError("systemd unit receipt differs from this deployment")
    unit_path = Path(str(receipt.get("unit_path", "")))
    run_script = Path(str(receipt.get("run_script", "")))
    python_contract = receipt.get("alas_python")
    if not isinstance(python_contract, Mapping):
        raise KvmLiveCutoverError("installed ALAS Python contract is missing")
    alas_python = Path(str(python_contract.get("path", "")))
    if unit_path.is_symlink() or not unit_path.is_file():
        raise KvmLiveCutoverError("installed systemd unit is unavailable")
    if run_script.is_symlink() or not run_script.is_file():
        raise KvmLiveCutoverError("installed KVM run script is unavailable")
    identity = UserIdentity(
        str(receipt.get("run_as_user", "")),
        int(receipt.get("run_as_uid", -1)),
        Path(str(receipt.get("user_home", ""))),
        int(receipt.get("run_as_gid", receipt.get("run_as_uid", -1))),
    )
    _validate_user_identity(identity)
    if python_contract != _validate_alas_python(
        alas_python, identity, context.inputs.runtime_root
    ):
        raise KvmLiveCutoverError("installed ALAS Python contract differs")
    if receipt.get("control_plane") != _control_plane_manifest(run_script):
        raise KvmLiveCutoverError("installed KVM control-plane sources differ")
    if receipt.get("contracts") != _contract_hashes(
        context, unit_path, run_script, alas_python
    ):
        raise KvmLiveCutoverError("installed systemd unit contracts differ")
    return receipt


def verify_unit_receipt_and_effective_state(
    context: CutoverContext,
    unit: str,
    receipt_path: Path,
    *,
    runner: CommandRunner = _run_command,
    systemctl: str = "systemctl",
    require_inactive: bool = True,
) -> tuple[Mapping[str, Any], Mapping[str, str]]:
    receipt = verify_unit_receipt(context, unit, receipt_path)
    identity = UserIdentity(
        str(receipt["run_as_user"]),
        int(receipt["run_as_uid"]),
        Path(str(receipt["user_home"])),
        int(receipt.get("run_as_gid", receipt["run_as_uid"])),
    )
    effective = verify_effective_systemd_contract(
        unit,
        Path(str(receipt["unit_path"])),
        identity,
        Path(str(receipt["run_script"])),
        Path(str(receipt["alas_python"]["path"])),
        _expected_unit_arguments(context),
        int(receipt["timeout_stop_seconds"]),
        runner=runner,
        systemctl=systemctl,
        require_inactive=require_inactive,
    )
    return receipt, effective


def _socket_lines_for_ports(output: str, ports: Iterable[int]) -> list[str]:
    selected = {str(port) for port in ports}
    matches: list[str] = []
    for line in output.splitlines():
        tokens = line.split()
        if any(
            token.rstrip(",").rsplit(":", 1)[-1] in selected
            for token in tokens
            if ":" in token
        ):
            matches.append(line)
    return matches


def require_ports_free(
    ports: Sequence[int],
    *,
    runner: CommandRunner = _run_command,
    ss_command: str = "ss",
) -> None:
    completed = _require_success(
        runner([ss_command, "-H", "-ltnp"], 15.0), "inspect TCP listeners"
    )
    matches = _socket_lines_for_ports(completed.stdout, ports)
    if matches:
        raise KvmLiveCutoverError(
            "KVM console/transport ports are still in use: " + " | ".join(matches)
        )


def _proc_stat_identity(value: str, pid: int) -> tuple[str, int]:
    """Return the stable start time and flags from one ``/proc/PID/stat`` read."""

    try:
        fields = value.rsplit(")", 1)[1].split()
        flags = int(fields[6])
        start_time = fields[19]
    except (IndexError, ValueError) as exc:
        raise KvmLiveCutoverError(f"process {pid} stat identity is malformed") from exc
    if flags < 0:
        raise KvmLiveCutoverError(f"process {pid} stat flags are malformed")
    return start_time, flags


def require_no_orphan_avd_users(
    context: CutoverContext,
    *,
    proc_root: Path = Path("/proc"),
    readlink: Callable[[Path], str] = os.readlink,
) -> None:
    """Reject any process outside systemd that still holds the live AVD.

    This intentionally scans exact filesystem dependencies instead of using a
    global process-name match.  A stopped or crashed emulator can release its
    ports while a QEMU child still owns userdata through an inherited fd.
    """

    avd = context.avd_directory.resolve(strict=True)
    descriptor = context.avd_descriptor.resolve(strict=True)
    current_pid = os.getpid()
    for process in sorted(proc_root.iterdir(), key=lambda item: item.name):
        if not process.name.isdigit() or int(process.name) == current_pid:
            continue
        pid = int(process.name)
        vanished = False
        for attempt in range(3):
            dependencies: list[str] = []
            churn = False
            try:
                stat_before = (process / "stat").read_text(encoding="ascii")
            except FileNotFoundError:
                if not process.exists():
                    vanished = True
                    break
                churn = True
                stat_before = ""
            except (PermissionError, OSError, UnicodeDecodeError) as exc:
                raise KvmLiveCutoverError(
                    f"cannot prove process {pid} is detached from the AVD"
                ) from exc
            if stat_before:
                start_before, flags_before = _proc_stat_identity(stat_before, pid)
                is_kernel_thread = bool(flags_before & PF_KTHREAD)
            else:
                start_before = ""
                flags_before = -1
                is_kernel_thread = False
            for name in ("exe", "cwd", "root"):
                try:
                    dependencies.append(readlink(process / name))
                except FileNotFoundError:
                    # A stable PF_KTHREAD process has no executable symlink by
                    # kernel design.  This narrow exception does not skip the
                    # cwd/root/fd/maps dependency checks below.
                    if name != "exe" or not is_kernel_thread:
                        churn = True
                except (PermissionError, ProcessLookupError, OSError) as exc:
                    raise KvmLiveCutoverError(
                        f"cannot prove process {pid} is detached from the AVD"
                    ) from exc
            try:
                fd_entries = sorted((process / "fd").iterdir())
            except FileNotFoundError:
                fd_entries = []
                churn = True
            except (PermissionError, OSError) as exc:
                raise KvmLiveCutoverError(
                    f"cannot prove process {pid} is detached from the AVD"
                ) from exc
            for path in fd_entries:
                try:
                    dependencies.append(readlink(path))
                except FileNotFoundError:
                    churn = True
                except (PermissionError, ProcessLookupError, OSError) as exc:
                    raise KvmLiveCutoverError(
                        f"cannot prove process {pid} is detached from the AVD"
                    ) from exc
            try:
                maps = (process / "maps").read_text(
                    encoding="utf-8", errors="surrogateescape"
                )
            except FileNotFoundError:
                maps = ""
                churn = True
            except (PermissionError, OSError) as exc:
                raise KvmLiveCutoverError(
                    f"cannot prove process {pid} is detached from the AVD"
                ) from exc
            dependencies.extend(
                token
                for token in re.findall(r"/[^\x00\s]+", maps)
                if token.startswith("/")
            )
            for value in dependencies:
                cleaned = value.removesuffix(" (deleted)")
                candidate = Path(cleaned).resolve(strict=False)
                if candidate == descriptor:
                    raise KvmLiveCutoverError(
                        f"orphan process {pid} still holds the AVD descriptor"
                    )
                try:
                    candidate.relative_to(avd)
                except ValueError:
                    continue
                raise KvmLiveCutoverError(
                    f"orphan process {pid} still holds the AVD: {candidate}"
                )
            try:
                stat_after = (process / "stat").read_text(encoding="ascii")
            except FileNotFoundError:
                if not process.exists():
                    vanished = True
                    break
                churn = True
                stat_after = ""
            except (PermissionError, OSError, UnicodeDecodeError) as exc:
                raise KvmLiveCutoverError(
                    f"cannot prove process {pid} is detached from the AVD"
                ) from exc
            if stat_before and stat_after:
                start_after, flags_after = _proc_stat_identity(stat_after, pid)
                if start_before != start_after or flags_before != flags_after:
                    churn = True
            if not churn:
                break
            if attempt == 2:
                raise KvmLiveCutoverError(
                    f"cannot prove process {pid} is detached from the AVD after bounded /proc retries"
                )
        if vanished:
            continue


def require_inactive_cgroup_empty(
    unit: str,
    *,
    runner: CommandRunner = _run_command,
    systemctl: str = "systemctl",
    cgroup_root: Path = Path("/sys/fs/cgroup"),
) -> None:
    cgroup = _systemctl_property(
        unit, "ControlGroup", runner=runner, systemctl=systemctl
    )
    if not cgroup:
        return
    if not cgroup.startswith("/") or ".." in Path(cgroup).parts:
        raise KvmLiveCutoverError("inactive systemd ControlGroup is malformed")
    root = cgroup_root.resolve(strict=True)
    candidate = (root / cgroup.lstrip("/")).resolve(strict=False)
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise KvmLiveCutoverError(
            "inactive systemd ControlGroup escapes cgroup root"
        ) from exc
    if not candidate.exists():
        return
    pids: set[int] = set()
    for path in candidate.rglob("cgroup.procs"):
        try:
            pids.update(
                int(line)
                for line in path.read_text(encoding="ascii").splitlines()
                if line.strip()
            )
        except (OSError, UnicodeDecodeError, ValueError) as exc:
            raise KvmLiveCutoverError(
                f"cannot prove inactive cgroup is empty: {path}"
            ) from exc
    if pids:
        raise KvmLiveCutoverError(
            f"inactive KVM systemd cgroup still contains processes: {sorted(pids)}"
        )


def _forbidden_dependency_roots(context: CutoverContext) -> tuple[Path, ...]:
    return (
        context.inputs.source_root.resolve(strict=False),
        context.inputs.output_root.resolve(strict=False),
        Path("/srv/android-build/src").resolve(strict=False),
        Path("/srv/android-cache/out").resolve(strict=False),
    )


def _dependency_path_candidates(
    value: str, *, relative_to: Path | None = None
) -> list[Path]:
    candidates: list[Path] = []
    for token in re.findall(r"/[^\x00\s\]\[(){}\"']+", value):
        candidates.append(Path(token.rstrip(":,;")))
    for token in re.findall(r"[A-Za-z]:[\\/][^\x00\s\]\[(){}\"']+", value):
        candidates.append(Path(token.rstrip(":,;")))
    if relative_to is not None and value and not value.startswith("/"):
        if any(
            separator in value for separator in ("/", "\\")
        ) or value.lower().endswith((".img", ".qcow2")):
            candidates.append((relative_to / value).resolve(strict=False))
    return candidates


def _dependency_violation(
    value: str,
    context: CutoverContext,
    *,
    relative_to: Path | None = None,
    allowed_runtime_release_roots: Sequence[Path] = (),
) -> str | None:
    lowered = value.lower()
    if "redroid" in lowered:
        return "redroid"
    candidates = _dependency_path_candidates(value, relative_to=relative_to)
    for candidate in candidates:
        normalized = candidate.resolve(strict=False)
        for root in _forbidden_dependency_roots(context):
            try:
                normalized.relative_to(root)
            except ValueError:
                continue
            return os.fspath(root)
        releases_root = (context.inputs.runtime_root / "releases").resolve(strict=False)
        try:
            normalized.relative_to(releases_root)
        except ValueError:
            pass
        else:
            try:
                normalized.relative_to(context.release_root.resolve(strict=False))
            except ValueError:
                if not any(
                    _path_is_within(normalized, root.resolve(strict=False))
                    for root in allowed_runtime_release_roots
                ):
                    return f"non-candidate KVM runtime release under {releases_root}"
    return None


def _path_is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _walk_json_strings(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, Mapping):
        for item in value.values():
            yield from _walk_json_strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _walk_json_strings(item)


def verify_avd_descriptor_binding(context: CutoverContext) -> Mapping[str, str | None]:
    """Bind the AVD name used by ``emulator -avd`` to the audited directory."""

    descriptor = context.avd_descriptor
    if descriptor.is_symlink() or not descriptor.is_file():
        raise KvmLiveCutoverError(f"AVD descriptor is unavailable: {descriptor}")
    try:
        lines = descriptor.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as exc:
        raise KvmLiveCutoverError(
            f"AVD descriptor is unreadable: {descriptor}"
        ) from exc
    values: dict[str, list[str]] = {"path": [], "path.rel": []}
    for line in lines:
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key in values:
            values[key].append(value)
    if len(values["path"]) != 1:
        raise KvmLiveCutoverError("AVD descriptor must contain exactly one path=")
    raw_path = values["path"][0]
    descriptor_path = Path(raw_path)
    if not raw_path or not descriptor_path.is_absolute():
        raise KvmLiveCutoverError("AVD descriptor path= must be an absolute local path")
    try:
        observed = descriptor_path.resolve(strict=True)
        expected = context.avd_directory.resolve(strict=True)
    except OSError as exc:
        raise KvmLiveCutoverError("AVD descriptor path= target is unavailable") from exc
    if observed != expected:
        raise KvmLiveCutoverError(
            f"AVD descriptor path= selects another directory: {observed}"
        )
    if len(values["path.rel"]) > 1:
        raise KvmLiveCutoverError("AVD descriptor contains duplicate path.rel=")
    relative_value: str | None = None
    if values["path.rel"]:
        relative_value = values["path.rel"][0]
        relative = Path(relative_value)
        if not relative_value or relative.is_absolute() or ".." in relative.parts:
            raise KvmLiveCutoverError("AVD descriptor path.rel= is unsafe")
        relative_target = (context.runtime_config.avd_home.parent / relative).resolve(
            strict=False
        )
        if relative_target != expected:
            raise KvmLiveCutoverError(
                f"AVD descriptor path.rel= selects another directory: {relative_target}"
            )
    return {
        "descriptor": os.fspath(descriptor.resolve(strict=True)),
        "path": os.fspath(observed),
        "path_rel": relative_value,
    }


def validate_pre_switch_image_sysdir(context: CutoverContext, value: str) -> Path:
    """Allow only the exact legacy KVM image root being snapshotted and replaced."""

    if not value or "redroid" in value.lower():
        raise KvmLiveCutoverError(
            "pre-switch image.sysdir is empty or references Redroid"
        )
    raw = Path(value.rstrip("/\\"))
    if not raw.is_absolute():
        raise KvmLiveCutoverError("pre-switch image.sysdir must be absolute")
    try:
        resolved = raw.resolve(strict=True)
    except OSError as exc:
        raise KvmLiveCutoverError("pre-switch image.sysdir is unavailable") from exc
    if not resolved.is_dir():
        raise KvmLiveCutoverError("pre-switch image.sysdir must be a directory")
    build_output = context.inputs.output_root.resolve(strict=False)
    releases = (context.inputs.runtime_root / "releases").resolve(strict=False)
    try:
        resolved.relative_to(build_output)
        return resolved
    except ValueError:
        pass
    try:
        relative = resolved.relative_to(releases)
    except ValueError as exc:
        raise KvmLiveCutoverError(
            "pre-switch image.sysdir is outside KVM build output/runtime releases"
        ) from exc
    if len(relative.parts) != 2 or relative.parts[1] != "images":
        raise KvmLiveCutoverError(
            "pre-switch runtime image.sysdir must be one immutable release images root"
        )
    return resolved


def inspect_avd_external_storage_paths(
    context: CutoverContext,
    *,
    previous_image_root: Path | None = None,
) -> list[Mapping[str, str]]:
    """Prove that persistent writable files are contained by the AVD snapshot."""

    verify_avd_descriptor_binding(context)

    allowed_roots = (
        context.avd_directory.resolve(strict=True),
        context.release_root.resolve(strict=True),
    )
    records: list[Mapping[str, str]] = []
    candidates = [context.avd_config]
    hardware = context.avd_directory / "hardware-qemu.ini"
    if hardware.is_file() and not hardware.is_symlink():
        candidates.append(hardware)
    for config in candidates:
        try:
            lines = config.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError) as exc:
            raise KvmLiveCutoverError(f"AVD config is unreadable: {config}") from exc
        for line in lines:
            if "=" not in line:
                continue
            key, raw_value = line.split("=", 1)
            key = key.strip()
            value = raw_value.strip().rstrip("/\\")
            path_like = (
                "path" in key.lower()
                or value.lower().endswith((".img", ".qcow2"))
                or any(separator in value for separator in ("/", "\\"))
            )
            if not path_like:
                continue
            raw_path = Path(value)
            path = (
                raw_path.resolve(strict=False)
                if raw_path.is_absolute()
                else (config.parent / raw_path).resolve(strict=False)
            )
            allowed = False
            lowered_key = key.lower()
            mutable = (
                "path" in lowered_key
                and not lowered_key.endswith("initpath")
                and any(
                    token in lowered_key
                    for token in ("data", "cache", "sdcard", "userdata")
                )
            )
            if config == hardware and lowered_key == "android.avd.home":
                # This is metadata, not an arbitrary storage-root allowance.
                # The derived file is removed after the whole-AVD snapshot,
                # but it must still identify this exact configured AVD home.
                allowed = path == context.runtime_config.avd_home.resolve(strict=True)
            else:
                roots = (allowed_roots[0],) if mutable else allowed_roots
                if (
                    config == hardware
                    and previous_image_root is not None
                    and not mutable
                ):
                    # hardware-qemu.ini is an emulator-derived file.  Before
                    # it is removed, its immutable tools (for example
                    # android.sdk.root) may belong to the same exact previous
                    # release as its image root.  Writable media remain
                    # confined to the live AVD through the mutable branch.
                    previous_release_root = previous_image_root.resolve(
                        strict=True
                    ).parent
                    roots = (*roots, previous_release_root)
                for root in roots:
                    try:
                        path.relative_to(root)
                    except ValueError:
                        continue
                    allowed = True
                    break
            if key == "image.sysdir.1":
                # The old live config can legitimately be the hot image being
                # published.  Its qcow backing chain is checked separately and
                # the switch removes this active dependency before first boot.
                allowed = False
                if "redroid" not in os.fspath(path).lower():
                    for root in (
                        context.inputs.output_root.resolve(strict=False),
                        (context.inputs.runtime_root / "releases").resolve(
                            strict=False
                        ),
                    ):
                        try:
                            path.relative_to(root)
                        except ValueError:
                            continue
                        allowed = True
                        break
            if not allowed:
                raise KvmLiveCutoverError(
                    f"AVD snapshot excludes external writable path {key}={path}"
                )
            records.append(
                {"config": os.fspath(config), "key": key, "path": os.fspath(path)}
            )
    return records


def inspect_qcow_backing_chains(
    context: CutoverContext,
    *,
    previous_image_root: Path | None = None,
    runner: CommandRunner = _run_command,
    timeout_seconds: float = 30.0,
) -> list[Mapping[str, Any]]:
    qemu_img = context.release_root / "emulator" / "qemu-img"
    if qemu_img.is_symlink() or not qemu_img.is_file():
        raise KvmLiveCutoverError(
            "verified runtime release does not contain emulator/qemu-img"
        )
    if os.name == "posix" and not os.access(qemu_img, os.X_OK):
        raise KvmLiveCutoverError("verified runtime qemu-img is not executable")
    avd = context.avd_directory
    userdata = avd / "userdata-qemu.img"
    if userdata.is_symlink() or not userdata.is_file():
        raise KvmLiveCutoverError("existing AVD userdata-qemu.img is unavailable")
    images = sorted(
        path
        for path in avd.rglob("*")
        if path.is_file()
        and not path.is_symlink()
        and path.suffix.lower() in {".img", ".qcow2"}
    )
    if userdata not in images:
        raise KvmLiveCutoverError(
            "existing AVD userdata was not included in chain audit"
        )
    records: list[Mapping[str, Any]] = []
    for image in images:
        completed = _require_success(
            runner(
                [
                    os.fspath(qemu_img),
                    "info",
                    "--backing-chain",
                    "--output=json",
                    os.fspath(image),
                ],
                timeout_seconds,
            ),
            f"inspect qcow backing chain for {image.name}",
        )
        try:
            document = json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            raise KvmLiveCutoverError(
                f"qemu-img returned malformed JSON for {image}"
            ) from exc
        _validate_qcow_chain_document(
            context,
            image,
            document,
            previous_image_root=previous_image_root,
        )
        records.append(
            {
                "image": os.fspath(image.resolve(strict=True)),
                "image_bytes": image.stat().st_size,
                "qemu_img": document,
            }
        )
    return records


_PATH_PROTOCOL = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")


def _resolve_qcow_local_path(
    context: CutoverContext,
    value: Any,
    *,
    field: str,
    relative_to: Path | None = None,
    previous_image_root: Path | None = None,
) -> Path:
    if not isinstance(value, str) or not value or "\x00" in value:
        raise KvmLiveCutoverError(f"qemu-img {field} must be a non-empty local path")
    violation = _dependency_violation(
        value,
        context,
        relative_to=relative_to,
        allowed_runtime_release_roots=()
        if previous_image_root is None
        else (previous_image_root,),
    )
    if violation is not None:
        raise KvmLiveCutoverError(
            f"AVD image backing chain references forbidden dependency {violation}"
        )
    windows_drive = os.name == "nt" and re.match(r"^[A-Za-z]:[\\/]", value)
    if (_PATH_PROTOCOL.match(value) and windows_drive is None) or value.startswith(
        ("\\\\", "//")
    ):
        raise KvmLiveCutoverError(
            f"qemu-img {field} uses a forbidden path protocol or network path: {value}"
        )
    raw = Path(value)
    if raw.is_absolute():
        candidate = raw
    elif relative_to is not None:
        candidate = relative_to / raw
    else:
        raise KvmLiveCutoverError(f"qemu-img {field} must be an absolute local path")
    try:
        canonical = candidate.resolve(strict=True)
    except OSError as exc:
        raise KvmLiveCutoverError(
            f"qemu-img {field} target is unavailable: {candidate}"
        ) from exc
    if not canonical.is_file():
        raise KvmLiveCutoverError(
            f"qemu-img {field} target is not a regular local file: {canonical}"
        )
    allowed = False
    for root in (
        context.avd_directory.resolve(strict=True),
        context.release_root.resolve(strict=True),
        *(
            ()
            if previous_image_root is None
            else (previous_image_root.resolve(strict=True),)
        ),
    ):
        try:
            canonical.relative_to(root)
        except ValueError:
            continue
        allowed = True
        break
    if not allowed:
        raise KvmLiveCutoverError(
            f"AVD image chain escapes the live AVD/candidate release roots: {canonical}"
        )
    return canonical


def _validate_qcow_chain_document(
    context: CutoverContext,
    image: Path,
    document: Any,
    *,
    previous_image_root: Path | None = None,
) -> None:
    if not isinstance(document, list) or not document:
        raise KvmLiveCutoverError(
            f"qemu-img backing chain must be a non-empty ImageInfo array: {image}"
        )
    filenames: list[Path] = []
    for index, item in enumerate(document):
        if not isinstance(item, Mapping):
            raise KvmLiveCutoverError(
                f"qemu-img backing chain layer {index} is not an ImageInfo object"
            )
        image_format = item.get("format")
        if not isinstance(image_format, str) or not image_format:
            raise KvmLiveCutoverError(
                f"qemu-img backing chain layer {index} has no format"
            )
        filenames.append(
            _resolve_qcow_local_path(
                context,
                item.get("filename"),
                field=f"layer {index} filename",
                previous_image_root=previous_image_root,
            )
        )
    expected_image = image.resolve(strict=True)
    if filenames[0] != expected_image:
        raise KvmLiveCutoverError(
            f"qemu-img backing chain describes another image: {filenames[0]}"
        )
    for index, item in enumerate(document):
        raw_backing = item.get("backing-filename")
        raw_full_backing = item.get("full-backing-filename")
        has_backing = raw_backing is not None or raw_full_backing is not None
        if index == len(document) - 1:
            if has_backing:
                raise KvmLiveCutoverError(
                    "qemu-img backing chain is truncated after its final layer"
                )
            continue
        if not has_backing:
            raise KvmLiveCutoverError(
                f"qemu-img backing chain layer {index} does not link to layer {index + 1}"
            )
        expected_next = filenames[index + 1]
        if raw_backing is not None:
            backing = _resolve_qcow_local_path(
                context,
                raw_backing,
                field=f"layer {index} backing-filename",
                relative_to=filenames[index].parent,
                previous_image_root=previous_image_root,
            )
            if backing != expected_next:
                raise KvmLiveCutoverError(
                    f"qemu-img relative backing chain differs at layer {index}"
                )
        if raw_full_backing is not None:
            full_backing = _resolve_qcow_local_path(
                context,
                raw_full_backing,
                field=f"layer {index} full-backing-filename",
                previous_image_root=previous_image_root,
            )
            if full_backing != expected_next:
                raise KvmLiveCutoverError(
                    f"qemu-img full backing chain differs at layer {index}"
                )


def _copy_with_rsync(
    source: Path,
    target: Path,
    *,
    runner: CommandRunner,
    timeout_seconds: float,
) -> None:
    target.mkdir(parents=True, exist_ok=False)
    completed = runner(
        [
            "rsync",
            "-aHAX",
            "--sparse",
            "--numeric-ids",
            "--",
            os.fspath(source) + os.sep,
            os.fspath(target) + os.sep,
        ],
        timeout_seconds,
    )
    _require_success(completed, "copy complete offline AVD snapshot")


def _ownership_snapshot(root: Path) -> list[Mapping[str, Any]]:
    entries: list[Mapping[str, Any]] = []
    candidates = [root]
    if root.is_dir() and not root.is_symlink():
        candidates.extend(sorted(root.rglob("*")))
    for path in candidates:
        info = path.lstat()
        relative = "." if path == root else path.relative_to(root).as_posix()
        kind = (
            "symlink"
            if stat.S_ISLNK(info.st_mode)
            else "directory"
            if stat.S_ISDIR(info.st_mode)
            else "file"
            if stat.S_ISREG(info.st_mode)
            else "other"
        )
        entries.append(
            {
                "path": relative,
                "kind": kind,
                "mode": stat.S_IMODE(info.st_mode),
                "uid": info.st_uid,
                "gid": info.st_gid,
            }
        )
    return entries


def _copy_file_preserving_metadata(source: Path, target: Path) -> None:
    source_info = source.stat(follow_symlinks=False)
    shutil.copy2(source, target, follow_symlinks=False)
    if os.name == "posix":
        os.chown(target, source_info.st_uid, source_info.st_gid)
    target_info = target.stat(follow_symlinks=False)
    if (
        stat.S_IMODE(target_info.st_mode) != stat.S_IMODE(source_info.st_mode)
        or target_info.st_uid != source_info.st_uid
        or target_info.st_gid != source_info.st_gid
    ):
        raise KvmLiveCutoverError(
            f"copied recovery file ownership or mode differs: {source}"
        )
    if os.name == "posix":
        descriptor = os.open(target, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)


def _rename_directory_noreplace(source: Path, target: Path) -> None:
    if os.path.lexists(target):
        raise KvmLiveCutoverError(f"snapshot destination already exists: {target}")
    if sys.platform == "linux":
        libc = ctypes.CDLL(None, use_errno=True)
        renameat2 = getattr(libc, "renameat2", None)
        if renameat2 is None:
            raise KvmLiveCutoverError(
                "renameat2 is required for atomic no-overwrite snapshot publication"
            )
        renameat2.argtypes = [
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_uint,
        ]
        renameat2.restype = ctypes.c_int
        result = renameat2(-100, os.fsencode(source), -100, os.fsencode(target), 1)
        if result != 0:
            error = ctypes.get_errno()
            if error == errno.EEXIST:
                raise KvmLiveCutoverError(
                    f"snapshot destination already exists: {target}"
                )
            raise KvmLiveCutoverError(
                f"atomic snapshot publication failed: {os.strerror(error)}"
            )
        return
    try:
        os.rename(source, target)
    except FileExistsError as exc:
        raise KvmLiveCutoverError(
            f"snapshot destination already exists: {target}"
        ) from exc


def plan_avd_runtime_ownership_changes(
    context: CutoverContext,
    identity: UserIdentity,
) -> list[Mapping[str, Any]]:
    """Plan only root-level mutable AVD files needed by the non-root emulator."""

    avd = context.avd_directory.resolve(strict=True)
    avd_info = avd.stat()
    target_gid = identity.uid if identity.gid is None else identity.gid
    if (
        avd_info.st_uid != identity.uid
        or stat.S_IMODE(avd_info.st_mode) & 0o700 != 0o700
    ):
        raise KvmLiveCutoverError(
            "live AVD directory must already be owned and writable by the candidate service user"
        )
    records: list[Mapping[str, Any]] = []
    for path in sorted(avd.iterdir()):
        if not path.name.endswith((".ini", ".lock", ".img", ".qcow2")):
            continue
        if path.is_symlink() or not path.is_file():
            raise KvmLiveCutoverError(
                f"mutable AVD runtime entry must be a regular file: {path}"
            )
        info = path.stat()
        mode = stat.S_IMODE(info.st_mode)
        if mode & 0o600 != 0o600:
            raise KvmLiveCutoverError(
                f"mutable AVD runtime file lacks owner read/write bits: {path}"
            )
        records.append(
            {
                "path": os.fspath(path),
                "sha256": _sha256_file(path),
                "before_uid": info.st_uid,
                "before_gid": info.st_gid,
                "mode": mode,
                "target_uid": identity.uid,
                "target_gid": target_gid,
                "change_required": info.st_uid != identity.uid
                or info.st_gid != target_gid,
            }
        )
    return records


def remove_snapshotted_derived_hardware(
    context: CutoverContext,
    snapshot: Mapping[str, Any],
    previous_image_root: Path,
) -> Mapping[str, Any]:
    """Remove only emulator-derived hardware state so the candidate rebuilds it."""

    manifest = Path(str(snapshot.get("manifest", "")))
    expected_manifest_sha = snapshot.get("manifest_sha256")
    if (
        manifest.is_symlink()
        or not manifest.is_file()
        or not isinstance(expected_manifest_sha, str)
        or _sha256_file(manifest) != expected_manifest_sha
    ):
        raise KvmLiveCutoverError(
            "durable whole-AVD snapshot is unavailable before hardware reset"
        )
    dependency_records = inspect_avd_external_storage_paths(
        context, previous_image_root=previous_image_root
    )
    hardware = context.avd_directory / "hardware-qemu.ini"
    lock = context.avd_directory / "hardware-qemu.ini.lock"
    entries: list[Mapping[str, Any]] = []
    removed: list[str] = []
    for path in (hardware, lock):
        if not os.path.lexists(path):
            entries.append({"path": os.fspath(path), "status": "absent"})
            continue
        if path.is_symlink() or not path.is_file():
            raise KvmLiveCutoverError(
                f"derived AVD hardware entry must be a regular file: {path}"
            )
        info = path.stat()
        entries.append(
            {
                "path": os.fspath(path),
                "status": "removed-after-snapshot",
                "sha256": _sha256_file(path),
                "bytes": info.st_size,
                "mode": stat.S_IMODE(info.st_mode),
                "uid": info.st_uid,
                "gid": info.st_gid,
            }
        )
        path.unlink()
        removed.append(os.fspath(path))
    _fsync_directory(context.avd_directory)
    return {
        "policy": "remove-exact-emulator-derived-hardware-after-whole-avd-snapshot",
        "snapshot_manifest_sha256": expected_manifest_sha,
        "previous_image_root": os.fspath(previous_image_root),
        "dependency_records": dependency_records,
        "entries": entries,
        "removed_paths": removed,
        "recursive_delete_performed": False,
        "rollback": "restore the verified whole-AVD snapshot while all consumers are stopped",
    }


def normalize_avd_runtime_ownership(
    context: CutoverContext,
    identity: UserIdentity,
    snapshot: Mapping[str, Any],
) -> Mapping[str, Any]:
    """Narrowly chown snapshotted mutable AVD files before first non-root boot."""

    _validate_user_identity(identity)
    verify_offline_avd_snapshot(context, snapshot)
    planned = plan_avd_runtime_ownership_changes(context, identity)
    changed: list[str] = []
    if any(bool(item["change_required"]) for item in planned) and os.name != "posix":
        raise KvmLiveCutoverError("AVD ownership migration requires a POSIX host")
    for item in planned:
        path = Path(str(item["path"]))
        if item["change_required"]:
            os.chown(path, int(item["target_uid"]), int(item["target_gid"]))
            changed.append(os.fspath(path))
        observed = path.stat()
        if (
            observed.st_uid != int(item["target_uid"])
            or observed.st_gid != int(item["target_gid"])
            or stat.S_IMODE(observed.st_mode) != int(item["mode"])
            or _sha256_file(path) != item["sha256"]
        ):
            raise KvmLiveCutoverError(
                f"AVD runtime ownership migration changed content/mode or did not take effect: {path}"
            )
        if os.name == "posix":
            descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
    _fsync_directory(context.avd_directory)
    return {
        "policy": "root-level-mutable-files-only-after-whole-avd-snapshot",
        "snapshot_manifest_sha256": snapshot["manifest_sha256"],
        "target_user": identity.name,
        "target_uid": identity.uid,
        "target_gid": identity.uid if identity.gid is None else identity.gid,
        "planned": planned,
        "changed_paths": changed,
        "recursive_chown_performed": False,
        "mode_changes_performed": False,
        "rollback": "restore the verified whole-AVD snapshot while all consumers are stopped",
    }


def create_offline_avd_snapshot(
    context: CutoverContext,
    snapshot_path: Path,
    qcow_chains: Sequence[Mapping[str, Any]],
    unit_receipt: Mapping[str, Any],
    previous_unit_archive_path: Path | None = None,
    *,
    runner: CommandRunner = _run_command,
    copy_timeout_seconds: float = 7200.0,
    created_epoch: int | None = None,
) -> Mapping[str, Any]:
    descriptor_binding = verify_avd_descriptor_binding(context)
    snapshot_path = _require_within(snapshot_path, context.archive_root, "AVD snapshot")
    if os.path.lexists(snapshot_path):
        raise KvmLiveCutoverError(
            f"snapshot destination already exists: {snapshot_path}"
        )
    avd = context.avd_directory
    descriptor = context.avd_descriptor
    if avd.is_symlink() or not avd.is_dir():
        raise KvmLiveCutoverError(f"existing AVD directory is unavailable: {avd}")
    if descriptor.is_symlink() or not descriptor.is_file():
        raise KvmLiveCutoverError(
            f"existing AVD descriptor is unavailable: {descriptor}"
        )
    snapshot_parent_existed = snapshot_path.parent.is_dir()
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    if snapshot_path.parent.is_symlink():
        raise KvmLiveCutoverError("AVD snapshot parent must not be a symlink")
    stage = Path(
        tempfile.mkdtemp(
            prefix=f".{snapshot_path.name}.staging.", dir=snapshot_path.parent
        )
    )
    try:
        source_before = snapshot_component(avd)
        descriptor_before = snapshot_component(descriptor)
        source_ownership_before = _ownership_snapshot(avd)
        descriptor_ownership_before = _ownership_snapshot(descriptor)
        copied_avd = stage / avd.name
        _copy_with_rsync(
            avd,
            copied_avd,
            runner=runner,
            timeout_seconds=copy_timeout_seconds,
        )
        _copy_file_preserving_metadata(descriptor, stage / descriptor.name)
        contracts = stage / "deployment-contracts"
        contracts.mkdir(mode=0o700)
        contract_snapshots: dict[str, str] = {}
        contract_sources = [
            ("android-build-domain.json", context.domain_path),
            ("kvm-image-build-profile.json", context.profile_path),
            ("runtime-config.json", context.runtime_config_path),
            ("systemd-unit.service", Path(str(unit_receipt["unit_path"]))),
            ("run-kvm-avd.sh", Path(str(unit_receipt["run_script"]))),
            (
                "alas-python-canonical",
                Path(str(unit_receipt["alas_python"]["canonical_path"])),
            ),
            (
                "alas-python-pyvenv.cfg",
                Path(str(unit_receipt["alas_python"]["pyvenv_config"])),
            ),
            ("release-manifest.json", context.release_root / "manifest.json"),
        ]
        if previous_unit_archive_path is not None:
            contract_sources.append(
                ("previous-systemd-unit-archive.json", previous_unit_archive_path)
            )
        for name, source in contract_sources:
            before_sha256 = _sha256_file(source)
            _copy_file_preserving_metadata(source, contracts / name)
            after_sha256 = _sha256_file(source)
            target_sha256 = _sha256_file(contracts / name)
            if before_sha256 != after_sha256 or before_sha256 != target_sha256:
                raise KvmLiveCutoverError(
                    f"deployment contract changed or copied content differs: {name}"
                )
            contract_snapshots[name] = target_sha256
        python_contract_path = contracts / "alas-python-contract.json"
        python_contract_path.write_text(
            json.dumps(unit_receipt["alas_python"], indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        contract_snapshots[python_contract_path.name] = _sha256_file(
            python_contract_path
        )
        control_manifest = contracts / "control-plane-manifest.json"
        control_manifest.write_text(
            json.dumps(unit_receipt["control_plane"], indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        contract_snapshots[control_manifest.name] = _sha256_file(control_manifest)
        control_files = contracts / "control-plane-files"
        control_files.mkdir(mode=0o700)
        control_root = Path(str(unit_receipt["control_plane"]["repo_root"]))
        for entry in unit_receipt["control_plane"]["entries"]:
            relative = Path(str(entry["path"]))
            if relative.is_absolute() or ".." in relative.parts:
                raise KvmLiveCutoverError("control-plane manifest path is unsafe")
            source = control_root / relative
            if source.is_symlink() or not source.is_file():
                raise KvmLiveCutoverError(
                    f"control-plane source changed before snapshot: {relative.as_posix()}"
                )
            target = control_files / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            _copy_file_preserving_metadata(source, target)
            if _sha256_file(target) != entry["sha256"]:
                raise KvmLiveCutoverError(
                    f"copied control-plane source differs: {relative.as_posix()}"
                )
        contract_snapshots["control-plane-files-tree-sha256"] = str(
            unit_receipt["control_plane"]["tree_sha256"]
        )
        source_after = snapshot_component(avd)
        descriptor_after = snapshot_component(descriptor)
        target_snapshot = snapshot_component(copied_avd)
        target_descriptor = snapshot_component(stage / descriptor.name)
        source_ownership_after = _ownership_snapshot(avd)
        descriptor_ownership_after = _ownership_snapshot(descriptor)
        target_ownership = _ownership_snapshot(copied_avd)
        target_descriptor_ownership = _ownership_snapshot(stage / descriptor.name)
        if source_before != source_after or source_before != target_snapshot:
            raise KvmLiveCutoverError(
                "AVD changed or copied content differs during snapshot"
            )
        if (
            descriptor_before != descriptor_after
            or descriptor_before != target_descriptor
        ):
            raise KvmLiveCutoverError(
                "AVD descriptor changed or copied content differs"
            )
        if (
            source_ownership_before != source_ownership_after
            or source_ownership_before != target_ownership
        ):
            raise KvmLiveCutoverError(
                "AVD ownership/mode changed or was not preserved in the snapshot"
            )
        if (
            descriptor_ownership_before != descriptor_ownership_after
            or descriptor_ownership_before != target_descriptor_ownership
        ):
            raise KvmLiveCutoverError(
                "AVD descriptor ownership/mode was not preserved in the snapshot"
            )
        snapshot_manifest = {
            "schema": SNAPSHOT_SCHEMA,
            "backend": "kvm",
            "created_epoch": int(
                time.time() if created_epoch is None else created_epoch
            ),
            "release_candidate": context.release_id,
            "source_avd": os.fspath(avd.resolve(strict=True)),
            "source_descriptor": os.fspath(descriptor.resolve(strict=True)),
            "descriptor_binding": dict(descriptor_binding),
            "cutover_intent": {
                "state": "snapshot-complete-before-switch",
                "unit": str(unit_receipt.get("unit", "unknown")),
                "previous_image_sysdir": _read_single_image_sysdir(context.avd_config),
                "candidate_image_sysdir": os.fspath(context.release_root / "images")
                + os.sep,
                "automatic_userdata_rollback_allowed": False,
            },
            "avd_snapshot": source_before,
            "descriptor_snapshot": descriptor_before,
            "avd_ownership": source_ownership_before,
            "descriptor_ownership": descriptor_ownership_before,
            "qcow_backing_chains": list(qcow_chains),
            "deployment_contracts": contract_snapshots,
            "restore_policy": "offline-whole-avd-only",
        }
        manifest_document = _with_self_sha256(snapshot_manifest)
        manifest_path = stage / "snapshot-manifest.json"
        manifest_path.write_text(
            json.dumps(manifest_document, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        with manifest_path.open("r+b") as source:
            os.fsync(source.fileno())
        _fsync_tree(stage)
        # rsync 3.1.x has no --fsync option.  Durability is provided by the
        # explicit recursive file + bottom-up directory fsync above.  Persist
        # the staging directory entry itself before the atomic rename, then
        # persist the final name below.
        _fsync_directory(stage.parent)
        _rename_directory_noreplace(stage, snapshot_path)
        _fsync_directory(snapshot_path.parent)
        if not snapshot_parent_existed:
            _fsync_directory(snapshot_path.parent.parent)
        return {
            "path": os.fspath(snapshot_path),
            "manifest": os.fspath(snapshot_path / "snapshot-manifest.json"),
            "manifest_sha256": _sha256_file(snapshot_path / "snapshot-manifest.json"),
            "avd_tree_sha256": str(source_before["tree_sha256"]),
            "descriptor_tree_sha256": str(descriptor_before["tree_sha256"]),
        }
    finally:
        if os.path.lexists(stage):
            shutil.rmtree(stage)


def _read_single_image_sysdir(config: Path) -> str:
    try:
        lines = config.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as exc:
        raise KvmLiveCutoverError(f"AVD config is unavailable: {config}") from exc
    values = [
        line.split("=", 1)[1] for line in lines if line.startswith("image.sysdir.1=")
    ]
    if len(values) != 1:
        raise KvmLiveCutoverError("AVD config must contain exactly one image.sysdir.1")
    return values[0]


def _recovery_instructions(
    context: CutoverContext,
    unit: str,
    snapshot: Mapping[str, Any],
    *,
    previous_unit: str | None = None,
) -> list[str]:
    instructions = [
        "Stop every ALAS consumer before stopping the KVM unit.",
        f"Stop {unit}; require ActiveState=inactive and require ports 5588/5589 free.",
        "Do not run an automatic image-only rollback after the candidate has booted; userdata may have migrated.",
        f"Restore the entire offline snapshot {snapshot['path']} to {context.avd_directory} with a reviewed host-specific atomic restore while the unit remains stopped.",
        "Restore the previous deployment contracts and systemd unit; do not reuse the candidate runtime config with an older image.",
        "Re-run qcow backing-chain, dedicated ADB, active-config, and whole-cgroup dependency verification before resuming ALAS.",
    ]
    if previous_unit is not None:
        instructions.insert(
            4,
            f"Review the archived {previous_unit} fragment/drop-ins, then unmask it only after the whole AVD restore is complete.",
        )
    return instructions


def write_recovery_plan(
    context: CutoverContext,
    unit: str,
    previous_unit: str,
    prepare_receipt_path: Path,
    output_path: Path,
    *,
    phase_marker_path: Path,
    activation_receipt_path: Path | None = None,
    created_epoch: int | None = None,
) -> Mapping[str, Any]:
    """Write a read-only restore plan; never overwrite the live AVD or a unit."""

    _validate_unit_name(unit)
    _validate_unit_name(previous_unit)
    _require_within(output_path, context.evidence_root, "recovery plan")
    _require_new_receipt_path(output_path)
    _require_within(prepare_receipt_path, context.evidence_root, "prepare receipt")
    prepare = load_receipt(prepare_receipt_path, PREPARE_RECEIPT_SCHEMA)
    if (
        prepare.get("release_id") != context.release_id
        or prepare.get("unit") != unit
        or prepare.get("previous_unit") != previous_unit
    ):
        raise KvmLiveCutoverError("prepare receipt differs from recovery plan")
    _require_within(phase_marker_path, context.evidence_root, "cutover phase marker")
    phase_marker = _load_phase_marker(phase_marker_path)
    if (
        phase_marker.get("backend") != "kvm"
        or phase_marker.get("release_id") != context.release_id
        or phase_marker.get("release_root") != os.fspath(context.release_root)
        or phase_marker.get("unit") != unit
        or phase_marker.get("previous_unit") != previous_unit
    ):
        raise KvmLiveCutoverError("cutover phase marker differs from recovery plan")
    phase = phase_marker.get("phase")
    if phase not in {
        "prepared",
        "activating",
        "boot-attempted",
        "active-verified",
        "activation-failed-recovery-required",
    }:
        raise KvmLiveCutoverError(
            f"cutover phase {phase!r} cannot authorize a post-prepare recovery plan"
        )
    history = phase_marker.get("history")
    if not isinstance(history, list) or not history:
        raise KvmLiveCutoverError("cutover phase marker history is malformed")
    history_phases: list[str] = []
    for event in history:
        if not isinstance(event, Mapping) or not isinstance(event.get("phase"), str):
            raise KvmLiveCutoverError("cutover phase marker history is malformed")
        history_phases.append(str(event["phase"]))
    marker_boot_attempted = any(
        item in {"boot-attempted", "active-verified"} for item in history_phases
    )
    verify_offline_avd_snapshot(context, prepare.get("snapshot"))
    archive_ref = prepare.get("previous_unit_archive")
    if not isinstance(archive_ref, Mapping):
        raise KvmLiveCutoverError("prepare receipt has no previous unit archive")
    archive_path = Path(str(archive_ref.get("path", "")))
    _require_within(archive_path, context.evidence_root, "previous unit archive")
    archive = load_receipt(archive_path, PREVIOUS_UNIT_ARCHIVE_SCHEMA)
    if (
        archive.get("self_sha256") != archive_ref.get("self_sha256")
        or archive.get("previous_unit") != previous_unit
    ):
        raise KvmLiveCutoverError("previous systemd unit archive differs")
    file_checks: list[Mapping[str, Any]] = []
    for entry in archive.get("files", []):
        if not isinstance(entry, Mapping):
            raise KvmLiveCutoverError("previous unit archive file entry is malformed")
        path = Path(str(entry.get("path", "")))
        current_sha = (
            _sha256_file(path) if path.is_file() and not path.is_symlink() else None
        )
        file_checks.append(
            {
                "path": os.fspath(path),
                "archived_sha256": entry.get("sha256"),
                "current_sha256": current_sha,
                "current_matches_archive": current_sha == entry.get("sha256"),
                "automatic_overwrite_allowed": False,
            }
        )
    activation: Mapping[str, Any] | None = None
    if activation_receipt_path is not None:
        _require_within(
            activation_receipt_path, context.evidence_root, "activation receipt"
        )
        activation = load_receipt(activation_receipt_path, ACTIVATION_RECEIPT_SCHEMA)
        if (
            activation.get("release_id") != context.release_id
            or activation.get("unit") != unit
            or activation.get("prepare_receipt_sha256") != prepare.get("self_sha256")
        ):
            raise KvmLiveCutoverError("activation receipt differs from recovery plan")
    boot_attempted = marker_boot_attempted or (
        activation is not None and bool(activation.get("boot_attempted"))
    )
    plan = {
        "schema": RECOVERY_PLAN_SCHEMA,
        "backend": "kvm",
        "status": "dry-run-only-review-required",
        "created_epoch": int(time.time() if created_epoch is None else created_epoch),
        "release_id": context.release_id,
        "unit": unit,
        "previous_unit": previous_unit,
        "boot_attempted": boot_attempted,
        "phase_marker": {
            "path": os.fspath(phase_marker_path),
            "phase": phase,
            "self_sha256": phase_marker["self_sha256"],
            "boot_attempted_in_history": marker_boot_attempted,
        },
        "snapshot": prepare["snapshot"],
        "previous_unit_archive": archive_ref,
        "previous_unit_file_checks": file_checks,
        "automatic_restore_performed": False,
        "automatic_overwrite_allowed": False,
        "ordered_review_steps": [
            f"systemctl stop -- {unit}",
            "prove candidate ActiveState=inactive, its recursive cgroup empty, and ports 5588/5589 free",
            "compare each current previous-unit file against archived content; do not overwrite automatically",
            f"offline whole-directory restore from {prepare['snapshot']['path']} to {context.avd_directory} plus {context.avd_descriptor}",
            f"systemctl unmask --runtime -- {previous_unit}",
            "restore reviewed previous fragment/drop-ins and prior enabled state, then daemon-reload",
            "re-run qcow, active config, 5043 listener, QEMU executable and whole-cgroup proofs before ALAS resumes",
        ],
    }
    return _write_json_noreplace(output_path, plan)


def verify_previous_unit_archive_reference(
    context: CutoverContext,
    previous_unit: str,
    value: Any,
) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise KvmLiveCutoverError("previous unit archive reference is missing")
    path = Path(str(value.get("path", "")))
    _require_within(path, context.evidence_root, "previous unit archive")
    archive = load_receipt(path, PREVIOUS_UNIT_ARCHIVE_SCHEMA)
    if (
        archive.get("backend") != "kvm"
        or archive.get("previous_unit") != previous_unit
        or archive.get("self_sha256") != value.get("self_sha256")
        or archive.get("restore_policy") != "dry-run-review-required-no-auto-overwrite"
    ):
        raise KvmLiveCutoverError("previous systemd unit archive reference differs")
    return archive


def verify_offline_avd_snapshot(
    context: CutoverContext, snapshot: Any
) -> Mapping[str, Any]:
    if not isinstance(snapshot, Mapping):
        raise KvmLiveCutoverError("prepare receipt snapshot is malformed")
    snapshot_root = _require_within(
        Path(str(snapshot.get("path", ""))), context.archive_root, "AVD snapshot"
    )
    manifest_path = snapshot_root / "snapshot-manifest.json"
    if (
        snapshot_root.is_symlink()
        or not snapshot_root.is_dir()
        or manifest_path.is_symlink()
        or not manifest_path.is_file()
    ):
        raise KvmLiveCutoverError("prepared offline AVD snapshot is unavailable")
    expected_manifest_sha = snapshot.get("manifest_sha256")
    if (
        not isinstance(expected_manifest_sha, str)
        or SHA256.fullmatch(expected_manifest_sha) is None
        or _sha256_file(manifest_path) != expected_manifest_sha
    ):
        raise KvmLiveCutoverError("prepared offline AVD snapshot manifest differs")
    try:
        manifest_value = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise KvmLiveCutoverError("prepared snapshot manifest is malformed") from exc
    manifest = _validate_receipt(manifest_value, SNAPSHOT_SCHEMA)
    if (
        manifest.get("backend") != "kvm"
        or manifest.get("release_candidate") != context.release_id
        or manifest.get("restore_policy") != "offline-whole-avd-only"
    ):
        raise KvmLiveCutoverError("prepared snapshot identity differs")
    copied_avd = snapshot_root / context.avd_directory.name
    copied_descriptor = snapshot_root / context.avd_descriptor.name
    if snapshot_component(copied_avd) != manifest.get("avd_snapshot"):
        raise KvmLiveCutoverError("prepared AVD snapshot content differs")
    if snapshot_component(copied_descriptor) != manifest.get("descriptor_snapshot"):
        raise KvmLiveCutoverError("prepared AVD descriptor snapshot differs")
    if _ownership_snapshot(copied_avd) != manifest.get("avd_ownership"):
        raise KvmLiveCutoverError("prepared AVD snapshot ownership/mode differs")
    if _ownership_snapshot(copied_descriptor) != manifest.get("descriptor_ownership"):
        raise KvmLiveCutoverError("prepared AVD descriptor ownership/mode differs")
    descriptor_binding = manifest.get("descriptor_binding")
    if not isinstance(descriptor_binding, Mapping) or descriptor_binding.get(
        "path"
    ) != os.fspath(context.avd_directory.resolve(strict=True)):
        raise KvmLiveCutoverError("prepared AVD descriptor binding differs")
    contracts = snapshot_root / "deployment-contracts"
    recorded_contracts = manifest.get("deployment_contracts")
    if (
        contracts.is_symlink()
        or not contracts.is_dir()
        or not isinstance(recorded_contracts, Mapping)
    ):
        raise KvmLiveCutoverError("prepared deployment contracts are unavailable")
    for name, expected_sha256 in recorded_contracts.items():
        if name == "control-plane-files-tree-sha256":
            continue
        contract = contracts / str(name)
        if contract.is_symlink() or not contract.is_file():
            raise KvmLiveCutoverError(
                f"prepared deployment contract is unavailable: {name}"
            )
        if _sha256_file(contract) != expected_sha256:
            raise KvmLiveCutoverError(f"prepared deployment contract differs: {name}")
    control_manifest_path = contracts / "control-plane-manifest.json"
    try:
        control_manifest = json.loads(control_manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise KvmLiveCutoverError(
            "prepared control-plane manifest is malformed"
        ) from exc
    if (
        not isinstance(control_manifest, Mapping)
        or control_manifest.get("tree_sha256")
        != recorded_contracts.get("control-plane-files-tree-sha256")
        or not isinstance(control_manifest.get("entries"), list)
    ):
        raise KvmLiveCutoverError("prepared control-plane manifest differs")
    control_files = contracts / "control-plane-files"
    for entry in control_manifest["entries"]:
        if not isinstance(entry, Mapping):
            raise KvmLiveCutoverError("prepared control-plane entry is malformed")
        relative = Path(str(entry.get("path", "")))
        if not relative.parts or relative.is_absolute() or ".." in relative.parts:
            raise KvmLiveCutoverError("prepared control-plane entry path is unsafe")
        target = control_files / relative
        if target.is_symlink() or not target.is_file():
            raise KvmLiveCutoverError(
                f"prepared control-plane file is unavailable: {relative.as_posix()}"
            )
        if _sha256_file(target) != entry.get("sha256"):
            raise KvmLiveCutoverError(
                f"prepared control-plane file differs: {relative.as_posix()}"
            )
    return manifest


def prepare_live_cutover(
    context: CutoverContext,
    unit: str,
    unit_receipt_path: Path,
    snapshot_path: Path,
    receipt_path: Path,
    *,
    previous_unit: str | None = None,
    previous_unit_archive_path: Path | None = None,
    runner: CommandRunner = _run_command,
    systemctl: str = "systemctl",
    ss_command: str = "ss",
    runuser: str = "runuser",
    cgroup_root: Path = Path("/sys/fs/cgroup"),
    proc_root: Path = Path("/proc"),
    readlink: Callable[[Path], str] = os.readlink,
    copy_timeout_seconds: float = 7200.0,
    created_epoch: int | None = None,
    cutover_lock_path: Path | None = None,
    phase_marker_path: Path | None = None,
) -> Mapping[str, Any]:
    with exclusive_cutover_lock(cutover_lock_path):
        try:
            return _prepare_live_cutover_locked(
                context,
                unit,
                unit_receipt_path,
                snapshot_path,
                receipt_path,
                previous_unit=previous_unit,
                previous_unit_archive_path=previous_unit_archive_path,
                runner=runner,
                systemctl=systemctl,
                ss_command=ss_command,
                runuser=runuser,
                cgroup_root=cgroup_root,
                proc_root=proc_root,
                readlink=readlink,
                copy_timeout_seconds=copy_timeout_seconds,
                created_epoch=created_epoch,
                phase_marker_path=phase_marker_path,
            )
        except BaseException as exc:
            if phase_marker_path is not None and phase_marker_path.is_file():
                with contextlib.suppress(Exception):
                    current_marker = _load_phase_marker(phase_marker_path)
                    phase = str(current_marker["phase"])
                    if phase in {
                        "previous-unit-archived",
                        "previous-unit-stopped",
                        "snapshot-complete",
                        "derived-hardware-removed",
                        "ownership-normalized",
                        "switching",
                        "prepared",
                        "prepare-failed-recovery-required",
                    }:
                        archive_evidence: Mapping[str, Any] | None = None
                        for event in current_marker.get("history", []):
                            if not isinstance(event, Mapping):
                                continue
                            evidence = event.get("evidence")
                            if isinstance(evidence, Mapping) and evidence.get(
                                "previous_unit_archive"
                            ):
                                archive_evidence = evidence
                        snapshot_reference: Mapping[str, Any] | None = None
                        snapshot_manifest = snapshot_path / "snapshot-manifest.json"
                        if (
                            snapshot_manifest.is_file()
                            and not snapshot_manifest.is_symlink()
                        ):
                            snapshot_reference = {
                                "path": os.fspath(snapshot_path),
                                "manifest": os.fspath(snapshot_manifest),
                                "manifest_sha256": _sha256_file(snapshot_manifest),
                            }
                        failure_receipt = {
                            "schema": PREPARE_RECEIPT_SCHEMA,
                            "backend": "kvm",
                            "status": "prepare-failed-recovery-required",
                            "created_epoch": int(
                                time.time() if created_epoch is None else created_epoch
                            ),
                            "release_id": context.release_id,
                            "release_root": os.fspath(context.release_root),
                            "unit": unit,
                            "previous_unit": previous_unit,
                            "failed_from_phase": phase,
                            "failure_type": type(exc).__name__,
                            "failure": str(exc),
                            "snapshot": snapshot_reference,
                            "previous_unit_archive": (
                                None
                                if archive_evidence is None
                                else {
                                    "path": archive_evidence.get(
                                        "previous_unit_archive"
                                    ),
                                    "self_sha256": archive_evidence.get(
                                        "previous_unit_archive_sha256"
                                    ),
                                }
                            ),
                            "first_boot_performed": False,
                            "boot_attempted": False,
                            "automatic_userdata_rollback_allowed": False,
                            "recovery_instructions": [
                                f"Do not start {unit}.",
                                "Inspect the cutover phase marker and immutable previous-unit archive.",
                                "If the previous unit was stopped or masked, review its archived fragment/drop-ins and prior enabled state before unmasking.",
                                "Do not overwrite the live AVD automatically; use only a complete verified whole-AVD snapshot.",
                            ],
                        }
                        predicted = _with_self_sha256(failure_receipt)
                        _update_phase_marker(
                            phase_marker_path,
                            context,
                            unit,
                            "prepare-failed-recovery-required",
                            expected_phases={phase},
                            previous_unit=previous_unit,
                            evidence={
                                "failed_from_phase": phase,
                                "prepare_failure_receipt_sha256": predicted[
                                    "self_sha256"
                                ],
                            },
                            created_epoch=created_epoch,
                        )
                        if not os.path.lexists(receipt_path):
                            _write_json_noreplace(receipt_path, failure_receipt)
            raise


def _prepare_live_cutover_locked(
    context: CutoverContext,
    unit: str,
    unit_receipt_path: Path,
    snapshot_path: Path,
    receipt_path: Path,
    *,
    previous_unit: str | None,
    previous_unit_archive_path: Path | None,
    runner: CommandRunner,
    systemctl: str,
    ss_command: str,
    runuser: str,
    cgroup_root: Path,
    proc_root: Path,
    readlink: Callable[[Path], str],
    copy_timeout_seconds: float,
    created_epoch: int | None,
    phase_marker_path: Path | None,
) -> Mapping[str, Any]:
    _validate_unit_name(unit)
    _require_within(receipt_path, context.evidence_root, "prepare receipt")
    _require_new_receipt_path(receipt_path)
    if previous_unit is not None:
        _validate_unit_name(previous_unit)
        if previous_unit == unit:
            raise KvmLiveCutoverError(
                "previous unit must be explicit and distinct from the candidate unit"
            )
        if previous_unit_archive_path is None:
            raise KvmLiveCutoverError("previous unit archive path is required")
    unit_receipt, effective_systemd = verify_unit_receipt_and_effective_state(
        context,
        unit,
        unit_receipt_path,
        runner=runner,
        systemctl=systemctl,
    )
    candidate_identity = UserIdentity(
        name=str(unit_receipt["run_as_user"]),
        uid=int(unit_receipt["run_as_uid"]),
        home=Path(str(unit_receipt["user_home"])),
        gid=int(unit_receipt.get("run_as_gid", unit_receipt["run_as_uid"])),
    )
    _validate_user_identity(candidate_identity)
    if phase_marker_path is not None:
        _require_phase_marker(
            phase_marker_path,
            context,
            unit,
            "unit-installed",
            evidence={"unit_receipt_sha256": unit_receipt["self_sha256"]},
        )
    previous_archive: Mapping[str, Any] | None = None
    previous_transition: Mapping[str, Any] | None = None
    previous_adb_observed: Mapping[str, Any] | None = None
    previous_adb_cleanup: Mapping[str, Any] | None = None
    if previous_unit is not None and previous_unit_archive_path is not None:
        previous_archive = archive_previous_systemd_unit(
            context,
            previous_unit,
            previous_unit_archive_path,
            runner=runner,
            systemctl=systemctl,
            created_epoch=created_epoch,
        )
        _update_phase_marker(
            phase_marker_path,
            context,
            unit,
            "previous-unit-archived",
            expected_phases={"unit-installed"},
            previous_unit=previous_unit,
            evidence={
                "previous_unit_archive": os.fspath(previous_unit_archive_path),
                "previous_unit_archive_sha256": previous_archive["self_sha256"],
            },
            created_epoch=created_epoch,
        )
        previous_adb_observed, previous_identity = inspect_previous_unit_adb_listener(
            context,
            previous_archive,
            runner=runner,
            ss_command=ss_command,
            proc_root=proc_root,
            readlink=readlink,
        )
        previous_transition = stop_disable_mask_previous_unit(
            previous_unit, runner=runner, systemctl=systemctl
        )
        previous_adb_cleanup = cleanup_previous_unit_adb_listener(
            context,
            previous_adb_observed,
            previous_identity,
            runner=runner,
            ss_command=ss_command,
            runuser=runuser,
            proc_root=proc_root,
            readlink=readlink,
        )
        _update_phase_marker(
            phase_marker_path,
            context,
            unit,
            "previous-unit-stopped",
            expected_phases={"previous-unit-archived"},
            previous_unit=previous_unit,
            evidence={
                "previous_unit_archive_sha256": previous_archive["self_sha256"],
                "previous_adb_cleanup_status": previous_adb_cleanup["status"],
            },
            created_epoch=created_epoch,
        )
    require_service_inactive(unit, runner=runner, systemctl=systemctl)
    require_ports_free(
        (context.runtime_config.console_port, context.runtime_config.console_port + 1),
        runner=runner,
        ss_command=ss_command,
    )
    require_inactive_cgroup_empty(
        unit,
        runner=runner,
        systemctl=systemctl,
        cgroup_root=cgroup_root,
    )
    if previous_unit is not None:
        require_inactive_cgroup_empty(
            previous_unit,
            runner=runner,
            systemctl=systemctl,
            cgroup_root=cgroup_root,
        )
    require_no_orphan_avd_users(context, proc_root=proc_root, readlink=readlink)
    previous_sysdir = _read_single_image_sysdir(context.avd_config)
    previous_image_root = validate_pre_switch_image_sysdir(context, previous_sysdir)
    external_paths = inspect_avd_external_storage_paths(
        context, previous_image_root=previous_image_root
    )
    original_config = context.avd_config.read_bytes()
    original_config_mode = stat.S_IMODE(context.avd_config.stat().st_mode)
    original_config_sha256 = _sha256_bytes(original_config)
    qcow_chains = inspect_qcow_backing_chains(
        context,
        previous_image_root=previous_image_root,
        runner=runner,
    )
    snapshot = create_offline_avd_snapshot(
        context,
        snapshot_path,
        qcow_chains,
        unit_receipt,
        previous_unit_archive_path,
        runner=runner,
        copy_timeout_seconds=copy_timeout_seconds,
        created_epoch=created_epoch,
    )
    _update_phase_marker(
        phase_marker_path,
        context,
        unit,
        "snapshot-complete",
        expected_phases={
            "previous-unit-stopped" if previous_unit is not None else "unit-installed"
        },
        previous_unit=previous_unit,
        evidence={
            "snapshot_path": snapshot["path"],
            "snapshot_manifest_sha256": snapshot["manifest_sha256"],
        },
        created_epoch=created_epoch,
    )
    derived_hardware_transition = remove_snapshotted_derived_hardware(
        context,
        snapshot,
        previous_image_root,
    )
    _update_phase_marker(
        phase_marker_path,
        context,
        unit,
        "derived-hardware-removed",
        expected_phases={"snapshot-complete"},
        previous_unit=previous_unit,
        evidence={
            "snapshot_path": snapshot["path"],
            "snapshot_manifest_sha256": snapshot["manifest_sha256"],
            "removed_paths": derived_hardware_transition["removed_paths"],
        },
        created_epoch=created_epoch,
    )
    ownership_transition = normalize_avd_runtime_ownership(
        context,
        candidate_identity,
        snapshot,
    )
    _update_phase_marker(
        phase_marker_path,
        context,
        unit,
        "ownership-normalized",
        expected_phases={"derived-hardware-removed"},
        previous_unit=previous_unit,
        evidence={
            "snapshot_path": snapshot["path"],
            "snapshot_manifest_sha256": snapshot["manifest_sha256"],
            "changed_path_count": len(ownership_transition["changed_paths"]),
        },
        created_epoch=created_epoch,
    )
    switched = False
    try:
        _update_phase_marker(
            phase_marker_path,
            context,
            unit,
            "switching",
            expected_phases={"ownership-normalized"},
            previous_unit=previous_unit,
            evidence={
                "snapshot_path": snapshot["path"],
                "snapshot_manifest_sha256": snapshot["manifest_sha256"],
            },
            created_epoch=created_epoch,
        )
        switch_result = switch_avd_runtime_release(
            context.inputs,
            context.release_id,
            context.runtime_config.avd_home,
            context.runtime_config.avd_name,
            unit,
            require_service_inactive=lambda selected: require_service_inactive(
                selected, runner=runner, systemctl=systemctl
            ),
            action="switch",
        )
        switched = bool(switch_result["changed"])
        backend = backend_from_config(
            dict(context.runtime_document),
            RuntimeCommandExecutor(),
            release_verifier=lambda selected: (
                context.release_root
                if selected.resolve(strict=False) == context.release_root
                else (_ for _ in ()).throw(
                    KvmLiveCutoverError("runtime config release changed during prepare")
                )
            ),
        )
        if not isinstance(backend, KvmBackend):
            raise KvmLiveCutoverError("runtime backend changed during prepare")
        backend._require_release_avd()
        post_switch_live = {
            "avd": snapshot_component(context.avd_directory),
            "descriptor": snapshot_component(context.avd_descriptor),
            "avd_ownership": _ownership_snapshot(context.avd_directory),
            "descriptor_ownership": _ownership_snapshot(context.avd_descriptor),
        }
        receipt = {
            "schema": PREPARE_RECEIPT_SCHEMA,
            "backend": "kvm",
            "status": "prepared-offline",
            "created_epoch": int(
                time.time() if created_epoch is None else created_epoch
            ),
            "release_id": context.release_id,
            "release_root": os.fspath(context.release_root),
            "unit": unit,
            "previous_unit": previous_unit,
            "unit_receipt_sha256": str(unit_receipt["self_sha256"]),
            "effective_systemd": dict(effective_systemd),
            "runtime_config": os.fspath(context.runtime_config_path),
            "avd_directory": os.fspath(context.avd_directory),
            "previous_image_sysdir": previous_sysdir,
            "candidate_image_sysdir": _read_single_image_sysdir(context.avd_config),
            "avd_config_before_sha256": original_config_sha256,
            "avd_config_after_sha256": _sha256_file(context.avd_config),
            "switch": dict(switch_result),
            "post_switch_live": post_switch_live,
            "snapshot": dict(snapshot),
            "previous_unit_archive": (
                None
                if previous_archive is None
                else {
                    "path": os.fspath(previous_unit_archive_path),
                    "self_sha256": previous_archive["self_sha256"],
                    "effective_state": previous_archive["effective_state"],
                }
            ),
            "previous_unit_transition": previous_transition,
            "previous_adb_listener_before_stop": previous_adb_observed,
            "previous_adb_cleanup": previous_adb_cleanup,
            "ports_proven_free": [
                context.runtime_config.console_port,
                context.runtime_config.console_port + 1,
            ],
            "external_storage_paths": external_paths,
            "derived_hardware_transition": derived_hardware_transition,
            "ownership_transition": ownership_transition,
            "first_boot_performed": False,
            "automatic_userdata_rollback_allowed": False,
            "recovery_instructions": _recovery_instructions(
                context, unit, snapshot, previous_unit=previous_unit
            ),
        }
        predicted = _with_self_sha256(receipt)
        _update_phase_marker(
            phase_marker_path,
            context,
            unit,
            "prepared",
            expected_phases={"switching"},
            previous_unit=previous_unit,
            evidence={
                "prepare_receipt_sha256": predicted["self_sha256"],
                "post_switch_avd_sha256": post_switch_live["avd"]["tree_sha256"],
                "post_switch_descriptor_sha256": post_switch_live["descriptor"][
                    "tree_sha256"
                ],
            },
            created_epoch=created_epoch,
        )
        return _write_json_noreplace(receipt_path, receipt)
    except BaseException:
        if switched:
            _atomic_replace(context.avd_config, original_config, original_config_mode)
        with contextlib.suppress(Exception):
            _update_phase_marker(
                phase_marker_path,
                context,
                unit,
                "prepare-failed-recovery-required",
                expected_phases={"switching", "prepared"},
                previous_unit=previous_unit,
                evidence={"live_config_restored_before_boot": switched},
                created_epoch=created_epoch,
            )
        raise


def _command_as_user(
    identity: UserIdentity,
    argv: Sequence[str],
    *,
    runuser: str,
) -> list[str]:
    if os.name == "posix" and os.geteuid() == identity.uid:
        return list(argv)
    return [runuser, "--user", identity.name, "--", *argv]


def _listener_pids(output: str, port: int) -> set[int]:
    lines = _socket_lines_for_ports(output, (port,))
    pids: set[int] = set()
    for line in lines:
        pids.update(int(value) for value in re.findall(r"pid=(\d+)", line))
    return pids


def _listener_records(output: str, port: int) -> list[Mapping[str, Any]]:
    records: list[Mapping[str, Any]] = []
    for line in _socket_lines_for_ports(output, (port,)):
        tokens = line.split()
        local = next(
            (
                token
                for token in tokens
                if token.rstrip(",").rsplit(":", 1)[-1] == str(port)
            ),
            "",
        )
        if not local:
            raise KvmLiveCutoverError("ADB listener local address is not inspectable")
        host = local.rsplit(":", 1)[0].strip("[]")
        try:
            address = ipaddress.ip_address(host)
        except ValueError as exc:
            raise KvmLiveCutoverError(
                f"ADB listener address is malformed: {local}"
            ) from exc
        if not address.is_loopback:
            raise KvmLiveCutoverError(
                f"dedicated ADB listener must bind loopback only; observed {local}"
            )
        pids = {int(value) for value in re.findall(r"pid=(\d+)", line)}
        if len(pids) != 1:
            raise KvmLiveCutoverError(
                "dedicated ADB listener must expose exactly one inspectable PID per socket"
            )
        records.append({"local_address": local, "pid": next(iter(pids)), "line": line})
    return records


def _read_process_uids(proc_root: Path, pid: int) -> tuple[int, int, int, int]:
    try:
        status = (proc_root / str(pid) / "status").read_text(encoding="ascii")
    except (OSError, UnicodeDecodeError) as exc:
        raise KvmLiveCutoverError(f"cannot inspect listener PID {pid} UID") from exc
    match = re.search(
        r"^Uid:\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s*$", status, re.MULTILINE
    )
    if match is None:
        raise KvmLiveCutoverError(f"listener PID {pid} UID record is malformed")
    return tuple(int(value) for value in match.groups())  # type: ignore[return-value]


def _read_process_start_time(proc_root: Path, pid: int) -> str:
    try:
        value = (proc_root / str(pid) / "stat").read_text(encoding="ascii")
        return value.rsplit(")", 1)[1].split()[19]
    except (OSError, UnicodeDecodeError, IndexError, ValueError) as exc:
        raise KvmLiveCutoverError(
            f"cannot inspect listener PID {pid} start time"
        ) from exc


def _inspect_adb_listener(
    context: CutoverContext,
    identity: UserIdentity,
    output: str,
    *,
    proc_root: Path,
    readlink: Callable[[Path], str],
    require_candidate: bool,
    expected_uid: int | None = None,
) -> Mapping[str, Any] | None:
    records = _listener_records(output, context.runtime_config.adb_server_port)
    if not records:
        return None
    pids = {int(record["pid"]) for record in records}
    if len(pids) != 1:
        raise KvmLiveCutoverError("dedicated ADB listeners expose multiple PIDs")
    pid = next(iter(pids))
    try:
        executable = Path(readlink(proc_root / str(pid) / "exe")).resolve(strict=True)
    except OSError as exc:
        raise KvmLiveCutoverError(
            "cannot resolve dedicated ADB server executable"
        ) from exc
    if os.name == "posix" and not os.access(executable, os.X_OK):
        raise KvmLiveCutoverError("dedicated ADB server executable is not executable")
    uids = _read_process_uids(proc_root, pid)
    required_uid = identity.uid if expected_uid is None else expected_uid
    if set(uids) != {required_uid}:
        raise KvmLiveCutoverError(
            f"ADB port 5043 listener UID differs from expected UID {required_uid}: {uids}"
        )
    candidate_adb = context.runtime_config.adb.resolve(strict=True)
    if require_candidate:
        try:
            allowed = os.path.samefile(executable, candidate_adb)
        except OSError as exc:
            raise KvmLiveCutoverError(
                "cannot compare dedicated ADB executable"
            ) from exc
    else:
        runtime_releases = (
            context.inputs.runtime_root.resolve(strict=False) / "releases"
        )
        try:
            relative = executable.relative_to(runtime_releases)
        except ValueError:
            allowed = False
        else:
            allowed = (
                len(relative.parts) >= 4
                and relative.parts[-3:] == ("sdk", "platform-tools", "adb")
                and "redroid" not in os.fspath(executable).lower()
            )
    if not allowed:
        qualifier = "candidate release" if require_candidate else "pinned KVM runtime"
        raise KvmLiveCutoverError(
            f"ADB port 5043 is not owned by the {qualifier}: {executable}"
        )
    start_time = _read_process_start_time(proc_root, pid)
    return {
        "port": context.runtime_config.adb_server_port,
        "pid": pid,
        "uid": required_uid,
        "start_time_ticks": start_time,
        "executable": os.fspath(executable),
        "listeners": [
            {"local_address": record["local_address"], "pid": record["pid"]}
            for record in records
        ],
    }


def _resolve_previous_unit_identity(effective_state: Mapping[str, Any]) -> UserIdentity:
    name = str(effective_state.get("User", "")).strip() or "root"
    if name == "root":
        return UserIdentity("root", 0, Path("/root"))
    return resolve_user_identity(name)


def inspect_previous_unit_adb_listener(
    context: CutoverContext,
    previous_unit_archive: Mapping[str, Any],
    *,
    runner: CommandRunner = _run_command,
    ss_command: str = "ss",
    proc_root: Path = Path("/proc"),
    readlink: Callable[[Path], str] = os.readlink,
) -> tuple[Mapping[str, Any] | None, UserIdentity]:
    effective = previous_unit_archive.get("effective_state")
    if not isinstance(effective, Mapping):
        raise KvmLiveCutoverError("previous unit archive has no effective state")
    previous_identity = _resolve_previous_unit_identity(effective)
    sockets = _require_success(
        runner([ss_command, "-H", "-ltnp"], 15.0),
        "inspect previous KVM ADB listener",
    )
    listener = _inspect_adb_listener(
        context,
        previous_identity,
        sockets.stdout,
        proc_root=proc_root,
        readlink=readlink,
        require_candidate=False,
        expected_uid=previous_identity.uid,
    )
    if listener is not None and effective.get("ActiveState") not in {
        "active",
        "activating",
    }:
        raise KvmLiveCutoverError(
            "cannot attribute ADB port 5043 to an inactive previous unit"
        )
    return listener, previous_identity


def cleanup_previous_unit_adb_listener(
    context: CutoverContext,
    observed: Mapping[str, Any] | None,
    identity: UserIdentity,
    *,
    runner: CommandRunner = _run_command,
    ss_command: str = "ss",
    runuser: str = "runuser",
    proc_root: Path = Path("/proc"),
    readlink: Callable[[Path], str] = os.readlink,
) -> Mapping[str, Any]:
    if observed is None:
        return {"status": "no-previous-listener", "port": EXACT_ADB_SERVER_PORT}
    current_sockets = _require_success(
        runner([ss_command, "-H", "-ltnp"], 15.0),
        "revalidate previous KVM ADB listener",
    )
    current = _inspect_adb_listener(
        context,
        identity,
        current_sockets.stdout,
        proc_root=proc_root,
        readlink=readlink,
        require_candidate=False,
        expected_uid=identity.uid,
    )
    if current is None:
        return {
            "status": "previous-listener-exited-after-unit-stop",
            "port": EXACT_ADB_SERVER_PORT,
            "observed": dict(observed),
        }
    comparable = ("pid", "uid", "start_time_ticks", "executable", "listeners")
    if any(current.get(key) != observed.get(key) for key in comparable):
        raise KvmLiveCutoverError(
            "previous ADB listener identity changed after stopping the old unit"
        )
    executable = str(current["executable"])
    command = [executable, "-P", str(EXACT_ADB_SERVER_PORT), "kill-server"]
    if identity.uid != 0:
        command = _command_as_user(identity, command, runuser=runuser)
    _require_success(runner(command, 15.0), "stop proven previous KVM ADB server")
    after = _require_success(
        runner([ss_command, "-H", "-ltnp"], 15.0),
        "verify previous KVM ADB listener stopped",
    )
    if _listener_records(after.stdout, EXACT_ADB_SERVER_PORT):
        raise KvmLiveCutoverError(
            "previous KVM ADB listener remained after targeted cleanup"
        )
    return {
        "status": "previous-listener-stopped",
        "port": EXACT_ADB_SERVER_PORT,
        "observed": dict(observed),
        "cleanup_executable": executable,
        "cleanup_uid": identity.uid,
    }


def restart_dedicated_adb_server(
    context: CutoverContext,
    identity: UserIdentity,
    *,
    runner: CommandRunner = _run_command,
    ss_command: str = "ss",
    runuser: str = "runuser",
    proc_root: Path = Path("/proc"),
    readlink: Callable[[Path], str] = os.readlink,
) -> Mapping[str, Any]:
    _validate_user_identity(identity)
    adb = context.runtime_config.adb.resolve(strict=True)
    prefix = [os.fspath(adb), "-P", str(context.runtime_config.adb_server_port)]
    before_sockets = _require_success(
        runner([ss_command, "-H", "-ltnp"], 15.0), "inspect existing ADB listener"
    )
    previous = _inspect_adb_listener(
        context,
        identity,
        before_sockets.stdout,
        proc_root=proc_root,
        readlink=readlink,
        require_candidate=False,
    )
    kill = runner(
        _command_as_user(identity, [*prefix, "kill-server"], runuser=runuser),
        15.0,
    )
    if kill.returncode != 0:
        detail = (kill.stderr or kill.stdout).strip().lower()
        if "cannot connect" not in detail and "connection refused" not in detail:
            _require_success(kill, "stop dedicated ADB server")
    after_kill = _require_success(
        runner([ss_command, "-H", "-ltnp"], 15.0), "verify ADB listener stopped"
    )
    if _listener_records(after_kill.stdout, context.runtime_config.adb_server_port):
        raise KvmLiveCutoverError("dedicated ADB listener remained after bounded stop")
    start_attempted = False
    try:
        start_attempted = True
        _require_success(
            runner(
                _command_as_user(identity, [*prefix, "start-server"], runuser=runuser),
                20.0,
            ),
            "start dedicated ADB server",
        )
        server_status = _require_success(
            runner(
                _command_as_user(identity, [*prefix, "server-status"], runuser=runuser),
                15.0,
            ),
            "inspect dedicated ADB server",
        )
        listeners = _require_success(
            runner([ss_command, "-H", "-ltnp"], 15.0), "inspect ADB listener"
        )
        candidate = _inspect_adb_listener(
            context,
            identity,
            listeners.stdout,
            proc_root=proc_root,
            readlink=readlink,
            require_candidate=True,
        )
        if candidate is None:
            raise KvmLiveCutoverError("candidate dedicated ADB listener is absent")
        return {
            **candidate,
            "previous_listener": previous,
            "server_status_sha256": _sha256_bytes(
                (server_status.stdout + server_status.stderr).encode("utf-8")
            ),
        }
    except BaseException as exc:
        cleanup_errors: list[str] = []
        if start_attempted:
            try:
                cleanup = runner(
                    _command_as_user(
                        identity, [*prefix, "kill-server"], runuser=runuser
                    ),
                    15.0,
                )
                if cleanup.returncode != 0:
                    cleanup_errors.append(
                        (cleanup.stderr or cleanup.stdout).strip()
                        or "candidate ADB cleanup failed"
                    )
                post_cleanup = _require_success(
                    runner([ss_command, "-H", "-ltnp"], 15.0),
                    "verify candidate ADB cleanup",
                )
                if _listener_records(
                    post_cleanup.stdout, context.runtime_config.adb_server_port
                ):
                    cleanup_errors.append("ADB port 5043 remained in use after cleanup")
            except Exception as cleanup_exc:
                cleanup_errors.append(str(cleanup_exc))
        suffix = (
            "" if not cleanup_errors else f"; cleanup unconfirmed: {cleanup_errors}"
        )
        raise KvmLiveCutoverError(
            f"dedicated ADB restart failed transactionally: {exc}{suffix}"
        ) from exc


def _wait_for_service_active(
    unit: str,
    timeout_seconds: float,
    *,
    runner: CommandRunner,
    systemctl: str,
    poll_interval_seconds: float = 0.5,
) -> None:
    deadline = time.monotonic() + timeout_seconds
    last_state = "unknown"
    while time.monotonic() < deadline:
        last_state = _systemctl_property(
            unit, "ActiveState", runner=runner, systemctl=systemctl
        )
        if last_state == "active":
            return
        if last_state in {"failed", "deactivating"}:
            break
        time.sleep(min(poll_interval_seconds, max(0.0, deadline - time.monotonic())))
    raise KvmLiveCutoverError(
        f"KVM systemd unit did not become active; observed {last_state}"
    )


def wait_for_dedicated_adb_transport(
    context: CutoverContext,
    identity: UserIdentity,
    timeout_seconds: float,
    *,
    runner: CommandRunner = _run_command,
    runuser: str = "runuser",
    poll_interval_seconds: float = 1.0,
) -> Mapping[str, Any]:
    if timeout_seconds <= 0 or timeout_seconds > 900:
        raise KvmLiveCutoverError("ADB wait timeout must be in (0, 900]")
    adb = os.fspath(context.runtime_config.adb.resolve(strict=True))
    prefix = [adb, "-P", str(context.runtime_config.adb_server_port)]
    serial = context.runtime_config.serial
    deadline = time.monotonic() + timeout_seconds
    attempts = 0
    last_detail = "not attempted"
    while time.monotonic() < deadline:
        attempts += 1
        remaining = max(0.1, deadline - time.monotonic())
        per_command = min(5.0, remaining)
        try:
            connect = runner(
                _command_as_user(
                    identity, [*prefix, "connect", serial], runuser=runuser
                ),
                per_command,
            )
        except KvmLiveCutoverError as exc:
            last_detail = str(exc)
            time.sleep(
                min(poll_interval_seconds, max(0.0, deadline - time.monotonic()))
            )
            continue
        if connect.returncode == 0:
            state = runner(
                _command_as_user(
                    identity,
                    [*prefix, "-s", serial, "get-state"],
                    runuser=runuser,
                ),
                per_command,
            )
            last_detail = (state.stderr or state.stdout).strip()
            if state.returncode == 0 and state.stdout.strip() == "device":
                inventory = _require_success(
                    runner(
                        _command_as_user(
                            identity, [*prefix, "devices", "-l"], runuser=runuser
                        ),
                        per_command,
                    ),
                    "read dedicated ADB inventory",
                )
                devices: list[tuple[str, str]] = []
                for line in inventory.stdout.splitlines()[1:]:
                    fields = line.split()
                    if not fields:
                        continue
                    if len(fields) < 2:
                        raise KvmLiveCutoverError(
                            "dedicated ADB inventory row has no transport state"
                        )
                    devices.append((fields[0], fields[1]))
                if devices != [(serial, "device")]:
                    raise KvmLiveCutoverError(
                        f"dedicated ADB server inventory differs: {devices}"
                    )
                return {
                    "serial": serial,
                    "state": "device",
                    "server_port": context.runtime_config.adb_server_port,
                    "attempts": attempts,
                    "inventory_sha256": _sha256_bytes(inventory.stdout.encode("utf-8")),
                }
        else:
            last_detail = (connect.stderr or connect.stdout).strip()
        time.sleep(min(poll_interval_seconds, max(0.0, deadline - time.monotonic())))
    raise KvmLiveCutoverError(
        f"dedicated ADB transport did not become ready: {last_detail or 'no diagnostic'}"
    )


def _read_process_dependency_record(
    pid: int,
    *,
    proc_root: Path,
    readlink: Callable[[Path], str],
) -> Mapping[str, Any]:
    root = proc_root / str(pid)
    try:
        stat_before = (root / "stat").read_text(encoding="ascii")
        cmdline_raw = (root / "cmdline").read_bytes()
        maps_raw = (root / "maps").read_bytes()
        executable = readlink(root / "exe")
        cwd = readlink(root / "cwd")
        fd_paths = [readlink(path) for path in sorted((root / "fd").iterdir())]
        stat_after = (root / "stat").read_text(encoding="ascii")
    except (FileNotFoundError, ProcessLookupError, PermissionError, OSError) as exc:
        raise KvmLiveCutoverError(
            f"cannot completely inspect cgroup process {pid}"
        ) from exc
    cmdline = (
        cmdline_raw.replace(b"\x00", b" ")
        .decode("utf-8", errors="surrogateescape")
        .strip()
    )
    maps = maps_raw.decode("utf-8", errors="surrogateescape")
    try:
        start_before = stat_before.rsplit(")", 1)[1].split()[19]
        start_after = stat_after.rsplit(")", 1)[1].split()[19]
    except (IndexError, ValueError) as exc:
        raise KvmLiveCutoverError(f"process {pid} stat identity is malformed") from exc
    if start_before != start_after:
        raise KvmLiveCutoverError(f"process {pid} identity changed during cgroup scan")
    return {
        "pid": pid,
        "start_time_ticks": start_before,
        "exe": executable,
        "cwd": cwd,
        "cmdline": cmdline,
        "maps_sha256": _sha256_bytes(maps_raw),
        "maps_text": maps,
        "fd_paths": fd_paths,
    }


def _cgroup_pids(cgroup_directory: Path) -> list[int]:
    if cgroup_directory.is_symlink() or not cgroup_directory.is_dir():
        raise KvmLiveCutoverError("systemd cgroup directory is unavailable")
    pids: set[int] = set()
    for path in sorted(cgroup_directory.rglob("cgroup.procs")):
        try:
            for line in path.read_text(encoding="ascii").splitlines():
                if line.strip():
                    pids.add(int(line.strip()))
        except (OSError, UnicodeDecodeError, ValueError) as exc:
            raise KvmLiveCutoverError(
                f"cannot read systemd cgroup processes: {path}"
            ) from exc
    if not pids:
        raise KvmLiveCutoverError("active KVM systemd cgroup contains no processes")
    return sorted(pids)


def scan_live_cgroup_dependencies(
    context: CutoverContext,
    unit: str,
    *,
    runner: CommandRunner = _run_command,
    systemctl: str = "systemctl",
    cgroup_root: Path = Path("/sys/fs/cgroup"),
    proc_root: Path = Path("/proc"),
    readlink: Callable[[Path], str] = os.readlink,
) -> Mapping[str, Any]:
    cgroup = _systemctl_property(
        unit, "ControlGroup", runner=runner, systemctl=systemctl
    )
    if not cgroup.startswith("/") or ".." in Path(cgroup).parts:
        raise KvmLiveCutoverError("systemd ControlGroup is malformed")
    cgroup_directory = (cgroup_root / cgroup.lstrip("/")).resolve(strict=True)
    cgroup_base = cgroup_root.resolve(strict=True)
    try:
        cgroup_directory.relative_to(cgroup_base)
    except ValueError as exc:
        raise KvmLiveCutoverError("systemd ControlGroup escapes cgroup root") from exc
    pids = _cgroup_pids(cgroup_directory)
    records = [
        _read_process_dependency_record(pid, proc_root=proc_root, readlink=readlink)
        for pid in pids
    ]
    if _cgroup_pids(cgroup_directory) != pids:
        raise KvmLiveCutoverError(
            "systemd cgroup membership changed during dependency scan"
        )
    qemu_seen = False
    qemu_processes: list[int] = []
    evidence: list[Mapping[str, Any]] = []
    for record in records:
        dependency_values = [
            str(record["exe"]),
            str(record["cwd"]),
            str(record["cmdline"]),
            str(record["maps_text"]),
            *(str(value) for value in record["fd_paths"]),
        ]
        for value in dependency_values:
            violation = _dependency_violation(value, context)
            if violation is not None:
                raise KvmLiveCutoverError(
                    f"live cgroup process {record['pid']} references forbidden dependency {violation}"
                )
        combined = f"{record['exe']} {record['cmdline']}".lower()
        if "qemu-system-" in combined:
            qemu_executable = Path(str(record["exe"])).resolve(strict=True)
            emulator_root = (context.release_root / "emulator").resolve(strict=True)
            try:
                qemu_executable.relative_to(emulator_root)
            except ValueError as exc:
                raise KvmLiveCutoverError(
                    f"QEMU PID {record['pid']} executable is outside the candidate release: {qemu_executable}"
                ) from exc
            if "qemu-system-" not in qemu_executable.name:
                raise KvmLiveCutoverError(
                    f"QEMU PID {record['pid']} executable identity is ambiguous"
                )
            qemu_seen = True
            qemu_processes.append(int(record["pid"]))
        evidence.append(
            {
                "pid": record["pid"],
                "start_time_ticks": record["start_time_ticks"],
                "exe": record["exe"],
                "cwd": record["cwd"],
                "cmdline": record["cmdline"],
                "maps_sha256": record["maps_sha256"],
                "fd_paths": record["fd_paths"],
            }
        )
    if not qemu_seen:
        raise KvmLiveCutoverError("active systemd cgroup contains no QEMU process")
    return {
        "control_group": cgroup,
        "processes": evidence,
        "qemu_seen": True,
        "qemu_processes": qemu_processes,
    }


def rescan_live_cgroup_dependencies(
    context: CutoverContext,
    unit: str,
    previous: Mapping[str, Any],
    *,
    runner: CommandRunner = _run_command,
    systemctl: str = "systemctl",
    cgroup_root: Path = Path("/sys/fs/cgroup"),
    proc_root: Path = Path("/proc"),
    readlink: Callable[[Path], str] = os.readlink,
) -> Mapping[str, Any]:
    """Repeat the complete dependency scan immediately before receipt publication."""

    current = scan_live_cgroup_dependencies(
        context,
        unit,
        runner=runner,
        systemctl=systemctl,
        cgroup_root=cgroup_root,
        proc_root=proc_root,
        readlink=readlink,
    )
    if current.get("control_group") != previous.get("control_group"):
        raise KvmLiveCutoverError("KVM systemd cgroup changed between full scans")

    def identities(document: Mapping[str, Any]) -> list[tuple[Any, ...]]:
        records = document.get("processes")
        if not isinstance(records, list):
            raise KvmLiveCutoverError("KVM cgroup evidence is malformed")
        return sorted(
            (
                int(record["pid"]),
                str(record["start_time_ticks"]),
                str(record["exe"]),
                str(record["cwd"]),
                str(record["cmdline"]),
            )
            for record in records
            if isinstance(record, Mapping)
        )

    if identities(current) != identities(previous):
        raise KvmLiveCutoverError(
            "KVM cgroup process identity changed between full dependency scans"
        )
    return current


def verify_live_cgroup_stability(
    unit: str,
    cgroup_evidence: Mapping[str, Any],
    *,
    runner: CommandRunner = _run_command,
    systemctl: str = "systemctl",
    cgroup_root: Path = Path("/sys/fs/cgroup"),
    proc_root: Path = Path("/proc"),
) -> Mapping[str, Any]:
    if (
        _systemctl_property(unit, "ActiveState", runner=runner, systemctl=systemctl)
        != "active"
    ):
        raise KvmLiveCutoverError("KVM service was not active at receipt boundary")
    control_group = _systemctl_property(
        unit, "ControlGroup", runner=runner, systemctl=systemctl
    )
    if control_group != cgroup_evidence.get("control_group"):
        raise KvmLiveCutoverError("KVM systemd cgroup changed before receipt")
    cgroup_directory = (cgroup_root / control_group.lstrip("/")).resolve(strict=True)
    observed_pids = _cgroup_pids(cgroup_directory)
    expected_records = cgroup_evidence.get("processes")
    if not isinstance(expected_records, list):
        raise KvmLiveCutoverError("KVM cgroup evidence is malformed")
    expected_pids = sorted(int(record["pid"]) for record in expected_records)
    if observed_pids != expected_pids:
        raise KvmLiveCutoverError("KVM cgroup membership changed before receipt")
    for record in expected_records:
        pid = int(record["pid"])
        try:
            process_stat = (proc_root / str(pid) / "stat").read_text(encoding="ascii")
            start_time = process_stat.rsplit(")", 1)[1].split()[19]
        except (OSError, UnicodeDecodeError, IndexError, ValueError) as exc:
            raise KvmLiveCutoverError(
                f"cannot revalidate KVM process {pid} identity before receipt"
            ) from exc
        if start_time != str(record["start_time_ticks"]):
            raise KvmLiveCutoverError(
                f"KVM process {pid} identity changed before receipt"
            )
    return {
        "active_state": "active",
        "control_group": control_group,
        "pids": observed_pids,
        "stable": True,
    }


def inspect_active_avd_configs(context: CutoverContext) -> Mapping[str, Any]:
    descriptor_binding = verify_avd_descriptor_binding(context)
    candidates = [context.avd_config, context.avd_descriptor]
    hardware = context.avd_directory / "hardware-qemu.ini"
    if hardware.is_file() and not hardware.is_symlink():
        candidates.append(hardware)
    records: list[Mapping[str, Any]] = []
    for path in candidates:
        if path.is_symlink() or not path.is_file():
            raise KvmLiveCutoverError(f"active AVD config is unavailable: {path}")
        try:
            content = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            raise KvmLiveCutoverError(
                f"active AVD config is not readable UTF-8: {path}"
            ) from exc
        violation = _dependency_violation(content, context)
        if violation is not None:
            raise KvmLiveCutoverError(
                f"active AVD config references forbidden dependency {violation}: {path}"
            )
        records.append(
            {"path": os.fspath(path.resolve(strict=True)), "sha256": _sha256_file(path)}
        )
    expected = os.fspath(context.release_root / "images") + os.sep
    if _read_single_image_sysdir(context.avd_config) != expected:
        raise KvmLiveCutoverError(
            "active AVD image.sysdir differs from verified release"
        )
    return {
        "files": records,
        "image_sysdir": expected,
        "descriptor_binding": dict(descriptor_binding),
    }


def _best_effort_stop(
    unit: str,
    context: CutoverContext,
    identity: UserIdentity,
    *,
    runner: CommandRunner,
    systemctl: str,
    runuser: str,
    ss_command: str = "ss",
) -> list[str]:
    errors: list[str] = []
    try:
        stopped = runner([systemctl, "stop", "--", unit], 105.0)
        if stopped.returncode != 0:
            errors.append(
                (stopped.stderr or stopped.stdout).strip() or "systemctl stop failed"
            )
    except Exception as exc:
        errors.append(f"systemctl stop raised {type(exc).__name__}: {exc}")
    try:
        state = _systemctl_property(
            unit, "ActiveState", runner=runner, systemctl=systemctl
        )
        if state != "inactive":
            errors.append(f"systemd unit remained {state or 'unknown'} after stop")
    except Exception as exc:
        errors.append(f"post-stop systemd check raised {type(exc).__name__}: {exc}")
    adb = os.fspath(context.runtime_config.adb)
    try:
        killed = runner(
            _command_as_user(
                identity,
                [adb, "-P", str(context.runtime_config.adb_server_port), "kill-server"],
                runuser=runuser,
            ),
            15.0,
        )
        if killed.returncode != 0:
            errors.append(
                (killed.stderr or killed.stdout).strip() or "ADB kill-server failed"
            )
    except Exception as exc:
        errors.append(f"ADB kill-server raised {type(exc).__name__}: {exc}")
    try:
        listeners = _require_success(
            runner([ss_command, "-H", "-ltnp"], 15.0),
            "verify dedicated ADB server stopped",
        )
        if _listener_records(listeners.stdout, context.runtime_config.adb_server_port):
            errors.append("ADB port 5043 remained in use after activation cleanup")
    except Exception as exc:
        errors.append(f"post-cleanup ADB check raised {type(exc).__name__}: {exc}")
    return errors


def activate_live_cutover(
    context: CutoverContext,
    unit: str,
    unit_receipt_path: Path,
    prepare_receipt_path: Path,
    receipt_path: Path,
    *,
    adb_timeout_seconds: float = 180.0,
    runner: CommandRunner = _run_command,
    systemctl: str = "systemctl",
    ss_command: str = "ss",
    runuser: str = "runuser",
    cgroup_root: Path = Path("/sys/fs/cgroup"),
    proc_root: Path = Path("/proc"),
    readlink: Callable[[Path], str] = os.readlink,
    created_epoch: int | None = None,
    cutover_lock_path: Path | None = None,
    phase_marker_path: Path | None = None,
) -> Mapping[str, Any]:
    with exclusive_cutover_lock(cutover_lock_path):
        return _activate_live_cutover_locked(
            context,
            unit,
            unit_receipt_path,
            prepare_receipt_path,
            receipt_path,
            adb_timeout_seconds=adb_timeout_seconds,
            runner=runner,
            systemctl=systemctl,
            ss_command=ss_command,
            runuser=runuser,
            cgroup_root=cgroup_root,
            proc_root=proc_root,
            readlink=readlink,
            created_epoch=created_epoch,
            phase_marker_path=phase_marker_path,
        )


def _activate_live_cutover_locked(
    context: CutoverContext,
    unit: str,
    unit_receipt_path: Path,
    prepare_receipt_path: Path,
    receipt_path: Path,
    *,
    adb_timeout_seconds: float,
    runner: CommandRunner,
    systemctl: str,
    ss_command: str,
    runuser: str,
    cgroup_root: Path,
    proc_root: Path,
    readlink: Callable[[Path], str],
    created_epoch: int | None,
    phase_marker_path: Path | None,
) -> Mapping[str, Any]:
    _require_within(receipt_path, context.evidence_root, "activation receipt")
    _require_new_receipt_path(receipt_path)
    _require_within(prepare_receipt_path, context.evidence_root, "prepare receipt")
    unit_receipt, effective_before = verify_unit_receipt_and_effective_state(
        context,
        unit,
        unit_receipt_path,
        runner=runner,
        systemctl=systemctl,
    )
    prepare_receipt = load_receipt(prepare_receipt_path, PREPARE_RECEIPT_SCHEMA)
    if (
        prepare_receipt.get("status") != "prepared-offline"
        or prepare_receipt.get("release_id") != context.release_id
        or prepare_receipt.get("release_root") != os.fspath(context.release_root)
        or prepare_receipt.get("unit") != unit
        or prepare_receipt.get("unit_receipt_sha256") != unit_receipt.get("self_sha256")
        or prepare_receipt.get("first_boot_performed") is not False
    ):
        raise KvmLiveCutoverError("prepare receipt differs from this activation")
    previous_unit = prepare_receipt.get("previous_unit")
    if previous_unit is not None:
        _validate_unit_name(str(previous_unit))
        verify_previous_unit_archive_reference(
            context,
            str(previous_unit),
            prepare_receipt.get("previous_unit_archive"),
        )
        previous_state = _systemctl_property(
            str(previous_unit),
            "UnitFileState",
            runner=runner,
            systemctl=systemctl,
        )
        if previous_state not in {"masked", "masked-runtime"}:
            raise KvmLiveCutoverError(
                f"previous KVM consumer is no longer masked: {previous_state or 'unknown'}"
            )
    _require_phase_marker(
        phase_marker_path,
        context,
        unit,
        "prepared",
        previous_unit=None if previous_unit is None else str(previous_unit),
        evidence={"prepare_receipt_sha256": prepare_receipt["self_sha256"]},
    )
    identity = UserIdentity(
        name=str(unit_receipt["run_as_user"]),
        uid=int(unit_receipt["run_as_uid"]),
        home=Path(str(unit_receipt["user_home"])),
        gid=int(unit_receipt.get("run_as_gid", unit_receipt["run_as_uid"])),
    )
    _validate_user_identity(identity)
    verify_offline_avd_snapshot(context, prepare_receipt.get("snapshot"))
    expected_live = prepare_receipt.get("post_switch_live")
    observed_live = {
        "avd": snapshot_component(context.avd_directory),
        "descriptor": snapshot_component(context.avd_descriptor),
        "avd_ownership": _ownership_snapshot(context.avd_directory),
        "descriptor_ownership": _ownership_snapshot(context.avd_descriptor),
    }
    if not isinstance(expected_live, Mapping) or observed_live != expected_live:
        raise KvmLiveCutoverError(
            "live AVD or descriptor changed after prepare; refusing activation mutation"
        )
    require_service_inactive(unit, runner=runner, systemctl=systemctl)
    require_ports_free(
        (context.runtime_config.console_port, context.runtime_config.console_port + 1),
        runner=runner,
        ss_command=ss_command,
    )
    require_inactive_cgroup_empty(
        unit,
        runner=runner,
        systemctl=systemctl,
        cgroup_root=cgroup_root,
    )
    require_no_orphan_avd_users(context, proc_root=proc_root, readlink=readlink)
    external_paths = inspect_avd_external_storage_paths(context)
    live_qcow_chains = inspect_qcow_backing_chains(context, runner=runner)
    backend = backend_from_config(
        dict(context.runtime_document), RuntimeCommandExecutor()
    )
    if not isinstance(backend, KvmBackend):
        raise KvmLiveCutoverError("runtime backend changed before activation")
    backend._require_release_avd()
    _update_phase_marker(
        phase_marker_path,
        context,
        unit,
        "activating",
        expected_phases={"prepared"},
        previous_unit=None if previous_unit is None else str(previous_unit),
        evidence={"prepare_receipt_sha256": prepare_receipt["self_sha256"]},
        created_epoch=created_epoch,
    )
    adb_server: Mapping[str, Any] | None = None
    started = False
    boot_attempted = False
    failure: BaseException | None = None
    activation: dict[str, Any] = {}
    try:
        adb_server = restart_dedicated_adb_server(
            context,
            identity,
            runner=runner,
            ss_command=ss_command,
            runuser=runuser,
            proc_root=proc_root,
            readlink=readlink,
        )
        _update_phase_marker(
            phase_marker_path,
            context,
            unit,
            "boot-attempted",
            expected_phases={"activating"},
            previous_unit=None if previous_unit is None else str(previous_unit),
            evidence={"adb_pid": adb_server["pid"]},
            created_epoch=created_epoch,
        )
        boot_attempted = True
        _require_success(
            runner([systemctl, "start", "--", unit], 30.0), "start KVM systemd unit"
        )
        started = True
        _wait_for_service_active(unit, 30.0, runner=runner, systemctl=systemctl)
        transport = wait_for_dedicated_adb_transport(
            context,
            identity,
            adb_timeout_seconds,
            runner=runner,
            runuser=runuser,
        )
        adb_listener_after_transport = _inspect_adb_listener(
            context,
            identity,
            _require_success(
                runner([ss_command, "-H", "-ltnp"], 15.0),
                "revalidate dedicated ADB listener",
            ).stdout,
            proc_root=proc_root,
            readlink=readlink,
            require_candidate=True,
        )
        if (
            adb_listener_after_transport is None
            or adb_listener_after_transport["pid"] != adb_server["pid"]
        ):
            raise KvmLiveCutoverError(
                "dedicated ADB listener identity changed after transport wait"
            )
        configs = inspect_active_avd_configs(context)
        cgroup = scan_live_cgroup_dependencies(
            context,
            unit,
            runner=runner,
            systemctl=systemctl,
            cgroup_root=cgroup_root,
            proc_root=proc_root,
            readlink=readlink,
        )
        effective_after = verify_effective_systemd_contract(
            unit,
            Path(str(unit_receipt["unit_path"])),
            identity,
            Path(str(unit_receipt["run_script"])),
            Path(str(unit_receipt["alas_python"]["path"])),
            _expected_unit_arguments(context),
            int(unit_receipt["timeout_stop_seconds"]),
            runner=runner,
            systemctl=systemctl,
            require_inactive=False,
        )
        if effective_after["ActiveState"] != "active":
            raise KvmLiveCutoverError("candidate unit is not active after verification")
        final_cgroup = rescan_live_cgroup_dependencies(
            context,
            unit,
            cgroup,
            runner=runner,
            systemctl=systemctl,
            cgroup_root=cgroup_root,
            proc_root=proc_root,
            readlink=readlink,
        )
        stability = verify_live_cgroup_stability(
            unit,
            final_cgroup,
            runner=runner,
            systemctl=systemctl,
            cgroup_root=cgroup_root,
            proc_root=proc_root,
        )
        activation = {
            "preactivation": {
                "external_storage_paths": external_paths,
                "qcow_backing_chains": live_qcow_chains,
            },
            "adb_server": dict(adb_server),
            "transport": dict(transport),
            "adb_listener_after_transport": dict(adb_listener_after_transport),
            "active_configs": dict(configs),
            "cgroup_initial": dict(cgroup),
            "cgroup": dict(final_cgroup),
            "effective_systemd_before": dict(effective_before),
            "effective_systemd_after": dict(effective_after),
            "receipt_boundary_stability": dict(stability),
        }
    except BaseException as exc:
        failure = exc

    created = int(time.time() if created_epoch is None else created_epoch)
    snapshot = prepare_receipt["snapshot"]
    if failure is None:
        receipt = {
            "schema": ACTIVATION_RECEIPT_SCHEMA,
            "backend": "kvm",
            "status": "active-verified",
            "created_epoch": created,
            "release_id": context.release_id,
            "release_root": os.fspath(context.release_root),
            "unit": unit,
            "unit_receipt_sha256": str(unit_receipt["self_sha256"]),
            "prepare_receipt_sha256": str(prepare_receipt["self_sha256"]),
            "previous_unit": previous_unit,
            "first_boot_performed": True,
            "boot_attempted": True,
            "automatic_userdata_rollback_allowed": False,
            "activation": activation,
            "snapshot": snapshot,
            "recovery_instructions": _recovery_instructions(
                context,
                unit,
                snapshot,
                previous_unit=None if previous_unit is None else str(previous_unit),
            ),
        }
        try:
            predicted = _with_self_sha256(receipt)
            _update_phase_marker(
                phase_marker_path,
                context,
                unit,
                "active-verified",
                expected_phases={"boot-attempted"},
                previous_unit=None if previous_unit is None else str(previous_unit),
                evidence={"activation_receipt_sha256": predicted["self_sha256"]},
                created_epoch=created_epoch,
            )
            return _write_json_noreplace(receipt_path, receipt)
        except BaseException as exc:
            failure = KvmLiveCutoverError(
                f"activation succeeded but durable receipt publication failed: {exc}"
            )

    cleanup_errors: list[str] = []
    if boot_attempted or started or adb_server is not None:
        cleanup_errors = _best_effort_stop(
            unit,
            context,
            identity,
            runner=runner,
            systemctl=systemctl,
            runuser=runuser,
            ss_command=ss_command,
        )
    failed_receipt = {
        "schema": ACTIVATION_RECEIPT_SCHEMA,
        "backend": "kvm",
        "status": (
            "failed-stopped-recovery-required"
            if not cleanup_errors
            else "failed-stop-unconfirmed-recovery-required"
        ),
        "created_epoch": created,
        "release_id": context.release_id,
        "release_root": os.fspath(context.release_root),
        "unit": unit,
        "unit_receipt_sha256": str(unit_receipt["self_sha256"]),
        "prepare_receipt_sha256": str(prepare_receipt["self_sha256"]),
        "previous_unit": previous_unit,
        "first_boot_performed": boot_attempted,
        "boot_attempted": boot_attempted,
        "automatic_userdata_rollback_allowed": False,
        "failure_type": type(failure).__name__,
        "failure": str(failure),
        "cleanup_errors": cleanup_errors,
        "snapshot": snapshot,
        "recovery_instructions": _recovery_instructions(
            context,
            unit,
            snapshot,
            previous_unit=None if previous_unit is None else str(previous_unit),
        ),
    }
    failed_predicted = _with_self_sha256(failed_receipt)
    _update_phase_marker(
        phase_marker_path,
        context,
        unit,
        "activation-failed-recovery-required",
        expected_phases={"activating", "boot-attempted", "active-verified"},
        previous_unit=None if previous_unit is None else str(previous_unit),
        evidence={"activation_receipt_sha256": failed_predicted["self_sha256"]},
        created_epoch=created_epoch,
    )
    _write_json_noreplace(receipt_path, failed_receipt)
    raise KvmLiveCutoverError(
        f"KVM activation failed; offline snapshot recovery is required: {failure}"
    ) from failure
