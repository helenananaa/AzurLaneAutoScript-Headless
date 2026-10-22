import copy
import json
from pathlib import Path

import pytest
from alas_headless import AlasSemanticAdapter, SemanticGateClosed
from alas_headless.adapter.semantic.dispatch_result import UNHANDLED
from tests.semantic_support.observer_fixtures import FakeBackend, make_button, make_oracle, make_ui
from tests.semantic_support.oracle_cases import GuildSemanticOracleTestsSupport


def scene():
    root = 'OverlayCamera/Overlay/UIMain/'
    backend = FakeBackend([make_button('back', root+'blur_panel/adapt/top/back', raycast_top=None)])
    toggles, images = GuildSemanticOracleTestsSupport._guild_nav('battle')
    backend.ui = make_ui([], toggles=toggles, images=images)
    adapter = AlasSemanticAdapter(make_oracle(backend), package_gate=lambda: None)
    return backend, adapter


def test_complete_guild_page_owns_notice_absence_after_entry_timer_expires():
    backend, adapter = scene()
    backend.ui['toggles'].reverse()
    backend.ui['extra_field'] = 'harmless upstream drift'
    assert adapter._main_guild_entry_until == 0
    assert adapter.appear('GET_MISSION') is False
    assert not backend.taps


@pytest.mark.parametrize('change', ['missing_nav', 'duplicate_nav', 'duplicate_back',
    'modal', 'urgent_notice', 'stale', 'foreground', 'split'])
def test_guild_absence_does_not_hide_an_unproven_or_obscured_notice(change):
    backend, adapter = scene()
    if change == 'missing_nav': backend.ui['toggles'].pop()
    elif change == 'duplicate_nav': backend.ui['toggles'].append(copy.deepcopy(backend.ui['toggles'][0]))
    elif change == 'duplicate_back': backend.buttons['buttons'].append(copy.deepcopy(backend.buttons['buttons'][0]))
    elif change in ('modal', 'loading'):
        path = ('OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/button_container/custom_button_1(Clone)'
                if change == 'modal' else 'OverlayCamera/Overlay/UIOverlay/Loading(Clone)')
        backend.buttons['buttons'].append(make_button('blocker', path))
    elif change == 'urgent_notice': adapter.oracle._campaign_urgent_notice_matches = lambda state: True
    elif change == 'stale': backend.snapshot['age_ms'] = 99999
    elif change == 'foreground': backend.foreground = 'com.android.settings/.Settings'
    else: backend.ui['generation'] = 13
    backend.buttons['button_count'] = len(backend.buttons['buttons'])
    backend.ui['toggle_count'] = len(backend.ui['toggles'])
    try:
        result = adapter._appear_priority('GET_MISSION')
    except SemanticGateClosed:
        pass
    else:
        assert result is UNHANDLED
    assert not backend.taps


def test_known_loading_yields_the_notice_probe_without_hiding_a_foreign_modal():
    backend, adapter = scene()
    backend.buttons['buttons'].append(make_button('loading', 'OverlayCamera/Overlay/UIOverlay/Loading(Clone)'))
    backend.buttons['button_count'] += 1
    assert adapter.appear('GET_MISSION') is False
    backend.buttons['buttons'].append(make_button('confirm', 'OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/button_container/custom_button_1(Clone)'))
    backend.buttons['button_count'] += 1
    assert adapter._appear_priority('GET_MISSION') is UNHANDLED
    assert not backend.taps


@pytest.mark.parametrize('loading', [False, True])
@pytest.mark.parametrize('name', ['MONTHLY_PASS_NOTICE', 'BATTLE_PASS_NOTICE', 'BATTLE_PASS_NEW_SEASON'])
def test_complete_guild_owns_native_main_notice_absence(loading, name):
    backend, adapter = scene()
    if loading:
        backend.buttons['buttons'].append(make_button('loading', 'OverlayCamera/Overlay/UIOverlay/Loading(Clone)'))
        backend.buttons['button_count'] += 1
    assert adapter.appear(name) is False
    backend.buttons['buttons'].append(make_button('confirm', 'OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/button_container/custom_button_1(Clone)'))
    backend.buttons['button_count'] += 1
    assert adapter._appear_priority(name) is UNHANDLED
    assert not backend.taps


@pytest.mark.parametrize('capture', ['retained_screenshot_at_session_entry', 'retained_screenshot_before_diagnostic_reads'])
def test_actual_r111_guild_loading_notice_probe_can_continue_without_input(capture):
    from alas_headless.semantic_oracle import OracleFingerprint
    from alas_headless.adapter.frame import _FrameBoundSemanticOracle
    path = Path(__file__).resolve().parents[1] / 'artifacts/continuity-20261004/goal-scheduler-r111.json'
    if not path.exists(): pytest.skip('retained r111 frame unavailable')
    row = json.loads(path.read_text(encoding='utf8'))['tasks'][-2]
    projections = row['failed_presence'][capture]['frame']['projections']
    backend = FakeBackend([])
    backend.snapshot, backend.buttons, backend.ui = (projections[n] for n in ('snapshot', 'buttons', 'ui'))
    oracle = _FrameBoundSemanticOracle(backend.request, backend.foreground_component, backend.tap,
        OracleFingerprint(package=backend.snapshot['package'], component=backend.foreground,
            driver_revision=backend.snapshot['driver_revision'], expected_pid=backend.snapshot['pid']), frame_guard=lambda: None)
    adapter = AlasSemanticAdapter(oracle, lambda: None, frame_observation_oracle=lambda: oracle)
    assert oracle.guild_page_mounted()
    assert adapter.appear('MONTHLY_PASS_NOTICE') is False and not backend.taps


def test_r100_later_guild_diagnostic_proves_absence_without_becoming_the_failed_frame():
    path = Path(__file__).resolve().parents[1]/'artifacts/continuity-20261004/goal-scheduler-r100.json'
    if not path.exists(): pytest.skip('retained r100 diagnostic unavailable')
    diagnostic = json.loads(path.read_text(encoding='utf8'))['tasks'][0]['failure_observation']
    backend = FakeBackend(diagnostic['state']['buttons_snapshot']['buttons'])
    ui = diagnostic['ui']
    backend.ui = make_ui([item['raw'] for item in ui['texts']],
        toggles=[item['raw'] for item in ui['toggles']],
        images=[item['raw'] for item in ui['images']])
    adapter = AlasSemanticAdapter(make_oracle(backend), package_gate=lambda: None)
    assert adapter.appear('GET_MISSION') is False
    assert not backend.taps


@pytest.mark.parametrize('capture',['retained_screenshot_at_session_entry','retained_screenshot_before_diagnostic_reads'])
def test_r103_actual_retained_loading_screenshots_yield_to_native_navigation(capture):
    from alas_headless.semantic_oracle import SemanticOracle, OracleFingerprint
    from alas_headless.adapter.frame import _FrameBoundSemanticOracle
    path=Path(__file__).resolve().parents[1]/'artifacts/continuity-20261004/goal-scheduler-r103.json'
    if not path.exists():pytest.skip('retained r103 actual screenshot unavailable')
    original=json.loads(path.read_text(encoding='utf8'))['tasks'][0]['failed_presence'][capture]['frame']['projections']
    backend=FakeBackend([])
    backend.snapshot=original['snapshot'];backend.buttons=original['buttons'];backend.ui=original['ui']
    fingerprint=OracleFingerprint(package=backend.snapshot['package'],component=backend.foreground_component(),
        driver_revision=backend.snapshot['driver_revision'],expected_pid=backend.snapshot['pid'])
    oracle=_FrameBoundSemanticOracle(backend.request,backend.foreground_component,backend.tap,fingerprint,frame_guard=lambda:None)
    adapter=AlasSemanticAdapter(oracle,package_gate=lambda:None)
    assert oracle.guild_page_mounted()
    assert [b.blocker_id for b in oracle._blocking_rules(oracle.read_state(),'ui/absence-probe')]==['loading']
    assert adapter.appear('GET_MISSION') is False
    assert not backend.taps
