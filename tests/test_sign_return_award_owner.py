import pytest

from alas_headless import AlasSemanticAdapter
from tests.semantic_support.observer_fixtures import FakeBackend, make_button, make_oracle


BACK = 'root/UICamera/Canvas/UIMain/ActivityMainUI(Clone)/adapt/blur_panel/adapt/top/back_btn'


@pytest.mark.parametrize('raycast', [True, False, None])
def test_decorative_layer_does_not_disable_the_reviewed_sign_return(raycast):
    backend = FakeBackend([make_button('back_btn', BACK, raycast_top=raycast)])
    adapter = AlasSemanticAdapter(make_oracle(backend), lambda: None)
    assert adapter._appear_fallback('LOGIN_RETURN_SIGN', 'event-list/page/back') is True
    assert not backend.taps


@pytest.mark.parametrize('owner', ['award', 'message', 'loading'])
def test_real_overlay_keeps_native_sign_return_passively_absent(owner):
    paths = {
        'award': 'root/OverlayCamera/Overlay/UIMain/AwardInfoUI(Clone)/items/close',
        'message': 'root/OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/button_container/custom_button_1(Clone)',
        'loading': 'root/OverlayCamera/Overlay/UIOverlay/Loading(Clone)/load',
    }
    backend = FakeBackend([make_button('back_btn', BACK, raycast_top=False), make_button('close', paths[owner])])
    adapter = AlasSemanticAdapter(make_oracle(backend), lambda: None)
    assert adapter._appear_fallback('LOGIN_RETURN_SIGN', 'event-list/page/back') is False
    assert not backend.taps


def test_absent_sign_return_does_not_authorize_an_unrelated_page():
    backend = FakeBackend([])
    adapter = AlasSemanticAdapter(make_oracle(backend), lambda: None)
    assert adapter._appear_fallback('LOGIN_RETURN_SIGN', 'event-list/page/back') is False
    assert not backend.taps
