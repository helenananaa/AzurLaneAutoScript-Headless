#!/usr/bin/env bash
set -euo pipefail

usage() {
    echo "USAGE: $0 REDROID_BUILD_DOMAIN_JSON KVM_BUILD_DOMAIN_JSON SOURCE_LOCK RUN_ID [x86_64|arm64-v8a]" >&2
    exit 2
}

[[ $# -eq 4 || $# -eq 5 ]] || usage
build_domain=$(realpath "$1")
peer_build_domain=$(realpath "$2")
source_lock=$(realpath "$3")
run_id=$4
selected_abi=${5:-all}
case "$selected_abi" in
    all|x86_64|arm64-v8a) ;;
    *) usage ;;
esac
[[ $run_id =~ ^[A-Za-z0-9._-]+$ ]] || {
    echo "RUN_ID contains unsupported characters" >&2; exit 1;
}
repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
python_bin=${ALAS_PYTHON:-python3}
build_jobs=${ALAS_BUILD_JOBS:-$(nproc)}
[[ $build_jobs =~ ^[1-9][0-9]*$ ]] || {
    echo "ALAS_BUILD_JOBS must be a positive integer" >&2; exit 1;
}

export PYTHONPATH="$repo_root/python"
build_domain_sha256=$("$python_bin" \
    "$repo_root/scripts/python/validate_android_build_domain.py" \
    --domain "$build_domain" --expected-backend redroid)
peer_build_domain_sha256=$("$python_bin" \
    "$repo_root/scripts/python/validate_android_build_domain.py" \
    --domain "$peer_build_domain" --expected-backend kvm)
"$python_bin" - "$build_domain" "$peer_build_domain" <<'PY'
import sys
from pathlib import Path

from alas_headless.android_build_domain import (
    AndroidBuildDomain,
    require_isolated_domain_pair,
)

redroid = AndroidBuildDomain.from_path(Path(sys.argv[1]), expected_backend="redroid")
kvm = AndroidBuildDomain.from_path(Path(sys.argv[2]), expected_backend="kvm")
require_isolated_domain_pair(redroid, kvm)
PY
source_lock_sha256=$("$python_bin" \
    "$repo_root/scripts/python/validate_android_image_source_lock.py" \
    --source-lock "$source_lock" | tail -n1)
mapfile -t configuration < <("$python_bin" - "$build_domain" <<'PY'
import json, sys
value = json.load(open(sys.argv[1], encoding="utf-8"))
paths = value["paths"]
for name in (
    "source_root", "repo_metadata_root", "output_root", "ccache_root",
    "build_home", "temp_root", "evidence_root",
):
    print(paths[name])
PY
)
source_root=${configuration[0]}
repo_metadata_root=${configuration[1]}
out_root=${configuration[2]}
ccache_root=${configuration[3]}
build_home=${configuration[4]}
temp_root=${configuration[5]}
evidence_base=${configuration[6]}
evidence_root="$evidence_base/$run_id"

case "$selected_abi" in
    x86_64)
        [[ $out_root == */x86_64 && $ccache_root == */x86_64 \
            && $temp_root == */x86_64 ]] || {
            echo "x86_64 build domain must use architecture-specific output, ccache, and temp roots" >&2
            exit 1
        }
        ;;
    arm64-v8a)
        [[ $out_root == */arm64 && $ccache_root == */arm64 \
            && $temp_root == */arm64 ]] || {
            echo "arm64-v8a build domain must use architecture-specific output, ccache, and temp roots" >&2
            exit 1
        }
        ;;
esac

[[ ! -e "$source_root" || -d "$source_root" ]] || {
    echo "source root is not a directory" >&2; exit 1;
}
mkdir -p "$source_root" "$repo_metadata_root" "$out_root" "$ccache_root" \
    "$build_home" "$temp_root" "$evidence_root"

resume_marker="$source_root/.alas-redroid-build-source-lock"
if [[ -e "$resume_marker" ]]; then
    [[ -f "$resume_marker" && $(cat "$resume_marker") == "$source_lock_sha256" ]] || {
        echo "source root resume marker differs from source lock" >&2; exit 1;
    }
elif [[ -n $(find "$source_root" -mindepth 1 -maxdepth 1 -print -quit) ]]; then
    echo "source root is non-empty and has no matching resume marker: $source_root" >&2
    exit 1
else
    printf '%s\n' "$source_lock_sha256" > "$resume_marker"
fi

repo_metadata_link="$source_root/.repo"
if [[ -L $repo_metadata_link ]]; then
    [[ $(realpath "$repo_metadata_link") == "$(realpath "$repo_metadata_root")" ]] || {
        echo "Redroid source .repo points at another build domain" >&2; exit 1;
    }
elif [[ -e $repo_metadata_link ]]; then
    echo "legacy in-tree .repo must be migrated to $repo_metadata_root" >&2
    exit 1
else
    ln -s "$repo_metadata_root" "$repo_metadata_link"
fi

export HOME="$build_home"
export XDG_CACHE_HOME="$HOME/.cache"
export GOCACHE="$XDG_CACHE_HOME/go-build"
export CCACHE_DIR="$ccache_root"
export TMPDIR="$temp_root"
export OUT_DIR="$out_root"
export DIST_DIR="$out_root/dist"
unset OUT_DIR_COMMON_BASE
mkdir -p "$GOCACHE" "$CCACHE_DIR" "$out_root/dist"

run_json_evidence() {
    local output=$1
    shift
    if [[ ! -e "$output" ]]; then
        "$@" --output "$output"
        return
    fi
    local temporary
    temporary=$(mktemp "$evidence_root/.resume-evidence.XXXXXX")
    rm -f "$temporary"
    "$@" --output "$temporary" >/dev/null
    cmp -s "$output" "$temporary" || {
        rm -f "$temporary"
        echo "existing evidence differs during resume: $output" >&2
        exit 1
    }
    rm -f "$temporary"
}

for binding in "$build_domain:$evidence_root/android-build-domain.json" \
               "$peer_build_domain:$evidence_root/android-build-peer-domain.json" \
               "$source_lock:$evidence_root/source-lock.json"; do
    source_path=${binding%%:*}
    destination_path=${binding#*:}
    if [[ -e $destination_path ]]; then
        cmp -s "$source_path" "$destination_path" || {
            echo "existing run identity differs: $destination_path" >&2; exit 1;
        }
    else
        cp "$source_path" "$destination_path"
    fi
done

preflight_args=(
    --source-lock "$source_lock" --root "$source_root"
    --evidence-root "$evidence_root"
)
if [[ -n ${ALAS_BUILD_BACKING_FREE_BYTES:-} ]]; then
    [[ $ALAS_BUILD_BACKING_FREE_BYTES =~ ^[0-9]+$ ]] || {
        echo "ALAS_BUILD_BACKING_FREE_BYTES must be an integer" >&2; exit 1;
    }
    preflight_args+=(--backing-free-bytes "$ALAS_BUILD_BACKING_FREE_BYTES")
fi
preflight_evidence="$evidence_root/host-preflight.json"
if [[ ! -e "$preflight_evidence" ]]; then
    "$python_bin" "$repo_root/scripts/python/preflight_redroid_build.py" \
        "${preflight_args[@]}" --output "$preflight_evidence"
else
    current_preflight=$(mktemp "$evidence_root/.resume-preflight.XXXXXX")
    rm -f "$current_preflight"
    "$python_bin" "$repo_root/scripts/python/preflight_redroid_build.py" \
        "${preflight_args[@]}" --output "$current_preflight" >/dev/null
    "$python_bin" - "$preflight_evidence" "$current_preflight" <<'PY'
import json, sys
initial = json.load(open(sys.argv[1], encoding="utf-8"))
current = json.load(open(sys.argv[2], encoding="utf-8"))
for value, label in ((initial, "initial"), (current, "current")):
    if value.get("outcome") != "pass":
        raise SystemExit(label + " build-host preflight is not pass")
for key in (
    "source_lock_sha256", "root", "evidence_root", "work_device",
    "evidence_device",
):
    if initial.get(key) != current.get(key):
        raise SystemExit("build-host identity changed during resume: " + key)
PY
    rm -f "$current_preflight"
fi
run_json_evidence "$evidence_root/source-remotes.json" \
    "$python_bin" "$repo_root/scripts/python/verify_android_image_source_remotes.py" \
    --source-lock "$source_lock" --abi "$selected_abi"

json_field() {
    "$python_bin" - "$source_lock" "$1" <<'PY'
import json, sys
value = json.load(open(sys.argv[1], encoding="utf-8"))
for part in sys.argv[2].split('.'):
    value = value[part]
print(value)
PY
}

manifest_url=$(json_field platform.manifest_url)
platform_revision=$(json_field platform.revision)
platform_commit=$(json_field platform.commit)
local_manifests_url=$(json_field redroid.local_manifests_url)
local_manifests_commit=$(json_field redroid.local_manifests_commit)
patches_url=$(json_field redroid.patches_url)
patches_commit=$(json_field redroid.patches_commit)
patch_set=$(json_field redroid.patch_set)
source_date_epoch=$(json_field build.source_date_epoch)
export BUILD_DATETIME="$source_date_epoch"
export SOURCE_DATE_EPOCH="$source_date_epoch"
export BUILD_NUMBER=$(json_field build.build_number)
export BUILD_USERNAME=$(json_field build.build_username)
export BUILD_HOSTNAME=$(json_field build.build_hostname)
export GIT_AUTHOR_NAME=$(json_field build.git_identity.name)
export GIT_AUTHOR_EMAIL=$(json_field build.git_identity.email)
export GIT_COMMITTER_NAME="$GIT_AUTHOR_NAME"
export GIT_COMMITTER_EMAIL="$GIT_AUTHOR_EMAIL"
export TZ=$(json_field build.timezone)
export LC_ALL=$(json_field build.locale)
export LANG="$LC_ALL"
export GIT_COMMITTER_DATE="@$source_date_epoch +0000"
export GIT_AUTHOR_DATE="$GIT_COMMITTER_DATE"
export E2FSPROGS_FAKE_TIME="$source_date_epoch"

cd "$source_root"
if [[ ! -d .repo ]]; then
    repo init -u "$manifest_url" -b "$platform_revision" --git-lfs --depth=1
fi
[[ $(git -C .repo/manifests rev-parse HEAD) == "$platform_commit" ]] || {
    echo "repo init manifest commit differs from source lock" >&2; exit 1;
}
if [[ ! -d .repo/local_manifests/.git ]]; then
    git init .repo/local_manifests
    git -C .repo/local_manifests remote add origin "$local_manifests_url"
fi
git -C .repo/local_manifests fetch --depth=1 origin "$local_manifests_commit"
git -C .repo/local_manifests checkout --detach "$local_manifests_commit"
"$python_bin" - "$source_lock" > .repo/local_manifests/zz-alas-source-lock.xml <<'PY'
import json, sys
from xml.sax.saxutils import quoteattr

value = json.load(open(sys.argv[1], encoding="utf-8"))
print('<?xml version="1.0" encoding="UTF-8"?>')
print("<manifest>")
for project in value["redroid"]["projects"] + value["redroid"]["webview_projects"]:
    print(
        "  <extend-project name={0} path={1} revision={2} />".format(
            quoteattr(project["name"]), quoteattr(project["path"]),
            quoteattr(project["commit"])
        )
    )
print("</manifest>")
PY
resolved_manifest="$evidence_root/resolved-manifest.xml"
if [[ ! -e "$resolved_manifest" ]]; then
    if [[ -e "$source_root/.alas-redroid-patches-applied" \
        || -e "$source_root/.alas-project-patches-applied" ]]; then
        seed_manifest=${ALAS_PREPATCH_MANIFEST:-}
        [[ -n $seed_manifest && -f $seed_manifest ]] || {
            echo "refusing repo sync over a prepared Redroid source; set ALAS_PREPATCH_MANIFEST to its pre-patch resolved manifest" >&2
            exit 1
        }
        cp "$seed_manifest" "$resolved_manifest"
    else
        sync_passed=false
        for attempt in 1 2 3 4 5; do
            if repo sync -c --fail-fast -j8; then
                sync_passed=true
                break
            fi
            echo "repo sync attempt $attempt failed; retaining objects for a rate-limited retry" >&2
            (( attempt < 5 )) && sleep $((attempt * 15))
        done
        [[ $sync_passed == true ]] || { echo "repo sync exhausted five attempts" >&2; exit 1; }
        repo manifest -r -o "$resolved_manifest"
    fi
fi
observed_source_epoch=$(git -C .repo/manifests show -s --format=%ct "$platform_commit")
[[ $observed_source_epoch == "$source_date_epoch" ]] || {
    echo "locked SOURCE_DATE_EPOCH differs from manifest commit" >&2; exit 1;
}
"$python_bin" - "$source_lock" "$resolved_manifest" <<'PY'
import json, sys
import xml.etree.ElementTree as ET

lock = json.load(open(sys.argv[1], encoding="utf-8"))
resolved = {
    (item.get("name"), item.get("path")): item.get("revision")
    for item in ET.parse(sys.argv[2]).getroot().findall("project")
}
for project in lock["redroid"]["projects"] + lock["redroid"]["webview_projects"]:
    key = (project["name"], project["path"])
    if resolved.get(key) != project["commit"]:
        raise SystemExit("resolved manifest mismatch for {0}".format(key))
PY

patch_root="$source_root/.alas-redroid-patches"
if [[ ! -d "$patch_root/.git" ]]; then
    git clone --no-checkout "$patches_url" "$patch_root"
fi
git -C "$patch_root" fetch origin "$patches_commit"
git -C "$patch_root" checkout --detach "$patches_commit"
[[ -d "$patch_root/$patch_set" ]] || { echo "locked patch set missing: $patch_set" >&2; exit 1; }
patch_marker="$source_root/.alas-redroid-patches-applied"
if [[ -e "$patch_marker" ]]; then
    [[ $(cat "$patch_marker") == "$patches_commit:$patch_set" ]] || {
        echo "patch resume marker mismatch" >&2; exit 1;
    }
else
    [[ ! -e "$evidence_root/apply-patches.log" ]] || {
        echo "patch log exists without completion marker; manual audit required" >&2; exit 1;
    }
    set +e
    "$patch_root/apply-patch.sh" "$source_root" "$patch_set" 2>&1 | tee "$evidence_root/apply-patches.log"
    patch_rc=${PIPESTATUS[0]}
    set -e
    [[ $patch_rc -eq 0 ]] || { echo "Redroid patch driver failed" >&2; exit 1; }
    if grep -Fq '[ERROR]' "$evidence_root/apply-patches.log"; then
        echo "Redroid patch driver reported a rejected patch" >&2
        exit 1
    fi
    printf '%s:%s\n' "$patches_commit" "$patch_set" > "$patch_marker"
fi
if find "$source_root/.repo/projects" "$source_root/.repo/project-objects" \
    -type d \( -name rebase-apply -o -name rebase-merge \) -print 2>/dev/null | grep -q .; then
    echo "unfinished git-am state after Redroid patch application" >&2
    exit 1
fi
project_patch_marker="$source_root/.alas-project-patches-applied"
project_patch_identity=$("$python_bin" - "$source_lock" <<'PY'
import hashlib, json, sys
value = json.load(open(sys.argv[1], encoding="utf-8"))["project_patches"]
print(hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest())
PY
)
if [[ -e "$project_patch_marker" ]]; then
    [[ $(cat "$project_patch_marker") == "$project_patch_identity" ]] || {
        echo "project patch resume marker mismatch" >&2; exit 1;
    }
else
    "$python_bin" - "$source_lock" "$repo_root" "$source_root" <<'PY'
import hashlib, json, pathlib, subprocess, sys
lock = json.load(open(sys.argv[1], encoding="utf-8"))
repo_root, source_root = map(pathlib.Path, sys.argv[2:])
for item in lock["project_patches"]:
    patch = (repo_root / item["path"]).resolve()
    if repo_root.resolve() not in patch.parents:
        raise SystemExit("project patch escapes repository")
    if hashlib.sha256(patch.read_bytes()).hexdigest() != item["sha256"]:
        raise SystemExit("project patch digest mismatch: " + item["path"])
    project = source_root / item["project"]
    subprocess.run(["git", "-C", str(project), "apply", "--check", str(patch)], check=True)
    subprocess.run(["git", "-C", str(project), "apply", "--index", str(patch)], check=True)
    subprocess.run([
        "git", "-C", str(project), "commit", "-m",
        item["commit_message"],
    ], check=True)
PY
    "$python_bin" - "$source_lock" >> "$evidence_root/apply-patches.log" <<'PY'
import json, sys
for item in json.load(open(sys.argv[1], encoding="utf-8"))["project_patches"]:
    print("process project: " + item["project"])
PY
    printf '%s\n' "$project_patch_identity" > "$project_patch_marker"
fi
if [[ ! -e "$evidence_root/apply-patches.log" ]]; then
    # Source markers survive across run-specific evidence directories. Rebuild
    # the affected-project inventory from the resolved manifest instead of
    # depending on a historical run's patch-driver log.
    "$python_bin" - "$source_root" "$resolved_manifest" \
        > "$evidence_root/apply-patches.log" <<'PY'
import pathlib, subprocess, sys, xml.etree.ElementTree as ET
source_root = pathlib.Path(sys.argv[1])
projects = []
for item in ET.parse(sys.argv[2]).getroot().findall("project"):
    path = item.get("path", item.get("name"))
    revision = item.get("revision")
    if not path or not revision:
        continue
    project = source_root / path
    head = subprocess.check_output(
        ["git", "-C", str(project), "rev-parse", "HEAD"],
        text=True, encoding="utf-8",
    ).strip()
    if head != revision:
        projects.append(path)
for path in sorted(projects):
    print("process project: " + path)
PY
fi
run_json_evidence "$evidence_root/post-patch-state.json" \
    "$python_bin" "$repo_root/scripts/python/capture_redroid_post_patch_state.py" \
    --source-lock "$source_lock" --source-root "$source_root" \
    --resolved-manifest "$resolved_manifest" \
    --apply-log "$evidence_root/apply-patches.log"

redroid_source_status=$(repo status -j8)
[[ $redroid_source_status == "nothing to commit (working directory clean)" ]] || {
    printf '%s\n' "$redroid_source_status" >&2
    echo "Redroid AOSP source is dirty after patch application" >&2
    exit 1
}
redroid_source_evidence="$evidence_root/redroid-source-status.txt"
if [[ -e $redroid_source_evidence ]]; then
    [[ $(cat "$redroid_source_evidence") == "$redroid_source_status" ]] || {
        echo "Redroid AOSP source status changed during resume" >&2; exit 1;
    }
else
    printf '%s\n' "$redroid_source_status" > "$redroid_source_evidence"
fi

# Upstream Redroid intentionally leaves product.mk as a local extension point.
# Bind our reviewed dual-volume FBE overlay into every build, and refuse to
# replace any pre-existing local customization.
overlay_root="$repo_root/integration/runtime/redroid-native-fbe"
overlay_evidence="$evidence_root/redroid-native-fbe-overlay.json"
run_json_evidence "$overlay_evidence" \
    "$python_bin" "$repo_root/scripts/python/validate_redroid_native_fbe_overlay.py" \
    --overlay "$overlay_root" --source-lock "$source_lock"
if [[ -e "$source_root/product.mk" ]] && ! cmp -s "$overlay_root/product.mk" "$source_root/product.mk"; then
    echo "refusing to overwrite different AOSP product.mk" >&2; exit 1
fi
mkdir -p "$source_root/alas/redroid-native-fbe"
cp "$overlay_root/fstab.redroid" "$source_root/alas/redroid-native-fbe/fstab.redroid"
cp "$overlay_root/init.alas-fbe.rc" "$source_root/alas/redroid-native-fbe/init.alas-fbe.rc"
cp "$overlay_root/product.mk" "$source_root/product.mk"

build_one() {
    local abi=$1 lunch_target=$2 product_name=$3
    # AOSP's envsetup probes variables such as TOP before defining them. Keep
    # strict nounset everywhere else, but do not impose it on the upstream
    # shell initialisation contract.
    set +u
    # shellcheck disable=SC1091
    source build/envsetup.sh
    lunch "$lunch_target"
    m -j"$build_jobs"
    m sbom -j"$build_jobs"
    set -u
    local product_dir="$out_root/target/product/$product_name"
    local build_prop="$product_dir/system/build.prop"
    [[ -f $build_prop ]] || build_prop="$product_dir/system/system/build.prop"
    [[ -f $build_prop ]] || { echo "system build.prop missing for $abi" >&2; exit 1; }
    local sbom="$product_dir/sbom.spdx.json"
    [[ -f $sbom ]] || sbom="$out_root/dist/sbom/sbom.spdx.json"
    [[ -f $sbom ]] || { echo "AOSP SPDX 2.3 SBOM missing for $abi" >&2; exit 1; }
    "$python_bin" "$repo_root/scripts/python/normalize_android_sbom.py" \
        --sbom "$sbom" --source-date-epoch "$source_date_epoch"
    local notice="$product_dir/obj/NOTICE.xml.gz"
    [[ -f $notice ]] || { echo "product NOTICE.xml.gz missing for $abi" >&2; exit 1; }
    run_json_evidence "$evidence_root/ext4-timestamps-$abi.json" \
        "$python_bin" "$repo_root/scripts/python/verify_android_ext4_timestamps.py" \
        --image "$product_dir/system.img" --image "$product_dir/vendor.img" \
        --source-date-epoch "$source_date_epoch"
    local fingerprint patch
    fingerprint=$(sed -n \
        -e 's/^ro.system.build.fingerprint=//p' \
        -e 's/^ro.build.fingerprint=//p' \
        "$build_prop" | head -n1)
    [[ -n $fingerprint ]] || {
        echo "system build fingerprint missing for $abi" >&2; exit 1;
    }
    patch=$(sed -n 's/^ro.build.version.security_patch=//p' "$build_prop" | head -n1)
    local observed_user observed_host observed_date observed_incremental
    observed_user=$(sed -n 's/^ro.build.user=//p' "$build_prop" | head -n1)
    observed_host=$(sed -n 's/^ro.build.host=//p' "$build_prop" | head -n1)
    observed_date=$(sed -n 's/^ro.build.date.utc=//p' "$build_prop" | head -n1)
    observed_incremental=$(sed -n 's/^ro.build.version.incremental=//p' "$build_prop" | head -n1)
    [[ $observed_user == "$BUILD_USERNAME" && $observed_host == "$BUILD_HOSTNAME" \
        && $observed_date == "$BUILD_DATETIME" && $observed_incremental == "$BUILD_NUMBER" ]] || {
        echo "built image identity differs from deterministic build environment" >&2; exit 1;
    }
    local oci_archive="$evidence_root/redroid-$abi.oci.tar"
    local oci_identity="$evidence_root/redroid-$abi.oci-build.json"
    local runtime_components="$evidence_root/runtime-components-$abi.json"
    sudo /bin/bash "$repo_root/scripts/wsl/package-redroid-oci.sh" \
        "$product_dir/system.img" "$product_dir/vendor.img" "$abi" \
        "$source_lock_sha256" "$fingerprint" "$source_date_epoch" \
        "$product_dir/system/lib64/libEGL.so" \
        "$product_dir/vendor/lib64/hw/vulkan.pastel.so" \
        "$oci_archive" "$oci_identity" "$runtime_components"
    "$python_bin" "$repo_root/scripts/python/create_android_build_provenance.py" \
        --source-lock "$source_lock" \
        --resolved-manifest "$evidence_root/resolved-manifest.xml" \
        --abi "$abi" --lunch "$lunch_target" --product-out "$product_name" \
        --build-fingerprint "$fingerprint" --security-patch "$patch" \
        --artifact "system.img=$product_dir/system.img" \
        --artifact "vendor.img=$product_dir/vendor.img" \
        --artifact "redroid.oci.tar=$oci_archive" \
        --artifact "android-build-domain.json=$evidence_root/android-build-domain.json" \
        --artifact "redroid-native-fbe-overlay.json=$overlay_evidence" \
        --artifact "post-patch-state.json=$evidence_root/post-patch-state.json" \
        --artifact "runtime-components.json=$runtime_components" \
        --artifact "ext4-timestamps.json=$evidence_root/ext4-timestamps-$abi.json" \
        --sbom "$sbom" --notice "$notice" \
        --installed-files "$product_dir/installed-files.txt" \
        --host-preflight "$evidence_root/host-preflight.json" \
        --output "$evidence_root/provenance-$abi.json"
}

case "$selected_abi" in
    all)
        build_one x86_64 redroid_x86_64_only-trunk_staging-userdebug redroid_x86_64_only
        build_one arm64-v8a redroid_arm64_only-trunk_staging-userdebug redroid_arm64_only
        ;;
    x86_64)
        build_one x86_64 redroid_x86_64_only-trunk_staging-userdebug redroid_x86_64_only
        ;;
    arm64-v8a)
        build_one arm64-v8a redroid_arm64_only-trunk_staging-userdebug redroid_arm64_only
        ;;
esac
