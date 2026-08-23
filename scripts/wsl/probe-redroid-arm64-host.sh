#!/usr/bin/env bash
set -euo pipefail

failures=()
arch="$(uname -m)"
[[ "$arch" == "aarch64" || "$arch" == "arm64" ]] || failures+=("host-architecture-is-not-arm64")
command -v docker >/dev/null 2>&1 || failures+=("docker-cli-missing")
[[ -f /sys/fs/cgroup/cgroup.controllers ]] || failures+=("cgroup-v2-missing")
if [[ ! -d /dev/binderfs && ! -e /dev/binder && ! -e /dev/hwbinder && ! -e /dev/vndbinder ]]; then
  failures+=("binder-device-or-binderfs-missing")
fi
image="${ALAS_REDROID_IMAGE:-}"
[[ "$image" == *@sha256:* ]] || failures+=("ALAS_REDROID_IMAGE-must-use-content-digest")

outcome="pass"
if ((${#failures[@]})); then
  outcome="blocked"
fi
printf '{\n'
printf '  "schema": "alas-headless.redroid-arm64-host-probe/v1",\n'
printf '  "outcome": "%s",\n' "$outcome"
printf '  "host_architecture": "%s",\n' "$arch"
printf '  "image": "%s",\n' "$image"
printf '  "failures": ['
for index in "${!failures[@]}"; do
  (( index == 0 )) || printf ', '
  printf '"%s"' "${failures[$index]}"
done
printf ']\n}\n'
[[ "$outcome" == "pass" ]]
