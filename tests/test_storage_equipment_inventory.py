"""Read-only equipment metadata from actual frames, without ItemGrid pixels."""
import copy

import pytest

from alas_headless import SemanticGateClosed
from tests.test_game_tips_loading_presence import host


ROOT='UICamera/Canvas/UIMain/StoreHouseUI(Clone)/adapt/equipment_scrollview/'
COUNT='OverlayCamera/Overlay/UIMain/topItems/adapt/select_panel/bottom_info/bg_input/count'


@pytest.mark.parametrize('drift',[False,True])
def test_actual_visible_inventory_does_not_include_the_clipped_fourth_row(drift):
    backend,oracle,_=host(drift,'storage-equipment-selection-20261027.json')
    observed=oracle.storage_equipment_inventory()
    assert observed.selected_count==0
    assert [item.slot for item in observed.items]==[str(i) for i in range(21)]
    assert observed.partial_slots==tuple(str(i) for i in range(21,28))
    assert observed.items[0].quantity==23
    assert observed.items[0].icon_sprite=='21300'
    assert observed.items[0].upgrade_level==0
    assert all(not item.button.actionable for item in observed.items)
    assert not backend.taps


def test_actual_loaded_upgrade_is_observed_without_making_it_a_visible_candidate():
    backend,oracle,_=host(fixture='storage-equipment-selection-20261027.json')
    item=oracle.storage_equipment_item('26')
    assert item.upgrade_level==7 and item.quantity==1
    assert item.background_sprite=='bg2'
    assert item.fully_visible is False
    assert not backend.taps


@pytest.mark.parametrize('damage',['count','duplicate','incoherent','truncated','level','foreign'])
def test_missing_or_ambiguous_metadata_never_becomes_an_empty_list_or_zero_level(damage):
    backend,oracle,_=host(fixture='storage-equipment-selection-20261027.json')
    if damage=='count':
        next(t for t in backend.ui['texts'] if t['path']==ROOT+'equipment_grid/0/frame/bg/icon_bg/count')['text']='2K'
    elif damage=='duplicate':
        target=next(b for b in backend.buttons['buttons'] if b['path']==ROOT+'equipment_grid/0')
        backend.buttons['buttons'].append(copy.deepcopy(target));backend.buttons['button_count']+=1
    elif damage=='incoherent':backend.ui['generation']+=3
    elif damage=='truncated':backend.ui['text_truncated']=True
    elif damage=='level':
        backend.ui['texts']=[t for t in backend.ui['texts'] if not t['path'].endswith('/26/frame/bg/icon_bg/slv/Text')]
        backend.ui['text_count']=len(backend.ui['texts'])
    else:backend.foreground='other/.Activity'
    with pytest.raises(SemanticGateClosed):
        if damage=='level':oracle.storage_equipment_item('26')
        else:oracle.storage_equipment_inventory()
    assert not backend.taps


def test_no_loaded_items_is_not_an_unqualified_native_empty_state():
    backend,oracle,_=host(fixture='storage-equipment-selection-20261027.json')
    backend.buttons['buttons']=[b for b in backend.buttons['buttons'] if not b['path'].startswith(ROOT+'equipment_grid/')]
    backend.buttons['button_count']=len(backend.buttons['buttons'])
    with pytest.raises(SemanticGateClosed):oracle.storage_equipment_inventory()
    assert not backend.taps


def test_selected_count_is_typed_and_final_disassembly_remains_unmapped():
    backend,oracle,adapter=host(fixture='storage-equipment-selection-20261027.json')
    assert oracle.storage_equipment_selected_count()==0
    next(t for t in backend.ui['texts'] if t['path']==COUNT)['text']='23'
    assert oracle.storage_equipment_selected_count()==23
    with pytest.raises(SemanticGateClosed):adapter.click('DISASSEMBLE_CONFIRM')
    assert not backend.taps


def test_partial_row_loading_does_not_block_complete_visible_inventory():
    backend,oracle,_=host(fixture='storage-equipment-selection-20261027.json')
    backend.ui['texts']=[t for t in backend.ui['texts'] if not t['path'].startswith(ROOT+'equipment_grid/26/')]
    backend.ui['text_count']=len(backend.ui['texts'])
    assert len(oracle.storage_equipment_inventory().items)==21
    with pytest.raises(SemanticGateClosed):oracle.storage_equipment_item('26')
    assert not backend.taps


def test_no_fully_visible_row_does_not_report_an_empty_inventory():
    backend,oracle,_=host(fixture='storage-equipment-selection-20261027.json')
    next(i for i in backend.ui['images'] if i['path']==ROOT.rstrip('/'))['adb_bounds']['bottom']=60
    with pytest.raises(SemanticGateClosed):oracle.storage_equipment_inventory()
    assert not backend.taps


def test_original_native_prefix_keeps_whole_stack_counting_without_real_input():
    """Only the retained ALAS prefix plans cells; ItemGrid pixels are a pending seam."""
    import ast
    from pathlib import Path
    from types import SimpleNamespace as N
    import numpy as np
    backend,oracle,_=host(fixture='storage-equipment-selection-20261027.json')
    items=oracle.storage_equipment_inventory().items
    node=ast.parse((Path(__file__).parent/'fixtures/storage-native-disassemble-once-20261027.py').read_text(encoding='utf-8')).body[0]
    # Stop the native function before its quantity OCR/confirmation loops.
    # Its original min/cumsum/selection loop is executed without copying it.
    stop=next(i for i,stmt in enumerate(node.body) if isinstance(stmt,ast.Assign)
              and any(isinstance(target,ast.Name) and target.id=='timeout' for target in stmt.targets))
    node.body=node.body[:stop]+[ast.Return(ast.Name(id='amount',ctx=ast.Load()))]
    aliases=('DISASSEMBLE_CONFIRM','DISASSEMBLE_POPUP_CONFIRM','GET_ITEMS_1','GET_ITEMS_2',
             'DISASSEMBLE_CANCEL','MATERIAL_STABLE_CHECK')
    class MetadataGrid:
        def predict(self,frame,*,name,amount):
            assert name is False and amount is True
            return [N(slot=item.slot,amount=item.quantity) for item in items]
    namespace=dict(np=np,EQUIPMENT_ITEMS=MetadataGrid(),logger=N(info=lambda *a:None,warning=lambda *a:None))
    namespace.update({name:name for name in aliases})
    exec(compile(ast.fix_missing_locations(ast.Module(body=[node],type_ignores=[])),'original-native-prefix','exec'),namespace)
    selected=[]
    native=N(interval_clear=lambda *a:None,loop=lambda:iter([None]),appear=lambda button,**kw:button=='DISASSEMBLE_CANCEL',
             handle_info_bar=lambda:False,wait_until_stable=lambda *a:None,
             device=N(image=object(),click=lambda item:selected.append(item.slot),click_record=[None]))
    result=namespace[node.name](native,amount=15)
    assert selected==['0'] and result==23  # original ALAS can exceed15 via a whole stack
    assert not backend.taps


def test_session_exposes_only_readonly_inventory_and_selected_count():
    from alas_headless import AlasSemanticSession
    from alas_headless.adapter import semantic_runtime_fingerprint_sha256
    from tests.test_adapter_session_runtime_handle import FakeRuntimeHandle
    backend,_,_=host(fixture='storage-equipment-selection-20261027.json')
    handle=FakeRuntimeHandle(semantic_runtime_fingerprint_sha256(
        package=backend.snapshot['package'],component=backend.foreground,
        driver_revision=backend.snapshot['driver_revision'],required_primary_abi='x86_64'))
    handle.pid=backend.snapshot['pid'];handle.observer_request=backend.request
    handle.foreground_component=backend.foreground_component
    handle.tap=backend.tap;handle.swipe=backend.swipe
    session=AlasSemanticSession(driver_revision=backend.snapshot['driver_revision'],runtime_handle=handle)
    try:
        session.open();session.refresh_frame()
        assert len(session.storage_equipment_inventory().items)==21
        assert session.storage_equipment_selected_count()==0
        before=session.storage_equipment_stability_sample()
        next(t for t in backend.ui['texts'] if t['path']==COUNT)['text']='23'
        for payload in (backend.snapshot,backend.buttons,backend.ui):payload['generation']+=1
        assert session.storage_equipment_selected_count()==0  # same immutable screenshot
        session.refresh_frame()
        assert session.storage_equipment_selected_count()==23
        assert session.storage_equipment_stability_sample()!=before
        with pytest.raises(SemanticGateClosed):session.click('DISASSEMBLE_CONFIRM')
        assert not backend.taps
    finally:session.close()


def test_stability_sample_ignores_generation_but_detects_actual_stack_changes():
    backend,oracle,_=host(fixture='storage-equipment-selection-20261027.json')
    sample=oracle.storage_equipment_stability_sample()
    for payload in (backend.snapshot,backend.buttons,backend.ui):payload['generation']+=1
    assert oracle.storage_equipment_stability_sample()==sample
    next(t for t in backend.ui['texts'] if t['path']==ROOT+'equipment_grid/0/frame/bg/icon_bg/count')['text']='24'
    assert oracle.storage_equipment_stability_sample()!=sample
    assert not backend.taps
