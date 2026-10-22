import pytest
from alas_headless import SemanticGateClosed
from tests.semantic_support.observer_fixtures import (
    FakeBackend, make_button, make_buttons, make_text, make_ui, make_oracle)

PRE = 'UICamera/Canvas/UIOrigin/PreCombatUI(Clone)/adapt/right/start'
ROOT = 'OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/'

def backend():
    b = FakeBackend([make_button('start', PRE, raycast_top=None),
                     make_button('custom_button_1(Clone)', ROOT+'button_container/custom_button_1(Clone)')])
    b.ui = make_ui([make_text(' 注意，自律战斗时可能出现以下情况', ROOT+'help_panel/list/help_tpl'),
                    make_text('知道了', ROOT+'button_container/custom_button_1(Clone)/pic')])
    return b

def test_exact_one_choice_information_restores_precombat():
    b = backend()
    o = make_oracle(b)
    assert o.combat_automation_info_visible()
    def closed():
        b.snapshot['generation'] = b.ui['generation'] = 11
        b.buttons = make_buttons(b.buttons['buttons'][:1], generation=11)
        b.ui['texts'] = []
    b.on_tap = closed
    assert o.click_combat_automation_info().semantic_id == 'os/precombat/info/confirm'
    assert len(b.taps) == 1

@pytest.mark.parametrize('change', ['foreign', 'choice', 'duplicate', 'raycast', 'generation', 'foreground'])
def test_unknown_or_obscured_information_never_clicks(change):
    b = backend()
    if change == 'foreign': b.ui['texts'][0]['text'] = '是否购买资源？'
    if change == 'choice': b.ui['texts'][1]['text'] = '购买'
    if change == 'duplicate':
        b.buttons['buttons'].append(dict(b.buttons['buttons'][-1]))
        b.buttons['button_count'] += 1
    if change == 'raycast': b.buttons['buttons'][-1]['raycast_top'] = False
    if change == 'generation': b.ui['generation'] += 3
    o = make_oracle(b)
    if change == 'foreground': o._foreground_component = lambda: 'other/app'
    with pytest.raises(SemanticGateClosed): o.click_combat_automation_info()
    assert not b.taps
