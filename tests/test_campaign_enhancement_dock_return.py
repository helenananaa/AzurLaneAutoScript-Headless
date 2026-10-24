"""Native Dock return must precede retained combat defensive aliases."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from alas_headless import AlasSemanticSession, SemanticGateClosed
from tests.semantic_support.adapter_cases import AlasSemanticAdapterTestsSupport


def session_with_retained_combat(control):
    adapter, oracle, _ = AlasSemanticAdapterTestsSupport().make_adapter()
    adapter.begin_campaign_pre_sortie('12-4')
    adapter.campaign_combat_committed = lambda: True
    oracle.enhancement_dock_back_control = control
    session = AlasSemanticSession.__new__(AlasSemanticSession)
    session.adapter = adapter
    session.open = lambda: adapter
    session._live_combat_visible = Mock(return_value=set())
    return session, oracle


def test_exact_dock_return_precedes_committed_combat_absence():
    session, oracle = session_with_retained_combat(lambda: object())
    assert session.appear(SimpleNamespace(name='BACK_ARROW')) is True
    session._live_combat_visible.assert_not_called()
    assert oracle.click_calls == []


def test_absent_dock_still_uses_existing_combat_probe():
    session, oracle = session_with_retained_combat(lambda: None)
    assert session.appear(SimpleNamespace(name='BACK_ARROW')) is False
    session._live_combat_visible.assert_called_once()
    assert oracle.click_calls == []


def test_obscured_or_ambiguous_dock_control_remains_closed():
    session, oracle = session_with_retained_combat(
        Mock(side_effect=SemanticGateClosed('Dock back Image is not actionable')))
    with pytest.raises(SemanticGateClosed, match='not actionable'):
        session.appear(SimpleNamespace(name='BACK_ARROW'))
    session._live_combat_visible.assert_not_called()
    assert oracle.click_calls == []


def test_dock_input_uses_existing_reviewed_return_not_combat_alias():
    session, oracle = session_with_retained_combat(lambda: object())
    session.refresh_frame = Mock()
    session._live_combat_click = Mock(side_effect=AssertionError('combat alias'))
    receipt = SimpleNamespace(generation=11)
    oracle.click_enhancement_dock_back = Mock(return_value=receipt)
    assert session.click(SimpleNamespace(name='BACK_ARROW')) is receipt
    session.refresh_frame.assert_called_once()
    session._live_combat_click.assert_not_called()
    oracle.click_enhancement_dock_back.assert_called_once()
