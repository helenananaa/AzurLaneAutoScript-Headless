#!/usr/bin/env bash
set -euo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
python_bin=${ALAS_PYTHON:-python3}
export PYTHONPATH="$repo_root/python"

exec "$python_bin" "$repo_root/scripts/python/manage_kvm_live_cutover.py" "$@"
