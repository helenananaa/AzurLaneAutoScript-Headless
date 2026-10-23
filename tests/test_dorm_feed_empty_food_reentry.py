from tests.alas_test_source import patched_alas_root
import ast
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from alas_headless.oracle.errors import SemanticGateClosed, SemanticTargetNotActionable
from tests.semantic_support.adapter_cases import AlasSemanticAdapterTestsSupport


@pytest.mark.parametrize('known_popup', [False, True])
def test_feed_refusal_is_retryable_only_before_any_card_with_exact_popup(known_popup):
    adapter, oracle, _ = AlasSemanticAdapterTestsSupport().make_adapter(dorm_feed_budget=1)
    adapter.begin_dorm()
    oracle.dorm_empty_food_cancel_value = known_popup
    adapter._fresh_dorm_feed_state = Mock(side_effect=SemanticGateClosed(
        'dorm feed panel identity is not proven'))
    with pytest.raises(SemanticGateClosed) as refused:
        adapter.dorm_feed_food(0, 1)
    assert isinstance(refused.value, SemanticTargetNotActionable) is known_popup
    if known_popup:
        assert refused.value.semantic_id == 'dorm/feed/item/50001'
    assert oracle.click_calls == []


def test_partially_consumed_batch_is_never_classified_for_replay():
    adapter, oracle, _ = AlasSemanticAdapterTestsSupport().make_adapter(dorm_feed_budget=2)
    adapter.begin_dorm()
    oracle.dorm_empty_food_cancel_value = True
    original = adapter._fresh_dorm_feed_state
    reads = []

    def state():
        reads.append(1)
        if len(reads) == 3:
            raise SemanticGateClosed('dorm feed panel identity is not proven')
        return original()

    adapter._fresh_dorm_feed_state = state
    with pytest.raises(SemanticGateClosed) as refused:
        adapter.dorm_feed_food(0, 2)
    assert not isinstance(refused.value, SemanticTargetNotActionable)
    assert oracle.click_calls == ['dorm/feed/item/50001']


@pytest.mark.parametrize('case', ['known', 'unknown', 'stale', 'other-target', 'unclassified'])
def test_original_food_click_uses_existing_entry_loop_only_for_safe_reentry(case):
    source = patched_alas_root() / 'module/dorm/dorm.py'
    tree = ast.parse(source.read_text(encoding='utf8'))
    method = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == '_dorm_feed_click')
    scope = {'SemanticTargetNotActionable': SemanticTargetNotActionable}
    exec(compile(ast.Module(body=[method], type_ignores=[]), str(source), 'exec'), scope)
    error = (SemanticGateClosed('blocked') if case == 'unclassified' else
             SemanticTargetNotActionable('dorm/feed/item/50002' if case == 'other-target' else 'dorm/feed/item/50001', 10))
    oracle = SimpleNamespace(read_state=lambda: SimpleNamespace(generation=9 if case == 'stale' else 11),
                             dorm_empty_food_cancel_available=lambda: case != 'unknown')
    session = SimpleNamespace(open=lambda: SimpleNamespace(oracle=oracle),
                              dorm_feed_food=Mock(side_effect=[error, ()]))
    button = object()
    host = SimpleNamespace(_dorm_food=SimpleNamespace(buttons=[button]),
                           loop=lambda **_: iter(range(2)), dorm_feed_enter=Mock())
    with patch('alas_headless.current_semantic_session', return_value=session):
        if case == 'known':
            scope['_dorm_feed_click'](host, button, 2)
            host.dorm_feed_enter.assert_called_once_with()
            assert session.dorm_feed_food.call_count == 2
        else:
            with pytest.raises(SemanticGateClosed):
                scope['_dorm_feed_click'](host, button, 2)
            host.dorm_feed_enter.assert_not_called()
            assert session.dorm_feed_food.call_count == 1
