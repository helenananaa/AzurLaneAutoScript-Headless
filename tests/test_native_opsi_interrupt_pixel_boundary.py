"""The native interrupt loop uses its typed port without pixel fallback."""
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from tests.test_alas_config_branch_compatibility import method
from alas_headless.oracle.errors import SemanticInputBlocked


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


@pytest.mark.parametrize('semantic_id, blockers, accepted', [
    ('os/page/back', ('loading',), True),
    ('os/page/back', ('loading', 'foreign-modal'), False),
    ('os/page/back', ('foreign-modal',), False),
    ('other/page/back', ('loading',), False),
])
def test_native_interrupt_waits_only_for_pre_input_os_back_loading(semantic_id, blockers, accepted):
    class NativeStop(Exception):
        pass
    state = {'screenshots': 0, 'attempts': 0}
    home = object()
    def frames():
        for _ in range(2):
            state['screenshots'] += 1
            yield None
    def appear_then_click(button, **kwargs):
        if button is home:
            state['attempts'] += 1
            raise SemanticInputBlocked(semantic_id, 7606, blockers)
        return False
    session = SimpleNamespace(handle_operation_siren_combat_interrupt=lambda: False)
    host = SimpleNamespace(loop=frames, device=SimpleNamespace(semantic_adapter=session),
        is_in_main=lambda: state['screenshots'] > 1,
        config=SimpleNamespace(task_stop=Mock(side_effect=NativeStop)),
        appear_then_click=appear_then_click, interval_reset=Mock(),
        ui_additional=lambda: False, handle_map_event=lambda: False,
        is_combat_loading=lambda: True)
    interrupt = method('module/os/map.py', 'OSMap', 'interrupt_auto_search', Timer=Mock(),
        AUTO_SEARCH_REWARD=object(), GOTO_MAIN=home, MAINTENANCE_ANNOUNCE=object())
    if accepted:
        with pytest.raises(NativeStop):
            interrupt(host)
        assert state['screenshots'] == 2
        host.config.task_stop.assert_called_once()
    else:
        with pytest.raises(SemanticInputBlocked) as rejected:
            interrupt(host)
        assert rejected.value.semantic_id == semantic_id
        assert rejected.value.blockers == blockers
        host.config.task_stop.assert_not_called()
    assert state['attempts'] == 1
