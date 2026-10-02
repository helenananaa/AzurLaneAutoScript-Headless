from unittest.mock import Mock
import pytest
from alas_headless import SemanticGateClosed
from tests.semantic_support.observer_fixtures import FakeBackend, make_oracle

def test_commission_prompt_rebinds_complete_snapshot_after_geometry_settles():
    oracle = make_oracle(FakeBackend([]))
    oracle._msgbox_prompt_parts = Mock(side_effect=[SemanticGateClosed('Msgbox snapshots are not coherent'), ('本次委托需要花费15石油','取消','确定')])
    oracle._tap = Mock()
    assert oracle.commission_start_prompt_cost() == 15
    assert oracle._msgbox_prompt_parts.call_count == 2
    oracle._tap.assert_not_called()

def test_persistent_incoherent_prompt_does_not_admit_cost_or_input():
    oracle = make_oracle(FakeBackend([]))
    oracle._msgbox_prompt_parts = Mock(side_effect=SemanticGateClosed('Msgbox snapshots are not coherent'))
    oracle._tap = Mock()
    with pytest.raises(SemanticGateClosed):
        oracle.commission_start_prompt_cost()
    assert oracle._msgbox_prompt_parts.call_count == 4
    oracle._tap.assert_not_called()
