#!/usr/bin/env bash
set -euo pipefail

action=${1:-status}
container=${ALAS_REDROID_LOCAL_CONTAINER:-alas-redroid-wsl-localdev}
image=${ALAS_REDROID_LOCAL_IMAGE:-redroid/redroid@sha256:0a611199ba2e0b5d60af39b3327a517f6407231f4352114ed3bd3cbfe2be69aa}
data_name=${ALAS_REDROID_LOCAL_DATA_NAME:-localdev-data}
data_root=${ALAS_REDROID_LOCAL_DATA:-$HOME/.local/share/alas-redroid/$data_name}
docker_config=${ALAS_REDROID_LOCAL_DOCKER_CONFIG:-$HOME/.config/alas-redroid/docker}
adb_port=${ALAS_REDROID_LOCAL_ADB_PORT:-5555}
oci_zst=${ALAS_REDROID_LOCAL_OCI_ZST:-}
oci_zst_sha256=${ALAS_REDROID_LOCAL_OCI_ZST_SHA256:-}

die() {
    printf 'redroid-local-dev: %s\n' "$*" >&2
    exit 1
}

[[ $adb_port =~ ^[0-9]+$ ]] || die "ADB port must be numeric"
((adb_port >= 1 && adb_port <= 65535)) || die "ADB port is out of range"

mkdir -p "$docker_config"
docker_cmd=(docker --config "$docker_config")

ensure_host() {
    grep -qw binder /proc/filesystems || die "binder filesystem is unavailable in the running WSL kernel"
    if ! mountpoint -q /dev/binderfs; then
        sudo -n install -d -m 0755 /dev/binderfs && \
            sudo -n mount -t binder binder /dev/binderfs || \
            die "binderfs is not mounted; use the Windows manager or mount it as root"
    fi
    for device in binder hwbinder vndbinder; do
        [[ -c /dev/binderfs/$device ]] || die "/dev/binderfs/$device is unavailable"
    done
    systemctl is-active --quiet docker || die "Docker is not active in this WSL distribution"
    [[ $(stat -fc %T /sys/fs/cgroup) == cgroup2fs ]] || die "cgroup v2 is unavailable"
    grep -qw overlay /proc/filesystems || die "overlayfs is unavailable"
}

container_exists() {
    "${docker_cmd[@]}" container inspect "$container" >/dev/null 2>&1
}

ensure_image() {
    local observed_sha256
    if "${docker_cmd[@]}" image inspect "$image" >/dev/null 2>&1; then
        return
    fi
    if [[ -z $oci_zst ]]; then
        "${docker_cmd[@]}" pull "$image"
        return
    fi
    [[ -f $oci_zst ]] || die "project OCI archive is missing: $oci_zst"
    [[ $oci_zst_sha256 =~ ^[0-9a-f]{64}$ ]] || \
        die "a lowercase SHA-256 is required for the compressed project OCI archive"
    command -v zstd >/dev/null || die "zstd is required to import the project OCI archive"
    observed_sha256=$(sha256sum "$oci_zst")
    observed_sha256=${observed_sha256%% *}
    [[ $observed_sha256 == "$oci_zst_sha256" ]] || \
        die "compressed project OCI archive digest mismatch"
    zstd -dc "$oci_zst" | "${docker_cmd[@]}" load
    "${docker_cmd[@]}" image inspect "$image" >/dev/null 2>&1 || \
        die "imported OCI archive did not provide expected image $image"
}

verify_existing_container() {
    local configured_image configured_image_id expected_image_id configured_bind configured_host_ip configured_host_port
    configured_image=$("${docker_cmd[@]}" container inspect --format '{{.Config.Image}}' "$container")
    configured_image_id=$("${docker_cmd[@]}" container inspect --format '{{.Image}}' "$container")
    expected_image_id=$("${docker_cmd[@]}" image inspect --format '{{.Id}}' "$image")
    [[ $configured_image_id == "$expected_image_id" ]] || \
        die "container $container image ID $configured_image_id does not match expected $expected_image_id ($image; configured as $configured_image)"
    configured_bind=$("${docker_cmd[@]}" container inspect \
        --format '{{range .HostConfig.Binds}}{{println .}}{{end}}' "$container")
    grep -Fxq "$data_root:/data" <<<"$configured_bind" || \
        die "container $container does not bind the expected local development data directory"
    configured_host_ip=$("${docker_cmd[@]}" container inspect \
        --format '{{(index (index .HostConfig.PortBindings "5555/tcp") 0).HostIp}}' "$container")
    configured_host_port=$("${docker_cmd[@]}" container inspect \
        --format '{{(index (index .HostConfig.PortBindings "5555/tcp") 0).HostPort}}' "$container")
    [[ $configured_host_ip == 127.0.0.1 && $configured_host_port == "$adb_port" ]] || \
        die "container $container does not expose ADB only on 127.0.0.1:$adb_port"
}

wait_for_boot() {
    local state boot
    for _ in {1..45}; do
        state=$("${docker_cmd[@]}" container inspect --format '{{.State.Status}}' "$container")
        [[ $state == running ]] || die "container stopped during boot with state $state"
        boot=$("${docker_cmd[@]}" exec "$container" /system/bin/getprop sys.boot_completed 2>/dev/null || true)
        if [[ $boot == 1 ]]; then
            printf 'container=%s status=running boot_completed=1 adb=127.0.0.1:%s\n' \
                "$container" "$adb_port"
            return
        fi
        sleep 2
    done
    "${docker_cmd[@]}" logs --tail 100 "$container" >&2 || true
    die "Android did not complete boot within 90 seconds"
}

start_container() {
    ensure_host
    install -d -m 0700 "$data_root"
    ensure_image
    if container_exists; then
        verify_existing_container
        if [[ $("${docker_cmd[@]}" container inspect --format '{{.State.Status}}' "$container") != running ]]; then
            "${docker_cmd[@]}" start "$container" >/dev/null
        fi
    else
        "${docker_cmd[@]}" run -d \
            --name "$container" \
            --privileged \
            --restart no \
            -v "$data_root:/data" \
            -p "127.0.0.1:$adb_port:5555" \
            "$image" \
            androidboot.redroid_width=1280 \
            androidboot.redroid_height=720 \
            androidboot.redroid_dpi=240 \
            androidboot.redroid_gpu_mode=guest >/dev/null
    fi
    wait_for_boot
    printf 'storage_mode=host-directory-persistent\n'
}

stop_container() {
    if ! container_exists; then
        printf 'container=%s status=absent\n' "$container"
        return
    fi
    if [[ $("${docker_cmd[@]}" container inspect --format '{{.State.Status}}' "$container") == running ]]; then
        "${docker_cmd[@]}" stop --timeout 10 "$container" >/dev/null
    fi
    printf 'container=%s status=%s data_retained=%s\n' \
        "$container" \
        "$("${docker_cmd[@]}" container inspect --format '{{.State.Status}}' "$container")" \
        "$data_root"
}

show_status() {
    ensure_host
    if ! container_exists; then
        printf 'container=%s status=absent storage_mode=host-directory-persistent\n' "$container"
        return
    fi
    verify_existing_container
    local state boot
    state=$("${docker_cmd[@]}" container inspect --format '{{.State.Status}}' "$container")
    boot=0
    if [[ $state == running ]]; then
        boot=$("${docker_cmd[@]}" exec "$container" /system/bin/getprop sys.boot_completed 2>/dev/null || true)
        [[ -n $boot ]] || boot=0
    fi
    printf 'container=%s status=%s boot_completed=%s adb=127.0.0.1:%s data=%s\n' \
        "$container" "$state" "$boot" "$adb_port" "$data_root"
    printf 'storage_mode=host-directory-persistent\n'
}

case "$action" in
    start)
        start_container
        ;;
    stop)
        stop_container
        ;;
    status)
        show_status
        ;;
    *)
        die "usage: $0 {start|stop|status}"
        ;;
esac
