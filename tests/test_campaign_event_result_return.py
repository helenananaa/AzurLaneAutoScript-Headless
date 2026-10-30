"""Native event return markers must outlive the completed combat observer."""

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from alas_headless import AlasSemanticAdapter, AlasSemanticSession, SemanticGateClosed
from tests.semantic_support.adapter_cases import AlasSemanticAdapterTestsSupport
from tests.semantic_support.campaign_live_fixtures import native, own_auto_search
from tests.semantic_support.observer_fixtures import FakeBackend, make_button, make_oracle, make_ui


def host(backend=None):
    if backend is None:
        backend = FakeBackend([])
        AlasSemanticAdapterTestsSupport._replace_with_real_event_page(backend)
    oracle = make_oracle(backend)
    adapter = AlasSemanticAdapter(oracle, lambda: None)
    own_auto_search(adapter).stage_code = 't1'
    session = AlasSemanticSession('offline', oracle.fingerprint.driver_revision)
    session.adapter = adapter
    session._live_combat_visible = Mock(return_value=())
    return backend, adapter, session


@pytest.mark.parametrize('marker', ['EVENT_CHECK', 'SP_CHECK'])
def test_completed_event_page_reaches_its_strict_owner(marker):
    backend, _, session = host()
    assert session.appear(marker)
    session._live_combat_visible.assert_not_called()
    assert not backend.taps


@pytest.mark.parametrize('damage', ['result-overlay', 'foreign-modal', 'missing-labels', 'stale', 'foreground'])
def test_event_return_never_promotes_an_obscured_or_unproven_selector(damage):
    backend, _, session = host()
    if damage in ('result-overlay', 'foreign-modal'):
        path = ('OverlayCamera/Overlay/UIMain/LevelStageTotalRewardPanel(Clone)/Window/Fixed/ButtonExit'
                if damage == 'result-overlay' else 'OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/popup')
        backend.buttons['buttons'].append(make_button('ButtonExit' if damage == 'result-overlay' else 'popup', path))
        backend.buttons['button_count'] += 1
    elif damage == 'missing-labels':
        backend.ui['texts'] = []
        backend.ui['text_count'] = 0
    elif damage == 'stale':
        backend.snapshot['age_ms'] = 1_000_000
    else:
        backend.foreground = 'other.package/.OtherActivity'
    for marker in ('EVENT_CHECK', 'SP_CHECK'):
        try:
            assert not session.appear(marker)
        except SemanticGateClosed:
            pass
    assert not backend.taps


@pytest.mark.parametrize('device_kind', ['semantic', 'rendered', 'without-semantic-port'])
def test_native_stage_detection_closes_after_event_result_return(device_kind):
    backend, adapter, session = host()
    method = native('EnemySearchingHandler', 'is_in_stage_page', 'module/handler/enemy_searching.py',
                    CAMPAIGN_CHECK='CAMPAIGN_CHECK', EVENT_CHECK='EVENT_CHECK', SP_CHECK='SP_CHECK')
    # Native handlers inherit a device from ModuleBase. Keep that real host
    # contract when executing its current optional Archives observation hook.
    device = SimpleNamespace()
    archives_probe = Mock(wraps=adapter.war_archives_campaign_visible)
    if device_kind != 'without-semantic-port':
        # This observation-unit fixture has no runtime/frame clock. Exercise
        # the real typed adapter probe through its native callback surface;
        # frame acquisition belongs to session/runtime tests and live cases.
        device.semantic_adapter = (SimpleNamespace(war_archives_campaign_visible=archives_probe)
                                   if device_kind == 'semantic' else None)
    handler = SimpleNamespace(device=device,
        appear=lambda button, **kwargs: session.appear(button),
        is_stage_page_has_entrance=adapter.oracle.event_campaign_stage_selector_visible)
    handler.is_in_stage_page = lambda: method(handler)
    is_in_stage = native('EnemySearchingHandler', 'is_in_stage', 'module/handler/enemy_searching.py')
    assert is_in_stage(handler)
    if device_kind == 'semantic':
        archives_probe.assert_called_once_with()
    else:
        archives_probe.assert_not_called()
    assert not backend.taps


def test_retained_r9_timeout_structure_returns_to_event_page():
    source = Path(__file__).resolve().parents[1] / 'artifacts/full-feature-live-20261024/native-r9.json'
    if not source.exists():
        pytest.skip('private r9 timeout receipt unavailable')
    observed = json.loads(source.read_text(encoding='utf-8'))['tasks'][0]['failure_observation']
    backend = FakeBackend(observed['state']['buttons_snapshot']['buttons'])
    ui = observed['ui']['snapshot']
    backend.ui = make_ui(ui['texts'], images=ui['images'], toggles=ui['toggles'])
    _, adapter, session = host(backend)
    assert adapter.oracle.event_campaign_stage_selector_visible()
    assert session.appear('EVENT_CHECK')
    assert session.appear('SP_CHECK')
    assert not backend.taps


@pytest.mark.parametrize('damage', [None, 'missing-retreat', 'duplicate-back', 'foreign-modal'])
def test_event_reparented_hud_keeps_covered_selector_absent(damage):
    backend, adapter, session = host()
    root = 'UICamera/Canvas/UIMain/LevelMainScene(Clone)/top/LevelStageView(Clone)'
    back = make_button('back_button', root + '/top_stage/back_button')
    retreat = make_button('retreat_button', root + '/bottom_stage/Normal/retreat_button')
    for button in backend.buttons['buttons']:
        if button['path'].endswith('/top/top_chapter/back_button'):
            button['raycast_top'] = False
    backend.buttons['buttons'].append(back)
    if damage != 'missing-retreat':
        backend.buttons['buttons'].append(retreat)
    if damage == 'duplicate-back':
        backend.buttons['buttons'].append(dict(back))
    elif damage == 'foreign-modal':
        backend.buttons['buttons'].append(make_button('popup',
            'OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/popup'))
    backend.buttons['button_count'] = len(backend.buttons['buttons'])
    assert adapter.oracle.campaign_auto_search_map_transition_visible() is (damage is None)
    for marker in ('EVENT_CHECK', 'SP_CHECK'):
        if damage in (None, 'foreign-modal'):
            assert not session.appear(marker)
        else:
            with pytest.raises(SemanticGateClosed):
                session.appear(marker)
    with pytest.raises(SemanticGateClosed):
        session.click('SP_CHECK')
    assert not backend.taps


def test_retained_r10_pre_reward_frame_is_a_passive_hud_transition():
    source = Path(__file__).resolve().parents[1] / 'artifacts/full-feature-live-20261024/native-r10.json'
    if not source.exists():
        pytest.skip('private r10 transition receipt unavailable')
    task = json.loads(source.read_text(encoding='utf-8'))['tasks'][-1]
    frame = task['failed_presence']['retained_screenshot_before_diagnostic_reads']['frame']['projections']
    backend = FakeBackend(frame['buttons']['buttons'])
    ui = frame['ui']
    backend.ui = make_ui(ui['texts'], images=ui['images'], toggles=ui['toggles'])
    _, adapter, session = host(backend)
    assert adapter.oracle.campaign_auto_search_map_transition_visible()
    assert not session.appear('EVENT_CHECK')
    assert not session.appear('SP_CHECK')
    assert not adapter.campaign_auto_search_result_visible()
    assert not backend.taps


def test_uncovered_event_page_wins_over_retained_hud():
    backend, adapter, session = host()
    root = 'UICamera/Canvas/UIMain/LevelMainScene(Clone)/top/LevelStageView(Clone)'
    backend.buttons['buttons'].extend([
        make_button('back_button', root + '/top_stage/back_button'),
        make_button('retreat_button', root + '/bottom_stage/Normal/retreat_button'),
    ])
    backend.buttons['button_count'] = len(backend.buttons['buttons'])
    assert not adapter.oracle.campaign_auto_search_map_transition_visible()
    assert session.appear('EVENT_CHECK')
    assert session.appear('SP_CHECK')
    assert not backend.taps
