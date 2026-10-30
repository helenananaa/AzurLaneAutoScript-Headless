"""A reused pool object can remain active with the exact cleared name -1."""
import json
from pathlib import Path
from types import SimpleNamespace
import pytest

from alas_headless import SemanticGateClosed
from tests.test_game_tips_loading_presence import host

RAW=json.loads((Path(__file__).parent/'fixtures/retirement-common-cv-cleared-slot-20261027.json').read_text(encoding='utf-8'))


def setup(drift=False):
    b,o,_=host(drift,'retirement-common-cv-cleared-slot-20261027.json')
    t=RAW['source_target'];target=SimpleNamespace(**{k:v for k,v in t.items() if k!='card'},card=SimpleNamespace(**t['card']))
    return b,o,target


@pytest.mark.parametrize('drift',[False,True])
def test_real_cleared_slot_proves_logical_deselection_without_new_ship_identity(drift):
    b,o,target=setup(drift)
    assert o.retirement_cv_deselection_instance_postcondition(target)==(True,None)
    assert all(card.template_id>0 for card in o.retirement_preconfirm_cards())
    assert b.taps==[]


@pytest.mark.parametrize('case',['unchanged-count','capacity-change','other-sentinel','name-path-disagree','no-modal','old-generation'])
def test_cleared_identity_alone_does_not_prove_unmatched_result(case):
    b,o,target=setup()
    button=next(v for v in b.buttons['buttons'] if v.get('instance_id')==target.card.instance_id)
    if case=='unchanged-count':
        next(v for v in b.ui['texts'] if v['path'].endswith('/bottom_info/bg_input/count'))['text']='2'
    elif case=='capacity-change': target.capacity_used+=1
    elif case=='other-sentinel': button['name']='-2';button['path']=button['path'][:-2]+'-2'
    elif case=='name-path-disagree': button['name']='206011'
    elif case=='no-modal':
        b.buttons['buttons']=[v for v in b.buttons['buttons'] if not v['path'].endswith('DestoryInfoUI(Clone)/frame/confirm_button')]
        b.buttons['button_count']=len(b.buttons['buttons'])
        with pytest.raises(SemanticGateClosed):o.retirement_cv_deselection_instance_postcondition(target)
        assert b.taps==[]
        return
    else:target.generation=b.ui['generation']
    assert o.retirement_cv_deselection_instance_postcondition(target)==(False,None)
    assert b.taps==[]


def test_duplicate_active_instance_remains_ambiguous():
    b,o,target=setup();source=next(v for v in b.buttons['buttons'] if v.get('instance_id')==target.card.instance_id)
    b.buttons['buttons'].append(dict(source));b.buttons['button_count']+=1
    with pytest.raises(SemanticGateClosed):o.retirement_cv_deselection_instance_postcondition(target)
    assert b.taps==[]
