import json
from pathlib import Path

import pytest

from alas_headless import SemanticGateClosed
from alas_headless.adapter.frame import _FrameBoundSemanticOracle
from alas_headless.semantic_oracle import SemanticOracle,OracleFingerprint
from tests.semantic_support.observer_fixtures import make_oracle,make_image,FakeBackend
from tests.test_semantic_oracle_opsi_storage_loggers import inventory,GRID


def test_coherent_inventory_card_missing_icon_settles_before_proving_absence():
    backend=inventory(include_icon=False)
    oracle=make_oracle(backend)
    sleeps=[]
    def publish(_):
        assert not backend.taps and oracle.input_dispatch_count==0
        sleeps.append(True)
        backend.snapshot['generation']=backend.buttons['generation']=14
        backend.ui['generation']=14
        backend.ui['images']=[make_image(GRID+'100/bg/icon_bg/icon','Wxingdonglihuifu1')]
        backend.ui['image_count']=1
        backend.ui['harmless_metadata']={'version':2}
    oracle._sleep=publish
    assert oracle.operation_siren_storage_loggers_absent()
    assert len(sleeps)==1 and not backend.taps and oracle.input_dispatch_count==0


@pytest.mark.parametrize('case',['missing','unknown-logger','duplicate','foreign','stale','foreground','incoherent'])
def test_incomplete_or_unsafe_inventory_never_reports_logger_absence(case):
    backend=inventory(include_icon=case!='missing')
    if case=='unknown-logger':backend.ui['images'][0]['sprite']='unopened_logger'
    elif case=='duplicate':
        backend.ui['images'].append(dict(backend.ui['images'][0]))
        backend.ui['image_count']+=1
    elif case=='foreign':backend.snapshot['package']='other.package'
    elif case=='stale':backend.snapshot['age_ms']=100000
    elif case=='foreground':backend.foreground='com.android.settings/.Settings'
    elif case=='incoherent':backend.ui['generation']=backend.buttons['generation']+3
    oracle=make_oracle(backend)
    sleeps=[]
    oracle._sleep=lambda _:sleeps.append(True)
    with pytest.raises(SemanticGateClosed):oracle.operation_siren_storage_loggers_absent()
    assert len(sleeps)==3 and not backend.taps and oracle.input_dispatch_count==0


def test_fixed_inventory_frame_does_not_re_read_or_sleep_when_icon_missing():
    backend=inventory(include_icon=False)
    original=make_oracle(backend)
    sleeps=[]
    oracle=_FrameBoundSemanticOracle(backend.request,backend.foreground_component,
        backend.tap,original.fingerprint,sleep=lambda _:sleeps.append(True),frame_guard=lambda:None)
    with pytest.raises(SemanticGateClosed,match='icon is missing'):oracle.operation_siren_storage_loggers_absent()
    assert not sleeps and not backend.taps


def test_retained_r97_later_diagnostic_inventory_is_complete_without_input():
    path=Path(__file__).resolve().parents[1]/'artifacts/continuity-20261004/goal-scheduler-r97.json'
    if not path.exists():pytest.skip('retained r97 later diagnostic inventory unavailable')
    frame=json.loads(path.read_text(encoding='utf8'))['tasks'][-1]['failure_observation']
    backend=FakeBackend([])
    backend.snapshot=frame['state']['snapshot']
    backend.buttons=frame['state']['buttons_snapshot']
    backend.ui=frame['ui']['snapshot']
    oracle=SemanticOracle(backend.request,backend.foreground_component,backend.tap,
        OracleFingerprint(package=backend.snapshot['package'],component=backend.foreground,
            driver_revision=backend.snapshot['driver_revision'],expected_pid=backend.snapshot['pid']))
    assert oracle.operation_siren_storage_loggers_absent()
    assert not backend.taps and oracle.input_dispatch_count==0
