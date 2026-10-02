"""Fail-closed contracts for ALAS MedalShop2 entry configuration."""

from __future__ import annotations

from dataclasses import dataclass
import re

from .semantic_oracle import SemanticGateClosed


MEDAL_SHOP_SECONDARY_CHOICES = {
    "RETROFIT_T1": ("dd", "cl", "bb", "cv"),
    "RETROFIT_T2": ("dd", "cl", "bb", "cv"),
    "RETROFIT_T3": ("dd", "cl", "bb", "cv"),
    "PLATE_T1": ("general", "gun", "torpedo", "antiair", "plane"),
    "PLATE_T2": ("general", "gun", "torpedo", "antiair", "plane"),
    "PLATE_T3": ("general", "gun", "torpedo", "antiair", "plane"),
}


@dataclass(frozen=True)
class AlasMedalShopSecondaryChoicesSnapshot:
    retrofit_t1: str
    retrofit_t2: str
    retrofit_t3: str
    plate_t1: str
    plate_t2: str
    plate_t3: str


def validate_alas_medal_shop_filter(*, filter_: object, value: object) -> str:
    """Validate MedalShop2 selector tokens with the pinned ALAS grammar."""
    if not isinstance(value, str):
        raise SemanticGateClosed("MedalShop2.Filter must be text")
    regex = getattr(filter_, "regex", None)
    if not hasattr(regex, "fullmatch"):
        raise SemanticGateClosed("pinned ALAS MedalShop2 filter grammar is unavailable")
    normalized = re.sub(r"[ \t\r\n]", "", value)
    normalized = re.sub(r"[＞﹥›˃ᐳ❯]", ">", normalized)
    normalized = re.sub(r"[‐‑‒–—―−－﹣﹘⁃]", "-", normalized)
    if not normalized:
        return value
    # ALAS treats a lone separator as a no-match selector.  Keep the source
    # policy intact: an empty string is replaced by ALAS's default buys.
    if normalized == ">":
        return value
    invalid = tuple(
        token
        for token in normalized.split(">")
        if not token or regex.fullmatch(token) is None
    )
    if invalid:
        raise SemanticGateClosed(
            "MedalShop2.Filter contains invalid token(s): " + ", ".join(invalid)
        )
    return value


def validate_alas_medal_shop_secondary_choices(
    *,
    retrofit_t1: object,
    retrofit_t2: object,
    retrofit_t3: object,
    plate_t1: object,
    plate_t2: object,
    plate_t3: object,
) -> AlasMedalShopSecondaryChoicesSnapshot:
    """Validate every MedalShop2 secondary choice before the shop loop starts."""
    values = {
        "RETROFIT_T1": retrofit_t1,
        "RETROFIT_T2": retrofit_t2,
        "RETROFIT_T3": retrofit_t3,
        "PLATE_T1": plate_t1,
        "PLATE_T2": plate_t2,
        "PLATE_T3": plate_t3,
    }
    for field, value in values.items():
        if type(value) is not str or value not in MEDAL_SHOP_SECONDARY_CHOICES[field]:
            raise SemanticGateClosed(f"MedalShop2.{field} is not an allowed choice")
    return AlasMedalShopSecondaryChoicesSnapshot(
        retrofit_t1=retrofit_t1,
        retrofit_t2=retrofit_t2,
        retrofit_t3=retrofit_t3,
        plate_t1=plate_t1,
        plate_t2=plate_t2,
        plate_t3=plate_t3,
    )
