"""Formation theme aliases reuse only the latest accepted navigation receipt."""
import json
from pathlib import Path
import time
from unittest.mock import Mock
from types import SimpleNamespace
import pytest
from alas_headless import AlasSemanticAdapter, SemanticGateClosed
from alas_headless.semantic_oracle import ActionReceipt,Bounds,Point,SemanticTargetMissing
from tests.semantic_support.observer_fixtures import FakeBackend,make_button,make_oracle,make_ui
from tests.test_gems_formation_page_discovery import formation

SOURCE="OverlayCamera/Overlay/UIMain/NewMainMellowTheme(Clone)/frame/right/1/formation"

def prior():return ActionReceipt("main/formation",9,Point(640,360),Bounds(620,340,660,380),SOURCE)

def host():
 b,o=formation();a=AlasSemanticAdapter(o,lambda:None);r=prior()
 a._commission_navigation_handoff=(r,o.input_dispatch_count,time.monotonic()+12)
 a._click_once=Mock(side_effect=SemanticTargetMissing("main/formation"))
 return b,o,a,r

@pytest.mark.parametrize("alias",["MAIN_GOTO_FLEET","MAIN_GOTO_FLEET_WHITE"])
def test_proven_arrival_reuses_receipt_with_no_second_input(alias):
 b,o,a,r=host()
 assert a.click(alias) is r
 a._click_once.assert_not_called();assert not b.taps

@pytest.mark.parametrize("alias",["MAIN_GOTO_FLEET","MAIN_GOTO_FLEET_WHITE"])
def test_native_first_entry_records_the_existing_handoff(alias):
 b,o=formation();a=AlasSemanticAdapter(o,lambda:None);r=prior()
 a._click_once=Mock(return_value=r)
 assert a.click(alias) is r
 assert a._commission_navigation_handoff[:2]==(r,o.input_dispatch_count)
 assert a.click("MAIN_GOTO_FLEET_WHITE") is r
 assert a._click_once.call_count==1

def test_accepted_source_still_pending_is_not_clicked_again():
 b=FakeBackend([make_button("formation",SOURCE)]);o=make_oracle(b);a=AlasSemanticAdapter(o,lambda:None);r=prior()
 a._commission_navigation_handoff=(r,o.input_dispatch_count,time.monotonic()+12)
 a._click_once=Mock(side_effect=AssertionError("No duplicate navigation input"))
 assert a.click("MAIN_GOTO_FLEET_WHITE") is r
 assert not b.taps

@pytest.mark.parametrize("fault",["expired","intervening_input","same_generation","stale","foreign","modal","incomplete","other_receipt"])
def test_old_or_unproved_navigation_never_becomes_an_acknowledgement(fault):
 b,o,a,r=host()
 if fault=="expired":a._commission_navigation_handoff=(r,o.input_dispatch_count,time.monotonic()-1)
 elif fault=="intervening_input":a._commission_navigation_handoff=(r,o.input_dispatch_count+1,time.monotonic()+12)
 elif fault=="same_generation":
  for v in (b.snapshot,b.buttons,b.ui):v["generation"]=r.generation
 elif fault=="stale":b.snapshot["age_ms"]=9000
 elif fault=="foreign":b.foreground="other.package/Activity"
 elif fault=="modal":o._blocking_rules=Mock(return_value=(SimpleNamespace(blocker_id="other-modal"),))
 elif fault=="incomplete":b.ui["images"].pop();b.ui["image_count"]-=1
 else:
  other=ActionReceipt("main/more",9,Point(640,360),r.bounds,"other/source")
  a._commission_navigation_handoff=(other,o.input_dispatch_count,time.monotonic()+12)
 with pytest.raises(SemanticGateClosed):a.click("MAIN_GOTO_FLEET_WHITE")
 assert not b.taps

def test_actual_refused_repeat_frame_is_the_proven_formation_destination():
 p=Path(__file__).resolve().parents[1]/"artifacts/full-feature-live-20261025/gems-original-roster-inspection-r1.json"
 if not p.exists():pytest.skip("Local live failure receipt unavailable")
 f=json.loads(p.read_text(encoding="utf-8"))["failure_observation"];u=f["ui"]["snapshot"]
 b=FakeBackend(f["state"]["buttons_snapshot"]["buttons"]);b.ui=make_ui(u["texts"],images=u["images"],toggles=u["toggles"])
 o=make_oracle(b);a=AlasSemanticAdapter(o,lambda:None);r=prior()
 a._commission_navigation_handoff=(r,o.input_dispatch_count,time.monotonic()+12)
 a._click_once=Mock(side_effect=AssertionError("No duplicate accepted edge"))
 assert a.click("MAIN_GOTO_FLEET_WHITE") is r
 assert not b.taps
