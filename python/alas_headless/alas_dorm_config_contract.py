"""Fail-closed contract for ALAS Dorm task configuration."""

from __future__ import annotations

from dataclasses import dataclass
import re

from .semantic_oracle import SemanticGateClosed


DORM_FOOD_VALUES = (1000, 2000, 3000, 5000, 10000, 20000)
_DORM_FILTER_SEPARATOR = re.compile(r"[＞﹥›˃ᐳ❯]")
_DORM_FILTER_WHITESPACE = re.compile(r"[ \t\r\n]")
_ASCII_DECIMAL = re.compile(r"[0-9]+")


@dataclass(frozen=True)
class AlasDormConfigSnapshot:
    collect: bool
    feed: bool
    feed_order: tuple[int, ...]


def parse_alas_dorm_feed_filter(value: object) -> tuple[int, ...]:
    """Return a unique, known food priority list using ALAS separators."""

    # ``ConfigUpdater.parse_value`` canonicalizes a numeric textarea value to
    # ``int`` before ``RewardDorm.run`` receives it.  A one-item filter such
    # as the UI value ``"1000"`` must therefore remain usable on the real
    # original ALAS configuration path; ``Filter.load`` itself already treats
    # that exact integer as the corresponding text token.
    if type(value) is int and value in DORM_FOOD_VALUES:
        return (value,)
    if type(value) is not str:
        raise SemanticGateClosed("Dorm.FeedFilter must be a string")
    normalized = _DORM_FILTER_WHITESPACE.sub("", value)
    normalized = _DORM_FILTER_SEPARATOR.sub(">", normalized)
    tokens = normalized.split(">")
    if not normalized or any(not token for token in tokens):
        raise SemanticGateClosed("Dorm.FeedFilter must not contain empty entries")
    order = []
    for token in tokens:
        if _ASCII_DECIMAL.fullmatch(token) is None:
            raise SemanticGateClosed("Dorm.FeedFilter entries must be decimal food values")
        amount = int(token)
        if token != str(amount) or amount not in DORM_FOOD_VALUES:
            raise SemanticGateClosed("Dorm.FeedFilter contains an unsupported food value")
        if amount in order:
            raise SemanticGateClosed("Dorm.FeedFilter contains a duplicate food value")
        order.append(amount)
    return tuple(order)


def validate_alas_dorm_config(
    *, collect: object, feed: object, feed_filter: object
) -> AlasDormConfigSnapshot:
    """Validate Dorm fields before scope entry, navigation, or resource use."""

    if type(collect) is not bool:
        raise SemanticGateClosed("Dorm.Collect must be a bool")
    if type(feed) is not bool:
        raise SemanticGateClosed("Dorm.Feed must be a bool")
    return AlasDormConfigSnapshot(
        collect=collect,
        feed=feed,
        # ALAS does not consume this filter when feeding is disabled.  An old
        # saved filter must not prevent collection or furniture handling.
        feed_order=parse_alas_dorm_feed_filter(feed_filter) if feed else (),
    )
