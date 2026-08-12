#!/usr/bin/env bash
set -euo pipefail

usage() {
    echo "usage: $0 [--role userdata|metadata] --image ABS_PATH --size-mib N --mount ABS_PATH --output ABS_PATH" >&2
    exit 2
}

image=""
size_mib=""
mountpoint=""
output=""
role="userdata"
while (($#)); do
    case "$1" in
        --image) image="${2:-}"; shift 2 ;;
        --size-mib) size_mib="${2:-}"; shift 2 ;;
        --mount) mountpoint="${2:-}"; shift 2 ;;
        --output) output="${2:-}"; shift 2 ;;
        --role) role="${2:-}"; shift 2 ;;
        *) usage ;;
    esac
done

[[ $EUID -eq 0 ]] || { echo "must run as root" >&2; exit 1; }
[[ "$image" == /* && "$mountpoint" == /* && "$output" == /* ]] || usage
[[ "$role" == userdata || "$role" == metadata ]] || { echo "invalid --role" >&2; exit 1; }
[[ "$size_mib" =~ ^[0-9]+$ ]] && ((size_mib >= 256)) || {
    echo "--size-mib must be an integer >= 256" >&2; exit 1;
}
[[ ! -e "$image" ]] || { echo "refusing to overwrite existing image: $image" >&2; exit 1; }
[[ ! -e "$output" ]] || { echo "refusing to overwrite evidence: $output" >&2; exit 1; }
case "$mountpoint" in
    /|/data|/var/lib/redroid/data) echo "refusing unsafe or production mountpoint" >&2; exit 1 ;;
esac
case "$image" in
    /var/lib/redroid/data|/var/lib/redroid/data/*)
        echo "refusing image inside production userdata" >&2; exit 1 ;;
esac
for command_name in truncate mkfs.ext4 losetup mount umount find findmnt tune2fs awk python3; do
    command -v "$command_name" >/dev/null || { echo "missing command: $command_name" >&2; exit 1; }
done

mkdir -p "$(dirname "$image")" "$(dirname "$output")"
if [[ -e "$mountpoint" ]]; then
    [[ -d "$mountpoint" ]] || { echo "mountpoint is not a directory" >&2; exit 1; }
    [[ -z "$(find "$mountpoint" -mindepth 1 -maxdepth 1 -print -quit)" ]] || {
        echo "mountpoint must be empty" >&2; exit 1;
    }
else
    mkdir -p "$mountpoint"
fi
findmnt --mountpoint "$mountpoint" >/dev/null 2>&1 && {
    echo "mountpoint is already mounted" >&2; exit 1;
}

image_created=false
loopdev=""
mounted=false
cleanup() {
    status=$?
    if [[ "$mounted" == true ]]; then umount "$mountpoint" || true; fi
    if [[ -n "$loopdev" ]]; then losetup -d "$loopdev" || true; fi
    if ((status != 0)) && [[ "$image_created" == true ]]; then rm -f -- "$image"; fi
    exit "$status"
}
trap cleanup EXIT

truncate -s "${size_mib}M" "$image"
image_created=true
mkfs.ext4 -q -F -L "alas_${role}" -O encrypt,metadata_csum,64bit "$image"
loopdev="$(losetup --find --show "$image")"
root_source="$(findmnt -no SOURCE /)"
[[ "$loopdev" != "$root_source" ]] || { echo "refusing host root device" >&2; exit 1; }
mount -o rw,nodev,nosuid "$loopdev" "$mountpoint"
mounted=true
filesystem_type="$(findmnt -no FSTYPE --mountpoint "$mountpoint")"
mount_options="$(findmnt -no OPTIONS --mountpoint "$mountpoint")"
filesystem_uuid="$(tune2fs -l "$loopdev" | awk -F: '/^Filesystem UUID:/ {gsub(/^[ \t]+/, "", $2); print $2}')"
features="$(tune2fs -l "$loopdev" | awk -F: '/^Filesystem features:/ {gsub(/^[ \t]+/, "", $2); print $2}')"

PROBE_IMAGE="$image" PROBE_SIZE_MIB="$size_mib" PROBE_MOUNT="$mountpoint" \
PROBE_OUTPUT="$output" PROBE_LOOP="$loopdev" PROBE_ROOT="$root_source" \
PROBE_FSTYPE="$filesystem_type" PROBE_OPTIONS="$mount_options" \
PROBE_UUID="$filesystem_uuid" PROBE_FEATURES="$features" \
PROBE_ROLE="$role" \
python3 - <<'PY'
import json
import os
from pathlib import Path

probe = {
    "schema": "alas-headless.redroid-userdata-volume-probe/v1",
    "scope": "empty-lab-volume",
    "role": os.environ["PROBE_ROLE"],
    "created_new": True,
    "backing_file_existed_before": False,
    "production_data_touched": False,
    "backing_file": os.environ["PROBE_IMAGE"],
    "provisioned_size_mib": int(os.environ["PROBE_SIZE_MIB"]),
    "block_device": os.environ["PROBE_LOOP"],
    "root_source": os.environ["PROBE_ROOT"],
    "mountpoint": os.environ["PROBE_MOUNT"],
    "filesystem_type": os.environ["PROBE_FSTYPE"],
    "filesystem_uuid": os.environ["PROBE_UUID"],
    "filesystem_features": os.environ["PROBE_FEATURES"].split(),
    "mount_options": os.environ["PROBE_OPTIONS"].split(","),
    "mounted_read_write": "rw" in os.environ["PROBE_OPTIONS"].split(","),
    "empty_before_mount": True,
    "android_fbe_claimed": False,
}
Path(os.environ["PROBE_OUTPUT"]).write_text(
    json.dumps(probe, indent=2, sort_keys=True) + "\n", encoding="utf-8"
)
PY

echo "$output"
