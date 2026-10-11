"""Purchase refusal leaves independent native Meowfficer branches schedulable."""
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from alas_headless import SemanticGateClosed
from alas_headless.adapter import ActionLeaseError
from alas_headless.adapter.semantic.contracts import AlasSemanticActionDeferred
from tests.test_alas_config_branch_compatibility import method


def host(error):
    adapter = SimpleNamespace(buy_meowfficer_boxes=Mock(side_effect=error),
                              admit_meowfficer_training_plan=Mock())
    config = SimpleNamespace(Meowfficer_BuyAmount=15, Meowfficer_OverflowCoins=-1,
        Meowfficer_FortChoreMeowfficer=True, MeowfficerTrain_Enable=True,
        MeowfficerTrain_Mode='once_a_day', MeowfficerTrain_RetainTalentedGold=True,
        MeowfficerTrain_RetainTalentedPurple=True, MeowfficerTrain_EnhanceIndex=1,
        MeowfficerTrain_MaxFeedLevel=30, task_delay=Mock())
    obj = SimpleNamespace(config=config, device=SimpleNamespace(semantic_adapter=adapter),
        meow_get_buy_count=Mock(side_effect=[3, 0]), ui_ensure=Mock(),
        wait_meowfficer_buttons=Mock(), meow_fort=Mock(), meow_train=Mock(),
        meow_enhance=Mock(), meow_is_sunday=lambda: False)
    buy = method('module/meowfficer/buy.py', 'MeowfficerBuy', 'meow_buy', logger=Mock())
    obj.meow_buy = lambda: buy(obj)
    return obj, adapter


def native_run(obj):
    run = method('module/meowfficer/meowfficer.py', 'RewardMeowfficer', 'run',
        page_meowfficer=object(),
        validate_alas_meowfficer_config=lambda **kw: SimpleNamespace(
            buy_amount=15, overflow_coins=-1, fort_chore_meowfficer=True,
            train_enable=True, train_mode='once_a_day'))
    return run(obj)


@pytest.mark.parametrize('error', [
    AlasSemanticActionDeferred('shop.purchase: task action grant is exhausted'), None])
def test_zero_purchase_grant_or_completed_purchase_keeps_native_fort_and_training(error):
    obj, adapter = host(error)
    native_run(obj)
    adapter.buy_meowfficer_boxes.assert_called_once_with(3)
    obj.meow_fort.assert_called_once()
    obj.meow_train.assert_called_once()
    obj.meow_enhance.assert_not_called()
    obj.config.task_delay.assert_called_once_with(minute=(150, 210), server_update=True)


@pytest.mark.parametrize('error', [ActionLeaseError(),
    SemanticGateClosed('meowfficer purchase coin postcondition failed')])
def test_closed_authority_and_uncertain_accepted_purchase_stay_fatal(error):
    obj, adapter = host(error)
    with pytest.raises(type(error)):
        native_run(obj)
    obj.meow_fort.assert_not_called()
    obj.meow_train.assert_not_called()
    obj.config.task_delay.assert_not_called()
