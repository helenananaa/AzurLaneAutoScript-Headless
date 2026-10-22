import pytest
from alas_headless import SemanticGateClosed
from tests.semantic_support.observer_fixtures import FakeBackend,make_button,make_buttons,make_oracle

ROOT='UICamera/Canvas/UIMain/NewNavalTacticsUI(Clone)/adpter/NewNavalTacticsStudentsPage(Clone)/'


def slots(count=3):
    backend=FakeBackend([make_button('add',ROOT+'add',x=300+200*i,y=393) for i in range(count)])
    oracle=make_oracle(backend)
    def publish_dock(_):
        if oracle.input_dispatch_count:
            generation=backend.snapshot['generation']+1
            backend.snapshot['generation']=backend.ui['generation']=generation
            backend.buttons=make_buttons([make_button('back',
                'OverlayCamera/Overlay/UIMain/blur_panel/adapt/top/back')],generation=generation)
    oracle._sleep=publish_dock
    return backend,oracle


def test_first_empty_is_a_positive_control_not_a_guessed_numbered_slot():
    backend,oracle=slots()
    assert oracle.tactical_empty_slots_ready()
    with pytest.raises(SemanticGateClosed):oracle.click_tactical_empty_slot(2)
    backend.buttons['buttons'].reverse()
    receipt=oracle.click_tactical_first_empty_slot()
    assert receipt.semantic_id=='tactical/slot/first-empty'
    assert receipt.path==ROOT+'add'
    assert backend.taps==[(300,393)] and oracle.input_dispatch_count==1


def test_unrelated_occupied_card_metadata_does_not_deny_known_empty_control():
    backend,oracle=slots(1)
    backend.buttons['buttons'].append(make_button('new-card-layout',ROOT+'info/new-card-layout',x=100,y=400))
    backend.buttons['button_count']+=1
    backend.snapshot['additive_metadata']='new game update'
    assert oracle.tactical_empty_slots_ready()
    assert oracle.click_tactical_first_empty_slot().semantic_id=='tactical/slot/first-empty'
    assert backend.taps==[(300,393)]


def test_mounting_positive_control_waits_for_fresh_actionability_before_one_tap():
    backend,oracle=slots(1)
    backend.buttons['buttons'][0]['raycast_top']=False
    assert oracle.tactical_empty_slots_ready()
    sleeps=[]
    def publish(_):
        sleeps.append(True)
        if not oracle.input_dispatch_count:
            assert backend.taps==[]
            backend.snapshot['generation']=11
            backend.buttons=make_buttons([make_button('add',ROOT+'add',x=400,y=393)],generation=11)
        else:
            assert backend.taps==[(400,393)]
            backend.snapshot['generation']=12
            backend.buttons=make_buttons([make_button('back',
                'OverlayCamera/Overlay/UIMain/blur_panel/adapt/top/back')],generation=12)
    oracle._sleep=publish
    receipt=oracle.click_tactical_first_empty_slot()
    assert receipt.generation==11 and receipt.point.x==400
    assert len(sleeps)==1 and backend.taps==[(400,393)]


@pytest.mark.parametrize('case',['foreign','stale','covered','ambiguous','foreign-popup','offscreen','foreground'])
def test_first_empty_keeps_unique_fresh_actionable_unobscured_input(case):
    backend,oracle=slots(1)
    if case=='foreign':backend.snapshot['package']='unrelated.package'
    elif case=='stale':backend.snapshot['age_ms']=100000
    elif case=='covered':backend.buttons['buttons'][0]['raycast_top']=False
    elif case=='ambiguous':
        backend.buttons['buttons'].append(dict(backend.buttons['buttons'][0]))
        backend.buttons['button_count']+=1
    elif case=='foreign-popup':
        backend.buttons['buttons'].append(make_button('custom_button_1(Clone)',
            'OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/button_container/custom_button_1(Clone)'))
        backend.buttons['button_count']+=1
    elif case=='offscreen':backend.buttons=make_buttons([make_button('add',ROOT+'add',x=300,y=800)])
    else:backend.foreground='unrelated.package/.Activity'
    with pytest.raises(SemanticGateClosed):oracle.click_tactical_first_empty_slot()
    assert backend.taps==[] and oracle.input_dispatch_count==0


def test_uncertain_dispatched_tap_is_never_retried():
    backend,oracle=slots(1)
    original=oracle._tap
    def uncertain(*args):
        original(*args)
        raise SemanticGateClosed('input result uncertain')
    oracle._tap=uncertain
    with pytest.raises(SemanticGateClosed,match='uncertain'):oracle.click_tactical_first_empty_slot()
    assert backend.taps==[(300,393)] and oracle.input_dispatch_count==1


def test_accepted_input_returns_before_dock_mounts():
    backend,oracle=slots(1)
    clock=[0.0]
    oracle._monotonic=lambda:clock[0]
    oracle._sleep=lambda _:clock.__setitem__(0,clock[0]+6)
    receipt=oracle.click_tactical_first_empty_slot()
    assert receipt.semantic_id=='tactical/slot/first-empty'
    assert backend.taps==[(300,393)] and oracle.input_dispatch_count==1


@pytest.mark.parametrize('layer',['dock','book','foreign-popup'])
def test_mounted_top_layer_hides_positive_underlay_empty_probe(layer):
    backend,oracle=slots(1)
    if layer=='dock':
        overlay=make_button('9707054','OverlayCamera/Overlay/UIMain/DockyardUI(Clone)/main/ship_container/ships/9707054')
    elif layer=='book':
        overlay=make_button('cancel_btn','OverlayCamera/Overlay/UIMain/NewNavalTacticsLessonPage(Clone)/cancel_btn')
    else:
        overlay=make_button('custom_button_1(Clone)',
            'OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/button_container/custom_button_1(Clone)')
    backend.buttons['buttons'].append(overlay)
    backend.buttons['button_count']+=1
    assert not oracle.tactical_empty_slots_ready()
    with pytest.raises(SemanticGateClosed):oracle.click_tactical_first_empty_slot()
    assert backend.taps==[] and oracle.input_dispatch_count==0
