#!/usr/bin/env bash
set -euo pipefail

usage() {
    echo "USAGE: $0 SYSTEM_IMG VENDOR_IMG ABI SOURCE_LOCK_SHA256 FINGERPRINT SOURCE_DATE_EPOCH EXPECTED_LIBEGL EXPECTED_PASTEL OUTPUT_OCI OUTPUT_IDENTITY OUTPUT_RUNTIME_COMPONENTS" >&2
    exit 2
}
[[ $# -eq 11 ]] || usage
[[ $EUID -eq 0 ]] || { echo "root is required for read-only image mounts" >&2; exit 1; }

system_img=$(realpath "$1")
vendor_img=$(realpath "$2")
abi=$3
source_lock_sha256=$4
fingerprint=$5
source_date_epoch=$6
expected_libegl=$(realpath "$7")
expected_pastel=$(realpath "$8")
output_oci=$(realpath -m "$9")
output_identity=$(realpath -m "${10}")
output_runtime_components=$(realpath -m "${11}")
repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
[[ -f $system_img && -f $vendor_img ]] || { echo "system/vendor image missing" >&2; exit 1; }
[[ -f $expected_libegl && -f $expected_pastel ]] || {
    echo "expected product runtime component missing" >&2; exit 1;
}
[[ ! -e $output_oci && ! -e $output_identity && ! -e $output_runtime_components ]] || {
    echo "output already exists" >&2; exit 1;
}

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

# A target-level incremental build can update product output without rebuilding
# system.img/vendor.img. Refuse to package unless both partition images contain
# byte-identical copies of the latest reviewed runtime components.
mkdir -p "$(dirname "$output_runtime_components")"
set +e
PYTHONPATH="$repo_root/python" python3 \
    "$repo_root/scripts/python/verify_redroid_partition_runtime_components.py" \
    --system-root "$system_mount" --vendor-root "$vendor_mount" \
    --expected-libegl "$expected_libegl" --expected-pastel "$expected_pastel" \
    --abi "$abi" --source-lock-sha256 "$source_lock_sha256" \
    --output "$output_runtime_components"
runtime_component_rc=$?
set -e
if [[ ${SUDO_UID:-} =~ ^[0-9]+$ && ${SUDO_GID:-} =~ ^[0-9]+$ ]]; then
    chown "$SUDO_UID:$SUDO_GID" "$output_runtime_components"
fi
[[ $runtime_component_rc -eq 0 ]] || {
    echo "partition runtime components differ from product output; rebuild systemimage/vendorimage before packaging" >&2
    exit "$runtime_component_rc"
}

# containerd resolves the OCI process user/group against rootfs /etc while it
# creates a fresh spec.  Android partition images use root-level absolute
# links such as /etc -> /system/etc; snapshotter-safe extraction needs the
# equivalent root-relative target (etc -> system/etc).  Only rewrite absolute
# links at the root.  Nested absolute links keep their Android semantics.
system_excludes=(--exclude='./vendor')
root_absolute_symlinks=()
while IFS= read -r -d '' path; do
    target=$(readlink -- "$path")
    [[ $target == /* ]] || continue
    name=${path#"$system_mount"/}
    [[ -n $name && $name != */* && $target != / ]] || {
        echo "unsafe root-level Android symlink: $name -> $target" >&2
        exit 1
    }
    case "/${target#/}/" in
        */../*)
            echo "root-level Android symlink contains parent traversal: $name -> $target" >&2
            exit 1
            ;;
    esac
    system_excludes+=("--exclude=./$name")
    root_absolute_symlinks+=("./$name")
done < <(find "$system_mount" -mindepth 1 -maxdepth 1 -type l -print0 | sort -z)

tar --sort=name --format=pax --pax-option=delete=atime,delete=ctime \
    --mtime="@$source_date_epoch" \
    --numeric-owner --xattrs --xattrs-include='*' \
    -cf "$layer" -C "$prefix" vendor
tar --sort=name --format=pax --pax-option=delete=atime,delete=ctime \
    --mtime="@$source_date_epoch" \
    --numeric-owner --xattrs --xattrs-include='*' \
    "${system_excludes[@]}" -rf "$layer" -C "$system_mount" .
if ((${#root_absolute_symlinks[@]})); then
    tar --sort=name --format=pax --pax-option=delete=atime,delete=ctime \
        --mtime="@$source_date_epoch" \
        --numeric-owner --xattrs --xattrs-include='*' \
        --transform='flags=s;s|^/||' \
        -rf "$layer" -C "$system_mount" "${root_absolute_symlinks[@]}"
fi
tar --sort=name --format=pax --pax-option=delete=atime,delete=ctime \
    --mtime="@$source_date_epoch" \
    --numeric-owner --xattrs --xattrs-include='*' \
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
