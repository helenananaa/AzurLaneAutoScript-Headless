"""A direct combat commit cannot leave ALAS observing the pre-input reward frame."""
from types import SimpleNamespace
from unittest.mock import Mock,patch
import pytest
from alas_headless import AlasSemanticSession, SemanticGateClosed
from alas_headless.adapter import StaleFrameError
from tests.test_adapter_frame import make_clock

@pytest.mark.parametrize('fails', [False, True])
def test_independently_proven_combat_commit_invalidates_previous_frame_before_dispatch(fails):
    handle,monotonic,clock=make_clock()
    frame=clock.acquire()
    adapter=SimpleNamespace(campaign_combat_committed=lambda:True,
                 meta_beacon_active=lambda:False,_campaign_context=None)
    session=AlasSemanticSession.__new__(AlasSemanticSession)
    session.open=lambda:adapter
    session._runtime_handle=handle;session._frame_clock=clock
    session._combat_last_generation=frame.generation-1
    receipt=SimpleNamespace(semantic_id='combat/resource/GET_ITEMS_1')
    commit=SimpleNamespace(commit_generation=frame.generation+1,action_name='GET_ITEMS_1',receipt=receipt)
    def dispatch(*_,**__):
        # An uncertain backend outcome must invalidate the source too.
        with pytest.raises(StaleFrameError):clock.borrow()
        if fails:raise SemanticGateClosed('dispatch outcome uncertain')
        handle.tap(100,100)
        return commit
    with patch.object(session,'_live_combat_manifest',return_value=object()),patch.object(
            session,'_arm_combat_result_transition'),patch(
            'alas_headless.adapter.semantic.session_combat.commit_alas_combat_resource_action_for_evidence',side_effect=dispatch):
        if fails:
            with pytest.raises(SemanticGateClosed,match='uncertain'):session._live_combat_click('GET_ITEMS_1')
        else:
            assert session._live_combat_click('GET_ITEMS_1') is receipt
            assert session._combat_last_result_receipt is receipt
    with pytest.raises(StaleFrameError):clock.borrow()
    # A new original screenshot still requires an advancing generation.
    handle.snapshot['generation']+=1;handle.buttons['generation']+=1;handle.ui['generation']+=1
    fresh=clock.acquire()
    assert fresh.generation>frame.generation
    assert len(handle.taps)==(0 if fails else 1)
