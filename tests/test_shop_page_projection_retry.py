from copy import deepcopy

import pytest

from alas_headless import SemanticGateClosed
from alas_headless.adapter.frame import _FrameBoundSemanticOracle
from tests.semantic_support.observer_fixtures import FakeBackend,make_button,make_text,make_ui,make_oracle


def shop():
    root='OverlayCamera/Overlay/UIMain/ShopSupplyShopUI(Clone)/'
    bounds=dict(left=150,top=200,right=400,bottom=250)
    buttons=[make_button('closeBtn',root+'buttonList/top/closeBtn'),
             make_button('homeBtn',root+'buttonList/top/homeBtn'),
             make_button('Toggle(Clone)',root+'toggleGroup/Toggle(Clone)',275,225,bounds)]
    buttons.extend(make_button(str(i),root+'scroll/content/'+str(i)) for i in range(10))
    backend=FakeBackend(buttons)
    backend.ui=make_ui([make_text('商店',root+'buttonList/top/title/Text'),
        make_text('大舰队',root+'toggleGroup/Toggle(Clone)/unselected/Label',bounds)])
    return backend,make_oracle(backend)


def test_live_page_split_re_reads_before_one_tab_input_without_widening_tolerance():
    backend,oracle=shop()
    backend.ui['generation']=backend.buttons['generation']+3
    sleeps=[]
    def publish(_):
        assert not backend.taps and oracle.input_dispatch_count==0
        sleeps.append(True)
        backend.snapshot['generation']=backend.buttons['generation']=20
        backend.ui['generation']=20
        backend.buttons['buttons'].reverse()
        backend.ui['upstream_addition']={'version':2}
    oracle._sleep=publish
    receipt=oracle.click_shop_tab('大舰队')
    assert receipt.semantic_id=='shop/tab/大舰队' and receipt.generation==20
    assert len(sleeps)==1 and len(backend.taps)==1


@pytest.mark.parametrize('case',['persistent','stale','foreign','foreground','ambiguous','wrong-page'])
def test_shop_page_or_tab_refusal_stays_closed_without_input(case):
    backend,oracle=shop()
    if case=='persistent':
        backend.ui['generation']=backend.buttons['generation']+3
    elif case=='stale':
        backend.snapshot['age_ms']=100000
    elif case=='foreign':
        backend.snapshot['package']='other.package'
    elif case=='foreground':
        backend.foreground='com.android.settings/.Settings'
    elif case=='ambiguous':
        backend.ui['texts'].append(deepcopy(backend.ui['texts'][1]))
        backend.ui['text_count']+=1
    else:
        backend.ui['texts'][0]['text']='其他页面'
    sleeps=[]
    oracle._sleep=lambda _:sleeps.append(True)
    with pytest.raises(SemanticGateClosed):
        oracle.click_shop_tab('大舰队')
    assert not backend.taps and oracle.input_dispatch_count==0 and len(sleeps)<=3


def test_immutable_shop_page_does_not_re_read_or_sleep():
    backend,original=shop()
    backend.ui['generation']=backend.buttons['generation']+3
    sleeps=[]
    oracle=_FrameBoundSemanticOracle(backend.request,backend.foreground_component,
        backend.tap,original.fingerprint,sleep=lambda _:sleeps.append(True),frame_guard=lambda:None)
    with pytest.raises(SemanticGateClosed,match='not coherent'):
        oracle.munitions_page_visible()
    assert not backend.taps and not sleeps


def test_uncertain_tab_input_is_not_retried():
    backend,oracle=shop()
    error=SemanticGateClosed('tab input completion uncertain')
    def uncertain(*_):
        raise error
    backend.on_tap=uncertain
    with pytest.raises(SemanticGateClosed) as caught:
        oracle.click_shop_tab('大舰队')
    assert caught.value is error and len(backend.taps)==1


def test_page_and_tab_share_one_pair_without_independent_identity_read():
    from unittest.mock import Mock
    backend,oracle=shop()
    state_read=oracle.read_state
    ui_read=oracle.read_ui_state
    oracle.read_state=Mock(wraps=state_read)
    oracle.read_ui_state=Mock(wraps=ui_read)
    oracle.munitions_page_visible=Mock(side_effect=AssertionError('unrelated second identity read'))
    assert oracle.click_shop_tab('大舰队').semantic_id=='shop/tab/大舰队'
    assert oracle.read_state.call_count==1 and oracle.read_ui_state.call_count==1
    assert len(backend.taps)==1
