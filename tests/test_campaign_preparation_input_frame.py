"""Original entry/cancel calls use one current stage-bound preparation frame."""
import pytest

from alas_headless import SemanticGateClosed
from alas_headless.adapter import StaleFrameError
from tests.test_campaign_auto_search_input_frame import input_case,ROOT

@pytest.mark.parametrize('drift',[False,True])
@pytest.mark.parametrize('port',['MAP_PREPARATION','MAP_PREPARATION_CANCEL'])
def test_preparation_input_does_not_use_split_live_stage_pair(port,drift):
 b,a=input_case(drift=drift)
 if port.endswith('CANCEL'):a._campaign_context.entry_receipt=None
 receipt=a.click(port)
 assert receipt.semantic_id==('campaign/map-preparation/cancel' if port.endswith('CANCEL') else 'campaign/map-preparation/proceed')
 assert len(b.taps)==1
 assert a._action_ledger.remaining('campaign.stage_entry')==1

@pytest.mark.parametrize('damage',['stage','blocked','truncated','stale'])
@pytest.mark.parametrize('port',['MAP_PREPARATION','MAP_PREPARATION_CANCEL'])
def test_current_preparation_rejects_damage_without_input_or_spend(port,damage):
 b,a=input_case(damage=damage)
 if port.endswith('CANCEL'):a._campaign_context.entry_receipt=None
 if damage=='blocked':
  suffix='btnBack' if port.endswith('CANCEL') else 'start_button'
  next(button for button in b.buttons['buttons'] if button['path']==ROOT+suffix)['raycast_top']=False
 with pytest.raises((SemanticGateClosed,StaleFrameError)):a.click(port)
 assert not b.taps and a._action_ledger.remaining('campaign.stage_entry')==1
