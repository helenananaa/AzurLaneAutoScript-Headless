from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / "scripts" / "wsl" / "run-kvm-avd.sh"
INSTALL = ROOT / "scripts" / "wsl" / "install-kvm-angle-observer.sh"


def test_kvm_runtime_disables_crashing_emulator_vulkan_path():
    text = RUN.read_text(encoding="utf-8")
    assert "-gpu swiftshader_indirect" in text
    assert "-feature -Vulkan" in text
    assert "-grpc 0" in text
    assert "-grpc-use-jwt" in text
    assert "-no-snapshot" in text
    assert "-no-boot-anim" in text
    assert 'exec "$emulator"' in text
    assert 'export ANDROID_ADB_SERVER_PORT="$adb_server_port"' in text
    assert 'platform_tools="${sdk_root}/platform-tools"' in text
    assert '[[ -x "$platform_tools/adb" ]]' in text
    assert 'export PATH="$platform_tools${PATH:+:$PATH}"' in text
    assert text.index('export PATH="$platform_tools${PATH:+:$PATH}"') < text.index(
        'exec "$emulator"'
    )
    assert "resolve_kvm_runtime_release_config.py" in text
    assert "KVM_DOMAIN_JSON KVM_BUILD_PROFILE RELEASE_ID RUNTIME_CONFIG" in text
    assert "usage: $0 EMULATOR" not in text


def test_kvm_angle_observer_is_queryable_before_routing():
    text = INSTALL.read_text(encoding="utf-8")
    install = text.index("--force-queryable")
    routing = text.index("angle_debug_package")
    assert install < routing
    assert "install -r -d --force-queryable" in text
    assert "angle_gl_driver_selection_pkgs" in text
    assert "angle_gl_driver_selection_values angle" in text
    assert 'adb_command=("$adb" -P "$adb_server_port")' in text
    assert "resolve_kvm_runtime_release_config.py" in text
    assert "KVM_DOMAIN_JSON KVM_BUILD_PROFILE RELEASE_ID RUNTIME_CONFIG" in text
    assert "usage: $0 ADB " not in text
