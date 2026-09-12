from types import SimpleNamespace
import copy
import pytest
from alas_headless import AlasSemanticAdapter, SemanticGateClosed
from tests.semantic_support.observer_fixtures import FakeBackend, make_button, make_toggle, make_text, make_image, make_ui, make_oracle

ROOT = 'UICamera/Canvas/UIMain/ShipBluePrintUI(Clone)/main'
CARD = 'OverlayCamera/Overlay/UIMain/blur_panel/adapt/bottom_panel/ships/bg/content/ship_tpl(Clone)'


def backend(research=True):
    b = FakeBackend([make_button('main', ROOT), make_button('back','OverlayCamera/Overlay/UIMain/blur_panel/adapt/top/back')])
    toggles, texts, images = [], [make_text('selected ship',ROOT+'/center_panel/name/name_mask/Text')], []
    for index in range(5):
        bounds = dict(left=100+index*180, right=260+index*180, top=600,bottom=720)
        toggles.append(make_toggle(CARD,checked=index==2,bounds=bounds))
        texts.append(make_text(str(48+index),CARD+'/count',bounds=bounds))
        # Development levels are not blueprint inventory.
        texts.append(make_text('15',CARD+'/state/dev/Text',bounds=bounds))
        if research and index==2:
            images.append(make_image(CARD+'/state/research/1','sel_dev',bounds=bounds))
        else:
            images.append(make_image(CARD+'/state/dev','dev_lv',bounds=bounds))
    if research:
        texts.append(make_text('研究进行中...',ROOT+'/center_panel/state_info/progress/label'))
    else:
        texts.append(make_text('<size=45>15</size>/<size=27>30</size>',
            'OverlayCamera/Overlay/UIMain/blur_panel/adapt/right_panel/mod_panel/title/level_bg/Text'))
    b.ui = make_ui(texts,toggles=toggles,images=images)
    return b


@pytest.mark.parametrize('research', [False,True])
def test_selected_card_inventory_and_phase_survive_clone_order(research):
    b = backend(research)
    b.ui['texts'].reverse();b.ui['toggles'].reverse();b.ui['images'].reverse()
    state = make_oracle(b).shipyard_state(3)
    assert state.blueprint_count==50
    assert state.cannot_strengthen is research
    assert state.level == (None if research else 15)
    assert state.phase == ('research' if research else 'dev')
    assert b.taps==[]


@pytest.mark.parametrize('change', ['missing_marker','wrong_marker','duplicate_count','wrong_selection','incoherent'])
def test_ambiguous_or_incomplete_selected_state_is_not_guessed(change):
    b = backend()
    if change=='missing_marker':
        b.ui['images']=[i for i in b.ui['images'] if not i['path'].endswith('/research/1')]
        b.ui['image_count']-=1
    elif change=='wrong_marker':
        next(i for i in b.ui['images'] if i['path'].endswith('/research/1'))['sprite']='unknown'
    elif change=='duplicate_count':
        b.ui['texts'].append(copy.deepcopy(next(t for t in b.ui['texts'] if t['text']=='50')))
        b.ui['text_count']+=1
    elif change=='wrong_selection':
        b.ui['toggles'][1]['checked']=True
    else:
        b.ui['generation']=13
    with pytest.raises(SemanticGateClosed):make_oracle(b).shipyard_state(3)
    assert make_oracle(b).shipyard_page_visible()
    assert b.taps==[]


def test_shipyard_page_does_not_require_a_dock_flow():
    a=AlasSemanticAdapter(make_oracle(backend()),package_gate=lambda:None)
    assert a.appear(SimpleNamespace(name='SHIPYARD_CHECK'))
    assert not a.appear(SimpleNamespace(name='DOCK_CHECK'))


@pytest.mark.parametrize('visible,generation,reuse', [(True,11,True),(False,11,False),(True,10,False)])
def test_repeated_entry_reuses_real_receipt_only_at_destination(visible,generation,reuse):
    from tests.semantic_support.adapter_fixtures import FakeOracle
    o=FakeOracle();o.shipyard_page_visible=lambda:visible;o.read_state=lambda:SimpleNamespace(generation=generation)
    a=AlasSemanticAdapter(o,package_gate=lambda:None);prior=SimpleNamespace(generation=10);a._shipyard_entry_receipt=prior
    receipt=a._click_mapped('RESHMENU_GOTO_SHIPYARD','research-menu/shipyard')
    assert (receipt is prior) is reuse
    assert o.click_calls==([] if reuse else ['research-menu/shipyard'])
    a.reset_task_state();assert a._shipyard_entry_receipt is None


def test_missing_development_level_never_means_strengthening_is_allowed():
    from alas_headless.oracle.contracts import ShipyardState
    state=ShipyardState(10,3,'ship',50,'dev',None,None,'complete')
    with pytest.raises(ValueError,match='unavailable'):
        _=state.cannot_strengthen
