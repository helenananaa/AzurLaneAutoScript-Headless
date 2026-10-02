import json,re
from pathlib import Path
import pytest
from alas_headless.semantic_oracle import SemanticGateClosed
from alas_headless import AlasSemanticAdapter
from tests.semantic_support.observer_fixtures import FakeBackend,make_ui,make_oracle

def retained():
    root=Path(__file__).resolve().parents[1]
    p=root/'artifacts/semantic-cn-original-scheduler-r37-20260930.json'
    if not p.exists():pytest.skip('native ghost map unavailable')
    r=json.loads(p.read_text(encoding='utf8'))['tasks'][-1]['failure_observation']
    b=FakeBackend(r['state']['buttons_snapshot']['buttons']);u=r['ui']['snapshot']
    b.ui=make_ui(u['texts'],images=u['images'],toggles=u['toggles'])
    source=(root/'artifacts/campaign-preparation/upstream/campaign/event_20260908_cn/d3.py').read_text(encoding='utf8')
    data=re.search(r'MAP.map_data = """(.*?)"""',source,re.S).group(1).strip()
    land=tuple((y,x) for y,line in enumerate(data.splitlines(),1)
               for x,tile in enumerate(line.split(),1) if tile=='++')
    return b,dict(stage_code='d3',columns=9,rows=9,land=land,expected_fleet_count=2)

def test_ghost_art_retains_exact_genre_size_and_cleared_identity():
    b,args=retained();s=make_oracle(b)._campaign_map_state_once(**args)
    assert len(s.enemies)==7
    assert {e.sprite for e in s.enemies}=={'ghostqz','ghosthm','ghostzl'}
    assert {e.genre for e in s.enemies}=={'Light','Carrier','Main'}
    assert {e.scale for e in s.enemies}=={1,2,3}
    assert all(not e.sprite.endswith('_d_blue') for e in s.enemies)
    assert b.taps==[]

@pytest.mark.parametrize('name',['GOTO_MAIN','GOTO_MAIN_WHITE','RPG_HOME'])
def test_retained_native_map_yields_to_original_withdrawal(name):
    b,_=retained();a=AlasSemanticAdapter(make_oracle(b),package_gate=lambda:None)
    assert a._appear_priority(name) is False
    assert b.taps==[]

def test_retained_map_notice_and_dock_probes_are_read_only():
    b,_=retained();a=AlasSemanticAdapter(make_oracle(b),package_gate=lambda:None)
    assert a._campaign_notice_navigation_surface() is True
    a._campaign_context=object()
    assert a._appear_priority('DOCK_CHECK') is False
    assert b.taps==[]

@pytest.mark.parametrize('name',['EVENT_CHECK','CAMPAIGN_CHECK','GOTO_MAIN_WHITE','DOCK_CHECK'])
def test_native_returned_map_covers_retained_selector(name):
    root=Path(__file__).resolve().parents[1]
    p=root/'artifacts/semantic-cn-original-scheduler-r39-20260930.json'
    if not p.exists():pytest.skip('native returned map unavailable')
    r=json.loads(p.read_text(encoding='utf8'))['tasks'][0]
    b=FakeBackend(r['failure_leased_frame']['buttons_snapshot']['buttons'])
    u=r['failure_observation']['ui']['snapshot']
    b.ui=make_ui(u['texts'],images=u['images'],toggles=u['toggles'])
    a=AlasSemanticAdapter(make_oracle(b),package_gate=lambda:None)
    if name=='DOCK_CHECK':a._campaign_context=object()
    assert a._appear_priority(name) is False
    assert a._campaign_notice_navigation_surface() is True
    assert b.taps==[]

@pytest.mark.parametrize('mutation',[None,'unknown-label','unknown-percent','duplicate-label'])
def test_native_combat_loading_dock_absence_requires_exact_labels(mutation):
    root=Path(__file__).resolve().parents[1]
    p=root/'artifacts/semantic-cn-original-scheduler-r38-20260930.json'
    if not p.exists():pytest.skip('native loading frame unavailable')
    r=json.loads(p.read_text(encoding='utf8'))['tasks'][1]['failure_observation']
    b=FakeBackend(r['state']['buttons_snapshot']['buttons']);u=r['ui']['snapshot']
    b.ui=make_ui(u['texts'],images=u['images'],toggles=u['toggles'])
    path='UICamera/Canvas/UIMain/CombatLoadUI(Clone)/loading/loading_label'
    label=next(t for t in b.ui['texts'] if t['path']==path)
    if mutation=='unknown-label':label['text']='unknown'
    if mutation=='unknown-percent':next(t for t in b.ui['texts'] if t['path']==path+'/percent')['text']='unknown'
    if mutation=='duplicate-label':
        b.ui['texts'].append(dict(label));b.ui['text_count']=len(b.ui['texts'])
    a=AlasSemanticAdapter(make_oracle(b),package_gate=lambda:None);a._campaign_context=object()
    from alas_headless.adapter.semantic.dispatch_result import UNHANDLED
    assert a._appear_priority('DOCK_CHECK') is (False if mutation is None else UNHANDLED)
    assert b.taps==[]

@pytest.mark.parametrize('mutation',['unknown-genre','missing-size','unknown-size'])
def test_ghost_enemies_still_require_typed_genre_and_size(mutation):
    b,args=retained();icon=next(i for i in b.ui['images'] if i['sprite']=='ghostqz')
    sizepath=icon['path'].removesuffix('/icon')+'/random_buff_container/1'
    if mutation=='unknown-genre':icon['sprite']='ghost_unknown'
    elif mutation=='missing-size':b.ui['images']=[i for i in b.ui['images'] if i['path']!=sizepath]
    else:next(i for i in b.ui['images'] if i['path']==sizepath)['sprite']='unknown'
    with pytest.raises(SemanticGateClosed):make_oracle(b)._campaign_map_state_once(**args)
    assert b.taps==[]
