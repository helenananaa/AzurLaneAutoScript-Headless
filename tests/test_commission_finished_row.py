"""Finished commissions hide countdowns; native ALAS owns their filtering."""
import copy

import pytest

from alas_headless import SemanticGateClosed
from alas_headless.oracle.contracts import CommissionStatus
from alas_headless.semantic_oracle import SemanticOracle
from tests.test_opsi_repair_input_frame import host
from tests.test_commission_incomplete_row_isolation import native_commission_class
from types import SimpleNamespace
from tests.test_alas_config_branch_compatibility import method


def observed():
    backend, session = host('commission-finished-row-r1002.json')
    return backend, SemanticOracle(backend.request, backend.foreground_component,
                                   backend.tap, session.open().oracle.fingerprint)


@pytest.mark.parametrize('drift', [False, True])
def test_retained_finished_row_with_no_countdown_preserves_native_status(drift):
    backend, oracle = observed()
    if drift:
        backend.buttons['buttons'].reverse()
        backend.ui['images'].reverse()
        backend.ui['compatible_extra_field'] = True
    rows = oracle.commission_rows()
    finished = next(row for row in rows if row.index == 0)
    assert finished.status == CommissionStatus.FINISHED
    assert finished.duration_seconds == 0
    native = native_commission_class()
    model = native.from_semantic(finished, SimpleNamespace(), 'daily')
    assert model.status == 'finished'
    check = method('module/commission/commission.py', 'RewardCommission', '_commission_check')
    assert not check(SimpleNamespace(config=SimpleNamespace()), model)
    with pytest.raises(SemanticGateClosed, match='not pending'):
        oracle.click_commission_row(finished.signature)
    with pytest.raises(SemanticGateClosed, match='signature is malformed'):
        oracle.click_commission_running_row(finished.signature)
    assert not backend.taps


def test_finished_neighbor_does_not_block_an_independent_pending_row():
    backend, oracle = observed()
    marker = next(item for item in backend.ui['images'] if item['path'].endswith('/content/1/iconState$/1'))
    marker['path'] = marker['path'][:-1] + '0'
    marker['sprite'] = 'kongxian_bg'
    rows = oracle.commission_rows()
    finished = next(row for row in rows if row.index == 0)
    pending = next(row for row in rows if row.index == 1)
    assert finished.status == CommissionStatus.FINISHED
    assert pending.status == CommissionStatus.PENDING
    receipt = oracle.click_commission_row(pending.signature)
    assert receipt.semantic_id == 'commission/row/1'
    assert len(backend.taps) == 1


@pytest.mark.parametrize('case', ['unknown', 'duplicate-status', 'truncated-status',
                                  'pending-without-timer', 'running-without-timer',
                                  'missing-name', 'foreign', 'stale'])
def test_unproven_finished_identity_or_other_status_without_timer_remains_closed(case):
    backend, oracle = observed()
    marker = next(item for item in backend.ui['images'] if item['path'].endswith('/content/0/iconState$/2'))
    if case == 'unknown':
        marker['sprite'] = 'unreviewed'
    elif case == 'duplicate-status':
        backend.ui['images'].append(copy.deepcopy(marker))
        backend.ui['image_count'] += 1
    elif case == 'truncated-status':
        marker['flags'] |= 0x10
    elif case in ('pending-without-timer', 'running-without-timer'):
        marker['path'] = marker['path'][:-1] + ('0' if case.startswith('pending') else '1')
        marker['sprite'] = 'kongxian_bg' if case.startswith('pending') else 'tag_ongoing'
    elif case == 'missing-name':
        backend.ui['texts'] = [t for t in backend.ui['texts'] if not t['path'].endswith('/content/0/labelName$')]
        backend.ui['text_count'] = len(backend.ui['texts'])
    elif case == 'foreign':
        backend.foreground = 'other.package/.Activity'
    else:
        backend.snapshot['age_ms'] = 100000
    with pytest.raises(SemanticGateClosed):
        oracle.commission_rows()
    assert not backend.taps
