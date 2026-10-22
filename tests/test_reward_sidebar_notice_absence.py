from types import SimpleNamespace

import pytest

from alas_headless import AlasSemanticAdapter, AlasSemanticUnmapped, SemanticGateClosed
from tests.semantic_support.observer_fixtures import FakeBackend, make_button, make_oracle


@pytest.mark.parametrize('name', ['MONTHLY_PASS_NOTICE', 'BATTLE_PASS_NOTICE', 'BATTLE_PASS_NEW_SEASON', 'POPUP_SINGLE_WHITE'])
@pytest.mark.parametrize('foreign', [False, True])
def test_sidebar_proves_passive_notice_absence_only_when_unobscured(name, foreign):
    buttons = [make_button('CommissionInfoUI4Mellow(Clone)', 'OverlayCamera/Overlay/UIMain/CommissionInfoUI4Mellow(Clone)')]
    if foreign:
        buttons.append(make_button('confirm', 'OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/button_container/custom_button_1(Clone)'))
    backend = FakeBackend(buttons)
    host = AlasSemanticAdapter(make_oracle(backend), package_gate=lambda: None)
    if foreign:
        with pytest.raises((AlasSemanticUnmapped, SemanticGateClosed)):
            host.appear(SimpleNamespace(name=name))
    else:
        assert host.appear(SimpleNamespace(name=name)) is False
    assert backend.taps == []
