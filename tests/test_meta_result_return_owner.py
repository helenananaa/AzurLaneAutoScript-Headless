from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from alas_headless import AlasSemanticAdapter, AlasSemanticSession
from tests.semantic_support.adapter_fixtures import FakeOracle, NamedButton


@pytest.mark.parametrize('owner', ['beacon', 'assist'])
@pytest.mark.parametrize('receipt,newer,result,combat,page,released', [
    (True, True, False, False, True, True),
    (False, True, False, False, True, False),
    (True, False, False, False, True, False),
    (True, True, True, False, True, False),
    (True, True, False, True, True, False),
    (True, True, False, False, False, False),
])
def test_meta_return_releases_only_accepted_result_on_new_proven_page(
        owner, receipt, newer, result, combat, page, released):
    o = FakeOracle()
    o.read_state = Mock(return_value=SimpleNamespace(generation=11 if newer else 10))
    o.daily_battle_result_visible = lambda: result
    o.daily_combat_visible = lambda: combat
    o.meta_page_visible_value = page
    o.operation_siren_battle_result_visible = lambda: False
    a = AlasSemanticAdapter(o, package_gate=lambda: None)
    getattr(a, 'begin_meta_' + owner)()
    a._operation_siren_combat_active = True
    s = AlasSemanticSession('emulator-test', '506b76f698b5089aaa29c4e7908b48edb8532a44')
    s.adapter = a
    s.open = lambda: a
    s._combat_last_result_receipt = SimpleNamespace(generation=10) if receipt else None
    s._live_combat_visible = Mock(return_value=())
    # This is the first presence probe in the original META expected_end.
    assert not s.appear(NamedButton('BATTLE_PREPARATION'))
    assert a.operation_siren_combat_committed() is (not released)
    if released:
        s._live_combat_visible.assert_not_called()
        assert s._combat_last_result_receipt is None
    assert o.click_calls == []
