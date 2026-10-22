"""A stale native entry request acknowledges only a proven accepted arrival."""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from alas_headless import AlasSemanticAdapter, SemanticGateClosed
from tests.test_meta_dossier_sync import backend, ROOT
from tests.semantic_support.observer_fixtures import make_button, make_buttons, make_text, make_ui, make_oracle


def arrival(b, *, generation=11):
    root = ROOT.replace('ArchivesWorldBossEmptyUI', 'ArchivesWorldBossListUI')
    b.snapshot['generation'] = generation
    b.buttons = make_buttons([make_button('back', root+'blur_panel/adapt/top/back', raycast_top=None)], generation=generation)
    b.ui = make_ui([make_text('53590', root+'main/award/pt/Text'),
                   make_text('同步值(53590/70000)', root+'main/list/scrollrect/content/0/underway/label')], generation=generation)


def entered():
    b = backend()
    a = AlasSemanticAdapter(make_oracle(b), package_gate=lambda: None)
    a.begin_meta_beacon()
    b.on_tap = lambda: arrival(b)
    first = a.click(SimpleNamespace(name='DOSSIER_REWARD_ENTER'))
    return b, a, first


def test_old_entry_request_acknowledges_complete_new_page_without_second_tap():
    b, a, first = entered()
    assert a.click(SimpleNamespace(name='DOSSIER_REWARD_ENTER')) is first
    assert len(b.taps) == 1
    assert a._meta_dossier_sync_open_receipt is None
    assert a.appear(SimpleNamespace(name='DOSSIER_REWARD_CHECK'))


@pytest.mark.parametrize('change', ['unknown_counter', 'covered', 'foreign', 'generation_gap', 'stale'])
def test_accepted_entry_does_not_make_unknown_or_stale_arrival_safe(change):
    b, a, first = entered()
    if change == 'unknown_counter': b.ui['texts'][0]['text'] = 'unknown'
    if change == 'covered': b.buttons['buttons'][0]['raycast_top'] = False
    if change == 'foreign':
        b.buttons['buttons'].append(make_button('custom_button_1(Clone)',
            'OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/button_container/custom_button_1(Clone)'))
        b.buttons['button_count'] += 1
    if change == 'generation_gap': b.ui['generation'] += 3
    if change == 'stale':
        for frame in (b.snapshot, b.buttons, b.ui): frame['generation'] = first.generation
    with pytest.raises(SemanticGateClosed): a.click(SimpleNamespace(name='DOSSIER_REWARD_ENTER'))
    assert len(b.taps) == 1


def test_sync_page_without_accepted_entry_cannot_acknowledge_a_missing_control():
    b = backend(); arrival(b)
    a = AlasSemanticAdapter(make_oracle(b), package_gate=lambda: None); a.begin_meta_beacon()
    with pytest.raises(SemanticGateClosed): a.click(SimpleNamespace(name='DOSSIER_REWARD_ENTER'))
    assert not b.taps


def test_entry_receipt_cannot_cross_native_task_ownership():
    b, a, _ = entered(); a.end_meta_beacon(); a.begin_meta_beacon()
    with pytest.raises(SemanticGateClosed): a.click(SimpleNamespace(name='DOSSIER_REWARD_ENTER'))
    assert len(b.taps) == 1


def test_retained_r65_arrival_is_complete_and_acknowledges_only_prior_entry():
    path = Path(__file__).resolve().parents[1]/'artifacts/continuity-20261004/goal-scheduler-r65.json'
    if not path.exists(): pytest.skip('retained r65 arrival unavailable')
    frame = json.loads(path.read_text(encoding='utf8'))['tasks'][-1]['failure_observation']
    b, a, first = entered()
    b.snapshot = frame['state']['snapshot']; b.buttons = frame['state']['buttons_snapshot']; b.ui = frame['ui']['snapshot']
    # Static replay has no advancing exporter. Preserve content; align endpoint
    # generations and fixture fingerprint only, without touching the receipt.
    for value in (b.snapshot, b.buttons, b.ui):
        value['generation'] = b.ui['generation']
        value['pid'] = a.oracle.fingerprint.expected_pid
        value['driver_revision'] = a.oracle.fingerprint.driver_revision
    assert a.click(SimpleNamespace(name='DOSSIER_REWARD_ENTER')) is first
    assert a.oracle.meta_dossier_sync_points() == 60090
    assert len(b.taps) == 1
