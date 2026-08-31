#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 5 ]]; then
    echo "usage: $0 KVM_DOMAIN_JSON KVM_BUILD_PROFILE RELEASE_ID AVD_HOME AVD_NAME" >&2
    exit 2
fi

domain=$(realpath "$1")
profile=$(realpath "$2")
release_id=$3
avd_home=$(realpath -m "$4")
avd_name=$5
repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
python_bin=${ALAS_PYTHON:-python3}
export PYTHONPATH="$repo_root/python"
case "$avd_name" in
    *[!A-Za-z0-9._-]*|'')
        echo "invalid AVD name: $avd_name" >&2
        exit 2
        ;;
esac

release_root=$(
    "$python_bin" "$repo_root/scripts/python/manage_kvm_runtime_bundle.py" \
        verify \
        --domain "$domain" \
        --profile "$profile" \
        --release-id "$release_id"
)
release_root=$(realpath "$release_root")
image_root=$(realpath "$release_root/images")
[[ $image_root == "$release_root/images" ]] || {
    echo "verified KVM release image root escapes its release" >&2
    exit 1
}

for image in system.img vendor.img ramdisk.img kernel-ranchu; do
    [[ -f "$image_root/$image" ]] || {
        echo "required KVM release image is unavailable: $image_root/$image" >&2
        exit 1
    }
done

avd_dir="$avd_home/$avd_name.avd"
config="$avd_dir/config.ini"
descriptor="$avd_home/$avd_name.ini"
expected_sysdir="image.sysdir.1=$image_root/"
data_partition_size=48G
display_width=1280
display_height=720

render_config() {
    local input=$1
    local output=$2
    sed -E \
        -e "s|^image\.sysdir\.1=.*$|$expected_sysdir|" \
        -e "s|^disk\.dataPartition\.size=.*$|disk.dataPartition.size=$data_partition_size|" \
        -e "s|^skin\.name=.*$|skin.name=${display_width}x${display_height}|" \
        -e "s|^skin\.path=.*$|skin.path=${display_width}x${display_height}|" \
        -e '/^hw\.lcd\.width=/d' \
        -e '/^hw\.lcd\.height=/d' \
        -e '/^hw\.initialOrientation=/d' \
        -e '/^hw\.cpu\.arch=/d' \
        -e '/^kernel\.parameters=/d' \
        "$input" > "$output"
    printf '\nhw.lcd.width=%s\nhw.lcd.height=%s\nhw.initialOrientation=landscape\n' \
        "$display_width" "$display_height" >> "$output"
    printf 'hw.cpu.arch=x86_64\nkernel.parameters=androidboot.hardware=ranchu\n' \
        >> "$output"
}

if [[ -f "$config" ]]; then
    grep -Fqx "$expected_sysdir" "$config" || {
        echo "existing AVD points outside the selected runtime release: $config" >&2
        exit 1
    }
    [[ -f "$descriptor" ]] || {
        echo "existing AVD descriptor is missing: $descriptor" >&2
        exit 1
    }
    render_config "$config" "$config.tmp"
    if cmp -s "$config" "$config.tmp"; then
        rm -f "$config.tmp"
    else
        mv "$config.tmp" "$config"
    fi
    echo "$config"
    exit 0
fi

if [[ -e "$avd_dir" ]] && [[ -n "$(find "$avd_dir" -mindepth 1 -maxdepth 1 -print -quit)" ]]; then
    echo "refusing to replace a non-empty AVD directory: $avd_dir" >&2
    exit 1
fi

mkdir -p "$avd_dir"
template="$image_root/config.ini"
if [[ ! -f "$template" ]]; then
    echo "KVM image config template is unavailable: $template" >&2
    exit 1
fi

render_config "$template" "$config.tmp"
grep -Fqx "$expected_sysdir" "$config.tmp" || {
    rm -f "$config.tmp"
    echo "KVM image config has no image.sysdir.1 field" >&2
    exit 1
}
mv "$config.tmp" "$config"

if [[ -f "$image_root/advancedFeatures.ini" ]]; then
    cp "$image_root/advancedFeatures.ini" "$avd_dir/advancedFeatures.ini"
fi

printf 'avd.ini.encoding=UTF-8\npath=%s\ntarget=android-34\n' "$avd_dir" > "$descriptor.tmp"
mv "$descriptor.tmp" "$descriptor"
echo "$config"
