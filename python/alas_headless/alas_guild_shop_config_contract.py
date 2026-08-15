"""Fail-closed contracts for pure ALAS GuildShop entry choices."""

from __future__ import annotations

import re
from dataclasses import dataclass

from .semantic_oracle import SemanticGateClosed


GUILD_SHOP_SECONDARY_CHOICES = {
    "BOX_T3": ("eagle", "royal", "sakura", "ironblood"),
    "BOX_T4": ("eagle", "royal", "sakura", "ironblood"),
    "BOOK_T2": ("red", "blue", "yellow"),
    "BOOK_T3": ("red", "blue", "yellow"),
    "RETROFIT_T2": ("dd", "cl", "bb", "cv"),
    "RETROFIT_T3": ("dd", "cl", "bb", "cv"),
    "PLATE_T2": ("general", "gun", "torpedo", "antiair", "plane"),
    "PLATE_T3": ("general", "gun", "torpedo", "antiair", "plane"),
    "PLATE_T4": ("general", "gun", "torpedo", "antiair", "plane"),
    "PR1": ("neptune", "monarch", "ibuki", "izumo", "roon", "saintlouis"),
    "PR2": ("seattle", "georgia", "kitakaze", "gascogne"),
    "PR3": ("cheshire", "mainz", "odin", "champagne"),
}


@dataclass(frozen=True)
class AlasGuildShopSecondaryChoicesSnapshot:
    box_t3: str
    box_t4: str
    book_t2: str
    book_t3: str
    retrofit_t2: str
    retrofit_t3: str
    plate_t2: str
    plate_t3: str
    plate_t4: str
    pr1: str
    pr2: str
    pr3: str


def validate_alas_guild_shop_refresh(*, refresh: object) -> bool:
    """Validate the refresh switch before the original GuildShop loop begins."""
    if type(refresh) is not bool:
        raise SemanticGateClosed("GuildShop.Refresh must be a bool")
    return refresh


def validate_alas_guild_shop_filter(*, filter_: object, value: object) -> str:
    """Validate GuildShop selector tokens with the pinned ALAS grammar."""
    if not isinstance(value, str):
        raise SemanticGateClosed("GuildShop.Filter must be text")
    regex = getattr(filter_, "regex", None)
    if not hasattr(regex, "fullmatch"):
        raise SemanticGateClosed("pinned ALAS GuildShop filter grammar is unavailable")
    normalized = re.sub(r"[ \t\r\n]", "", value)
    normalized = re.sub(r"[＞﹥›˃ᐳ❯]", ">", normalized)
    normalized = re.sub(r"[‐‑‒–—―−－﹣﹘⁃]", "-", normalized)
    if not normalized:
        return value
    invalid = tuple(
        token
        for token in normalized.split(">")
        if not token or regex.fullmatch(token) is None
    )
    if invalid:
        raise SemanticGateClosed(
            "GuildShop.Filter contains invalid token(s): " + ", ".join(invalid)
        )
    return value


def validate_alas_guild_shop_secondary_choices(
    *,
    box_t3: object,
    box_t4: object,
    book_t2: object,
    book_t3: object,
    retrofit_t2: object,
    retrofit_t3: object,
    plate_t2: object,
    plate_t3: object,
    plate_t4: object,
    pr1: object,
    pr2: object,
    pr3: object,
) -> AlasGuildShopSecondaryChoicesSnapshot:
    """Validate all GuildShop secondary-choice values before purchase starts."""
    values = {
        "BOX_T3": box_t3,
        "BOX_T4": box_t4,
        "BOOK_T2": book_t2,
        "BOOK_T3": book_t3,
        "RETROFIT_T2": retrofit_t2,
        "RETROFIT_T3": retrofit_t3,
        "PLATE_T2": plate_t2,
        "PLATE_T3": plate_t3,
        "PLATE_T4": plate_t4,
        "PR1": pr1,
        "PR2": pr2,
        "PR3": pr3,
    }
    for field, value in values.items():
        if type(value) is not str or value not in GUILD_SHOP_SECONDARY_CHOICES[field]:
            raise SemanticGateClosed(f"GuildShop.{field} is not an allowed choice")
    return AlasGuildShopSecondaryChoicesSnapshot(
        box_t3=box_t3,
        box_t4=box_t4,
        book_t2=book_t2,
        book_t3=book_t3,
        retrofit_t2=retrofit_t2,
        retrofit_t3=retrofit_t3,
        plate_t2=plate_t2,
        plate_t3=plate_t3,
        plate_t4=plate_t4,
        pr1=pr1,
        pr2=pr2,
        pr3=pr3,
    )
