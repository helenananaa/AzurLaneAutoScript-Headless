"""Controlled future equipment telemetry; raw live fixture remains unchanged."""
import ast
from types import SimpleNamespace as N
from unittest.mock import Mock

import numpy as np
import pytest

from alas_headless import SemanticGateClosed
from alas_headless.adapter.semantic.session_tasks import SessionTasksPorts
from tests.test_game_tips_loading_presence import host
from tests.test_storage_scrollbar_input_observation import queried,routing
from tests.test_alas_config_branch_compatibility import source


def equipment(adapt=True,active=True,size=.1):
    backend,oracle,adapter=host(fixture='storage-equipment-selection-20261027.json')
    oracle._swipe=backend.swipe
    bar=backend.ui['storage_scroll']['scrollbar']
    # Model the pending observer owner/path change; not a live export receipt.
    root='UICamera/Canvas/UIMain/StoreHouseUI(Clone)/'+('adapt/' if adapt else '')+'equipment_scrollview/Scrollbar'
    for index,control in enumerate(bar['controls']):
        control.update(path=root+('/Handle' if control['role']=='handle' else ''),
                       instance_id=801+index,active_in_hierarchy=active)
    bar.update(value=1.,size=size)
    return backend,oracle,adapter,bar


def session(adapter):
    return N(open=lambda:adapter)


@pytest.mark.parametrize('adapt',[False,True])
def test_existing_native_scroll_getter_selects_the_equipment_owner(adapt):
    backend,oracle,adapter,bar=equipment(adapt)
    observed=SessionTasksPorts.storage_material_scroll_state(session(adapter))
    assert observed.controls[0].path.endswith('equipment_scrollview/Scrollbar')
    assert observed.controls[0].instance_id==801
    assert not backend.taps and not backend.swipes


def test_actual_old_inactive_material_bar_is_not_reused_as_equipment():
    backend,_,adapter=host(fixture='storage-equipment-selection-20261027.json')
    with pytest.raises(SemanticGateClosed):SessionTasksPorts.storage_material_scroll_state(session(adapter))
    assert not backend.swipes and not backend.taps


def test_material_page_keeps_its_existing_native_scroll_owner():
    from tests.test_storage_equipment_tab import material_host
    backend,oracle,adapter=material_host()
    observed=SessionTasksPorts.storage_material_scroll_state(session(adapter))
    assert observed.controls[0].path.endswith('item_scrollview/Scrollbar')
    assert not backend.swipes and not backend.taps


def test_native_hidden_scrollbar_is_absence_but_unavailable_telemetry_is_an_error():
    backend,oracle,adapter,bar=equipment(active=False,size=1.)
    node=next(n for n in ast.parse(source('module/ui/scroll.py')).body if isinstance(n,ast.ClassDef) and n.name=='Scroll')
    namespace=dict(np=np,logger=Mock())
    exec(compile(ast.Module(body=[node],type_ignores=[]),'native-Scroll','exec'),namespace)
    scroll=namespace['Scroll'].__new__(namespace['Scroll']);scroll.name='METERIAL_SCROLL'
    semantic=N(storage_material_scroll_state=lambda:SessionTasksPorts.storage_material_scroll_state(session(adapter)))
    main=N(device=N(semantic_adapter=semantic))
    assert scroll.appear(main) is False
    bar['status']=2
    with pytest.raises(SemanticGateClosed):scroll.appear(main)
    assert not backend.swipes and not backend.taps


def test_equipment_drag_reuses_actual_handler_proof_and_one_progress_receipt():
    backend,oracle,_,bar=equipment()
    raw=routing(backend,point=[1260,128],handler_instance_id=801)
    queried(backend,oracle,raw)
    def progress():
        bar['value']=0.
        for packet in (backend.snapshot,backend.buttons,backend.ui):packet['generation']+=1
    backend.on_swipe=progress
    receipt=oracle.drag_storage_equipment_scroll_toward(1.)
    assert receipt.semantic_id=='storage/equipment/scroll'
    assert len(backend.swipes)==1 and not backend.taps
    assert receipt.after_position==1.


@pytest.mark.parametrize('damage',['other-handler','unowned','changed-page'])
def test_unproven_equipment_drag_is_not_dispatched(damage):
    backend,oracle,_,bar=equipment()
    raw=routing(backend,point=[1260,128],handler_instance_id=801)
    if damage=='other-handler':raw['handler_instance_id']=999
    if damage=='unowned':raw['owned']=False
    queried(backend,oracle,raw)
    if damage=='changed-page':
        original=oracle._request
        def request(line):
            result=original(line)
            if line.startswith('GET /v1/storage-scrollbar-input'):
                for toggle in backend.ui['toggles']:
                    if toggle['name']=='weapon':toggle['checked']=False
                    elif toggle['name']=='material':toggle['checked']=True
            return result
        oracle._request=request
    with pytest.raises(SemanticGateClosed):oracle.drag_storage_equipment_scroll_toward(1.)
    assert not backend.swipes and not backend.taps
    assert sum(q.startswith('GET /v1/storage-scrollbar-input') for q in backend.requests)==1


def test_switched_owner_after_accepted_equipment_drag_never_retries():
    backend,oracle,_,bar=equipment()
    queried(backend,oracle,routing(backend,point=[1260,128],handler_instance_id=801))
    def change():
        for control in bar['controls']:control['path']=control['path'].replace('equipment_scrollview','item_scrollview')
        for packet in (backend.snapshot,backend.buttons,backend.ui):packet['generation']+=1
    backend.on_swipe=change
    with pytest.raises(SemanticGateClosed):oracle.drag_storage_equipment_scroll_toward(1.)
    assert len(backend.swipes)==1 and not backend.taps
