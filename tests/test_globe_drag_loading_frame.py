from unittest.mock import Mock
import pytest
from alas_headless import SemanticGateClosed
from tests.test_semantic_oracle_opsi_port_geometry import fixture

LOADING = 'OverlayCamera/Overlay/UIOverlay/Loading(Clone)'
PLANE = 'WorldMap3D/entity/Plane'

def test_previous_loading_proof_is_reobserved_after_blocker_disappears():
    _, oracle = fixture()
    oracle._blocking_rules = Mock(return_value=())
    oracle.operation_siren_globe_drag_proof = Mock(side_effect=[
        (10, {'samples': [{'owned': False, 'top_path': LOADING}]}),
        (11, {'samples': [{'owned': True, 'top_path': PLANE}]}),
    ])
    assert oracle.operation_siren_globe_drag_owned((200,300),(500,400))
    assert oracle.operation_siren_globe_drag_proof.call_count == 2

@pytest.mark.parametrize('path', [LOADING, 'UnknownUI/Loading(Clone)', 'SVFloatPanel(Clone)/bg'])
def test_persistent_loading_or_other_owner_never_becomes_owned(path):
    backend, oracle = fixture()
    oracle._blocking_rules = Mock(return_value=())
    oracle.operation_siren_globe_drag_proof = Mock(return_value=(10, {'samples': [{'owned':False,'top_path':path}]}))
    if path == LOADING:
        with pytest.raises(SemanticGateClosed, match='loading did not settle'):
            oracle.operation_siren_globe_drag_owned((200,300),(500,400))
        assert oracle.operation_siren_globe_drag_proof.call_count == 30
    else:
        assert not oracle.operation_siren_globe_drag_owned((200,300),(500,400))
        assert oracle.operation_siren_globe_drag_proof.call_count == 1
    assert backend.taps == []
    assert backend.swipes == []
