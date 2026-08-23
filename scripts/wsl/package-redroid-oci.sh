#!/usr/bin/env bash
set -euo pipefail

usage() {
    echo "USAGE: $0 SYSTEM_IMG VENDOR_IMG ABI SOURCE_LOCK_SHA256 FINGERPRINT SOURCE_DATE_EPOCH OUTPUT_OCI OUTPUT_IDENTITY" >&2
    exit 2
}
[[ $# -eq 8 ]] || usage
[[ $EUID -eq 0 ]] || { echo "root is required for read-only image mounts" >&2; exit 1; }

system_img=$(realpath "$1")
vendor_img=$(realpath "$2")
abi=$3
source_lock_sha256=$4
fingerprint=$5
source_date_epoch=$6
output_oci=$(realpath -m "$7")
output_identity=$(realpath -m "$8")
repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
[[ -f $system_img && -f $vendor_img ]] || { echo "system/vendor image missing" >&2; exit 1; }
[[ ! -e $output_oci && ! -e $output_identity ]] || { echo "output already exists" >&2; exit 1; }

work=$(mktemp -d /tmp/alas-redroid-oci.XXXXXX)
work=$(realpath "$work")
[[ $work == /tmp/alas-redroid-oci.* ]] || { echo "unsafe work directory" >&2; exit 1; }
system_mount="$work/system"
vendor_mount="$work/vendor"
layer="$work/rootfs.tar"
prefix="$work/prefix"
mkdir -p "$system_mount" "$vendor_mount" "$prefix/vendor"
mounted_system=false
mounted_vendor=false
cleanup() {
    $mounted_vendor && umount "$vendor_mount" 2>/dev/null || true
    $mounted_system && umount "$system_mount" 2>/dev/null || true
    if [[ -n ${work:-} && $work == /tmp/alas-redroid-oci.* && -d $work ]]; then
        rm -rf -- "$work"
    fi
}
trap cleanup EXIT

mount -o loop,ro "$system_img" "$system_mount"
mounted_system=true
mount -o loop,ro "$vendor_img" "$vendor_mount"
mounted_vendor=true

tar --sort=name --format=pax --pax-option=delete=atime,delete=ctime \
    --mtime="@$source_date_epoch" \
    --numeric-owner --owner=0 --group=0 --xattrs --xattrs-include='*' \
    -cf "$layer" -C "$prefix" vendor
tar --sort=name --format=pax --pax-option=delete=atime,delete=ctime \
    --mtime="@$source_date_epoch" \
    --numeric-owner --owner=0 --group=0 --xattrs --xattrs-include='*' \
    --exclude='./vendor' -rf "$layer" -C "$system_mount" .
tar --sort=name --format=pax --pax-option=delete=atime,delete=ctime \
    --mtime="@$source_date_epoch" \
    --numeric-owner --owner=0 --group=0 --xattrs --xattrs-include='*' \
    --transform='s|^\.$|./vendor|;s|^\./|./vendor/|' \
    -rf "$layer" -C "$vendor_mount" .
mkdir -p "$(dirname "$output_oci")" "$(dirname "$output_identity")"
PYTHONPATH="$repo_root/python" python3 "$repo_root/scripts/python/create_redroid_oci_archive.py" \
    --rootfs-layer "$layer" --abi "$abi" \
    --source-lock-sha256 "$source_lock_sha256" \
    --build-fingerprint "$fingerprint" --source-date-epoch "$source_date_epoch" \
    --output "$output_oci" --identity-output "$output_identity"
if [[ ${SUDO_UID:-} =~ ^[0-9]+$ && ${SUDO_GID:-} =~ ^[0-9]+$ ]]; then
    chown "$SUDO_UID:$SUDO_GID" "$output_oci" "$output_identity"
fi
