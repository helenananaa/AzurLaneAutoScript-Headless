#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 2 || $# -gt 3 ]]; then
    echo "usage: $0 SOURCE_FILES_ROOT TARGET_FILES_ROOT [JOBS]" >&2
    exit 2
fi

source_root=$(realpath "$1")
target_root=$(realpath "$2")
jobs=${3:-8}
container=alas-redroid-wsl-projectlocal
docker_config=/home/helenanana/.config/alas-redroid/docker

[[ $source_root == /mnt/h/program/AzurLaneAutoScript-Headless-localdata/game-cn-9.7.10-files/files ]] || {
    echo "unexpected retained resource source: $source_root" >&2
    exit 1
}
[[ $target_root == /home/helenanana/.local/share/alas-redroid/projectlocal-data/media/0/Android/data/com.bilibili.azurlane/files ]] || {
    echo "unexpected Project resource target: $target_root" >&2
    exit 1
}
[[ $jobs =~ ^[1-8]$ ]] || {
    echo "JOBS must be between 1 and 8" >&2
    exit 1
}
[[ $(id -u) -eq 0 ]] || {
    echo "resource import requires root only for Android UID/GID restoration" >&2
    exit 1
}
[[ -d $source_root && -d $target_root ]] || {
    echo "resource source or target is missing" >&2
    exit 1
}

running=$(docker --config "$docker_config" container inspect \
    --format '{{.State.Running}}' "$container" 2>/dev/null || true)
[[ $running != true ]] || {
    echo "Project container must be stopped before importing resources" >&2
    exit 1
}

cd "$source_root"
find AssetBundles AssetBundles-more -mindepth 1 -maxdepth 1 -type d -print0 |
    xargs -0 -r -n 12 -P "$jobs" bash -c '
        set -o pipefail
        source_root=$1
        target_root=$2
        shift 2
        cd "$source_root"
        tar -cf - "$@" | tar -C "$target_root" -xf -
    ' _ "$source_root" "$target_root"

tar -cf - il2cpp | tar -C "$target_root" -xf -
find . -mindepth 1 -maxdepth 1 -type f -exec cp -f -- {} "$target_root"/ \;

chown -R 10067:1078 "$target_root"
find "$target_root" -type d -exec chmod 2770 {} +
find "$target_root" -type f -exec chmod 0660 {} +

read -r source_count source_bytes < <(
    find "$source_root" -type f -printf '%s\n' |
        awk '{count += 1; total += $1} END {printf "%d %.0f\n", count, total}'
)
read -r target_count target_bytes < <(
    find "$target_root" -type f -printf '%s\n' |
        awk '{count += 1; total += $1} END {printf "%d %.0f\n", count, total}'
)
printf 'source_files=%s target_files=%s source_bytes=%s target_bytes=%s owner=10067:1078\n' \
    "$source_count" "$target_count" "$source_bytes" "$target_bytes"
[[ $target_count -ge $source_count && $target_bytes -ge $source_bytes ]] || {
    echo "resource import inventory is incomplete" >&2
    exit 1
}
