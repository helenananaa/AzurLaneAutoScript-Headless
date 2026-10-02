import ast
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
import numpy as np
import pytest
from alas_headless import SemanticGateClosed
from alas_headless.oracle.errors import SemanticGlobeDragPathUnavailable


def run_camera(points, visible=True):
    source = Path(__file__).resolve().parents[1]/'artifacts/campaign-preparation/upstream/module/os/globe_camera.py'
    node = next(n for n in ast.walk(ast.parse(source.read_text(encoding='utf-8')))
                if isinstance(n, ast.FunctionDef) and n.name == 'globe_in_sight')
    ns = {'np':np, 'GameStuckError':RuntimeError, 'SemanticGateClosed':SemanticGateClosed,
          'SemanticGlobeDragPathUnavailable':SemanticGlobeDragPathUnavailable, 'logger':Mock(),
          'point_in_area':lambda p, area, threshold=0: area[0]<p[0]<area[2] and area[1]<p[1]<area[3]}
    exec(compile(ast.fix_missing_locations(ast.Module(body=[node], type_ignores=[])), str(source), 'exec'), ns)
    adapter = SimpleNamespace(operation_siren_globe_map_projection=Mock(side_effect=points),
                              operation_siren_globe_visible=Mock(return_value=visible))
    device = SimpleNamespace(semantic_adapter=adapter, sleep=Mock(), screenshot=Mock(), swipe_vector=Mock())
    zone = SimpleNamespace(zone_id=121, area_pos=(1834,1149))
    host = SimpleNamespace(device=device, name_to_zone=lambda _:zone)
    return lambda:ns['globe_in_sight'](host,zone), device, adapter


OUT = SimpleNamespace(x=1101,y=97)
IN = SimpleNamespace(x=971,y=269)


def test_one_missed_drag_is_inspected_before_original_path_retry():
    run, d, a = run_camera([OUT, OUT, OUT, OUT, IN, IN, IN])
    run()
    assert d.swipe_vector.call_count == 2
    d.screenshot.assert_called_once()
    a.operation_siren_globe_visible.assert_called_once()


def test_late_motion_after_readonly_inspection_needs_no_second_drag():
    run,d,_ = run_camera([OUT,OUT,IN,IN,IN])
    run()
    assert d.swipe_vector.call_count == 1


@pytest.mark.parametrize('failure', ['missing', 'stale', 'second_miss'])
def test_unavailable_state_or_repeated_nonprogress_stops_input(failure):
    points = [OUT,OUT,OUT,OUT,OUT]
    if failure == 'stale': points[2] = SemanticGateClosed('stale projection')
    run,d,_ = run_camera(points, visible=failure!='missing')
    with pytest.raises((SemanticGateClosed, RuntimeError)):
        run()
    assert d.swipe_vector.call_count == (2 if failure=='second_miss' else 1)


@pytest.mark.parametrize('outcome',['quarter','exhausted','malformed'])
def test_original_camera_can_shorten_a_rejected_half_leg_once(outcome):
    run,d,_ = run_camera([OUT,IN,IN,IN])
    unavailable=SemanticGlobeDragPathUnavailable('complete native proofs reject path')
    d.swipe_vector.side_effect=[unavailable,unavailable,
        None if outcome=='quarter' else unavailable if outcome=='exhausted' else SemanticGateClosed('malformed')]
    if outcome=='quarter':run()
    else:
        with pytest.raises(SemanticGateClosed):run()
    assert d.swipe_vector.call_count == 3
    assert [tuple(call.args[0]) for call in d.swipe_vector.call_args_list] == [(-300,300),(-150,150),(-75,75)]
    assert [call.kwargs['box'] for call in d.swipe_vector.call_args_list] == [(20,220,980,620),(600,220,980,620),(600,220,980,620)]
    d.screenshot.assert_not_called()
