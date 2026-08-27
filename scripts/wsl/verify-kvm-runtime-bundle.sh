#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 3 ]]; then
    echo "usage: $0 KVM_DOMAIN_JSON KVM_BUILD_PROFILE RELEASE_ID" >&2
    exit 2
fi

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
python_bin=${ALAS_PYTHON:-python3}
export PYTHONPATH="$repo_root/python"

exec "$python_bin" "$repo_root/scripts/python/manage_kvm_runtime_bundle.py" \
    verify \
    --domain "$1" \
    --profile "$2" \
    --release-id "$3"
