"""Native non-port intent projection, typed input and task isolation."""

import copy
import math
import pytest

from alas_headless import SemanticGateClosed
from alas_headless.oracle.errors import SemanticViewportReanchorRequired
from tests.test_semantic_oracle_opsi_port_geometry import fixture
from tests.semantic_support.observer_fixtures import make_ui, make_text, make_button, make_buttons, make_image


def native_fixture():
    backend, oracle = fixture()
    row = dict(name='map-projection', path='WorldMap3D/entity/Plane/PointerInfo/GetMapScreenPos',
               world_center=[268, 421, 0], screen=[528, 289, 100], truncated=False,
               plane_hit=True, ui_clear=True, plane_instance_id=55, input_point=[528, 289])
    backend.ui['globe_geometry']['objects'] = [row]
    request = backend.request
    def projected(line):
        if line.startswith('GET /v1/globe-projection '):
            backend.ui['generation'] += 1
            backend.buttons['generation'] = backend.ui['generation']
            return {'status': 'ok', 'scope': 'read-only-map-projection'}
        return request(line)
    oracle._request = projected
    return backend, oracle, row


def test_native_projection_accepts_offscreen_observation_but_not_input():
    backend, oracle, row = native_fixture()
    row.update(screen=[-351, 123, 130], input_point=None, plane_hit=False)
    point = oracle.operation_siren_globe_map_projection((268, 421))
    assert (point.x, point.y) == (-351, 123)
    with pytest.raises(SemanticGateClosed, match='not actionable'):
        oracle.click_operation_siren_globe_map_zone('西大陆架D', (268, 421))
    assert backend.taps == []


def test_native_float32_rounding_preserves_the_same_area_intent():
    backend, oracle, row = native_fixture()
    row['world_center'][0] = 268.100006
    assert oracle.operation_siren_globe_map_projection((268.1, 421)).x == 528
    assert backend.taps == []


def test_camera_drift_requests_reanchor_without_input():
    backend, oracle, row = native_fixture()
    row.update(screen=[54, 625, 100], input_point=[54, 625])
    with pytest.raises(SemanticViewportReanchorRequired):
        oracle.click_operation_siren_globe_map_zone('zone', (268, 421))
    assert backend.taps == []


@pytest.mark.parametrize('case', ['other_intent', 'duplicate', 'truncated', 'obscured', 'no_plane', 'invalid_screen'])
def test_native_projection_rejects_unproven_input(case):
    backend, oracle, row = native_fixture()
    if case == 'other_intent': row['world_center'] = [269, 421, 0]
    if case == 'duplicate': backend.ui['globe_geometry']['objects'].append(copy.deepcopy(row))
    if case == 'truncated': backend.ui['globe_geometry']['truncated'] = True
    if case == 'obscured': row['ui_clear'] = False
    if case == 'no_plane': row['plane_hit'] = False
    if case == 'invalid_screen': row['screen'][0] = math.nan
    with pytest.raises(SemanticGateClosed):
        oracle.click_operation_siren_globe_map_zone('西大陆架D', (268, 421))
    assert backend.taps == []


@pytest.mark.parametrize('selected', ['西大陆架D', '西大陆架C'])
def test_native_selection_has_one_input_and_exact_named_postcondition(selected):
    backend, oracle, row = native_fixture()
    def select():
        backend.ui = make_ui([make_text(selected + '-安全海域',
            'root/SVFloatPanel(Clone)/point/line/bg/title/name/subText')], generation=12)
    backend.on_tap = select
    if selected == '西大陆架D':
        assert oracle.click_operation_siren_globe_map_zone(selected, (268, 421)).semantic_id == 'os/globe/zone/select'
    else:
        with pytest.raises(SemanticGateClosed, match='different zone'):
            oracle.click_operation_siren_globe_map_zone('西大陆架D', (268, 421))
    assert backend.taps == [(528, 289)]


def test_nonport_capability_failure_keeps_port_observation_available():
    backend, oracle = fixture()
    request = backend.request
    oracle._request = lambda line: ({'status': 'bad-request'}
        if line.startswith('GET /v1/globe-projection ') else request(line))
    with pytest.raises(SemanticGateClosed):
        oracle.operation_siren_globe_map_projection((268, 421))
    assert oracle.operation_siren_globe_port_projection(2).x == 528
    assert backend.taps == []


@pytest.mark.parametrize('clears', [True, False])
def test_globe_swipe_waits_for_loading_without_input_under_blocker(clears):
    backend, oracle = fixture()
    oracle.operation_siren_globe_drag_owned = lambda *args: True
    back = backend.buttons['buttons'][0]
    loading = make_button('Loading(Clone)', 'root/Overlay/UIOverlay/Loading(Clone)')
    backend.buttons = make_buttons([back, loading])
    if clears:
        backend.buttons = make_buttons([back], generation=11)
        backend.buttons_sequence = [make_buttons([back, loading]), make_buttons([back], generation=11)]
        backend.on_swipe = lambda: setattr(backend, 'buttons', make_buttons([back], generation=12))
        receipt = oracle.operation_siren_globe_swipe((200, 300), (500, 400), 300)
        assert receipt.post_generation == 12
        assert len(backend.swipes) == 1
        assert backend.swipes[0][-1] == 2000
    else:
        with pytest.raises(SemanticGateClosed, match='loading'):
            oracle.operation_siren_globe_swipe((200, 300), (500, 400), 300)
        assert backend.swipes == []


@pytest.mark.parametrize('clear', [True, False])
def test_unpin_uses_proven_native_plane_when_ports_are_unavailable(clear):
    backend, oracle, row = native_fixture()
    oracle.operation_siren_globe_drag_owned = lambda *args: True
    row['ui_clear'] = clear
    row['ui_top_path'] = 'WorldMap3D/entity/Plane' if clear else 'Overlay/popup'
    backend.ui['images'] = [make_image('root/SVFloatPanel(Clone)/point', 'click_point_safe')]
    backend.ui['image_count'] = 1
    oracle.operation_siren_globe_state = lambda: None
    def unpinned():
        backend.ui = make_ui([], generation=12)
        backend.ui_sequence = [make_ui([], generation=11), make_ui([], generation=12)]
        backend.buttons['generation'] = 12
        backend.snapshot['generation'] = 12
    backend.on_swipe = unpinned
    if clear:
        receipt = oracle.operation_siren_globe_unpin()
        assert receipt.semantic_id == 'os/globe/zone/unpin'
        assert len(backend.swipes) == 1
    else:
        with pytest.raises(SemanticGateClosed, match='unobscured typed plane'):
            oracle.operation_siren_globe_unpin()
        assert backend.swipes == []


def test_transient_globe_identity_retries_only_read_projection():
    from unittest.mock import Mock
    backend,oracle,row=native_fixture()
    oracle._sleep=lambda _:None
    oracle.operation_siren_globe_visible=Mock(side_effect=[False,True])
    point=oracle.operation_siren_globe_map_projection((268,421))
    assert point.x==528 and oracle.operation_siren_globe_visible.call_count==2
    assert backend.taps==backend.swipes==[]


def test_absent_globe_identity_remains_closed_without_input_or_projection():
    from unittest.mock import Mock
    backend,oracle,row=native_fixture()
    oracle._sleep=lambda _:None
    oracle.operation_siren_globe_visible=Mock(return_value=False)
    oracle._request=Mock()
    with pytest.raises(SemanticGateClosed,match='globe identity is absent'):
        oracle.operation_siren_globe_map_projection((268,421))
    assert oracle.operation_siren_globe_visible.call_count==4
    oracle._request.assert_not_called()
    assert backend.taps==backend.swipes==[]


@pytest.mark.parametrize('persistent', [False, True])
def test_zone_selection_recaptures_incoherent_pair_before_any_input(persistent):
    from dataclasses import replace
    backend, oracle, _ = native_fixture()
    original_projection = oracle._operation_siren_globe_map_projection_record
    original_state = oracle.read_state
    pending = [False]
    pairs = [0]
    def projection(area, **kwargs):
        result = original_projection(area, **kwargs)
        pairs[0] += 1
        pending[0] = True
        return result
    def state(**kwargs):
        value = original_state(**kwargs)
        if pending[0]:
            pending[0] = False
            assert kwargs == {'check_foreground': False}
            if persistent or pairs[0] == 1:
                return replace(value, generation=value.generation + 3)
        return value
    oracle._operation_siren_globe_map_projection_record = projection
    oracle.read_state = state
    def select():
        backend.ui = make_ui([make_text('西大陆架D-安全海域',
            'root/SVFloatPanel(Clone)/point/line/bg/title/name/subText')],
            generation=backend.ui['generation'] + 1)
    backend.on_tap = select
    if persistent:
        with pytest.raises(SemanticGateClosed, match='not coherent'):
            oracle.click_operation_siren_globe_map_zone('西大陆架D', (268,421))
        assert pairs[0] == 4
        assert backend.taps == []
    else:
        oracle.click_operation_siren_globe_map_zone('西大陆架D', (268,421))
        assert pairs[0] == 2
        assert backend.taps == [(528,289)]


@pytest.mark.parametrize('case', ['unselected', 'loading', 'partial', 'ambiguous-title'])
def test_missed_selection_hands_back_only_complete_unselected_globe(case):
    from alas_headless.oracle.errors import SemanticGlobeSelectionMissed
    backend, oracle, _ = native_fixture()
    def advance(_):
        backend.ui['generation'] += 1
        backend.buttons['generation'] = backend.ui['generation']
    oracle._sleep = advance
    def miss():
        backend.ui = make_ui([], generation=backend.ui['generation'] + 1)
        if case == 'loading':
            backend.buttons['buttons'].append(make_button('Loading(Clone)', 'root/Overlay/UIOverlay/Loading(Clone)'))
            backend.buttons['button_count'] = len(backend.buttons['buttons'])
        if case == 'partial': backend.ui['image_truncated'] = True
        if case == 'ambiguous-title':
            backend.ui['texts'] = [make_text('', 'root/SVFloatPanel(Clone)/point/line/bg/title/name/subText')]
    backend.on_tap = miss
    if case == 'unselected':
        with pytest.raises(SemanticGlobeSelectionMissed, match='produced no pin'):
            oracle.click_operation_siren_globe_map_zone('西大陆架D', (268,421))
    else:
        with pytest.raises(SemanticGateClosed) as caught:
            oracle.click_operation_siren_globe_map_zone('西大陆架D', (268,421))
        assert not isinstance(caught.value, SemanticGlobeSelectionMissed)
    assert backend.taps == [(528,289)]
