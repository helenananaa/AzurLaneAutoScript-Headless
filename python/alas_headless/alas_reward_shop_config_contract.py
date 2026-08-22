"""Fail-closed contracts for the remaining ordinary reward-shop fields."""

from __future__ import annotations

import re

from .semantic_oracle import SemanticGateClosed


def _validate_filter(*, field: str, filter_: object, value: object) -> str:
    if not isinstance(value, str):
        raise SemanticGateClosed(f"{field} must be text")
    regex = getattr(filter_, "regex", None)
    if not hasattr(regex, "fullmatch"):
        raise SemanticGateClosed(f"pinned ALAS {field} grammar is unavailable")
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
            f"{field} contains invalid token(s): " + ", ".join(invalid)
        )
    return value


def validate_alas_merit_shop_filter(*, filter_: object, value: object) -> str:
    return _validate_filter(field="MeritShop.Filter", filter_=filter_, value=value)


def validate_alas_merit_shop_refresh(*, refresh: object) -> bool:
    if type(refresh) is not bool:
        raise SemanticGateClosed("MeritShop.Refresh must be a bool")
    return refresh


def validate_alas_core_shop_filter(*, filter_: object, value: object) -> str:
    return _validate_filter(field="CoreShop.Filter", filter_=filter_, value=value)
