"""One owned scrollbar drag, including padded/off-screen handles and no-input cases."""
import pytest
from alas_headless import SemanticGateClosed
from tests.test_storage_scrollbar_observation import storage
from tests.test_storage_scrollbar_input_observation import routing, queried
from tests.semantic_support.observer_fixtures import make_button


def actual_geometry(direction=2):
    backend, oracle = storage()
    bar = backend.ui['storage_scroll']['scrollbar']
    bar.update(direction=direction, value=1 if direction == 2 else 0, size=.1)
    for row in bar['controls']:
        row['adb_bounds'] = (dict(left=1230.4, top=90.667, right=1289.6, bottom=164.533)
                             if row['role'] == 'handle'
                             else dict(left=1257.067, top=104, right=1262.933, bottom=576))
    raw = routing(backend, point=[1260, 128])
    queried(backend, oracle, raw)
    return backend, oracle, bar, raw


@pytest.mark.parametrize('direction', [2, 3])
def test_padded_handle_reaches_native_track_edge_with_one_owned_drag(direction):
    backend, oracle, bar, _ = actual_geometry(direction)
    def moved():
        bar['value'] = 0 if direction == 2 else 1
        for packet in (backend.snapshot, backend.buttons, backend.ui): packet['generation'] += 1
    backend.on_swipe = moved
    receipt = oracle.drag_storage_material_scroll_toward(1)
    # The padded handle remains a valid start. Terminal gestures reach the
    # exported track edge so Unity can clamp to the actual endpoint.
    assert backend.swipes == [(1260, 128, 1260, 576, 350)]
    assert (receipt.before_position, receipt.after_position) == (0, 1)
    assert receipt.post_generation > receipt.generation
    assert not backend.taps


@pytest.mark.parametrize('case', ['already-top', 'entire-list-visible'])
def test_noop_does_not_require_a_swipe_backend_or_query(case):
    backend, oracle, bar, _ = actual_geometry()
    oracle._swipe = None
    if case == 'entire-list-visible': bar['size'] = 1
    assert oracle.drag_storage_material_scroll_toward(0 if case == 'already-top' else 1) is None
    assert not backend.swipes and not backend.taps
    assert not any('storage-scrollbar-input' in q for q in backend.requests)


@pytest.mark.parametrize('case', ['unowned', 'moved-handle', 'inactive', 'loading', 'foreground'])
def test_changed_or_obscured_drag_start_never_dispatches(case):
    backend, oracle, bar, raw = actual_geometry()
    if case == 'unowned': raw['owned'] = False
    original = oracle._request
    def request(line):
        result = original(line)
        if line.startswith('GET /v1/storage-scrollbar-input'):
            if case == 'moved-handle': bar['controls'][1]['adb_bounds'].update(top=400, bottom=450)
            elif case == 'inactive': bar['controls'][1]['active_in_hierarchy'] = False
            elif case == 'loading':
                backend.buttons['buttons'].append(make_button('Loading(Clone)', 'OverlayCamera/Overlay/UIOverlay/Loading(Clone)'))
                backend.buttons['button_count'] += 1
            elif case == 'foreground': backend.foreground = 'other/.Activity'
        return result
    oracle._request = request
    with pytest.raises(SemanticGateClosed): oracle.drag_storage_material_scroll_toward(1)
    assert not backend.swipes and not backend.taps


@pytest.mark.parametrize('case', ['no-progress', 'different-owner'])
def test_uncertain_postcondition_is_not_retried_or_reported_as_success(case):
    backend, oracle, bar, _ = actual_geometry()
    def changed():
        for packet in (backend.snapshot, backend.buttons, backend.ui): packet['generation'] += 1
        if case == 'different-owner': bar['controls'][0]['instance_id'] += 100
    backend.on_swipe = changed
    with pytest.raises(SemanticGateClosed): oracle.drag_storage_material_scroll_toward(1)
    assert len(backend.swipes) == 1 and not backend.taps



def test_last_inventory_row_requires_real_bottom_even_inside_old_five_percent_tolerance():
    backend,oracle,bar,raw=actual_geometry()
    bar['value']=.023749
    bar['controls'][1]['adb_bounds'].update(top=515,bottom=589)
    raw['point']=[1260,552]
    def moved():
        bar['value']=0
        for packet in (backend.snapshot,backend.buttons,backend.ui):packet['generation']+=1
    backend.on_swipe=moved
    receipt=oracle.drag_storage_material_scroll_toward(1)
    assert backend.swipes==[(1260,552,1260,576,350)]
    assert receipt.after_position==1



def test_intermediate_target_retains_native_size_travel_instead_of_endpoint_clamp():
    backend,oracle,bar,_=actual_geometry()
    def moved():
        bar['value']=.5
        for packet in (backend.snapshot,backend.buttons,backend.ui):packet['generation']+=1
    backend.on_swipe=moved
    receipt=oracle.drag_storage_material_scroll_toward(.5)
    assert backend.swipes==[(1260,128,1260,340,350)]
    assert receipt.after_position==.5
