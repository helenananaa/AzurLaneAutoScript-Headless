"""Native ALAS endpoint clipping is compatible with the typed map drag port."""
from types import SimpleNamespace
from unittest.mock import Mock
from pathlib import Path
import ast
from datetime import datetime, timedelta

import pytest

from alas_headless import AlasSemanticAdapter, SemanticGateClosed
from alas_headless.adapter.task_lifecycle import semantic_task_scope, TaskCapabilityUnavailable
from tests.semantic_support.adapter_fixtures import FakeOracle
from tests.test_opsi_native_camera_view import native


BOX = (239, 128, 993, 628)
FAILED_VECTOR = (-754.8620912238902, -21.459645460267918)
FAILED_START = (977, 392)
FAILED_END = (239, 371)


def selection(blacklist=(), **changes):
    result = dict(box=BOX, random_range=(0, 0, 0, 0), padding=15, duration=(.1, .2),
        whitelist_area=None, blacklist_area=blacklist,
        name='MAP_SWIPE_6_0', distance_check=True)
    result.update(changes)
    return result


def armed(vector, blacklist=(), **changes):
    oracle = FakeOracle()
    adapter = AlasSemanticAdapter(oracle, lambda: None)
    adapter._operation_siren_camera_geometry = SimpleNamespace(zone_name='卡利比安海C')
    adapter._operation_siren_allows_passive_probe = lambda: True
    oracle.operation_siren_map_swipe = Mock(return_value='typed-drag-receipt')
    token = adapter.begin_operation_siren_map_swipe_vector(vector, **selection(blacklist, **changes))
    return adapter, oracle, token


def dispatch(adapter, token, start, end):
    return adapter.swipe(start, end, duration=.3925, name=token.name, distance_check=True)


def test_retained_r34_native_boundary_clipping_routes_original_endpoints():
    # Actual r34 failure: request(-755,-21), native point_limit clips end x222
    # to239. The exact requested camera vector is therefore not the final drag.
    adapter, oracle, token = armed(FAILED_VECTOR)
    assert dispatch(adapter, token, FAILED_START, FAILED_END) == 'typed-drag-receipt'
    oracle.operation_siren_map_swipe.assert_called_once_with(
        token.geometry, FAILED_START, FAILED_END, 392)
    adapter.end_operation_siren_map_swipe_vector(token)
    assert adapter._operation_siren_map_swipe_intent is None


@pytest.mark.parametrize('vector', [FAILED_VECTOR, (755, 21), (0, -510),
    (0, 510), (-900, -600), (900, 600), (0, -200)])
def test_actual_original_alas_sampler_output_remains_compatible(native, vector):
    from module.base.utils import ensure_int, random_rectangle_vector_opted
    adapter, oracle, token = armed(vector)
    start, end = random_rectangle_vector_opted(vector, BOX,
        random_range=(0, 0, 0, 0), padding=15)
    # Device.swipe performs this native conversion before the semantic port.
    start, end = map(tuple, ensure_int(start, end))
    assert dispatch(adapter, token, start, end) == 'typed-drag-receipt'
    oracle.operation_siren_map_swipe.assert_called_once_with(
        token.geometry, start, end, 392)


@pytest.mark.parametrize('padding', [0, 16, 32, 'native-integer'])
def test_native_sampler_padding_drift_preserves_reviewed_endpoint_port(native, padding):
    from module.base.utils import ensure_int, random_rectangle_vector_opted
    if padding == 'native-integer':
        from module.base.utils import np
        padding = np.int64(15)
    adapter, oracle, token = armed(FAILED_VECTOR, padding=padding)
    start, end = map(tuple, ensure_int(*random_rectangle_vector_opted(
        FAILED_VECTOR, BOX, random_range=(0, 0, 0, 0), padding=padding)))
    assert dispatch(adapter, token, start, end) == 'typed-drag-receipt'
    oracle.operation_siren_map_swipe.assert_called_once_with(token.geometry, start, end, 392)


@pytest.mark.parametrize('timing,actual', [((.08, .16), .28), ((.12, .24), .42)])
def test_native_duration_range_drift_stays_bound_to_the_original_call(timing, actual):
    adapter, oracle, token = armed(FAILED_VECTOR, duration=timing)
    assert adapter.swipe(FAILED_START, FAILED_END, duration=actual,
        name=token.name, distance_check=True) == 'typed-drag-receipt'
    oracle.operation_siren_map_swipe.assert_called_once_with(
        token.geometry, FAILED_START, FAILED_END, round(actual*1000))
    with pytest.raises(SemanticGateClosed, match='duration changed'):
        adapter.swipe(FAILED_START, FAILED_END, duration=actual+1,
            name=token.name, distance_check=True)
    assert oracle.operation_siren_map_swipe.call_count == 1


@pytest.mark.parametrize('changes', [dict(padding=-1), dict(padding=True),
    dict(padding=float('nan')), dict(duration=(0, .2)),
    dict(duration=(-.1, .2)), dict(duration=(.2, .1))])
def test_malformed_sampler_arguments_still_reject_before_input(changes):
    adapter, oracle, token = armed(FAILED_VECTOR)
    adapter.end_operation_siren_map_swipe_vector(token)
    with pytest.raises(SemanticGateClosed):
        adapter.begin_operation_siren_map_swipe_vector(FAILED_VECTOR, **selection(**changes))
    oracle.operation_siren_map_swipe.assert_not_called()


@pytest.mark.parametrize('changes', [dict(random_range=(-1, -1, 1, 1)),
    dict(distance_check=False)])
def test_unknown_sampler_mode_is_local_and_does_not_disable_research(changes):
    adapter, oracle, token = armed(FAILED_VECTOR)
    adapter.end_operation_siren_map_swipe_vector(token)
    session = scope_session()
    with pytest.raises(TaskCapabilityUnavailable):
        with semantic_task_scope(session, 'opsi_explore'):
            adapter.begin_operation_siren_map_swipe_vector(FAILED_VECTOR, **selection(**changes))
    oracle.operation_siren_map_swipe.assert_not_called()
    with semantic_task_scope(session, 'research'):
        pass
    assert session.last_task_outcome == {'task': 'research', 'outcome': 'returned'}


@pytest.mark.parametrize('vector,start,end', [
    ((-755, -21), (977, 392), (240, 371)),  # Shortened away from any boundary.
    ((-755, -21), (300, 392), (993, 371)),  # Reversed horizontal direction.
    ((-200, 0), (977, 392), (239, 392)),   # Boundary does not justify a longer drag.
    ((0, -21), (977, 392), (239, 371)),    # Added unrelated horizontal movement.
    ((-755, -21), (977, 392), (239, 370)), # Unclipped vertical displacement changed.
    ((-755, -21), (977, 392), (238, 371)), # Outside native ALAS box.
])
def test_changed_or_unowned_geometry_still_rejects_before_dispatch(vector, start, end):
    adapter, oracle, token = armed(vector)
    with pytest.raises(SemanticGateClosed):
        dispatch(adapter, token, start, end)
    oracle.operation_siren_map_swipe.assert_not_called()


def test_actual_clipped_path_still_respects_original_forbidden_areas():
    adapter, oracle, token = armed(FAILED_VECTOR, [(968, 380, 980, 400)])
    with pytest.raises(SemanticGateClosed, match='forbidden'):
        dispatch(adapter, token, FAILED_START, FAILED_END)
    oracle.operation_siren_map_swipe.assert_not_called()


def test_a_phantom_unclipped_path_does_not_block_the_real_native_gesture():
    # Computing start backwards from clipped end using the unclipped request
    # invents x994. Actual original sampler starts at977 and never crosses here.
    adapter, oracle, token = armed(FAILED_VECTOR, [(988, 380, 1000, 400)])
    assert dispatch(adapter, token, FAILED_START, FAILED_END) == 'typed-drag-receipt'
    oracle.operation_siren_map_swipe.assert_called_once()


@pytest.mark.parametrize('vector,start,end', [
    ((175.9272149858033, 1.407508782451973), (631, 251), (807, 252)),
    ((176., 0.), (631, 252), (807, 252)),
])
def test_native_continuous_path_outside_or_on_blacklist_edge_remains_allowed(
        native, monkeypatch, vector, start, end):
    from module.base import utils
    blacklist = ((740.173, 256.987, 840.198, 321.896),
        (642.992, 324.582, 743.255, 394.177),
        (542.45, 256.987, 639.15, 321.896),
        (878, 252, 997, 329), (786, 319, 906, 402), (684, 252, 796, 329))
    # r48 failed before input after rounding y251.667 to252. The original
    # sampler accepts its first candidate with floating path points and a
    # strict interior test (point_in_area threshold=0).
    candidates = []
    def choose(area):
        if tuple(area) == (0, 0, 0, 0):
            return utils.np.array((0, 0))
        candidates.append(tuple(area))
        return utils.np.array(end)
    monkeypatch.setattr(utils, 'random_rectangle_point', choose)
    native_start, native_end = map(tuple, utils.ensure_int(
        *utils.random_rectangle_vector_opted(vector, BOX,
            blacklist_area=blacklist)))
    assert (native_start, native_end) == (start, end)
    assert len(candidates) == 1
    adapter, oracle, token = armed(vector, blacklist, name='MAP_SWIPE_-1_0')
    assert dispatch(adapter, token, start, end) == 'typed-drag-receipt'
    oracle.operation_siren_map_swipe.assert_called_once_with(
        token.geometry, start, end, 392)


def scope_session():
    return SimpleNamespace(discard_task_state=Mock(), trace=None)


def test_native_blacklist_sampler_exhaustion_defers_only_its_task(native, monkeypatch):
    from module.base import utils
    vector = (200., 0.)
    blacklist = ((590, 390, 610, 410),)
    candidates = []
    def choose(area):
        if tuple(area) == (0, 0, 0, 0):
            return utils.np.array((0, 0))
        candidates.append(tuple(area))
        return utils.np.array((600, 400))
    monkeypatch.setattr(utils, 'random_rectangle_point', choose)
    start, end = map(tuple, utils.ensure_int(*utils.random_rectangle_vector_opted(
        vector, BOX, blacklist_area=blacklist)))
    assert (start, end) == ((400, 400), (600, 400))
    assert len(candidates) == 101  # Original bounded attempts plus fallback.
    adapter, oracle, token = armed(vector, blacklist, name='MAP_SWIPE_-1_0')
    session = scope_session()
    with pytest.raises(TaskCapabilityUnavailable):
        with semantic_task_scope(session, 'opsi_explore'):
            dispatch(adapter, token, start, end)
    oracle.operation_siren_map_swipe.assert_not_called()
    assert session.last_task_outcome['outcome'] == 'capability-unavailable'
    with semantic_task_scope(session, 'research'):
        pass
    assert session.last_task_outcome == {'task': 'research', 'outcome': 'returned'}


def test_unrecognized_native_vector_is_task_local_without_dispatching_input():
    adapter, oracle, token = armed((-755, -21))
    session = scope_session()
    with pytest.raises(TaskCapabilityUnavailable):
        with semantic_task_scope(session, 'opsi_explore'):
            dispatch(adapter, token, FAILED_START, (240, 371))
    oracle.operation_siren_map_swipe.assert_not_called()
    assert session.last_task_outcome['outcome'] == 'capability-unavailable'
    with semantic_task_scope(session, 'research'):
        pass
    assert session.last_task_outcome == {'task': 'research', 'outcome': 'returned'}
    assert session.discard_task_state.call_count == 2


@pytest.mark.parametrize('failure', ['package identity changed',
    'operation siren logical map changed before camera swipe',
    'operation siren camera swipe did not advance native map state'])
def test_runtime_or_uncertain_input_failure_keeps_the_original_error(failure):
    adapter, oracle, token = armed(FAILED_VECTOR)
    error = SemanticGateClosed(failure)
    if failure == 'package identity changed':
        adapter._package_gate = Mock(side_effect=error)
    else:
        oracle.operation_siren_map_swipe.side_effect = error
    session = scope_session()
    with pytest.raises(SemanticGateClosed) as caught:
        with semantic_task_scope(session, 'opsi_explore'):
            dispatch(adapter, token, FAILED_START, FAILED_END)
    assert caught.value is error
    assert session.last_task_outcome['outcome'] == 'raised'


def native_run():
    from module.config.config import TaskEnd
    source = Path(__file__).resolve().parents[1] / 'artifacts/continuity-20261004/alas-runtime/alas.py'
    if not source.exists():
        pytest.skip('installed native ALAS run method unavailable')
    tree = ast.parse(source.read_text(encoding='utf-8'))
    method = next(node for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == 'run')
    scope = dict(TaskEnd=TaskEnd, TaskCapabilityUnavailable=TaskCapabilityUnavailable,
        semantic_task_scope=semantic_task_scope, logger=Mock(), datetime=datetime)
    exec(compile(ast.Module(body=[method], type_ignores=[]), str(source), 'exec'), scope)
    return scope['run']


def test_actual_native_run_defers_only_the_unrecognized_camera_task(native):
    run = native_run()
    adapter, oracle, token = armed((-755, -21))
    session = scope_session()
    host = SimpleNamespace(device=SimpleNamespace(semantic_adapter=session, screenshot=Mock()),
        config=SimpleNamespace(task_delay=Mock()),
        opsi_explore=lambda: dispatch(adapter, token, FAILED_START, (240, 371)), research=Mock())
    assert run(host, 'opsi_explore') is None
    host.config.task_delay.assert_called_once_with(success=False)
    oracle.operation_siren_map_swipe.assert_not_called()
    assert run(host, 'research') is True
    host.research.assert_called_once()


@pytest.mark.parametrize('has_native_future', [True, False])
def test_native_deferral_keeps_original_selected_cooldown_or_failure_policy(native, has_native_future):
    from module.config.config import AzurLaneConfig
    now = datetime.now().replace(microsecond=0)
    native_future = now + timedelta(minutes=27)
    # The real native task_delay writes only this in-memory diagnostic config.
    config = SimpleNamespace(Scheduler_NextRun=native_future if has_native_future else now,
        Scheduler_FailureInterval=0 if has_native_future else 15,
        task=SimpleNamespace(command='OpsiExplore'), modified={}, update=Mock())
    config.task_delay = lambda **kwargs: AzurLaneConfig.task_delay(config, **kwargs)
    adapter, oracle, token = armed((-755, -21))
    host = SimpleNamespace(device=SimpleNamespace(semantic_adapter=scope_session(), screenshot=Mock()),
        config=config, opsi_explore=lambda: dispatch(adapter, token, FAILED_START, (240, 371)))
    assert native_run()(host, 'opsi_explore') is None
    chosen = config.modified['OpsiExplore.Scheduler.NextRun']
    if has_native_future:
        assert chosen == native_future
    else:
        assert now + timedelta(minutes=15) <= chosen <= datetime.now() + timedelta(minutes=15)
    oracle.operation_siren_map_swipe.assert_not_called()
