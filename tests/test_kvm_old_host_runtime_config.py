from __future__ import annotations

import json
from pathlib import Path, PurePosixPath


ROOT = Path(__file__).resolve().parents[1]
CONFIG = (
    ROOT
    / "integration"
    / "runtime"
    / "history"
    / "kvm.old-build-host.runtime-config.json"
)
RELEASE_ROOT = PurePosixPath(
    "/srv/android-runtime/kvm/alas-headless/releases/kvm-r75-x86_64-v2"
)


def test_old_build_host_runtime_retains_one_explicit_immutable_release() -> None:
    value = json.loads(CONFIG.read_text(encoding="utf-8"))
    assert PurePosixPath(value["runtime_release_root"]) == RELEASE_ROOT
    assert PurePosixPath(value["emulator"]) == RELEASE_ROOT / "emulator" / "emulator"
    assert PurePosixPath(value["emulator_check"]) == (
        RELEASE_ROOT / "emulator" / "emulator-check"
    )
    assert PurePosixPath(value["adb"]) == (
        RELEASE_ROOT / "sdk" / "platform-tools" / "adb"
    )
    assert PurePosixPath(value["sdk_root"]) == RELEASE_ROOT / "sdk"


def test_old_build_host_executables_never_point_to_mutable_build_state() -> None:
    value = json.loads(CONFIG.read_text(encoding="utf-8"))
    mutable_roots = (
        PurePosixPath("/srv/android-build/src"),
        PurePosixPath("/srv/android-cache/out"),
        PurePosixPath("/srv/android-runtime/kvm/alas-headless/sdk"),
        PurePosixPath("/srv/android-runtime/kvm/alas-headless/emulator"),
        PurePosixPath("/srv/android-runtime/kvm/alas-headless/current"),
    )
    for field in (
        "runtime_release_root",
        "emulator",
        "emulator_check",
        "adb",
        "sdk_root",
    ):
        path = PurePosixPath(value[field])
        assert all(root != path and root not in path.parents for root in mutable_roots)
        assert RELEASE_ROOT == path or RELEASE_ROOT in path.parents
