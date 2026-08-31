from __future__ import annotations

import json
import subprocess
import unittest
from pathlib import Path

from alas_headless.android_kvm_source import KvmImageSourceLock


class KvmFirstStageSlimProductTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = Path(__file__).resolve().parents[1]
        patch_root = cls.root / "integration" / "runtime" / "aosp-patches"
        cls.build_make_patch = (
            patch_root / "0002-build-image-source-date-epoch.patch"
        ).read_text(encoding="utf-8")
        cls.product_patch = (
            patch_root / "0003-alas-kvm-first-stage-product.patch"
        ).read_text(encoding="utf-8")
        cls.webview_patch = (
            patch_root / "0004-webview-x86_64-only-prebuilt.patch"
        ).read_text(encoding="utf-8")
        cls.font_patch = (
            patch_root / "0005-kvm-language-font-whitelist.patch"
        ).read_text(encoding="utf-8")
        cls.build_script = (cls.root / "scripts" / "wsl" / "build-kvm-image.sh").read_text(
            encoding="utf-8"
        )
        cls.profile = json.loads(
            (
                cls.root
                / "integration"
                / "runtime"
                / "kvm-image-build-profile.example.json"
            ).read_text(encoding="utf-8")
        )
        cls.source_lock = KvmImageSourceLock.from_path(
            cls.root
            / "integration"
            / "runtime"
            / "kvm-image-source-lock.example.json"
        )

    def test_profile_selects_the_project_owned_goldfish_product(self) -> None:
        self.assertEqual(
            self.profile["product"]["lunch"],
            "alas_kvm_x86_64-trunk_staging-userdebug",
        )
        self.assertEqual(self.profile["product"]["product_out"], "emu64x")
        self.assertEqual(
            self.profile["source_lock_sha256"], self.source_lock.sha256
        )

    def test_product_keeps_real_android_recovery_and_login_surfaces(self) -> None:
        for module in (
            "CarrierConfig",
            "Launcher3QuickStep",
            "LatinIME",
            "SdkSetup",
            "Settings",
            "SettingsIntelligence",
            "StorageManager",
            "SystemUI",
        ):
            self.assertIn(module, self.product_patch)
        self.assertIn("media_product.mk", self.product_patch)
        self.assertNotIn("+    FakeSystemApp \\", self.product_patch)
        self.assertNotIn("+    debug.hwui.drawing_enabled=0", self.product_patch)
        self.assertIn("generic_system.mk", self.product_patch)
        self.assertIn("emulator64_vendor.mk", self.product_patch)
        self.assertNotIn("+    Provision \\", self.product_patch)

    def test_kvm_wifi_is_not_permanently_disabled_by_public_probe_failure(self) -> None:
        self.assertIn(
            '"alas_kvm_x86_64".equals(SystemProperties.get("ro.product.name"))',
            self.product_patch,
        )
        self.assertIn(
            'Settings.Global.putInt(getContentResolver(), "captive_portal_mode", 0);',
            self.product_patch,
        )
        self.assertNotIn("config.noInternetAccessExpected", self.product_patch)

    def test_first_stage_exclusions_are_target_local(self) -> None:
        for module in (
            "CtsShimPrebuilt",
            "CalendarProvider",
            "CameraExtensionsProxy",
            "DeviceAsWebcam",
            "PrintSpooler",
            "Traceur",
            "LiveWallpapersPicker",
        ):
            self.assertIn(
                f"$(if $(filter alas_kvm_x86_64,$(TARGET_PRODUCT)),,{module})",
                self.build_make_patch,
            )
        self.assertNotIn("$(filter sdk_phone64_x86_64", self.build_make_patch)
        self.assertIn("     ContactsProvider \\", self.build_make_patch)
        self.assertNotIn(
            "$(if $(filter alas_kvm_x86_64,$(TARGET_PRODUCT)),,ContactsProvider)",
            self.build_make_patch,
        )

    def test_second_stage_exclusions_are_target_local(self) -> None:
        for module in (
            "BackupRestoreConfirmation",
            "CompanionDeviceManager",
            "DynamicSystemInstallationService",
            "ManagedProvisioning",
            "SecureElement",
            "Stk",
            "Tag",
        ):
            self.assertIn(
                f"$(if $(filter alas_kvm_x86_64,$(TARGET_PRODUCT)),,{module})",
                self.build_make_patch,
            )
        self.assertIn(
            "$(if $(filter alas_kvm_x86_64,$(TARGET_PRODUCT)),,$(RELEASE_PACKAGE_SOUND_PICKER))",
            self.build_make_patch,
        )

    def test_font_whitelist_keeps_english_cjk_emoji_and_symbols(self) -> None:
        for module in (
            "NotoColorEmoji.ttf",
            "NotoColorEmojiFlags.ttf",
            "NotoSansCJK-Regular.ttc",
            "NotoSansSymbols-Regular-Subsetted.ttf",
            "NotoSansSymbols-Regular-Subsetted2.ttf",
            "NotoSerif-Regular.ttf",
        ):
            self.assertIn(module, self.font_patch)
        self.assertIn("ifeq ($(TARGET_PRODUCT),alas_kvm_x86_64)", self.font_patch)
        self.assertNotIn("+    NotoSerifCJK-Regular.ttc", self.font_patch)

    def test_product_keeps_only_required_resource_locales(self) -> None:
        self.assertIn("PRODUCT_LOCALES := \\", self.product_patch)
        for locale in ("en_US", "zh_CN", "zh_TW", "ja_JP", "ko_KR"):
            self.assertIn(f"+    {locale}", self.product_patch)
        self.assertGreater(
            self.product_patch.rindex("+PRODUCT_LOCALES := \\"),
            self.product_patch.rindex("+$(call inherit-product"),
            "the final locale override must follow languages_default inheritance",
        )

    def test_incremental_combined_image_rebuilds_when_envelope_changes(self) -> None:
        self.assertIn(
            'expected_size = (2 + sum(int(p["sizeByMb"]) for p in partitions))',
            self.product_patch,
        )
        self.assertIn("os.remove(output_filename)", self.product_patch)

    def test_package_policy_preserves_critical_boundary_and_rejects_consumer_apps(self) -> None:
        for module in (
            '"SystemUI"',
            '"webview"',
            '"NotoSansCJK-Regular.ttc"',
            '"Roboto-Regular.ttf"',
            '"PackageInstaller"',
            '"ContactsProvider"',
            '"SdkSetup"',
            '"KeyChain"',
            '"ExternalStorageProvider"',
            '"com.android.permission"',
            '"com.android.resolv"',
            '"com.android.wifi"',
        ):
            self.assertIn(module, self.build_script)
        for module in (
            '"Camera2"',
            '"Gallery2"',
            '"Dialer"',
            '"messaging"',
            '"ThemePicker"',
            '"PrintSpooler"',
            '"Provision"',
            '"CtsShimPrebuilt"',
            '"ManagedProvisioning"',
            '"CompanionDeviceManager"',
            '"DynamicSystemInstallationService"',
            '"SecureElement"',
            '"SoundPicker"',
            '"Stk"',
            '"Tag"',
        ):
            self.assertIn(module, self.build_script)

    def test_webview_keeps_the_x86_64_provider_and_strips_only_x86(self) -> None:
        self.assertIn('name: "webview_x86_64_only_apk"', self.webview_patch)
        self.assertIn("-x 'lib/x86/*'", self.webview_patch)
        self.assertIn('apk: ":webview_x86_64_only_apk"', self.webview_patch)
        self.assertNotIn("lib/x86_64/*", self.webview_patch)
        parsed = subprocess.check_output(
            [
                "git",
                "apply",
                "--numstat",
                str(
                    self.root
                    / "integration"
                    / "runtime"
                    / "aosp-patches"
                    / "0004-webview-x86_64-only-prebuilt.patch"
                ),
            ],
            text=True,
        )
        self.assertEqual(parsed.strip(), "12\t1\tAndroid.bp")


if __name__ == "__main__":
    unittest.main()
