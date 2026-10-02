from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from alas_headless import AlasSemanticSession, SemanticGateClosed
from tests.semantic_support.adapter_fixtures import NamedButton


@pytest.mark.parametrize('known', [True, False])
def test_student_selection_return_uses_reviewed_task_port(known):
    a = Mock()
    a._commission_context = SimpleNamespace(flow_kind='tactical')
    a.campaign_combat_committed.return_value = False
    a.operation_siren_combat_committed.return_value = False
    o = a._require_frame_observation_oracle.return_value
    o.enabled.side_effect = lambda target: target == 'tactical/dock/cancel'
    if known:
        o.tactical_candidate_ships.return_value = (SimpleNamespace(ship_id=818014),)
    else:
        o.tactical_candidate_ships.side_effect = SemanticGateClosed('unknown selection')
    s = AlasSemanticSession.__new__(AlasSemanticSession)
    s.adapter = a
    s.open = lambda: a
    s.refresh_frame = Mock()
    if known:
        assert s.click(NamedButton('GOTO_MAIN')) is o.click.return_value
        o.click.assert_called_once_with('tactical/dock/back')
        a.oracle.click_dock_page_back.assert_not_called()
    else:
        with pytest.raises(SemanticGateClosed, match='unknown selection'):
            s.click(NamedButton('GOTO_MAIN'))
        o.click.assert_not_called()
        a.oracle.click_dock_page_back.assert_not_called()
