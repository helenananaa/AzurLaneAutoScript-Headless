#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$script_dir/../.." && pwd)"
export PYTHONPATH="$repo_root/python${PYTHONPATH:+:$PYTHONPATH}"
exec python3 "$repo_root/scripts/python/probe_redroid_arm64_host.py"
