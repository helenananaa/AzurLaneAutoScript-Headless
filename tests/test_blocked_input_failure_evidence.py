"""Controlled offline causal-evidence checks; no device or real failure frame."""
import json
from pathlib import Path
from types import MappingProxyType,SimpleNamespace

import pytest

import alas_headless.oracle.errors as source
from alas_headless.oracle.contracts import OracleState,Point,Bounds
from alas_headless.oracle.errors import SemanticInputBlocked,SemanticSnapshotStale
from alas_headless.oracle.opsi_state import OpsiStateOracle
from alas_headless.oracle.core import CoreOracle
from alas_headless.adapter.task_lifecycle import semantic_task_scope,TaskCapabilityUnavailable

ROOT=Path(__file__).resolve().parents[1]
assert ROOT/'python' in Path(source.__file__).resolve().parents

def state(generation=4242,extra=False):
    snapshot=dict(pid=10867,generation=generation,package='com.bilibili.azurlane')
    if extra:snapshot['future_metadata']=MappingProxyType({'schema':3,'values':('a','b')})
    return OracleState(generation,-76,MappingProxyType(snapshot),
        MappingProxyType(dict(generation=generation,buttons=(MappingProxyType({'path':'root/back','bounds':MappingProxyType({'x':1})}),))),())

def port_host(observed,blockers=('loading',)):
    calls=dict(reads=0,taps=[])
    def read():calls['reads']+=1;return observed
    host=SimpleNamespace(operation_siren_storage_visible=lambda:False,
        _operation_siren_exit_prompt_state=lambda:None,operation_siren_state=lambda:None,
        read_state=read,_unique=lambda *a:SimpleNamespace(active_in_hierarchy=True,active_and_enabled=True,
            interactable=True,raycast_top=None,point=Point(100,100),bounds=Bounds(80,80,120,120),path='root/back'),
        _blocking_rules=lambda *a:[SimpleNamespace(blocker_id=b) for b in blockers],
        _foreground_component=lambda:'exact-component',fingerprint=SimpleNamespace(component='exact-component'),
        _tap=lambda *p:calls['taps'].append(p))
    return host,calls

@pytest.mark.parametrize('extra',[False,True])
def test_original_port_retains_exact_already_read_state_and_no_input(extra):
    observed=state(extra=extra);host,calls=port_host(observed)
    with pytest.raises(SemanticInputBlocked) as failed:
        OpsiStateOracle.click_operation_siren_back(host)
    assert failed.value.observed_state is observed
    assert failed.value.generation==4242 and failed.value.blockers==('loading',)
    assert calls==dict(reads=1,taps=[])

def test_successful_back_keeps_its_original_action_and_has_no_diagnostic_read():
    host,calls=port_host(state(),blockers=())
    receipt=OpsiStateOracle.click_operation_siren_back(host)
    assert receipt.semantic_id=='os/page/back' and receipt.generation==4242
    assert calls==dict(reads=1,taps=[(100,100)])

@pytest.mark.parametrize('extra',[False,True])
def test_terminal_record_survives_cleanup_and_mappingproxy_without_later_read(extra):
    observed=state(extra=extra);later=state(9999)
    error=SemanticInputBlocked('os/page/back',4242,('loading',),observed_state=observed)
    session=SimpleNamespace(trace=None,current_state=observed)
    def cleanup():session.current_state=later
    session.discard_task_state=cleanup
    with pytest.raises(TaskCapabilityUnavailable) as ended:
        with semantic_task_scope(session,'dorm'):raise error
    assert ended.value.cause is error and session.current_state.generation==9999
    record=session.last_task_error['input_admission_observation']
    assert record['state']['generation']==4242
    assert record['state']['snapshot']['generation']==4242
    assert record['state']['buttons_snapshot']['buttons'][0]['bounds']=={'x':1}
    assert session.last_task_outcome==dict(task='dorm',outcome='input-unavailable')
    assert json.loads(json.dumps(session.last_task_error))['input_admission_observation']['state']['generation']==4242

def test_legacy_call_shape_and_error_record_are_unchanged_without_state():
    error=SemanticInputBlocked('os/page/back',4242,('loading',))
    assert error.observed_state is None
    session=SimpleNamespace(trace=None,discard_task_state=lambda:None)
    with pytest.raises(TaskCapabilityUnavailable):
        with semantic_task_scope(session,'dorm'):raise error
    assert session.last_task_error==dict(type='SemanticInputBlocked',message='semantic input is blocked by: loading',semantic_id='os/page/back',generation=4242,blockers=['loading'])

def test_failed_diagnostic_encoding_preserves_original_classification_and_cause():
    error=SemanticInputBlocked('os/page/back',4242,('loading',),observed_state=object())
    session=SimpleNamespace(trace=None,discard_task_state=lambda:None)
    with pytest.raises(TaskCapabilityUnavailable) as ended:
        with semantic_task_scope(session,'dorm'):raise error
    assert ended.value.cause is error
    assert session.last_task_error['type']=='SemanticInputBlocked'
    assert session.last_task_error['input_admission_recording_error']['type']=='TypeError'
    assert 'input_admission_observation' not in session.last_task_error
    json.dumps(session.last_task_error)

def test_uncertain_post_dispatch_read_still_escapes_with_one_dispatch_and_no_retry():
    error=SemanticSnapshotStale(9999);dispatches=[]
    def backend(*p):raise error
    host=SimpleNamespace(_input_preflight=None,_mark_input_dispatched=lambda:dispatches.append(True),_tap_backend=backend)
    session=SimpleNamespace(trace=None,discard_task_state=lambda:None)
    with pytest.raises(SemanticSnapshotStale) as ended:
        with semantic_task_scope(session,'dorm'):CoreOracle._dispatch_tap(host,1,2)
    assert ended.value is error and error.input_outcome_uncertain
    assert dispatches==[True] and session.last_task_outcome['outcome']=='raised'
    assert 'input_admission_observation' not in session.last_task_error
