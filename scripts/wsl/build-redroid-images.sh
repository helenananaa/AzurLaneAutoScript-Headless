#!/usr/bin/env bash
set -euo pipefail

usage() {
    echo "USAGE: $0 SOURCE_LOCK SOURCE_ROOT EVIDENCE_ROOT" >&2
    exit 2
}

[[ $# -eq 3 ]] || usage
source_lock=$(realpath "$1")
source_root=$(realpath -m "$2")
evidence_root=$(realpath -m "$3")
repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)

[[ ! -e "$source_root" || -d "$source_root" ]] || { echo "source root is not a directory" >&2; exit 1; }
if [[ -d "$source_root" ]] && [[ -n $(find "$source_root" -mindepth 1 -maxdepth 1 -print -quit) ]]; then
    echo "source root must be absent or empty: $source_root" >&2
    exit 1
fi
mkdir -p "$source_root" "$evidence_root"

export PYTHONPATH="$repo_root/python"
python3 "$repo_root/scripts/python/validate_android_image_source_lock.py" --source-lock "$source_lock"
python3 "$repo_root/scripts/python/preflight_redroid_build.py" \
    --source-lock "$source_lock" --root / --output "$evidence_root/host-preflight.json"
python3 "$repo_root/scripts/python/verify_android_image_source_remotes.py" \
    --source-lock "$source_lock" --output "$evidence_root/source-remotes.json"

json_field() {
    python3 - "$source_lock" "$1" <<'PY'
import json, sys
value = json.load(open(sys.argv[1], encoding="utf-8"))
for part in sys.argv[2].split('.'):
    value = value[part]
print(value)
PY
}

manifest_url=$(json_field platform.manifest_url)
platform_revision=$(json_field platform.revision)
local_manifests_url=$(json_field redroid.local_manifests_url)
local_manifests_commit=$(json_field redroid.local_manifests_commit)
patches_url=$(json_field redroid.patches_url)
patches_commit=$(json_field redroid.patches_commit)
patch_set=$(json_field redroid.patch_set)

cd "$source_root"
repo init -u "$manifest_url" -b "$platform_revision" --git-lfs --depth=1
git init .repo/local_manifests
git -C .repo/local_manifests remote add origin "$local_manifests_url"
git -C .repo/local_manifests fetch --depth=1 origin "$local_manifests_commit"
git -C .repo/local_manifests checkout --detach FETCH_HEAD
repo sync -c --fail-fast -j"$(nproc)"
repo manifest -r -o "$evidence_root/resolved-manifest.xml"

patch_root="$evidence_root/redroid-patches"
git clone --no-checkout "$patches_url" "$patch_root"
git -C "$patch_root" checkout --detach "$patches_commit"
[[ -d "$patch_root/$patch_set" ]] || { echo "locked patch set missing: $patch_set" >&2; exit 1; }
set +e
"$patch_root/apply-patch.sh" "$source_root" "$patch_set" 2>&1 | tee "$evidence_root/apply-patches.log"
patch_rc=${PIPESTATUS[0]}
set -e
[[ $patch_rc -eq 0 ]] || { echo "Redroid patch driver failed" >&2; exit 1; }
if grep -Fq '[ERROR]' "$evidence_root/apply-patches.log"; then
    echo "Redroid patch driver reported a rejected patch" >&2
    exit 1
fi
if find "$source_root/.repo/projects" "$source_root/.repo/project-objects" \
    -type d \( -name rebase-apply -o -name rebase-merge \) -print 2>/dev/null | grep -q .; then
    echo "unfinished git-am state after Redroid patch application" >&2
    exit 1
fi

build_one() {
    local abi=$1 lunch_target=$2 product_name=$3
    # shellcheck disable=SC1091
    source build/envsetup.sh
    lunch "$lunch_target"
    m -j"$(nproc)"
    m sbom -j"$(nproc)"
    local product_dir="$source_root/out/target/product/$product_name"
    local build_prop="$product_dir/system/build.prop"
    [[ -f $build_prop ]] || build_prop="$product_dir/system/system/build.prop"
    [[ -f $build_prop ]] || { echo "system build.prop missing for $abi" >&2; exit 1; }
    local sbom="$product_dir/sbom.spdx.json"
    [[ -f $sbom ]] || sbom="$source_root/out/dist/sbom/sbom.spdx.json"
    [[ -f $sbom ]] || sbom="$source_root/out/dist/sbom.spdx.json"
    [[ -f $sbom ]] || { echo "AOSP SPDX 2.3 SBOM missing for $abi" >&2; exit 1; }
    local notice="$product_dir/obj/NOTICE.xml.gz"
    [[ -f $notice ]] || { echo "product NOTICE.xml.gz missing for $abi" >&2; exit 1; }
    local fingerprint patch
    fingerprint=$(sed -n 's/^ro.build.fingerprint=//p' "$build_prop" | head -n1)
    patch=$(sed -n 's/^ro.build.version.security_patch=//p' "$build_prop" | head -n1)
    python3 "$repo_root/scripts/python/create_android_build_provenance.py" \
        --source-lock "$source_lock" \
        --resolved-manifest "$evidence_root/resolved-manifest.xml" \
        --abi "$abi" --lunch "$lunch_target" --product-out "$product_name" \
        --build-fingerprint "$fingerprint" --security-patch "$patch" \
        --artifact "system.img=$product_dir/system.img" \
        --artifact "vendor.img=$product_dir/vendor.img" \
        --sbom "$sbom" --notice "$notice" \
        --installed-files "$product_dir/installed-files.txt" \
        --host-preflight "$evidence_root/host-preflight.json" \
        --output "$evidence_root/provenance-$abi.json"
}

build_one x86_64 redroid_x86_64_only-userdebug redroid_x86_64_only
build_one arm64-v8a redroid_arm64_only-userdebug redroid_arm64_only
