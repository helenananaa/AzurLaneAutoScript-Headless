from __future__ import annotations

import unittest
from pathlib import Path


class AndroidBuildScriptTests(unittest.TestCase):
    @classmethod
    def script(cls) -> str:
        return (
            Path(__file__).resolve().parents[1]
            / "scripts"
            / "wsl"
            / "build-redroid-images.sh"
        ).read_text(encoding="utf-8")

    def test_aosp_envsetup_runs_without_nounset(self) -> None:
        script = self.script()
        expected = """set +u
    # shellcheck disable=SC1091
    source build/envsetup.sh
    lunch \"$lunch_target\"
    m -j\"$build_jobs\"
    m sbom -j\"$build_jobs\"
    set -u"""
        self.assertIn(expected, script)

    def test_redroid_domain_uses_backend_owned_build_state(self) -> None:
        script = self.script()
        self.assertIn("validate_android_build_domain.py", script)
        self.assertIn("--expected-backend redroid", script)
        self.assertIn("--expected-backend kvm", script)
        self.assertIn("require_isolated_domain_pair", script)
        self.assertNotIn("assert-buildable", script)
        self.assertNotIn("flock", script)
        self.assertNotIn("hot_output", script)
        self.assertNotIn("build_lock", script)
        self.assertIn('export HOME="$build_home"', script)
        self.assertIn('export XDG_CACHE_HOME="$HOME/.cache"', script)
        self.assertIn('export GOCACHE="$XDG_CACHE_HOME/go-build"', script)
        self.assertIn('export CCACHE_DIR="$ccache_root"', script)
        self.assertIn('export TMPDIR="$temp_root"', script)
        self.assertIn('export OUT_DIR="$out_root"', script)
        self.assertIn('export DIST_DIR="$out_root/dist"', script)
        self.assertNotIn("out_alias=", script)
        self.assertIn('Redroid AOSP source is dirty', script)
        self.assertNotIn('value["shared"]', script)
        self.assertIn('unset OUT_DIR_COMMON_BASE', script)

    def test_non_executable_packager_is_run_through_bash(self) -> None:
        self.assertIn(
            'sudo /bin/bash "$repo_root/scripts/wsl/package-redroid-oci.sh"',
            self.script(),
        )

    def test_single_abi_build_uses_only_the_selected_product(self) -> None:
        script = self.script()
        self.assertIn('selected_abi=${5:-all}', script)
        self.assertIn('all|x86_64|arm64-v8a', script)
        self.assertIn('[[ $out_root == */x86_64', script)
        self.assertIn('[[ $out_root == */arm64', script)
        self.assertIn('case "$selected_abi" in', script)
        self.assertIn('--source-lock "$source_lock" --abi "$selected_abi"', script)
        self.assertIn('--prepared-source-root "$source_root"', script)

    def test_redroid_angle_workspace_defaults_are_backend_owned(self) -> None:
        root = Path(__file__).resolve().parents[1]
        scripts = (
            "bootstrap-angle.sh",
            "apply-angle-patches.sh",
            "apply-angle-g3-patches.sh",
            "build-angle-null.sh",
            "build-angle-null-observer.sh",
            "build-gles-contract.sh",
        )
        for name in scripts:
            with self.subTest(script=name):
                text = (root / "scripts" / "wsl" / name).read_text(encoding="utf-8")
                self.assertIn("alas-headless-angle-redroid", text)
                self.assertNotIn("${HOME}/src/alas-headless-angle}", text)
        for name in ("bootstrap-angle.sh", "build-angle-null.sh", "build-angle-null-observer.sh"):
            with self.subTest(depot_tools_script=name):
                text = (root / "scripts" / "wsl" / name).read_text(encoding="utf-8")
                self.assertIn("depot_tools-redroid", text)
                self.assertNotIn("${HOME}/src/depot_tools}", text)

    def test_android_14_partition_fingerprint_is_supported(self) -> None:
        script = self.script()
        self.assertIn("s/^ro.system.build.fingerprint=//p", script)
        self.assertIn('[[ -n $fingerprint ]]', script)

    def test_resume_does_not_sync_over_redroid_patches(self) -> None:
        script = self.script()
        self.assertIn('if [[ ! -e "$resolved_manifest" ]]; then', script)
        self.assertIn("ALAS_PREPATCH_MANIFEST", script)
        self.assertIn("refusing repo sync over a prepared Redroid source", script)
        self.assertIn('post-patch-state.json', script)

    def test_build_parallelism_is_overridable_without_changing_the_default(self) -> None:
        script = self.script()
        self.assertIn('build_jobs=${ALAS_BUILD_JOBS:-$(nproc)}', script)
        self.assertIn('ALAS_BUILD_JOBS must be a positive integer', script)
        self.assertEqual(script.count('\n    m -j"$build_jobs"'), 1)
        self.assertEqual(script.count('\n    m sbom -j"$build_jobs"'), 1)

    def test_project_patches_and_artifact_times_are_deterministic(self) -> None:
        script = self.script()
        self.assertIn('.alas-project-patches-applied', script)
        self.assertIn('git", "-C", str(project), "apply", "--check"', script)
        self.assertIn('export E2FSPROGS_FAKE_TIME="$source_date_epoch"', script)
        self.assertIn('normalize_android_sbom.py', script)
        self.assertIn('verify_android_ext4_timestamps.py', script)

    def test_android_14_packaged_angle_uses_private_loader_suffix(self) -> None:
        root = Path(__file__).resolve().parents[1]
        patch = (
            root
            / "integration"
            / "runtime"
            / "aosp-patches"
            / "0003-angle-apk-private-loader-suffix.patch"
        ).read_text(encoding="utf-8")
        self.assertIn('kind + "_angle.so"', patch)
        self.assertIn('kind + "_alasx.so"', patch)

        packager = (
            root / "scripts" / "wsl" / "package-angle-private-loader.sh"
        ).read_text(encoding="utf-8")
        self.assertIn("libEGL_alasx.so", packager)
        self.assertIn("libGLESv1_CM_alasx.so", packager)
        self.assertIn("libGLESv2_alasx.so", packager)
        self.assertIn("chromium-debug.keystore", packager)
        self.assertIn('cp "$egl" "$private_egl"', packager)
        self.assertIn("s/libGLESv2_angle/libGLESv2_alasx/g' \"$private_egl\"", packager)
        self.assertIn("'$private_egl'", packager.replace('"', "'"))
        self.assertIn("s/libEGL_alasx\\.so/libEGL_angle.so/g' \"$egl\"", packager)
        self.assertIn("s/libGLESv2_alasx\\.so/libGLESv2_angle.so/g'", packager)
        self.assertIn("! LC_ALL=C grep -aqF 'libGLESv2_angle' \"$private_egl\"", packager)
        self.assertIn("-x 'lib/*/*.so' 'assets/a4a_rules.json'", packager)
        self.assertIn(
            "zip -X -q -0 \"$work/unsigned.apk\" lib/*/*.so assets/a4a_rules.json",
            packager,
        )
        self.assertIn("compression method:", packager)
        self.assertIn("none (stored)", packager)
        self.assertIn('"$zipalign" -P 16 -f 4', packager)

        observer_build = (
            root / "scripts" / "wsl" / "build-angle-null-observer.sh"
        ).read_text(encoding="utf-8")
        self.assertIn("package-angle-private-loader.sh", observer_build)
        self.assertIn('script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"', observer_build)
        self.assertIn('"${script_dir}/package-angle-private-loader.sh"', observer_build)

    def test_swiftshader_llvm_state_is_process_lived(self) -> None:
        patch = (
            Path(__file__).resolve().parents[1]
            / "integration"
            / "runtime"
            / "aosp-patches"
            / "0004-swiftshader-keep-llvm-state-process-lived.patch"
        ).read_text(encoding="utf-8")
        self.assertIn("LLVM state is process-wide", patch)
        self.assertIn("-llvm::llvm_shutdown_obj llvmShutdownObj;", patch)
        self.assertIn("-#include \"llvm/Support/ManagedStatic.h\"", patch)
        self.assertIn(
            "+  static PassRegistry *PassRegistryObj = new PassRegistry();", patch
        )
        self.assertIn("instead of registering a DSO-scoped destructor", patch)
        self.assertIn("llvm::Intrinsic::fptosi_sat", patch)
        self.assertIn("static std::mutex *ErrorHandlerMutex = new std::mutex();", patch)
        self.assertNotIn("ENABLE_RR_LLVM_IR_VERIFICATION", patch)

    def test_x86_64_redroid_webview_strips_only_the_32_bit_payload(self) -> None:
        root = Path(__file__).resolve().parents[1]
        patch = (
            root
            / "integration"
            / "runtime"
            / "aosp-patches"
            / "0005-redroid-webview-x86_64-only-prebuilt.patch"
        ).read_text(encoding="utf-8")
        self.assertIn('name: "redroid_webview_x86_64_only_apk"', patch)
        self.assertIn("-x 'lib/x86/*'", patch)
        self.assertIn('apk: ":redroid_webview_x86_64_only_apk"', patch)
        self.assertNotIn("-x 'lib/x86_64/*'", patch)

        build = self.script()
        self.assertIn("verify_redroid_webview_abi.py", build)
        self.assertIn('if [[ $abi == x86_64 ]]', build)
        self.assertIn('webview-abi-$abi.json', build)
        self.assertIn('webview-abi.json=$webview_abi_evidence', build)

    def test_x86_64_headless_consumer_trim_is_target_local_and_verified(self) -> None:
        root = Path(__file__).resolve().parents[1]
        patch = (
            root
            / "integration"
            / "runtime"
            / "aosp-patches"
            / "0006-redroid-x86_64-headless-consumer-app-trim.patch"
        ).read_text(encoding="utf-8")
        for module in (
            "Camera2",
            "Contacts",
            "Gallery2",
            "LiveWallpapersPicker",
            "PrintSpooler",
            "Traceur",
        ):
            self.assertIn(
                f"$(if $(filter redroid_x86_64_only,$(TARGET_PRODUCT)),,{module})",
                patch,
            )
        self.assertNotIn("ContactsProvider", patch)
        self.assertNotIn("redroid_arm64_only", patch)

        build = self.script()
        self.assertIn("verify_redroid_headless_package_policy.py", build)
        self.assertIn('headless-package-policy-$abi.json', build)
        self.assertIn(
            'headless-package-policy.json=$package_policy_evidence', build
        )

    def test_x86_64_locale_and_font_trim_is_target_local_and_verified(self) -> None:
        root = Path(__file__).resolve().parents[1]
        locale_patch = (
            root
            / "integration"
            / "runtime"
            / "aosp-patches"
            / "0007-redroid-x86_64-five-locale-product.patch"
        ).read_text(encoding="utf-8")
        font_patch = (
            root
            / "integration"
            / "runtime"
            / "aosp-patches"
            / "0008-redroid-x86_64-noto-font-whitelist.patch"
        ).read_text(encoding="utf-8")
        self.assertIn("PRODUCT_LOCALES := \\", locale_patch)
        for locale in ("en_US", "zh_CN", "zh_TW", "ja_JP", "ko_KR"):
            self.assertIn(f"+    {locale}", locale_patch)
        self.assertIn(
            "ifeq ($(TARGET_PRODUCT),redroid_x86_64_only)", font_patch
        )
        self.assertIn("+    NotoSansCJK-Regular.ttc", font_patch)
        self.assertNotIn("+    NotoSerifCJK-Regular.ttc", font_patch)

        build = self.script()
        self.assertIn("verify_redroid_locale_font_policy.py", build)
        self.assertIn('locale-font-policy-$abi.json', build)
        self.assertIn('locale-font-policy.json=$locale_font_evidence', build)

    def test_oci_packager_preserves_android_numeric_ownership(self) -> None:
        packager = (
            Path(__file__).resolve().parents[1]
            / "scripts"
            / "wsl"
            / "package-redroid-oci.sh"
        ).read_text(encoding="utf-8")
        self.assertIn("--numeric-owner --xattrs", packager)
        self.assertNotIn("--owner=0", packager)
        self.assertNotIn("--group=0", packager)

    def test_oci_packager_rejects_stale_partition_runtime_components(self) -> None:
        root = Path(__file__).resolve().parents[1]
        packager = (root / "scripts" / "wsl" / "package-redroid-oci.sh").read_text(
            encoding="utf-8"
        )
        build = self.script()
        self.assertIn("verify_redroid_partition_runtime_components.py", packager)
        self.assertIn("rebuild systemimage/vendorimage before packaging", packager)
        self.assertIn('"$product_dir/system/lib64/libEGL.so"', build)
        self.assertIn(
            '"$product_dir/vendor/lib64/hw/vulkan.pastel.so"', build
        )
        self.assertIn('runtime-components-$abi.json', build)

    def test_oci_packager_normalizes_only_root_absolute_symlinks(self) -> None:
        packager = (
            Path(__file__).resolve().parents[1]
            / "scripts"
            / "wsl"
            / "package-redroid-oci.sh"
        ).read_text(encoding="utf-8")
        self.assertIn("-mindepth 1 -maxdepth 1 -type l", packager)
        self.assertIn("system_excludes+=(\"--exclude=./$name\")", packager)
        self.assertIn("root_absolute_symlinks+=(\"./$name\")", packager)
        self.assertIn("--transform='flags=s;s|^/||'", packager)
        self.assertIn("root-level Android symlink contains parent traversal", packager)

    def test_rendered_login_requires_and_restores_private_null_routing(self) -> None:
        script = (
            Path(__file__).resolve().parents[1]
            / "scripts"
            / "windows"
            / "run-redroid-rendered-login.ps1"
        ).read_text(encoding="utf-8")
        self.assertIn("Assert-NullRouting", script)
        self.assertIn("Assert-NativeRouting", script)
        self.assertIn("Wait-GamePackageRuntime -RequirePrivateAngle", script)
        self.assertIn("libEGL_alasx", script)
        self.assertIn("libGLESv2_alasx", script)
        self.assertIn("ALAS_G3_SNAPSHOT", script)
        self.assertIn("--pid", script)
        self.assertIn("Run this script once with -RestoreOnly", script)

    def test_observer_login_bootstrap_and_resource_actions_are_narrow(self) -> None:
        root = Path(__file__).resolve().parents[1]
        probe = (
            root
            / "overlays"
            / "angle-g3"
            / "src"
            / "libANGLE"
            / "renderer"
            / "null"
            / "Il2CppNamespaceProbe.cpp"
        ).read_text(encoding="utf-8")
        for path in (
            "PaintingPrefsPanel(Clone)/Panel/Confirm",
            "OtherPrefsPanel(Clone)/Panel/Confirm",
            "DialogPanel/dialog/action_button",
        ):
            self.assertIn(path, probe)

        bootstrap = (
            root
            / "patches"
            / "angle-g3"
            / "0012-android-null-bootstrap-snapshot-retry.patch"
        ).read_text(encoding="utf-8")
        self.assertIn("!mObserverReady", bootstrap)
        self.assertIn("mSwapCount <= 120 && mSwapCount % 3 == 0", bootstrap)
        self.assertIn("status == 0 && !mObserverReady", bootstrap)
        self.assertIn("ALAS_G3_BOOTSTRAP_READY", bootstrap)
        self.assertIn("mSwapCount % 60 == 0", bootstrap)

        apply_script = (
            root / "scripts" / "wsl" / "apply-angle-g3-patches.sh"
        ).read_text(encoding="utf-8")
        observer_build = (
            root / "scripts" / "wsl" / "build-angle-null-observer.sh"
        ).read_text(encoding="utf-8")
        self.assertIn(
            "0012-android-null-bootstrap-snapshot-retry.patch", apply_script
        )
        self.assertIn("Initial typed-snapshot retry is missing", observer_build)

    def test_g4_uses_observer_revision_and_both_resumed_activity_formats(self) -> None:
        script = (
            Path(__file__).resolve().parents[1]
            / "scripts"
            / "windows"
            / "run-g4-game-init.ps1"
        ).read_text(encoding="utf-8")
        self.assertIn("ObserverServer.cpp", script)
        self.assertIn("kDriverRevision", script)
        self.assertIn("angle_source_revision", script)
        self.assertIn("topResumedActivity=|mResumedActivity:", script)


if __name__ == "__main__":
    unittest.main()
