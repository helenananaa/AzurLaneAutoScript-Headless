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


@pytest.mark.parametrize('drift', [False, True])
@pytest.mark.parametrize('case', ['slow-query', 'handoff', 'generation-gap'])
def test_default_ui_capture_keeps_reward_summary_endpoints_adjacent(drift, case):
    page = 'root/Overlay/UIMain/CommissionInfoUI4Mellow(Clone)'
    backend = FakeBackend([make_button('CommissionInfoUI4Mellow(Clone)', page)])
    backend.ui = make_ui([
        make_text('3', page + '/frame/main/content/event/frame/counter/finished/Text'),
        make_text('unrelated', page + '/optional/label')])
    if drift:
        backend.ui['optional_metadata'] = {'new_field': True}
        backend.ui['texts'].reverse()
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
        assert oracle._reward_summary_count_once('commission', 'finished') == 3
        assert len(calls) == 2
    else:
        with pytest.raises(SemanticGateClosed):
            oracle._reward_summary_count_once('commission', 'finished')
    assert not backend.taps


def test_default_ui_capture_rejects_activity_handoff_during_endpoint_request():
    backend, oracle = setup()
    request = oracle._request

    def handoff(line):
        packet = request(line)
        if line == 'GET /v1/ui\n':
            backend.foreground = 'other/app'
        return packet

    oracle._request = handoff
    with pytest.raises(SemanticGateClosed, match='top-resumed'):
        oracle.read_ui_state()
    assert not backend.taps


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
def test_retirement_custom_cap_reader_closes_foreground_after_the_endpoint_pair(case):
    backend = FakeBackend([])
    backend.ui = make_ui([])
    oracle = make_oracle(backend)
    calls = []
    if case == 'generation-gap':
        backend.ui['generation'] = 13
    def foreground():
        calls.append(True)
        if len(calls) > 1:
            backend.ui['generation'] = 13
            if case == 'handoff':
                return 'other/app'
        return oracle.fingerprint.component
    oracle._foreground_component = foreground
    if case == 'slow-query':
        state, ui = oracle._retirement_records()
        assert state.generation == ui.generation == 10
        assert len(calls) == 2
    else:
        with pytest.raises(SemanticGateClosed):
            oracle._retirement_records()
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


@pytest.mark.parametrize('case', ['slow-query', 'handoff', 'generation-gap'])
def test_campaign_precombat_cancel_pairs_before_foreground_recheck(case):
    from tests.semantic_support.observer_fixtures import make_image
    path = 'OverlayCamera/Overlay/UIMain/ChapterPreCombatUI(Clone)/adapt/top/back_btn'
    backend = FakeBackend([make_button('back_btn', path, raycast_top=True)])
    backend.ui = make_ui([], images=[
        make_image(path, 'icon_bg_front_1920'),
        make_image(path + '/mask', 'icon_bg_mask_1920'),
        make_image(path + '/mask/Image', 'back_btn')])
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
        assert oracle.click_campaign_precombat_back().semantic_id == 'campaign/precombat/back'
        assert len(backend.taps) == 1
    else:
        with pytest.raises(SemanticGateClosed):
            oracle.click_campaign_precombat_back()
        assert backend.taps == []


@pytest.mark.parametrize('case', ['slow-query', 'handoff', 'generation-gap'])
def test_campaign_urgent_notice_pairs_before_foreground_recheck(case):
    root = 'OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/'
    backend = FakeBackend([make_button('custom_button_1(Clone)',
        root+'button_container/custom_button_1(Clone)')])
    backend.ui = make_ui([make_text('出现紧急委托《解救商船Ⅰ》', root+'msg_panel/content'),
        make_text('INFORMATION', root+'top/bg/infomation/title_en'),
        make_text('确 定', root+'button_container/custom_button_1(Clone)/pic')])
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
    state = oracle.read_state()
    if case == 'slow-query':
        assert oracle._campaign_urgent_notice_matches(state)
        assert len(calls) == 2
    else:
        with pytest.raises(SemanticGateClosed):
            oracle._campaign_urgent_notice_matches(state)
    assert backend.taps == []


@pytest.mark.parametrize('case', ['slow-query', 'handoff', 'generation-gap'])
def test_campaign_fleet_index_pairs_before_foreground_recheck(case):
    root = 'OverlayCamera/Overlay/UIMain/top/LevelStageView(Clone)'
    backend = FakeBackend([make_button('back_button', root+'/top_stage/back_button')])
    backend.ui = make_ui([make_text('1', root+'/top_stage/msg_panel/fleet_info/number')])
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
        assert oracle.campaign_map_displayed_fleet_index() == 1
        assert len(calls) == 2
    else:
        with pytest.raises(SemanticGateClosed):
            oracle.campaign_map_displayed_fleet_index()
    assert backend.taps == []


@pytest.mark.parametrize('case', ['slow-query', 'handoff', 'generation-gap'])
def test_reward_resource_pairs_before_foreground_recheck(case):
    page = 'root/Overlay/UIMain/CommissionInfoUI4Mellow(Clone)'
    bubble = page+'/frame/resources/canteen/bubble'
    backend = FakeBackend([make_button('CommissionInfoUI4Mellow(Clone)', page, 827, 622),
                           make_button('bubble', bubble, 142, 67)])
    backend.ui = make_ui([make_text('32', bubble+'/Text')])
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
        assert oracle._reward_resource_state_once('oil')[0] == 32
        assert len(calls) == 2
    else:
        with pytest.raises(SemanticGateClosed):
            oracle._reward_resource_state_once('oil')
    assert backend.taps == []
