"""Actual loading entry plus controlled clear/unsafe Academy return variants."""
import copy

import pytest

from alas_headless import AlasSemanticUnmapped, SemanticGateClosed
from tests.test_game_tips_loading_presence import host
from tests.semantic_support.observer_fixtures import make_button, make_snapshot, make_buttons, make_ui


def academy(drift=False, clear=True):
    b, o, a = host(drift, 'academy-entry-loading-r132.json')
    if clear:
        b.buttons['buttons'] = [v for v in b.buttons['buttons'] if v['name'] != 'Loading(Clone)']
        b.buttons['button_count'] = len(b.buttons['buttons'])
        # Controlled completion of the loading transition restores back's
        # raycast; the retained entry remains untouched on disk.
        next(v for v in b.buttons['buttons'] if v['name'] == 'back')['raycast_top'] = None
    return b, o, a


@pytest.mark.parametrize('drift', [False, True])
def test_actual_academy_loading_yields_native_page_scan(drift):
    b, o, a = academy(drift, clear=False)
    assert o.read_state().generation == 148359
    assert a.appear('FLEET_CHECK') is False
    assert a.appear('ACADEMY_CHECK') is False
    with pytest.raises((SemanticGateClosed, AlasSemanticUnmapped)):
        a.click('GOTO_MAIN')
    assert b.taps == []


@pytest.mark.parametrize('drift', [False, True])
def test_clear_academy_original_home_edge_reaches_main_once(drift):
    b, o, a = academy(drift)
    assert a.appear('ACADEMY_CHECK')
    def arrive():
        g = b.snapshot['generation'] + 1
        b.snapshot = make_snapshot(generation=g)
        b.snapshot.update(package=o.fingerprint.package, pid=o.fingerprint.expected_pid,
                          driver_revision=o.fingerprint.driver_revision)
        b.buttons = make_buttons([
            make_button('battle', 'root/frame/right/1/battle'),
            make_button('formation', 'root/frame/right/1/formation'),
        ], generation=g)
        b.buttons.update(package=o.fingerprint.package, pid=o.fingerprint.expected_pid,
                         driver_revision=o.fingerprint.driver_revision)
        b.ui = make_ui([], generation=g)
        b.ui.update(package=o.fingerprint.package, pid=o.fingerprint.expected_pid,
                    driver_revision=o.fingerprint.driver_revision)
    b.on_tap = arrive
    receipt = a.click('GOTO_MAIN')
    assert receipt.semantic_id == 'academy/page/back'
    assert len(b.taps) == 1
    assert o.main_page_visible()


@pytest.mark.parametrize('case', ['foreign-modal', 'duplicate-back', 'wrong-label', 'truncated', 'foreign-package', 'point-outside', 'covered-back'])
def test_academy_return_rejects_unsafe_or_unproven_input(case):
    b, o, a = academy()
    back = next(v for v in b.buttons['buttons'] if v['name'] == 'back')
    if case == 'foreign-modal':
        b.buttons['buttons'].append(make_button('confirm', 'root/UIOverlay/Msgbox(Clone)/confirm'))
    elif case == 'duplicate-back':
        b.buttons['buttons'].append(copy.deepcopy(back))
    elif case == 'wrong-label':
        next(v for v in b.ui['texts'] if v['text'] == '补给商店')['text'] = 'unrelated'
    elif case == 'truncated':
        b.buttons['truncated'] = True
    elif case == 'foreign-package':
        b.snapshot['package'] = 'unrelated.package'
    elif case == 'covered-back':
        back['raycast_top'] = False
    else:
        back['adb_point']['x'] = 4000
    b.buttons['button_count'] = len(b.buttons['buttons'])
    with pytest.raises((SemanticGateClosed, AlasSemanticUnmapped)):
        a.click('GOTO_MAIN')
    assert b.taps == []
