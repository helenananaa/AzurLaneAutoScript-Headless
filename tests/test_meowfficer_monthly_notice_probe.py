from types import SimpleNamespace

import pytest

from alas_headless import AlasSemanticUnmapped
from tests.semantic_support.adapter_cases import AlasSemanticAdapterTestsSupport
from tests.semantic_support.adapter_fixtures import NamedButton


@pytest.mark.parametrize('foreign', [False, True])
def test_exact_meow_dock_owns_notice_absence_only_without_foreign_overlay(foreign):
    adapter, oracle, _ = AlasSemanticAdapterTestsSupport().make_adapter()
    oracle.exists_values['meowfficer/page/back'] = True
    oracle.enabled_values['meowfficer/page/back'] = False
    oracle._blocking_rules = lambda *_: [SimpleNamespace(blocker_id='meowfficer-dock')] + (
        [SimpleNamespace(blocker_id='unknown')] if foreign else [])
    if foreign:
        from alas_headless.adapter.semantic.dispatch_result import UNHANDLED
        assert adapter._appear_priority('MONTHLY_PASS_NOTICE') is UNHANDLED
    else:
        assert not adapter.appear(NamedButton('MONTHLY_PASS_NOTICE'))
    with pytest.raises(AlasSemanticUnmapped):
        adapter.click(NamedButton('MONTHLY_PASS_NOTICE'))
    assert oracle.click_calls == []
