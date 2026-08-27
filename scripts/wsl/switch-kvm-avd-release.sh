#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 7 ]]; then
    echo "usage: $0 switch|rollback KVM_DOMAIN_JSON KVM_BUILD_PROFILE RELEASE_ID AVD_HOME AVD_NAME EMULATOR_SERVICE" >&2
    exit 2
fi
case "$1" in
    switch) command=switch-avd ;;
    rollback) command=rollback-avd ;;
    *) echo "first argument must be switch or rollback" >&2; exit 2 ;;
esac

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
python_bin=${ALAS_PYTHON:-python3}
export PYTHONPATH="$repo_root/python"

exec "$python_bin" "$repo_root/scripts/python/manage_kvm_runtime_bundle.py" \
    "$command" \
    --domain "$2" \
    --profile "$3" \
    --release-id "$4" \
    --avd-home "$5" \
    --avd-name "$6" \
    --emulator-service "$7"
