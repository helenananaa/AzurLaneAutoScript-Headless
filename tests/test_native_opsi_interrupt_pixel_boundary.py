"""The native interrupt loop uses its typed port without pixel fallback."""
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from tests.test_alas_config_branch_compatibility import method


@pytest.mark.parametrize('semantic', [True,False])
def test_original_interrupt_preserves_loop_and_never_enters_legacy_quit_in_semantic_mode(semantic):
    session=Mock();session.handle_operation_siren_combat_interrupt.return_value=False
    legacy=Mock(return_value=True)
    if semantic:legacy.side_effect=AssertionError('typed interrupt fell into pixel quit matcher')
    host=SimpleNamespace(loop=lambda:[None],device=SimpleNamespace(semantic_adapter=session if semantic else None,
        click=Mock(side_effect=AssertionError('typed loop used legacy pause input'))),
        is_in_main=lambda:False,appear_then_click=lambda *a,**k:False,
        is_combat_executing=lambda:object() if semantic else False,interval_reset=Mock(),
        handle_combat_quit=legacy,handle_combat_quit_reconfirm=legacy,
        ui_additional=lambda:False,handle_map_event=lambda:False,is_combat_loading=lambda:True)
    interrupt=method('module/os/map.py','OSMap','interrupt_auto_search',Timer=Mock(),
        AUTO_SEARCH_REWARD=object(),GOTO_MAIN=object(),MAINTENANCE_ANNOUNCE=object())
    assert interrupt(host) is None
    assert legacy.call_count==(0 if semantic else 1)
