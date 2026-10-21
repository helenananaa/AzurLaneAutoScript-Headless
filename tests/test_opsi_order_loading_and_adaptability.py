from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from alas_headless import AlasSemanticSession,SemanticGateClosed
from alas_headless.oracle.errors import SemanticInputBlocked
from tests.test_game_tips_loading_presence import host


@pytest.mark.parametrize('case', ['ready', 'drift', 'from-loading', 'unsubmitted', 'old', 'foreign', 'covered'])
def test_accepted_entry_yields_to_its_mounted_panel_without_repeating_input(case):
    backend,o,a=host(case=='drift',fixture='opsi-order-inherited-r56.json')
    generation=o.read_state().generation
    a._operation_siren_order_entry_receipt=(None if case=='unsubmitted' else
        SimpleNamespace(generation=generation if case=='old' else generation-5))
    if case=='foreign':backend.snapshot['package']='foreign.package'
    if case=='covered':
        from tests.semantic_support.observer_fixtures import make_button
        backend.buttons['buttons'].append(make_button('Loading(Clone)','OverlayCamera/Overlay/UIOverlay/Loading(Clone)'))
        backend.buttons['button_count']+=1
    error=SemanticInputBlocked('os/map/order',generation,
        ('loading',) if case=='from-loading' else ('operation-siren-order',))
    s=AlasSemanticSession.__new__(AlasSemanticSession)
    s.click=Mock(side_effect=error);s.refresh_frame=Mock();s.open=lambda:a
    if case in ('ready','drift','from-loading'):
        assert s.click_if_present('ORDER_ENTER') is None
    else:
        with pytest.raises(SemanticGateClosed):s.click_if_present('ORDER_ENTER')
    assert not backend.taps

@pytest.mark.parametrize('case',['owned','unsubmitted','old','foreign-blocker','foreign-package'])
def test_only_accepted_order_entry_can_yield_its_loading_to_native_loop(case):
    backend,o,a=host(fixture='opsi-order-entry-loading-r61.json')
    generation=o.read_state().generation
    entry=SimpleNamespace(generation=generation-5)
    a._operation_siren_order_entry_receipt=None if case=='unsubmitted' else entry
    if case=='old':entry.generation=generation
    error=SemanticInputBlocked('os/map/order',generation,('loading',))
    if case=='foreign-blocker':
        from tests.semantic_support.observer_fixtures import make_button
        backend.buttons['buttons'].append(make_button('custom_button_1(Clone)','OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/button_container/custom_button_1(Clone)'));backend.buttons['button_count']+=1
    if case=='foreign-package':backend.snapshot['package']='foreign.package'
    s=AlasSemanticSession.__new__(AlasSemanticSession);s.click=Mock(side_effect=error);s.refresh_frame=Mock();s.open=lambda:a
    if case=='owned':
        assert s.click_if_present('ORDER_ENTER') is None
        s.refresh_frame.assert_called_once()
    else:
        with pytest.raises((SemanticInputBlocked,SemanticGateClosed)):s.click_if_present('ORDER_ENTER')
    assert not backend.taps

@pytest.mark.parametrize('drift',[False,True])
def test_actual_adaptability_info_is_dismissed_by_original_popup_alias(drift):
    backend,o,a=host(drift,'opsi-adaptability-info-r61.json')
    assert o.operation_siren_adaptability_info_visible()
    assert a.appear('POPUP_CONFIRM') and a.appear('POPUP_CONFIRM_UI_ADDITIONAL')
    for name in ('EXERCISE_CHECK','GOTO_MAIN','ORDER_ENTER','RESET_TICKET_POPUP','POPUP_CONFIRM_WITHDRAW'):
        assert not a.appear(name)
    a._fresh_input_oracle=lambda:o
    assert a.click('POPUP_CONFIRM_UI_ADDITIONAL').semantic_id=='os/adaptability/info/confirm'
    assert len(backend.taps)==1

@pytest.mark.parametrize('case',['wrong-name','wrong-description','extra-button','covered','foreign'])
def test_adaptability_confirmation_does_not_accept_other_or_blocked_msgboxes(case):
    backend,o,_=host(fixture='opsi-adaptability-info-r61.json')
    if case=='wrong-name':next(t for t in backend.ui['texts'] if t['path'].endswith('/name_container/name/Text'))['text']='购买物品'
    if case=='wrong-description':next(t for t in backend.ui['texts'] if t['path'].endswith('/display_panel/desc/Text'))['text']='消耗500钻石'
    if case in ('extra-button','covered'):
        from tests.semantic_support.observer_fixtures import make_button
        backend.buttons['buttons'].append(make_button('custom_button_2(Clone)' if case=='extra-button' else 'Loading(Clone)',
            'OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/button_container/custom_button_2(Clone)' if case=='extra-button' else 'OverlayCamera/Overlay/UIOverlay/Loading(Clone)'));backend.buttons['button_count']+=1
    if case=='foreign':backend.foreground='other/.Activity'
    with pytest.raises(SemanticGateClosed):o.click_operation_siren_adaptability_info()
    assert not backend.taps
