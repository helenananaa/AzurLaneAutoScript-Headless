"""Real typed pooled-slot replay and fail-closed unknown/incomplete outcomes."""
from copy import deepcopy
import pytest
from alas_headless.oracle.errors import SemanticGateClosed
from tests.semantic_support.common_cv import rig

def test_real_pooled_slot_rebind_proves_single_deselection_without_resource_grant(monkeypatch):
    r=rig(monkeypatch,pooled=True)
    with r.delegate.retirement_preconfirm_scope(object()):
        target=r.delegate.retirement_match_common_cv('HERMES')
        receipt=r.delegate.retirement_deselect_common_cv(target)
    assert(receipt.selected_before,receipt.selected_after,receipt.capacity_used)==(13,12,873)
    assert receipt.post_instance_reused_by_template==201111
    assert receipt.modal_instance_id==target.card.instance_id
    assert len(r.handle.taps)==1 and r.cv_invalidated==[True]
    assert r.delegate.action_ledger.remaining('retirement.execute')==0

def test_unchanged_identity_does_not_prove_removal(monkeypatch):
    r=rig(monkeypatch);o=r.adapter._require_frame_observation_oracle()
    target=o.retirement_match_common_cv('HERMES')
    assert o.retirement_cv_deselection_instance_postcondition(target)==(False,None)

def test_incomplete_rebound_cannot_be_accepted_from_just_a_new_path(monkeypatch):
    r=rig(monkeypatch);o=r.adapter._require_frame_observation_oracle()
    target=o.retirement_match_common_cv('HERMES');frame=r.cv_fixture['frames']['after']
    r.handle.snapshot=deepcopy(frame['snapshot']);r.handle.buttons=deepcopy(frame['buttons']);r.handle.ui=deepcopy(frame['ui'])
    changed=0
    for image in r.handle.ui['images']:
        if '/DestoryInfoUI(Clone)/frame/sliders/content/201111/'in image['path']:
            image['sprite']='';changed+=1
    assert changed
    r.delegate.refresh_frame();o=r.adapter._require_frame_observation_oracle()
    with pytest.raises(SemanticGateClosed,match='incomplete'):
        o.retirement_cv_deselection_instance_postcondition(target)

def test_destroyed_old_instance_remains_a_compatible_postcondition(monkeypatch):
    r=rig(monkeypatch)
    with r.delegate.retirement_preconfirm_scope(object()):
        receipt=r.delegate.retirement_deselect_common_cv(r.delegate.retirement_match_common_cv('HERMES'))
    assert receipt.post_instance_reused_by_template is None and len(r.handle.taps)==1

def test_unknown_cv_input_is_not_replayed_after_task_cleanup(monkeypatch):
    r=rig(monkeypatch,unknown=True)
    with pytest.raises(OSError,match='outcome unknown'):
        with r.delegate.retirement_preconfirm_scope(object()):
            r.delegate.retirement_deselect_common_cv(r.delegate.retirement_match_common_cv('HERMES'))
    r.delegate.discard_old_retirement_task_state()
    assert r.delegate.retirement_cv_pending_evidence()['input_requested']
    with pytest.raises(SemanticGateClosed,match='unresolved'):
        with r.delegate.retirement_preconfirm_scope(object()):pass
    assert len(r.handle.taps)==1 and r.delegate.unrelated_capability_probe()=='unrelated capability remains available'

def test_missing_raycast_proof_refuses_before_input_and_keeps_unrelated_capability(monkeypatch):
    r=rig(monkeypatch,raycast=False)
    with pytest.raises(SemanticGateClosed,match='not actionable'):
        with r.delegate.retirement_preconfirm_scope(object()):
            r.delegate.retirement_deselect_common_cv(r.delegate.retirement_match_common_cv('HERMES'))
    assert not r.handle.taps and r.delegate.retirement_cv_pending_evidence() is None
    assert r.delegate.unrelated_capability_probe()=='unrelated capability remains available'
