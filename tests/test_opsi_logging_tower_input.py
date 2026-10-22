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
def tower(monkeypatch, request):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1]/'artifacts/campaign-preparation/upstream'))
    backend, oracle = setup_map()
    backend.ui['images'].pop()
    scanning = getattr(request, 'param', 'tower') == 'scanning'
    model = ROOT+'cells/cell_1_2/attachments/' + (
        'event_1401/icon/model/laohuji(Clone)' if scanning else 'event_1101/icon/model/xinxita(Clone)')
    sprites = (('', 'laohuji'),) if scanning else (
        ('', 'xinxita1'), ('/0', 'xinxita'), ('/2', 'xinxita2'), ('/3', 'xinxita3'), ('/4', 'xinxita4'))
    backend.ui['images'].extend(make_image(model+suffix, sprite) for suffix, sprite in sprites)
    backend.ui['image_count'] = len(backend.ui['images'])
    for image in backend.ui['images']:
        if '/walk_quad' in image['path']:
            for key in ('left', 'right'): image['adb_bounds'][key] += 290
            for key in ('top', 'bottom'): image['adb_bounds'][key] += 10
            image['adb_point']['x'] += 290; image['adb_point']['y'] += 10
    state = oracle.operation_siren_map_geometry('东北航道A', rows=3, columns=3)
    view = AlasSemanticOpsiView(state, SimpleNamespace(SCREEN_CENTER=(640, 360)))
    grid = view.select(**({'is_scanning_device': True} if scanning else {'is_logging_tower': True})).grids[0]
    assert grid.is_enemy
    assert grid.enemy_genre == ('ScanningDevice' if scanning else 'LoggingTower')
    return backend, oracle, grid


@pytest.mark.parametrize('session_port', [False, True])
@pytest.mark.parametrize('tower', ['tower', 'scanning'], indirect=True)
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
@pytest.mark.parametrize('tower', ['tower', 'scanning'], indirect=True)
def test_tower_identity_drift_or_cover_rejects_before_input(tower, change):
    backend, oracle, grid = tower
    images = backend.ui['images']
    if change == 'event-id':
        for image in images:
            image['path'] = image['path'].replace('event_1101', 'event_1102').replace('event_1401', 'event_1499')
    elif change == 'sprite': images[-1]['sprite'] = 'unknown'
    elif change == 'missing': images.pop()
    elif change == 'extra':
        images.append(make_image(ROOT+'cells/cell_1_2/attachments/event_999/icon', 'unknown'))
    elif change == 'wrong-zone': backend.ui['texts'][0]['text'] = '别的海域'
    elif change == 'foreign':
        backend.buttons['buttons'].append(make_button('confirm', 'OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/button_container/custom_button_1(Clone)'))
        backend.buttons['button_count'] += 1
    elif change == 'not-tower':
        grid.is_logging_tower = False
        grid.is_scanning_device = False
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


def test_retained_zone61_scanning_device_frame_fills_original_native_flag(monkeypatch):
    import json
    import re
    from tests.semantic_support.observer_fixtures import FakeBackend, make_oracle
    repo = Path(__file__).resolve().parents[1]
    path = repo / 'artifacts/continuity-20261004/goal-scheduler-r28.json'
    if not path.exists():
        pytest.skip('retained r28 frame unavailable')
    task = next(t for t in json.loads(path.read_text(encoding='utf-8'))['tasks']
                if t['selected_task'] == 'OpsiExplore')
    frame = task['failure_observation']
    backend = FakeBackend([])
    backend.snapshot = frame['state']['snapshot']
    backend.buttons = frame['state']['buttons_snapshot']
    backend.ui = frame['ui']['snapshot']
    coordinates = [tuple(map(int, m.groups())) for image in backend.ui['images']
                   if (m := re.search(r'/quads/world_quad_(\d+)_(\d+)/walk_quad$', image['path']))]
    rows = max(r for r, _ in coordinates) + 1
    columns = max(c for _, c in coordinates) + 1
    title = next(t['text'] for t in backend.ui['texts'] if t['path'].endswith('/top_stage/title/name'))
    monkeypatch.syspath_prepend(str(repo / 'artifacts/campaign-preparation/upstream'))
    from alas_headless.semantic_oracle import SemanticOracle, OracleFingerprint
    oracle = SemanticOracle(backend.request, backend.foreground_component, backend.tap,
        OracleFingerprint(package=backend.snapshot['package'], component=backend.foreground,
            driver_revision=backend.snapshot['driver_revision'], expected_pid=backend.snapshot['pid']))
    state = oracle.operation_siren_map_geometry(title, rows=rows, columns=columns)
    view = AlasSemanticOpsiView(state, SimpleNamespace(SCREEN_CENTER=(640, 360)))
    selected = view.select(is_scanning_device=True)
    assert selected.count == 1
    assert selected[0].semantic_os_cell == (9, 6)
    assert selected[0].is_enemy and selected[0].enemy_genre == 'ScanningDevice'
    assert not selected[0].is_land and not selected[0].is_logging_tower
    assert not selected[0].semantic_passable_decorations
    assert backend.taps == []


def test_scanning_device_returns_to_original_walk_and_auto_search_owner():
    from contextlib import nullcontext
    from unittest.mock import Mock
    from tests.test_alas_config_branch_compatibility import method
    grid = SimpleNamespace(is_scanning_device=True)
    host = SimpleNamespace(view=SimpleNamespace(select=lambda **kw: [grid] if kw.get('is_scanning_device') else []),
        _solved_map_event=set(), is_in_task_cl1_leveling=False,
        device=SimpleNamespace(click=Mock()), config=SimpleNamespace(temporary=lambda **kw: nullcontext()),
        wait_until_walk_stable=Mock(return_value='event'), os_auto_search_run=Mock())
    original = method('module/os/map.py', 'OSMap', 'map_rescan_current', Timer=Mock())
    assert original(host)
    host.device.click.assert_called_once_with(grid)
    host.wait_until_walk_stable.assert_called_once()
    host.os_auto_search_run.assert_called_once()
    assert host._solved_map_event == {'is_scanning_device'}
