"""The reviewed personal META underlay cannot block its exact information modal."""
import pytest
from alas_headless import SemanticGateClosed
from tests.test_game_tips_loading_presence import host
from tests.semantic_support.observer_fixtures import make_button


def current_fixture(drift=False):
    backend, oracle, adapter = host(drift, 'meta-precombat-automation-info-r179.json')
    original = backend.request
    def request(line):
        value = original(line)
        if line == 'GET /v1/ui\n':
            # Simulate the subsequent state publication reaching the UI clock.
            # Replaying the older state forever after a newer UI is invalid;
            # the retained adjacent live endpoint payloads remain untouched.
            for part in (backend.snapshot, backend.buttons):
                part['generation'] = max(part['generation'], backend.ui['generation'])
        return value
    oracle._request = request
    return backend, oracle, adapter


@pytest.mark.parametrize('drift', [False, True])
def test_actual_current_beacon_underlay_allows_exact_information_acknowledgement(drift):
    backend, oracle, _ = current_fixture(drift)
    assert oracle.combat_automation_info_visible()
    def closed():
        for part in (backend.snapshot, backend.buttons, backend.ui):
            part['generation'] = 7040
        backend.buttons['buttons'] = [b for b in backend.buttons['buttons'] if '/Msgbox(Clone)/' not in b['path']]
        backend.buttons['button_count'] = len(backend.buttons['buttons'])
        backend.ui['texts'] = [t for t in backend.ui['texts'] if '/Msgbox(Clone)/' not in t['path']]
        backend.ui['text_count'] = len(backend.ui['texts'])
    backend.on_tap = closed
    receipt = oracle.click_combat_automation_info()
    assert receipt.semantic_id == 'os/precombat/info/confirm'
    assert len(backend.taps) == 1
    assert oracle.daily_precombat_visible()


@pytest.mark.parametrize('case', ['loading', 'different-underlay', 'foreign-text', 'covered', 'stale', 'no-precombat'])
def test_personal_meta_underlay_never_bypasses_other_information_guards(case):
    backend, oracle, _ = current_fixture()
    if case == 'loading':
        backend.buttons['buttons'].append(make_button('Loading(Clone)', 'OverlayCamera/Overlay/UIOverlay/Loading(Clone)'))
    elif case == 'different-underlay':
        for b in backend.buttons['buttons']:
            b['path'] = b['path'].replace('CurrentWorldBossDetailUI(Clone)', 'CurrentWorldBossEmptyUI(Clone)')
    elif case == 'foreign-text':
        next(t for t in backend.ui['texts'] if t['path'].endswith('/help_panel/list/help_tpl'))['text'] = '是否购买资源？'
    elif case == 'covered':
        next(b for b in backend.buttons['buttons'] if b['name'] == 'custom_button_1(Clone)')['raycast_top'] = False
    elif case == 'stale':
        backend.snapshot['age_ms'] = 10001
    else:
        backend.buttons['buttons'] = [b for b in backend.buttons['buttons'] if '/PreCombatUI(Clone)/' not in b['path']]
    backend.buttons['button_count'] = len(backend.buttons['buttons'])
    with pytest.raises(SemanticGateClosed):
        oracle.click_combat_automation_info()
    assert not backend.taps
