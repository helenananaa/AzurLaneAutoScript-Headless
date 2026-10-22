import pytest

from alas_headless import AlasSemanticAdapter, SemanticGateClosed
from tests.semantic_support.observer_fixtures import FakeBackend, make_button, make_oracle


@pytest.mark.parametrize('foreign', [None, 'loading', 'msgbox'])
def test_original_page_graph_leaves_only_actionable_inherited_classroom(foreign):
    buttons = [make_button('btnBack',
        'root/UICamera/Canvas/UIMain/NewNavalTacticsUI(Clone)/adpter/frame/btnBack')]
    if foreign == 'loading':
        buttons.append(make_button('load', 'root/OverlayCamera/Overlay/UIOverlay/Loading(Clone)/load'))
    elif foreign == 'msgbox':
        buttons.append(make_button('confirm',
            'root/OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/button_container/custom_button_1(Clone)'))
    backend = FakeBackend(buttons)
    adapter = AlasSemanticAdapter(make_oracle(backend), lambda: None)
    assert adapter._commission_context is None
    if foreign:
        with pytest.raises(SemanticGateClosed):
            adapter.click('BACK_ARROW')
        assert backend.taps == []
    else:
        receipt = adapter.click('BACK_ARROW')
        assert receipt.semantic_id == 'tactical/page/back'
        assert backend.taps == [(640, 360)]


def test_unknown_page_cannot_borrow_classroom_back():
    backend = FakeBackend([make_button('btnBack', 'root/UnknownUI(Clone)/adpter/frame/btnBack')])
    adapter = AlasSemanticAdapter(make_oracle(backend), lambda: None)
    with pytest.raises(SemanticGateClosed):
        adapter.click('BACK_ARROW')
    assert backend.taps == []
