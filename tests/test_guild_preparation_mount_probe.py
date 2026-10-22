import time
from types import SimpleNamespace

import pytest

from alas_headless import AlasSemanticAdapter
from alas_headless.adapter.semantic.dispatch_result import UNHANDLED
from tests.semantic_support.adapter_fixtures import FakeOracle


@pytest.mark.parametrize('probe', ['WITHDRAW', 'MAP_PREPARATION', 'FLEET_PREPARATION', 'RAID_FLEET_PREPARATION'])
@pytest.mark.parametrize('case', ['loading', 'fresh', 'stale', 'expired', 'foreign'])
def test_original_additional_preparation_probes_yield_only_to_fresh_guild_mount(probe, case):
    oracle = FakeOracle()
    oracle.guild_page_visible = lambda: False
    oracle.main_page_visible = lambda: False
    oracle.read_state = lambda: SimpleNamespace(generation=10 if case == 'stale' else 11)
    blockers = ['msgbox'] if case == 'foreign' else ['loading'] if case == 'loading' else []
    oracle._blocking_rules = lambda *_: [SimpleNamespace(blocker_id=name) for name in blockers]
    adapter = AlasSemanticAdapter(oracle, lambda: None)
    adapter._main_guild_entry_receipt = SimpleNamespace(generation=10)
    adapter._main_guild_entry_until = time.monotonic() + (-1 if case == 'expired' else 12)
    result = adapter._appear_priority(probe)
    assert result is (False if case in ('loading', 'fresh') else UNHANDLED)
    assert oracle.click_calls == []
