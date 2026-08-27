#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 6 ]]; then
    echo "usage: $0 KVM_DOMAIN_JSON KVM_BUILD_PROFILE RELEASE_ID RUNTIME_CONFIG ANGLE_APK GAME_PACKAGE" >&2
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
for name in ("adb", "adb_server_port", "transport_serial"):
    print(value[name])
PY
)
adb=${values[0]}
adb_server_port=${values[1]}
transport_serial=${values[2]}
angle_apk=$(realpath "$5")
game_package=$6

[[ -x "$adb" ]] || {
    echo "adb is not executable: $adb" >&2
    exit 1
}
[[ -f "$angle_apk" ]] || {
    echo "ANGLE observer APK is unavailable: $angle_apk" >&2
    exit 1
}
[[ "$game_package" =~ ^[A-Za-z0-9_]+([.][A-Za-z0-9_]+)+$ ]] || {
    echo "invalid game package: $game_package" >&2
    exit 2
}

adb_command=("$adb" -P "$adb_server_port")

"${adb_command[@]}" connect "$transport_serial" >/dev/null 2>&1 || true
"${adb_command[@]}" -s "$transport_serial" wait-for-device

# Android package visibility otherwise makes GraphicsEnvironment report the
# installed debug provider as "not installed" from inside the game process.
"${adb_command[@]}" -s "$transport_serial" install -r -d --force-queryable "$angle_apk"
"${adb_command[@]}" -s "$transport_serial" shell settings put global angle_debug_package org.chromium.angle
"${adb_command[@]}" -s "$transport_serial" shell settings put global angle_gl_driver_selection_pkgs "$game_package"
"${adb_command[@]}" -s "$transport_serial" shell settings put global angle_gl_driver_selection_values angle
"${adb_command[@]}" -s "$transport_serial" shell settings put global show_angle_in_use_dialog_box 0
"${adb_command[@]}" -s "$transport_serial" shell pm path org.chromium.angle
