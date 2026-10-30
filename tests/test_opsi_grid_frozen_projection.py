"""Native projection dicts become read-only mappings at screenshot boundaries."""
from pathlib import Path
from types import MappingProxyType, SimpleNamespace
from unittest.mock import Mock
import json

import pytest

from alas_headless import SemanticGateClosed
from alas_headless.adapter.frame import _freeze, _FrameBoundSemanticOracle
from alas_headless.oracle.contracts import Bounds
from alas_headless.oracle.opsi_navigation import _native_grid_projection_point
from tests.test_opsi_question_fleet_relative import scene, PLANE
from tests.test_opsi_daemon_resource_radar import image


def frozen_oracle(backend, live):
    return _FrameBoundSemanticOracle(lambda line: _freeze(backend.request(line)),
        backend.foreground_component, backend.tap, live.fingerprint, frame_guard=Mock())


@pytest.mark.parametrize('frozen', [False, True])
def test_current_projection_accepts_mutable_or_immutable_mapping(frozen):
    backend, live = scene()
    backend.ui['images'].append(image('10220151', 'exp', (0, -2)))
    backend.ui['image_count'] = len(backend.ui['images'])
    oracle = frozen_oracle(backend, live) if frozen else live
    receipt = oracle.click_operation_siren_daemon_target(oracle.operation_siren_nearest_daemon_target())
    assert receipt.path == PLANE+'quads/world_quad_6_6/walk_quad'
    assert backend.taps == [(640, 430)]


@pytest.mark.parametrize('value', [None, [], {'x': True, 'y': 5}, {'x': float('nan'), 'y': 5},
                                 {'x': 100, 'y': 5}, {'x': 5}])
def test_projection_still_rejects_missing_malformed_or_outside_native_bounds(value):
    if isinstance(value, dict):
        value = MappingProxyType(value)
    item = SimpleNamespace(raw={'adb_point': value}, bounds=Bounds(0, 0, 10, 10))
    with pytest.raises(SemanticGateClosed):
        _native_grid_projection_point(item)


def test_actual_active_fleet_projection_survives_native_frame_freezing():
    from tests.semantic_support.observer_fixtures import FakeBackend, make_oracle, make_ui
    path = Path(__file__).resolve().parents[1] / 'artifacts/full-feature-live-20261025/opsi-daemon-r9.json'
    if not path.exists():
        pytest.skip('private failed live frame unavailable')
    data = json.loads(path.read_text(encoding='utf-8'))
    raw = data['retained_immutable_frame']['frame']['projections']
    backend = FakeBackend(raw['buttons']['buttons'])
    ui = raw['ui']
    backend.ui = make_ui(ui['texts'], images=ui['images'], toggles=ui['toggles'])
    backend.ui['operation_siren_map_state'] = ui['operation_siren_map_state']
    live = make_oracle(backend)
    oracle = frozen_oracle(backend, live)
    target = oracle.operation_siren_nearest_daemon_target()
    assert target.relative_position == (0, -2)
    receipt = oracle.click_operation_siren_daemon_target(target)
    assert receipt.path == PLANE+'quads/world_quad_5_2/walk_quad'
    assert len(backend.taps) == 1
