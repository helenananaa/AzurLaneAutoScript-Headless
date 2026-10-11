"""Fail-closed contract for ALAS Commission selection configuration."""

from __future__ import annotations

from dataclasses import dataclass
import re

from .semantic_oracle import SemanticGateClosed


COMMISSION_PRESETS = (
    "cube",
    "cube_24h",
    "chip",
    "chip_24h",
    "oil",
    "custom",
)
_CATEGORIES = r"(?:major|daily|extra|urgent|night)"
_GENRES = r"(?:resource|chip|event|drill|part|cube|oil|book|retrofit|box|gem|ship)"
_DURATION = r"(?:[0-9]{1,2}:[0-9]{2}|[0-9]{1,2}(?:\.[0-9]{1,2})?)"
_CUSTOM_TOKEN = re.compile(
    rf"(?:shortest|{_CATEGORIES}(?:-?{_GENRES})?(?:-?{_DURATION})?|"
    rf"{_GENRES}(?:-?{_DURATION})?|{_DURATION})",
    re.IGNORECASE,
)
_FILTER_SEPARATOR = re.compile(r"[＞﹥›˃ᐳ❯]")
_FILTER_HYPHEN = re.compile(r"[‐‑‒–—―−－﹣﹘⁃]")
_FILTER_WHITESPACE = re.compile(r"[ \t\r\n]")


@dataclass(frozen=True)
class AlasCommissionConfigSnapshot:
    preset_filter: str
    custom_tokens: tuple[str, ...]
    do_major_commission: bool


def parse_alas_commission_custom_filter(value: object) -> tuple[str, ...]:
    """Validate and normalize an ALAS commission priority expression."""

    if type(value) is not str:
        raise SemanticGateClosed("Commission.CustomFilter must be a string")
    normalized = _FILTER_WHITESPACE.sub("", value)
    normalized = _FILTER_SEPARATOR.sub(">", normalized)
    normalized = _FILTER_HYPHEN.sub("-", normalized)
    tokens = normalized.split(">")
    if not normalized or any(not token for token in tokens):
        raise SemanticGateClosed("Commission.CustomFilter contains an empty entry")
    if any(_CUSTOM_TOKEN.fullmatch(token) is None for token in tokens):
        raise SemanticGateClosed("Commission.CustomFilter contains an unsupported entry")
    return tuple(token.lower() for token in tokens)


def validate_alas_commission_config(
    *, preset_filter: object, custom_filter: object, do_major_commission: object
) -> AlasCommissionConfigSnapshot:
    """Validate Commission fields before scope entry, rewards, or dispatch."""

    # The installed ALAS owns preset resolution, including new preset names and
    # its existing fallback to the generated default.  The baseline catalog is
    # qualification metadata, not a runtime allowlist.
    if type(preset_filter) is not str or not preset_filter.strip():
        raise SemanticGateClosed("Commission.PresetFilter must be non-empty text")
    if type(do_major_commission) is not bool:
        raise SemanticGateClosed("Commission.DoMajorCommission must be a bool")
    return AlasCommissionConfigSnapshot(
        preset_filter=preset_filter,
        custom_tokens=(
            parse_alas_commission_custom_filter(custom_filter)
            if preset_filter == "custom"
            else ()
        ),
        do_major_commission=do_major_commission,
    )
