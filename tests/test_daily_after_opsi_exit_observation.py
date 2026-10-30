"""A proven Daily destination must own its original detail probes."""
import json
import time
from pathlib import Path
from types import SimpleNamespace
import pytest
from alas_headless import AlasSemanticAdapter, SemanticGateClosed
from tests.semantic_support.observer_fixtures import FakeBackend, make_button, make_oracle

ROOT = 'UICamera/Canvas/UIMain/DailyLevelUI(Clone)/'


def make_case(change=None):
    records = [make_button('back_button',ROOT+'blur_panel/adapt/top/back_button',raycast_top=None),
               make_button('info',ROOT+'desc_panel/main_mask/main/scrollview/content/stagetpl(Clone)/info',raycast_top=None)]
    if change == 'duplicate': records.append(dict(records[0]))
    if change == 'missing': records = []
    if change in ('foreign','loading'):
        path = ('OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/button_container/cancel_button'
                if change == 'foreign' else 'OverlayCamera/Overlay/UIOverlay/Loading(Clone)')
        records.append(make_button('blocker',path))
    backend = FakeBackend(records)
    if change == 'stale': backend.snapshot['age_ms'] = backend.buttons['age_ms'] = 99999
    if change == 'foreground': backend.foreground = 'com.android.settings/.Settings'
    adapter = AlasSemanticAdapter(make_oracle(backend),package_gate=lambda:None)
    adapter._operation_siren_entry_transition_until = time.monotonic()+30
    return backend,adapter


def test_exact_daily_details_end_the_previous_opsi_observation_lease():
    backend,adapter = make_case()
    assert adapter.oracle.daily_navigation_visible()
    assert not adapter.oracle.daily_entry_visible()
    assert adapter.appear(SimpleNamespace(name='DAILY_ENTER_CHECK')) is True
    assert adapter._operation_siren_entry_transition_until == 0
    assert backend.taps == []


@pytest.mark.parametrize('change',['duplicate','missing','foreign','loading','stale','foreground'])
def test_unproven_daily_destination_cannot_end_an_opsi_lease(change):
    backend,adapter = make_case(change)
    before = adapter._operation_siren_entry_transition_until
    try: adapter._operation_siren_allows_passive_probe()
    except SemanticGateClosed: pass
    assert adapter._operation_siren_entry_transition_until == before
    assert backend.taps == []


def test_real_r203_expanded_card_reaches_existing_daily_detail_probe():
    source = Path(__file__).resolve().parents[1]/'artifacts/semantic-cn-original-daily-r203-20261002.json'
    if not source.exists():pytest.skip('retained r203 failure frame unavailable')
    failure=json.loads(source.read_text(encoding='utf-8'))['failure_observation']
    backend=FakeBackend(failure['state']['buttons_snapshot']['buttons'])
    raw=failure['ui']['snapshot']
    for key in ('texts','images','toggles','text_count','image_count','toggle_count'):
        backend.ui[key]=raw[key]
    adapter=AlasSemanticAdapter(make_oracle(backend),package_gate=lambda:None)
    adapter._operation_siren_entry_transition_until=time.monotonic()+30
    assert adapter.appear(SimpleNamespace(name='DAILY_ENTER_CHECK')) is True
    assert backend.taps == []
