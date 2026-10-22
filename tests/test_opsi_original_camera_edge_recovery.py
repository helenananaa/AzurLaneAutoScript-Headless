"""Typed OS views enter the original ALAS camera recovery without pixels."""
import ast
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import alas_headless
from alas_headless.alas_opsi_camera_view import install_alas_opsi_camera_view
from alas_headless import SemanticGateClosed
from tests.test_opsi_native_camera_view import geometry, native


def original_update(monkeypatch, native, *, screen_center, unknown=False):
    from module.exception import MapDetectionError
    source = Path(__file__).resolve().parents[1] / 'artifacts/campaign-preparation/upstream/module/map/camera.py'
    method = next(n for n in ast.walk(ast.parse(source.read_text(encoding='utf-8')))
                  if isinstance(n, ast.FunctionDef) and n.name == '_update_view')
    scope = {'logger': Mock(), 'MapDetectionError': MapDetectionError}
    for node in ast.walk(method):
        if isinstance(node, ast.Name) and node.id.isupper():
            scope[node.id] = node.id
    exec(compile(ast.Module(body=[method], type_ignores=[]), str(source), 'exec'), scope)
    monkeypatch.setattr(alas_headless, 'current_semantic_session', lambda: object())
    state = geometry()
    if unknown:
        state = replace(state, attachments=(replace(state.attachments[0], object_id=123456),))
    # There is deliberately no device.image and no pixel View loader.
    host = SimpleNamespace(config=SimpleNamespace(SCREEN_CENTER=screen_center,
                                                  task=SimpleNamespace(command='OpsiExplore')),
                           device=SimpleNamespace(app_is_running=Mock(return_value=True)),
                           _prev_view=None, _auto_search_menu_offset=(50,50), info_bar_count=Mock(return_value=0),
                           appear=Mock(return_value=False), handle_popup_confirm=Mock(return_value=False),
                           handle_story_skip=Mock(return_value=False), is_in_stage=Mock(return_value=False),
                           _map_swipe=Mock(), _view_init=Mock(side_effect=AssertionError('pixel View init')))
    host._load_semantic_os_view = lambda: install_alas_opsi_camera_view(host, state)
    return scope['_update_view'], host


def test_complete_outside_view_uses_original_boundary_offset_recovery(monkeypatch, native):
    # Fixture projection: cell centers 110,210,310; the screen center is
    # one cell beyond the map. Preserve that observation; do not clamp it.
    update, host = original_update(monkeypatch, native, screen_center=(410,410))
    assert update(host) is True
    assert host.view.semantic_observation.camera_location == (3,3)
    host._map_swipe.assert_called_once_with((-1,-1))
    host._view_init.assert_not_called()


def test_in_map_typed_view_needs_no_recovery(monkeypatch, native):
    update, host = original_update(monkeypatch, native, screen_center=(310,310))
    assert update(host) is True
    host._map_swipe.assert_not_called()
    host._view_init.assert_not_called()


def test_unknown_attachment_cannot_enter_outside_map_recovery(monkeypatch, native):
    update, host = original_update(monkeypatch, native, screen_center=(410,410), unknown=True)
    with pytest.raises(SemanticGateClosed, match='classification unavailable'):
        update(host)
    host._map_swipe.assert_not_called()
    host._view_init.assert_not_called()


def test_original_swipe_wait_without_previous_view_can_finish(native):
    import numpy as np
    from module.base.timer import Timer
    source = Path(__file__).resolve().parents[1] / 'artifacts/campaign-preparation/upstream/module/map/camera.py'
    method = next(n for n in ast.walk(ast.parse(source.read_text(encoding='utf-8')))
                  if isinstance(n, ast.FunctionDef) and n.name == 'update')
    scope = {'logger': Mock(), 'Timer': Timer, 'np': np}
    exec(compile(ast.Module(body=[method], type_ignores=[]), str(source), 'exec'), scope)
    host = SimpleNamespace(_prev_view=None, config=SimpleNamespace(MAP_GRID_CENTER_TOLERANCE=.3),
                           device=SimpleNamespace(screenshot=Mock(), _screenshot_interval=Mock()),
                           view=SimpleNamespace(center_offset=np.array((.5,.5))),
                           _update_view=Mock(return_value=True), _update_view_data=Mock())
    scope['update'](host, wait_swipe=True)
    host._update_view.assert_called_once_with()
    host._update_view_data.assert_called_once_with()
