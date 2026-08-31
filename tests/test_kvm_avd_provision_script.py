from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "wsl" / "provision-kvm-avd.sh"


def test_kvm_avd_provision_is_isolated_and_preserves_userdata():
    text = SCRIPT.read_text(encoding="utf-8")
    assert 'avd_dir="$avd_home/$avd_name.avd"' in text
    assert "userdata-qemu" not in text
    assert "rm -rf" not in text
    assert "refusing to replace a non-empty AVD directory" in text
    assert "existing AVD points outside the selected runtime release" in text


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
