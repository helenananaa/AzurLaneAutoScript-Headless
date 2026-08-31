#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 4 ]]; then
    echo "usage: $0 KVM_DOMAIN_JSON KVM_BUILD_PROFILE RELEASE_ID RUNTIME_CONFIG" >&2
    exit 2
fi

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
python_bin=${ALAS_PYTHON:-python3}
export PYTHONPATH="$repo_root/python"
resolved=$(
    "$python_bin" "$repo_root/scripts/python/resolve_kvm_runtime_release_config.py" \
        --domain "$1" --profile "$2" --release-id "$3" --runtime-config "$4"
)
mapfile -t values < <("$python_bin" - "$resolved" <<'PY'
import json, sys
value = json.loads(sys.argv[1])
for name in ("emulator", "avd_home", "sdk_root", "avd_name", "console_port", "adb_server_port"):
    print(value[name])
PY
)
emulator=${values[0]}
avd_home=${values[1]}
sdk_root=${values[2]}
avd_name=${values[3]}
console_port=${values[4]}
adb_server_port=${values[5]}
platform_tools="${sdk_root}/platform-tools"

[[ -x "$emulator" ]] || {
    echo "emulator is not executable: $emulator" >&2
    exit 1
}
[[ -x "$platform_tools/adb" ]] || {
    echo "release adb is not executable: $platform_tools/adb" >&2
    exit 1
}
export ANDROID_AVD_HOME="$avd_home"
export ANDROID_SDK_ROOT="$sdk_root"
export ANDROID_ADB_SERVER_PORT="$adb_server_port"
export PATH="$platform_tools${PATH:+:$PATH}"

# Emulator 34.2.7 crashes in goldfish_vk while the game queries Vulkan
# features.  The game itself is routed through the separately installed ANGLE
# NULL provider, so guest Vulkan is unnecessary for this KVM runtime.
exec "$emulator" \
    -avd "$avd_name" \
    -no-window \
    -no-audio \
    -no-snapshot \
    -no-snapshot-save \
    -no-metrics \
    -gpu swiftshader_indirect \
    -feature -Vulkan \
    -port "$console_port"
