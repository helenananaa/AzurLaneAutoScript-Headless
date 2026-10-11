"""Complete empty dossier ownership survives native task cleanup."""
import copy
import json
from pathlib import Path

import pytest

from alas_headless import AlasSemanticAdapter, AlasSemanticUnmapped, SemanticGateClosed
from alas_headless.adapter.frame import _FrameBoundSemanticOracle
from alas_headless.semantic_oracle import OracleFingerprint
from tests.semantic_support.observer_fixtures import FakeBackend, make_button, make_oracle
from tests.test_meta_dossier_empty import dossier_backend


@pytest.mark.parametrize('metadata', [False, True])
def test_inherited_complete_empty_dossier_allows_native_unrelated_page_probes(metadata):
    backend = dossier_backend()
    if metadata:
        backend.snapshot['future_optional_metadata'] = {'v': 2}
        backend.buttons['buttons'].reverse()
        backend.ui['images'].reverse()
        backend.ui['texts'].reverse()
    adapter = AlasSemanticAdapter(make_oracle(backend), package_gate=lambda: None)
    adapter._frame_or_live_observation_oracle = lambda: adapter.oracle
    assert not adapter._meta_beacon_active and not adapter._meta_assist_active
    for name in ('FLEET_CHECK', 'WITHDRAW', 'CAMPAIGN_WITHDRAW_CONFIRM', 'MAP_PREPARATION',
                 'FLEET_PREPARATION', 'RAID_FLEET_PREPARATION', 'AUTO_SEARCH_REWARD',
                 'AUTO_SEARCH_MENU_EXIT', 'GOTO_MAIN_WHITE', 'RPG_HOME'):
        assert adapter.appear(name) is False
        with pytest.raises((SemanticGateClosed, AlasSemanticUnmapped)):
            adapter.click(name)
    assert not backend.taps


@pytest.mark.parametrize('case', ['stale', 'pid', 'duplicate', 'malformed', 'missing', 'incoherent'])
def test_incomplete_or_unsafe_dossier_does_not_supply_passive_page_identity(case):
    backend = dossier_backend()
    if case == 'stale':
        backend.snapshot['age_ms'] = 99999
    elif case == 'pid':
        backend.snapshot['pid'] += 1
    elif case == 'duplicate':
        backend.buttons['buttons'].append(copy.deepcopy(backend.buttons['buttons'][0]))
        backend.buttons['button_count'] += 1
    elif case == 'incoherent':
        backend.ui['generation'] += 3
    else:
        for text in backend.ui['texts']:
            if text['path'].endswith('progress/value'):
                if case == 'missing':
                    text['active_in_hierarchy'] = False
                else:
                    text['text'] = 'unknown'
    oracle = make_oracle(backend)
    adapter = AlasSemanticAdapter(oracle, package_gate=lambda: None)
    adapter._frame_or_live_observation_oracle = lambda: oracle
    with pytest.raises(SemanticGateClosed):
        adapter._meta_dossier_allows_passive_page_probe()
    assert not backend.taps


def test_foreign_modal_is_not_hidden_by_a_complete_empty_dossier_underlay():
    backend = dossier_backend()
    backend.buttons['buttons'].append(make_button('custom_button_1(Clone)',
        'OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/button_container/custom_button_1(Clone)'))
    backend.buttons['button_count'] += 1
    adapter = AlasSemanticAdapter(make_oracle(backend), package_gate=lambda: None)
    adapter._frame_or_live_observation_oracle = lambda: adapter.oracle
    assert not adapter._meta_dossier_allows_passive_page_probe()
    assert not backend.taps


@pytest.mark.parametrize('key', ['retained_screenshot_at_session_entry', 'retained_screenshot_before_diagnostic_reads'])
def test_actual_r115_daily_inherited_frame_recovers_only_passive_absence(key):
    path = Path(__file__).resolve().parents[1] / 'artifacts/continuity-20261004/goal-r115-daily-inherited-empty-dossier-failure-r1.json'
    if not path.exists():
        pytest.skip('local actual failure unavailable; portable baseline cases remain active')
    projections = json.loads(path.read_text(encoding='utf8'))['native_row']['failed_presence'][key]['frame']['projections']
    backend = FakeBackend([])
    backend.snapshot, backend.buttons, backend.ui = (projections[k] for k in ('snapshot','buttons','ui'))
    fp = OracleFingerprint(package=backend.snapshot['package'], component=backend.foreground,
        expected_pid=backend.snapshot['pid'], driver_revision=backend.snapshot['driver_revision'])
    oracle = _FrameBoundSemanticOracle(backend.request,backend.foreground_component,backend.tap,fp,frame_guard=lambda:None)
    adapter = AlasSemanticAdapter(oracle,package_gate=lambda:None)
    adapter._frame_or_live_observation_oracle = lambda: oracle
    assert adapter.appear('FLEET_CHECK') is False
    assert adapter._goto_main_target() == 'meta/home'
    assert not adapter._meta_beacon_active and not adapter._meta_assist_active
    assert not backend.taps
