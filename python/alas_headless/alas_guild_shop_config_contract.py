"""Fail-closed contracts for pure ALAS GuildShop entry choices."""

from __future__ import annotations

import re

from .semantic_oracle import SemanticGateClosed


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
