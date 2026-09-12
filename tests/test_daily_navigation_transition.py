from types import SimpleNamespace
import pytest
from alas_headless import AlasSemanticAdapter, SemanticGateClosed
from tests.semantic_support.adapter_fixtures import FakeOracle


@pytest.mark.parametrize('present,enabled,generation,reuse', [
    (True, True, 11, True), (False, True, 11, False),
    (True, False, 11, False), (True, True, 10, False),
])
def test_daily_repeat_requires_fresh_actionable_destination(present, enabled, generation, reuse):
    o = FakeOracle()
    o.daily_entry_visible = lambda: present and enabled
    o.enabled = lambda target: enabled
    o.read_state = lambda: SimpleNamespace(generation=generation)
    o.input_dispatch_count = 0
    new = SimpleNamespace(generation=12)
    def click():
        o.input_dispatch_count += 1
        return new
    o.click_campaign_daily_entrance = click
    a = AlasSemanticAdapter(o, package_gate=lambda: None)
    prior = SimpleNamespace(generation=10)
    a._daily_entry_receipt = prior
    assert a._click_mapped('CAMPAIGN_MENU_GOTO_DAILY','campaign-menu/daily') is (prior if reuse else new)
    assert o.input_dispatch_count == (0 if reuse else 1)
    a.reset_task_state()
    assert a._daily_entry_receipt is None


@pytest.mark.parametrize('dispatched', [False, True])
def test_daily_race_never_hides_an_input_failure(dispatched):
    o = FakeOracle()
    pages = iter((False, True))
    o.daily_entry_visible = lambda: next(pages)
    o.enabled = lambda target: True
    o.read_state = lambda: SimpleNamespace(generation=11)
    o.input_dispatch_count = 0
    def click():
        o.input_dispatch_count += int(dispatched)
        raise SemanticGateClosed('source is obscured')
    o.click_campaign_daily_entrance = click
    a = AlasSemanticAdapter(o, package_gate=lambda: None)
    prior = SimpleNamespace(generation=10)
    a._daily_entry_receipt = prior
    if dispatched:
        with pytest.raises(SemanticGateClosed):
            a._click_mapped('CAMPAIGN_MENU_GOTO_DAILY','campaign-menu/daily')
    else:
        assert a._click_mapped('CAMPAIGN_MENU_GOTO_DAILY','campaign-menu/daily') is prior


@pytest.mark.parametrize('hit,visible', [(None, True), (True, True), (False, False)])
def test_arrival_observation_is_not_generic_input_authority(hit, visible):
    from tests.semantic_support.observer_fixtures import FakeBackend, make_button, make_oracle
    path = 'UICamera/Canvas/UIMain/DailyLevelUI(Clone)/blur_panel/adapt/top/back_button'
    b = FakeBackend([make_button('back_button',path,raycast_top=hit)])
    o = make_oracle(b)
    assert o.daily_entry_visible() is visible
    b.buttons['buttons'].append(make_button('back_button',path,raycast_top=hit))
    b.buttons['button_count'] += 1
    assert not o.daily_entry_visible()
    assert b.taps == []


def test_daily_page_owns_registry_sweep_without_a_dock_task():
    from tests.semantic_support.observer_fixtures import FakeBackend, make_button, make_oracle
    path = 'UICamera/Canvas/UIMain/DailyLevelUI(Clone)/blur_panel/adapt/top/back_button'
    b = FakeBackend([make_button('back_button',path,raycast_top=None)])
    a = AlasSemanticAdapter(make_oracle(b), package_gate=lambda: None)
    assert a.appear(SimpleNamespace(name='DAILY_CHECK'))
    assert not a.appear(SimpleNamespace(name='DOCK_CHECK'))
    assert not a.appear(SimpleNamespace(name='MAIN_GOTO_CAMPAIGN_WHITE'))
    assert b.taps == []
