from pathlib import Path
from types import SimpleNamespace
import pytest
from alas_headless import AlasSemanticAdapter, AlasSemanticSession, SemanticGateClosed
from alas_headless.alas_opsi_camera_view import AlasSemanticOpsiView
from tests.test_semantic_oracle_opsi_map_geometry import setup_map, ROOT
from tests.semantic_support.observer_fixtures import make_image, make_button
from tests.semantic_support.adapter_fixtures import FakeOracle
from tests.semantic_support.adapter_cases import AlasSemanticAdapterTestsSupport


@pytest.fixture
def tower(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1]/'artifacts/campaign-preparation/upstream'))
    backend, oracle = setup_map()
    backend.ui['images'].pop()
    model = ROOT+'cells/cell_1_2/attachments/event_1101/icon/model/xinxita(Clone)'
    backend.ui['images'].extend(make_image(model+suffix, sprite) for suffix, sprite in (
        ('', 'xinxita1'), ('/0', 'xinxita'), ('/2', 'xinxita2'), ('/3', 'xinxita3'), ('/4', 'xinxita4')))
    backend.ui['image_count'] = len(backend.ui['images'])
    for image in backend.ui['images']:
        if '/walk_quad' in image['path']:
            for key in ('left', 'right'): image['adb_bounds'][key] += 290
            for key in ('top', 'bottom'): image['adb_bounds'][key] += 10
            image['adb_point']['x'] += 290; image['adb_point']['y'] += 10
    state = oracle.operation_siren_map_geometry('东北航道A', rows=3, columns=3)
    view = AlasSemanticOpsiView(state, SimpleNamespace(SCREEN_CENTER=(640, 360)))
    grid = view.select(is_logging_tower=True).grids[0]
    return backend, oracle, grid


@pytest.mark.parametrize('session_port', [False, True])
def test_native_nameless_grid_uses_fresh_reviewed_tower_cell(tower, session_port):
    backend, oracle, grid = tower
    adapter = AlasSemanticAdapter(oracle, package_gate=lambda: None)
    if session_port:
        session = AlasSemanticSession.__new__(AlasSemanticSession)
        session.open = lambda: adapter
        session.refresh_frame = lambda: None
        result = session.click(grid)
    else:
        result = adapter.click(grid)
    assert result.path == grid.semantic_path
    assert result.semantic_id == 'os/map/grid/relative/0/-1'
    assert backend.taps == [(640, 260)]


@pytest.mark.parametrize('change', ['event-id', 'sprite', 'missing', 'extra', 'wrong-zone', 'foreign', 'not-tower'])
def test_tower_identity_drift_or_cover_rejects_before_input(tower, change):
    backend, oracle, grid = tower
    images = backend.ui['images']
    if change == 'event-id':
        for image in images: image['path'] = image['path'].replace('event_1101', 'event_1102')
    elif change == 'sprite': images[-1]['sprite'] = 'unknown'
    elif change == 'missing': images.pop()
    elif change == 'extra':
        images.append(make_image(ROOT+'cells/cell_1_2/attachments/event_999/icon', 'unknown'))
    elif change == 'wrong-zone': backend.ui['texts'][0]['text'] = '别的海域'
    elif change == 'foreign':
        backend.buttons['buttons'].append(make_button('confirm', 'OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/button_container/custom_button_1(Clone)'))
        backend.buttons['button_count'] += 1
    elif change == 'not-tower': grid.is_logging_tower = False
    backend.ui['image_count'] = len(images)
    adapter = AlasSemanticAdapter(oracle, package_gate=lambda: None)
    with pytest.raises(SemanticGateClosed): adapter.click(grid)
    assert backend.taps == []


def test_camera_moving_between_observation_and_input_cannot_change_selected_cell(tower):
    backend, oracle, grid = tower
    original = oracle.click_operation_siren_relative_grid
    def move(*args, **kwargs):
        for image in backend.ui['images']:
            if '/walk_quad' in image['path']:
                for key in ('left', 'right'): image['adb_bounds'][key] += 100
        return original(*args, **kwargs)
    oracle.click_operation_siren_relative_grid = move
    adapter = AlasSemanticAdapter(oracle, package_gate=lambda: None)
    with pytest.raises(SemanticGateClosed, match='target changed'):
        adapter.click(grid)
    assert backend.taps == []


@pytest.mark.parametrize('tower_flag', [None, False])
def test_unrelated_named_input_with_grid_metadata_keeps_original_dispatch(tower_flag):
    oracle = FakeOracle()
    oracle.enabled_values['login/enter'] = True
    adapter = AlasSemanticAdapter(oracle, package_gate=lambda: None,
        frame_observation_oracle=lambda: oracle,
        frame_identity_provider=AlasSemanticAdapterTestsSupport.frame_identity)
    adapter.begin_login()
    button = SimpleNamespace(name='LOGIN_CHECK', semantic_os_cell=(0, 0))
    if tower_flag is not None:
        button.is_logging_tower = tower_flag
    receipt = adapter.click(button)
    assert receipt.semantic_id == 'login/enter'
    assert oracle.click_calls == ['login/enter']
