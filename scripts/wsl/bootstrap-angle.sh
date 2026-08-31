#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
revision="$(tr -d '\r\n' < "${repo_root}/ANGLE_REVISION")"

angle_backend="${ALAS_ANGLE_BACKEND:-kvm}"
case "${angle_backend}" in
  kvm)
    default_angle_workspace="${HOME}/src/alas-headless-angle-kvm"
    default_depot_tools_dir="${HOME}/src/depot_tools-kvm"
    ;;
  redroid)
    default_angle_workspace="${HOME}/src/alas-headless-angle-redroid"
    default_depot_tools_dir="${HOME}/src/depot_tools-redroid"
    ;;
  *) echo "Unsupported ALAS_ANGLE_BACKEND: ${angle_backend} (expected kvm or redroid)" >&2; exit 2 ;;
esac
angle_workspace="${ALAS_ANGLE_WORKSPACE:-${default_angle_workspace}}"
depot_tools_dir="${ALAS_DEPOT_TOOLS_DIR:-${default_depot_tools_dir}}"
angle_dir="${angle_workspace}/angle"

mkdir -p "$(dirname "${depot_tools_dir}")" "${angle_workspace}"

if [[ ! -d "${depot_tools_dir}/.git" ]]; then
  git clone https://chromium.googlesource.com/chromium/tools/depot_tools.git "${depot_tools_dir}"
fi

export PATH="${depot_tools_dir}:${PATH}"

if [[ ! -d "${angle_dir}/.git" ]]; then
  git clone --filter=blob:none https://chromium.googlesource.com/angle/angle "${angle_dir}"
fi

git -C "${angle_dir}" fetch --no-tags origin "${revision}"
git -C "${angle_dir}" checkout --detach "${revision}"

cd "${angle_dir}"
if [[ ! -f .gclient ]]; then
  python3 scripts/bootstrap.py
fi

gclient sync -D --no-history --revision "angle@${revision}"

actual_revision="$(git rev-parse HEAD)"
if [[ "${actual_revision}" != "${revision}" ]]; then
  echo "ANGLE revision mismatch: expected ${revision}, got ${actual_revision}" >&2
  exit 1
fi

echo "ANGLE ready at ${angle_dir} (${actual_revision})"
