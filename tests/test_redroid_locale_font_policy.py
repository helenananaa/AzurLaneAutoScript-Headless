from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "python" / (
    "verify_redroid_locale_font_policy.py"
)
SPEC = importlib.util.spec_from_file_location("verify_redroid_locale_font_policy", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class RedroidLocaleFontPolicyTests(unittest.TestCase):
    def fixture(self, root: Path) -> tuple[Path, Path, list[Path]]:
        fonts = root / "fonts"
        fonts.mkdir()
        for name in MODULE.REQUIRED_FONTS:
            (fonts / name).write_bytes(b"font")
        inventory = root / "product_packages.txt"
        inventory.write_text(
            "\n".join(sorted(MODULE.ALLOWED_NOTO_FONTS)) + "\n",
            encoding="utf-8",
        )
        apks = []
        for name in ("Settings.apk", "SystemUI.apk", "Launcher3QuickStep.apk"):
            apk = root / name
            apk.write_bytes(b"apk")
            apks.append(apk)
        return inventory, fonts, apks

    @mock.patch.object(MODULE.subprocess, "check_output")
    def test_accepts_exact_five_locale_and_font_boundary(self, check_output) -> None:
        check_output.return_value = "default\nja\nko\nzh-rCN\nzh-rTW\nland\n"
        with TemporaryDirectory() as raw:
            inventory, fonts, apks = self.fixture(Path(raw))
            result = MODULE.verify(
                inventory=inventory,
                fonts_dir=fonts,
                aapt2=Path("aapt2"),
                apks=apks,
                product_locales="en_US zh_CN zh_TW ja_JP ko_KR",
                product_aapt_config="en_US,zh_CN,zh_TW,ja_JP,ko_KR,",
            )
            self.assertEqual(result["outcome"], "pass")
            self.assertEqual(result["blockers"], [])

    @mock.patch.object(MODULE.subprocess, "check_output")
    def test_rejects_foreign_resource_and_cjk_serif_font(self, check_output) -> None:
        check_output.return_value = "ja\nko\nzh-rCN\nzh-rTW\nfr\nen-rXA\n"
        with TemporaryDirectory() as raw:
            inventory, fonts, apks = self.fixture(Path(raw))
            (fonts / "NotoSerifCJK-Regular.ttc").write_bytes(b"unexpected")
            result = MODULE.verify(
                inventory=inventory,
                fonts_dir=fonts,
                aapt2=Path("aapt2"),
                apks=apks,
                product_locales="en_US zh_CN zh_TW ja_JP ko_KR",
                product_aapt_config="en_US,zh_CN,zh_TW,ja_JP,ko_KR",
            )
            self.assertEqual(result["outcome"], "fail")
            self.assertIn("unexpected-noto-fonts-present", result["blockers"])
            for apk in result["apk_results"]:
                self.assertEqual(apk["unexpected_resource_locales"], ["en_XA", "fr"])

    @mock.patch.object(MODULE.subprocess, "check_output")
    def test_rejects_locale_inheritance_drift_and_missing_font(self, check_output) -> None:
        check_output.return_value = "ja\nko\nzh-rCN\nzh-rTW\n"
        with TemporaryDirectory() as raw:
            inventory, fonts, apks = self.fixture(Path(raw))
            (fonts / "NotoSansCJK-Regular.ttc").unlink()
            result = MODULE.verify(
                inventory=inventory,
                fonts_dir=fonts,
                aapt2=Path("aapt2"),
                apks=apks,
                product_locales="en_US zh_CN zh_TW ja_JP ko_KR fr_FR",
                product_aapt_config="en_US,zh_CN,zh_TW,ja_JP,ko_KR,fr_FR",
            )
            self.assertEqual(result["outcome"], "fail")
            self.assertIn("product-locales-not-exact", result["blockers"])
            self.assertIn("product-aapt-config-not-exact", result["blockers"])
            self.assertIn("required-fonts-missing", result["blockers"])


if __name__ == "__main__":
    unittest.main()
