from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from alas_headless import AlasSemanticSession
from alas_headless import SemanticGateClosed
from alas_headless.adapter import AdbRuntimeHandle,semantic_runtime_fingerprint_sha256
from alas_headless.semantic_oracle import AdbObserverBridge
from tests.test_game_tips_loading_presence import host
from tests.test_alas_config_branch_compatibility import method


def session_with_info():
    backend,oracle,_=host(fixture='opsi-adaptability-info-r61.json')
    bridge=AdbObserverBridge('offline-adaptability',backend.snapshot['package']);bridge.pid=backend.snapshot['pid']
    bridge.request=backend.request;bridge.foreground_component=backend.foreground_component
    bridge.tap=backend.tap;bridge.swipe=backend.swipe;bridge.package_pid=Mock(return_value=bridge.pid)
    rev=backend.snapshot['driver_revision']
    fp=semantic_runtime_fingerprint_sha256(package=backend.snapshot['package'],component=backend.foreground,driver_revision=rev,required_primary_abi='x86_64')
    s=AlasSemanticSession(driver_revision=rev,runtime_handle=AdbRuntimeHandle(bridge,fingerprint_sha256=fp));s.refresh_frame()
    return backend,s


def test_original_single_confirm_handler_reaches_typed_popup_through_real_session_dispatch():
    backend,s=session_with_info()
    class Button:
        def __init__(self,name):self.name=name
    names={n:Button(n) for n in ('POPUP_CANCEL','POPUP_CONFIRM','POPUP_CONFIRM_WHITE')}
    run=method('module/handler/info_handler.py','InfoHandler','handle_popup_confirm',**names)
    h=SimpleNamespace(device=SimpleNamespace(semantic_adapter=s,click=s.click),_popup_offset=(3,30),
                      appear=lambda b,**kw:s.appear(b))
    assert run(h,'UI_ADDITIONAL')
    assert names['POPUP_CONFIRM_WHITE'].name=='POPUP_CONFIRM_WHITE'
    assert len(backend.taps)==1


@pytest.mark.parametrize('case', ['new-popup', 'foreign-package'])
def test_owned_dismissal_does_not_acknowledge_unrelated_or_foreign_state(case):
    backend,s=session_with_info()
    s.click('POPUP_CONFIRM_WHITE_UI_ADDITIONAL')
    for source in (backend.snapshot,backend.buttons,backend.ui):source['generation']+=1
    if case == 'new-popup':
        next(t for t in backend.ui['texts'] if t['path'].endswith('/display_panel/desc/Text'))['text']='消耗500钻石'
    else:
        backend.snapshot['package']='foreign.package'
    with pytest.raises(SemanticGateClosed):
        s.click('POPUP_CONFIRM_WHITE_UI_ADDITIONAL')
    assert len(backend.taps)==1



def test_departed_info_alias_acknowledges_one_actual_map_return_without_second_input():
    backend,s=session_with_info()
    receipt=s.click('POPUP_CONFIRM_WHITE_UI_ADDITIONAL')
    assert receipt.semantic_id=='os/adaptability/info/confirm'
    for source in (backend.snapshot,backend.buttons,backend.ui):source['generation']+=1
    backend.buttons['buttons']=[b for b in backend.buttons['buttons'] if '/Msgbox(Clone)/' not in b['path']]
    backend.buttons['button_count']=len(backend.buttons['buttons'])
    backend.ui['texts']=[t for t in backend.ui['texts'] if '/Msgbox(Clone)/' not in t['path']]
    backend.ui['text_count']=len(backend.ui['texts'])
    backend.ui['images']=[i for i in backend.ui['images'] if '/Msgbox(Clone)/' not in i['path']]
    backend.ui['image_count']=len(backend.ui['images'])
    assert s.click('POPUP_CONFIRM_WHITE_UI_ADDITIONAL') is None
    assert s.open()._operation_siren_adaptability_info_receipt is None
    assert len(backend.taps)==1


def test_native_map_back_acquires_new_input_frame_instead_of_old_observer():
    backend,s=session_with_info()
    backend.buttons['buttons']=[b for b in backend.buttons['buttons'] if '/Msgbox(Clone)/' not in b['path']]
    backend.buttons['button_count']=len(backend.buttons['buttons'])
    backend.ui['texts']=[t for t in backend.ui['texts'] if '/Msgbox(Clone)/' not in t['path']]
    backend.ui['text_count']=len(backend.ui['texts'])
    backend.ui['images']=[i for i in backend.ui['images'] if '/Msgbox(Clone)/' not in i['path']]
    backend.ui['image_count']=len(backend.ui['images'])
    s.refresh_frame()
    adapter=s.open()
    adapter.oracle.click_operation_siren_back=Mock(side_effect=AssertionError('old observer must not dispatch input'))
    adapter._goto_main_target=lambda:'os/page/back'
    receipt=s.click('GOTO_MAIN')
    assert receipt.semantic_id=='os/page/back'
    assert len(backend.taps)==1
