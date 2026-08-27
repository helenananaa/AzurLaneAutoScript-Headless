from __future__ import annotations

import contextlib
import hashlib
import os
import shutil
import stat
from dataclasses import replace
from pathlib import Path

import pytest

import alas_headless.kvm_runtime_bundle as runtime_bundle
from alas_headless.kvm_runtime_bundle import KvmRuntimeBundleError
from alas_headless.kvm_runtime_bundle import RUNTIME_RELEASE_ROOT_MODE
from alas_headless.kvm_runtime_bundle import SDK_PLATFORMS_MODE
from alas_headless.kvm_runtime_bundle import RuntimeBundleInputs
from alas_headless.kvm_runtime_bundle import publish_runtime_release
from alas_headless.kvm_runtime_bundle import require_publish_output
from alas_headless.kvm_runtime_bundle import switch_avd_runtime_release
from alas_headless.kvm_runtime_bundle import verify_pinned_runtime_release
from alas_headless.kvm_runtime_bundle import verify_runtime_release


@contextlib.contextmanager
def _snapshot_scope(_inputs: RuntimeBundleInputs):
    yield


def _copy_tree(source: Path, target: Path) -> None:
    if source.is_dir() and not source.is_symlink():
        shutil.copytree(source, target, symlinks=True, copy_function=shutil.copy2)
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target, follow_symlinks=False)


def _output_owned(_inputs: RuntimeBundleInputs):
    return {"backend": "kvm", "peer_output_independent": True}


def _fixture(tmp_path: Path) -> RuntimeBundleInputs:
    source = tmp_path / "source"
    output = tmp_path / "output"
    runtime = tmp_path / "runtime"
    emulator = source / "prebuilts" / "android-emulator" / "linux-x86_64"
    platform_tools = source / "prebuilts" / "runtime"
    images = output / "target" / "product" / "emu64x" / "emulator" / "x86_64"
    emulator.mkdir(parents=True)
    platform_tools.mkdir(parents=True)
    images.mkdir(parents=True)
    (emulator / "emulator").write_bytes(b"emulator")
    (emulator / "emulator-check").write_bytes(b"check")
    (emulator / "lib64").mkdir()
    (emulator / "lib64" / "libemu.so").write_bytes(b"library")
    (platform_tools / "adb").write_bytes(b"adb")
    (platform_tools / "fastboot").write_bytes(b"fastboot")
    for name in ("system.img", "vendor.img", "ramdisk.img", "kernel-ranchu"):
        (images / name).write_bytes(name.encode("ascii") * 7)
    (images / "config.ini").write_text(
        "image.sysdir.1=./\nhw.cpu.arch=x86_64\n", encoding="utf-8"
    )
    (images / "userdata.img").write_bytes(b"immutable-seed")
    source_lock_sha256 = "a" * 64
    (source / ".alas-kvm-build-source-lock").write_text(
        source_lock_sha256 + "\n", encoding="utf-8"
    )
    return RuntimeBundleInputs(
        source_root=source,
        output_root=output,
        runtime_root=runtime,
        domain_sha256="b" * 64,
        profile_sha256="c" * 64,
        source_lock_sha256=source_lock_sha256,
        emulator_relative=Path("prebuilts/android-emulator/linux-x86_64"),
        adb_relative=Path("prebuilts/runtime/adb"),
        image_relative=Path("target/product/emu64x/emulator/x86_64"),
    )


def _publish(inputs: RuntimeBundleInputs, release_id: str) -> Path:
    return publish_runtime_release(
        inputs,
        release_id,
        copy_tree=_copy_tree,
        snapshot_scope_factory=_snapshot_scope,
        output_check=_output_owned,
        created_epoch=123,
    )


def test_publish_copies_complete_runtime_and_verifies_each_file(tmp_path: Path) -> None:
    inputs = _fixture(tmp_path)
    release = _publish(inputs, "kvm-14-r75-test1")

    assert (release / "emulator" / "emulator").read_bytes() == b"emulator"
    assert (release / "emulator" / "lib64" / "libemu.so").is_file()
    assert (release / "sdk" / "platform-tools" / "adb").read_bytes() == b"adb"
    assert {path.name for path in (release / "sdk" / "platform-tools").iterdir()} == {
        "adb"
    }
    platforms = release / "sdk" / "platforms"
    assert platforms.is_dir()
    assert not any(platforms.iterdir())
    assert runtime_bundle._read_sdk_platforms_mode(platforms) == 0o755
    assert (release / "images" / "system.img").is_file()
    assert runtime_bundle._read_release_root_mode(release) == 0o755
    manifest = (release / "manifest.json").read_text(encoding="utf-8")
    assert '"source_before"' in manifest
    assert '"source_after"' in manifest
    assert '"target_snapshot"' in manifest
    assert verify_runtime_release(inputs, "kvm-14-r75-test1") == release


@pytest.mark.parametrize("mode", (0o700, 0o744, 0o777))
def test_pinned_verifier_rejects_unsafe_or_untraversable_release_root_mode(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mode: int,
) -> None:
    inputs = _fixture(tmp_path)
    release = _publish(inputs, f"bad-mode-{mode:o}")
    monkeypatch.setattr(runtime_bundle, "_read_release_root_mode", lambda _path: mode)

    with pytest.raises(KvmRuntimeBundleError, match="exactly 0755"):
        verify_pinned_runtime_release(release)


def test_release_root_mode_contract_is_fixed_to_world_traversable_nonwritable() -> None:
    assert RUNTIME_RELEASE_ROOT_MODE == 0o755
    assert RUNTIME_RELEASE_ROOT_MODE & 0o011 == 0o011
    assert RUNTIME_RELEASE_ROOT_MODE & 0o022 == 0


def test_pinned_verifier_rejects_missing_sdk_platforms(tmp_path: Path) -> None:
    inputs = _fixture(tmp_path)
    release = _publish(inputs, "missing-platforms")
    (release / "sdk" / "platforms").rmdir()

    with pytest.raises(KvmRuntimeBundleError, match="SDK layout"):
        verify_pinned_runtime_release(release)


def test_pinned_verifier_rejects_nonempty_sdk_platforms(tmp_path: Path) -> None:
    inputs = _fixture(tmp_path)
    release = _publish(inputs, "nonempty-platforms")
    (release / "sdk" / "platforms" / "android.jar").write_bytes(b"not-owned")

    with pytest.raises(KvmRuntimeBundleError, match="platforms must be empty"):
        verify_pinned_runtime_release(release)


def test_pinned_verifier_rejects_symlink_sdk_platforms(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    inputs = _fixture(tmp_path)
    release = _publish(inputs, "symlink-platforms")
    platforms = release / "sdk" / "platforms"
    original_is_symlink = Path.is_symlink

    def report_platforms_symlink(path: Path) -> bool:
        return path == platforms or original_is_symlink(path)

    monkeypatch.setattr(Path, "is_symlink", report_platforms_symlink)
    with pytest.raises(KvmRuntimeBundleError, match="must be a real directory"):
        verify_pinned_runtime_release(release)


def test_pinned_verifier_rejects_wrong_sdk_platforms_mode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    inputs = _fixture(tmp_path)
    release = _publish(inputs, "wrong-platforms-mode")
    monkeypatch.setattr(runtime_bundle, "_read_sdk_platforms_mode", lambda _path: 0o700)

    with pytest.raises(KvmRuntimeBundleError, match="mode must be exactly 0755"):
        verify_pinned_runtime_release(release)


def test_sdk_platforms_mode_contract_is_fixed() -> None:
    assert SDK_PLATFORMS_MODE == 0o755


def test_publish_ignores_vcs_project_git_escape_and_copies_only_pinned_adb(
    tmp_path: Path,
) -> None:
    inputs = _fixture(tmp_path)
    project = inputs.source_root / "prebuilts" / "runtime"
    metadata = tmp_path / "repo-metadata" / "projects" / "prebuilts" / "runtime.git"
    metadata.mkdir(parents=True)
    git_entry = project / ".git"
    try:
        git_entry.symlink_to(metadata, target_is_directory=True)
    except OSError:
        # Windows without symlink privilege uses the equivalent gitdir pointer form.
        git_entry.write_text(f"gitdir: {metadata}\n", encoding="utf-8")

    release = _publish(inputs, "vcs-project-adb-only")

    platform_tools = release / "sdk" / "platform-tools"
    assert {path.name for path in platform_tools.iterdir()} == {"adb"}
    assert (platform_tools / "adb").read_bytes() == b"adb"
    assert not (platform_tools / ".git").exists()
    assert not (platform_tools / "fastboot").exists()


def test_publish_rejects_source_change_during_copy(tmp_path: Path) -> None:
    inputs = _fixture(tmp_path)

    def mutating_copy(source: Path, target: Path) -> None:
        _copy_tree(source, target)
        if source == inputs.source_root / inputs.emulator_relative:
            (source / "emulator").write_bytes(b"changed-during-copy")

    with pytest.raises(KvmRuntimeBundleError, match="source changed during publish"):
        publish_runtime_release(
            inputs,
            "source-race",
            copy_tree=mutating_copy,
            snapshot_scope_factory=_snapshot_scope,
            output_check=_output_owned,
        )
    assert not (inputs.runtime_root / "releases" / "source-race").exists()
    assert not list((inputs.runtime_root / "releases").glob(".source-race.staging.*"))


def test_publish_and_verify_reject_corrupted_target(tmp_path: Path) -> None:
    inputs = _fixture(tmp_path)

    def corrupting_copy(source: Path, target: Path) -> None:
        _copy_tree(source, target)
        if source == inputs.output_root / inputs.image_relative:
            (target / "system.img").write_bytes(b"corrupt")

    with pytest.raises(KvmRuntimeBundleError, match="differs from its source"):
        publish_runtime_release(
            inputs,
            "copy-corrupt",
            copy_tree=corrupting_copy,
            snapshot_scope_factory=_snapshot_scope,
            output_check=_output_owned,
        )

    release = _publish(inputs, "later-corrupt")
    (release / "images" / "vendor.img").write_bytes(b"damaged-after-publish")
    with pytest.raises(KvmRuntimeBundleError, match="component is damaged"):
        verify_runtime_release(inputs, "later-corrupt")


def test_publish_never_overwrites_existing_release(tmp_path: Path) -> None:
    inputs = _fixture(tmp_path)
    existing = inputs.runtime_root / "releases" / "fixed-id"
    existing.mkdir(parents=True)
    sentinel = existing / "keep.txt"
    sentinel.write_bytes(b"keep")

    def forbidden_copy(_source: Path, _target: Path) -> None:
        raise AssertionError("copy must not start for an existing release")

    with pytest.raises(KvmRuntimeBundleError, match="already exists"):
        publish_runtime_release(
            inputs,
            "fixed-id",
            copy_tree=forbidden_copy,
            snapshot_scope_factory=_snapshot_scope,
            output_check=_output_owned,
        )
    assert sentinel.read_bytes() == b"keep"


def test_publish_requires_pair_ownership_check_without_build_locks(
    tmp_path: Path,
) -> None:
    inputs = _fixture(tmp_path)
    with pytest.raises(KvmRuntimeBundleError, match="both KVM and Redroid"):
        publish_runtime_release(
            inputs,
            "missing-peer-domain",
            copy_tree=lambda _source, _target: pytest.fail("copy must not start"),
            snapshot_scope_factory=_snapshot_scope,
        )
    assert not (inputs.runtime_root / "releases" / "missing-peer-domain").exists()


def test_publish_pair_check_delegates_to_independent_output_contract(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    inputs = replace(_fixture(tmp_path), domain=object(), peer_domain=object())
    observed = {}

    def check(domain, peer_domain, *, backend, for_build):
        observed.update(
            domain=domain,
            peer_domain=peer_domain,
            backend=backend,
            for_build=for_build,
        )
        return {"backend": backend, "peer_output_independent": True}

    monkeypatch.setattr(
        "alas_headless.kvm_runtime_bundle.require_output_buildable", check
    )
    result = require_publish_output(inputs)
    assert result["peer_output_independent"] is True
    assert observed == {
        "domain": inputs.domain,
        "peer_domain": inputs.peer_domain,
        "backend": "kvm",
        "for_build": False,
    }


def test_pinned_verifier_needs_only_the_immutable_release(tmp_path: Path) -> None:
    inputs = _fixture(tmp_path)
    release = _publish(inputs, "self-contained")
    shutil.rmtree(inputs.source_root)
    shutil.rmtree(inputs.output_root)

    assert verify_pinned_runtime_release(release) == release


def test_avd_switch_and_rollback_change_only_sysdir_and_preserve_userdata(
    tmp_path: Path,
) -> None:
    inputs = _fixture(tmp_path)
    first = _publish(inputs, "release-one")
    image_source = inputs.output_root / inputs.image_relative / "system.img"
    image_source.write_bytes(b"second-release-system")
    second = _publish(inputs, "release-two")

    avd_home = tmp_path / "avd-home"
    avd = avd_home / "alas.avd"
    avd.mkdir(parents=True)
    config = avd / "config.ini"
    original_config = (
        "AvdId=alas\n"
        "image.sysdir.1=/mutable/build/output/\n"
        "disk.dataPartition.size=48G\n"
    ).encode("utf-8")
    config.write_bytes(original_config)
    config_info = config.stat()
    userdata = avd / "userdata-qemu.img"
    userdata.write_bytes(b"real-user-state")
    userdata_before = (
        hashlib.sha256(userdata.read_bytes()).hexdigest(),
        userdata.stat().st_mtime_ns,
    )

    switched = switch_avd_runtime_release(
        inputs,
        "release-two",
        avd_home,
        "alas",
        "alas-kvm.service",
        require_service_inactive=lambda _unit: None,
    )
    assert switched["changed"] is True
    assert Path(str(switched["backup"])).read_bytes() == original_config
    backup_info = Path(str(switched["backup"])).stat()
    switched_info = config.stat()
    for observed in (backup_info, switched_info):
        assert observed.st_uid == config_info.st_uid
        assert observed.st_gid == config_info.st_gid
        assert stat.S_IMODE(observed.st_mode) == stat.S_IMODE(config_info.st_mode)
    expected_second = f"image.sysdir.1={second / 'images'}{os.sep}\n"
    assert expected_second in config.read_text(encoding="utf-8")
    assert "disk.dataPartition.size=48G\n" in config.read_text(encoding="utf-8")
    assert userdata_before == (
        hashlib.sha256(userdata.read_bytes()).hexdigest(),
        userdata.stat().st_mtime_ns,
    )

    rolled_back = switch_avd_runtime_release(
        inputs,
        "release-one",
        avd_home,
        "alas",
        "alas-kvm.service",
        require_service_inactive=lambda _unit: None,
        action="rollback",
    )
    assert rolled_back["changed"] is True
    expected_first = f"image.sysdir.1={first / 'images'}{os.sep}\n"
    assert expected_first in config.read_text(encoding="utf-8")
    rolled_back_info = config.stat()
    assert rolled_back_info.st_uid == config_info.st_uid
    assert rolled_back_info.st_gid == config_info.st_gid
    assert stat.S_IMODE(rolled_back_info.st_mode) == stat.S_IMODE(config_info.st_mode)
    assert userdata_before == (
        hashlib.sha256(userdata.read_bytes()).hexdigest(),
        userdata.stat().st_mtime_ns,
    )


def test_avd_switch_rejects_active_service_before_config_write(tmp_path: Path) -> None:
    inputs = _fixture(tmp_path)
    _publish(inputs, "verified")
    avd_home = tmp_path / "avd-home"
    avd = avd_home / "alas.avd"
    avd.mkdir(parents=True)
    config = avd / "config.ini"
    original = b"image.sysdir.1=/old/\n"
    config.write_bytes(original)

    def active(_unit: str) -> None:
        raise KvmRuntimeBundleError("observed active")

    with pytest.raises(KvmRuntimeBundleError, match="active"):
        switch_avd_runtime_release(
            inputs,
            "verified",
            avd_home,
            "alas",
            "alas-kvm.service",
            require_service_inactive=active,
        )
    assert config.read_bytes() == original
    assert not (avd / "config.ini.alas-backups").exists()


def test_production_publisher_uses_verified_copy_without_build_locks() -> None:
    source = (
        Path(__file__).resolve().parents[1]
        / "python"
        / "alas_headless"
        / "kvm_runtime_bundle.py"
    ).read_text(encoding="utf-8")
    assert '"-aHAX"' in source
    assert '"--sparse"' in source
    assert "flock" not in source
    assert "build_lock" not in source
    assert "hot_output_slot_lock" not in source
    assert "renameat2" in source
