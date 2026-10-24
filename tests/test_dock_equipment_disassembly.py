from types import SimpleNamespace

import pytest

from alas_headless import SemanticGateClosed
from alas_headless.adapter.semantic.dock import DockAdapterPorts
from tests.semantic_support.observer_fixtures import (
    FakeBackend, make_oracle, make_snapshot, make_buttons, make_button,
    make_ui, make_text, make_image, set_enhancement_page,
    set_retirement_selection,
)


ROOT = 'OverlayCamera/Overlay/UIMain/ResolveEquipmentUI(Clone)/'


def equipment(backend, generation=30, selected=True):
    root = ROOT + 'main/'
    buttons = [make_button('cancel_btn', root+'cancel_btn', 844, 606, raycast_top=True),
               make_button('ok_btn', root+'ok_btn', 1080, 606, raycast_top=True),
               make_button('ALL', root+'options/ALL', 200, 601, raycast_top=True)]
    if selected:
        buttons.append(make_button('reduce', root+'frame/view/content/0/frame/bg/selected/reduce',
                                   250, 156, raycast_top=True))
    backend.snapshot = make_snapshot(generation=generation)
    backend.buttons = make_buttons(buttons, generation=generation)
    backend.ui = make_ui([
        make_text('请选择需要拆解的装备，未选的装备将放入仓库',root+'title/Text'),
        make_text('确 定',root+'ok_btn/Image'), make_text('取 消',root+'cancel_btn/Image'),
        make_text('全部',root+'options/ALL/Label'),
        make_text('2',root+'frame/view/content/0/frame/bg/icon_bg/count'),
    ],images=[make_image(root+'options/ALL/Background/Checkmark','toggle_on')] if selected else [],
       generation=generation)


def confirmation(backend, generation=31, case='valid'):
    root=ROOT+'destroy_confirm/'
    backend.snapshot=make_snapshot(generation=generation)
    backend.buttons=make_buttons([
        make_button('destroy_button',root+'actions/destroy_button',790,510,raycast_top=case!='blocked'),
        make_button('cancel_button',root+'actions/cancel_button',480,510,raycast_top=True),
    ],generation=generation)
    backend.ui=make_ui([
        make_text('wrong' if case=='wrong-title' else '将获得以下材料:',root+'got/title'),
        make_text('确 定',root+'actions/destroy_button/Image'),
        make_text('取 消',root+'actions/cancel_button/Image'),
    ],generation=generation)


def award(backend, generation=32):
    root='OverlayCamera/Overlay/UIMain/AwardInfoUI(Clone)/items/'
    backend.snapshot=make_snapshot(generation=generation)
    backend.buttons=make_buttons([make_button('close',root+'close',640,482,raycast_top=True)],generation=generation)
    backend.ui=make_ui([
        make_text('物资',root+'items_scroll/content/item_tpl(Clone)/bg/name_mask/name'),
        make_text('4',root+'items_scroll/content/item_tpl(Clone)/bg/icon_bg/count'),
    ],generation=generation)


@pytest.mark.parametrize('owner',['enhancement','retirement'])
@pytest.mark.parametrize('selected',[True,False])
def test_disassembly_has_owned_confirmations_reward_and_native_return(owner,selected):
    backend=FakeBackend([]); equipment(backend,selected=selected)
    phases=[lambda: confirmation(backend),lambda: award(backend),
            lambda: set_enhancement_page(backend,33,enhanced=True)]
    if not selected: phases.insert(0,lambda: equipment(backend,generation=31))
    # Advance every transition's generation even when select-all was needed.
    def advance():
        phases.pop(0)()
        generation=30+len(backend.taps)*2
        for record in (backend.snapshot,backend.buttons,backend.ui):record['generation']=generation
    backend.on_tap=advance
    oracle=make_oracle(backend)
    oracle.retirement_selection_state=lambda: SimpleNamespace(generation=backend.snapshot['generation'],selected_count=0)
    quantities,actions,rewards=oracle._finish_dock_equipment_disassembly(owner=owner,timeout_seconds=2)
    assert quantities==((0,2),) and rewards==(('物资',4),)
    assert len(backend.taps)==(3 if selected else 4)
    assert all(a.semantic_id.startswith(owner+'/equipment/') for a in actions)
    assert backend.taps[-2:]==[(790,510),(640,482)]


@pytest.mark.parametrize('case',['wrong-title','blocked','stale','no-reward'])
def test_unknown_or_unsettled_destroy_never_repeats_confirmation(case):
    backend=FakeBackend([]);equipment(backend)
    def advance():
        if len(backend.taps)==1:confirmation(backend,30 if case=='stale' else 31,case)
        else:set_enhancement_page(backend,32,enhanced=True)
    backend.on_tap=advance
    oracle=make_oracle(backend)
    with pytest.raises(SemanticGateClosed):
        oracle._finish_dock_equipment_disassembly(owner='enhancement',timeout_seconds=.2)
    assert len(backend.taps)==(2 if case=='no-reward' else 1)


def test_enhancement_receipt_records_actual_disassembly():
    backend=FakeBackend([]);set_enhancement_page(backend,20)
    phases=[lambda:set_enhancement_page(backend,21,materials=((0,'xiaolietuquan'),),complete_card_images=True),
            lambda:equipment(backend),lambda:confirmation(backend),lambda:award(backend),
            lambda:set_enhancement_page(backend,33,enhanced=True)]
    backend.on_tap=lambda:phases.pop(0)()
    receipt=make_oracle(backend).enhance_with_official_recommendation(preserve_equipment=False)
    assert receipt.consumed_count==1 and receipt.equipment_disassembled
    assert not receipt.equipment_preserved and receipt.equipment_policy=='disassemble'
    assert receipt.equipment_quantities==((0,2),)


def test_policy_is_explicit_and_local(monkeypatch):
    monkeypatch.delenv('ALAS_SEMANTIC_DOCK_EQUIPMENT_POLICY',raising=False)
    assert DockAdapterPorts._dock_equipment_options()=={}
    monkeypatch.setenv('ALAS_SEMANTIC_DOCK_EQUIPMENT_POLICY','disassemble')
    assert DockAdapterPorts._dock_equipment_options()=={'preserve_equipment':False}
    monkeypatch.setenv('ALAS_SEMANTIC_DOCK_EQUIPMENT_POLICY','unknown')
    with pytest.raises(SemanticGateClosed):DockAdapterPorts._dock_equipment_options()


def test_retirement_receipt_keeps_ship_and_equipment_outcomes_separate():
    from alas_headless.oracle.contracts import RetirementSettingsState
    backend=FakeBackend([]);award(backend,20)
    phases=[lambda:equipment(backend),lambda:confirmation(backend),lambda:award(backend),
            lambda:set_retirement_selection(backend,33,970)]
    backend.on_tap=lambda:phases.pop(0)()
    settings=RetirementSettingsState(20,True,('R','SR','N'),'keep_none','keep_none')
    receipt=make_oracle(backend)._finish_retirement_transaction(
        SimpleNamespace(capacity_used=973,capacity_total=910),3,settings,[],3,
        preserve_equipment=False)
    assert receipt.retired_count==3 and receipt.equipment_disassembled
    assert not receipt.equipment_preserved and receipt.equipment_policy=='disassemble'
    assert receipt.equipment_quantities==((0,2),) and receipt.equipment_rewards==(('物资',4),)
