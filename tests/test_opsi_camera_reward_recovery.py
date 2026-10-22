"""Known reward overlays return to ALAS recovery; no obscured swipe is sent."""
import ast
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from alas_headless.oracle.errors import SemanticGateClosed, SemanticViewportReanchorRequired
from tests.test_opsi_native_map_swipe import reader, proof, START, END
from tests.test_opsi_original_camera_edge_recovery import original_update
from tests.test_opsi_native_camera_view import native


def loader():
    source = Path(__file__).resolve().parents[1] / 'artifacts/campaign-preparation/upstream/module/os/camera.py'
    node = next(n for n in ast.walk(ast.parse(source.read_text(encoding='utf-8')))
                if isinstance(n, ast.FunctionDef) and n.name == '_load_semantic_os_view')
    from module.exception import MapDetectionError
    scope = {'MapDetectionError': MapDetectionError}
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(source), 'exec'), scope)
    return scope['_load_semantic_os_view']


def test_reward_covered_view_uses_original_quit_owner(monkeypatch, native):
    update, host = original_update(monkeypatch, native, screen_center=(310,310))
    host.device.semantic_adapter = SimpleNamespace(operation_siren_map_geometry=Mock())
    host.os_auto_search_quit = Mock()
    host.appear = lambda button, **kwargs: (button if isinstance(button,str) else button.name) == 'AUTO_SEARCH_REWARD'
    host._load_semantic_os_view = lambda: loader()(host)
    assert update(host) is False
    host.os_auto_search_quit.assert_called_once_with()
    host.device.semantic_adapter.operation_siren_map_geometry.assert_not_called()
    host._map_swipe.assert_not_called()


def test_uncovered_view_keeps_original_native_view_loader(monkeypatch, native):
    from tests.test_opsi_native_camera_view import geometry
    host = SimpleNamespace(device=SimpleNamespace(semantic_adapter=SimpleNamespace(
        operation_siren_map_geometry=Mock(return_value=geometry()))),
        appear=Mock(return_value=False), zone=SimpleNamespace(shape=(2,2),cn='东北航道A'),
        config=SimpleNamespace(SCREEN_CENTER=(310,310)))
    fn = loader()
    fn.__globals__.update(location_ensure=lambda shape: shape,logger=Mock())
    assert fn(host) is True
    assert host.view.semantic_observation.generation == geometry().generation


@pytest.mark.parametrize('mixed',[False,True])
@pytest.mark.parametrize('root',['WorldAutoFightRewardUI(Clone)',
    'OverlayCamera/Overlay/UIMain/WorldAutoFightRewardUI(Clone)'])
def test_late_exact_reward_requests_refresh_without_input(mixed, root):
    result = proof()
    for sample in result['samples'][8:16] if mixed else result['samples']:
        sample.update(owned=False,top_path=root+'/Window/Fixed/bg')
    backend, oracle = reader(result)
    with pytest.raises(SemanticViewportReanchorRequired):
        oracle.operation_siren_map_drag_proof(START,END)
    assert backend.swipes == [] and backend.taps == []


@pytest.mark.parametrize('fault',['foreign','near-name','point','ambiguous-owned'])
@pytest.mark.parametrize('root',['WorldAutoFightRewardUI(Clone)',
    'OverlayCamera/Overlay/UIMain/WorldAutoFightRewardUI(Clone)'])
def test_reward_cannot_hide_other_invalid_drag_evidence(fault, root):
    result = proof()
    for sample in result['samples']:
        sample.update(owned=False,top_path=root+'/Window')
    sample = result['samples'][12]
    if fault == 'foreign': sample['top_path'] = 'OtherPopup/Window'
    if fault == 'near-name': sample['top_path'] = root+'Other/Window'
    if fault == 'point': sample['x'] += 1
    if fault == 'ambiguous-owned': sample['owned'] = None
    backend, oracle = reader(result)
    with pytest.raises(SemanticGateClosed) as error:
        oracle.operation_siren_map_drag_proof(START,END)
    assert not isinstance(error.value,SemanticViewportReanchorRequired)
    assert backend.swipes == [] and backend.taps == []


def test_retained_r188_complete_reward_path_requests_original_recovery():
    import json
    source = Path(__file__).resolve().parents[1]/'artifacts/semantic-cn-original-scheduler-r188-20261002.json'
    if not source.exists(): pytest.skip('retained native drag failure unavailable')
    receipt = json.loads(source.read_text(encoding='utf-8'))
    task = next(t for t in receipt['tasks'] if t['selected_task']=='OpsiExplore')
    result = task['failure_observation']['ui']['snapshot']['operation_siren_map_drag']
    start, end = tuple(map(int,result['endpoints'][:2])), tuple(map(int,result['endpoints'][2:]))
    backend, oracle = reader(result)
    with pytest.raises(SemanticViewportReanchorRequired):
        oracle.operation_siren_map_drag_proof(start,end)
    assert backend.swipes == [] and backend.taps == []
