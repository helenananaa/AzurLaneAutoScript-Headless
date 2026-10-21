"""Post-input activity checks do not resurrect an invalidated semantic frame."""
from unittest.mock import Mock
import pytest
from alas_headless import AlasSemanticSession, SemanticGateClosed
from alas_headless.adapter import AdbRuntimeHandle, StaleFrameError, semantic_runtime_fingerprint_sha256
from alas_headless.semantic_oracle import AdbObserverBridge
from tests.test_game_tips_loading_presence import host


def session_for_meta(fixture='meta-challenge-return-r34.json'):
    backend,oracle,_=host(fixture=fixture)
    bridge=AdbObserverBridge('offline-meta-home',backend.snapshot['package'])
    bridge.pid=backend.snapshot['pid'];bridge.request=backend.request
    bridge.foreground_component=backend.foreground_component;bridge.tap=backend.tap;bridge.swipe=backend.swipe
    bridge.package_pid=Mock(return_value=bridge.pid)
    rev=backend.snapshot['driver_revision']
    fp=semantic_runtime_fingerprint_sha256(package=backend.snapshot['package'],component=backend.foreground,
                                          driver_revision=rev,required_primary_abi='x86_64')
    session=AlasSemanticSession(driver_revision=rev,runtime_handle=AdbRuntimeHandle(bridge,fingerprint_sha256=fp))
    session.refresh_frame()
    return backend,session,session.open()._require_frame_observation_oracle()


@pytest.mark.parametrize('foreign_after', [False, True])
def test_actual_meta_home_checks_live_activity_after_one_input_without_reading_old_frame(foreign_after):
    backend,session,oracle=session_for_meta()
    def tap(*_):
        assert session._frame_clock.current_frame_id is None
        if foreign_after:backend.foreground='other/.Activity'
    backend.on_tap=tap
    if foreign_after:
        with pytest.raises(SemanticGateClosed,match='foreground changed after META home input'):oracle.click_meta_home()
    else:
        assert oracle.click_meta_home().semantic_id=='meta/home'
    assert len(backend.taps)==1
    for read in (oracle.read_state,oracle.read_ui_state,oracle.click_meta_home):
        with pytest.raises(StaleFrameError):read()
    assert len(backend.taps)==1


def test_changed_foreground_before_meta_home_is_rejected_without_input():
    backend,session,oracle=session_for_meta()
    backend.foreground='other/.Activity'
    with pytest.raises(SemanticGateClosed,match='changed before semantic input'):oracle.click_meta_home()
    assert not backend.taps
