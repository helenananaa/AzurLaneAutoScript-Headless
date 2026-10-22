"""META's shared combat latch must not fan out into live OS map readers."""
from unittest.mock import Mock
import pytest
from tests.semantic_support.adapter_cases import AlasSemanticAdapterTestsSupport


@pytest.mark.parametrize('owner', ['_meta_beacon_active', '_meta_assist_active'])
def test_meta_return_never_reads_unrelated_live_os_completion_surfaces(owner):
    adapter, oracle, _ = AlasSemanticAdapterTestsSupport().make_adapter()
    adapter._operation_siren_combat_active = True
    setattr(adapter, owner, True)
    readers = ['daily_battle_result_visible', 'operation_siren_battle_statistics_visible',
               'award_info_page_visible', 'operation_siren_local_map_visible']
    for name in readers:
        setattr(oracle, name, Mock(side_effect=AssertionError('unrelated live OS result probe')))
    assert adapter.complete_operation_siren_combat_if_map_restored() is False
    assert adapter._operation_siren_combat_active  # META must release its owner.
    for name in readers:
        getattr(oracle, name).assert_not_called()


def test_real_os_owner_still_requires_and_accepts_exact_unobscured_map():
    adapter, oracle, _ = AlasSemanticAdapterTestsSupport().make_adapter()
    adapter._operation_siren_combat_active = True
    oracle.daily_battle_result_visible = Mock(return_value=False)
    oracle.operation_siren_battle_statistics_visible = Mock(return_value=False)
    oracle.award_info_page_visible = Mock(return_value=False)
    oracle.operation_siren_local_map_visible = Mock(return_value=True)
    assert adapter.complete_operation_siren_combat_if_map_restored()
    assert not adapter._operation_siren_combat_active
    oracle.operation_siren_local_map_visible.assert_called_once()
