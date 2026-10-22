"""A missed detail entry must not disable ALAS' original row retry loop."""
import json
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from alas_headless import AlasSemanticAdapter, SemanticGateClosed
from tests.semantic_support.adapter_fixtures import FakeOracle

SIGNATURE = (4,'日常资源开发V',40,3600,'pending','ziyuan')


def host_on_list():
    oracle = FakeOracle()
    oracle.enabled_values['commission/page/back'] = True
    oracle.observation_target_present = lambda target: False
    oracle.commission_rows = Mock(return_value=[SimpleNamespace(signature=SIGNATURE)])
    oracle.commission_detail_state = Mock(side_effect=SemanticGateClosed('detail absent'))
    host = AlasSemanticAdapter(oracle,lambda:None)
    host.begin_commission()
    host._commission_context.selected_signature = SIGNATURE
    host._commission_context.selected_at = time.monotonic()-30
    return host,oracle


def test_exact_pending_list_yields_to_original_timer_after_entry_grace():
    host,oracle = host_on_list()
    assert host.commission_selection_active() is False
    assert host._appear_fallback('COMMISSION_ADVICE',None) is False
    assert host._appear_fallback('COMMISSION_START',None) is False
    oracle.commission_detail_state.assert_not_called()
    assert oracle.click_calls == []
    assert host._commission_context.selected_signature == SIGNATURE


@pytest.mark.parametrize('fault',['detail','unowned-page','changed-row','ambiguous-row','covered','submitted'])
def test_list_reentry_cannot_hide_unproven_state_or_repeat_submitted_start(fault):
    host,oracle = host_on_list()
    if fault == 'detail': oracle.observation_target_present = lambda target: True
    elif fault == 'unowned-page': oracle.enabled_values['commission/page/back'] = False
    elif fault == 'changed-row': oracle.commission_rows.return_value = [SimpleNamespace(signature=SIGNATURE[:-2]+('running','ziyuan'))]
    elif fault == 'ambiguous-row': oracle.commission_rows.return_value *= 2
    elif fault == 'covered': oracle.commission_rows.side_effect = SemanticGateClosed('covered list')
    elif fault == 'submitted': host._commission_context.start_receipt = SimpleNamespace(generation=10)
    with pytest.raises(SemanticGateClosed):
        host._appear_fallback('COMMISSION_ADVICE',None)
    assert oracle.click_calls == []


def test_retained_r61_unopened_list_can_reenter_without_new_input():
    from alas_headless.semantic_oracle import SemanticOracle, OracleFingerprint
    from tests.semantic_support.observer_fixtures import FakeBackend
    path=Path(__file__).resolve().parents[1]/'artifacts/continuity-20261004/goal-scheduler-r61.json'
    if not path.exists(): pytest.skip('retained live frame unavailable')
    task=json.loads(path.read_text(encoding='utf8'))['tasks'][-1]
    frame=task['failure_leased_frame'];backend=FakeBackend([])
    backend.snapshot=frame['snapshot'];backend.buttons=frame['buttons_snapshot']
    backend.ui=task['failure_observation']['ui']['snapshot']
    # The recorded endpoints are adjacent frames. The static replay backend
    # uses one generation so repeated reads do not travel backwards in time.
    for snapshot in (backend.snapshot,backend.buttons,backend.ui):
        snapshot['generation']=backend.ui['generation']
    oracle=SemanticOracle(backend.request,backend.foreground_component,backend.tap,
        OracleFingerprint(package=backend.snapshot['package'],component=backend.foreground,
            driver_revision=backend.snapshot['driver_revision'],expected_pid=backend.snapshot['pid']))
    rows=oracle.commission_rows();selected=next(r for r in rows if r.index==4)
    host=AlasSemanticAdapter(oracle,lambda:None);host.begin_commission()
    host._commission_context.selected_signature=selected.signature
    host._commission_context.selected_at=time.monotonic()-30
    assert host.commission_selection_active() is False
    assert host._appear_fallback('COMMISSION_ADVICE',None) is False
    assert backend.taps==[]
