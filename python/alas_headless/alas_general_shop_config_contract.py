"""Fail-closed contract for pure ALAS GeneralShop custom-item choices."""

from __future__ import annotations

from dataclasses import dataclass
import re

from .semantic_oracle import SemanticGateClosed


@dataclass(frozen=True)
class AlasGeneralShopCustomItemsConfigSnapshot:
    consume_coins: bool
    buy_skin_box: bool


def validate_alas_general_shop_custom_items_config(
    *, consume_coins: object, buy_skin_box: object
) -> AlasGeneralShopCustomItemsConfigSnapshot:
    """Validate switches before the original pure custom-item predicate."""
    if type(consume_coins) is not bool:
        raise SemanticGateClosed("GeneralShop.ConsumeCoins must be a bool")
    if type(buy_skin_box) is not bool:
        raise SemanticGateClosed("GeneralShop.BuySkinBox must be a bool")
    return AlasGeneralShopCustomItemsConfigSnapshot(
        consume_coins=consume_coins,
        buy_skin_box=buy_skin_box,
    )


def validate_alas_general_shop_use_gems(*, use_gems: object) -> bool:
    """Validate the gem-purchase screening switch before item inspection."""
    if type(use_gems) is not bool:
        raise SemanticGateClosed("GeneralShop.UseGems must be a bool")
    return use_gems


def validate_alas_general_shop_refresh(*, refresh: object) -> bool:
    """Validate the refresh switch before the original shop loop begins."""
    if type(refresh) is not bool:
        raise SemanticGateClosed("GeneralShop.Refresh must be a bool")
    return refresh


def validate_alas_general_shop_filter(*, filter_: object, value: object) -> str:
    """Validate GeneralShop selector tokens with the pinned ALAS grammar."""
    if not isinstance(value, str):
        raise SemanticGateClosed("GeneralShop.Filter must be text")
    regex = getattr(filter_, "regex", None)
    if not hasattr(regex, "fullmatch"):
        raise SemanticGateClosed("pinned ALAS GeneralShop filter grammar is unavailable")
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
            "GeneralShop.Filter contains invalid token(s): " + ", ".join(invalid)
        )
    return value
