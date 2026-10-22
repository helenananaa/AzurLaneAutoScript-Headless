from types import SimpleNamespace
import pytest
from alas_headless import AlasSemanticAdapter, SemanticGateClosed
from alas_headless.adapter.semantic.contracts import AlasSemanticUnmapped
from tests.semantic_support.observer_fixtures import (
    FakeBackend, make_button, make_oracle, make_text, make_ui)

ROOT = 'UICamera/Canvas/UIMain/WorldBossUI(Clone)/pages/ArchivesWorldBossDetailUI(Clone)/'


def backend():
    b = FakeBackend([make_button('list_btn', ROOT+'list_btn')])
    b.ui = make_ui([make_text('1200000/1600000', ROOT+'hp/Text')])
    return b


@pytest.mark.parametrize('name', ['FLEET_CHECK', 'EXERCISE_CHECK', 'DORM_CHECK', 'GUILD_CHECK', 'TACTICAL_CHECK', 'MUNITIONS_CHECK', 'DOCK_CHECK', 'STORAGE_CHECK', 'GOTO_MAIN_WHITE', 'RPG_HOME', 'WITHDRAW', 'CAMPAIGN_WITHDRAW_CONFIRM', 'MAP_PREPARATION', 'FLEET_PREPARATION', 'RAID_FLEET_PREPARATION', 'AUTO_SEARCH_MENU_EXIT', 'AUTO_SEARCH_REWARD'])
def test_other_task_can_discover_dossier_without_optional_auto_field(name):
    b = backend()
    a = AlasSemanticAdapter(make_oracle(b), package_gate=lambda: None)
    assert not a.appear(SimpleNamespace(name=name))
    with pytest.raises(AlasSemanticUnmapped):
        a.click(SimpleNamespace(name='FLEET_CHECK'))
    assert not b.taps


def test_foreign_popup_on_dossier_keeps_campaign_probe_fail_closed():
    b = backend()
    b.buttons['buttons'].append(make_button('confirm', 'root/Msgbox(Clone)/window/button_container/custom_button_1(Clone)'))
    b.buttons['button_count'] += 1
    a = AlasSemanticAdapter(make_oracle(b), package_gate=lambda: None)
    with pytest.raises(SemanticGateClosed):
        a.appear(SimpleNamespace(name='CAMPAIGN_WITHDRAW_CONFIRM'))
    assert not b.taps


@pytest.mark.parametrize('change', ['hp', 'generation', 'duplicate'])
def test_unknown_or_obscured_dossier_does_not_authorize_passive_absence(change):
    b = backend()
    if change == 'hp': b.ui['texts'][0]['text'] = 'unknown'
    if change == 'generation': b.ui['generation'] += 3
    if change == 'duplicate':
        b.buttons['buttons'].append(dict(b.buttons['buttons'][0]))
        b.buttons['button_count'] += 1
    a = AlasSemanticAdapter(make_oracle(b), package_gate=lambda: None)
    with pytest.raises(SemanticGateClosed):
        a.appear(SimpleNamespace(name='FLEET_CHECK'))
    assert not b.taps
