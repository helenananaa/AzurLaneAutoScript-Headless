import json
from pathlib import Path
from types import SimpleNamespace
import pytest
from alas_headless import AlasSemanticAdapter, AlasSemanticUnmapped, SemanticGateClosed
from tests.semantic_support.observer_fixtures import FakeBackend, make_button, make_oracle, make_ui

ROOT='UICamera/Canvas/UIMain/CourtYardUI(Clone)/main/'
def backend():
    return FakeBackend([
        make_button('return',ROOT+'topPanel/btns/topleft/return'),
        make_button('decorate_btn',ROOT+'bottomPanel/bottomright/decorate_btn')])

def test_retained_dorm_proves_notice_absence_without_task_context():
    b=backend(); a=AlasSemanticAdapter(make_oracle(b),lambda:None)
    assert a._dorm_context is None
    assert a.appear(SimpleNamespace(name='GET_MISSION')) is False
    assert not b.taps

@pytest.mark.parametrize('change',['unknown','duplicate','loading','foreign','stale','foreground','disabled'])
def test_unproven_dorm_does_not_suppress_notice(change):
    b=backend()
    if change=='unknown': b.buttons['buttons'][0]['path']='UnknownUI/back'
    if change=='duplicate': b.buttons['buttons'].append(dict(b.buttons['buttons'][0]));b.buttons['button_count']+=1
    if change in ('loading','foreign'):
        path=('OverlayCamera/Overlay/UIOverlay/Loading(Clone)/block' if change=='loading'
              else 'OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/button_container/custom_button_1(Clone)')
        b.buttons['buttons'].append(make_button('block',path));b.buttons['button_count']+=1
    if change=='stale':b.snapshot['age_ms']=b.buttons['age_ms']=99999
    if change=='foreground': b.foreground='com.android.settings/.Settings'
    if change=='disabled': b.buttons['buttons'][0]['interactable']=False
    oracle=make_oracle(b)
    a=AlasSemanticAdapter(oracle,lambda:None)
    if change=='loading':
        # Native ALAS waits for its next frame; a covered passive probe is
        # false while the same loading layer still refuses return input.
        assert a._appear_once(SimpleNamespace(name='GET_MISSION')) is False
        with pytest.raises(SemanticGateClosed):
            oracle.click('dorm/page/back')
    else:
        with pytest.raises((AlasSemanticUnmapped,SemanticGateClosed)):
            a._appear_once(SimpleNamespace(name='GET_MISSION'))
    assert not b.taps

def test_urgent_notice_is_not_hidden_by_dorm_underlay():
    b=backend();o=make_oracle(b);o._campaign_urgent_notice_matches=lambda state:True
    a=AlasSemanticAdapter(o,lambda:None)
    with pytest.raises(SemanticGateClosed,match='urgent commission'):
        a._appear_once(SimpleNamespace(name='GET_MISSION'))
    assert not b.taps

def test_exact_retained_r214_dorm_frame():
    path=Path(__file__).resolve().parents[1]/'artifacts/semantic-cn-r214-probe-failures.jsonl'
    if not path.exists():pytest.skip('retained frame unavailable')
    row=next(json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()
             if json.loads(line)['resource']=='GET_MISSION')
    b=FakeBackend(row['state']['buttons_snapshot']['buttons'])
    b.ui=make_ui([])
    # Preserve the exact records while rebinding only fixture runtime identity.
    for key in ('texts','images'):
        b.ui[key]=row['ui'][key]
        b.ui['text_count' if key=='texts' else 'image_count']=len(b.ui[key])
    a=AlasSemanticAdapter(make_oracle(b),lambda:None)
    assert a.appear(SimpleNamespace(name='GET_MISSION')) is False
    assert not b.taps
