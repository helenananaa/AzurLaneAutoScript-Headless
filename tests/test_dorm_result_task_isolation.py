import time

import pytest

from alas_headless import AlasSemanticSession, SemanticGateClosed
from alas_headless.adapter.semantic.contracts import AlasSemanticDormFeedResultUnproven
from alas_headless.adapter.task_lifecycle import TaskCapabilityUnavailable,semantic_task_scope
from alas_headless.oracle.errors import ObserverTransportError
from tests.semantic_support.adapter_fixtures import NamedButton
from tests.semantic_support.observer_fixtures import DRIVER_REVISION
from tests.test_dorm_native_batch_consumption import batch
from tests.test_opsi_native_camera_view import native


def task(delta=2):
    oracle,adapter=batch(delta)
    session=AlasSemanticSession('offline-test',DRIVER_REVISION)
    session.adapter=adapter
    return session,adapter,oracle


def fast_deadline(monkeypatch):
    clock=[time.monotonic()]
    monkeypatch.setattr('alas_headless.adapter.semantic.dorm.time.monotonic',lambda:clock[0])
    monkeypatch.setattr('alas_headless.adapter.semantic.dorm.time.sleep',lambda _:clock.__setitem__(0,clock[0]+6))


def test_accepted_food_with_complete_but_inconsistent_result_stops_only_dorm(monkeypatch):
    session,adapter,oracle=task()
    fast_deadline(monkeypatch)
    with pytest.raises(TaskCapabilityUnavailable) as caught:
        with semantic_task_scope(session,'dorm'):
            adapter.dorm_feed_food(0,1)
    cause=caught.value.cause
    assert isinstance(cause,AlasSemanticDormFeedResultUnproven)
    assert cause.observed_consumed==2 and cause.requested_count==1
    assert cause.receipt.semantic_id=='dorm/feed/item/50001'
    assert session.last_task_outcome=={'task':'dorm','outcome':'result-unproven'}
    assert adapter._dorm_context is None
    assert oracle.click_calls==['dorm/feed/item/50001']
    assert adapter._action_ledger.remaining('dorm.feed')==2
    oracle.exists_values['task/page/back']=True
    with semantic_task_scope(session,'reward'):
        assert adapter.appear(NamedButton('MISSION_CHECK'))
    assert session.last_task_outcome=={'task':'reward','outcome':'returned'}
    assert adapter._action_ledger.remaining('dorm.feed')==2


@pytest.mark.parametrize('error',[ObserverTransportError('malformed observer'),
    SemanticGateClosed('package identity failed'),SemanticGateClosed('target ambiguous'),
    SemanticGateClosed('game activity is not top-resumed'),SemanticGateClosed('stale semantic frame')])
def test_invalid_post_input_observation_does_not_become_local_result(error,monkeypatch):
    session,adapter,oracle=task(1)
    fast_deadline(monkeypatch)
    original=adapter._fresh_dorm_feed_state
    reads=[0]
    def fresh():
        reads[0]+=1
        if reads[0]>1:
            raise error
        return original()
    adapter._fresh_dorm_feed_state=fresh
    with pytest.raises(SemanticGateClosed) as caught:
        with semantic_task_scope(session,'dorm'):
            adapter.dorm_feed_food(0,1)
    assert not isinstance(caught.value,AlasSemanticDormFeedResultUnproven)
    assert caught.value.__cause__ is error
    assert session.last_task_outcome['outcome']=='raised'
    assert oracle.click_calls==['dorm/feed/item/50001']


def test_uncertain_food_dispatch_keeps_original_failure_without_retry():
    session,adapter,oracle=task(1)
    original=oracle.click_dorm_food
    error=ObserverTransportError('input completion uncertain')
    def uncertain(item_id):
        original(item_id)
        raise error
    oracle.click_dorm_food=uncertain
    with pytest.raises(ObserverTransportError) as caught:
        with semantic_task_scope(session,'dorm'):
            adapter.dorm_feed_food(0,1)
    assert caught.value is error
    assert oracle.click_calls==['dorm/feed/item/50001']
    assert session.last_task_outcome['outcome']=='raised'


def test_dorm_result_class_does_not_change_other_task_error_classification():
    session,adapter,oracle=task(1)
    receipt=oracle.click_dorm_food(50001)
    error=AlasSemanticDormFeedResultUnproven('unproven',receipt,1,0,0)
    with pytest.raises(AlasSemanticDormFeedResultUnproven) as caught:
        with semantic_task_scope(session,'research'):
            raise error
    assert caught.value is error
    assert session.last_task_outcome['outcome']=='raised'


@pytest.mark.parametrize('future', [False, True])
def test_original_scheduler_defers_real_dorm_result_and_executes_next_task(native, monkeypatch, future):
    from datetime import timedelta
    from unittest.mock import Mock
    from module.config.config import Function
    from tests.test_native_zero_interval_task_isolation import harness
    host,cfg,_,now=harness(interval=278)
    dorm=cfg.data.pop('OpsiExplore')
    dorm['Scheduler']['Command']='Dorm'
    dorm['Scheduler']['NextRun']=now+timedelta(minutes=27) if future else now-timedelta(seconds=1)
    cfg.data['Dorm']=dorm
    cfg.bind(Function(dorm))
    session,adapter,oracle=task()
    fast_deadline(monkeypatch)
    host.device.semantic_adapter=session
    host.dorm=Mock(side_effect=lambda:adapter.dorm_feed_food(0,1))
    assert host.run('dorm') is None
    assert session.last_task_outcome['outcome']=='result-unproven'
    assert cfg.data['Dorm']['Scheduler']['Enable'] is True
    if future:
        assert cfg.data['Dorm']['Scheduler']['NextRun']==now+timedelta(minutes=27)
    else:
        assert cfg.data['Dorm']['Scheduler']['NextRun']>=now+timedelta(minutes=278)
    next_task=cfg.get_next()
    assert next_task.command=='Minigame'
    cfg.bind(next_task)
    assert host.run('minigame') is True
    host.minigame.assert_called_once()
    assert host.failure_record=={}
    assert oracle.click_calls==['dorm/feed/item/50001']
    assert adapter._action_ledger.remaining('dorm.feed')==2
