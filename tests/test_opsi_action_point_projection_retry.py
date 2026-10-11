import pytest
from alas_headless import AlasSemanticAdapter,SemanticGateClosed
from alas_headless.adapter.frame import _FrameBoundSemanticOracle
from tests.semantic_support.observer_fixtures import make_oracle
from tests.semantic_support.oracle_cases import OperationSirenSemanticOracleTestsSupport


def scene():
    backend=OperationSirenSemanticOracleTestsSupport._action_point_backend(selected_index=1)
    return backend,make_oracle(backend)


def test_complete_ap_pair_can_settle_before_one_cancel_input():
    backend,oracle=scene();backend.ui['generation']=13;sleeps=[]
    def publish(_):
        assert not backend.taps
        sleeps.append(True)
        backend.snapshot['generation']=backend.buttons['generation']=backend.ui['generation']=14
        backend.ui['texts'].reverse();backend.ui['upstream_addition']='compatible'
    oracle._sleep=publish
    receipt=oracle.click_operation_siren_action_point_control(False)
    assert receipt.generation==14 and len(backend.taps)==1 and len(sleeps)==1


@pytest.mark.parametrize('change',['persistent','missing','duplicate','stale','foreign','foreground'])
def test_ap_read_does_not_allow_input_from_an_invalid_panel(change):
    backend,oracle=scene()
    if change=='persistent':backend.ui['generation']=13
    elif change=='missing':backend.buttons['buttons'].pop(0);backend.buttons['button_count']-=1
    elif change=='duplicate':backend.buttons['buttons'].append(dict(backend.buttons['buttons'][0]));backend.buttons['button_count']+=1
    elif change=='stale':backend.snapshot['age_ms']=100000
    elif change=='foreign':backend.snapshot['package']='other.package'
    else:backend.foreground='com.android.settings/.Settings'
    oracle._sleep=lambda _:None
    with pytest.raises(SemanticGateClosed):oracle.click_operation_siren_action_point_control(False)
    assert not backend.taps


def test_immutable_ap_read_does_not_poll_the_same_split_frame():
    backend,live=scene();backend.ui['generation']=13;sleeps=[]
    fixed=_FrameBoundSemanticOracle(backend.request,backend.foreground_component,backend.tap,
        live.fingerprint,sleep=lambda _:sleeps.append(True),frame_guard=lambda:None)
    with pytest.raises(SemanticGateClosed,match='not coherent'):fixed.operation_siren_action_point_state()
    assert not sleeps and not backend.taps


def test_public_ap_state_keeps_one_existing_retry_budget_without_nesting():
    from unittest.mock import Mock
    backend,oracle=scene();backend.ui['generation']=13
    once=Mock(wraps=oracle._operation_siren_action_point_read_once)
    oracle._operation_siren_action_point_read_once=once
    def still_split(_):
        backend.snapshot['generation']+=4
        backend.buttons['generation']+=4
        backend.ui['generation']+=4
    oracle._sleep=still_split
    with pytest.raises(SemanticGateClosed,match='not coherent'):oracle.operation_siren_action_point_state()
    assert once.call_count==4 and not backend.taps


def test_cancel_uses_the_fresh_input_frame_and_does_not_repeat_uncertain_input():
    backend,live=scene();fresh=[]
    fixed=_FrameBoundSemanticOracle(backend.request,backend.foreground_component,live._tap,
        live.fingerprint,frame_guard=lambda:None)
    adapter=AlasSemanticAdapter(live,package_gate=lambda:None)
    adapter._fresh_input_oracle=lambda:fresh.append(True) or fixed
    error=SemanticGateClosed('AP cancel outcome uncertain')
    def uncertain(*_):raise error
    backend.on_tap=uncertain
    with pytest.raises(SemanticGateClosed) as caught:adapter.click_operation_siren_action_point_control(False)
    assert caught.value is error and fresh==[True] and len(backend.taps)==1
