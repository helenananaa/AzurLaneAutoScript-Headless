"""Native Academy navigation can repeat its accepted edge during Loading."""
import json
import time
from pathlib import Path
from unittest.mock import Mock

import pytest

from alas_headless import AlasSemanticAdapter
from alas_headless.semantic_oracle import ActionReceipt, Bounds, OracleFingerprint, Point, SemanticOracle
from tests.semantic_support.observer_fixtures import FakeBackend


@pytest.mark.parametrize('expired', [False, True])
def test_recorded_academy_entry_reuses_only_recent_accepted_navigation(expired):
    data = json.loads((Path(__file__).parent/'fixtures/academy-entry-loading-r219.json').read_text(encoding='utf8'))
    backend = FakeBackend([])
    backend.snapshot, backend.buttons = data['snapshot'], data['buttons']
    oracle = SemanticOracle(backend.request, backend.foreground_component, backend.tap,
        OracleFingerprint(package=backend.snapshot['package'], component=backend.foreground,
            driver_revision=backend.snapshot['driver_revision'], expected_pid=backend.snapshot['pid'], max_age_ms=10000))
    adapter = AlasSemanticAdapter(oracle, lambda: None)
    raw_receipt = dict(data['prior_receipt'])
    raw_receipt['point'] = Point(**raw_receipt['point'])
    raw_receipt['bounds'] = Bounds(**raw_receipt['bounds'])
    previous = ActionReceipt(**raw_receipt)
    adapter._commission_navigation_handoff = (previous, oracle.input_dispatch_count,
        time.monotonic()+(-1 if expired else 12))
    final_attempt = object()
    adapter._click_once = Mock(return_value=final_attempt)
    assert adapter.click('DORMMENU_GOTO_ACADEMY') is (final_attempt if expired else previous)
    assert adapter._click_once.call_count == int(expired)
    assert not backend.taps
