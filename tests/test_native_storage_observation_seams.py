"""Execute the original wait/count loops with only their observation ports replaced."""
import ast
from types import SimpleNamespace as N
from unittest.mock import Mock

import numpy as np
import pytest

from alas_headless import SemanticGateClosed
from alas_headless.adapter.semantic.session_tasks import SessionTasksPorts
from tests.test_alas_config_branch_compatibility import method,source
from tests.test_game_tips_loading_presence import host
from tests.test_storage_equipment_tab import material_host


@pytest.mark.parametrize('fixture,role',[
    ('storage-equipment-selection-20261027.json','equipment'),
    ('storage-equipment-warehouse-20261027.json','equipment'),
    ('storage-material-warehouse-20261027.json','material'),
])
def test_single_storage_sample_supports_each_actual_owned_list(fixture,role):
    backend,oracle,_=material_host() if role=='material' else host(fixture=fixture)
    first=oracle.storage_stability_sample()
    assert first[0]==role
    for value in (backend.snapshot,backend.buttons,backend.ui):value['generation']+=1
    assert oracle.storage_stability_sample()==first
    assert not backend.taps and not backend.swipes


@pytest.mark.parametrize('skip_first',[False,True])
def test_original_wait_timer_and_screenshots_own_the_typed_sample_loop(skip_first):
    run=method('module/base/base.py','ModuleBase','wait_until_stable',Timer=lambda *a,**kw:None)
    sampler=Mock(side_effect=[('material','a'),('material','b'),('material','b'),('material','b')])
    semantic=N(storage_stability_sample=sampler)
    device=N(semantic_adapter=semantic,screenshot=Mock())  # no image attribute
    button=N(name='MATERIAL_STABLE_CHECK',load_color=Mock(side_effect=AssertionError('pixels')),
             match=Mock(side_effect=AssertionError('pixels')))
    timer=Mock();timer.reached.side_effect=[False,True]
    timeout=Mock();timeout.reached.return_value=False
    run(N(device=device),button,timer=timer,timeout=timeout,skip_first_screenshot=skip_first)
    assert sampler.call_count==4
    assert device.screenshot.call_count==(3 if skip_first else 4)
    assert timer.reset.call_count==1 and timeout.reset.call_count==1
    button.load_color.assert_not_called();button.match.assert_not_called()


@pytest.mark.parametrize('semantic',[None,N(storage_stability_sample=Mock())])
def test_nonstorage_wait_retains_original_observation_behavior(semantic):
    run=method('module/base/base.py','ModuleBase','wait_until_stable',Timer=lambda *a,**kw:None)
    button=N(name='OTHER_STABLE',load_color=Mock(),match=Mock(side_effect=[False,True,True]))
    device=N(semantic_adapter=semantic,image=object(),screenshot=Mock())
    timer=Mock();timer.reached.side_effect=[False,True]
    timeout=Mock();timeout.reached.return_value=False
    run(N(device=device),button,timer=timer,timeout=timeout)
    assert button.load_color.call_count==2 and button.match.call_count==3
    assert device.screenshot.call_count==3
    if semantic:semantic.storage_stability_sample.assert_not_called()


def test_native_itemgrid_boundary_keeps_its_whole_stack_count_loop():
    backend,oracle,adapter=host(fixture='storage-equipment-selection-20261027.json')
    semantic=N(open=lambda:adapter)
    semantic.storage_equipment_inventory=lambda:SessionTasksPorts.storage_equipment_inventory(semantic)
    candidates=SessionTasksPorts.storage_equipment_items(semantic)
    assert len(candidates)==21 and candidates[0].amount==23
    # The native consumer still chooses cells. Stop before its OCR/confirmation.
    tree=ast.parse(source('module/storage/storage.py'))
    node=next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name=='_storage_disassemble_equipment_execute_once')
    stop=next(i for i,n in enumerate(node.body) if isinstance(n,ast.Assign)
              and any(isinstance(t,ast.Name) and t.id=='timeout' for t in n.targets))
    node.body=node.body[:stop]+[ast.Return(ast.Name(id='amount',ctx=ast.Load()))]
    aliases=('DISASSEMBLE_CONFIRM','DISASSEMBLE_POPUP_CONFIRM','GET_ITEMS_1','GET_ITEMS_2',
             'DISASSEMBLE_CANCEL','MATERIAL_STABLE_CHECK')
    namespace=dict(np=np,logger=Mock(),EQUIPMENT_ITEMS=N(predict=Mock(side_effect=AssertionError('pixel ItemGrid'))))
    namespace.update({key:key for key in aliases})
    exec(compile(ast.fix_missing_locations(ast.Module(body=[node],type_ignores=[])),'native-Storage-count','exec'),namespace)
    chosen=[]
    native=N(interval_clear=Mock(),loop=lambda:iter([None]),appear=lambda b,**kw:b=='DISASSEMBLE_CANCEL',
             handle_info_bar=lambda:False,wait_until_stable=Mock(),
             device=N(semantic_adapter=N(storage_equipment_items=lambda:candidates),
                      click=lambda item:chosen.append(item),click_record=[None]))
    assert namespace[node.name](native,amount=15)==23
    assert chosen==[candidates[0]]
    namespace['EQUIPMENT_ITEMS'].predict.assert_not_called()
    with pytest.raises(SemanticGateClosed):adapter.click(candidates[0])
    assert not backend.taps and not backend.swipes


def test_unknown_storage_surface_is_not_an_empty_stable_sample():
    _,oracle,_=host(fixture='commission-return-page-r131.json')
    with pytest.raises(SemanticGateClosed):oracle.storage_stability_sample()
