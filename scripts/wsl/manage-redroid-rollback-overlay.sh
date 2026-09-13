#!/usr/bin/env bash
set -euo pipefail

# Only mounts and removes this run's scratch overlays. Never copies, restores,
# chmods or deletes the retained Project userdata used as the lower directory.
[[ $# == 3 ]] || { echo 'usage: overlay-helper ACTION SOURCE_DATA LAB_ROOT' >&2; exit 2; }
action=$1
source_data=$(realpath -e -- "$2")
lab_root=$(realpath -m -- "$3")
expected_parent=$(realpath -m -- "$(dirname -- "$source_data")/rollback-labs")
[[ -d $source_data && $source_data != / ]] || exit 2
[[ $(dirname -- "$lab_root") == "$expected_parent" ]] || { echo 'lab must be a sibling rollback-labs run' >&2; exit 2; }
[[ $(basename -- "$lab_root") =~ ^run-[a-z0-9-]+$ ]] || { echo 'invalid lab run directory' >&2; exit 2; }
[[ $lab_root != "$source_data" && $lab_root != "$source_data/"* ]] || exit 2
case "$source_data$lab_root" in *','*|*':'*|*'\'*|*$'\n'*) echo 'unsupported overlay path characters' >&2; exit 2;; esac
[[ $action == check ]] && exit 0
if [[ $action == keepalive ]]; then
    exec -a "alas-redroid-rollback-keepalive-$(basename -- "$lab_root")" sleep 3600
fi
if [[ $action == keepalive-stop ]]; then
    pkill -f "^alas-redroid-rollback-keepalive-$(basename -- "$lab_root")( |$)" || [[ $? == 1 ]]
    exit 0
fi
[[ $(id -u) == 0 ]] || { echo 'overlay mount/cleanup requires root' >&2; exit 2; }

mount_stage() {
    local stage=$1 lower=$2
    [[ ! -e $lab_root/$stage ]] || { echo 'stage already exists' >&2; exit 1; }
    mkdir -p -- "$lab_root/$stage/upper" "$lab_root/$stage/work" "$lab_root/$stage/merged" || return
    mount -t overlay overlay -o "lowerdir=$lower,upperdir=$lab_root/$stage/upper,workdir=$lab_root/$stage/work" "$lab_root/$stage/merged"
}

case "$action" in
    base)
        mkdir -p -- "$expected_parent"
        mkdir -- "$lab_root" || { echo 'lab already exists' >&2; exit 1; }
        if ! mount_stage base "$source_data"; then
            if mountpoint -q "$lab_root/base/merged"; then umount "$lab_root/base/merged"; fi
            rm -rf -- "$lab_root"
            exit 1
        fi
        ;;
    candidate)
        mountpoint -q "$lab_root/base/merged"
        mount -o remount,ro "$lab_root/base/merged"
        mount_stage candidate "$lab_root/base/merged"
        ;;
    rollback)
        mountpoint -q "$lab_root/candidate/merged"
        umount "$lab_root/candidate/merged"
        mount -o remount,rw "$lab_root/base/merged"
        ;;
    cleanup)
        for stage in candidate base; do
            if mountpoint -q "$lab_root/$stage/merged"; then
                umount "$lab_root/$stage/merged"
            fi
        done
        # A leftover nested mount must prevent recursive removal of scratch.
        if findmnt -rn -o TARGET | awk -v root="$lab_root" '$0 == root || index($0, root "/") == 1 {found=1} END {exit !found}'; then
            echo 'lab still contains a mount; retaining scratch' >&2
            exit 1
        fi
        [[ $(realpath -m -- "$lab_root") == "$expected_parent/$(basename -- "$lab_root")" ]] || exit 2
        rm -rf -- "$lab_root"
        ;;
    *) echo 'unknown overlay action' >&2; exit 2;;
esac
