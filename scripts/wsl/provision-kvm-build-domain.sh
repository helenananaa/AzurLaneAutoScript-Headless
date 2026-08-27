#!/usr/bin/env bash
set -euo pipefail

usage() {
    echo "USAGE: $0 KVM_DOMAIN_JSON REDROID_DOMAIN_JSON" >&2
    exit 2
}

[[ $# -eq 2 ]] || usage
domain=$(realpath "$1")
peer_domain=$(realpath "$2")
repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
python_bin=${ALAS_PYTHON:-python3}
export PYTHONPATH="$repo_root/python"
"$python_bin" "$repo_root/scripts/python/validate_android_build_domain.py" \
    --domain "$domain" --expected-backend kvm >/dev/null
"$python_bin" "$repo_root/scripts/python/validate_android_build_domain.py" \
    --domain "$peer_domain" --expected-backend redroid >/dev/null

mapfile -t values < <("$python_bin" - "$domain" <<'PY'
import json, sys
value = json.load(open(sys.argv[1], encoding="utf-8"))
if value["backend"] != "kvm":
    raise SystemExit("KVM provisioner requires a kvm build domain")
for name, path in value["paths"].items():
    print(name + "\t" + path)
PY
)

declare -A paths=()
for entry in "${values[@]}"; do
    name=${entry%%$'\t'*}
    path=${entry#*$'\t'}
    paths["$name"]=$path
done

for name in source_root repo_metadata_root output_root ccache_root build_home \
        temp_root runtime_root archive_root evidence_root apk_archive; do
    mkdir -p "${paths[$name]}"
done

"$python_bin" - "$domain" "$peer_domain" <<'PY'
from pathlib import Path
import sys

from alas_headless.android_build_domain import AndroidBuildDomain
from alas_headless.android_build_domain_migration import initialize_owner_root
from alas_headless.android_build_domain_migration import (
    require_actual_domain_pair_isolated,
)

domain = AndroidBuildDomain.from_path(Path(sys.argv[1]), expected_backend="kvm")
peer = AndroidBuildDomain.from_path(Path(sys.argv[2]), expected_backend="redroid")
for root_kind in ("output", "archive"):
    initialize_owner_root(domain, backend="kvm", root_kind=root_kind)
require_actual_domain_pair_isolated(peer, domain)
PY

source_repo_link="${paths[source_root]}/.repo"
repo_metadata=${paths[repo_metadata_root]}
if [[ -L $source_repo_link ]]; then
    [[ $(realpath "$source_repo_link") == "$(realpath "$repo_metadata")" ]] || {
        echo "KVM source .repo points outside its domain metadata root" >&2
        exit 1
    }
elif [[ -e $source_repo_link ]]; then
    [[ -d $source_repo_link ]] || {
        echo "KVM source .repo is not a directory" >&2
        exit 1
    }
    [[ $(stat -Lc '%d:%i' "$source_repo_link") == \
       "$(stat -Lc '%d:%i' "$repo_metadata")" ]] || {
        echo "KVM source .repo is neither the owned symlink nor its bind mount" >&2
        exit 1
    }
else
    ln -s "$repo_metadata" "$source_repo_link"
fi

echo "KVM build domain is provisioned without changing existing build state"
