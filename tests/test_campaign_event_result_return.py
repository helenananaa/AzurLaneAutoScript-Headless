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


def test_native_stage_detection_closes_after_event_result_return():
    backend, adapter, session = host()
    method = native('EnemySearchingHandler', 'is_in_stage_page', 'module/handler/enemy_searching.py',
                    CAMPAIGN_CHECK='CAMPAIGN_CHECK', EVENT_CHECK='EVENT_CHECK', SP_CHECK='SP_CHECK')
    handler = SimpleNamespace(appear=lambda button, **kwargs: session.appear(button),
        is_stage_page_has_entrance=adapter.oracle.event_campaign_stage_selector_visible)
    handler.is_in_stage_page = lambda: method(handler)
    is_in_stage = native('EnemySearchingHandler', 'is_in_stage', 'module/handler/enemy_searching.py')
    assert is_in_stage(handler)
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
