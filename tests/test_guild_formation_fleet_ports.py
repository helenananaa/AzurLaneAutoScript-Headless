"""Reviewed footer observations and input for ALAS' native fleet switch loop."""
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from alas_headless import AlasSemanticAdapter, AlasSemanticSession
from contextlib import nullcontext
from alas_headless.adapter.semantic.contracts import AlasSemanticUnmapped
from alas_headless.adapter.task_lifecycle import semantic_task_scope, TaskCapabilityUnavailable
from alas_headless.oracle.errors import SemanticGateClosed, SemanticGuildFormationUnavailable
from tests.semantic_support.observer_fixtures import (
    FakeBackend, make_button, make_toggle, make_image, make_text, make_ui, make_oracle,
)

ROOT='OverlayCamera/Overlay/UIMain/GuildMissionFormationPage(Clone)'


def footer_backend(names=('1','add'), selected='1'):
    buttons=[make_button('GuildMissionFormationPage(Clone)',ROOT,raycast_top=None)]
    toggles=[]; images=[]
    for i,name in enumerate(names):
        path=ROOT+'/frame/single/dot/'+name
        bounds={'left':500+i*40,'top':379,'right':528+i*40,'bottom':407}
        toggles.append(make_toggle(path,checked=name==selected,raycast_top=None,
            x=514+i*40,y=393,bounds=bounds))
        images.append(make_image(path,'dot5' if name=='add' else 'dot1',bounds))
    texts=[make_text(value,ROOT+'/frame/bottom/'+suffix+'/Text') for suffix,value in
        (('effect','158'),('score_addition','4'),('effect_addition','174'))]
    backend=FakeBackend(buttons)
    backend.ui=make_ui(texts,toggles=toggles,images=images)
    return backend


def advance(backend, selected):
    for toggle in backend.ui['toggles']:
        toggle['checked']=toggle['name']==selected
    for packet in (backend.snapshot,backend.buttons,backend.ui):
        packet['generation']+=1


def session(adapter):
    return SimpleNamespace(discard_task_state=adapter.reset_task_state,trace=None)


@pytest.mark.parametrize('names', [('1','add'), ('1','2','3','4','5','add')])
def test_observed_rightmost_toggle_and_additive_fleets_remain_usable(names):
    backend=footer_backend(names)
    backend.ui['toggles'].reverse()
    backend.ui['images'].reverse()
    backend.ui['harmless_metadata']='upstream-addition'
    oracle=make_oracle(backend)
    adapter=AlasSemanticAdapter(oracle,lambda:None)
    button=adapter.guild_formation_switch_button()
    assert button.name=='GUILD_FORMATION_FLEET_add'
    assert str(button)==button.name
    assert button.area==(500+(len(names)-1)*40,379,528+(len(names)-1)*40,407)
    backend.on_tap=lambda:advance(backend,'add')
    receipt=adapter.click(button)
    assert receipt.path==ROOT+'/frame/single/dot/add'
    assert backend.taps==[(514+(len(names)-1)*40,393)]
    assert adapter.guild_formation_switch_button() is None
    assert adapter._action_ledger.remaining('guild.dispatch')==0


def test_already_rightmost_observation_needs_no_navigation_or_dispatch_grant():
    backend=footer_backend(selected='add')
    adapter=AlasSemanticAdapter(make_oracle(backend),lambda:None)
    assert adapter.guild_formation_switch_button() is None
    assert backend.taps==[]


def test_cosmetic_sprite_drift_on_another_fleet_does_not_deny_native_choice():
    backend=footer_backend()
    backend.ui['images'][0]['sprite']='new-fleet-decoration'
    adapter=AlasSemanticAdapter(make_oracle(backend),lambda:None)
    backend.on_tap=lambda:advance(backend,'add')
    button=adapter.guild_formation_switch_button()
    assert adapter.click(button).path==ROOT+'/frame/single/dot/add'
    assert backend.taps==[(554,393)]


@pytest.mark.parametrize('kind', ['duplicate','multiple_selected','bad_geometry','overlap','blocked'])
def test_unsafe_footer_input_stays_closed(kind):
    backend=footer_backend()
    target=backend.ui['toggles'][-1]
    if kind=='duplicate': backend.ui['toggles'].append(deepcopy(target))
    elif kind=='multiple_selected': target['checked']=True
    elif kind=='bad_geometry': target['adb_point']['x']=100
    elif kind=='overlap':
        target['adb_bounds']=deepcopy(backend.ui['toggles'][0]['adb_bounds'])
        target['adb_point']=deepcopy(backend.ui['toggles'][0]['adb_point'])
    else: target['raycast_top']=False
    backend.ui['toggle_count']=len(backend.ui['toggles'])
    oracle=make_oracle(backend)
    with pytest.raises(SemanticGateClosed): oracle.click_toggle('guild/formation/fleet/add')
    assert backend.taps==[]


def test_unknown_footer_sprite_is_local_only_before_input_and_research_keeps_reading():
    backend=footer_backend()
    backend.ui['images'][-1]['sprite']='unreviewed'
    oracle=make_oracle(backend)
    adapter=AlasSemanticAdapter(oracle,lambda:None)
    task=session(adapter)
    with pytest.raises(TaskCapabilityUnavailable):
        with semantic_task_scope(task,'guild'): adapter.guild_formation_switch_button()
    with semantic_task_scope(task,'research'): assert oracle.read_state().generation>0
    assert backend.taps==[]


def test_changed_native_choice_defers_before_input():
    backend=footer_backend()
    adapter=AlasSemanticAdapter(make_oracle(backend),lambda:None)
    with pytest.raises(AlasSemanticUnmapped): adapter.click_guild_formation_fleet('1')
    assert backend.taps==[]


def test_missing_footer_after_accepted_input_is_fatal_not_local_compatibility():
    backend=footer_backend()
    oracle=make_oracle(backend)
    adapter=AlasSemanticAdapter(oracle,lambda:None)
    def disappear():
        advance(backend,'add')
        backend.ui['images']=[]
        backend.ui['image_count']=0
    backend.on_tap=disappear
    with pytest.raises(SemanticGateClosed) as caught:
        with semantic_task_scope(session(adapter),'guild'): adapter.click_guild_formation_fleet('add')
    assert not isinstance(caught.value,SemanticGuildFormationUnavailable)
    assert len(backend.taps)==1


def test_no_progress_stops_after_one_navigation_input(monkeypatch):
    backend=footer_backend()
    adapter=AlasSemanticAdapter(make_oracle(backend),lambda:None)
    clock=iter((0,0,6))
    monkeypatch.setattr('alas_headless.adapter.semantic.guild.time.monotonic',lambda:next(clock))
    monkeypatch.setattr('alas_headless.adapter.semantic.guild.time.sleep',lambda _:None)
    with pytest.raises(SemanticGateClosed,match='did not advance'):
        adapter.click_guild_formation_fleet('add')
    assert len(backend.taps)==1


def test_in_progress_comes_from_typed_doing_image_not_missing_go():
    backend=footer_backend()
    oracle=make_oracle(backend)
    assert not oracle.guild_formation_state().in_progress
    assert oracle.guild_dispatch_in_progress_generation() is None
    backend.ui['images'].append(make_image(ROOT+'/frame/bottom/doingBtn','doing',
        {'left':910,'top':624,'right':1280,'bottom':712}))
    backend.ui['image_count']=len(backend.ui['images'])
    assert oracle.guild_formation_state().in_progress
    assert oracle.guild_dispatch_in_progress_generation() == backend.ui['generation']
    backend.buttons['buttons'].append(make_button('go',ROOT+'/frame/bottom/go'))
    backend.buttons['button_count']=len(backend.buttons['buttons'])
    with pytest.raises(SemanticGateClosed,match='conflict'): oracle.guild_formation_state()
    with pytest.raises(SemanticGateClosed,match='conflict'):
        oracle.guild_dispatch_in_progress_generation()


def fleet_session(adapter, oracle):
    native = AlasSemanticSession.__new__(AlasSemanticSession)
    native.adapter = adapter
    native.open = lambda: adapter
    native._frame_clock = Mock()
    native.refresh_frame = Mock(return_value=SimpleNamespace(frame_id=1))
    adapter._require_frame_observation_oracle = lambda: oracle
    adapter.prepared_input_frame = lambda provider: nullcontext()
    return native


@pytest.mark.parametrize('names', [('1', 'add'), ('1', '2', '3', '4', '5', 'add')])
def test_original_session_can_dispatch_the_reviewed_native_fleet_selection(names):
    backend = footer_backend(names)
    oracle = make_oracle(backend)
    adapter = AlasSemanticAdapter(oracle, lambda: None)
    native = fleet_session(adapter, oracle)
    button = adapter.guild_formation_switch_button()
    backend.on_tap = lambda: advance(backend, 'add')
    receipt = native.click(button)
    assert receipt.semantic_id == 'guild/formation/fleet/add'
    assert len(backend.taps) == 1
    assert adapter.guild_formation_switch_button() is None
    assert adapter._action_ledger.remaining('guild.dispatch') == 0
    native.refresh_frame.assert_called_once()


def test_original_session_fleet_selection_still_rejects_changed_rightmost_identity():
    backend = footer_backend()
    oracle = make_oracle(backend)
    adapter = AlasSemanticAdapter(oracle, lambda: None)
    native = fleet_session(adapter, oracle)
    button = adapter.guild_formation_switch_button()
    # The observed button is stale after the native footer loses its add tab.
    backend.ui['toggles'] = [t for t in backend.ui['toggles'] if t['name'] != 'add']
    backend.ui['toggle_count'] = len(backend.ui['toggles'])
    with pytest.raises(SemanticGateClosed):
        native.click(button)
    assert not backend.taps
