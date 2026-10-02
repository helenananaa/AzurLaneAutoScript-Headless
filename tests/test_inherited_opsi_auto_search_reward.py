import json
from pathlib import Path
from types import SimpleNamespace
import pytest
from alas_headless import AlasSemanticAdapter, SemanticGateClosed
from tests.semantic_support.adapter_fixtures import NamedButton
from tests.semantic_support.observer_fixtures import (
    FakeBackend, make_button, make_text, make_image, make_ui, make_oracle,
    make_snapshot, make_buttons,
)

ROOT='OverlayCamera/Overlay/UIMain/WorldAutoFightRewardUI(Clone)'
EXIT=ROOT+'/Window/Fixed/ButtonExit'
TARGET='os/auto-search/reward/close'
def setup():
    bounds={'left':580.,'top':580.,'right':700.,'bottom':640.}
    exit=make_button('ButtonExit',EXIT,640,640,bounds,raycast_top=None)
    backend=FakeBackend([exit,make_button('back_button',
        'LevelCamera/Canvas/LevelOrigin/top/adapt/top_stage/back_button')])
    graphic=make_image(EXIT,'btn_big_grey',dict(bounds))
    graphic['raycast_target']=True
    backend.ui=make_ui([make_text('离开',EXIT+'/pic'),
        make_text('TOTAL REWARDS',ROOT+'/Window/Fixed/top/bg/obtain/title/title_en')],images=[graphic])
    oracle=make_oracle(backend)
    return backend,oracle

@pytest.mark.parametrize('name',['OS_CHECK','RESEARCH_CHECK','TACTICAL_CHECK',
    'WITHDRAW','CAMPAIGN_WITHDRAW_CONFIRM','GET_ITEMS_1','MONTHLY_PASS_NOTICE',
    'AUTO_SEARCH_OS_MAP_OPTION_OFF','AUTO_SEARCH_OS_MAP_OPTION_OFF_DISABLED','AUTO_SEARCH_OS_MAP_OPTION_ON'])
def test_inherited_foreground_reward_hides_underlay_probes(name):
    backend,oracle=setup()
    adapter=AlasSemanticAdapter(oracle,package_gate=lambda:None)
    assert adapter.appear(NamedButton(name)) is False
    assert adapter.appear(NamedButton('AUTO_SEARCH_REWARD')) is True
    assert backend.taps==[]


def test_foreground_reward_blocks_underlay_input_targets():
    backend,oracle=setup()
    assert any(rule.blocker_id=='operation-siren-auto-reward' for rule in
               oracle._blocking_rules(oracle.read_state(),'os/page/back'))
    with pytest.raises(SemanticGateClosed): oracle.click('os/page/back')
    assert backend.taps==[]

def test_original_reward_alias_closes_once_and_requires_newer_root_absence():
    backend,oracle=setup()
    def closed():
        backend.snapshot=make_snapshot(generation=11)
        backend.buttons=make_buttons([],generation=11)
        backend.ui=make_ui([],generation=11)
    backend.on_tap=closed
    adapter=AlasSemanticAdapter(oracle,package_gate=lambda:None)
    adapter._fresh_input_oracle=lambda:oracle
    receipt=adapter.click(NamedButton('AUTO_SEARCH_REWARD'))
    assert receipt.semantic_id==TARGET
    assert backend.taps==[(640,640)]

@pytest.mark.parametrize('failure',['duplicate','title','leave','sprite','graphic-bounds',
    'button-raycast','graphic-raycast','loading','foreign','stale','foreground','incoherent'])
def test_reward_delegate_cannot_bypass_identity_or_input_guards(failure):
    backend,oracle=setup()
    if failure=='duplicate':
        backend.buttons['buttons'].append(dict(backend.buttons['buttons'][0]))
        backend.buttons['button_count']+=1
    elif failure=='title': backend.ui['texts'][1]['text']='OTHER REWARDS'
    elif failure=='leave': backend.ui['texts'][0]['text']='购买'
    elif failure=='sprite': backend.ui['images'][0]['sprite']='other'
    elif failure=='graphic-bounds': backend.ui['images'][0]['adb_bounds']['left']+=1
    elif failure=='button-raycast': backend.buttons['buttons'][0]['raycast_top']=False
    elif failure=='graphic-raycast': backend.ui['images'][0]['raycast_top']=False
    elif failure in ('loading','foreign'):
        path='OverlayCamera/Overlay/UIOverlay/Loading(Clone)' if failure=='loading' else 'OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/button_container/cancel_button'
        backend.buttons['buttons'].append(make_button(path.rsplit('/',1)[-1],path))
        backend.buttons['button_count']+=1
    elif failure=='stale': backend.snapshot['age_ms']=backend.buttons['age_ms']=99999
    elif failure=='foreground': backend.foreground='com.android.settings/.Settings'
    elif failure=='incoherent': backend.ui['generation']=15
    with pytest.raises(SemanticGateClosed): oracle.click(TARGET)
    assert backend.taps==[]

def test_close_without_advance_does_not_submit_a_second_input(monkeypatch):
    import alas_headless.adapter.semantic.dispatch_actions as actions
    ticks=iter((0,1,10))
    monkeypatch.setattr(actions.time,'monotonic',lambda:next(ticks))
    monkeypatch.setattr(actions.time,'sleep',lambda _:None)
    backend,oracle=setup()
    adapter=AlasSemanticAdapter(oracle,package_gate=lambda:None)
    adapter._fresh_input_oracle=lambda:oracle
    with pytest.raises(SemanticGateClosed,match='postcondition'):
        adapter.click(NamedButton('AUTO_SEARCH_REWARD'))
    assert backend.taps==[(640,640)]


def test_changed_foreground_after_close_is_not_a_success(monkeypatch):
    import alas_headless.adapter.semantic.dispatch_actions as actions
    ticks=iter((0,1,10))
    monkeypatch.setattr(actions.time,'monotonic',lambda:next(ticks))
    monkeypatch.setattr(actions.time,'sleep',lambda _:None)
    backend,oracle=setup()
    def closed_in_wrong_foreground():
        backend.snapshot=make_snapshot(generation=11)
        backend.buttons=make_buttons([],generation=11)
        backend.foreground='com.android.settings/.Settings'
    backend.on_tap=closed_in_wrong_foreground
    adapter=AlasSemanticAdapter(oracle,package_gate=lambda:None)
    adapter._fresh_input_oracle=lambda:oracle
    with pytest.raises(SemanticGateClosed,match='game activity is not top-resumed'):
        adapter.click(NamedButton('AUTO_SEARCH_REWARD'))
    assert backend.taps==[(640,640)]

def test_retained_r194_reward_is_a_valid_native_delegate_replay():
    source=Path(__file__).resolve().parents[1]/'artifacts/semantic-cn-original-scheduler-r194-20261002.json'
    if not source.exists():pytest.skip('retained inherited reward unavailable')
    task=json.loads(source.read_text(encoding='utf-8'))['tasks'][0]
    backend=FakeBackend(task['failure_leased_frame']['buttons_snapshot']['buttons'])
    ui=task['failure_observation']['ui']['snapshot']
    backend.ui=make_ui(ui['texts'],images=ui['images'],toggles=ui['toggles'])
    oracle=make_oracle(backend)
    assert oracle.enabled(TARGET)
    assert backend.taps==[]
