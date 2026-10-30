"""Preparation identity and switch input share one current typed frame."""
import time
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from alas_headless import AlasSemanticAdapter,SemanticGateClosed
from alas_headless.adapter import StaleFrameError
from alas_headless.adapter.frame import _FrameBoundSemanticOracle
from tests.semantic_support.observer_fixtures import FakeBackend,make_button,make_text,make_toggle,make_ui,make_oracle

ROOT='OverlayCamera/Overlay/UIMain/LevelStageInfoView(Clone)/panel/'
TOGGLE=ROOT+'BottomExtra/LoopGroup/view/container/AutoFight'

def input_case(*,drift=False,damage=None):
 b=FakeBackend([make_button('start_button',ROOT+'start_button',951,523),make_button('btnBack',ROOT+'btnBack',1066,149)])
 b.ui=make_ui([make_text('12-4',ROOT+'title_form/title_index'),make_text('TF58',ROOT+'title_form/title')],
  toggles=[make_toggle(TOGGLE,checked=True,x=838,y=596)])
 if drift:b.buttons['optional_metadata']={'new':True}
 if damage=='stage':b.ui['texts'][0]['text']='12-3'
 if damage=='state':b.ui['toggles'][0]['checked']=False
 if damage=='blocked':b.ui['toggles'][0]['raycast_top']=False
 if damage=='truncated':b.ui['toggle_truncated']=True
 live=make_oracle(b)
 # Model the observed advisory read: independent live reads are incoherent.
 live.campaign_preparation_state=Mock(side_effect=SemanticGateClosed('campaign snapshots are not coherent'))
 def guard():
  if damage=='stale':raise StaleFrameError()
 fresh=_FrameBoundSemanticOracle(b.request,b.foreground_component,live._tap,live.fingerprint,
  frame_guard=guard,input_dispatch_counter=lambda:live.input_dispatch_count)
 a=AlasSemanticAdapter(live,lambda:None,campaign_stage_entry_budget=1,
  input_frame_refresher=Mock(),frame_observation_oracle=lambda:fresh)
 a.begin_campaign_pre_sortie('12-4')
 a._campaign_context.entry_receipt=SimpleNamespace(semantic_id='campaign/stage/12-4',generation=9)
 a._campaign_context.passive_transition_until=time.monotonic()+30
 return b,a

@pytest.mark.parametrize('drift',[False,True])
def test_auto_search_input_uses_one_fresh_stage_and_switch_frame(drift):
 b,a=input_case(drift=drift)
 receipt=a.click('AUTO_SEARCH_ON')
 assert receipt.semantic_id=='campaign/map-preparation/auto-search'
 assert b.taps==[(838,596)]
 a._input_frame_refresher.assert_called_once()

@pytest.mark.parametrize('damage',['stage','state','blocked','truncated','stale'])
def test_changed_or_unusable_current_preparation_never_borrows_old_positive(damage):
 b,a=input_case(damage=damage)
 with pytest.raises((SemanticGateClosed,StaleFrameError)):a.click('AUTO_SEARCH_ON')
 assert not b.taps
 assert a._campaign_context.auto_search_toggle_receipt is None
 assert a._action_ledger.remaining('campaign.stage_entry')==1

def test_current_frame_does_not_supply_missing_stage_entry_authority():
 b,a=input_case()
 a._campaign_context.entry_receipt=None
 with pytest.raises(SemanticGateClosed,match='proven stage entry'):a.click('AUTO_SEARCH_ON')
 assert not b.taps
