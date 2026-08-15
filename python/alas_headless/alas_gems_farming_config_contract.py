"""Fail-closed contract for pinned ALAS GemsFarming settings."""

from __future__ import annotations

from dataclasses import dataclass

from .semantic_oracle import SemanticGateClosed


GEMS_FARMING_CHANGE_FLAGSHIPS = frozenset(("ship", "ship_equip"))
GEMS_FARMING_CHANGE_VANGUARDS = frozenset(("disabled", "ship", "ship_equip"))
GEMS_FARMING_COMMON_CVS = frozenset(("any", "langley", "bogue", "ranger", "hermes"))
GEMS_FARMING_COMMON_DDS = frozenset(("any", "favourite", "aulick_or_foote", "cassin_or_downes", "z20_or_z21"))


@dataclass(frozen=True)
class AlasGemsFarmingConfigSnapshot:
    change_flagship: str
    common_cv: str
    change_vanguard: str
    common_dd: str
    commission_limit: bool


def validate_alas_gems_farming_config(
    *,
    change_flagship: object,
    common_cv: object,
    change_vanguard: object,
    common_dd: object,
    commission_limit: object,
) -> AlasGemsFarmingConfigSnapshot:
    """Admit declared GemsFarming settings before campaign or dock work."""

    for name, value, allowed in (
        ("GemsFarming.ChangeFlagship", change_flagship, GEMS_FARMING_CHANGE_FLAGSHIPS),
        ("GemsFarming.CommonCV", common_cv, GEMS_FARMING_COMMON_CVS),
        ("GemsFarming.ChangeVanguard", change_vanguard, GEMS_FARMING_CHANGE_VANGUARDS),
        ("GemsFarming.CommonDD", common_dd, GEMS_FARMING_COMMON_DDS),
    ):
        if type(value) is not str or value not in allowed:
            raise SemanticGateClosed(name + " is outside the pinned enum")
    if type(commission_limit) is not bool:
        raise SemanticGateClosed("GemsFarming.CommissionLimit must be a boolean")
    return AlasGemsFarmingConfigSnapshot(
        change_flagship=change_flagship,
        common_cv=common_cv,
        change_vanguard=change_vanguard,
        common_dd=common_dd,
        commission_limit=commission_limit,
    )
