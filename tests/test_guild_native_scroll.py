"""Original Guild retries own scrolling; typed points supply the drag boundary."""
import ast
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from alas_headless import SemanticGateClosed
from alas_headless.oracle.errors import SemanticTargetNotActionable, SemanticInputBlocked
from tests.test_game_tips_loading_presence import host
from tests.test_guild_operation_candidates import ROOT, backend_for_nodes
from tests.test_alas_config_branch_compatibility import source
from tests.semantic_support.observer_fixtures import make_oracle, make_button


def scroll_host(drift=False, fixture='guild-operation-offscreen-r194.json'):
    backend, oracle, adapter = host(drift, fixture)
    # The retained live endpoints may differ by one generation. The fake
    # server freezes them, so advance all frames to its latest publication
    # before repeated reads; do not weaken the runtime backwards check.
    generation = max(frame['generation'] for frame in (backend.snapshot, backend.buttons, backend.ui))
    for frame in (backend.snapshot, backend.buttons, backend.ui):
        frame['generation'] = generation
    oracle._swipe_backend = backend.swipe
    oracle._swipe = oracle._dispatch_swipe
    return backend, oracle, adapter


def move(backend, delta):
    for node in backend.buttons['buttons']:
        if '/missionlist/path/' in node['path']:
            node['adb_point']['x'] += delta
            node['adb_bounds']['left'] += delta
            node['adb_bounds']['right'] += delta
    for frame in (backend.snapshot, backend.buttons, backend.ui):
        frame['generation'] += 1


@pytest.mark.parametrize('drift', [False, True])
def test_retained_offscreen_mission_becomes_visible_by_exact_native_chain_points(drift):
    backend, oracle, _ = scroll_host(drift)
    assert not oracle.guild_operation_visible_nodes()
    backend.on_swipe = lambda: move(backend, backend.swipes[-1][2] - backend.swipes[-1][0])
    result = oracle.swipe_guild_operations(True)
    assert result['start'] == (937, 382)
    assert result['end'] == (528, 382)
    assert result['post_generation'] > result['pre_generation']
    assert len(backend.swipes) == 1
    assert not backend.taps
    # The current live chain has advanced to12-1. One successful scroll
    # moves the chain but does not yet expose its active branch.
    assert not oracle.guild_operation_visible_nodes()
    oracle.swipe_guild_operations(True)
    assert len(backend.swipes) == 2
    assert any(n.name == '12-1' for n in oracle.guild_operation_visible_nodes())


@pytest.mark.parametrize('case', ['duplicate', 'covered', 'wrong-package', 'stale', 'no-anchors'])
def test_unsafe_scroll_never_sends_input(case):
    backend, oracle, _ = scroll_host()
    if case == 'duplicate':
        node = next(b for b in backend.buttons['buttons'] if b['name'] == '9-1')
        backend.buttons['buttons'].append(deepcopy(node))
        backend.buttons['button_count'] += 1
    elif case == 'covered':
        backend.buttons['buttons'].append(make_button('custom_button_1(Clone)',
            'root/Msgbox(Clone)/window/button_container/custom_button_1(Clone)'))
        backend.buttons['button_count'] += 1
    elif case == 'wrong-package': backend.snapshot['package'] = 'wrong.package'
    elif case == 'stale': backend.snapshot['age_ms'] = 10001
    else:
        for node in backend.buttons['buttons']:
            if '/missionlist/path/' in node['path']: node['raycast_top'] = False
    with pytest.raises(SemanticGateClosed): oracle.swipe_guild_operations()
    assert not backend.swipes and not backend.taps


@pytest.mark.parametrize('delta', [0, 410])
def test_no_movement_or_wrong_direction_stops_after_one_drag(delta):
    backend, oracle, _ = scroll_host()
    backend.on_swipe = lambda: move(backend, delta)
    oracle._monotonic = Mock(side_effect=[0, 0, 6])
    with pytest.raises(SemanticTargetNotActionable): oracle.swipe_guild_operations()
    assert len(backend.swipes) == 1
    assert not backend.taps


def native_methods():
    tree = ast.parse(source('module/guild/operations.py'))
    owner = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'GuildOperations')
    wanted = {'_guild_operations_get_entrance', '_guild_operations_dispatch_swipe'}
    methods = [n for n in owner.body if isinstance(n, ast.FunctionDef) and n.name in wanted]
    namespace = dict(logger=Mock())
    exec(compile(ast.fix_missing_locations(ast.Module(body=methods, type_ignores=[])), '<native-guild-scroll>', 'exec'), namespace)
    return namespace


def test_original_five_attempt_loop_reads_visible_nodes_and_stops_when_found():
    methods = native_methods()
    adapter = Mock()
    node = make_oracle(backend_for_nodes(1)).guild_operation_visible_nodes()[0]
    adapter.guild_operation_visible_nodes.side_effect = [(), (), (node,)]
    device = SimpleNamespace(semantic_adapter=SimpleNamespace(open=lambda: adapter), screenshot=Mock())
    native = SimpleNamespace(device=device)
    native._guild_operations_get_entrance = lambda: methods['_guild_operations_get_entrance'](native)
    assert methods['_guild_operations_dispatch_swipe'](native, forward=False) is True
    assert adapter.swipe_guild_operations.call_args_list == [((False,),), ((False,),)]
    assert device.screenshot.call_count == 2


def test_original_loop_does_not_retry_an_input_without_postcondition():
    methods = native_methods()
    adapter = Mock()
    adapter.guild_operation_visible_nodes.return_value = ()
    adapter.swipe_guild_operations.side_effect = SemanticTargetNotActionable('guild/operations/scroll', 1)
    native = SimpleNamespace(device=SimpleNamespace(
        semantic_adapter=SimpleNamespace(open=lambda: adapter), screenshot=Mock()))
    native._guild_operations_get_entrance = lambda: methods['_guild_operations_get_entrance'](native)
    with pytest.raises(SemanticTargetNotActionable): methods['_guild_operations_dispatch_swipe'](native)
    assert adapter.swipe_guild_operations.call_count == 1


@pytest.mark.parametrize('changed_package', [False, True])
def test_fresh_input_frame_expires_but_result_uses_live_oracle(changed_package):
    from alas_headless.adapter import SemanticFrameClock, SemanticFrameReader, StaleFrameError
    backend, oracle, adapter = scroll_host()
    handle = SimpleNamespace(pid=backend.snapshot['pid'], fingerprint_sha256='a' * 64,
        observer_request=backend.request, foreground_component=backend.foreground_component,
        tap=backend.tap, swipe=backend.swipe)
    clock = SemanticFrameClock(handle, oracle)
    clock.acquire(include_ui=True)
    reader = SemanticFrameReader(clock, oracle)
    frozen = reader.oracle()
    adapter._fresh_input_oracle = lambda: frozen
    def changed():
        clock.invalidate()
        move(backend, backend.swipes[-1][2] - backend.swipes[-1][0])
        if changed_package: backend.snapshot['package'] = 'wrong.package'
    backend.on_swipe = changed
    if changed_package:
        with pytest.raises(SemanticGateClosed): adapter.swipe_guild_operations(True)
    else:
        assert adapter.swipe_guild_operations(True)['post_generation'] > frozen._last_generation
    assert len(backend.swipes) == 1
    with pytest.raises(StaleFrameError): frozen.read_state()


def test_actual_scrolled_chain_uses_rect_centers_outside_navbar():
    backend, oracle, _ = scroll_host(fixture='guild-operation-scrolled-r195.json')
    state, nodes, first, last = oracle._guild_operation_scroll_plan(True)
    assert first.name == '11-1'
    assert last.name == '9-1'
    assert round(last.point.x) == 255
    assert all(n.bounds.left >= 103 for n in nodes)
    backend.on_swipe = lambda: move(backend, backend.swipes[-1][2] - backend.swipes[-1][0])
    assert oracle.swipe_guild_operations()['post_generation'] > state.generation
    assert any(n.name == '12-1' for n in oracle.guild_operation_visible_nodes())
