import copy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from alas_headless import AlasSemanticAdapter, AlasSemanticUnmapped, SemanticGateClosed
from alas_headless.semantic_oracle import SemanticOracle, OracleFingerprint
from tests.semantic_support.observer_fixtures import (
    FakeBackend, make_button, make_oracle, make_text, make_ui)


PROBES = ('CAMPAIGN_WITHDRAW_CONFIRM', 'WITHDRAW', 'MAP_PREPARATION',
          'FLEET_PREPARATION', 'RAID_FLEET_PREPARATION', 'AUTO_SEARCH_MENU_EXIT',
          'AUTO_SEARCH_REWARD', 'GET_MISSION', 'GET_ITEMS_1', 'GET_ITEMS_2',
          'GET_ITEMS_3', 'GET_SHIP')
ROOT = 'root/UICamera/Canvas/UIMain/CourtYardUI(Clone)/main/'


def baseline():
    backend = FakeBackend([make_button('decorate_btn',
        ROOT + 'bottomPanel/bottomright/decorate_btn')])
    backend.ui = make_ui([make_text(text, ROOT + path) for text, path in (
        ('6/6', 'bottomPanel/bottomleft/train_btn/Text'),
        ('39966/40000', 'bottomPanel/bottomleft/feed_btn/Text'),
        ('454', 'topPanel/btns/topright/comfortable/Text'),
        ('1F', 'topPanel/btns/topright/switch/Text'),
        ('', 'bottomPanel/bottomleft/feed_btn/time'))])
    return backend, make_oracle(backend)


@pytest.mark.parametrize('probe', PROBES)
@pytest.mark.parametrize('drift', [False, True])
def test_unowned_complete_dorm_summary_owns_unrelated_passive_absence(probe, drift):
    backend, oracle = baseline()
    if drift:
        backend.buttons['buttons'].reverse()
        backend.ui['texts'].reverse()
        backend.ui['new_optional_export'] = {'supported': False}
    adapter = AlasSemanticAdapter(oracle, lambda: None)
    assert adapter._dorm_context is None and adapter._campaign_context is None
    assert adapter.appear(SimpleNamespace(name=probe)) is False
    assert adapter.appear(SimpleNamespace(name='DORM_CHECK')) is True
    assert backend.taps == backend.swipes == []


@pytest.mark.parametrize('case', ['unknown', 'covered', 'foreign-package', 'stale'])
def test_incomplete_or_unproven_page_does_not_hide_unknown_probe(case):
    backend, oracle = baseline()
    if case == 'unknown':
        backend.buttons['buttons'][0]['path'] = 'unknown/decorate_btn'
    elif case == 'covered':
        backend.buttons['buttons'].append(make_button('custom_button_1(Clone)',
            'root/Msgbox(Clone)/window/button_container/custom_button_1(Clone)'))
        backend.buttons['button_count'] += 1
    elif case == 'foreign-package':
        backend.snapshot['package'] = 'foreign.package'
    else:
        backend.snapshot['age_ms'] = oracle.fingerprint.max_age_ms + 1
    adapter = AlasSemanticAdapter(oracle, lambda: None)
    if case == 'stale':
        # Presence dispatch can conservatively report False for stale state;
        # the typed classifier and real input must retain the stale refusal.
        with pytest.raises(SemanticGateClosed, match='snapshot is stale'):
            adapter._appear_priority('CAMPAIGN_WITHDRAW_CONFIRM')
        with pytest.raises(SemanticGateClosed, match='snapshot is stale'):
            adapter.click(SimpleNamespace(name='CAMPAIGN_WITHDRAW_CONFIRM'))
    else:
        with pytest.raises((AlasSemanticUnmapped, SemanticGateClosed)):
            adapter.appear(SimpleNamespace(name='CAMPAIGN_WITHDRAW_CONFIRM'))
    assert backend.taps == backend.swipes == []


@pytest.mark.parametrize('case', ['missing-summary', 'duplicate-summary'])
def test_unrelated_summary_drift_does_not_enable_campaign_input(case):
    backend, oracle = baseline()
    if case == 'missing-summary':
        backend.ui['texts'].pop(); backend.ui['text_count'] -= 1
    else:
        backend.ui['texts'].append(copy.deepcopy(backend.ui['texts'][0]))
        backend.ui['text_count'] += 1
    adapter = AlasSemanticAdapter(oracle, lambda: None)
    # Existing page-shell absence still recognizes this unrelated probe.
    # Incomplete food metadata must never authorize a withdrawal action.
    assert adapter.appear(SimpleNamespace(name='CAMPAIGN_WITHDRAW_CONFIRM')) is False
    with pytest.raises(SemanticGateClosed, match='withdrawal target is not actionable'):
        adapter.click(SimpleNamespace(name='CAMPAIGN_WITHDRAW_CONFIRM'))
    assert backend.taps == backend.swipes == []


def test_retained_r73_failure_frame_has_complete_unowned_dorm_summary():
    source = Path(__file__).resolve().parents[1] / 'artifacts/continuity-20261004/goal-scheduler-r73.json'
    if not source.exists():
        pytest.skip('retained live r73 frame unavailable')
    rows = json.loads(source.read_text(encoding='utf-8-sig'))['tasks']
    failed = next(t['failed_presence'] for t in rows
        if t.get('failed_presence', {}).get('name') == 'CAMPAIGN_WITHDRAW_CONFIRM')
    backend = FakeBackend([])
    backend.snapshot = failed['state']['snapshot']
    backend.buttons = failed['state']['buttons_snapshot']
    backend.ui = failed['ui']['snapshot']
    oracle = SemanticOracle(backend.request, backend.foreground_component, backend.tap,
        OracleFingerprint(package=backend.snapshot['package'], component=backend.foreground,
            driver_revision=backend.snapshot['driver_revision'], expected_pid=backend.snapshot['pid']),
        sleep=lambda _: None)
    adapter = AlasSemanticAdapter(oracle, lambda: None)
    assert oracle._dorm_state_once().food == 39948
    assert adapter.appear(SimpleNamespace(name='CAMPAIGN_WITHDRAW_CONFIRM')) is False
    assert adapter.appear(SimpleNamespace(name='DORM_CHECK')) is True
    assert backend.taps == []
