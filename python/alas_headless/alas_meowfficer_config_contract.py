"""Fail-closed contract for pinned ALAS Meowfficer settings."""

from __future__ import annotations

from dataclasses import dataclass

from .semantic_oracle import SemanticGateClosed


MEOWFFICER_TRAIN_MODES = frozenset(("seamlessly", "once_a_day"))


@dataclass(frozen=True)
class AlasMeowfficerConfigSnapshot:
    buy_amount: int
    fort_chore_meowfficer: bool
    overflow_coins: int
    train_enable: bool
    train_mode: str | None
    retain_talented_gold: bool | None
    retain_talented_purple: bool | None
    enhance_index: int | None
    max_feed_level: int | None


def validate_alas_meowfficer_config(
    *, buy_amount: object, fort_chore_meowfficer: object, overflow_coins: object,
    train_enable: object, train_mode: object, retain_talented_gold: object,
    retain_talented_purple: object, enhance_index: object, max_feed_level: object,
) -> AlasMeowfficerConfigSnapshot:
    """Admit explicit settings before UI, purchase, training, or config rewrites."""
    if type(buy_amount) is not int or not 0 <= buy_amount <= 15:
        raise SemanticGateClosed("Meowfficer.BuyAmount must be an integer from 0 to 15")
    if type(overflow_coins) is not int or overflow_coins < -1:
        raise SemanticGateClosed("Meowfficer.OverflowCoins must be -1 or a non-negative integer")
    for name, value in (("Meowfficer.FortChoreMeowfficer", fort_chore_meowfficer), ("MeowfficerTrain.Enable", train_enable)):
        if type(value) is not bool:
            raise SemanticGateClosed(name + " must be a boolean")
    # The original run dispatches training, collection and enhancement only
    # inside Train.Enable.  Their saved settings do not affect buying or fort
    # chores when training is disabled.
    if not train_enable:
        return AlasMeowfficerConfigSnapshot(
            buy_amount, fort_chore_meowfficer, overflow_coins, False,
            None, None, None, None, None,
        )
    for name, value in (("MeowfficerTrain.RetainTalentedGold", retain_talented_gold), ("MeowfficerTrain.RetainTalentedPurple", retain_talented_purple)):
        if type(value) is not bool:
            raise SemanticGateClosed(name + " must be a boolean")
    if type(train_mode) is not str or train_mode not in MEOWFFICER_TRAIN_MODES:
        raise SemanticGateClosed("MeowfficerTrain.Mode is outside the pinned enum")
    if type(enhance_index) is not int or not 1 <= enhance_index <= 12:
        raise SemanticGateClosed("MeowfficerTrain.EnhanceIndex must be an integer from 1 to 12")
    # The original enhancement consumer clamps integer values to 1..30.
    # Preserve that ALAS decision instead of rejecting the entire task first.
    if type(max_feed_level) is not int:
        raise SemanticGateClosed("MeowfficerTrain.MaxFeedLevel must be an integer")
    return AlasMeowfficerConfigSnapshot(buy_amount, fort_chore_meowfficer, overflow_coins, train_enable, train_mode, retain_talented_gold, retain_talented_purple, enhance_index, max_feed_level)
