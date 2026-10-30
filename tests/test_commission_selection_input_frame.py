"""Row/recommend/start authority must come from one fresh typed input frame."""
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from alas_headless import AlasSemanticAdapter, SemanticGateClosed
from alas_headless.adapter import StaleFrameError
from alas_headless.adapter.frame import _FrameBoundSemanticOracle
from tests.test_combat_screenshot_observation import host
from tests.test_commission_start_pending import pending,SIGNATURE
from tests.semantic_support.observer_fixtures import set_commission_scroll_view


@pytest.mark.parametrize('drift',[False,True])
def test_row_selection_uses_fresh_input_frame_instead_of_split_live_pair(drift):
    backend,session,_=host('combat',False)
    set_commission_scroll_view(backend,index=0,name='current',handle_top=75,generation=11)
    if drift:backend.buttons['optional_metadata']='additive'
    session.refresh_frame();session.begin_commission()
    signature=session.commission_rows()[0].signature
    session.open().oracle.click_commission_row=Mock(side_effect=SemanticGateClosed('split live row pair'))
    receipt=session.click(SimpleNamespace(name='COMMISSION_ROW_0',semantic_commission_signature=signature))
    assert receipt.semantic_id=='commission/row/0' and len(backend.taps)==1


def test_changed_row_cannot_borrow_original_positive_selection():
    backend,session,_=host('combat',False)
    set_commission_scroll_view(backend,index=0,name='before',handle_top=75,generation=11)
    session.refresh_frame();session.begin_commission()
    signature=session.commission_rows()[0].signature
    set_commission_scroll_view(backend,index=0,name='changed',handle_top=75,generation=12)
    with pytest.raises(SemanticGateClosed,match='identity'):
        session.click(SimpleNamespace(name='COMMISSION_ROW_0',semantic_commission_signature=signature))
    assert not backend.taps


def detail_case(*,drift=False,changed=False,stale=False):
    backend,live,_=pending(drift)
    if changed:
        next(t for t in backend.ui['texts'] if t['path'].endswith('/scrollItem/labelName$'))['text']='changed commission'
    def guard():
        if stale:raise StaleFrameError()
    fresh=_FrameBoundSemanticOracle(backend.request,backend.foreground_component,live._tap,
        live.fingerprint,frame_guard=guard,input_dispatch_counter=lambda:live.input_dispatch_count)
    adapter=AlasSemanticAdapter(live,lambda:None,commission_start_budget=1,
        input_frame_refresher=Mock(),frame_observation_oracle=lambda:fresh)
    adapter.begin_commission();adapter._commission_context.selected_signature=SIGNATURE
    live.commission_detail_state=Mock(side_effect=SemanticGateClosed('split live detail pair'))
    live.click_commission_recommend=Mock(side_effect=SemanticGateClosed('split live recommend pair'))
    live.click_commission_start=Mock(side_effect=SemanticGateClosed('split live start pair'))
    return backend,adapter


@pytest.mark.parametrize('drift',[False,True])
@pytest.mark.parametrize('port',['COMMISSION_ADVICE','COMMISSION_START'])
def test_detail_input_reuses_its_fresh_signature_and_assigned_ships(port,drift):
    backend,adapter=detail_case(drift=drift)
    receipt=adapter.click(port)
    assert receipt.semantic_id==('commission/detail/recommend' if port=='COMMISSION_ADVICE' else 'commission/detail/start')
    assert len(backend.taps)==1
    assert adapter._action_ledger.remaining('commission.start')==(0 if port=='COMMISSION_START' else 1)


@pytest.mark.parametrize('port',['COMMISSION_ADVICE','COMMISSION_START'])
def test_changed_detail_rejects_input_and_preserves_unused_grant(port):
    backend,adapter=detail_case(changed=True)
    with pytest.raises(SemanticGateClosed,match='identity changed'):
        adapter.click(port)
    assert not backend.taps and adapter._action_ledger.remaining('commission.start')==1


def test_expired_start_input_frame_cannot_consume_or_replay_grant():
    backend,adapter=detail_case(stale=True)
    with pytest.raises(StaleFrameError):adapter.click('COMMISSION_START')
    assert not backend.taps and adapter._action_ledger.remaining('commission.start')==1
