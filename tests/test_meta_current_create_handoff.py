"""A native cached create decision cannot spend another beacon after creation."""
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from alas_headless import AlasSemanticAdapter, SemanticGateClosed
from alas_headless.semantic_oracle import ActionReceipt
from tests.test_alas_config_branch_compatibility import method
from tests.test_game_tips_loading_presence import host
from tests.semantic_support.observer_fixtures import (
    FakeBackend, make_button, make_text, make_ui, make_oracle,
)


@pytest.mark.parametrize('drift', [False, True])
def test_native_cached_empty_page_decision_reuses_create_on_actual_new_detail(drift):
    backend, oracle, adapter = host(drift, fixture='meta-created-detail-r127.json')
    adapter.begin_meta_beacon()
    assert oracle.meta_current_detail_state().current_hp == 1820000
    previous = ActionReceipt('meta/current/create', 22093, None, None,
        'UICamera/Canvas/UIMain/WorldBossUI(Clone)/pages/CurrentWorldBossEmptyUI(Clone)/useItem/list/tpl')
    adapter._meta_current_create_handoff = (previous, oracle.input_dispatch_count)
    native = method('module/os_ash/meta.py', 'OpsiAshBeacon', '_begin_meta',
        logger=Mock(), ASH_SHOWDOWN='ASH_SHOWDOWN', BEACON_LIST='BEACON_LIST',
        META_BEGIN_ENTRANCE='META_BEGIN_ENTRANCE')
    returned = []
    native_host = SimpleNamespace(config=SimpleNamespace(OpsiAshBeacon_AttackMode='current_dossier'),
        appear=lambda name, **_: name == 'BEACON_LIST', _check_beacon_point=lambda: True,
        device=SimpleNamespace(click=lambda name: returned.append(adapter.click(name))))
    assert native(native_host) is True
    assert returned == [previous]
    assert not backend.taps


@pytest.mark.parametrize('case', ['foreign', 'stale', 'duplicate_detail', 'covered'])
def test_unknown_or_unsafe_detail_does_not_acknowledge_creation(case):
    backend, oracle, adapter = host(fixture='meta-created-detail-r127.json')
    adapter._meta_current_create_handoff = (
        ActionReceipt('meta/current/create', 22093, None, None, 'accepted'), oracle.input_dispatch_count)
    if case == 'foreign': backend.foreground = 'other/.Activity'
    elif case == 'stale': backend.snapshot['age_ms'] = 100000
    elif case == 'duplicate_detail':
        backend.ui['texts'].append(dict(next(x for x in backend.ui['texts'] if x['path'].endswith('/hp/Text'))))
        backend.ui['text_count'] += 1
    else:
        backend.buttons['buttons'].append(make_button('confirm',
            'OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/button_container/custom_button_1(Clone)'))
        backend.buttons['button_count'] += 1
    with pytest.raises(SemanticGateClosed): adapter._click_meta_current_create()
    assert not backend.taps


def test_pending_exact_empty_page_cannot_repeat_create_but_new_flow_can_create():
    root = 'UICamera/Canvas/UIMain/WorldBossUI(Clone)/pages/CurrentWorldBossEmptyUI(Clone)/'
    backend = FakeBackend([make_button('list_btn', root+'list_btn', raycast_top=None),
        make_button('tpl', root+'useItem/list/tpl', raycast_top=None)])
    backend.ui = make_ui([make_text('200/200', root+'progress/value')])
    oracle = make_oracle(backend)
    adapter = AlasSemanticAdapter(oracle, lambda: None)
    adapter.begin_meta_beacon()
    previous = adapter._click_meta_current_create()
    assert adapter._click_meta_current_create() is previous
    assert len(backend.taps) == 1
    adapter.end_meta_beacon()
    adapter.begin_meta_beacon()
    assert adapter._meta_current_create_handoff is None
    assert adapter._click_meta_current_create().semantic_id == 'meta/current/create'
    assert len(backend.taps) == 2
