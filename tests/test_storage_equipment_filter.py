"""Equipment-owned CustomIndex ports; live raycasts remain unavailable in this fixture."""
import ast
import copy
from pathlib import Path
from types import SimpleNamespace as N
import typing

import pytest

from alas_headless import SemanticGateClosed
from tests.test_game_tips_loading_presence import host


ROOT = 'OverlayCamera/Overlay/UIMain/CustomIndexUI(Clone)/index_panel/layout/'


def equipment_filter(drift=False):
    backend, oracle, adapter = host(drift, 'storage-equipment-filter-20261027.json')
    adapter._fresh_input_oracle = lambda: oracle
    return backend, oracle, adapter


@pytest.mark.parametrize('drift', [False, True])
def test_exact_popup_is_observed_without_granting_unexported_inputs(drift):
    backend, oracle, adapter = equipment_filter(drift)
    assert adapter.appear('EQUIPMENT_FILTER_CONFIRM') is True
    assert adapter.appear('DISASSEMBLE_CANCEL') is False
    assert adapter.appear('STORAGE_CHECK') is False
    assert adapter.image_color_count('FILTER_RARITY_0_0', (181,142,90),235,250) is True
    assert adapter.image_color_count('FILTER_RARITY_1_0', (181,142,90),235,250) is False
    with pytest.raises(SemanticGateClosed): adapter.click('FILTER_RARITY_1_0')
    with pytest.raises(SemanticGateClosed): adapter.click('EQUIPMENT_FILTER_CONFIRM')
    assert not backend.taps


@pytest.mark.parametrize('damage', ['owner','label','sprite','duplicate','incoherent','foreign'])
def test_unsafe_popup_never_authorizes_filter_input(damage):
    backend, oracle, adapter = equipment_filter()
    target = next(b for b in backend.buttons['buttons'] if b['path']==ROOT+'container/indexsort_rarity/bg/1')
    target['raycast_top']=True
    if damage=='owner':
        backend.ui['images']=[i for i in backend.ui['images'] if 'StoreHouseUI(Clone)' not in i['path']]
    elif damage=='label':
        next(t for t in backend.ui['texts'] if t['path']==target['path']+'/Image')['text']='超稀有'
    elif damage=='sprite':
        next(i for i in backend.ui['images'] if i['path']==target['path'])['sprite']='unknown'
    elif damage=='duplicate':
        backend.buttons['buttons'].append(copy.deepcopy(target));backend.buttons['button_count']+=1
    elif damage=='incoherent':backend.ui['generation']+=3
    else:backend.foreground='other/.Activity'
    with pytest.raises(SemanticGateClosed):adapter.click('FILTER_RARITY_1_0')
    assert not backend.taps


def test_nonstorage_popup_and_unknown_option_do_not_enable_equipment_ports():
    backend, oracle, adapter = equipment_filter()
    with pytest.raises(SemanticGateClosed):adapter.click('FILTER_RARITY_6_0')
    with pytest.raises(SemanticGateClosed):adapter.click('DISASSEMBLE_CONFIRM')
    assert not backend.taps
    _, unrelated, _ = host(fixture='commission-return-page-r131.json')
    assert unrelated.storage_equipment_filter() is None


def test_existing_shared_blue_selection_contract_is_allowed_without_pixels():
    backend, _, adapter = equipment_filter()
    for image in backend.ui['images']:
        if image['path']==ROOT+'container/indexsort_rarity/bg/tpl':image['sprite']='btn_index_grey'
        if image['path']==ROOT+'container/indexsort_rarity/bg/1':image['sprite']='btn_index_blue'
    assert adapter.image_color_count('FILTER_RARITY_1_0',(74,117,189),235,250) is True
    assert adapter.image_color_count('FILTER_RARITY_1_0',(181,142,90),235,250) is False
    with pytest.raises(SemanticGateClosed):
        adapter.image_color_count('FILTER_RARITY_1_0',(1,2,3),235,250)
    assert not backend.taps


@pytest.mark.parametrize('name', ['FILTER_RARITY_1_0', 'EQUIPMENT_FILTER_CONFIRM'])
def test_real_session_admission_does_not_read_an_invalidated_input_frame(name):
    from alas_headless import AlasSemanticSession
    from alas_headless.adapter import semantic_runtime_fingerprint_sha256
    from tests.test_adapter_session_runtime_handle import FakeRuntimeHandle
    backend, _, _ = equipment_filter()
    suffix = 'container/indexsort_rarity/bg/1' if name.startswith('FILTER') else 'btns/ok'
    next(b for b in backend.buttons['buttons'] if b['path']==ROOT+suffix)['raycast_top']=True
    handle=FakeRuntimeHandle(semantic_runtime_fingerprint_sha256(
        package=backend.snapshot['package'],component=backend.foreground,
        driver_revision=backend.snapshot['driver_revision'],required_primary_abi='x86_64'))
    handle.pid=backend.snapshot['pid'];handle.observer_request=backend.request
    handle.foreground_component=backend.foreground_component
    handle.tap=backend.tap;handle.swipe=backend.swipe
    session=AlasSemanticSession(driver_revision=backend.snapshot['driver_revision'],runtime_handle=handle)
    try:
        session.open();session.refresh_frame()
        receipt=session.click(name)
        assert receipt.semantic_id.startswith('storage/equipment/filter')
        assert len(backend.taps)==1
    finally:session.close()


def test_native_setting_retains_its_reset_selection_and_screenshot_loop():
    backend, oracle, adapter = equipment_filter()
    # Controlled widget transition model, not a live selection claim.
    for button in backend.buttons['buttons']:
        if button['path'].startswith(ROOT):button['raycast_top']=True
    images={i['path']:i for i in backend.ui['images']}
    images[ROOT+'container/indexsort_rarity/bg/tpl']['sprite']='btn_index_grey'
    images[ROOT+'container/indexsort_rarity/bg/3']['sprite']='btn_index_yellow'
    native_tap=backend.tap
    def tap(x,y):
        native_tap(x,y)
        matches=[b for b in backend.buttons['buttons'] if b['path'].startswith(ROOT+'container/indexsort_rarity/bg/')
                 and round(b['adb_point']['x'])==x and round(b['adb_point']['y'])==y]
        assert len(matches)==1
        for path,image in images.items():
            if path.startswith(ROOT+'container/indexsort_rarity/bg/'):
                image['sprite']='btn_index_yellow' if path==matches[0]['path'] else 'btn_index_grey'
    oracle._tap=tap
    screenshots=[]
    def screenshot():
        screenshots.append(True)
        for payload in (backend.snapshot,backend.buttons,backend.ui):payload['generation']+=1
    class Timer:
        def __init__(self,value,**kwargs):self.value=value
        def start(self):return self
        def reset(self):return self
        def reached(self):return self.value==1
    tree=ast.parse((Path(__file__).parent/'fixtures/storage-native-setting-20261027.py').read_text(encoding='utf-8'))
    node=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='Setting')
    namespace=dict(copy=copy,t=typing,Button=object,ModuleBase=object,ScriptError=RuntimeError,
                   ButtonGrid=type('UnusedGrid',(),{}),Timer=Timer,
                   logger=N(info=lambda *a:None,attr=lambda *a:None,warning=lambda *a:None),dict_to_kv=lambda d:str(d))
    exec(compile(ast.Module(body=[node],type_ignores=[]),'native-Setting','exec'),namespace)
    def color(button,**kwargs):return adapter.image_color_count(button,**kwargs)
    main=N(image_color_count=color,device=N(click=adapter.click,screenshot=screenshot))
    setting=namespace['Setting']('STORAGE',main)
    buttons=[N(name=f'FILTER_RARITY_{i}_0') for i in range(6)]
    # Native Button is hashable; SimpleNamespace is not.
    buttons=[type('NativeOption',(),{'name':button.name})() for button in buttons]
    setting.add_setting('rarity',buttons,['all','common','rare','elite','super_rare','ultra_rare'],'all')
    setting.set(rarity='common')
    assert len(backend.taps)==2  # original reset all, then common
    assert screenshots
    assert images[ROOT+'container/indexsort_rarity/bg/1']['sprite']=='btn_index_yellow'
    assert adapter.image_color_count('FILTER_RARITY_1_0',(74,117,189),235,250) is False
