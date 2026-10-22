from types import SimpleNamespace

import pytest

from alas_headless import AlasSemanticAdapter, SemanticGateClosed
from tests.semantic_support.adapter_fixtures import FakeOracle


@pytest.mark.parametrize('main,dispatched,ready', [
    (True, False, True), (True, False, False),
    (False, False, True), (True, True, True),
])
@pytest.mark.parametrize('target', ['mail', 'dock', 'battle'])
def test_main_mapping_reuses_home_actionability_wait_without_repeating_input(monkeypatch, main, dispatched, ready, target):
    from alas_headless.adapter.semantic import dispatch_actions
    clock = [0.0]
    monkeypatch.setattr(dispatch_actions.time, 'monotonic', lambda: clock[0])
    monkeypatch.setattr(dispatch_actions.time, 'sleep', lambda seconds: clock.__setitem__(0, clock[0] + seconds))
    o = FakeOracle()
    o.input_dispatch_count = 0
    o.main_page_visible = lambda: main
    o.enabled = lambda _: ready and clock[0] >= .4
    calls = []
    semantic_id = 'main/' + target
    name = 'MAIN_GOTO_CAMPAIGN' if target == 'battle' else 'MAIN_GOTO_' + target.upper() + '_WHITE'
    receipt = SimpleNamespace(semantic_id=semantic_id, generation=11)
    def click(target):
        calls.append(target)
        if len(calls) == 1:
            o.input_dispatch_count += int(dispatched)
            raise SemanticGateClosed('semantic target is not actionable')
        o.input_dispatch_count += 1
        return receipt
    o.click = click
    a = AlasSemanticAdapter(o, package_gate=lambda: None)
    if target == 'mail':
        a.begin_mail()
    if main and not dispatched and ready:
        assert a._click_mapped(name, semantic_id) is receipt
        assert o.input_dispatch_count == 1
        if target == 'mail':
            assert a._mail_context.entry_receipt is receipt
    else:
        with pytest.raises(SemanticGateClosed):
            a._click_mapped(name, semantic_id)
        assert o.input_dispatch_count == int(dispatched)
    assert calls == [semantic_id] * (2 if main and not dispatched and ready else 1)
