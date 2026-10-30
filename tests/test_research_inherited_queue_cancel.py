"""Native Research cancels an inherited unsubmitted queue prompt before discovery."""
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from alas_headless import SemanticGateClosed
from tests.test_research_queue_frame_input import queue_confirm_session
from tests.test_alas_config_branch_compatibility import method
from tests.semantic_support.adapter_fixtures import NamedButton

PORT='RESEARCH_INHERITED_QUEUE_CANCEL'

def inherited(drift=False):
    backend,bridge,session,adapter=queue_confirm_session(drift=drift)
    adapter.end_research();adapter.begin_research()
    for projection in (backend.snapshot,backend.buttons,backend.ui):
        projection['generation']+=1
    session.refresh_frame(include_ui=True)
    return backend,bridge,session,adapter

@pytest.mark.parametrize('drift',[False,True])
def test_exact_inherited_queue_can_only_cancel_without_resource_mutation(drift):
    backend,_,session,adapter=inherited(drift)
    assert session.appear(PORT)
    receipt=session.click(PORT)
    assert receipt.semantic_id=='research/queue/cancel'
    assert len(backend.taps)==1
    assert adapter._action_ledger.remaining('research.start')==1
    assert adapter._research_context.selected_code is None

@pytest.mark.parametrize('damage',['prompt','blocked','duplicate','owned'])
def test_unreviewed_or_owned_dialog_cannot_use_inherited_cancel(damage):
    backend,_,session,adapter=inherited()
    if damage=='prompt':backend.ui['texts'][1]['text']='是否花费钻石购买物品？'
    elif damage=='blocked':backend.buttons['buttons'][-1]['raycast_top']=False
    elif damage=='duplicate':
        backend.buttons['buttons'].append(dict(backend.buttons['buttons'][-1]))
        backend.buttons['button_count']+=1
    else:adapter._research_context.selected_code='D-332-MI'
    with pytest.raises(SemanticGateClosed):session.click(PORT)
    assert not backend.taps and adapter._action_ledger.remaining('research.start')==1

def test_recovery_port_does_not_admit_other_task_context():
    backend,_,session,adapter=inherited()
    adapter.end_research()
    assert not session.appear(PORT)
    with pytest.raises(SemanticGateClosed):session.click(PORT)
    assert not backend.taps

@pytest.mark.parametrize('has_inherited',[False,True])
def test_current_patched_native_run_owns_cancel_then_original_navigation(has_inherited):
    events=[]
    api=SimpleNamespace(begin_research=lambda:events.append('begin'),end_research=lambda:events.append('end'),
        appear=lambda port:has_inherited,click=lambda port:events.append(('cancel',port)))
    device=SimpleNamespace(semantic_adapter=api,screenshot=lambda:events.append('refresh'))
    runner=SimpleNamespace(device=device,appear=lambda button:True,
        research_detail_quit=lambda:events.append('original-detail-quit'),is_in_queue=lambda:False,
        _run_alas_state_machine=lambda:events.append('original-state-machine') or True)
    run=method('module/research/research.py','RewardResearch','run',RESEARCH_DETAIL_QUIT=NamedButton('RESEARCH_DETAIL_QUIT'))
    assert run(runner) is True
    expected=['begin']
    if has_inherited:expected += [('cancel',PORT),'refresh']
    assert events==expected+['original-detail-quit','original-state-machine','end']
