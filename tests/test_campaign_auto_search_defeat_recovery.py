"""Original auto-search result handlers own recovery after an exact defeat tip."""
import ast
import copy
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from alas_headless import SemanticGateClosed
from alas_headless.oracle.errors import SemanticNavigationPending
from tests.alas_test_source import patched_alas_root
from tests.semantic_support.observer_fixtures import FakeBackend,make_button,make_text,make_ui,make_oracle,make_buttons,make_snapshot

ROOT="OverlayCamera/Overlay/UIMain/BattleFailTipUI(Clone)/"

def backend():
 b=FakeBackend([make_button("CloseBtn",ROOT+"Main/CloseBtn",raycast_top=None)])
 b.ui=make_ui([make_text("DEFEAT",ROOT+"BG/BG/bg_fail/bg03/Text")])
 return b

def disappear(b):
 b.snapshot=make_snapshot(11);b.buttons=make_buttons([],11);b.ui=make_ui([],generation=11)

def test_defeat_tip_close_proves_fresh_disappearance():
 b=backend();b.on_tap=lambda:disappear(b)
 assert make_oracle(b).close_campaign_battle_fail_tip_if_present()
 assert len(b.taps)==1

@pytest.mark.parametrize("fault",["duplicate","wrong_label","foreign","stale","occluded","incoherent","blocked"])
def test_defeat_tip_rejects_unsafe_input(fault):
 b=backend();o=make_oracle(b)
 if fault=="duplicate":b.buttons["buttons"].append(copy.deepcopy(b.buttons["buttons"][0]));b.buttons["button_count"]+=1
 elif fault=="wrong_label":b.ui["texts"][0]["text"]="VICTORY"
 elif fault=="foreign":b.foreground="other.package/Activity"
 elif fault=="stale":b.snapshot["age_ms"]=9000
 elif fault=="occluded":b.buttons["buttons"][0]["raycast_top"]=False
 elif fault=="incoherent":b.ui["generation"]=13
 else:o._blocking_rules=Mock(return_value=("other-dialog",))
 with pytest.raises(SemanticGateClosed):o.close_campaign_battle_fail_tip_if_present()
 assert not b.taps

def test_pending_accepted_close_keeps_receipt_without_repeat():
 b=backend()
 with pytest.raises(SemanticNavigationPending) as failure:make_oracle(b).close_campaign_battle_fail_tip_if_present()
 assert len(b.taps)==1
 assert failure.value.receipt.path==ROOT+"Main/CloseBtn"

def test_absent_tip_has_no_input():
 b=FakeBackend([])
 assert not make_oracle(b).close_campaign_battle_fail_tip_if_present()
 assert not b.taps

def test_actual_failed_frame_keeps_exact_tip_identity():
 p=Path(__file__).resolve().parents[1]/"artifacts/full-feature-live-20261025/main3-boss-status-readonly-r1.json"
 if not p.exists():pytest.skip("Local failure frame unavailable")
 d=json.loads(p.read_text(encoding="utf-8"));wire=d["ui"]["snapshot"]
 b=FakeBackend(d["state"]["buttons_snapshot"]["buttons"]);b.ui=make_ui(wire["texts"],images=wire["images"],toggles=wire["toggles"])
 b.on_tap=lambda:disappear(b)
 assert make_oracle(b).close_campaign_battle_fail_tip_if_present()
 assert len(b.taps)==1

@pytest.mark.parametrize("mode",["defeat","ordinary","legacy","error"])
def test_native_auto_search_reuses_existing_statistics_handlers_only_after_close(mode):
 tree=ast.parse((patched_alas_root()/"module/combat/auto_search_combat.py").read_text(encoding="utf-8"))
 method=next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name=="auto_search_combat_status")
 frame=[None];actions=[]
 def loop():
  for value in ("defeat","statistics","map"):
   frame[0]=value;yield
 def close():
  if mode=="error":raise SemanticGateClosed("Unproved tip input")
  if mode=="defeat" and frame[0]=="defeat":actions.append("close");return True
  return False
 port=Mock(side_effect=close)
 class Host(SimpleNamespace):
  def __getattr__(self,name):
   if name.startswith("handle_"):return lambda *a,**kw:False
   raise AttributeError(name)
 def statistics():
  if frame[0]=="statistics":actions.append("statistics");return True
  return False
 h=Host(device=SimpleNamespace(semantic_adapter=None if mode=="legacy" else SimpleNamespace(close_campaign_battle_fail_tip_if_present=port),stuck_record_clear=Mock(),click_record_clear=Mock()),loop=loop,
  _auto_search_status_confirm=False,is_auto_search_running=lambda:frame[0]=="map",is_in_auto_search_menu=lambda:False,_handle_auto_search_menu_missing=lambda:False,handle_exp_info=statistics)
 ns={"logger":Mock(),"CampaignEnd":RuntimeError}
 exec(compile(ast.fix_missing_locations(ast.Module(body=[method],type_ignores=[])),"<native auto-search status>","exec"),ns)
 if mode=="error":
  with pytest.raises(SemanticGateClosed):ns[method.name](h)
  assert port.call_count==1
 else:
  ns[method.name](h)
  assert actions==(["close","statistics"] if mode=="defeat" else [])
