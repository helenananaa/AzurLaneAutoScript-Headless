"""Slow Android foreground inspection stays outside a typed endpoint pair."""
from unittest.mock import Mock

import pytest

from alas_headless.oracle.surfaces import ObservationSurface, RESET_SHOP_ROOT, RESET_SHOP_MESSAGE
from alas_headless.semantic_oracle import SemanticGateClosed
from tests.semantic_support.observer_fixtures import FakeBackend, make_button, make_oracle, make_text, make_ui


def setup():
    backend = FakeBackend([make_button('custom_button_1(Clone)',
        RESET_SHOP_ROOT + 'button_container/custom_button_1(Clone)')])
    backend.ui = make_ui([make_text(RESET_SHOP_MESSAGE, RESET_SHOP_ROOT + 'msg_panel/content')])
    return backend, make_oracle(backend)


def test_shared_prompt_routing_does_not_split_pair_with_slow_foreground_read():
    backend, oracle = setup()
    calls = []
    def foreground():
        calls.append(True)
        if len(calls) > 1:
            backend.ui['generation'] = 13
        return oracle.fingerprint.component
    oracle._foreground_component = foreground
    assert oracle.observation_surface_present(ObservationSurface.RESET_SHOP)
    assert len(calls) == 2
    assert backend.taps == []


@pytest.mark.parametrize('surface', ['entry', 'map'])
@pytest.mark.parametrize('case', ['slow-query', 'handoff', 'generation-gap'])
def test_campaign_grid_pair_excludes_slow_activity_query(surface, case):
    from tests.semantic_support.campaign_fixtures import make_campaign_map_backend
    backend = make_campaign_map_backend(generations=(10,))
    published_ui = backend.ui_sequence[0]
    oracle = make_oracle(backend)
    calls = []
    if case == 'generation-gap':
        published_ui['generation'] = 13
    def foreground():
        calls.append(True)
        if len(calls) > 1:
            published_ui['generation'] = 13
            if case == 'handoff':
                return 'other/app'
        return oracle.fingerprint.component
    oracle._foreground_component = foreground
    def read():
        if surface == 'entry':
            return oracle._campaign_map_entry_state_once()
        return oracle._campaign_map_state_once('12-4', columns=3, rows=2,
            land=((1, 2),), expected_fleet_count=2)
    if case == 'slow-query':
        assert read().generation == 10
        assert len(calls) == 2
    else:
        with pytest.raises(SemanticGateClosed):
            read()
    assert backend.taps == []


def test_shared_prompt_still_rejects_activity_handoff_and_real_generation_gap():
    backend, oracle = setup()
    oracle._foreground_component = Mock(side_effect=[oracle.fingerprint.component, 'other/app'])
    with pytest.raises(SemanticGateClosed, match='activity changed during paired observation'):
        oracle.observation_surface_present(ObservationSurface.RESET_SHOP)
    backend, oracle = setup()
    backend.ui['generation'] = 13
    with pytest.raises(SemanticGateClosed, match='snapshots are not coherent'):
        oracle.observation_surface_present(ObservationSurface.RESET_SHOP)
    assert backend.taps == []


@pytest.mark.parametrize('case', ['slow-query', 'handoff', 'generation-gap'])
def test_campaign_return_page_pairs_before_closing_foreground_check(case):
    root = 'root/UICamera/Canvas/UIMain/LevelMainScene(Clone)/'
    stage = root + 'float/levels/items/Chapter_1204'
    backend = FakeBackend([make_button('back_button', root + 'top/top_chapter/back_button'),
                           make_button('main', stage + '/main')])
    backend.ui = make_ui([
        make_text('马里亚纳风云上', root + 'top/top_chapter/title_chapter/name'),
        make_text('12-4', stage + '/main/info/bk/title_form/title_index'),
        make_text('TF58，翱翔于天际', stage + '/main/info/bk/title_form/title')])
    oracle = make_oracle(backend)
    calls = []
    def foreground():
        calls.append(True)
        if len(calls) > 1:
            backend.ui['generation'] = 13
            if case == 'handoff':
                return 'other/app'
        return oracle.fingerprint.component
    oracle._foreground_component = foreground
    if case == 'generation-gap':
        backend.ui['generation'] = 13
    if case == 'slow-query':
        assert oracle._campaign_page_state_once().stages[0].stage_code == '12-4'
        assert len(calls) == 2
    else:
        with pytest.raises(SemanticGateClosed):
            oracle._campaign_page_state_once()
    assert backend.taps == []
