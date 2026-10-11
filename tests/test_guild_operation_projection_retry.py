from copy import deepcopy

import pytest

from alas_headless import SemanticGateClosed
from alas_headless.adapter.frame import _FrameBoundSemanticOracle
from tests.semantic_support.observer_fixtures import make_oracle
from tests.test_guild_operation_candidates import backend_for_nodes, ROOT


@pytest.mark.parametrize('offset', [-1, 3])
def test_live_operation_re_reads_complete_projection_before_exact_single_input(offset):
    backend=backend_for_nodes()
    oracle=make_oracle(backend)
    backend.ui['generation']=backend.buttons['generation']+offset
    sleeps=[]
    def publish(_):
        assert not backend.taps and oracle.input_dispatch_count==0
        sleeps.append(True)
        backend.snapshot['generation']=backend.buttons['generation']=20
        backend.ui['generation']=20
        backend.ui['images'].reverse()
        backend.snapshot['upstream_addition']={'version':2}
    oracle._sleep=publish
    receipt=oracle.click_guild_active_operation(ROOT+'6-1')
    assert receipt.path==ROOT+'6-1' and receipt.generation==20
    assert len(sleeps)==1 and len(backend.taps)==1


@pytest.mark.parametrize('case', ['persistent','foreign','stale','ambiguous','disabled','wrong-page','foreground'])
def test_retry_preserves_unsafe_refusal_without_any_input(case):
    backend=backend_for_nodes()
    oracle=make_oracle(backend)
    if case=='persistent':
        backend.ui['generation']=backend.buttons['generation']+3
    elif case=='foreign':
        backend.snapshot['package']='other.package'
    elif case=='stale':
        backend.snapshot['age_ms']=100000
    elif case=='ambiguous':
        backend.buttons['buttons'].append(deepcopy(backend.buttons['buttons'][1]))
        backend.buttons['button_count']+=1
    elif case=='disabled':
        backend.buttons['buttons'][1]['interactable']=False
    elif case=='wrong-page':
        backend.ui['toggles']=[]
        backend.ui['toggle_count']=0
    else:
        backend.foreground='com.android.settings/.Settings'
    sleeps=[]
    oracle._sleep=lambda _:sleeps.append(True)
    with pytest.raises(SemanticGateClosed):
        oracle.click_guild_active_operation(ROOT+'6-1')
    assert not backend.taps and oracle.input_dispatch_count==0
    assert len(sleeps)<=3


def test_immutable_operation_frame_has_one_attempt_without_sleep():
    backend=backend_for_nodes()
    original=make_oracle(backend)
    backend.ui['generation']=backend.buttons['generation']+3
    sleeps=[]
    oracle=_FrameBoundSemanticOracle(backend.request,backend.foreground_component,
        backend.tap,original.fingerprint,sleep=lambda _:sleeps.append(True),frame_guard=lambda:None)
    with pytest.raises(SemanticGateClosed,match='not coherent'):
        oracle.guild_operations_state()
    assert not sleeps and not backend.taps


def test_accepted_operation_dispatch_is_never_retried_on_backend_failure():
    backend=backend_for_nodes()
    oracle=make_oracle(backend)
    error=SemanticGateClosed('accepted input completion uncertain')
    def uncertain(*_):
        raise error
    backend.on_tap=uncertain
    with pytest.raises(SemanticGateClosed) as caught:
        oracle.click_guild_active_operation(ROOT+'6-1')
    assert caught.value is error and len(backend.taps)==1
