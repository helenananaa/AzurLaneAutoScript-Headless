import json
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from alas_headless import AlasSemanticAdapter, AlasSemanticUnmapped
from alas_headless.semantic_oracle import SemanticOracle, OracleFingerprint
from tests.semantic_support.observer_fixtures import FakeBackend
from tests.semantic_support.adapter_fixtures import FakeOracle


@pytest.mark.parametrize('name', ['GET_ITEMS_1', 'GET_ITEMS_2', 'GET_ITEMS_3'])
def test_retained_later_main_frame_already_proves_reward_absence(name):
    p = Path(__file__).resolve().parents[1] / 'artifacts/continuity-20261004/goal-scheduler-r20.json'
    if not p.exists():
        pytest.skip('retained r20 frame unavailable')
    t = next(t for t in json.loads(p.read_text(encoding='utf-8'))['tasks']
             if t['selected_task'] == 'Meowfficer')
    frame = t['failed_presence']
    b = FakeBackend([])
    b.snapshot = frame['state']['snapshot']
    b.buttons = frame['state']['buttons_snapshot']
    b.ui = frame['ui']['snapshot']
    o = SemanticOracle(b.request, b.foreground_component, b.tap,
        OracleFingerprint(package=b.snapshot['package'], component=b.foreground,
            driver_revision=b.snapshot['driver_revision'], expected_pid=b.snapshot['pid']))
    a = AlasSemanticAdapter(o, package_gate=lambda: None)
    # This diagnostic frame is already ready. It does not reproduce the
    # original timing failure and must not be relabeled as a partial frame.
    assert o.main_page_visible()
    assert not a.appear(SimpleNamespace(name=name))
    assert b.taps == []


@pytest.mark.parametrize('name', ['GET_ITEMS_1', 'GET_ITEMS_2', 'GET_ITEMS_3'])
@pytest.mark.parametrize('receipt_kind', ['dorm/page/back', 'unknown/page/back', 'expired'])
def test_partial_home_mount_uses_only_reviewed_dorm_back_return(name, receipt_kind):
    o = FakeOracle()
    o.main_page_visible = lambda: False
    a = AlasSemanticAdapter(o, package_gate=lambda: None)
    receipt = SimpleNamespace(semantic_id='dorm/page/back' if receipt_kind == 'expired'
                              else receipt_kind, generation=10)
    a._record_mission_transition(receipt)
    if receipt_kind == 'expired':
        a._dorm_return_transition_until = time.monotonic() - 1
    if receipt_kind == 'dorm/page/back':
        assert not a.appear(SimpleNamespace(name=name))
    else:
        with pytest.raises(AlasSemanticUnmapped):
            a.appear(SimpleNamespace(name=name))
    assert o.click_calls == []
