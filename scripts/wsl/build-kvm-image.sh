#!/usr/bin/env bash
set -euo pipefail

usage() {
    echo "USAGE: $0 KVM_DOMAIN_JSON REDROID_DOMAIN_JSON KVM_SOURCE_LOCK KVM_PROFILE" >&2
    exit 2
}

[[ $# -eq 4 ]] || usage

effective_uid=${EUID:-$(id -u)}
if [[ $effective_uid -eq 0 ]]; then
    echo "ERROR: KVM Android image builds must run as the non-root build account." >&2
    echo "Under EUID 0, Android nsjail maps nobody to host uid 65534; ensure the KVM build domain is owned by and run from the non-root build account." >&2
    exit 1
fi

domain=$(realpath "$1")
peer_domain=$(realpath "$2")
source_lock=$(realpath "$3")
profile=$(realpath "$4")
repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
python_bin=${ALAS_PYTHON:-python3}
export PYTHONPATH="$repo_root/python"

domain_sha=$(
    "$python_bin" "$repo_root/scripts/python/validate_android_build_domain.py" \
        --domain "$domain" --expected-backend kvm
)
peer_domain_sha=$(
    "$python_bin" "$repo_root/scripts/python/validate_android_build_domain.py" \
        --domain "$peer_domain" --expected-backend redroid
)
source_lock_sha=$(
    "$python_bin" "$repo_root/scripts/python/validate_kvm_image_source_lock.py" \
        --source-lock "$source_lock"
)
profile_sha=$(
    "$python_bin" "$repo_root/scripts/python/validate_kvm_image_build_profile.py" \
        --profile "$profile"
)

mapfile -t configuration < <("$python_bin" - "$domain" "$source_lock" "$profile" <<'PY'
import json, sys
domain = json.load(open(sys.argv[1], encoding="utf-8"))
source = json.load(open(sys.argv[2], encoding="utf-8"))
profile = json.load(open(sys.argv[3], encoding="utf-8"))
if domain["backend"] != "kvm" or source["backend"] != "kvm" or profile["backend"] != "kvm":
    raise SystemExit("all build contracts must belong to kvm")
paths = domain["paths"]
values = (
    paths["source_root"],
    paths["repo_metadata_root"],
    paths["output_root"],
    paths["ccache_root"],
    paths["build_home"],
    paths["temp_root"],
    paths["evidence_root"],
    profile["source_lock_sha256"],
    source["platform"]["manifest_url"],
    source["platform"]["revision"],
    source["platform"]["commit"],
    json.dumps(source["project_patches"], separators=(",", ":")),
    profile["product"]["lunch"],
    profile["product"]["product_out"],
    profile["build"]["target"],
    str(profile["build"]["relax_uses_library_check"]).lower(),
    str(profile["build"]["dynamic_partitions_size_bytes"]),
    str(profile["build"]["super_partition_size_bytes"]),
)
print("\n".join(str(item) for item in values))
PY
)
source_root=${configuration[0]}
repo_metadata_root=${configuration[1]}
out_root=${configuration[2]}
ccache_root=${configuration[3]}
build_home=${configuration[4]}
temp_root=${configuration[5]}
evidence_root=${configuration[6]}
expected_source_lock_sha=${configuration[7]}
manifest_url=${configuration[8]}
platform_revision=${configuration[9]}
platform_commit=${configuration[10]}
project_patches_json=${configuration[11]}
lunch_target=${configuration[12]}
product_name=${configuration[13]}
build_target=${configuration[14]}
relax_uses_library_check=${configuration[15]}
dynamic_partitions_size_bytes=${configuration[16]}
super_partition_size_bytes=${configuration[17]}

[[ $source_lock_sha == "$expected_source_lock_sha" ]] || {
    echo "KVM profile and source lock differ" >&2
    exit 1
}

mkdir -p "$source_root" "$repo_metadata_root" "$out_root" "$ccache_root" \
    "$build_home" "$temp_root" "$evidence_root"

output_availability=$("$python_bin" - "$domain" "$peer_domain" "$repo_root/python" <<'PY'
import json, sys, types
from pathlib import Path

# Load only the build-domain modules on the minimal build-host Python.  Do not
# execute alas_headless/__init__.py and its unrelated newer-runtime surface.
package_root = Path(sys.argv[3]) / "alas_headless"
package = types.ModuleType("alas_headless")
package.__path__ = [str(package_root)]
package.__package__ = "alas_headless"
sys.modules["alas_headless"] = package

from alas_headless.android_build_domain import AndroidBuildDomain
from alas_headless.android_build_domain_migration import require_output_buildable

selected = AndroidBuildDomain.from_path(Path(sys.argv[1]), expected_backend="kvm")
peer = AndroidBuildDomain.from_path(Path(sys.argv[2]), expected_backend="redroid")
result = require_output_buildable(
    selected,
    peer,
    backend="kvm",
    for_build=True,
)
print(json.dumps(result, sort_keys=True, separators=(",", ":")))
PY
)

readonly SOURCE_FREE_MIN_BYTES=$((400 * 1024 * 1024 * 1024))
readonly REPO_METADATA_FREE_MIN_BYTES=$((64 * 1024 * 1024 * 1024))
require_capacity() {
    local phase=$1
    local source_free
    local repo_free
    source_free=$(df -B1 --output=avail "$source_root" | tail -n1 | tr -d ' ')
    repo_free=$(df -B1 --output=avail "$repo_metadata_root" | tail -n1 | tr -d ' ')
    [[ $source_free =~ ^[0-9]+$ && $repo_free =~ ^[0-9]+$ ]] || {
        echo "cannot read KVM build capacity at $phase" >&2
        exit 1
    }
    ((source_free >= SOURCE_FREE_MIN_BYTES)) || {
        echo "KVM source filesystem has less than 400 GiB free at $phase" >&2
        exit 1
    }
    ((repo_free >= REPO_METADATA_FREE_MIN_BYTES)) || {
        echo "KVM repo metadata filesystem has less than 64 GiB free at $phase" >&2
        exit 1
    }
    printf 'KVM capacity %s: source_free=%s repo_metadata_free=%s\n' \
        "$phase" "$source_free" "$repo_free"
}

source_repo="$source_root/.repo"
if [[ -L $source_repo ]]; then
    [[ $(realpath "$source_repo") == "$(realpath "$repo_metadata_root")" ]] || {
        echo "KVM source .repo points outside its domain metadata root" >&2
        exit 1
    }
elif [[ -d $source_repo ]]; then
    [[ $(stat -Lc '%d:%i' "$source_repo") == \
       "$(stat -Lc '%d:%i' "$repo_metadata_root")" ]] || {
        echo "KVM source .repo is not its owned bind mount" >&2
        exit 1
    }
else
    echo "KVM source .repo is not provisioned" >&2
    exit 1
fi

if ! command -v repo >/dev/null 2>&1; then
    embedded_repo="$source_repo/repo/repo"
    [[ -x $embedded_repo ]] || {
        echo "repo is unavailable from PATH and the provisioned source checkout" >&2
        exit 1
    }
    export PATH="$(dirname "$embedded_repo")${PATH:+:$PATH}"
fi

source_marker="$source_root/.alas-kvm-build-source-lock"
if [[ -e $source_marker ]]; then
    [[ -f $source_marker && $(cat "$source_marker") == "$source_lock_sha" ]] || {
        echo "KVM source marker differs from source lock" >&2
        exit 1
    }
else
    unexpected=$(find "$source_root" -mindepth 1 -maxdepth 1 \
        ! -name .repo -print -quit)
    [[ -z $unexpected ]] || {
        echo "KVM source is non-empty and has no source marker: $unexpected" >&2
        exit 1
    }
    printf '%s\n' "$source_lock_sha" > "$source_marker"
fi

if [[ -e $source_root/.repo/local_manifests ]]; then
    echo "KVM clean AOSP source must not contain local manifests" >&2
    exit 1
fi

export HOME="$build_home"
export XDG_CACHE_HOME="$build_home/.cache"
export GOCACHE="$XDG_CACHE_HOME/go-build"
export TMPDIR="$temp_root"
export CCACHE_DIR="$ccache_root"
mkdir -p "$GOCACHE" "$CCACHE_DIR" "$TMPDIR"

cd "$source_root"
require_capacity before-repo-sync
if [[ ! -d .repo/manifests/.git ]]; then
    repo init -u "$manifest_url" -b "$platform_revision" --git-lfs --depth=1
fi
[[ $(git -C .repo/manifests rev-parse HEAD) == "$platform_commit" ]] || {
    echo "KVM manifest checkout differs from source lock" >&2
    exit 1
}
[[ ! -e .repo/local_manifests ]] || {
    echo "KVM clean AOSP source acquired local manifests during init" >&2
    exit 1
}

sync_marker="$source_root/.alas-kvm-sync-complete"
if [[ -e $sync_marker ]]; then
    [[ -f $sync_marker && $(cat "$sync_marker") == "$source_lock_sha" ]] || {
        echo "KVM sync marker differs from source lock" >&2
        exit 1
    }
else
    repo sync -c --fail-fast -j8
    printf '%s\n' "$source_lock_sha" > "$sync_marker"
fi
require_capacity after-repo-sync

run_id=${ALAS_KVM_RUN_ID:-$(date -u +%Y%m%dT%H%M%SZ)}
[[ $run_id =~ ^[A-Za-z0-9._-]+$ ]] || {
    echo "ALAS_KVM_RUN_ID contains unsupported characters" >&2
    exit 1
}
run_evidence="$evidence_root/$run_id"
[[ ! -e $run_evidence ]] || {
    echo "KVM evidence run already exists: $run_evidence" >&2
    exit 1
}
mkdir -p "$run_evidence"
cp "$domain" "$run_evidence/android-build-domain.json"
cp "$peer_domain" "$run_evidence/peer-redroid-build-domain.json"
cp "$source_lock" "$run_evidence/source-lock.json"
cp "$profile" "$run_evidence/kvm-image-build-profile.json"
printf '%s\n' "$output_availability" > \
    "$run_evidence/output-availability.json"
repo manifest -r -o "$run_evidence/resolved-manifest.xml"

patch_identity=$("$python_bin" - "$project_patches_json" <<'PY'
import hashlib, json, sys
value = json.loads(sys.argv[1])
print(hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest())
PY
)
patch_marker="$source_root/.alas-kvm-project-patches-applied"
if [[ -e $patch_marker ]]; then
    [[ -f $patch_marker && $(cat "$patch_marker") == "$patch_identity" ]] || {
        echo "KVM project patch marker differs" >&2
        exit 1
    }
fi

mapfile -t patch_specs < <("$python_bin" - "$project_patches_json" <<'PY'
import json, sys
for item in json.loads(sys.argv[1]):
    print("\t".join((item["project"], item["path"], item["sha256"])))
PY
)
for patch_spec in "${patch_specs[@]}"; do
    IFS=$'\t' read -r project patch_relative expected_patch_sha <<<"$patch_spec"
    project_root="$source_root/$project"
    patch=$(realpath "$repo_root/$patch_relative")
    case "$patch" in
        "$repo_root"/*) ;;
        *) echo "KVM project patch escapes its control repository" >&2; exit 1 ;;
    esac
    [[ -d $project_root/.git || -f $project_root/.git ]] || {
        echo "KVM patch project is unavailable: $project" >&2
        exit 1
    }
    [[ $(sha256sum "$patch" | awk '{print $1}') == "$expected_patch_sha" ]] || {
        echo "KVM project patch digest differs: $patch_relative" >&2
        exit 1
    }
    mapfile -t touched_paths < <(
        git -C "$project_root" apply --numstat "$patch" | awk '{print $3}'
    )
    [[ ${#touched_paths[@]} -gt 0 ]] || {
        echo "KVM project patch touches no files: $patch_relative" >&2
        exit 1
    }
    if git -C "$project_root" apply --check "$patch"; then
        [[ -z $(git -C "$project_root" status --porcelain) ]] || {
            echo "KVM patch project is dirty before patching: $project" >&2
            exit 1
        }
        git -C "$project_root" apply "$patch"
    else
        mapfile -t dirty_paths < <(
            { git -C "$project_root" diff --name-only HEAD; \
              git -C "$project_root" ls-files --others --exclude-standard; } | sort -u
        )
        [[ ${#dirty_paths[@]} -gt 0 ]] || {
            echo "KVM project patch has no corresponding worktree change: $project" >&2
            exit 1
        }
        for dirty_path in "${dirty_paths[@]}"; do
            found=false
            for touched_path in "${touched_paths[@]}"; do
                [[ $dirty_path == "$touched_path" ]] && found=true
            done
            $found || {
                echo "KVM patch project has an unrelated change: $project/$dirty_path" >&2
                exit 1
            }
        done
        expected_index=$(mktemp "$temp_root/.kvm-expected-index.XXXXXX")
        actual_index=$(mktemp "$temp_root/.kvm-actual-index.XXXXXX")
        rm -f "$expected_index" "$actual_index"
        GIT_INDEX_FILE="$expected_index" git -C "$project_root" read-tree HEAD
        GIT_INDEX_FILE="$expected_index" git -C "$project_root" apply --cached "$patch"
        expected_tree=$(GIT_INDEX_FILE="$expected_index" \
            git -C "$project_root" write-tree)
        GIT_INDEX_FILE="$actual_index" git -C "$project_root" read-tree HEAD
        GIT_INDEX_FILE="$actual_index" git -C "$project_root" add -A -- \
            "${touched_paths[@]}"
        actual_tree=$(GIT_INDEX_FILE="$actual_index" git -C "$project_root" write-tree)
        rm -f "$expected_index" "$actual_index"
        [[ $actual_tree == "$expected_tree" ]] || {
            echo "KVM project worktree is not the exact pinned patch: $project" >&2
            exit 1
        }
    fi
done

unexpected_projects=$("$python_bin" - "$source_root" "$project_patches_json" <<'PY'
import json, pathlib, subprocess, sys
root = pathlib.Path(sys.argv[1])
allowed = {item["project"] for item in json.loads(sys.argv[2])}
unexpected = []
for line in (root / ".repo" / "project.list").read_text(encoding="utf-8").splitlines():
    project = line.strip()
    if not project or project in allowed:
        continue
    status = subprocess.check_output(
        ["git", "-C", str(root / project), "status", "--porcelain"],
        text=True,
        encoding="utf-8",
    ).strip()
    if status:
        unexpected.append(project)
print("\n".join(unexpected))
PY
)
[[ -z $unexpected_projects ]] || {
    printf '%s\n' "$unexpected_projects" >&2
    echo "KVM source contains changes outside its pinned project patches" >&2
    exit 1
}
if [[ ! -e $patch_marker ]]; then
    printf '%s\n' "$patch_identity" > "$patch_marker"
fi
repo status -j8 > "$run_evidence/kvm-source-status.txt"

jobs=${ALAS_KVM_JOBS:-$(nproc)}
[[ $jobs =~ ^[1-9][0-9]*$ ]] || {
    echo "ALAS_KVM_JOBS must be a positive integer" >&2
    exit 1
}
[[ $relax_uses_library_check == true ]] && export RELAX_USES_LIBRARY_CHECK=true
export BOARD_EMULATOR_DYNAMIC_PARTITIONS_SIZE="$dynamic_partitions_size_bytes"
export BOARD_SUPER_PARTITION_SIZE="$super_partition_size_bytes"

out_alias="$source_root/out-kvm"
if [[ -L $out_alias ]]; then
    [[ $(realpath "$out_alias") == "$(realpath "$out_root")" ]] || {
        echo "KVM output alias points outside its domain output root" >&2
        exit 1
    }
elif [[ -e $out_alias ]]; then
    echo "KVM output alias is not a symlink" >&2
    exit 1
else
    ln -s "$out_root" "$out_alias"
fi
export OUT_DIR="out-kvm"
export DIST_DIR="out-kvm/dist"
unset OUT_DIR_COMMON_BASE
require_capacity before-build
mkdir -p "$OUT_DIR/target/product/$product_name/data" "$DIST_DIR"

free_before=$(df -B1 --output=avail "$out_root" | tail -n1 | tr -d ' ')
start_epoch=$(date +%s)
build_log="$run_evidence/build.log"
set +u
# shellcheck disable=SC1091
source build/envsetup.sh
lunch "$lunch_target"
set +e
m -j"$jobs" "$build_target" 2>&1 | tee "$build_log"
build_status=${PIPESTATUS[0]}
set -e
if ((build_status != 0)); then
    data_staging="$OUT_DIR/target/product/$product_name/data"
    missing_data_error="acp: file '$data_staging' does not exist"
    if [[ $build_target == emu_img_zip ]] &&
       tail -n 20 "$build_log" | grep -Fq "$missing_data_error"; then
        echo "KVM SDK packaging lost its empty data staging directory after a product-switch installclean; retrying once." | tee -a "$build_log"
        mkdir -p "$data_staging"
        set +e
        m -j"$jobs" "$build_target" 2>&1 | tee -a "$build_log"
        build_status=${PIPESTATUS[0]}
        set -e
    fi
fi
((build_status == 0)) || exit "$build_status"
set -u

product_out="$out_root/target/product/$product_name"
[[ -d $product_out ]] || {
    echo "KVM product output is unavailable: $product_out" >&2
    exit 1
}
package_inventory="$product_out/product_packages.txt"
package_policy_receipt="$run_evidence/package-policy.json"
[[ -f $package_inventory ]] || {
    echo "KVM product package inventory is unavailable: $package_inventory" >&2
    exit 1
}
"$python_bin" - "$package_inventory" "$package_policy_receipt" <<'PY'
import hashlib
import json
import pathlib
import sys

inventory = pathlib.Path(sys.argv[1])
receipt = pathlib.Path(sys.argv[2])
required = {
    "CarrierConfig",
    "ContactsProvider",
    "DocumentsUI",
    "DownloadProvider",
    "ExternalStorageProvider",
    "GoldfishSkinConfig",
    "IntentResolver",
    "KeyChain",
    "LatinIME",
    "Launcher3QuickStep",
    "NotoColorEmoji.ttf",
    "NotoSansCJK-Regular.ttc",
    "NotoSansSymbols-Regular-Subsetted.ttf",
    "PackageInstaller",
    "Roboto-Regular.ttf",
    "SdkSetup",
    "Settings",
    "SettingsIntelligence",
    "StorageManager",
    "SystemUI",
    "com.android.conscrypt",
    "com.android.i18n",
    "com.android.media",
    "com.android.mediaprovider",
    "com.android.permission",
    "com.android.resolv",
    "com.android.wifi",
    "webview",
}
removed = {
    "AccessibilityMenu",
    "BasicDreams",
    "BackupRestoreConfirmation",
    "BookmarkProvider",
    "Browser2",
    "BuiltInPrintService",
    "Calendar",
    "CalendarProvider",
    "Camera2",
    "CameraExtensionsProxy",
    "Contacts",
    "CompanionDeviceManager",
    "CtsShimPrebuilt",
    "CtsShimPrivPrebuilt",
    "DeskClock",
    "DeviceAsWebcam",
    "Dialer",
    "DynamicSystemInstallationService",
    "E2eeContactKeysProvider",
    "EasterEgg",
    "EmergencyInfo",
    "Gallery2",
    "ImsServiceEntitlement",
    "LiveWallpapersPicker",
    "ManagedProvisioning",
    "MtpService",
    "Music",
    "MusicFX",
    "PartnerBookmarksProvider",
    "PhotoTable",
    "PrintRecommendationService",
    "PrintSpooler",
    "Provision",
    "QuickSearchBox",
    "ThemePicker",
    "SecureElement",
    "SoundPicker",
    "Stk",
    "Tag",
    "Traceur",
    "WallpaperCropper",
    "WallpaperPicker",
    "messaging",
    "vr",
    "NotoSerifCJK-Regular.ttc",
}
modules = {
    line.strip()
    for line in inventory.read_text(encoding="utf-8").splitlines()
    if line.strip()
}
missing = sorted(required - modules)
present = sorted(removed & modules)
payload = inventory.read_bytes()
value = {
    "schema": "alas-headless.kvm-package-policy/v1",
    "outcome": "pass" if not missing and not present else "blocked",
    "inventory_sha256": hashlib.sha256(payload).hexdigest(),
    "module_count": len(modules),
    "required_modules": sorted(required),
    "missing_required_modules": missing,
    "removed_modules": sorted(removed),
    "forbidden_modules_present": present,
}
receipt.write_text(
    json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
)
if missing or present:
    raise SystemExit(
        "KVM package policy blocked: "
        f"missing={missing}, forbidden_present={present}"
    )
PY
cp "$package_inventory" "$run_evidence/product_packages.txt"
image_out="$product_out/emulator/x86_64"
[[ -d $image_out ]] || {
    echo "KVM emulator image output is unavailable: $image_out" >&2
    exit 1
}
cp "$source_root/device/generic/goldfish/data/etc/config.ini" "$image_out/config.ini"
free_after=$(df -B1 --output=avail "$out_root" | tail -n1 | tr -d ' ')
end_epoch=$(date +%s)

"$python_bin" - "$run_evidence/manifest.json" "$image_out" <<PY
import hashlib, json, pathlib, platform, sys
output = pathlib.Path(sys.argv[1])
product = pathlib.Path(sys.argv[2])
artifacts = {}
for name in ("system.img", "vendor.img", "ramdisk.img", "userdata.img", "cache.img"):
    path = product / name
    if path.is_file():
        digest = hashlib.sha256()
        with path.open("rb") as source:
            for chunk in iter(lambda: source.read(8 * 1024 * 1024), b""):
                digest.update(chunk)
        artifacts[name] = {"bytes": path.stat().st_size, "sha256": digest.hexdigest()}
value = {
    "schema": "alas-headless.kvm-image-build/v2",
    "backend": "kvm",
    "outcome": "pass",
    "domain_sha256": "$domain_sha",
    "peer_domain_sha256": "$peer_domain_sha",
    "profile_sha256": "$profile_sha",
    "source_lock_sha256": "$source_lock_sha",
    "project_patches": json.load(open("$source_lock", encoding="utf-8"))["project_patches"],
    "output_residency": "backend-owned",
    "lunch": "$lunch_target",
    "product_out": str(product),
    "build_target": "$build_target",
    "jobs": int("$jobs"),
    "start_epoch": int("$start_epoch"),
    "end_epoch": int("$end_epoch"),
    "free_bytes_before": int("$free_before"),
    "free_bytes_after": int("$free_after"),
    "host": platform.node(),
    "artifacts": artifacts,
    "package_policy": json.load(open("$package_policy_receipt", encoding="utf-8")),
}
output.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY

echo "KVM image build completed: $run_evidence/manifest.json"
