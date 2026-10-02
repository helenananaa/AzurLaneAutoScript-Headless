import pytest
from types import SimpleNamespace
from alas_headless import AlasSemanticAdapter, SemanticGateClosed
from tests.semantic_support.observer_fixtures import (
    FakeBackend, make_button, make_image, make_oracle, make_text, make_ui,
)

ROOT = 'UICamera/Canvas/UIMain/WorldBossUI(Clone)/pages/CurrentWorldBossDetailUI(Clone)/'


def backend(*, reward=True, hp=0, sprite='btn_get', raycast=None):
    controls = [('list_btn', 'list_btn')]
    controls += ([('award_btn', 'btns/award_btn')] if reward else
                 [('help_btn', 'btns/help_btn'), ('start_btn', 'btns/start_btn')])
    b = FakeBackend([make_button(n, ROOT+p, raycast_top=raycast) for n, p in controls])
    b.ui = make_ui([make_text(v, ROOT+p) for p, v in (
        ('progress/value', '100/200'), ('point/Text', '3/3'),
        ('hp/Text', f'{hp}/<color=#E31D15>1820000</color>'), ('hp/level/Text', '15'),
    )], images=[make_image(ROOT+'btns/award_btn', sprite)] if reward else [])
    return b


def test_completed_beacon_is_the_original_complete_branch_and_claim():
    b = backend()
    b.ui['images'].append(make_image('UnrelatedNewUI/icon', 'additive'))
    b.ui['image_count'] += 1
    o = make_oracle(b)
    a = AlasSemanticAdapter(o, package_gate=lambda: None)
    assert o.meta_page_visible()
    assert a.appear(SimpleNamespace(name='BEACON_LIST'))
    assert not a.appear(SimpleNamespace(name='HELP_ENTER'))
    assert a.appear(SimpleNamespace(name='BEACON_REWARD'))
    assert a.click(SimpleNamespace(name='BEACON_REWARD')).semantic_id == 'meta/current/reward'
    assert len(b.taps) == 1


@pytest.mark.parametrize('change', ['hp', 'sprite', 'raycast', 'duplicate', 'blocker'])
def test_reward_claim_rejects_wrong_or_obscured_state(change):
    b = backend(hp=1 if change == 'hp' else 0,
                sprite='unknown' if change == 'sprite' else 'btn_get',
                raycast=False if change == 'raycast' else None)
    if change == 'duplicate':
        b.buttons['buttons'].append(dict(b.buttons['buttons'][1]))
        b.buttons['button_count'] += 1
    if change == 'blocker':
        b.buttons['buttons'].append(make_button('confirm', 'root/Msgbox(Clone)/window/button_container/custom_button_1(Clone)'))
        b.buttons['button_count'] += 1
    with pytest.raises(SemanticGateClosed):
        make_oracle(b).click_meta_current_reward()
    assert b.taps == []


def test_normal_attack_detail_remains_available_without_reward():
    b = backend(reward=False, hp=100)
    o = make_oracle(b)
    assert o.meta_current_detail_state().current_hp == 100
    assert not o.meta_current_reward_visible()
    assert b.taps == []


@pytest.mark.parametrize('recover', [True, False])
def test_detail_start_retries_only_full_observation_before_one_input(recover):
    import copy
    b = backend(reward=False, hp=100)
    incoherent = copy.deepcopy(b.ui)
    incoherent['generation'] = 13
    generations = [10, 13] if recover else [10, 13, 16, 19]
    b.snapshot_sequence = [dict(b.snapshot, generation=g) for g in generations]
    b.snapshot['generation'] = b.buttons['generation'] = generations[-1]
    if recover:
        b.ui = dict(b.ui, generation=13)
        b.ui_sequence = [incoherent, copy.deepcopy(b.ui)]
    else:
        b.ui_sequence = [dict(copy.deepcopy(b.ui), generation=g + 3) for g in generations]
    o = make_oracle(b)
    o._sleep = lambda _seconds: None
    if recover:
        assert o.click_meta_current_start().semantic_id == 'meta/current/start'
        assert b.taps == [(640, 360)] and o.input_dispatch_count == 1
    else:
        with pytest.raises(SemanticGateClosed, match='not coherent'):
            o.click_meta_current_start()
        assert b.taps == [] and o.input_dispatch_count == 0


def test_detail_start_keeps_final_input_foreground_check_after_retry():
    from unittest.mock import Mock
    b = backend(reward=False, hp=100)
    o = make_oracle(b)
    read = o._retry_transition_read
    def change_after_proof(reader):
        result = read(reader)
        o._foreground_component = Mock(return_value='other/activity')
        return result
    o._retry_transition_read = change_after_proof
    with pytest.raises(SemanticGateClosed, match='not top-resumed|foreground changed before'):
        o.click_meta_current_start()
    assert b.taps == []


def test_meta_home_recovery_closes_only_the_reviewed_reward_overlay():
    from unittest.mock import Mock
    from tests.semantic_support.adapter_fixtures import FakeOracle
    o = FakeOracle()
    o.award_info_page_visible = Mock(return_value=True)
    o.meta_page_visible = Mock(return_value=True)
    a = AlasSemanticAdapter(o, package_gate=lambda: None)
    a._award_close_target = Mock(return_value='reward/award-info/close')
    for name in ('GOTO_MAIN', 'GOTO_MAIN_WHITE', 'RPG_HOME'):
        assert a._appear_priority(name) is True
    assert o.click_calls == []
    a._click_main('GOTO_MAIN', None)
    assert o.click_calls == ['reward/award-info/close']
    a._award_close_target.return_value = None
    with pytest.raises(SemanticGateClosed):
        a._click_main('GOTO_MAIN', None)
    assert o.click_calls == ['reward/award-info/close']


def test_meta_legacy_safe_area_closes_only_exact_award_target():
    from unittest.mock import Mock
    from tests.semantic_support.adapter_fixtures import FakeOracle
    from alas_headless.adapter.semantic.dispatch_result import UNHANDLED
    o = FakeOracle()
    o.meta_character_sync_page_visible = Mock(return_value=False)
    o.award_info_page_visible = Mock(return_value=True)
    a = AlasSemanticAdapter(o, package_gate=lambda: None)
    a._meta_beacon_active = True
    a._award_close_target = Mock(return_value='reward/award-info/close')
    a._click_priority('CLICK_SAFE_AREA')
    assert o.click_calls == ['reward/award-info/close']
    o.award_info_page_visible.return_value = False
    assert a._click_priority('CLICK_SAFE_AREA') is UNHANDLED
    assert o.click_calls == ['reward/award-info/close']
    a._award_close_target.return_value = None
    o.award_info_page_visible.return_value = True
    with pytest.raises(SemanticGateClosed):
        a._click_priority('CLICK_SAFE_AREA')
    assert o.click_calls == ['reward/award-info/close']


@pytest.mark.parametrize('change', [None, 'stale', 'unknown-page', 'covered'])
def test_meta_reward_close_duplicate_is_one_use_without_input(change):
    from unittest.mock import Mock
    from tests.semantic_support.adapter_fixtures import FakeOracle
    from alas_headless.adapter.semantic.dispatch_result import UNHANDLED
    o = FakeOracle()
    o.meta_character_sync_page_visible = Mock(return_value=False)
    o.award_info_page_visible = Mock(return_value=False)
    o.meta_page_visible = Mock(return_value=change != 'unknown-page')
    o.observation_target_present = Mock(return_value=change == 'covered')
    o.read_state = Mock(return_value=SimpleNamespace(generation=10 if change == 'stale' else 11))
    a = AlasSemanticAdapter(o, package_gate=lambda: None)
    a._meta_beacon_active = True
    prior = SimpleNamespace(generation=10)
    a._meta_reward_close_receipt = prior
    result = a._click_priority('CLICK_SAFE_AREA')
    if change is None:
        assert result is prior
        assert a._click_priority('CLICK_SAFE_AREA') is UNHANDLED
    else:
        assert result is UNHANDLED
    assert not o.click_calls


@pytest.mark.parametrize('foreign_popup', [False, True])
def test_meta_entrance_allows_topmost_award_close_but_not_covered_home(foreign_popup):
    b = FakeBackend([
        make_button('close', 'OverlayCamera/Overlay/UIMain/AwardInfoUI(Clone)/items/close'),
        make_button('btn', 'UICamera/Canvas/UIMain/WorldBossUI(Clone)/pages/WorldBossEntranceUI(Clone)/btn'),
        make_button('option', 'UICamera/Canvas/UIMain/WorldBossUI(Clone)/option'),
    ])
    if foreign_popup:
        b.buttons['buttons'].append(make_button(
            'confirm', 'root/Msgbox(Clone)/window/button_container/custom_button_1(Clone)'))
        b.buttons['button_count'] += 1
    o = make_oracle(b)
    if foreign_popup:
        assert not o.enabled('reward/award-info/close')
        with pytest.raises(SemanticGateClosed):
            o.click('reward/award-info/close')
        assert b.taps == []
        return
    assert o.enabled('reward/award-info/close')
    assert not o.enabled('meta/home')
    o.click('reward/award-info/close')
    assert len(b.taps) == 1
