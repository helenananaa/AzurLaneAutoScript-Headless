"""Actual updated ActivityMainUI keeps native page discovery and return."""
import copy
import pytest
from alas_headless import SemanticGateClosed
from tests.test_game_tips_loading_presence import host
from tests.semantic_support.observer_fixtures import make_button


@pytest.mark.parametrize('legacy', [False, True])
def test_retained_sign_page_reaches_native_page_graph_and_typed_back(legacy):
    backend, oracle, adapter = host(fixture='month-sign-renamed-back-r177.json')
    back = next(b for b in backend.buttons['buttons'] if b['name'] == 'btnBack')
    if legacy:
        back['name'] = 'back_btn'
        back['path'] = back['path'].removesuffix('btnBack') + 'back_btn'
    adapter.begin_tactical()
    assert adapter.appear('FLEET_CHECK') is False
    assert adapter.appear('EVENT_LIST_CHECK') is True
    assert adapter._goto_main_target() == 'event-list/page/back'
    receipt = oracle.click('event-list/page/back')
    assert receipt.path == back['path']
    assert backend.taps == [(57, 54)]


@pytest.mark.parametrize('failure', ['covered', 'disabled', 'duplicate', 'foreign-path', 'foreign-package', 'foreground', 'stale', 'modal'])
def test_renamed_back_keeps_input_safety(failure):
    backend, oracle, _ = host(fixture='month-sign-renamed-back-r177.json')
    back = next(b for b in backend.buttons['buttons'] if b['name'] == 'btnBack')
    if failure == 'covered': back['raycast_top'] = False
    elif failure == 'disabled': back['active_and_enabled'] = False
    elif failure == 'duplicate': backend.buttons['buttons'].append(copy.deepcopy(back))
    elif failure == 'foreign-path': back['path'] = 'root/UnrelatedUI/btnBack'
    elif failure == 'foreign-package': backend.snapshot['package'] = 'unrelated.package'
    elif failure == 'foreground': backend.foreground = 'unrelated.package/OtherActivity'
    elif failure == 'stale': backend.snapshot['age_ms'] = 10001
    else: backend.buttons['buttons'].append(make_button('custom_button_1(Clone)',
        'root/OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/button_container/custom_button_1(Clone)'))
    backend.buttons['button_count'] = len(backend.buttons['buttons'])
    with pytest.raises(SemanticGateClosed): oracle.click('event-list/page/back')
    assert not backend.taps
