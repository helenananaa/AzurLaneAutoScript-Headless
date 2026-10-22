import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from alas_headless import AlasSemanticAdapter, SemanticGateClosed
from alas_headless.adapter.semantic.dispatch_result import UNHANDLED
from alas_headless.adapter.semantic.contracts import AlasSemanticActionDeferred
from alas_headless.semantic_oracle import SemanticOracle, OracleFingerprint
from tests.semantic_support.adapter_fixtures import FakeOracle
from tests.semantic_support.observer_fixtures import FakeBackend


@pytest.mark.parametrize('confirm', [True, False])
def test_tactical_navigation_delegates_proven_os_exit(confirm):
    o = FakeOracle()
    o.observation_prompt_kind_value = 'opsi-exit'
    o.operation_siren_exit_prompt_visible = lambda: True
    receipt = SimpleNamespace(semantic_id='os/exit/confirm' if confirm else 'os/exit/cancel', generation=10)
    o.click_operation_siren_exit = Mock(return_value=receipt)
    a = AlasSemanticAdapter(o, package_gate=lambda: None)
    a.begin_tactical()
    a._tactical_course_target_enabled = Mock(side_effect=AssertionError('wrong owner'))
    name = 'POPUP_CONFIRM' if confirm else 'POPUP_CANCEL'
    assert a._appear_tactical(name, None) is UNHANDLED
    assert a._click_tactical(name) is UNHANDLED
    assert a.appear(SimpleNamespace(name=name))
    # FakeOracle also advertises the legacy login cancel mapping. Verify the
    # shared cancel handler directly; the live regression uses confirmation.
    assert (a.click(SimpleNamespace(name=name)) if confirm
            else a._click_confirmation(name)) is receipt
    o.click_operation_siren_exit.assert_called_once_with(confirm=confirm)
    a._tactical_course_target_enabled.assert_not_called()
    assert a._commission_context.tactical_confirm_receipt is None


@pytest.mark.parametrize('kind, visible', [('opsi-exit', False), (None, True), ('tactical-course', True)])
def test_tactical_unproven_exit_keeps_assignment_boundary(kind, visible):
    o = FakeOracle()
    o.observation_prompt_kind_value = kind
    o.operation_siren_exit_prompt_visible = lambda: visible
    a = AlasSemanticAdapter(o, package_gate=lambda: None)
    a.begin_tactical()
    assert a._appear_tactical('POPUP_CONFIRM', None) is False
    with pytest.raises(AlasSemanticActionDeferred, match='tactical.assign'):
        a._click_tactical('POPUP_CONFIRM')
    assert o.click_calls == []


def test_retained_tactical_exit_frame_reaches_original_confirmation_probe():
    p = Path(__file__).resolve().parents[1] / 'artifacts/continuity-20261004/goal-tactical-back-observation-r1.json'
    if not p.exists():
        pytest.skip('retained read-only live frame unavailable')
    frame = json.loads(p.read_text(encoding='utf-8'))['samples'][0]
    b = FakeBackend([])
    b.snapshot = frame['state']['snapshot']
    b.buttons = frame['state']['buttons_snapshot']
    b.ui = frame['ui_state']['snapshot']
    o = SemanticOracle(b.request, b.foreground_component, b.tap,
        OracleFingerprint(package=b.snapshot['package'], component=b.foreground,
            driver_revision=b.snapshot['driver_revision'], expected_pid=b.snapshot['pid']))
    a = AlasSemanticAdapter(o, package_gate=lambda: None)
    a.begin_tactical()
    assert o.observation_prompt_kind() == 'opsi-exit'
    assert o.operation_siren_exit_prompt_visible()
    assert a.appear(SimpleNamespace(name='POPUP_CONFIRM'))
    assert b.taps == []
