import copy
import pytest
from alas_headless.semantic_oracle import SemanticGateClosed
from tests.semantic_support.observer_fixtures import FakeBackend, make_button, make_oracle, make_ui, make_text


def fixture():
    backend = FakeBackend([make_button('back_button',
        'root/OverlayCamera/Overlay/UIMain/top/adapt/top_chapter/back_button')])
    backend.ui = make_ui([], generation=10)
    backend.ui['globe_geometry'] = dict(schema='alas-headless.globe-geometry/v1',
        status=1, truncated=False, error_count=0, camera_path='WorldMap3D/Main Camera',
        harmless_new_field=True, objects=[dict(name='port',
            path='WorldMap3D/entity/sprite_scene/port_3/mark_port_1(Clone)/port',
            truncated=False, plane_hit=True, ui_clear=True, plane_instance_id=55,
            input_point=[528, 289], screen=[528, 289, 100], port_anchor=[80, -500, 40])])
    return backend, make_oracle(backend)


def test_exact_port_marker_and_newer_named_postcondition():
    backend, oracle = fixture()
    def selected():
        backend.ui = make_ui([make_text('Gibraltar-safe',
            'root/SVFloatPanel(Clone)/point/line/bg/title/name/subText')], generation=11)
    backend.on_tap = selected
    receipt = oracle.click_operation_siren_globe_port('Gibraltar', 2)
    assert backend.taps == [(528, 289)]
    assert receipt.path.endswith('/port_3/mark_port_1(Clone)/port')

def test_precise_port_dispatch_uses_its_independent_plane_and_ui_proof():
    backend, oracle = fixture()
    marker = backend.ui['globe_geometry']['objects'][0]
    marker.update(plane_hit=False, ui_clear=False, input_point=None,
                  precise_input=dict(point=[528.541199,289.222137],
                      plane_hit=True, ui_clear=True, plane_instance_id=55))
    backend.on_tap = lambda: setattr(backend, 'ui', make_ui([make_text('Gibraltar-safe',
        'root/SVFloatPanel(Clone)/point/line/bg/title/name/subText')], generation=11))
    receipt = oracle.click_operation_siren_globe_port('Gibraltar', 2)
    assert backend.taps == [(528.541199,289.222137)]
    assert (receipt.point.x, receipt.point.y) == backend.taps[0]

@pytest.mark.parametrize('case', ['missing', 'obscured', 'no_hit', 'identity', 'malformed', 'nan', 'offscreen'])
def test_failed_precise_proof_never_falls_back_to_rounded_point(case):
    backend, oracle = fixture()
    proof = dict(point=[528.541199,289.222137], plane_hit=True, ui_clear=True, plane_instance_id=55)
    if case == 'missing': proof = None
    elif case == 'obscured': proof['ui_clear'] = False
    elif case == 'no_hit': proof['plane_hit'] = False
    elif case == 'identity': proof['plane_instance_id'] = 0
    elif case == 'malformed': proof['point'] = [1]
    elif case == 'nan': proof['point'][0] = float('nan')
    else: proof['point'][0] = 1500
    backend.ui['globe_geometry']['objects'][0]['precise_input'] = proof
    with pytest.raises(SemanticGateClosed): oracle.click_operation_siren_globe_port('Gibraltar', 2)
    assert not backend.taps


@pytest.mark.parametrize('case', ['missing', 'duplicate', 'obscured', 'no_hit', 'truncated', 'no_anchor'])
def test_unproven_port_has_no_input(case):
    backend, oracle = fixture()
    geometry = backend.ui['globe_geometry']
    if case == 'missing': geometry['objects'] = []
    if case == 'duplicate': geometry['objects'] += copy.deepcopy(geometry['objects'])
    if case == 'obscured': geometry['objects'][0]['ui_clear'] = False
    if case == 'no_hit': geometry['objects'][0]['plane_hit'] = False
    if case == 'truncated': geometry['truncated'] = True
    if case == 'no_anchor': geometry['objects'][0].pop('port_anchor')
    with pytest.raises(SemanticGateClosed):
        oracle.click_operation_siren_globe_port('Gibraltar', 2)
    assert backend.taps == []


def test_different_selected_name_stops_after_one_input():
    backend, oracle = fixture()
    backend.on_tap = lambda: setattr(backend, 'ui', make_ui([make_text('Brest-safe',
        'root/SVFloatPanel(Clone)/point/line/bg/title/name/subText')], generation=11))
    with pytest.raises(SemanticGateClosed, match='different zone'):
        oracle.click_operation_siren_globe_port('Gibraltar', 2)
    assert len(backend.taps) == 1


def test_offscreen_projection_is_observation_only():
    backend, oracle = fixture()
    marker = backend.ui['globe_geometry']['objects'][0]
    marker.update(screen=[350, 1121, 60], input_point=None, ui_clear=False)
    point = oracle.operation_siren_globe_port_projection(2)
    assert (point.x, point.y) == (350, 1121)
    with pytest.raises(SemanticGateClosed, match='not actionable'):
        oracle.click_operation_siren_globe_port('Gibraltar', 2)
    assert backend.taps == []


def test_optional_texture_diagnostics_do_not_change_port_identity_or_input():
    backend,oracle=fixture()
    backend.ui['globe_geometry']['objects'].append(dict(name='pointer-texture-settings',
        path='WorldMap3D/entity/Plane/PointerInfo/tex/format=RGB24/filterMode=Bilinear/wrapMode=Clamp',
        truncated=False,plane_hit=False,ui_clear=False,input_point=None,screen=None))
    point=oracle.operation_siren_globe_port_projection(2)
    assert (point.x,point.y)==(528,289)
    assert backend.taps==backend.swipes==[]


@pytest.mark.parametrize('alas_id,game_id', [(0, 1), (7, 8)])
def test_port_numbering_preserves_alas_zero_based_metadata(alas_id, game_id):
    backend, oracle = fixture()
    backend.ui['globe_geometry']['objects'][0]['path'] = (
        f'WorldMap3D/entity/sprite_scene/port_{game_id}/mark_port_1(Clone)/port')
    assert oracle.operation_siren_globe_port_projection(alas_id).x == 528


@pytest.mark.parametrize('case', ['unselected', 'loading', 'partial', 'ambiguous-title', 'stale'])
def test_missed_port_returns_to_native_focus_only_for_proven_unselected_globe(case):
    from alas_headless.oracle.errors import SemanticGlobeSelectionMissed
    backend, oracle = fixture()
    def advance(_):
        if case != 'stale':
            backend.ui['generation'] += 1
            backend.buttons['generation'] = backend.ui['generation']
    oracle._sleep = advance
    def miss():
        backend.ui = make_ui([], generation=10)
        if case == 'loading':
            backend.buttons['buttons'].append(make_button('Loading(Clone)', 'root/Overlay/UIOverlay/Loading(Clone)'))
            backend.buttons['button_count'] = len(backend.buttons['buttons'])
        if case == 'partial':
            backend.ui['image_truncated'] = True
        if case == 'ambiguous-title':
            backend.ui['texts'] = [make_text('', 'root/SVFloatPanel(Clone)/point/line/bg/title/name/subText')]
    backend.on_tap = miss
    with pytest.raises(SemanticGateClosed) as caught:
        oracle.click_operation_siren_globe_port('Gibraltar', 2)
    assert isinstance(caught.value, SemanticGlobeSelectionMissed) == (case == 'unselected')
    assert backend.taps == [(528, 289)]
