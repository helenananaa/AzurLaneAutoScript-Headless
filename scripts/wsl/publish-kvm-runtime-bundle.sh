#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 4 ]]; then
    echo "usage: $0 KVM_DOMAIN_JSON REDROID_DOMAIN_JSON KVM_BUILD_PROFILE RELEASE_ID" >&2
    exit 2
fi

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
python_bin=${ALAS_PYTHON:-python3}
export PYTHONPATH="$repo_root/python"

exec "$python_bin" "$repo_root/scripts/python/manage_kvm_runtime_bundle.py" \
    publish \
    --domain "$1" \
    --peer-domain "$2" \
    --profile "$3" \
    --release-id "$4"
