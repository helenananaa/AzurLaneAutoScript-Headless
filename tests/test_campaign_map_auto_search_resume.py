from tests.alas_test_source import patched_alas_root
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from alas_headless import AlasSemanticAdapter
from alas_headless.semantic_oracle import SemanticGateClosed
from tests.semantic_support.observer_fixtures import FakeBackend,make_ui,make_oracle
from tests.semantic_support.adapter_fixtures import FakeOracle

def retained():
    p=Path(__file__).resolve().parents[1]/'artifacts/semantic-cn-r36-after-enhancement-readonly-20260930.json'
    if not p.exists():pytest.skip('native map OFF switch unavailable')
    r=json.loads(p.read_text(encoding='utf8'));b=FakeBackend(r['state']['buttons_snapshot']['buttons'])
    u=r['ui']['snapshot'];b.ui=make_ui(u['texts'],images=u['images'],toggles=u['toggles'])
    return b

def test_native_off_switch_has_complete_reviewed_layers():
    b=retained();s=make_oracle(b).campaign_map_auto_search_state()
    assert s is not None and s[2] is False
    assert s[3].sprite=='auto_fight_off'
    assert b.taps==[]

def test_public_adapter_dispatch_reaches_native_off_port():
    b=retained();o=make_oracle(b);a=AlasSemanticAdapter(o,package_gate=lambda:None)
    a.begin_campaign_pre_sortie('D3',mode='hard')
    assert a.appear('AUTO_SEARCH_MAP_OPTION_OFF') is True
    assert a.appear('AUTO_SEARCH_MAP_OPTION_ON') is False
    assert b.taps==[]

@pytest.mark.parametrize('mutation',['duplicate','missing-icon','covered','unknown-sprite'])
def test_partial_or_covered_switch_rejects_before_input(mutation):
    b=retained();control=next(x for x in b.buttons['buttons'] if x['name']=='Off')
    if mutation=='duplicate':b.buttons['buttons'].append(dict(control))
    elif mutation=='covered':control['raycast_top']=False
    elif mutation=='missing-icon':b.ui['images']=[x for x in b.ui['images'] if x['path']!=control['path']+'/Icon']
    else:next(x for x in b.ui['images'] if x['path']==control['path'])['sprite']='unknown'
    with pytest.raises(SemanticGateClosed):make_oracle(b).click_campaign_map_auto_search_on()
    assert b.taps==[]

def test_absent_switch_does_not_parse_foreign_ui():
    o=make_oracle(FakeBackend([]));o.read_ui_state=Mock(side_effect=AssertionError('foreign UI'))
    assert o.campaign_map_auto_search_state() is None
    o.read_ui_state.assert_not_called()

def test_original_resources_observe_off_and_submit_once_to_on_postcondition():
    o=FakeOracle();s=SimpleNamespace(generation=11);receipt=SimpleNamespace(generation=10)
    o._foreground_component=Mock(return_value='exact/game')
    o.campaign_map_auto_search_state=Mock(return_value=(s,None,False,None))
    a=AlasSemanticAdapter(o,package_gate=lambda:None);a.begin_campaign_pre_sortie('D3',mode='hard')
    assert a._appear_campaign('AUTO_SEARCH_MAP_OPTION_OFF') is True
    assert a._appear_campaign('AUTO_SEARCH_MAP_OPTION_ON') is False
    o.click_campaign_map_auto_search_on=Mock(return_value=receipt)
    o.campaign_map_auto_search_state=Mock(return_value=(s,None,True,None))
    a._fresh_input_oracle=lambda:o
    assert a._click_campaign_strategy('AUTO_SEARCH_MAP_OPTION_OFF') is receipt
    o.click_campaign_map_auto_search_on.assert_called_once_with(post_input_foreground=o._foreground_component)

def test_original_recovery_refreshes_before_map_identity_and_resumes_paused_map():
    import ast
    source=patched_alas_root() / 'module/campaign/campaign_base.py'
    if not source.exists():pytest.skip('patched original ALAS tree unavailable')
    tree=ast.parse(source.read_text(encoding='utf8'))
    method=next(x for c in tree.body if isinstance(c,ast.ClassDef) and c.name=='CampaignBase'
                for x in c.body if isinstance(x,ast.FunctionDef) and x.name=='_semantic_campaign_retirement_recovery')
    env={};exec(compile(ast.Module(body=[method],type_ignores=[]),str(source),'exec'),env)
    calls=[];fresh={'value':False}
    def screenshot():fresh['value']=True;calls.append('screenshot')
    def retire():fresh['value']=False;calls.append('retire');return False
    def in_map():assert fresh['value'];calls.append('map');return True
    h=SimpleNamespace(device=SimpleNamespace(screenshot=screenshot),handle_retirement=retire,
                      is_in_map=in_map,handle_auto_search_map_option=lambda:calls.append('resume') or True)
    assert env['_semantic_campaign_retirement_recovery'](h) is True
    assert calls==['screenshot','retire','screenshot','map','resume']

def test_waiting_paused_map_calls_original_recovery_handler(monkeypatch):
    import itertools
    from alas_headless.adapter.semantic import campaign
    clock=itertools.count(0,10);monkeypatch.setattr(campaign.time,'monotonic',lambda:next(clock))
    o=FakeOracle();o.campaign_map_auto_search_state=lambda:(None,None,False,None)
    o.campaign_dock_full_visible=lambda *_:False;o.retirement_selection_visible=lambda:False
    o.enhancement_dock_visible=lambda:False
    a=AlasSemanticAdapter(o,package_gate=lambda:None);a.begin_campaign_pre_sortie('D3',mode='hard')
    a._campaign_context.sortie_proof=SimpleNamespace(map_generation=1)
    a._campaign_context.auto_search_role_state=SimpleNamespace()
    class OriginalRecovered(Exception):pass
    handler=Mock(side_effect=OriginalRecovered)
    with pytest.raises(OriginalRecovered):a.wait_campaign_auto_search_completion('d3',recovery_handler=handler)
    handler.assert_called_once_with();assert o.click_calls==[]

@pytest.mark.parametrize('post_matches',[True,False])
def test_post_input_foreground_uses_live_check_and_never_reuses_lease(post_matches):
    b=retained();o=make_oracle(b)
    component=o.fingerprint.component
    def leased_foreground():
        if b.taps:raise AssertionError('invalidated input frame')
        return component
    o._foreground_component=leased_foreground
    def live_post():
        assert len(b.taps)==1
        return component if post_matches else 'other/package'
    if post_matches:
        r=o.click_campaign_map_auto_search_on(post_input_foreground=live_post)
        assert r.semantic_id=='campaign/map/auto-search/on'
    else:
        with pytest.raises(SemanticGateClosed,match='game activity changed after'):
            o.click_campaign_map_auto_search_on(post_input_foreground=live_post)
    assert len(b.taps)==1

def test_dock_full_modal_hides_retained_map_switch():
    p=Path(__file__).resolve().parents[1]/'artifacts/semantic-cn-r36-after-resume-readonly-20260930.json'
    if not p.exists():pytest.skip('native full-dock modal unavailable')
    r=json.loads(p.read_text(encoding='utf8'));b=FakeBackend(r['state']['buttons_snapshot']['buttons'])
    u=r['ui']['snapshot'];b.ui=make_ui(u['texts'],images=u['images'],toggles=u['toggles'])
    assert make_oracle(b).campaign_map_auto_search_state() is None
    assert b.taps==[]

def test_new_dock_full_after_resume_returns_to_original_recovery():
    o=FakeOracle();o._foreground_component=Mock(return_value='exact/game')
    receipt=SimpleNamespace(generation=10)
    o.click_campaign_map_auto_search_on=Mock(return_value=receipt)
    o.read_state=Mock(return_value=SimpleNamespace(generation=11))
    o.campaign_dock_full_visible=Mock(return_value=True)
    o.campaign_map_auto_search_state=Mock(side_effect=AssertionError('covered map'))
    a=AlasSemanticAdapter(o,package_gate=lambda:None);a.begin_campaign_pre_sortie('D3',mode='hard')
    a._fresh_input_oracle=lambda:o
    assert a._click_campaign_strategy('AUTO_SEARCH_MAP_OPTION_OFF') is receipt
    o.campaign_dock_full_visible.assert_called_once_with('d3')
    o.click_campaign_map_auto_search_on.assert_called_once()

def test_retirement_dock_is_not_parsed_as_enhancement_dock():
    p=Path(__file__).resolve().parents[1]/'artifacts/semantic-cn-r36-original-dock-and-map-recovery-r3-20260930.json'
    if not p.exists():pytest.skip('native retirement selection unavailable')
    r=json.loads(p.read_text(encoding='utf8'));b=FakeBackend(r['after']['buttons_snapshot']['buttons'])
    u=r['ui_after']['snapshot'];b.ui=make_ui(u['texts'],images=u['images'],toggles=u['toggles'])
    o=make_oracle(b);o.enhancement_dock_visible=Mock(side_effect=AssertionError('foreign Dock parser'))
    assert o.retirement_selection_visible() is True
    assert o.campaign_is_in_map() is False
    o.enhancement_dock_visible.assert_not_called()
