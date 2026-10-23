"""Native camera retries exact fleet projection without a new adapter loop."""
import ast
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from alas_headless import SemanticGateClosed


def native_methods():
    root = os.environ.get('ALAS_TEST_ROOT')
    if not root:
        pytest.skip('set ALAS_TEST_ROOT to the verified patched ALAS tree')
    tree = ast.parse(Path(root, 'module/map/camera.py').read_text(encoding='utf-8'))
    return {n.name: n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}


@pytest.mark.parametrize('error', [SemanticGateClosed('moving'),
    SemanticGateClosed('malformed')])
def test_unprojectable_map_enters_native_detection_retry_without_partial_view(monkeypatch, error):
    import alas_headless
    session = SimpleNamespace(campaign_camera_state=Mock(side_effect=error))
    monkeypatch.setattr(alas_headless, 'current_semantic_session', lambda: session)
    install = Mock(side_effect=AssertionError('must not install a partial map'))
    monkeypatch.setattr(alas_headless, 'install_alas_campaign_camera_view', install)
    class MapDetectionError(Exception): pass
    ns = dict(MapDetectionError=MapDetectionError)
    exec(compile(ast.fix_missing_locations(ast.Module(
        body=[native_methods()['_update_view']], type_ignores=[])), '<native camera>', 'exec'), ns)
    with pytest.raises(MapDetectionError):
        ns['_update_view'](SimpleNamespace())
    install.assert_not_called()


@pytest.mark.parametrize('persistent', [False, True])
def test_original_camera_update_refreshes_and_keeps_its_timeout(persistent):
    class MapDetectionError(Exception): pass
    timer = SimpleNamespace(start=lambda: timer, reached=lambda: True)
    host = SimpleNamespace(device=SimpleNamespace(screenshot=Mock()),
        _update_view=Mock(side_effect=[MapDetectionError('moving'), True]),
        view=SimpleNamespace(center_offset=(0.5, 0.5)), _update_view_data=Mock())
    confirm = SimpleNamespace(start=lambda: confirm, reached=lambda: persistent)
    ns = dict(MapDetectionError=MapDetectionError, logger=Mock(),
        Timer=Mock(side_effect=[confirm, timer]))
    exec(compile(ast.fix_missing_locations(ast.Module(
        body=[native_methods()['update']], type_ignores=[])), '<native camera update>', 'exec'), ns)
    if persistent:
        with pytest.raises(MapDetectionError):
            ns['update'](host)
        host._update_view_data.assert_not_called()
    else:
        ns['update'](host)
        assert host.device.screenshot.call_count == 2
        host._update_view_data.assert_called_once()


@pytest.mark.parametrize('surface', ['preparation', 'loading', 'combat', 'unknown', 'unowned'])
def test_native_goto_hands_crossed_camera_frame_to_its_own_combat_loop(surface):
    root = os.environ.get('ALAS_TEST_ROOT')
    if not root:
        pytest.skip('set ALAS_TEST_ROOT to the verified patched ALAS tree')
    tree = ast.parse(Path(root, 'module/map/fleet.py').read_text(encoding='utf-8'))
    goto = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == '_goto')
    branch = next(n for n in ast.walk(goto) if isinstance(n, ast.If)
        and n.body and isinstance(n.body[0], ast.Try)
        and any(isinstance(h.type, ast.Name) and h.type.id == 'MapDetectionError'
                for h in n.body[0].handlers))
    class MapDetectionError(Exception): pass
    oracle = SimpleNamespace(campaign_precombat_visible=Mock(return_value=surface == 'preparation'),
        daily_battle_loading_visible=Mock(return_value=surface == 'loading'),
        daily_combat_visible=Mock(return_value=surface == 'combat'))
    adapter = SimpleNamespace(campaign_combat_committed=Mock(return_value=surface != 'unowned'),
        open=lambda: SimpleNamespace(_frame_or_live_observation_oracle=lambda: oracle))
    host = SimpleNamespace(is_in_map=Mock(side_effect=[True, False]),
        update=Mock(side_effect=MapDetectionError('frame entered preparation')),
        convert_global_to_local=Mock(side_effect=AssertionError('no partial View')))
    loop = ast.For(target=ast.Name(id='_', ctx=ast.Store()),
        iter=ast.Tuple(elts=[ast.Constant(0), ast.Constant(1)], ctx=ast.Load()),
        body=[branch], orelse=[])
    code = compile(ast.fix_missing_locations(ast.Module(body=[loop], type_ignores=[])),
        '<native goto handoff>', 'exec')
    ns = dict(self=host, semantic_adapter=adapter, location=(3, 5), MapDetectionError=MapDetectionError)
    if surface in ('unknown', 'unowned'):
        with pytest.raises(MapDetectionError): exec(code, ns)
    else:
        exec(code, ns)
        assert host.is_in_map.call_count == 2
    host.update.assert_called_once()
    host.convert_global_to_local.assert_not_called()
