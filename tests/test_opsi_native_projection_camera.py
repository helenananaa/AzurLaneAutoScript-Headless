"""Run the original ALAS camera decision for ports and ordinary areas."""
from tests.alas_test_source import patched_alas_root

import ast
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pytest
from alas_headless import SemanticGateClosed
from alas_headless.oracle.errors import SemanticViewportReanchorRequired
from alas_headless.oracle.errors import SemanticGlobeDragPathUnavailable, SemanticGlobeSelectionMissed


@pytest.mark.parametrize('zone_id', [2, 44])
@pytest.mark.parametrize('start', [(-351,123),(336,623)])
def test_original_camera_routes_port_and_native_area_without_other_reader(zone_id,start):
    source = patched_alas_root() / 'module/os/globe_camera.py'
    if not source.exists():
        pytest.skip('materialized patched ALAS tree unavailable')
    node = next(n for n in ast.walk(ast.parse(source.read_text(encoding='utf-8')))
                if isinstance(n, ast.FunctionDef) and n.name == 'globe_in_sight')
    ns = {'np': np, 'GameStuckError': RuntimeError, 'SemanticGlobeDragPathUnavailable': SemanticGlobeDragPathUnavailable,
          'point_in_area': lambda p, area, threshold=5: area[0]-threshold < p[0] < area[2]+threshold and area[1]-threshold < p[1] < area[3]+threshold}
    exec(compile(ast.fix_missing_locations(ast.Module(body=[node], type_ignores=[])), str(source), 'exec'), ns)
    points = [SimpleNamespace(x=start[0], y=start[1]), *[SimpleNamespace(x=528, y=289) for _ in range(3)]]
    port = Mock(side_effect=points if zone_id == 2 else AssertionError('non-port must not enter port reader'))
    native = Mock(side_effect=points if zone_id == 44 else AssertionError('port must keep established reader'))
    adapter = SimpleNamespace(operation_siren_globe_port_projection=port, operation_siren_globe_map_projection=native)
    device = SimpleNamespace(semantic_adapter=adapter, sleep=Mock(), swipe_vector=Mock())
    zone = SimpleNamespace(zone_id=zone_id, area_pos=(268, 421))
    host = SimpleNamespace(device=device, name_to_zone=lambda _: zone)
    ns['globe_in_sight'](host, zone)
    assert device.swipe_vector.call_count == 1
    active, unused = (port, native) if zone_id == 2 else (native, port)
    assert active.call_count == 4
    unused.assert_not_called()


@pytest.mark.parametrize('failure', [SemanticViewportReanchorRequired('moved before input'), SemanticGlobeSelectionMissed('fresh unselected after input'), SemanticGateClosed('different selected zone')])
def test_original_focus_reanchors_only_a_classified_preinput_view_failure(failure):
    source = patched_alas_root() / 'module/os/globe_camera.py'
    node = next(n for n in ast.walk(ast.parse(source.read_text(encoding='utf-8')))
                if isinstance(n, ast.FunctionDef) and n.name == 'globe_focus_to')
    ns = {'SemanticGateClosed': SemanticGateClosed, 'SemanticViewportReanchorRequired': SemanticViewportReanchorRequired, 'SemanticGlobeSelectionMissed': SemanticGlobeSelectionMissed,
          'logger': Mock()}
    exec(compile(ast.fix_missing_locations(ast.Module(body=[node], type_ignores=[])), str(source), 'exec'), ns)
    select = Mock(side_effect=[failure, object()])
    adapter = SimpleNamespace(operation_siren_globe_state=lambda: None, click_operation_siren_globe_map_zone=select)
    zone = SimpleNamespace(zone_id=44, cn='zone', area_pos=(268,421))
    host = SimpleNamespace(name_to_zone=lambda _: zone, device=SimpleNamespace(semantic_adapter=adapter, screenshot=Mock()), globe_in_sight=Mock())
    if isinstance(failure, (SemanticViewportReanchorRequired, SemanticGlobeSelectionMissed)):
        ns['globe_focus_to'](host, zone)
        assert host.globe_in_sight.call_count == select.call_count == 2
        assert host.device.screenshot.call_count == 4
    else:
        with pytest.raises(SemanticGateClosed, match='different selected'):
            ns['globe_focus_to'](host, zone)
        assert host.globe_in_sight.call_count == select.call_count == 1
        assert host.device.screenshot.call_count == 2


@pytest.mark.parametrize('zone_id', [2, 141])
def test_already_selected_zone_refreshes_frame_and_native_unpin_projection(zone_id):
    source = patched_alas_root() / 'module/os/globe_camera.py'
    node = next(n for n in ast.walk(ast.parse(source.read_text(encoding='utf-8')))
                if isinstance(n, ast.FunctionDef) and n.name == 'globe_focus_to')
    ns = {'SemanticGateClosed': SemanticGateClosed, 'SemanticViewportReanchorRequired': SemanticViewportReanchorRequired, 'SemanticGlobeSelectionMissed': SemanticGlobeSelectionMissed, 'logger': Mock()}
    exec(compile(ast.fix_missing_locations(ast.Module(body=[node], type_ignores=[])), str(source), 'exec'), ns)
    zone = SimpleNamespace(zone_id=zone_id, cn='zone', area_pos=(268,421))
    adapter = SimpleNamespace(operation_siren_globe_state=lambda: SimpleNamespace(zone_name='zone'),
        operation_siren_globe_map_projection=Mock(), click_operation_siren_globe_map_zone=Mock(), click_operation_siren_globe_port=Mock())
    device = SimpleNamespace(semantic_adapter=adapter, screenshot=Mock())
    host = SimpleNamespace(name_to_zone=lambda _: zone, device=device, globe_in_sight=Mock())
    ns['globe_focus_to'](host, zone)
    assert device.screenshot.call_count == (2 if zone_id > 7 else 1)
    if zone_id > 7:
        adapter.operation_siren_globe_map_projection.assert_called_once_with(zone.area_pos)
    else:
        adapter.operation_siren_globe_map_projection.assert_not_called()
    adapter.click_operation_siren_globe_map_zone.assert_not_called()
    adapter.click_operation_siren_globe_port.assert_not_called()
    host.globe_in_sight.assert_not_called()


@pytest.mark.parametrize('pinned_id',[2,82])
def test_different_selected_zone_projects_existing_pin_before_unpin(pinned_id):
    source=patched_alas_root() / 'module/os/globe_camera.py'
    node=next(n for n in ast.walk(ast.parse(source.read_text(encoding='utf-8'))) if isinstance(n,ast.FunctionDef) and n.name=='globe_focus_to')
    ns={'SemanticGateClosed':SemanticGateClosed,'SemanticViewportReanchorRequired':SemanticViewportReanchorRequired,'logger':Mock()}
    exec(compile(ast.fix_missing_locations(ast.Module(body=[node],type_ignores=[])),str(source),'exec'),ns)
    pinned=SimpleNamespace(zone_id=pinned_id,cn='existing',area_pos=(872,801))
    target=SimpleNamespace(zone_id=52,cn='next',area_pos=(1000,243))
    events=[]
    adapter=SimpleNamespace(operation_siren_globe_state=lambda:SimpleNamespace(zone_name='existing'),
        operation_siren_globe_map_projection=Mock(side_effect=lambda p:events.append(('project',p))),
        operation_siren_globe_unpin=Mock(side_effect=lambda:events.append(('unpin',))),
        click_operation_siren_globe_map_zone=Mock(side_effect=lambda *p:events.append(('select',p))))
    host=SimpleNamespace(device=SimpleNamespace(semantic_adapter=adapter,screenshot=Mock()),name_to_zone=lambda z:pinned if z=='existing' else target,globe_in_sight=Mock())
    ns['globe_focus_to'](host,target)
    assert events==([('project',pinned.area_pos)] if pinned_id>7 else [])+[('unpin',),('select',('next',target.area_pos))]
    adapter.operation_siren_globe_unpin.assert_called_once()


@pytest.mark.parametrize('moving',[True,False])
def test_camera_keeps_centering_beyond_six_swipes_but_stops_when_target_stalls(moving):
    source=patched_alas_root() / 'module/os/globe_camera.py'
    node=next(n for n in ast.walk(ast.parse(source.read_text(encoding='utf-8'))) if isinstance(n,ast.FunctionDef) and n.name=='globe_in_sight')
    ns={'np':np,'GameStuckError':RuntimeError,'SemanticGateClosed':SemanticGateClosed,'logger':Mock(),'SemanticGlobeDragPathUnavailable':SemanticGlobeDragPathUnavailable,'point_in_area':lambda p,area,threshold=5:area[0]-threshold<p[0]<area[2]+threshold and area[1]-threshold<p[1]<area[3]+threshold}
    exec(compile(ast.fix_missing_locations(ast.Module(body=[node],type_ignores=[])),str(source),'exec'),ns)
    location=[-650]
    def swipe(*args,**kwargs):
        if moving:location[0]+=100
    project=Mock(side_effect=lambda _:SimpleNamespace(x=location[0],y=420))
    device=SimpleNamespace(semantic_adapter=SimpleNamespace(operation_siren_globe_map_projection=project,operation_siren_globe_visible=Mock(return_value=True)),sleep=Mock(),screenshot=Mock(),swipe_vector=Mock(side_effect=swipe))
    zone=SimpleNamespace(zone_id=11,area_pos=(32,279));host=SimpleNamespace(device=device,name_to_zone=lambda _:zone)
    if moving:
        ns['globe_in_sight'](host,zone)
        assert device.swipe_vector.call_count==7
    else:
        with pytest.raises(RuntimeError,match='did not move'):ns['globe_in_sight'](host,zone)
        assert device.swipe_vector.call_count==2
        device.screenshot.assert_called_once()


@pytest.mark.parametrize('rejection',[SemanticGlobeDragPathUnavailable('unowned candidates'),SemanticGateClosed('malformed proof')])
def test_camera_shortens_only_classified_preinput_unowned_path(rejection):
    source=patched_alas_root() / 'module/os/globe_camera.py'
    node=next(n for n in ast.walk(ast.parse(source.read_text(encoding='utf-8'))) if isinstance(n,ast.FunctionDef) and n.name=='globe_in_sight')
    ns={'np':np,'GameStuckError':RuntimeError,'SemanticGlobeDragPathUnavailable':SemanticGlobeDragPathUnavailable,'point_in_area':lambda p,area,threshold=5:area[0]<p[0]<area[2] and area[1]<p[1]<area[3]}
    exec(compile(ast.fix_missing_locations(ast.Module(body=[node],type_ignores=[])),str(source),'exec'),ns)
    points=[SimpleNamespace(x=-50,y=900),*[SimpleNamespace(x=500,y=420) for _ in range(3)]]
    project=Mock(side_effect=points);swipe=Mock(side_effect=[rejection,None])
    zone=SimpleNamespace(zone_id=83,area_pos=(300,500));host=SimpleNamespace(name_to_zone=lambda _:zone,device=SimpleNamespace(semantic_adapter=SimpleNamespace(operation_siren_globe_map_projection=project),sleep=Mock(),swipe_vector=swipe))
    if isinstance(rejection,SemanticGlobeDragPathUnavailable):
        ns['globe_in_sight'](host,zone)
        assert swipe.call_args_list[0].args==((300.,-300.),)
        assert swipe.call_args_list[1].args==((150.,-150.),)
        assert swipe.call_args_list[0].kwargs['box']==(20,220,980,620)
        assert swipe.call_args_list[1].kwargs['box']==(600,220,980,620)
    else:
        with pytest.raises(SemanticGateClosed,match='malformed'):ns['globe_in_sight'](host,zone)
        assert swipe.call_count==1
