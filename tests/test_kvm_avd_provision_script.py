from pathlib import Path
import os
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "wsl" / "provision-kvm-avd.sh"


@pytest.mark.skipif(os.name == "nt", reason="executes the Linux provision entrypoint")
@pytest.mark.parametrize("template", [None, "hw.ramSize=3072\n", "existing"])
def test_provision_failure_leaves_no_avd_and_existing_userdata_survives(tmp_path, template):
    release = tmp_path / "release"
    images = release / "images"
    images.mkdir(parents=True)
    for name in ("system.img", "vendor.img", "ramdisk.img", "kernel-ranchu"):
        (images / name).touch()
    if template is not None and template != "existing":
        (images / "config.ini").write_text(template)
    # Isolate provisioning from expensive bundle hashing; real release/boot
    # validation is separate. The fake verifier only returns this fixture path.
    verifier = tmp_path / "verifier"
    verifier.write_text('#!/bin/sh\nprintf "%s\\n" "$TEST_RELEASE"\n')
    verifier.chmod(0o755)
    domain, profile = tmp_path / "domain.json", tmp_path / "profile.json"
    domain.touch()
    profile.touch()
    avd_home = tmp_path / "avd"
    avd = avd_home / "sample.avd"
    if template == "existing":
        avd.mkdir(parents=True)
        (avd / "config.ini").write_text(f'image.sysdir.1={images}/\n')
        (avd_home / "sample.ini").touch()
        (avd / "userdata-qemu.img").write_bytes(b"retained user data")
    result = subprocess.run(
        ["bash", str(SCRIPT), str(domain), str(profile), "sample-release",
         str(avd_home), "sample"],
        env={**os.environ, "ALAS_PYTHON": str(verifier), "TEST_RELEASE": str(release)},
        text=True, capture_output=True, timeout=10,
    )
    if template == "existing":
        assert result.returncode == 0, result.stderr
        assert (avd / "userdata-qemu.img").read_bytes() == b"retained user data"
    else:
        assert result.returncode != 0
        assert "KVM image config" in result.stderr
        assert not avd.exists()
        assert not avd_home.exists()


def test_kvm_avd_provision_is_isolated_and_preserves_userdata():
    text = SCRIPT.read_text(encoding="utf-8")
    assert 'avd_dir="$avd_home/$avd_name.avd"' in text
    assert "rm -rf" not in text
    assert "refusing to replace a non-empty AVD directory" in text
    assert "existing AVD points outside the selected runtime release" in text
    assert "refusing to replace existing KVM userdata" in text
    existing = text.index('if [[ -f "$config" ]]')
    existing_exit = text.index("exit 0", existing)
    userdata_create = text.index('truncate -s "$data_partition_size"')
    assert existing < existing_exit < userdata_create


def test_kvm_avd_provision_creates_checked_empty_ext4_userdata():
    text = SCRIPT.read_text(encoding="utf-8")
    assert 'mkfs_ext4="$release_root/emulator/bin64/mkfs.ext4"' in text
    assert 'e2fsck="$release_root/emulator/bin64/e2fsck"' in text
    assert "integration/runtime/kvm-userdata-mke2fs.conf" in text
    assert 'truncate -s "$data_partition_size" "$userdata_stage"' in text
    assert '"$mkfs_ext4" -F -t ext4 -I 512 -L data -m 0 "$userdata_stage"' in text
    assert '"$e2fsck" -fn "$userdata_stage"' in text
    assert 'chmod 0600 "$userdata_stage"' in text
    assert 'mv "$userdata_stage" "$userdata"' in text
    create = text.index('truncate -s "$data_partition_size"')
    assert text.index('template="$image_root/config.ini"') < create
    assert text.index('KVM image config has no image.sysdir.1 field') < create


def test_kvm_avd_provision_binds_real_goldfish_images():
    text = SCRIPT.read_text(encoding="utf-8")
    for image in ("system.img", "vendor.img", "ramdisk.img", "kernel-ranchu"):
        assert image in text
    assert "image.sysdir.1=" in text
    assert "hw.cpu.arch=x86_64" in text
    assert "androidboot.hardware=ranchu" in text
    assert "data_partition_size=48G" in text
    assert "guest_ram_mib=3072" in text
    assert "hw.ramSize=%s" in text
    assert "display_width=960" in text
    assert "display_height=540" in text
    assert "display_density=180" in text
    assert "hw.lcd.density=%s" in text
    assert "hw.initialOrientation=landscape" in text
    assert 'render_config "$config" "$config.tmp"' in text
    assert "config.ini" in text


def test_kvm_avd_provision_accepts_only_a_verified_immutable_release():
    text = SCRIPT.read_text(encoding="utf-8")
    assert "KVM_DOMAIN_JSON KVM_BUILD_PROFILE RELEASE_ID" in text
    assert "manage_kvm_runtime_bundle.py" in text
    assert "verify" in text
    assert 'image_root=$(realpath "$release_root/images")' in text
    assert 'expected_sysdir="image.sysdir.1=$image_root/"' in text
    assert "PRODUCT_OUT" not in text
    assert "product_out" not in text
