import json
from pathlib import Path

import pytest

from alas_headless import SemanticGateClosed
from alas_headless.semantic_oracle import SemanticOracle,OracleFingerprint
from tests.semantic_support.observer_fixtures import FakeBackend,make_button,make_image,make_text,make_ui,make_oracle

ROOT='OverlayCamera/Overlay/UIMain/WorldInventoryUI(Clone)/adapt/'
CARD=ROOT+'item_scrollview/Viewport/item_grid/110144'
TRACK=ROOT+'item_scrollview/Scrollbar'


def scene(top=615,bottom=780):
    card=make_button('110144',CARD,1000,(top+bottom)/2,
        dict(left=932,top=top,right=1071,bottom=bottom),raycast_top=None)
    backend=FakeBackend([make_button('back_btn',ROOT+'blur_panel/adapt/top/back_btn',raycast_top=None),card])
    images=[make_image(TRACK,'scroll_bg',dict(left=1257,top=104,right=1263,bottom=588)),
            make_image(TRACK+'/Handle','scroll_bar',dict(left=1252,top=100,right=1268,bottom=360))]
    for image in images:image['raycast_target']=True
    backend.ui=make_ui([make_text('塞壬坐标:东北海域',CARD+'/bg/name'),
                       make_text('1',CARD+'/bg/icon_bg/count')],images=images)
    return backend,make_oracle(backend)


def reveal(backend):
    backend.snapshot['generation']=backend.buttons['generation']=11
    backend.ui['generation']=11
    card=backend.buttons['buttons'][1]
    card['adb_bounds'].update(top=360,bottom=525)
    card['adb_point']['y']=442
    backend.ui['images'].reverse()
    backend.ui['harmless_addition']={'version':2}


def test_single_drag_uses_live_scrollbar_and_requires_visible_abyssal_destination():
    backend,oracle=scene()
    backend.on_swipe=lambda:reveal(backend)
    receipt=oracle.operation_siren_storage_scroll_for_abyssal()
    assert backend.swipes==[(1260,230,1260,458,450)]
    assert not backend.taps and oracle.input_dispatch_count==1
    assert receipt.pre_generation==10 and receipt.post_generation==11
    assert receipt.visible_abyssal_count==1


def test_already_visible_fresh_coordinate_needs_no_scroll_or_receipt():
    backend,oracle=scene(360,525)
    assert oracle.operation_siren_storage_scroll_for_abyssal() is None
    assert not backend.swipes and not backend.taps and oracle.input_dispatch_count==0


@pytest.mark.parametrize('case',['missing','duplicate','covered','detached','offscreen','truncated','foreground','foreign','stale','modal'])
def test_unproven_scrollbar_never_falls_back_to_content_coordinates(case):
    backend,oracle=scene()
    if case=='missing':backend.ui['images'].pop()
    elif case=='duplicate':backend.ui['images'].append(dict(backend.ui['images'][1]))
    elif case=='covered':backend.ui['images'][1]['raycast_top']=False
    elif case=='detached':backend.ui['images'][1]['adb_bounds'].update(left=1100,right=1110)
    elif case=='offscreen':backend.ui['images'][1]['adb_bounds']['right']=1300
    elif case=='truncated':backend.ui['image_truncated']=True
    elif case=='foreground':backend.foreground='com.android.settings/.Settings'
    elif case=='foreign':backend.snapshot['package']='other.package'
    elif case=='stale':backend.snapshot['age_ms']=100000
    else:
        backend.buttons['buttons'].append(make_button('confirm','OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/button_container/custom_button_1(Clone)'))
        backend.buttons['button_count']+=1
    backend.ui['image_count']=len(backend.ui['images'])
    with pytest.raises(SemanticGateClosed):oracle.operation_siren_storage_scroll_for_abyssal()
    assert not backend.swipes and not backend.taps and oracle.input_dispatch_count==0


def test_unproved_scroll_result_is_not_replayed():
    backend,oracle=scene()
    clock=[0.0]
    oracle._monotonic=lambda:clock[0]
    oracle._sleep=lambda _:clock.__setitem__(0,clock[0]+6)
    with pytest.raises(SemanticGateClosed,match='scroll was not proven'):
        oracle.operation_siren_storage_scroll_for_abyssal()
    assert len(backend.swipes)==1 and oracle.input_dispatch_count==1


def test_uncertain_swipe_dispatch_is_not_retried():
    backend,oracle=scene()
    error=SemanticGateClosed('swipe completion uncertain')
    def uncertain():raise error
    backend.on_swipe=uncertain
    with pytest.raises(SemanticGateClosed) as caught:oracle.operation_siren_storage_scroll_for_abyssal()
    assert caught.value is error and len(backend.swipes)==1


def test_retained_r98_scrollbar_plan_is_dynamic_and_input_free():
    path=Path(__file__).resolve().parents[1]/'artifacts/continuity-20261004/goal-scheduler-r98.json'
    if not path.exists():pytest.skip('retained r98 later scroll diagnostic unavailable')
    frame=json.loads(path.read_text(encoding='utf8'))['tasks'][-1]['failure_observation']
    backend=FakeBackend([])
    backend.snapshot=frame['state']['snapshot']
    backend.buttons=frame['state']['buttons_snapshot']
    backend.ui=frame['ui']['snapshot']
    oracle=SemanticOracle(backend.request,backend.foreground_component,backend.tap,
        OracleFingerprint(package=backend.snapshot['package'],component=backend.foreground,
            driver_revision=backend.snapshot['driver_revision'],expected_pid=backend.snapshot['pid']))
    _,start,end=oracle._operation_siren_storage_scrollbar_plan()
    assert start==(1260,231) and end==(1260,455)
    assert not backend.swipes and not backend.taps and oracle.input_dispatch_count==0
