#!/usr/bin/env python3
"""Verify the x86_64 Redroid locale and font slimming boundary."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path
from typing import Sequence


SCHEMA = "alas-headless.redroid-locale-font-policy/v1"
EXPECTED_LOCALES = ("en_US", "zh_CN", "zh_TW", "ja_JP", "ko_KR")
EXPECTED_RESOURCE_LOCALES = frozenset({"ja_JP", "ko_KR", "zh_CN", "zh_TW"})
ALLOWED_RESOURCE_LOCALES = EXPECTED_RESOURCE_LOCALES | {"en_US"}
ALLOWED_NOTO_FONTS = frozenset({
    "NotoColorEmoji.ttf",
    "NotoColorEmojiFlags.ttf",
    "NotoSansCJK-Regular.ttc",
    "NotoSansSymbols-Regular-Subsetted.ttf",
    "NotoSansSymbols-Regular-Subsetted2.ttf",
    "NotoSerif-Bold.ttf",
    "NotoSerif-BoldItalic.ttf",
    "NotoSerif-Italic.ttf",
    "NotoSerif-Regular.ttf",
})
REQUIRED_FONTS = ALLOWED_NOTO_FONTS | {"Roboto-Regular.ttf"}
ANDROID_LANGUAGE_CODES = frozenset({
    "af", "am", "ar", "as", "az", "be", "bg", "bn", "bs", "ca", "cs",
    "da", "de", "el", "en", "es", "et", "eu", "fa", "fi", "fr", "gl",
    "gu", "hi", "hr", "hu", "hy", "in", "is", "it", "iw", "ja", "ka",
    "kk", "km", "kn", "ko", "ky", "lo", "lt", "lv", "mk", "ml", "mn",
    "mr", "ms", "my", "nb", "ne", "nl", "or", "pa", "pl", "pt", "ro",
    "ru", "si", "sk", "sl", "sq", "sr", "sv", "sw", "ta", "te", "th",
    "tl", "tr", "uk", "ur", "uz", "vi", "zh", "zu",
})
DEFAULT_REGIONS = {"en": "US", "ja": "JP", "ko": "KR"}
LOCALE_CONFIG = re.compile(r"^([a-z]{2,3})(?:-r([A-Z]{2}))?(?:-|$)")


def split_product_locales(value: str) -> list[str]:
    return [item for item in re.split(r"[\s,]+", value.strip()) if item]


def resource_locale(config: str) -> str | None:
    match = LOCALE_CONFIG.match(config.strip())
    if match is None or match.group(1) not in ANDROID_LANGUAGE_CODES:
        return None
    language, region = match.groups()
    if region is None:
        region = DEFAULT_REGIONS.get(language)
    return language + ("_" + region if region else "")


def apk_resource_locales(aapt2: Path, apk: Path) -> set[str]:
    output = subprocess.check_output(
        [str(aapt2), "dump", "configurations", str(apk)],
        text=True,
        encoding="utf-8",
    )
    return {
        locale
        for line in output.splitlines()
        if (locale := resource_locale(line.strip())) is not None
    }


def verify(
    *,
    inventory: Path,
    fonts_dir: Path,
    aapt2: Path,
    apks: Sequence[Path],
    product_locales: str,
    product_aapt_config: str,
) -> dict[str, object]:
    blockers: list[str] = []
    modules: set[str] = set()
    try:
        modules = {
            line.strip()
            for line in inventory.read_text(encoding="utf-8").splitlines()
            if line.strip()
        }
    except (FileNotFoundError, OSError, UnicodeDecodeError) as error:
        blockers.append("package-inventory-unreadable:{0}".format(type(error).__name__))

    observed_locales = split_product_locales(product_locales)
    observed_aapt = split_product_locales(product_aapt_config)
    if observed_locales != list(EXPECTED_LOCALES):
        blockers.append("product-locales-not-exact")
    if observed_aapt != list(EXPECTED_LOCALES):
        blockers.append("product-aapt-config-not-exact")

    font_files: dict[str, int] = {}
    try:
        font_files = {
            item.name: item.stat().st_size
            for item in fonts_dir.iterdir()
            if item.is_file()
        }
    except (FileNotFoundError, OSError) as error:
        blockers.append("font-directory-unreadable:{0}".format(type(error).__name__))
    missing_fonts = sorted(REQUIRED_FONTS - font_files.keys())
    observed_noto = {name for name in font_files if name.startswith("Noto")}
    unexpected_noto = sorted(observed_noto - ALLOWED_NOTO_FONTS)
    missing_font_modules = sorted(ALLOWED_NOTO_FONTS - modules)
    if missing_fonts:
        blockers.append("required-fonts-missing")
    if unexpected_noto:
        blockers.append("unexpected-noto-fonts-present")
    if missing_font_modules:
        blockers.append("required-font-modules-missing")

    apk_results: list[dict[str, object]] = []
    for apk in apks:
        apk_blockers: list[str] = []
        locales: set[str] = set()
        try:
            locales = apk_resource_locales(aapt2, apk)
        except (FileNotFoundError, OSError, subprocess.CalledProcessError) as error:
            apk_blockers.append("apk-configurations-unreadable:{0}".format(type(error).__name__))
        missing = sorted(EXPECTED_RESOURCE_LOCALES - locales)
        unexpected = sorted(locales - ALLOWED_RESOURCE_LOCALES)
        if missing:
            apk_blockers.append("required-resource-locales-missing")
        if unexpected:
            apk_blockers.append("unexpected-resource-locales-present")
        if apk_blockers:
            blockers.append("apk-locale-policy-failed:" + apk.name)
        apk_results.append({
            "path": str(apk.resolve()),
            "bytes": apk.stat().st_size if apk.is_file() else 0,
            "resource_locales": sorted(locales),
            "missing_resource_locales": missing,
            "unexpected_resource_locales": unexpected,
            "blockers": apk_blockers,
        })

    return {
        "schema": SCHEMA,
        "outcome": "pass" if not blockers else "fail",
        "abi": "x86_64",
        "expected_locales": list(EXPECTED_LOCALES),
        "product_locales": observed_locales,
        "product_aapt_config": observed_aapt,
        "required_fonts": sorted(REQUIRED_FONTS),
        "missing_required_fonts": missing_fonts,
        "unexpected_noto_fonts": unexpected_noto,
        "missing_required_font_modules": missing_font_modules,
        "font_file_count": len(font_files),
        "font_bytes": sum(font_files.values()),
        "apk_results": apk_results,
        "blockers": blockers,
        "alas_workload_used": False,
    }


def main(argv: Sequence[str] = ()) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--inventory", required=True, type=Path)
    parser.add_argument("--fonts-dir", required=True, type=Path)
    parser.add_argument("--aapt2", required=True, type=Path)
    parser.add_argument("--apk", action="append", required=True, type=Path)
    parser.add_argument("--product-locales", required=True)
    parser.add_argument("--product-aapt-config", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(list(argv) if argv else None)
    if args.output.exists():
        parser.error("--output must not already exist")
    result = verify(
        inventory=args.inventory,
        fonts_dir=args.fonts_dir,
        aapt2=args.aapt2,
        apks=args.apk,
        product_locales=args.product_locales,
        product_aapt_config=args.product_aapt_config,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(args.output)
    return 0 if result["outcome"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
