import ast
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from tests.test_alas_config_branch_compatibility import source as patched_source
from alas_headless import SemanticGateClosed
from alas_headless.oracle.errors import SemanticGlobeSelectionMissed, SemanticViewportReanchorRequired

def original_focus(zone_id=5):
    source='module/os/globe_camera.py'
    node=next(n for n in ast.walk(ast.parse(patched_source(source))) if isinstance(n,ast.FunctionDef) and n.name=='globe_focus_to')
    ns={'logger':Mock(),'SemanticGateClosed':SemanticGateClosed,'SemanticGlobeSelectionMissed':SemanticGlobeSelectionMissed,'SemanticViewportReanchorRequired':SemanticViewportReanchorRequired}
    exec(compile(ast.fix_missing_locations(ast.Module(body=[node],type_ignores=[])),str(source),'exec'),ns)
    zone=SimpleNamespace(cn='塔伦托' if zone_id==5 else '北海',zone_id=zone_id,area_pos=(1796,565))
    a=SimpleNamespace(operation_siren_globe_state=Mock(side_effect=SemanticGateClosed('unselected globe')),
        click_operation_siren_globe_port=Mock(),click_operation_siren_globe_map_zone=Mock())
    d=SimpleNamespace(semantic_adapter=a,screenshot=Mock())
    h=SimpleNamespace(device=d,name_to_zone=lambda _:zone,globe_in_sight=Mock())
    return lambda:ns['globe_focus_to'](h,zone),a,d,h,zone

def test_successful_existing_port_keeps_root_path():
    run,a,d,h,z=original_focus();run()
    a.click_operation_siren_globe_port.assert_called_once_with(z.cn,z.zone_id)
    a.click_operation_siren_globe_map_zone.assert_not_called()

def test_proven_root_miss_reuses_original_zone_intent():
    run,a,d,h,z=original_focus();a.click_operation_siren_globe_port.side_effect=[SemanticGlobeSelectionMissed('fresh unselected'), None]
    run()
    assert a.click_operation_siren_globe_port.call_count==2
    a.click_operation_siren_globe_port.assert_called_with(z.cn,z.zone_id,native_mask=True)
    a.click_operation_siren_globe_map_zone.assert_not_called()
    assert h.globe_in_sight.call_count==2

def test_retry_limit_remains_three_and_never_accepts_missing_pin():
    run,a,d,h,z=original_focus();error=SemanticGlobeSelectionMissed('fresh unselected')
    a.click_operation_siren_globe_port.side_effect=error;a.click_operation_siren_globe_map_zone.side_effect=error
    with pytest.raises(SemanticGlobeSelectionMissed):run()
    assert a.click_operation_siren_globe_port.call_count==2
    assert a.click_operation_siren_globe_map_zone.call_count==1
    assert h.globe_in_sight.call_count==3

@pytest.mark.parametrize('where',['root','mask','projection'])
def test_unknown_state_is_fatal_before_any_alternative(where):
    run,a,d,h,z=original_focus()
    a.click_operation_siren_globe_port.side_effect=(SemanticGateClosed('ambiguous') if where=='root' else
        [SemanticGlobeSelectionMissed('fresh unselected'), SemanticGateClosed('ambiguous') if where=='mask' else SemanticGlobeSelectionMissed('fresh unselected')])
    a.click_operation_siren_globe_map_zone.side_effect=SemanticGateClosed('ambiguous')
    with pytest.raises(SemanticGateClosed,match='ambiguous'):run()
    assert a.click_operation_siren_globe_map_zone.call_count==(1 if where=='projection' else 0)

def test_nonport_uses_existing_logical_projection_first():
    run,a,d,h,z=original_focus(62);run()
    a.click_operation_siren_globe_port.assert_not_called()
    a.click_operation_siren_globe_map_zone.assert_called_once_with(z.cn,z.area_pos)
