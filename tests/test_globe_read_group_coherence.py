"""Globe read groups avoid repeated ADB foreground calls but keep end/input checks."""
from unittest.mock import patch
import pytest
from alas_headless import SemanticGateClosed
from tests.test_semantic_oracle_opsi_native_projection import native_fixture
from tests.test_globe_unpin_anchor import setup_unpin


def test_projection_checks_foreground_at_each_end_of_the_read_group():
    b,o,_=native_fixture();o._sleep=lambda _:None
    o.operation_siren_globe_map_projection((268,421))
    assert b.foreground_requests == 2
    assert not b.taps and not b.swipes


def test_projection_does_not_accept_foreground_changed_during_native_query():
    b,o,_=native_fixture();o._sleep=lambda _:None
    request=o._request
    def change(line):
        result=request(line)
        if line.startswith('GET /v1/globe-projection '):b.foreground='other/.Activity'
        return result
    o._request=change
    with pytest.raises(SemanticGateClosed):o.operation_siren_globe_map_projection((268,421))
    assert not b.taps and not b.swipes


def test_unpin_reuses_explicit_foreground_checks_for_adjacent_button_reads():
    b,o=setup_unpin();o._sleep=lambda _:None
    with patch.object(o,'operation_siren_globe_state'),patch.object(o,'operation_siren_globe_drag_owned',return_value=True):
        o.operation_siren_globe_unpin()
    assert b.foreground_requests == 4
    assert len(b.swipes)==1


def test_unpin_rechecks_foreground_after_native_path_proof_before_any_gesture():
    b,o=setup_unpin();o._sleep=lambda _:None
    def changed(*_):
        b.foreground='other/.Activity'
        return True
    with patch.object(o,'operation_siren_globe_state'),patch.object(o,'operation_siren_globe_drag_owned',side_effect=changed):
        with pytest.raises(SemanticGateClosed,match='changed after unpin drag proof'):o.operation_siren_globe_unpin()
    assert not b.taps and not b.swipes
