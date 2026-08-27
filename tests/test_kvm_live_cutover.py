from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Sequence

import pytest

import alas_headless.kvm_live_cutover as cutover
from alas_headless.kvm_live_cutover import (
    CutoverContext,
    KvmLiveCutoverError,
    UserIdentity,
    _listener_pids,
    activate_live_cutover,
    create_offline_avd_snapshot,
    inspect_active_avd_configs,
    inspect_avd_external_storage_paths,
    inspect_qcow_backing_chains,
    install_systemd_unit,
    prepare_live_cutover,
    render_systemd_unit,
    require_inactive_cgroup_empty,
    require_no_orphan_avd_users,
    require_ports_free,
    scan_live_cgroup_dependencies,
    verify_offline_avd_snapshot,
    wait_for_dedicated_adb_transport,
)
from alas_headless.kvm_runtime_bundle import RuntimeBundleInputs
from alas_headless.runtime_backend_kvm import KvmRuntimeConfig


def _completed(
    argv: Sequence[str], returncode: int = 0, stdout: str = "", stderr: str = ""
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(list(argv), returncode, stdout, stderr)


def _context(tmp_path: Path) -> CutoverContext:
    source = tmp_path / "source-kvm"
    output = tmp_path / "output-kvm"
    runtime = tmp_path / "runtime-kvm"
    release = runtime / "releases" / "kvm-r75-v2"
    archive = tmp_path / "archive-kvm"
    evidence = tmp_path / "evidence-kvm"
    for path in (source, output, archive, evidence, release / "emulator"):
        path.mkdir(parents=True, exist_ok=True)
    (output / "target" / "product" / "emu64x" / "emulator" / "x86_64").mkdir(
        parents=True
    )
    (release / "manifest.json").write_text("{}\n", encoding="utf-8")
    (release / "emulator" / "qemu-img").write_bytes(b"qemu-img")
    (release / "emulator" / "qemu-system-x86_64").write_bytes(b"qemu")
    adb = release / "sdk" / "platform-tools" / "adb"
    adb.parent.mkdir(parents=True)
    adb.write_bytes(b"adb")
    emulator = release / "emulator" / "emulator"
    emulator.write_bytes(b"emulator")
    emulator_check = release / "emulator" / "emulator-check"
    emulator_check.write_bytes(b"check")
    (release / "images").mkdir()

    avd_home = runtime / "avd"
    avd = avd_home / "alas-headless-kvm-r75-x86_64.avd"
    avd.mkdir(parents=True)
    (avd / "config.ini").write_text(
        f"image.sysdir.1={output}/target/product/emu64x/emulator/x86_64/\n"
        "disk.dataPartition.size=48G\n",
        encoding="utf-8",
    )
    (avd / "userdata-qemu.img").write_bytes(b"persistent-userdata")
    (avd / "cache.img").write_bytes(b"cache")
    descriptor = avd_home / "alas-headless-kvm-r75-x86_64.ini"
    descriptor.write_text(f"path={avd}\n", encoding="utf-8")

    domain_path = tmp_path / "android-build-domain.json"
    profile_path = tmp_path / "kvm-image-build-profile.json"
    runtime_config_path = tmp_path / "runtime-config.json"
    domain_path.write_text('{"backend":"kvm"}\n', encoding="utf-8")
    profile_path.write_text('{"backend":"kvm"}\n', encoding="utf-8")
    runtime_document = {
        "schema": "alas-headless.runtime-config/v1",
        "backend": "kvm",
        "serial": "127.0.0.1:5589",
        "package": "com.bilibili.azurlane",
        "component": "com.bilibili.azurlane/com.manjuu.azurlane.MainActivity",
        "host_class": "linux-x86_64-kvm-image-host",
        "runtime_release_root": str(release),
        "emulator": str(emulator),
        "emulator_check": str(emulator_check),
        "adb": str(adb),
        "avd_name": "alas-headless-kvm-r75-x86_64",
        "avd_home": str(avd_home),
        "console_port": 5588,
        "adb_server_port": 5043,
        "sdk_root": str(release / "sdk"),
    }
    runtime_config_path.write_text(
        json.dumps(runtime_document) + "\n", encoding="utf-8"
    )
    config = KvmRuntimeConfig(
        serial="127.0.0.1:5589",
        package="com.bilibili.azurlane",
        component="com.bilibili.azurlane/com.manjuu.azurlane.MainActivity",
        host_class="linux-x86_64-kvm-image-host",
        emulator=emulator,
        emulator_check=emulator_check,
        adb=adb,
        avd_name="alas-headless-kvm-r75-x86_64",
        avd_home=avd_home,
        console_port=5588,
        adb_server_port=5043,
        runtime_release_root=release,
        sdk_root=release / "sdk",
    )
    inputs = RuntimeBundleInputs(
        source_root=source,
        output_root=output,
        runtime_root=runtime,
        domain_sha256="a" * 64,
        profile_sha256="b" * 64,
        source_lock_sha256="c" * 64,
        emulator_relative=Path("emulator"),
        adb_relative=Path("adb"),
        image_relative=Path("images"),
    )
    return CutoverContext(
        inputs=inputs,
        release_id="kvm-r75-v2",
        release_root=release,
        domain_path=domain_path,
        profile_path=profile_path,
        runtime_config_path=runtime_config_path,
        runtime_document=runtime_document,
        runtime_config=config,
        archive_root=archive,
        evidence_root=evidence,
    )


def _alas_python(context: CutoverContext) -> Path:
    venv = context.inputs.runtime_root / "toolchains" / "control-venv-3.12.11"
    path = venv / "bin" / "python"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"pinned-python")
    (venv / "pyvenv.cfg").write_text("version = 3.12.11\n", encoding="utf-8")
    if os.name == "posix":
        path.chmod(0o755)
    return path


def _unit_receipt_stub(tmp_path: Path) -> dict[str, object]:
    return {
        "self_sha256": "1" * 64,
        "run_as_user": "weipa",
        "run_as_uid": 1000,
        "run_as_gid": 1000,
        "user_home": str(tmp_path / "home-weipa"),
    }


def _post_switch_live(context: CutoverContext) -> dict[str, object]:
    return {
        "avd": cutover.snapshot_component(context.avd_directory),
        "descriptor": cutover.snapshot_component(context.avd_descriptor),
        "avd_ownership": cutover._ownership_snapshot(context.avd_directory),
        "descriptor_ownership": cutover._ownership_snapshot(context.avd_descriptor),
    }


def _effective_properties(
    context: CutoverContext,
    unit_path: Path,
    run_script: Path,
    alas_python: Path,
    identity: UserIdentity,
    *,
    active_state: str = "inactive",
    unit_file_state: str = "disabled",
) -> dict[str, str]:
    argv = " ".join(
        (
            str(run_script.resolve()),
            str(context.domain_path.resolve()),
            str(context.profile_path.resolve()),
            context.release_id,
            str(context.runtime_config_path.resolve()),
        )
    )
    home = str(identity.home).replace("\\", "\\\\").replace('"', '\\"')
    logical_python = os.path.abspath(os.fspath(alas_python))
    logical_python = logical_python.replace("\\", "\\\\").replace('"', '\\"')
    return {
        "LoadState": "loaded",
        "ActiveState": active_state,
        "FragmentPath": str(unit_path.resolve()),
        "DropInPaths": "",
        "User": identity.name,
        "Environment": f'"HOME={home}" "ALAS_PYTHON={logical_python}"',
        "ExecStart": f"{{ path={run_script.resolve()} ; argv[]={argv} ; ignore_errors=no ; }}",
        "KillMode": "control-group",
        "Restart": "no",
        "TimeoutStopUSec": "1min 30s",
        "UnitFileState": unit_file_state,
        "ControlGroup": "",
    }


def test_systemd_unit_is_non_root_bounded_and_exact(tmp_path: Path) -> None:
    context = _context(tmp_path)
    run_script = tmp_path / "run-kvm-avd.sh"
    run_script.write_text("#!/bin/sh\n", encoding="utf-8")
    alas_python = _alas_python(context)
    identity = UserIdentity("weipa", 1000, tmp_path / "home-weipa")

    content = render_systemd_unit(
        context,
        "alas-kvm.service",
        identity,
        run_script,
        alas_python,
        timeout_stop_seconds=75,
    ).decode("utf-8")

    assert "User=weipa\n" in content
    assert "KillMode=control-group\n" in content
    assert "Restart=no\n" in content
    assert f"Environment=ALAS_PYTHON={os.path.abspath(alas_python)}\n" in content
    assert "TimeoutStopSec=75s\n" in content
    assert f"WorkingDirectory={context.release_root}\n" in content
    assert (
        f"ExecStart={run_script.resolve()} {context.domain_path.resolve()} "
        f"{context.profile_path.resolve()} {context.release_id} "
        f"{context.runtime_config_path.resolve()}\n"
    ) in content
    assert "systemctl start" not in content

    with pytest.raises(KvmLiveCutoverError, match="non-root"):
        render_systemd_unit(
            context,
            "alas-kvm.service",
            UserIdentity("root", 0, Path("/root")),
            run_script,
            alas_python,
        )


def test_install_unit_is_atomic_inactive_and_not_enabled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    context = _context(tmp_path)
    run_script = tmp_path / "run-kvm-avd.sh"
    run_script.write_text("#!/bin/sh\n", encoding="utf-8")
    alas_python = _alas_python(context)
    unit_directory = tmp_path / "systemd"
    unit_directory.mkdir()
    unit_path = unit_directory / "alas-kvm.service"
    identity = UserIdentity("weipa", 1000, tmp_path / "home-weipa")
    reloaded = False
    calls: list[tuple[str, ...]] = []
    monkeypatch.setattr(
        cutover,
        "_control_plane_manifest",
        lambda _path: {
            "repo_root": str(tmp_path),
            "tree_sha256": "d" * 64,
            "entries": [],
        },
    )

    def runner(
        argv: Sequence[str], _timeout: float
    ) -> subprocess.CompletedProcess[str]:
        nonlocal reloaded
        calls.append(tuple(argv))
        if "daemon-reload" in argv:
            reloaded = True
            return _completed(argv)
        for name, value in _effective_properties(
            context, unit_path, run_script, alas_python, identity
        ).items():
            if f"--property={name}" in argv:
                if name == "LoadState" and not reloaded:
                    return _completed(argv, stdout="not-found\n")
                return _completed(argv, stdout=value + "\n")
        raise AssertionError(argv)

    receipt = install_systemd_unit(
        context,
        "alas-kvm.service",
        identity,
        run_script,
        alas_python,
        unit_directory,
        context.evidence_root / "unit.json",
        runner=runner,
        created_epoch=123,
    )

    unit = (unit_directory / "alas-kvm.service").read_text(encoding="utf-8")
    assert "User=weipa" in unit
    assert receipt["status"] == "installed-inactive"
    assert receipt["enabled"] is False
    assert receipt["alas_python"]["sha256"] == cutover._sha256_file(alas_python)
    assert any("daemon-reload" in call for call in calls)
    assert not any("enable" in call or "start" in call for call in calls)


def test_effective_environment_keeps_logical_venv_symlink_and_decodes_quotes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    context = _context(tmp_path)
    target = (
        context.inputs.runtime_root
        / "toolchains"
        / "python"
        / "cpython-3.12.11-linux-x86_64-gnu"
        / "bin"
        / "python3.12"
    )
    target.parent.mkdir(parents=True)
    target.write_bytes(b"canonical-python")
    logical = (
        context.inputs.runtime_root
        / "toolchains"
        / "control-venv-3.12.11"
        / "bin"
        / "python"
    )
    logical.parent.mkdir(parents=True)
    try:
        logical.symlink_to(target)
    except OSError:
        # Windows without Developer Mode cannot create a file symlink.  The
        # resolve override below still models the exact logical/canonical split.
        logical.write_bytes(b"logical-venv-launcher")
    (logical.parent.parent / "pyvenv.cfg").write_text(
        "version = 3.12.11\n", encoding="utf-8"
    )
    run_script = tmp_path / "run-kvm-avd.sh"
    run_script.write_text("#!/bin/sh\n", encoding="utf-8")
    unit_path = tmp_path / "alas-kvm.service"
    unit_path.write_text("[Service]\n", encoding="utf-8")
    identity = UserIdentity("weipa", 1000, tmp_path / "home-weipa")
    properties = _effective_properties(
        context, unit_path, run_script, logical, identity
    )
    properties["Environment"] = properties["Environment"].replace(
        "control-venv", r"control\x2dvenv"
    )
    original_resolve = Path.resolve

    def resolve(path: Path, *args, **kwargs) -> Path:
        if os.path.abspath(path) == os.path.abspath(logical):
            return target
        return original_resolve(path, *args, **kwargs)

    monkeypatch.setattr(Path, "resolve", resolve)
    assert str(logical.resolve()) != os.path.abspath(logical)

    def runner(
        argv: Sequence[str], _timeout: float
    ) -> subprocess.CompletedProcess[str]:
        for name, value in properties.items():
            if f"--property={name}" in argv:
                return _completed(argv, stdout=value + "\n")
        raise AssertionError(argv)

    effective = cutover.verify_effective_systemd_contract(
        "alas-kvm.service",
        unit_path,
        identity,
        run_script,
        logical,
        [
            str(context.domain_path.resolve()),
            str(context.profile_path.resolve()),
            context.release_id,
            str(context.runtime_config_path.resolve()),
        ],
        90,
        runner=runner,
    )
    assert "control\\x2dvenv" in effective["Environment"]


def test_unit_install_failure_restores_previous_unit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    context = _context(tmp_path)
    run_script = tmp_path / "run-kvm-avd.sh"
    run_script.write_text("#!/bin/sh\n", encoding="utf-8")
    alas_python = _alas_python(context)
    unit_directory = tmp_path / "systemd"
    unit_directory.mkdir()
    unit = unit_directory / "alas-kvm.service"
    previous = b"[Service]\nExecStart=/old/runtime\n"
    unit.write_bytes(previous)
    monkeypatch.setattr(
        cutover,
        "_control_plane_manifest",
        lambda _path: {
            "repo_root": str(tmp_path),
            "tree_sha256": "d" * 64,
            "entries": [],
        },
    )

    def runner(
        argv: Sequence[str], _timeout: float
    ) -> subprocess.CompletedProcess[str]:
        if "--property=LoadState" in argv:
            return _completed(argv, stdout="loaded\n")
        if "--property=ActiveState" in argv:
            return _completed(argv, stdout="inactive\n")
        if "--property=UnitFileState" in argv:
            return _completed(argv, stdout="disabled\n")
        if "daemon-reload" in argv:
            return _completed(argv, returncode=1, stderr="reload failed")
        raise AssertionError(argv)

    with pytest.raises(KvmLiveCutoverError, match="daemon-reload"):
        install_systemd_unit(
            context,
            "alas-kvm.service",
            UserIdentity("weipa", 1000, tmp_path / "home-weipa"),
            run_script,
            alas_python,
            unit_directory,
            context.evidence_root / "unit-failed.json",
            runner=runner,
        )

    assert unit.read_bytes() == previous
    assert not (context.evidence_root / "unit-failed.json").exists()


@pytest.mark.parametrize("port", (5588, 5589))
def test_console_and_transport_ports_must_be_free(port: int) -> None:
    def runner(
        argv: Sequence[str], _timeout: float
    ) -> subprocess.CompletedProcess[str]:
        return _completed(
            argv,
            stdout=f'LISTEN 0 4 127.0.0.1:{port} 0.0.0.0:* users:(("qemu",pid=44,fd=9))\n',
        )

    with pytest.raises(KvmLiveCutoverError, match="still in use"):
        require_ports_free((5588, 5589), runner=runner)


def test_port_parser_distinguishes_5043_listener_pid() -> None:
    output = (
        'LISTEN 0 4 127.0.0.1:5043 0.0.0.0:* users:(("adb",pid=91,fd=7))\n'
        'LISTEN 0 4 127.0.0.1:5037 0.0.0.0:* users:(("adb",pid=92,fd=7))\n'
    )
    assert _listener_pids(output, 5043) == {91}


def test_qcow_chain_rejects_mutable_build_output_dependency(tmp_path: Path) -> None:
    context = _context(tmp_path)

    def runner(
        argv: Sequence[str], _timeout: float
    ) -> subprocess.CompletedProcess[str]:
        document = [
            {
                "filename": argv[-1],
                "format": "qcow2",
                "backing-filename": "/srv/android-cache/out/kvm-14-r75-x86_64/system.img",
                "full-backing-filename": "/srv/android-cache/out/kvm-14-r75-x86_64/system.img",
            },
            {
                "filename": "/srv/android-cache/out/kvm-14-r75-x86_64/system.img",
                "format": "raw",
            },
        ]
        return _completed(argv, stdout=json.dumps(document))

    with pytest.raises(KvmLiveCutoverError, match="forbidden dependency"):
        inspect_qcow_backing_chains(context, runner=runner)


def test_qcow_chain_allows_avd_and_immutable_release_dependencies(
    tmp_path: Path,
) -> None:
    context = _context(tmp_path)
    backing = context.release_root / "images" / "userdata.img"
    backing.write_bytes(b"immutable-base")

    def runner(
        argv: Sequence[str], _timeout: float
    ) -> subprocess.CompletedProcess[str]:
        document = [
            {
                "filename": argv[-1],
                "format": "qcow2",
                "backing-filename": str(backing),
                "full-backing-filename": str(backing),
            },
            {"filename": str(backing), "format": "raw"},
        ]
        return _completed(argv, stdout=json.dumps(document))

    records = inspect_qcow_backing_chains(context, runner=runner)
    assert {Path(str(item["image"])).name for item in records} == {
        "cache.img",
        "userdata-qemu.img",
    }


@pytest.mark.parametrize("document", ({}, [], [None], [{"format": "qcow2"}]))
def test_qcow_chain_rejects_empty_or_malformed_image_info(
    tmp_path: Path, document: object
) -> None:
    context = _context(tmp_path)
    with pytest.raises(KvmLiveCutoverError, match="ImageInfo|filename"):
        inspect_qcow_backing_chains(
            context,
            runner=lambda argv, _timeout: _completed(argv, stdout=json.dumps(document)),
        )


@pytest.mark.parametrize(
    "protocol", ("nbd://host/export", "rbd:pool/image", "file:/tmp/base.img", "json:{}")
)
def test_qcow_chain_rejects_protocol_backing_filename(
    tmp_path: Path, protocol: str
) -> None:
    context = _context(tmp_path)

    def runner(
        argv: Sequence[str], _timeout: float
    ) -> subprocess.CompletedProcess[str]:
        return _completed(
            argv,
            stdout=json.dumps(
                [
                    {
                        "filename": argv[-1],
                        "format": "qcow2",
                        "backing-filename": protocol,
                    },
                    {
                        "filename": str(context.avd_directory / "cache.img"),
                        "format": "raw",
                    },
                ]
            ),
        )

    with pytest.raises(KvmLiveCutoverError, match="protocol"):
        inspect_qcow_backing_chains(context, runner=runner)


def test_qcow_chain_allows_canonical_relative_local_backing(tmp_path: Path) -> None:
    context = _context(tmp_path)

    def runner(
        argv: Sequence[str], _timeout: float
    ) -> subprocess.CompletedProcess[str]:
        image = Path(argv[-1])
        if image.name == "userdata-qemu.img":
            return _completed(
                argv,
                stdout=json.dumps(
                    [
                        {
                            "filename": str(image),
                            "format": "qcow2",
                            "backing-filename": "cache.img",
                            "full-backing-filename": str(
                                context.avd_directory / "cache.img"
                            ),
                        },
                        {
                            "filename": str(context.avd_directory / "cache.img"),
                            "format": "raw",
                        },
                    ]
                ),
            )
        return _completed(
            argv,
            stdout=json.dumps([{"filename": str(image), "format": "raw"}]),
        )

    assert inspect_qcow_backing_chains(context, runner=runner)


def test_offline_snapshot_contains_full_avd_descriptor_and_contracts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    context = _context(tmp_path)
    unit = tmp_path / "alas-kvm.service"
    unit.write_text("[Service]\n", encoding="utf-8")
    run_script = tmp_path / "run-kvm-avd.sh"
    run_script.write_text("#!/bin/sh\n", encoding="utf-8")
    alas_python = _alas_python(context)
    unit_receipt = {
        "unit_path": str(unit),
        "run_script": str(run_script),
        "alas_python": cutover._validate_alas_python(
            alas_python,
            UserIdentity("weipa", 1000, tmp_path / "home-weipa"),
            context.inputs.runtime_root,
        ),
        "control_plane": {
            "repo_root": str(tmp_path),
            "tree_sha256": "d" * 64,
            "entries": [],
        },
    }

    def runner(
        argv: Sequence[str], _timeout: float
    ) -> subprocess.CompletedProcess[str]:
        assert argv == [
            "rsync",
            "-aHAX",
            "--sparse",
            "--numeric-ids",
            "--",
            str(context.avd_directory) + os.sep,
            str(Path(argv[-1].rstrip("/\\"))) + os.sep,
        ]
        assert "--fsync" not in argv
        source = Path(argv[-2].rstrip("/\\"))
        target = Path(argv[-1].rstrip("/\\"))
        for child in source.iterdir():
            destination = target / child.name
            if child.is_dir():
                shutil.copytree(child, destination, symlinks=True)
            else:
                shutil.copy2(child, destination)
        return _completed(argv)

    durability_events: list[tuple[str, Path, Path | None]] = []
    monkeypatch.setattr(
        cutover,
        "_fsync_tree",
        lambda path: durability_events.append(("tree", path, None)),
    )
    monkeypatch.setattr(
        cutover,
        "_fsync_directory",
        lambda path: durability_events.append(("directory", path, None)),
    )
    original_rename = cutover._rename_directory_noreplace

    def rename_directory_noreplace(source: Path, target: Path) -> None:
        durability_events.append(("rename", source, target))
        original_rename(source, target)

    monkeypatch.setattr(
        cutover, "_rename_directory_noreplace", rename_directory_noreplace
    )

    snapshot_path = context.archive_root / "avd-snapshots" / "cutover-001"
    result = create_offline_avd_snapshot(
        context,
        snapshot_path,
        [{"image": str(context.avd_directory / "userdata-qemu.img")}],
        unit_receipt,
        runner=runner,
        created_epoch=123,
    )

    copied_avd = snapshot_path / context.avd_directory.name
    assert (copied_avd / "userdata-qemu.img").read_bytes() == b"persistent-userdata"
    assert (snapshot_path / context.avd_descriptor.name).is_file()
    assert {
        "android-build-domain.json",
        "kvm-image-build-profile.json",
        "runtime-config.json",
        "systemd-unit.service",
        "run-kvm-avd.sh",
        "alas-python-canonical",
        "alas-python-pyvenv.cfg",
        "alas-python-contract.json",
        "control-plane-manifest.json",
        "control-plane-files",
        "release-manifest.json",
    } == {path.name for path in (snapshot_path / "deployment-contracts").iterdir()}
    manifest = json.loads(Path(result["manifest"]).read_text(encoding="utf-8"))
    assert manifest["restore_policy"] == "offline-whole-avd-only"
    assert manifest["avd_ownership"]
    assert manifest["descriptor_ownership"]
    stage = durability_events[0][1]
    assert durability_events == [
        ("tree", stage, None),
        ("directory", snapshot_path.parent, None),
        ("rename", stage, snapshot_path),
        ("directory", snapshot_path.parent, None),
        ("directory", snapshot_path.parent.parent, None),
    ]
    assert verify_offline_avd_snapshot(context, result)["backend"] == "kvm"

    (copied_avd / "userdata-qemu.img").write_bytes(b"damaged")
    with pytest.raises(KvmLiveCutoverError, match="content differs"):
        verify_offline_avd_snapshot(context, result)


def test_snapshot_rejects_relative_external_sdcard_path(tmp_path: Path) -> None:
    context = _context(tmp_path)
    with context.avd_config.open("a", encoding="utf-8") as output:
        output.write("sdcard.path=../../outside.img\n")
    with pytest.raises(KvmLiveCutoverError, match="external writable path"):
        inspect_avd_external_storage_paths(context)


def test_avd_descriptor_is_bound_to_the_exact_audited_directory(tmp_path: Path) -> None:
    context = _context(tmp_path)
    binding = cutover.verify_avd_descriptor_binding(context)
    assert binding["path"] == str(context.avd_directory.resolve())

    other = context.runtime_config.avd_home / "other.avd"
    other.mkdir()
    context.avd_descriptor.write_text(f"path={other}\n", encoding="utf-8")
    with pytest.raises(KvmLiveCutoverError, match="another directory"):
        cutover.verify_avd_descriptor_binding(context)


def test_avd_descriptor_rejects_mismatched_path_rel(tmp_path: Path) -> None:
    context = _context(tmp_path)
    context.avd_descriptor.write_text(
        f"path={context.avd_directory}\npath.rel=avd/other.avd\n",
        encoding="utf-8",
    )
    with pytest.raises(KvmLiveCutoverError, match="path.rel=.*another"):
        cutover.verify_avd_descriptor_binding(context)


def test_receipt_publication_is_noreplace_and_fsyncs_new_parent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[Path] = []
    monkeypatch.setattr(cutover, "_fsync_directory", lambda path: calls.append(path))
    receipt = tmp_path / "new-evidence" / "receipt.json"
    cutover._write_json_noreplace(receipt, {"schema": "test/v1"})
    original = receipt.read_bytes()
    assert receipt.parent in calls
    assert receipt.parent.parent in calls
    with pytest.raises(KvmLiveCutoverError, match="overwrite"):
        cutover._write_json_noreplace(receipt, {"schema": "changed/v1"})
    assert receipt.read_bytes() == original


def test_snapshot_directory_publication_never_replaces_existing_target(
    tmp_path: Path,
) -> None:
    source = tmp_path / "stage"
    target = tmp_path / "published"
    source.mkdir()
    target.mkdir()
    (source / "source.txt").write_text("source", encoding="utf-8")
    (target / "target.txt").write_text("target", encoding="utf-8")
    with pytest.raises(KvmLiveCutoverError, match="already exists"):
        cutover._rename_directory_noreplace(source, target)
    assert (source / "source.txt").read_text(encoding="utf-8") == "source"
    assert (target / "target.txt").read_text(encoding="utf-8") == "target"


def test_avd_runtime_ownership_plan_is_narrow_and_rejects_unwritable_metadata(
    tmp_path: Path,
) -> None:
    context = _context(tmp_path)
    avd_info = context.avd_directory.stat()
    identity = UserIdentity(
        "weipa",
        avd_info.st_uid,
        tmp_path / "home-weipa",
        avd_info.st_gid,
    )
    (context.avd_directory / "ignored.bin").write_bytes(b"ignored")
    planned = cutover.plan_avd_runtime_ownership_changes(context, identity)
    assert all(
        Path(str(item["path"])).parent == context.avd_directory for item in planned
    )
    assert not any(Path(str(item["path"])).name == "ignored.bin" for item in planned)

    metadata = context.avd_directory / "bootcompleted.ini"
    metadata.write_text("boot=yes\n", encoding="utf-8")
    metadata.chmod(0o400)
    with pytest.raises(KvmLiveCutoverError, match="owner read/write"):
        cutover.plan_avd_runtime_ownership_changes(context, identity)


def test_prepare_snapshots_before_switch_and_records_no_first_boot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    context = _context(tmp_path)
    events: list[str] = []
    unit_receipt = _unit_receipt_stub(tmp_path)

    monkeypatch.setattr(
        cutover,
        "verify_unit_receipt_and_effective_state",
        lambda *_args, **_kwargs: (unit_receipt, {}),
    )
    monkeypatch.setattr(
        cutover,
        "require_service_inactive",
        lambda *_args, **_kwargs: events.append("inactive"),
    )
    monkeypatch.setattr(
        cutover, "require_ports_free", lambda *_args, **_kwargs: events.append("ports")
    )
    monkeypatch.setattr(
        cutover,
        "require_inactive_cgroup_empty",
        lambda *_args, **_kwargs: events.append("cgroup"),
    )
    monkeypatch.setattr(
        cutover,
        "require_no_orphan_avd_users",
        lambda *_args, **_kwargs: events.append("orphan"),
    )
    monkeypatch.setattr(
        cutover,
        "inspect_avd_external_storage_paths",
        lambda *_args, **_kwargs: events.append("external") or [],
    )
    monkeypatch.setattr(
        cutover,
        "inspect_qcow_backing_chains",
        lambda *_args, **_kwargs: events.append("qcow") or [],
    )
    snapshot_path = context.archive_root / "snapshot-prepare"
    monkeypatch.setattr(
        cutover,
        "create_offline_avd_snapshot",
        lambda *_args, **_kwargs: (
            events.append("snapshot")
            or {"path": str(snapshot_path), "manifest_sha256": "2" * 64}
        ),
    )
    monkeypatch.setattr(
        cutover,
        "remove_snapshotted_derived_hardware",
        lambda *_args, **_kwargs: (
            events.append("hardware-reset") or {"removed_paths": []}
        ),
    )
    monkeypatch.setattr(
        cutover,
        "normalize_avd_runtime_ownership",
        lambda *_args, **_kwargs: events.append("ownership") or {"changed_paths": []},
    )

    def switch(*_args, **_kwargs):
        events.append("switch")
        _kwargs["require_service_inactive"]("alas-kvm.service")
        context.avd_config.write_text(
            f"image.sysdir.1={context.release_root / 'images'}{os.sep}\n",
            encoding="utf-8",
        )
        return {
            "changed": True,
            "backup": str(context.avd_directory / "config.backup"),
            "image_sysdir": str(context.release_root / "images") + os.sep,
        }

    monkeypatch.setattr(cutover, "switch_avd_runtime_release", switch)

    class Backend:
        def _require_release_avd(self) -> None:
            events.append("verify-switched")

    monkeypatch.setattr(
        cutover, "backend_from_config", lambda *_args, **_kwargs: Backend()
    )
    monkeypatch.setattr(cutover, "KvmBackend", Backend)

    receipt = prepare_live_cutover(
        context,
        "alas-kvm.service",
        context.evidence_root / "unit.json",
        snapshot_path,
        context.evidence_root / "prepare.json",
        created_epoch=123,
    )

    assert events == [
        "inactive",
        "ports",
        "cgroup",
        "orphan",
        "external",
        "qcow",
        "snapshot",
        "hardware-reset",
        "ownership",
        "switch",
        "inactive",
        "verify-switched",
    ]
    assert receipt["status"] == "prepared-offline"
    assert receipt["first_boot_performed"] is False
    assert receipt["automatic_userdata_rollback_allowed"] is False


def test_orphan_process_holding_userdata_is_rejected(tmp_path: Path) -> None:
    context = _context(tmp_path)
    proc = tmp_path / "proc"
    process = proc / "4242"
    (process / "fd").mkdir(parents=True)
    (process / "fd" / "6").write_text("", encoding="utf-8")
    (process / "fd" / "7").write_text("", encoding="utf-8")
    (process / "maps").write_text("", encoding="utf-8")
    (process / "stat").write_text(
        "4242 (runtime) S " + " ".join(["0"] * 18 + ["42420"]) + "\n",
        encoding="ascii",
    )
    targets = {
        str(process / "exe"): "/usr/bin/qemu-system-x86_64",
        str(process / "cwd"): "/",
        str(process / "root"): "/",
        str(process / "fd" / "7"): str(context.avd_directory / "userdata-qemu.img"),
    }

    def readlink(path: Path) -> str:
        if path.name == "6":
            raise FileNotFoundError(path)
        return targets[str(path)]

    with pytest.raises(KvmLiveCutoverError, match="still holds the AVD"):
        require_no_orphan_avd_users(context, proc_root=proc, readlink=readlink)


def test_persistent_proc_fd_churn_fails_closed_after_bounded_retries(
    tmp_path: Path,
) -> None:
    context = _context(tmp_path)
    proc = tmp_path / "proc"
    process = proc / "4243"
    (process / "fd").mkdir(parents=True)
    (process / "fd" / "6").write_text("", encoding="utf-8")
    (process / "maps").write_text("", encoding="utf-8")
    (process / "stat").write_text(
        "4243 (runtime) S " + " ".join(["0"] * 18 + ["42430"]) + "\n",
        encoding="ascii",
    )

    def readlink(path: Path) -> str:
        if path.name == "6":
            raise FileNotFoundError(path)
        return "/"

    with pytest.raises(KvmLiveCutoverError, match="bounded /proc retries"):
        require_no_orphan_avd_users(context, proc_root=proc, readlink=readlink)


def _proc_stat(pid: int, *, start_time: int, flags: int) -> str:
    fields = ["S"] + ["0"] * 18 + [str(start_time)]
    fields[1] = "2"
    fields[6] = str(flags)
    return f"{pid} (migration/14) " + " ".join(fields) + "\n"


def test_stable_kernel_thread_without_exe_is_not_a_false_orphan(
    tmp_path: Path,
) -> None:
    context = _context(tmp_path)
    proc = tmp_path / "proc"
    process = proc / "100"
    (process / "fd").mkdir(parents=True)
    (process / "maps").write_text("", encoding="utf-8")
    (process / "stat").write_text(
        _proc_stat(100, start_time=1000, flags=69238848),
        encoding="ascii",
    )

    def readlink(path: Path) -> str:
        if path.name == "exe":
            raise FileNotFoundError(path)
        assert path.name in {"cwd", "root"}
        return "/"

    require_no_orphan_avd_users(context, proc_root=proc, readlink=readlink)


def test_kernel_thread_still_rejects_an_avd_file_descriptor(tmp_path: Path) -> None:
    context = _context(tmp_path)
    proc = tmp_path / "proc"
    process = proc / "100"
    (process / "fd").mkdir(parents=True)
    (process / "fd" / "7").write_text("", encoding="utf-8")
    (process / "maps").write_text("", encoding="utf-8")
    (process / "stat").write_text(
        _proc_stat(100, start_time=1000, flags=69238848),
        encoding="ascii",
    )

    def readlink(path: Path) -> str:
        if path.name == "exe":
            raise FileNotFoundError(path)
        if path.name == "7":
            return str(context.avd_directory / "userdata-qemu.img")
        return "/"

    with pytest.raises(KvmLiveCutoverError, match="still holds the AVD"):
        require_no_orphan_avd_users(context, proc_root=proc, readlink=readlink)


def test_non_kernel_thread_missing_exe_still_fails_closed(tmp_path: Path) -> None:
    context = _context(tmp_path)
    proc = tmp_path / "proc"
    process = proc / "4244"
    (process / "fd").mkdir(parents=True)
    (process / "maps").write_text("", encoding="utf-8")
    (process / "stat").write_text(
        _proc_stat(4244, start_time=42440, flags=0),
        encoding="ascii",
    )

    def readlink(path: Path) -> str:
        if path.name == "exe":
            raise FileNotFoundError(path)
        return "/"

    with pytest.raises(KvmLiveCutoverError, match="bounded /proc retries"):
        require_no_orphan_avd_users(context, proc_root=proc, readlink=readlink)


def test_inactive_service_with_recursive_cgroup_process_is_rejected(
    tmp_path: Path,
) -> None:
    cgroup_root = tmp_path / "cgroup"
    child = cgroup_root / "system.slice" / "alas-kvm.service" / "emulator"
    child.mkdir(parents=True)
    (child / "cgroup.procs").write_text("919\n", encoding="ascii")

    def runner(
        argv: Sequence[str], _timeout: float
    ) -> subprocess.CompletedProcess[str]:
        assert "--property=ControlGroup" in argv
        return _completed(argv, stdout="/system.slice/alas-kvm.service\n")

    with pytest.raises(KvmLiveCutoverError, match="still contains processes"):
        require_inactive_cgroup_empty(
            "alas-kvm.service", runner=runner, cgroup_root=cgroup_root
        )


def test_adb_wait_uses_release_binary_port_and_exact_serial(tmp_path: Path) -> None:
    context = _context(tmp_path)
    calls: list[tuple[str, ...]] = []

    def runner(
        argv: Sequence[str], _timeout: float
    ) -> subprocess.CompletedProcess[str]:
        calls.append(tuple(argv))
        if "connect" in argv:
            return _completed(argv, stdout="connected\n")
        if "get-state" in argv:
            return _completed(argv, stdout="device\n")
        if "devices" in argv:
            return _completed(
                argv,
                stdout="List of devices attached\n127.0.0.1:5589\tdevice product:sdk\n",
            )
        raise AssertionError(argv)

    result = wait_for_dedicated_adb_transport(
        context,
        UserIdentity("weipa", 1000, tmp_path / "home-weipa"),
        10.0,
        runner=runner,
    )

    assert result["serial"] == "127.0.0.1:5589"
    for call in calls:
        assert str(context.runtime_config.adb) in call
        port_index = call.index("-P")
        assert call[port_index + 1] == "5043"
    assert any(call[-2:] == ("connect", "127.0.0.1:5589") for call in calls)


def test_adb_wait_rejects_transport_that_turns_offline_in_final_inventory(
    tmp_path: Path,
) -> None:
    context = _context(tmp_path)

    def runner(
        argv: Sequence[str], _timeout: float
    ) -> subprocess.CompletedProcess[str]:
        if "connect" in argv:
            return _completed(argv, stdout="connected\n")
        if "get-state" in argv:
            return _completed(argv, stdout="device\n")
        if "devices" in argv:
            return _completed(
                argv,
                stdout="List of devices attached\n127.0.0.1:5589\toffline\n",
            )
        raise AssertionError(argv)

    with pytest.raises(KvmLiveCutoverError, match="inventory differs"):
        wait_for_dedicated_adb_transport(
            context,
            UserIdentity("weipa", 1000, tmp_path / "home-weipa"),
            10.0,
            runner=runner,
        )


def test_whole_cgroup_scan_rejects_forbidden_child_fd(tmp_path: Path) -> None:
    context = _context(tmp_path)
    cgroup_root = tmp_path / "cgroup"
    group = cgroup_root / "system.slice" / "alas-kvm.service"
    child = group / "emulator"
    child.mkdir(parents=True)
    (group / "cgroup.procs").write_text("101\n", encoding="ascii")
    (child / "cgroup.procs").write_text("202\n", encoding="ascii")
    proc_root = tmp_path / "proc"
    links: dict[str, str] = {}
    for pid in (101, 202):
        process = proc_root / str(pid)
        (process / "fd").mkdir(parents=True)
        (process / "fd" / "3").write_text("", encoding="utf-8")
        (process / "cmdline").write_bytes(
            b"qemu-system-x86_64\x00" if pid == 202 else b"emulator\x00"
        )
        (process / "stat").write_text(
            f"{pid} (runtime) S " + " ".join(["0"] * 18 + [str(pid * 10)]) + "\n",
            encoding="ascii",
        )
        (process / "maps").write_text(
            "1000-2000 r-xp 0 00:00 0 /lib/libc.so\n", encoding="utf-8"
        )
        links[str(process / "exe")] = (
            str(context.release_root / "emulator" / "qemu-system-x86_64")
            if pid == 202
            else str(context.runtime_config.emulator)
        )
        links[str(process / "cwd")] = str(context.release_root)
        links[str(process / "fd" / "3")] = (
            str(context.release_root / "images" / "system.img")
            if pid == 202
            else "socket:[22]"
        )

    def runner(
        argv: Sequence[str], _timeout: float
    ) -> subprocess.CompletedProcess[str]:
        assert "--property=ControlGroup" in argv
        return _completed(argv, stdout="/system.slice/alas-kvm.service\n")

    allowed = scan_live_cgroup_dependencies(
        context,
        "alas-kvm.service",
        runner=runner,
        cgroup_root=cgroup_root,
        proc_root=proc_root,
        readlink=lambda path: links[str(path)],
    )
    assert allowed["qemu_seen"] is True
    assert {item["pid"] for item in allowed["processes"]} == {101, 202}
    assert (
        cutover.rescan_live_cgroup_dependencies(
            context,
            "alas-kvm.service",
            allowed,
            runner=runner,
            cgroup_root=cgroup_root,
            proc_root=proc_root,
            readlink=lambda path: links[str(path)],
        )["qemu_seen"]
        is True
    )

    links[str(proc_root / "202" / "fd" / "3")] = str(
        context.inputs.runtime_root / "releases" / "legacy-r2" / "images" / "system.img"
    )
    with pytest.raises(KvmLiveCutoverError, match="non-candidate KVM runtime"):
        cutover.rescan_live_cgroup_dependencies(
            context,
            "alas-kvm.service",
            allowed,
            runner=runner,
            cgroup_root=cgroup_root,
            proc_root=proc_root,
            readlink=lambda path: links[str(path)],
        )

    links[str(proc_root / "202" / "fd" / "3")] = (
        "/srv/android-build/src/redroid-14-r75/system.img"
    )
    with pytest.raises(KvmLiveCutoverError, match="forbidden dependency"):
        cutover.rescan_live_cgroup_dependencies(
            context,
            "alas-kvm.service",
            allowed,
            runner=runner,
            cgroup_root=cgroup_root,
            proc_root=proc_root,
            readlink=lambda path: links[str(path)],
        )


def test_active_config_must_use_candidate_release(tmp_path: Path) -> None:
    context = _context(tmp_path)
    with pytest.raises(KvmLiveCutoverError, match="forbidden dependency|differs"):
        inspect_active_avd_configs(context)

    context.avd_config.write_text(
        f"image.sysdir.1={context.release_root / 'images'}{os.sep}\n",
        encoding="utf-8",
    )
    result = inspect_active_avd_configs(context)
    assert result["image_sysdir"] == str(context.release_root / "images") + os.sep


def test_activation_timeout_stops_candidate_and_records_manual_recovery(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    context = _context(tmp_path)
    unit_receipt = {
        "self_sha256": "1" * 64,
        "run_as_user": "weipa",
        "run_as_uid": 1000,
        "user_home": str(tmp_path / "home-weipa"),
    }
    prepare_receipt = {
        "schema": cutover.PREPARE_RECEIPT_SCHEMA,
        "status": "prepared-offline",
        "release_id": context.release_id,
        "release_root": str(context.release_root),
        "unit": "alas-kvm.service",
        "unit_receipt_sha256": unit_receipt["self_sha256"],
        "first_boot_performed": False,
        "self_sha256": "2" * 64,
        "snapshot": {"path": str(context.archive_root / "snapshot-001")},
        "post_switch_live": _post_switch_live(context),
    }
    stopped: list[str] = []

    class Backend:
        def _require_release_avd(self) -> None:
            return None

    monkeypatch.setattr(
        cutover,
        "verify_unit_receipt_and_effective_state",
        lambda *_args, **_kwargs: (unit_receipt, {}),
    )
    monkeypatch.setattr(cutover, "load_receipt", lambda *_args: prepare_receipt)
    monkeypatch.setattr(
        cutover, "verify_offline_avd_snapshot", lambda *_args, **_kwargs: {}
    )
    monkeypatch.setattr(
        cutover, "require_service_inactive", lambda *_args, **_kwargs: None
    )
    monkeypatch.setattr(cutover, "require_ports_free", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        cutover, "require_inactive_cgroup_empty", lambda *_args, **_kwargs: None
    )
    monkeypatch.setattr(
        cutover, "require_no_orphan_avd_users", lambda *_args, **_kwargs: None
    )
    monkeypatch.setattr(
        cutover, "inspect_avd_external_storage_paths", lambda *_args, **_kwargs: []
    )
    monkeypatch.setattr(
        cutover, "inspect_qcow_backing_chains", lambda *_args, **_kwargs: []
    )
    monkeypatch.setattr(
        cutover, "backend_from_config", lambda *_args, **_kwargs: Backend()
    )
    monkeypatch.setattr(cutover, "KvmBackend", Backend)
    monkeypatch.setattr(
        cutover,
        "restart_dedicated_adb_server",
        lambda *_args, **_kwargs: {"port": 5043, "pid": 44},
    )
    monkeypatch.setattr(
        cutover, "_wait_for_service_active", lambda *_args, **_kwargs: None
    )
    monkeypatch.setattr(
        cutover,
        "wait_for_dedicated_adb_transport",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            KvmLiveCutoverError("adb-ready-timeout")
        ),
    )
    monkeypatch.setattr(
        cutover,
        "_best_effort_stop",
        lambda unit, *_args, **_kwargs: stopped.append(unit) or [],
    )

    def runner(
        argv: Sequence[str], _timeout: float
    ) -> subprocess.CompletedProcess[str]:
        assert argv[:2] == ["systemctl", "start"]
        return _completed(argv)

    receipt = context.evidence_root / "activation-failed.json"
    with pytest.raises(KvmLiveCutoverError, match="snapshot recovery is required"):
        activate_live_cutover(
            context,
            "alas-kvm.service",
            context.evidence_root / "unit.json",
            context.evidence_root / "prepare.json",
            receipt,
            runner=runner,
            created_epoch=123,
        )

    document = json.loads(receipt.read_text(encoding="utf-8"))
    assert stopped == ["alas-kvm.service"]
    assert document["status"] == "failed-stopped-recovery-required"
    assert document["first_boot_performed"] is True
    assert document["automatic_userdata_rollback_allowed"] is False
    assert any(
        "Restore the entire offline snapshot" in item
        for item in document["recovery_instructions"]
    )


def test_cutover_lock_and_phase_marker_reject_parallel_or_out_of_order_work(
    tmp_path: Path,
) -> None:
    context = _context(tmp_path)
    lock = tmp_path / "formal-cutover.lock"
    with cutover.exclusive_cutover_lock(lock):
        with pytest.raises(KvmLiveCutoverError, match="another KVM live cutover"):
            with cutover.exclusive_cutover_lock(lock):
                pass

    marker = context.evidence_root / "phase.json"
    cutover._update_phase_marker(
        marker,
        context,
        "alas-kvm.service",
        "unit-installed",
        expected_phases={None},
        evidence={"unit_receipt_sha256": "1" * 64},
        created_epoch=1,
    )
    with pytest.raises(KvmLiveCutoverError, match="phase must be"):
        cutover._update_phase_marker(
            marker,
            context,
            "alas-kvm.service",
            "boot-attempted",
            expected_phases={"prepared"},
        )


def test_effective_systemd_contract_rejects_drop_in_override(tmp_path: Path) -> None:
    context = _context(tmp_path)
    run_script = tmp_path / "run-kvm-avd.sh"
    run_script.write_text("#!/bin/sh\n", encoding="utf-8")
    alas_python = _alas_python(context)
    unit = tmp_path / "alas-kvm.service"
    unit.write_text("[Service]\n", encoding="utf-8")
    identity = UserIdentity("weipa", 1000, tmp_path / "home-weipa")
    properties = _effective_properties(context, unit, run_script, alas_python, identity)
    properties["DropInPaths"] = "/etc/systemd/system/alas-kvm.service.d/override.conf"

    def runner(
        argv: Sequence[str], _timeout: float
    ) -> subprocess.CompletedProcess[str]:
        name = next(key for key in properties if f"--property={key}" in argv)
        return _completed(argv, stdout=properties[name] + "\n")

    with pytest.raises(KvmLiveCutoverError, match="DropInPaths"):
        cutover.verify_effective_systemd_contract(
            "alas-kvm.service",
            unit,
            identity,
            run_script,
            alas_python,
            cutover._expected_unit_arguments(context),
            90,
            runner=runner,
        )


def test_previous_unit_is_archived_before_stop_disable_and_mask(
    tmp_path: Path,
) -> None:
    context = _context(tmp_path)
    fragment = tmp_path / "old.service"
    drop_in = tmp_path / "10-old.conf"
    fragment.write_text("[Service]\nExecStart=/old/emulator\n", encoding="utf-8")
    drop_in.write_text("[Service]\nEnvironment=OLD=1\n", encoding="utf-8")
    state = {"active": "active", "unit_file": "enabled"}
    calls: list[tuple[str, ...]] = []
    effective = {
        "LoadState": "loaded",
        "ActiveState": "active",
        "FragmentPath": str(fragment),
        "DropInPaths": str(drop_in),
        "User": "weipa",
        "Environment": "",
        "ExecStart": "{ path=/old/emulator ; argv[]=/old/emulator ; }",
        "KillMode": "control-group",
        "Restart": "no",
        "TimeoutStopUSec": "1min 30s",
        "UnitFileState": "enabled",
        "ControlGroup": "/system.slice/old.service",
    }

    def runner(
        argv: Sequence[str], _timeout: float
    ) -> subprocess.CompletedProcess[str]:
        calls.append(tuple(argv))
        if "is-enabled" in argv:
            return _completed(argv, stdout="enabled\n")
        if "stop" in argv:
            state["active"] = "inactive"
            return _completed(argv)
        if "disable" in argv:
            state["unit_file"] = "disabled"
            return _completed(argv)
        if "mask" in argv:
            state["unit_file"] = "masked-runtime"
            return _completed(argv)
        if "daemon-reload" in argv:
            return _completed(argv)
        for key, value in effective.items():
            if f"--property={key}" in argv:
                if key == "ActiveState":
                    value = state["active"]
                elif key == "UnitFileState":
                    value = state["unit_file"]
                return _completed(argv, stdout=value + "\n")
        raise AssertionError(argv)

    archive_path = context.evidence_root / "previous-unit.json"
    archive = cutover.archive_previous_systemd_unit(
        context,
        "old.service",
        archive_path,
        runner=runner,
        created_epoch=1,
    )
    transition = cutover.stop_disable_mask_previous_unit("old.service", runner=runner)

    assert archive["effective_state"]["FragmentPath"] == str(fragment)
    assert {item["path"] for item in archive["files"]} == {
        str(fragment.resolve()),
        str(drop_in.resolve()),
    }
    assert transition["unit_file_state_after"] == "masked-runtime"
    stop_index = next(i for i, call in enumerate(calls) if "stop" in call)
    assert all("stop" not in call for call in calls[:stop_index])
    assert any("disable" in call for call in calls)
    assert any("mask" in call and "--runtime" in call for call in calls)


def test_adb_unknown_listener_is_rejected_before_kill(tmp_path: Path) -> None:
    context = _context(tmp_path)
    foreign = tmp_path / "foreign-adb"
    foreign.write_bytes(b"foreign")
    proc_root = tmp_path / "proc"
    process = proc_root / "91"
    process.mkdir(parents=True)
    (process / "status").write_text(
        "Name:\tadb\nUid:\t1000\t1000\t1000\t1000\n", encoding="ascii"
    )
    calls: list[tuple[str, ...]] = []

    def runner(
        argv: Sequence[str], _timeout: float
    ) -> subprocess.CompletedProcess[str]:
        calls.append(tuple(argv))
        assert argv[0] == "ss"
        return _completed(
            argv,
            stdout='LISTEN 0 4 127.0.0.1:5043 0.0.0.0:* users:(("adb",pid=91,fd=7))\n',
        )

    with pytest.raises(KvmLiveCutoverError, match="pinned KVM runtime"):
        cutover.restart_dedicated_adb_server(
            context,
            UserIdentity("weipa", 1000, tmp_path / "home-weipa"),
            runner=runner,
            proc_root=proc_root,
            readlink=lambda _path: str(foreign),
        )
    assert calls == [("ss", "-H", "-ltnp")]


def test_adb_post_start_failure_kills_candidate_transactionally(
    tmp_path: Path,
) -> None:
    context = _context(tmp_path)
    calls: list[tuple[str, ...]] = []
    socket_reads = 0

    def runner(
        argv: Sequence[str], _timeout: float
    ) -> subprocess.CompletedProcess[str]:
        nonlocal socket_reads
        calls.append(tuple(argv))
        if argv[0] == "ss":
            socket_reads += 1
            if socket_reads == 3:
                return _completed(
                    argv,
                    stdout='LISTEN 0 4 0.0.0.0:5043 0.0.0.0:* users:(("adb",pid=91,fd=7))\n',
                )
            return _completed(argv)
        if "kill-server" in argv:
            return _completed(argv, returncode=1, stderr="cannot connect")
        if "start-server" in argv or "server-status" in argv:
            return _completed(argv, stdout="ok\n")
        raise AssertionError(argv)

    with pytest.raises(KvmLiveCutoverError, match="transactionally"):
        cutover.restart_dedicated_adb_server(
            context,
            UserIdentity("weipa", 1000, tmp_path / "home-weipa"),
            runner=runner,
            proc_root=tmp_path / "proc",
        )
    assert sum("kill-server" in call for call in calls) == 2
    assert socket_reads == 4


def test_root_legacy_adb_is_only_cleaned_after_exact_provenance_recheck(
    tmp_path: Path,
) -> None:
    context = _context(tmp_path)
    old_adb = (
        context.inputs.runtime_root
        / "releases"
        / "old-kvm-release"
        / "sdk"
        / "platform-tools"
        / "adb"
    )
    old_adb.parent.mkdir(parents=True)
    old_adb.write_bytes(b"old-pinned-adb")
    proc_root = tmp_path / "proc"
    process = proc_root / "91"
    process.mkdir(parents=True)
    (process / "status").write_text("Name:\tadb\nUid:\t0\t0\t0\t0\n", encoding="ascii")
    (process / "stat").write_text(
        "91 (adb) S " + " ".join(["0"] * 18 + ["910"]) + "\n",
        encoding="ascii",
    )
    listener = 'LISTEN 0 4 127.0.0.1:5043 0.0.0.0:* users:(("adb",pid=91,fd=7))\n'
    archive = {"effective_state": {"ActiveState": "active", "User": ""}}

    def inspect_runner(
        argv: Sequence[str], _timeout: float
    ) -> subprocess.CompletedProcess[str]:
        return _completed(argv, stdout=listener)

    observed, identity = cutover.inspect_previous_unit_adb_listener(
        context,
        archive,
        runner=inspect_runner,
        proc_root=proc_root,
        readlink=lambda _path: str(old_adb),
    )
    calls: list[tuple[str, ...]] = []
    socket_reads = 0

    def cleanup_runner(
        argv: Sequence[str], _timeout: float
    ) -> subprocess.CompletedProcess[str]:
        nonlocal socket_reads
        calls.append(tuple(argv))
        if argv[0] == "ss":
            socket_reads += 1
            return _completed(argv, stdout=listener if socket_reads == 1 else "")
        assert tuple(argv) == (str(old_adb.resolve()), "-P", "5043", "kill-server")
        return _completed(argv)

    result = cutover.cleanup_previous_unit_adb_listener(
        context,
        observed,
        identity,
        runner=cleanup_runner,
        proc_root=proc_root,
        readlink=lambda _path: str(old_adb),
    )

    assert identity.uid == 0
    assert result["status"] == "previous-listener-stopped"
    assert any(call[0] == str(old_adb.resolve()) for call in calls)
    assert not any("kill" in item for call in calls for item in call if item.isdigit())


def test_qcow_chain_rejects_another_runtime_release(tmp_path: Path) -> None:
    context = _context(tmp_path)
    other = context.inputs.runtime_root / "releases" / "old" / "images" / "system.img"
    other.parent.mkdir(parents=True)
    other.write_bytes(b"old")

    def runner(
        argv: Sequence[str], _timeout: float
    ) -> subprocess.CompletedProcess[str]:
        return _completed(
            argv,
            stdout=json.dumps(
                [
                    {
                        "filename": argv[-1],
                        "format": "qcow2",
                        "backing-filename": str(other),
                        "full-backing-filename": str(other),
                    },
                    {"filename": str(other), "format": "raw"},
                ]
            ),
        )

    with pytest.raises(KvmLiveCutoverError, match="candidate release|non-candidate"):
        inspect_qcow_backing_chains(context, runner=runner)


def test_mutable_external_storage_must_remain_inside_live_avd(
    tmp_path: Path,
) -> None:
    context = _context(tmp_path)
    with context.avd_config.open("a", encoding="utf-8") as output:
        output.write(
            f"disk.dataPartition.path={context.release_root / 'images' / 'userdata.img'}\n"
        )
    with pytest.raises(KvmLiveCutoverError, match="external writable path"):
        inspect_avd_external_storage_paths(context)


def test_legacy_hardware_is_snapshotted_then_removed_for_candidate_rebuild(
    tmp_path: Path,
) -> None:
    context = _context(tmp_path)
    legacy = context.inputs.runtime_root / "releases" / "legacy-r2" / "images"
    legacy.mkdir(parents=True)
    legacy_sdk = legacy.parent / "sdk"
    legacy_sdk.mkdir()
    for name in ("kernel-ranchu", "ramdisk.img", "system.img", "vendor.img"):
        (legacy / name).write_bytes(name.encode("ascii"))
    context.avd_config.write_text(
        f"image.sysdir.1={legacy}{os.sep}\n", encoding="utf-8"
    )
    hardware = context.avd_directory / "hardware-qemu.ini"
    hardware.write_text(
        f"kernel.path = {legacy / 'kernel-ranchu'}\n"
        f"disk.ramdisk.path = {legacy / 'ramdisk.img'}\n"
        f"disk.systemPartition.initPath = {legacy / 'system.img'}\n"
        f"disk.vendorPartition.initPath = {legacy / 'vendor.img'}\n"
        f"android.sdk.root = {legacy_sdk}\n"
        f"android.avd.home = {context.runtime_config.avd_home}\n",
        encoding="utf-8",
    )
    lock = context.avd_directory / "hardware-qemu.ini.lock"
    lock.write_bytes(b"")
    previous = cutover.validate_pre_switch_image_sysdir(context, str(legacy) + os.sep)
    records = inspect_avd_external_storage_paths(context, previous_image_root=previous)
    assert any(item["config"] == str(hardware) for item in records)
    snapshot_root = context.archive_root / "snapshot"
    snapshot_root.mkdir()
    manifest = snapshot_root / "snapshot-manifest.json"
    manifest.write_text("{}\n", encoding="utf-8")
    transition = cutover.remove_snapshotted_derived_hardware(
        context,
        {
            "manifest": str(manifest),
            "manifest_sha256": cutover._sha256_file(manifest),
        },
        previous,
    )
    assert transition["removed_paths"] == [str(hardware), str(lock)]
    assert not hardware.exists()
    assert not lock.exists()
    assert transition["recursive_delete_performed"] is False


@pytest.mark.parametrize("dependency_location", ["sibling-release", "outside"])
def test_legacy_hardware_rejects_non_previous_release_sdk_root(
    tmp_path: Path,
    dependency_location: str,
) -> None:
    context = _context(tmp_path)
    legacy = context.inputs.runtime_root / "releases" / "legacy-r2" / "images"
    legacy.mkdir(parents=True)
    if dependency_location == "sibling-release":
        dependency = context.inputs.runtime_root / "releases" / "hostile" / "sdk"
    else:
        dependency = tmp_path / "outside" / "sdk"
    dependency.mkdir(parents=True)
    (context.avd_directory / "hardware-qemu.ini").write_text(
        f"android.sdk.root = {dependency}\n",
        encoding="utf-8",
    )

    with pytest.raises(KvmLiveCutoverError, match="external writable path"):
        inspect_avd_external_storage_paths(context, previous_image_root=legacy)


def test_legacy_hardware_requires_exact_configured_avd_home(tmp_path: Path) -> None:
    context = _context(tmp_path)
    legacy = context.inputs.runtime_root / "releases" / "legacy-r2" / "images"
    legacy.mkdir(parents=True)
    sibling = context.runtime_config.avd_home.parent / "other-avd-home"
    sibling.mkdir()
    (context.avd_directory / "hardware-qemu.ini").write_text(
        f"android.avd.home = {sibling}\n",
        encoding="utf-8",
    )

    with pytest.raises(KvmLiveCutoverError, match="external writable path"):
        inspect_avd_external_storage_paths(context, previous_image_root=legacy)


def test_legacy_hardware_mutable_media_cannot_use_previous_release_root(
    tmp_path: Path,
) -> None:
    context = _context(tmp_path)
    legacy = context.inputs.runtime_root / "releases" / "legacy-r2" / "images"
    legacy.mkdir(parents=True)
    cache = legacy.parent / "cache.img"
    cache.write_bytes(b"cache")
    (context.avd_directory / "hardware-qemu.ini").write_text(
        f"disk.cachePartition.path = {cache}\n",
        encoding="utf-8",
    )

    with pytest.raises(KvmLiveCutoverError, match="external writable path"):
        inspect_avd_external_storage_paths(context, previous_image_root=legacy)


def test_active_hardware_rejects_sibling_kvm_release_images(tmp_path: Path) -> None:
    context = _context(tmp_path)
    legacy = context.inputs.runtime_root / "releases" / "legacy-r2" / "images"
    legacy.mkdir(parents=True)
    (legacy / "system.img").write_bytes(b"legacy")
    context.avd_config.write_text(
        f"image.sysdir.1={context.release_root / 'images'}{os.sep}\n",
        encoding="utf-8",
    )
    (context.avd_directory / "hardware-qemu.ini").write_text(
        f"disk.systemPartition.initPath={legacy / 'system.img'}\n",
        encoding="utf-8",
    )
    with pytest.raises(KvmLiveCutoverError, match="non-candidate KVM runtime"):
        inspect_active_avd_configs(context)


def test_activation_revalidates_post_switch_manifest_before_adb_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    context = _context(tmp_path)
    expected = _post_switch_live(context)
    unit_receipt = {
        "self_sha256": "1" * 64,
        "run_as_user": "weipa",
        "run_as_uid": 1000,
        "user_home": str(tmp_path / "home-weipa"),
    }
    prepare_receipt = {
        "status": "prepared-offline",
        "release_id": context.release_id,
        "release_root": str(context.release_root),
        "unit": "alas-kvm.service",
        "unit_receipt_sha256": unit_receipt["self_sha256"],
        "first_boot_performed": False,
        "self_sha256": "2" * 64,
        "snapshot": {"path": str(context.archive_root / "snapshot")},
        "post_switch_live": expected,
    }
    monkeypatch.setattr(
        cutover,
        "verify_unit_receipt_and_effective_state",
        lambda *_args, **_kwargs: (unit_receipt, {}),
    )
    monkeypatch.setattr(cutover, "load_receipt", lambda *_args: prepare_receipt)
    monkeypatch.setattr(cutover, "verify_offline_avd_snapshot", lambda *_args: {})
    mutated: list[str] = []
    monkeypatch.setattr(
        cutover,
        "restart_dedicated_adb_server",
        lambda *_args, **_kwargs: mutated.append("adb") or {},
    )
    with context.avd_config.open("a", encoding="utf-8") as output:
        output.write("tampered=yes\n")

    with pytest.raises(KvmLiveCutoverError, match="changed after prepare"):
        activate_live_cutover(
            context,
            "alas-kvm.service",
            context.evidence_root / "unit.json",
            context.evidence_root / "prepare.json",
            context.evidence_root / "activation.json",
        )
    assert mutated == []


def test_nonzero_systemctl_start_is_boot_attempted_and_requires_recovery(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    context = _context(tmp_path)
    unit_receipt = {
        "self_sha256": "1" * 64,
        "run_as_user": "weipa",
        "run_as_uid": 1000,
        "user_home": str(tmp_path / "home-weipa"),
    }
    prepare_receipt = {
        "status": "prepared-offline",
        "release_id": context.release_id,
        "release_root": str(context.release_root),
        "unit": "alas-kvm.service",
        "unit_receipt_sha256": unit_receipt["self_sha256"],
        "first_boot_performed": False,
        "self_sha256": "2" * 64,
        "snapshot": {"path": str(context.archive_root / "snapshot")},
        "post_switch_live": _post_switch_live(context),
    }

    class Backend:
        def _require_release_avd(self) -> None:
            return None

    monkeypatch.setattr(
        cutover,
        "verify_unit_receipt_and_effective_state",
        lambda *_args, **_kwargs: (unit_receipt, {}),
    )
    monkeypatch.setattr(cutover, "load_receipt", lambda *_args: prepare_receipt)
    for name, value in {
        "verify_offline_avd_snapshot": lambda *_args, **_kwargs: {},
        "require_service_inactive": lambda *_args, **_kwargs: None,
        "require_ports_free": lambda *_args, **_kwargs: None,
        "require_inactive_cgroup_empty": lambda *_args, **_kwargs: None,
        "require_no_orphan_avd_users": lambda *_args, **_kwargs: None,
        "inspect_avd_external_storage_paths": lambda *_args, **_kwargs: [],
        "inspect_qcow_backing_chains": lambda *_args, **_kwargs: [],
    }.items():
        monkeypatch.setattr(cutover, name, value)
    monkeypatch.setattr(
        cutover, "backend_from_config", lambda *_args, **_kwargs: Backend()
    )
    monkeypatch.setattr(cutover, "KvmBackend", Backend)
    monkeypatch.setattr(
        cutover,
        "restart_dedicated_adb_server",
        lambda *_args, **_kwargs: {"port": 5043, "pid": 44},
    )
    stopped: list[str] = []
    monkeypatch.setattr(
        cutover,
        "_best_effort_stop",
        lambda unit, *_args, **_kwargs: stopped.append(unit) or [],
    )

    def runner(
        argv: Sequence[str], _timeout: float
    ) -> subprocess.CompletedProcess[str]:
        assert argv[:2] == ["systemctl", "start"]
        return _completed(argv, returncode=1, stderr="start failed after fork")

    receipt = context.evidence_root / "activation-start-failed.json"
    with pytest.raises(KvmLiveCutoverError, match="snapshot recovery is required"):
        activate_live_cutover(
            context,
            "alas-kvm.service",
            context.evidence_root / "unit.json",
            context.evidence_root / "prepare.json",
            receipt,
            runner=runner,
            created_epoch=123,
        )
    document = json.loads(receipt.read_text(encoding="utf-8"))
    assert document["boot_attempted"] is True
    assert document["first_boot_performed"] is True
    assert stopped == ["alas-kvm.service"]


def test_qemu_executable_must_come_from_candidate_release(tmp_path: Path) -> None:
    context = _context(tmp_path)
    cgroup_root = tmp_path / "cgroup"
    group = cgroup_root / "system.slice" / "alas-kvm.service"
    group.mkdir(parents=True)
    (group / "cgroup.procs").write_text("202\n", encoding="ascii")
    proc_root = tmp_path / "proc"
    process = proc_root / "202"
    (process / "fd").mkdir(parents=True)
    (process / "cmdline").write_bytes(b"qemu-system-x86_64\x00")
    (process / "stat").write_text(
        "202 (runtime) S " + " ".join(["0"] * 18 + ["2020"]) + "\n",
        encoding="ascii",
    )
    (process / "maps").write_text("", encoding="utf-8")
    outside = tmp_path / "outside" / "qemu-system-x86_64"
    outside.parent.mkdir()
    outside.write_bytes(b"qemu")
    links = {
        str(process / "exe"): str(outside),
        str(process / "cwd"): str(context.release_root),
    }

    def runner(
        argv: Sequence[str], _timeout: float
    ) -> subprocess.CompletedProcess[str]:
        return _completed(argv, stdout="/system.slice/alas-kvm.service\n")

    with pytest.raises(KvmLiveCutoverError, match="outside the candidate release"):
        scan_live_cgroup_dependencies(
            context,
            "alas-kvm.service",
            runner=runner,
            cgroup_root=cgroup_root,
            proc_root=proc_root,
            readlink=lambda path: links[str(path)],
        )


def test_recovery_plan_is_dry_run_and_never_overwrites_live_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    context = _context(tmp_path)
    old_fragment = tmp_path / "old.service"
    old_fragment.write_text("current-content\n", encoding="utf-8")
    archived_payload = b"archived-content\n"
    archive_path = context.evidence_root / "old-unit.json"
    archive = cutover._write_json_noreplace(
        archive_path,
        {
            "schema": cutover.PREVIOUS_UNIT_ARCHIVE_SCHEMA,
            "backend": "kvm",
            "status": "archived-before-mutation",
            "previous_unit": "old.service",
            "restore_policy": "dry-run-review-required-no-auto-overwrite",
            "files": [
                {
                    "path": str(old_fragment),
                    "sha256": cutover._sha256_bytes(archived_payload),
                    "content_base64": cutover.base64.b64encode(archived_payload).decode(
                        "ascii"
                    ),
                }
            ],
        },
    )
    prepare_path = context.evidence_root / "prepare-recovery.json"
    prepare = cutover._write_json_noreplace(
        prepare_path,
        {
            "schema": cutover.PREPARE_RECEIPT_SCHEMA,
            "release_id": context.release_id,
            "unit": "alas-kvm.service",
            "previous_unit": "old.service",
            "snapshot": {"path": str(context.archive_root / "snapshot")},
            "previous_unit_archive": {
                "path": str(archive_path),
                "self_sha256": archive["self_sha256"],
            },
        },
    )
    monkeypatch.setattr(cutover, "verify_offline_avd_snapshot", lambda *_args: {})
    marker = context.evidence_root / "phase-recovery.json"
    cutover._update_phase_marker(
        marker,
        context,
        "alas-kvm.service",
        "prepared",
        expected_phases={None},
        previous_unit="old.service",
        created_epoch=1,
    )
    output = context.evidence_root / "recovery-plan.json"
    plan = cutover.write_recovery_plan(
        context,
        "alas-kvm.service",
        "old.service",
        prepare_path,
        output,
        phase_marker_path=marker,
        created_epoch=1,
    )

    assert prepare["self_sha256"]
    assert plan["status"] == "dry-run-only-review-required"
    assert plan["automatic_restore_performed"] is False
    assert plan["automatic_overwrite_allowed"] is False
    assert plan["boot_attempted"] is False
    assert old_fragment.read_text(encoding="utf-8") == "current-content\n"
    assert plan["previous_unit_file_checks"][0]["current_matches_archive"] is False

    cutover._update_phase_marker(
        marker,
        context,
        "alas-kvm.service",
        "activating",
        expected_phases={"prepared"},
        previous_unit="old.service",
        created_epoch=2,
    )
    cutover._update_phase_marker(
        marker,
        context,
        "alas-kvm.service",
        "boot-attempted",
        expected_phases={"activating"},
        previous_unit="old.service",
        created_epoch=3,
    )
    boot_plan = cutover.write_recovery_plan(
        context,
        "alas-kvm.service",
        "old.service",
        prepare_path,
        context.evidence_root / "recovery-plan-after-boot-marker.json",
        phase_marker_path=marker,
        created_epoch=3,
    )
    assert boot_plan["boot_attempted"] is True
    assert boot_plan["phase_marker"]["boot_attempted_in_history"] is True


def test_receipt_boundary_rejects_changed_cgroup_membership(tmp_path: Path) -> None:
    cgroup_root = tmp_path / "cgroup"
    group = cgroup_root / "system.slice" / "alas-kvm.service"
    group.mkdir(parents=True)
    (group / "cgroup.procs").write_text("101\n202\n", encoding="ascii")

    def runner(
        argv: Sequence[str], _timeout: float
    ) -> subprocess.CompletedProcess[str]:
        if "--property=ActiveState" in argv:
            return _completed(argv, stdout="active\n")
        if "--property=ControlGroup" in argv:
            return _completed(argv, stdout="/system.slice/alas-kvm.service\n")
        raise AssertionError(argv)

    with pytest.raises(KvmLiveCutoverError, match="membership changed"):
        cutover.verify_live_cgroup_stability(
            "alas-kvm.service",
            {
                "control_group": "/system.slice/alas-kvm.service",
                "processes": [{"pid": 101, "start_time_ticks": "100"}],
            },
            runner=runner,
            cgroup_root=cgroup_root,
            proc_root=tmp_path / "proc",
        )


def test_prepare_failure_after_previous_archive_writes_recovery_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    context = _context(tmp_path)
    marker = context.evidence_root / "phase-prepare-failure.json"
    cutover._update_phase_marker(
        marker,
        context,
        "alas-kvm.service",
        "unit-installed",
        expected_phases={None},
        evidence={"unit_receipt_sha256": "1" * 64},
        created_epoch=1,
    )
    monkeypatch.setattr(
        cutover,
        "verify_unit_receipt_and_effective_state",
        lambda *_args, **_kwargs: (_unit_receipt_stub(tmp_path), {}),
    )
    monkeypatch.setattr(
        cutover,
        "archive_previous_systemd_unit",
        lambda *_args, **_kwargs: {
            "self_sha256": "2" * 64,
            "effective_state": {"User": "", "ActiveState": "active"},
        },
    )
    monkeypatch.setattr(
        cutover,
        "inspect_previous_unit_adb_listener",
        lambda *_args, **_kwargs: (None, UserIdentity("root", 0, Path("/root"))),
    )
    monkeypatch.setattr(
        cutover,
        "stop_disable_mask_previous_unit",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            KvmLiveCutoverError("mask failed")
        ),
    )
    receipt = context.evidence_root / "prepare-failed.json"
    with pytest.raises(KvmLiveCutoverError, match="mask failed"):
        prepare_live_cutover(
            context,
            "alas-kvm.service",
            context.evidence_root / "unit.json",
            context.archive_root / "snapshot-failed",
            receipt,
            previous_unit="old.service",
            previous_unit_archive_path=context.evidence_root / "old-unit.json",
            phase_marker_path=marker,
            created_epoch=1,
        )

    document = json.loads(receipt.read_text(encoding="utf-8"))
    assert document["status"] == "prepare-failed-recovery-required"
    assert document["boot_attempted"] is False
    assert document["previous_unit_archive"]["self_sha256"] == "2" * 64
    assert (
        cutover._load_phase_marker(marker)["phase"]
        == "prepare-failed-recovery-required"
    )
