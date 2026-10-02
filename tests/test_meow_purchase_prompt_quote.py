import pytest
from tests.semantic_support.observer_fixtures import FakeBackend, make_button, make_oracle, make_text, make_ui


@pytest.mark.parametrize('nested', [False, True])
@pytest.mark.parametrize('content,expected', [
    ('<color=#847D7B>是否消耗17220物资购买15个喵箱？</color>', True),
    ('是否消耗17221物资购买15个喵箱？', False),
    ('是否消耗17220物资购买14个喵箱？', False),
    ('是否消耗17220钻石购买15个喵箱？', False),
])
def test_native_prompt_layout_requires_matching_ordinary_coin_quote(nested, content, expected):
    reserve='root/OverlayCamera/Overlay/UIMain/CommanderReserveUI(Clone)/'
    root=(reserve if nested else 'root/OverlayCamera/Overlay/UIMain/')+'CommanderMsgBoxUI(Clone)/frame/'
    backend=FakeBackend([make_button('cancel_btn',root+'cancel_btn',raycast_top=None),
                         make_button('confirm_btn',root+'confirm_btn',raycast_top=None)])
    backend.ui=make_ui([make_text(content,root+'bg/content/Text'),
                       make_text('15',reserve+'frame/bg1/count/Text'),
                       make_text('17220',reserve+'frame/bg1/price_all/Text')])
    oracle=make_oracle(backend)
    assert oracle.enabled('meowfficer/buy/confirm') is expected
    assert backend.taps==[]


@pytest.mark.parametrize('count,price,content,expected', [
    ('1','0','<color=#847D7B>每天的第一次喵箱预定免费喵！</color>', True),
    ('2','0','每天的第一次喵箱预定免费喵！', False),
    ('1','1','每天的第一次喵箱预定免费喵！', False),
    ('1','0','未知购买提示', False)])
def test_free_prompt_admits_exactly_one_zero_cost_box(count, price, content, expected):
    reserve='root/OverlayCamera/Overlay/UIMain/CommanderReserveUI(Clone)/'
    root='root/OverlayCamera/Overlay/UIMain/CommanderMsgBoxUI(Clone)/frame/'
    backend=FakeBackend([make_button('cancel_btn',root+'cancel_btn',raycast_top=None),
                         make_button('confirm_btn',root+'confirm_btn',raycast_top=None)])
    backend.ui=make_ui([make_text(content,root+'bg/content/Text'),
                       make_text(count,reserve+'frame/bg1/count/Text'),
                       make_text(price,reserve+'frame/bg1/price_all/Text')])
    oracle=make_oracle(backend)
    assert oracle.enabled('meowfficer/buy/confirm') is expected
    if expected:
        oracle.click('meowfficer/buy/confirm')
        assert len(backend.taps)==1
    else:
        from alas_headless import SemanticGateClosed
        with pytest.raises(SemanticGateClosed):
            oracle.click('meowfficer/buy/confirm')
        assert backend.taps==[]
