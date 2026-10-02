from unittest.mock import patch
import pytest
from alas_headless import SemanticGateClosed

from tests.semantic_support.observer_fixtures import (
    FakeBackend, make_button, make_buttons, make_image, make_oracle, make_ui,
)


def setup_unpin():
    b = FakeBackend([make_button('back_button',
        'root/OverlayCamera/Overlay/UIMain/top/adapt/top_chapter/back_button')])
    b.ui = make_ui([], images=[make_image('root/SVFloatPanel(Clone)/point',
        'click_point_safe', {'left':470, 'top':396, 'right':546, 'bottom':455})])
    def marker(name, path, point):
        return dict(name=name, path=path, truncated=False, plane_hit=True,
            ui_clear=True, ui_top_path='WorldMap3D/entity/Plane',
            plane_instance_id=55, input_point=point)
    b.ui['globe_geometry'] = dict(status=1, truncated=False, error_count=0,
        camera_path='WorldMap3D/Main Camera', objects=[
            marker('map-projection', 'WorldMap3D/entity/Plane/PointerInfo/GetMapScreenPos', [508,425]),
            marker('port', 'WorldMap3D/entity/sprite_scene/port_5/port', [693,535])])
    def unpin():
        b.buttons = make_buttons(b.buttons['buttons'], generation=13)
        b.ui = make_ui([], generation=13)
        b.ui_sequence = [make_ui([], generation=12), make_ui([], generation=13)]
    b.on_swipe = unpin
    o = make_oracle(b)
    return b, o


def test_unpin_prefers_owned_anchor_outside_selected_pin():
    b, o = setup_unpin()
    with patch.object(o, 'operation_siren_globe_state'), patch.object(
            o, 'operation_siren_globe_drag_owned', return_value=True) as proof:
        receipt = o.operation_siren_globe_unpin()
    assert receipt.start == (693,535)
    assert b.swipes == [(693,535,743,485,2000)]
    proof.assert_called_once_with((693,535), (743,485))


def test_unpin_rejects_transient_panel_disappearance_after_zone_selection():
    b, o = setup_unpin()
    pin = b.ui['images'][0]
    def select_other_zone():
        b.buttons = make_buttons(b.buttons['buttons'], generation=13)
        b.ui = make_ui([], images=[pin], generation=13)
        b.ui_sequence = [make_ui([], generation=12), b.ui]
    b.on_swipe = select_other_zone
    with patch.object(o, 'operation_siren_globe_state'), patch.object(
            o, 'operation_siren_globe_drag_owned', return_value=True):
        with pytest.raises(SemanticGateClosed, match='unpin was not proven'):
            o.operation_siren_globe_unpin()
    assert len(b.swipes) == 1


def test_unpin_checks_next_native_anchor_before_any_input():
    b, o = setup_unpin()
    with patch.object(o, 'operation_siren_globe_state'), patch.object(
            o, 'operation_siren_globe_drag_owned', side_effect=[False, True]) as proof:
        receipt = o.operation_siren_globe_unpin()
    assert proof.call_args_list[0].args == ((693,535), (743,485))
    assert proof.call_args_list[1].args == ((508,425), (558,375))
    assert receipt.start == (508,425)
    assert b.swipes == [(508,425,558,375,2000)]


def test_unpin_all_native_paths_obscured_has_no_input():
    b, o = setup_unpin()
    with patch.object(o, 'operation_siren_globe_state'), patch.object(
            o, 'operation_siren_globe_drag_owned', return_value=False) as proof:
        with pytest.raises(SemanticGateClosed, match='outside the owned plane'):
            o.operation_siren_globe_unpin()
    assert proof.call_count == 2
    assert b.swipes == []


def test_unpin_unknown_proof_stops_without_trying_another_anchor():
    b, o = setup_unpin()
    with patch.object(o, 'operation_siren_globe_state'), patch.object(
            o, 'operation_siren_globe_drag_owned',
            side_effect=SemanticGateClosed('malformed proof')) as proof:
        with pytest.raises(SemanticGateClosed, match='malformed proof'):
            o.operation_siren_globe_unpin()
    assert proof.call_count == 1
    assert b.swipes == []


def test_transient_empty_native_anchors_retry_read_before_one_input():
    b,o=setup_unpin();complete=b.ui
    import copy
    transient=copy.deepcopy(complete);transient['globe_geometry']['objects']=[]
    b.ui_sequence=[transient,complete]
    with patch.object(o,'operation_siren_globe_state'), patch.object(
            o,'operation_siren_globe_drag_owned',return_value=True):
        receipt=o.operation_siren_globe_unpin()
    assert receipt.start==(693,535)
    assert len(b.swipes)==1


def test_persistent_absent_anchors_remain_closed_without_input():
    b,o=setup_unpin();b.ui['globe_geometry']['objects']=[]
    with patch.object(o,'operation_siren_globe_state'), patch.object(
            o,'operation_siren_globe_drag_owned') as proof:
        with pytest.raises(SemanticGateClosed,match='no unobscured typed plane target'):
            o.operation_siren_globe_unpin()
    proof.assert_not_called()
    assert not b.swipes
