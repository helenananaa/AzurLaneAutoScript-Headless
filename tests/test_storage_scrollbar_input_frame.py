"""Async scrollbar routing keeps each observation on a fresh semantic frame."""
from copy import deepcopy
import pytest

from alas_headless import AlasSemanticSession, SemanticGateClosed
from alas_headless.adapter import semantic_runtime_fingerprint_sha256
from tests.test_adapter_session_runtime_handle import FakeRuntimeHandle
from tests.test_storage_equipment_tab import material_host
from tests.test_storage_material_scroll_drag import actual_geometry
from tests.semantic_support.observer_fixtures import make_button


def scrolling_session(*, advance=3, drift=False, damage=None):
    backend, _, _ = material_host(drift)
    _, _, geometry, _ = actual_geometry()
    # Existing live material fixture + controlled native drag/progress model.
    # No fixture clock or original evidence is rewritten.
    backend.ui['storage_scroll']['scrollbar'] = deepcopy(geometry)
    bar = backend.ui['storage_scroll']['scrollbar']
    original = backend.request

    def tick(amount):
        for packet in (backend.snapshot, backend.buttons, backend.ui):
            packet['generation'] += amount

    def request(line):
        if line == 'GET /v1/ui\n':
            # Models the observed +3 split pair. Existing FrameClock brackets
            # it with unchanged atomic states instead of widening coherence.
            tick(advance)
        if line.startswith('GET /v1/storage-scrollbar-input '):
            backend.requests.append(line)
            point = list(map(float, line.split()[2:]))
            tick(1)
            bar['input'] = dict(schema='alas-headless.storage-scrollbar-input/v1',
                status=1, point=point, enabled=True, interactable=True, owned=True,
                handler_instance_id=bar['controls'][0]['instance_id'],
                top_path=bar['controls'][0]['path']+'/Handle/Image')
            if damage == 'other-handler':bar['input']['handler_instance_id'] += 999
            if damage == 'moved-handle':bar['controls'][1]['adb_bounds'].update(top=400,bottom=450)
            if damage == 'inactive':bar['controls'][1]['active_in_hierarchy'] = False
            if damage == 'foreground':backend.foreground = 'other/.Activity'
            if damage == 'loading':
                backend.buttons['buttons'].append(make_button('Loading(Clone)',
                    'OverlayCamera/Overlay/UIOverlay/Loading(Clone)'))
                backend.buttons['button_count'] += 1
            return dict(status='ok',scope='read-only-storage-scrollbar-input')
        return original(line)

    backend.request = request
    def moved():
        if damage != 'no-progress':bar['value'] = 0.
        tick(1)
    backend.on_swipe = moved
    revision = backend.snapshot['driver_revision']
    handle = FakeRuntimeHandle(semantic_runtime_fingerprint_sha256(
        package=backend.snapshot['package'],component=backend.foreground,
        driver_revision=revision,required_primary_abi='x86_64'))
    handle.pid = backend.snapshot['pid']
    handle.observer_request = backend.request
    handle.foreground_component = backend.foreground_component
    handle.tap, handle.swipe = backend.tap, backend.swipe
    session = AlasSemanticSession(driver_revision=revision,runtime_handle=handle)
    session.refresh_frame()
    return backend, session


@pytest.mark.parametrize('advance',[0,3])
@pytest.mark.parametrize('drift',[False,True])
def test_actual_session_async_drag_uses_coherent_frames_and_one_progress_receipt(advance,drift):
    backend,session = scrolling_session(advance=advance,drift=drift)
    try:
        receipt = session.storage_material_scroll_drag_toward(1.)
        assert receipt.semantic_id == 'storage/material/scroll'
        assert receipt.after_position == 1. and receipt.post_generation > receipt.generation
        assert backend.swipes == [(1260,128,1260,576,350)] and not backend.taps
        assert sum(x.startswith('GET /v1/storage-scrollbar-input ')for x in backend.requests) == 1
        frame = session._frame_clock._current
        if advance:
            assert frame.projections['ui_source_generation'] <= frame.generation
    finally:session.close()


@pytest.mark.parametrize('damage',['other-handler','moved-handle','inactive','foreground','loading'])
def test_async_refresh_cannot_borrow_old_drag_ownership(damage):
    backend,session = scrolling_session(damage=damage)
    try:
        with pytest.raises(SemanticGateClosed):session.storage_material_scroll_drag_toward(1.)
        assert not backend.taps and not backend.swipes
    finally:session.close()


def test_unproven_post_drag_progress_does_not_repeat_accepted_input():
    backend,session = scrolling_session(damage='no-progress')
    try:
        with pytest.raises(SemanticGateClosed,match='progress was not proven'):
            session.storage_material_scroll_drag_toward(1.)
        assert len(backend.swipes)==1 and not backend.taps
    finally:session.close()


def test_frame_expiring_after_routing_proof_cannot_dispatch_a_drag():
    from alas_headless.adapter.errors import ExpiredFrameError
    backend,session = scrolling_session()
    live = session.open()._live_oracle
    original = live._linked_scrollbar_input_proof
    def proof(*args,**kwargs):
        result = original(*args,**kwargs)
        clock = session._frame_clock
        monotonic = clock._monotonic_ns
        clock._monotonic_ns = lambda:monotonic()+20_000_000_000
        return result
    live._linked_scrollbar_input_proof = proof
    try:
        with pytest.raises(ExpiredFrameError):session.storage_material_scroll_drag_toward(1.)
        assert not backend.swipes and not backend.taps
    finally:session.close()
