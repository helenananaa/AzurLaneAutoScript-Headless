"""Retained r602 Main sources must not dispatch a pending live-menu edge twice."""
from copy import deepcopy
import json
from pathlib import Path
import time

import pytest

from alas_headless import AlasSemanticAdapter, SemanticGateClosed
from alas_headless.semantic_oracle import OracleFingerprint, SemanticOracle
from tests.semantic_support.observer_fixtures import FakeBackend, make_button


def replay(drift=False):
    rows = json.loads((Path(__file__).parent / 'fixtures/live-menu-entry-r602.json')
                      .read_text(encoding='utf-8'))['records']
    backend = FakeBackend([])

    def load(index):
        source = deepcopy(rows[index]['source'])
        backend.snapshot, backend.buttons = source['snapshot'], source['buttons']
        if drift:
            backend.buttons['buttons'].reverse()
            backend.buttons['optional_metadata'] = {'additive': True}

    load(0)
    oracle = SemanticOracle(backend.request, backend.foreground_component, backend.tap,
        OracleFingerprint(package=backend.snapshot['package'], component=backend.foreground,
            driver_revision=backend.snapshot['driver_revision'],
            expected_pid=backend.snapshot['pid'], max_age_ms=10000))
    adapter = AlasSemanticAdapter(oracle, lambda: None)
    adapter._fresh_input_oracle = lambda: oracle
    return backend, oracle, adapter, load


@pytest.mark.parametrize('drift', [False, True])
@pytest.mark.parametrize('alias', ['MAIN_GOTO_DORMMENU', 'MAIN_GOTO_DORMMENU_WHITE'])
def test_exact_pending_source_reuses_accepted_edge_without_second_input(alias, drift):
    backend, oracle, adapter, load = replay(drift)
    first = adapter.click('MAIN_GOTO_DORMMENU')
    assert first.generation == 65991
    assert len(backend.taps) == 1
    load(1)  # Exact 65993 source: Main still owns input; no live-menu anchor yet.
    assert not oracle.observation_target_present('dorm-menu/dorm')
    assert adapter.click(alias) is first
    assert len(backend.taps) == 1
    load(4)  # Exact accepted Academy source 66014, menu now owns input.
    assert adapter.click(alias) is first
    academy = adapter.click('DORMMENU_GOTO_ACADEMY')
    assert academy.semantic_id == 'dorm-menu/academy'
    assert academy.generation == 66014
    assert len(backend.taps) == 2


@pytest.mark.parametrize('case', ['expired', 'intervening-input'])
def test_real_new_entry_or_native_retry_remains_allowed(case):
    backend, oracle, adapter, load = replay()
    first = adapter.click('MAIN_GOTO_DORMMENU')
    load(1)
    if case == 'expired':
        receipt, count, _ = adapter._commission_navigation_handoff
        adapter._commission_navigation_handoff = receipt, count, time.monotonic() - 1
    else:
        oracle.click('main/tech')
    second = adapter.click('MAIN_GOTO_DORMMENU_WHITE')
    assert second is not first
    assert len(backend.taps) == (2 if case == 'expired' else 3)


@pytest.mark.parametrize('case', ['stale', 'foreign-modal', 'wrong-foreground'])
def test_pending_receipt_does_not_bypass_current_state_refusals(case):
    backend, _, adapter, load = replay()
    adapter.click('MAIN_GOTO_DORMMENU')
    load(1)
    if case == 'stale':
        backend.snapshot['age_ms'] = 10001
    elif case == 'wrong-foreground':
        backend.foreground = 'other.package/.Main'
    else:
        backend.buttons['buttons'].append(make_button('custom_button_1(Clone)',
            'OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/button_container/custom_button_1(Clone)'))
        backend.buttons['button_count'] += 1
    with pytest.raises(SemanticGateClosed):
        adapter.click('MAIN_GOTO_DORMMENU_WHITE')
    assert len(backend.taps) == 1
