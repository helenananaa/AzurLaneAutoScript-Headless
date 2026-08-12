#!/usr/bin/env bash
set -euo pipefail

usage() {
    echo "USAGE: $0 PREVIOUS_IMAGE CANDIDATE_IMAGE ABI HOST_PORT [WIDTH HEIGHT DPI]" >&2
    exit 2
}

[[ $# -eq 4 || $# -eq 7 ]] || usage
previous_image=$1
candidate_image=$2
abi=$3
host_port=$4
width=${5:-1280}
height=${6:-720}
dpi=${7:-240}

digest_ref='^[a-z0-9][a-z0-9._/-]*@sha256:[0-9a-f]{64}$'
[[ $previous_image =~ $digest_ref ]] || { echo "previous image must use a digest" >&2; exit 1; }
[[ $candidate_image =~ $digest_ref ]] || { echo "candidate image must use a digest" >&2; exit 1; }
[[ $previous_image != "$candidate_image" ]] || { echo "rollback requires two distinct digests" >&2; exit 1; }
[[ $abi == arm64-v8a || $abi == x86_64 ]] || { echo "unsupported ABI" >&2; exit 1; }
[[ $host_port =~ ^[0-9]+$ ]] && (( host_port >= 1024 && host_port <= 65535 )) || {
    echo "host port must be between 1024 and 65535" >&2; exit 1;
}
if ss -H -ltn "sport = :$host_port" | grep -q .; then
    echo "host port is already in use: $host_port" >&2
    exit 1
fi

expected_arch=amd64
[[ $abi == arm64-v8a ]] && expected_arch=arm64
platform="linux/$expected_arch"
host_arch=$(uname -m)
execution_mode=native
host_expected=amd64
[[ $host_arch == x86_64 || $host_arch == amd64 ]] && host_normalized=amd64 || host_normalized=$host_arch
[[ $expected_arch == arm64 ]] && host_expected=arm64
[[ $host_arch == aarch64 ]] && host_normalized=arm64
[[ $host_normalized == "$host_expected" ]] || {
    echo "privileged Redroid rollback requires a native-architecture host; binfmt emulation is forbidden" >&2
    exit 1
}
docker pull --platform "$platform" "$previous_image" >/dev/null
docker pull --platform "$platform" "$candidate_image" >/dev/null
previous_arch=$(docker image inspect "$previous_image" --format '{{.Architecture}}')
candidate_arch=$(docker image inspect "$candidate_image" --format '{{.Architecture}}')
[[ $previous_arch == "$expected_arch" && $candidate_arch == "$expected_arch" ]] || {
    echo "image architecture mismatch" >&2; exit 1;
}

previous_digest=${previous_image##*@}
candidate_digest=${candidate_image##*@}
container="alas-rollback-$RANDOM-$$"
lab_root=$(mktemp -d /var/lib/redroid/rollback-lab.XXXXXX)
lab_root=$(realpath "$lab_root")
[[ $lab_root == /var/lib/redroid/rollback-lab.* ]] || {
    echo "unsafe rollback lab root: $lab_root" >&2; exit 1;
}
data_dir="$lab_root/data"
snapshot="$lab_root/data-before-candidate.tar"
mkdir -p "$data_dir"
sentinel="alas-image-rollback-$RANDOM-$$"
sentinel_path=/data/local/tmp/alas-image-rollback-sentinel
cleaned=false

cleanup() {
    docker rm -f "$container" >/dev/null 2>&1 || true
    if [[ -n ${lab_root:-} && $lab_root == /var/lib/redroid/rollback-lab.* && -d $lab_root ]]; then
        rm -rf -- "$lab_root"
    fi
}
trap cleanup EXIT

wait_boot() {
    local deadline=$((SECONDS + 180))
    until [[ $(docker exec "$container" getprop sys.boot_completed 2>/dev/null || true) == 1 ]]; do
        (( SECONDS < deadline )) || { docker logs "$container" >&2; return 1; }
        sleep 2
    done
}

start_image() {
    local image=$1
    docker run -d --name "$container" --platform "$platform" --privileged \
        -v "$data_dir:/data" -p "127.0.0.1:$host_port:5555" \
        "$image" \
        "androidboot.redroid_width=$width" \
        "androidboot.redroid_height=$height" \
        "androidboot.redroid_dpi=$dpi" >/dev/null
    wait_boot
}

stop_image() {
    docker rm -f "$container" >/dev/null
}

start_image "$previous_image"
previous_firstboot_before=$(docker exec "$container" getprop ro.runtime.firstboot)
previous_fingerprint_before=$(docker exec "$container" getprop ro.build.fingerprint)
previous_api_before=$(docker exec "$container" getprop ro.build.version.sdk)
[[ -n $previous_fingerprint_before && -n $previous_api_before ]]
docker exec "$container" sh -c "printf '%s' '$sentinel' > '$sentinel_path'"
[[ $(docker exec "$container" cat "$sentinel_path") == "$sentinel" ]]
stop_image

tar --xattrs --acls --selinux --numeric-owner -cpf "$snapshot" -C "$data_dir" .
snapshot_sha256=$(sha256sum "$snapshot" | awk '{print $1}')

start_image "$candidate_image"
candidate_firstboot=$(docker exec "$container" getprop ro.runtime.firstboot)
candidate_fingerprint=$(docker exec "$container" getprop ro.build.fingerprint)
candidate_api=$(docker exec "$container" getprop ro.build.version.sdk)
[[ -n $candidate_fingerprint && -n $candidate_api ]]
[[ $candidate_fingerprint != "$previous_fingerprint_before" ]] || {
    echo "candidate build fingerprint did not change" >&2; exit 1;
}
candidate_preserved=false
[[ $(docker exec "$container" cat "$sentinel_path" 2>/dev/null || true) == "$sentinel" ]] && candidate_preserved=true
stop_image
[[ $candidate_preserved == true ]] || { echo "candidate did not preserve /data sentinel" >&2; exit 1; }

resolved_data=$(realpath "$data_dir")
[[ $resolved_data == "$lab_root/data" ]] || { echo "unsafe data restore target" >&2; exit 1; }
find "$resolved_data" -mindepth 1 -maxdepth 1 -exec rm -rf -- {} +
tar --xattrs --acls --selinux --numeric-owner -xpf "$snapshot" -C "$resolved_data"

start_image "$previous_image"
previous_firstboot_after=$(docker exec "$container" getprop ro.runtime.firstboot)
previous_fingerprint_after=$(docker exec "$container" getprop ro.build.fingerprint)
previous_api_after=$(docker exec "$container" getprop ro.build.version.sdk)
[[ $previous_fingerprint_after == "$previous_fingerprint_before" ]] || {
    echo "rollback did not restore previous build fingerprint" >&2; exit 1;
}
[[ $previous_api_after == "$previous_api_before" ]] || {
    echo "rollback did not restore previous API level" >&2; exit 1;
}
rollback_preserved=false
[[ $(docker exec "$container" cat "$sentinel_path" 2>/dev/null || true) == "$sentinel" ]] && rollback_preserved=true
stop_image
[[ $rollback_preserved == true ]] || { echo "rollback snapshot did not restore /data sentinel" >&2; exit 1; }

cleanup
cleaned=true
trap - EXIT
cat <<JSON
{
  "schema": "alas-headless.redroid-image-rollback/v1",
  "outcome": "pass",
  "abi": "$abi",
  "platform": "$platform",
  "host_architecture": "$host_arch",
  "execution_mode": "$execution_mode",
  "performance_claim_allowed": false,
  "previous_image_digest": "$previous_digest",
  "candidate_image_digest": "$candidate_digest",
  "snapshot_sha256": "$snapshot_sha256",
  "candidate_userdata_preserved": $candidate_preserved,
  "rollback_snapshot_restored": $rollback_preserved,
  "previous_firstboot_before": "$previous_firstboot_before",
  "previous_fingerprint_before": "$previous_fingerprint_before",
  "previous_api_before": "$previous_api_before",
  "candidate_firstboot": "$candidate_firstboot",
  "candidate_fingerprint": "$candidate_fingerprint",
  "candidate_api": "$candidate_api",
  "previous_firstboot_after": "$previous_firstboot_after",
  "previous_fingerprint_after": "$previous_fingerprint_after",
  "previous_api_after": "$previous_api_after",
  "lab_cleaned": $cleaned,
  "game_installed": false,
  "alas_workload_used": false
}
JSON
