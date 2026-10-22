"""A later task can inherit the complete META detail without login notices."""
import copy

import pytest

from alas_headless import AlasSemanticUnmapped, SemanticGateClosed
from tests.test_game_tips_loading_presence import host
from tests.semantic_support.observer_fixtures import make_button


@pytest.mark.parametrize('drift', [False, True])
@pytest.mark.parametrize('name', ['MONTHLY_PASS_NOTICE', 'BATTLE_PASS_NOTICE', 'BATTLE_PASS_NEW_SEASON'])
def test_recorded_guild_entry_observes_notice_absence_on_complete_meta_detail(name, drift):
    backend, oracle, adapter = host(drift, 'meta-return-guild-notice-r210.json')
    assert not adapter.meta_beacon_active()
    assert oracle.meta_current_detail_state().current_hp == 372838
    assert adapter.appear(name) is False
    with pytest.raises(AlasSemanticUnmapped):
        adapter.click(name)
    assert not backend.taps


@pytest.mark.parametrize('case', ['modal', 'duplicate-hp', 'foreign', 'stale'])
def test_unknown_or_unsafe_meta_detail_cannot_prove_notice_absence(case):
    backend, _, adapter = host(fixture='meta-return-guild-notice-r210.json')
    if case == 'modal':
        backend.buttons['buttons'].append(make_button('confirm',
            'OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/button_container/custom_button_1(Clone)'))
        backend.buttons['button_count'] += 1
    elif case == 'duplicate-hp':
        backend.ui['texts'].append(copy.deepcopy(next(t for t in backend.ui['texts'] if t['path'].endswith('/hp/Text'))))
        backend.ui['text_count'] += 1
    elif case == 'foreign':
        backend.foreground = 'other/.Activity'
    else:
        backend.snapshot['age_ms'] = 100000
    with pytest.raises((AlasSemanticUnmapped, SemanticGateClosed)):
        adapter._appear_once('MONTHLY_PASS_NOTICE')
    assert not backend.taps
