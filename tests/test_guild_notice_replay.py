import json
from pathlib import Path
from types import SimpleNamespace
import pytest
from alas_headless import AlasSemanticAdapter
from alas_headless.semantic_oracle import SemanticOracle, OracleFingerprint
from tests.semantic_support.observer_fixtures import FakeBackend
from tests.semantic_support.adapter_fixtures import NamedButton


def test_retained_r8_closed_guild_notice_acknowledges_without_second_input():
    path = Path(__file__).resolve().parents[1] / 'artifacts/continuity-20261004/goal-scheduler-r8.json'
    if not path.exists():
        pytest.skip('retained r8 failure unavailable')
    task = json.loads(path.read_text(encoding='utf-8'))['tasks'][0]
    frame = task['failure_leased_frame']
    backend = FakeBackend([])
    backend.snapshot = frame['snapshot']
    backend.buttons = frame['buttons_snapshot']
    o = SemanticOracle(backend.request, backend.foreground_component, backend.tap,
        OracleFingerprint(package=backend.snapshot['package'], component=backend.foreground,
            driver_revision=backend.snapshot['driver_revision'], expected_pid=backend.snapshot['pid']))
    a = AlasSemanticAdapter(o, package_gate=lambda: None)
    close = next(action for action in task['actions'] if action['semantic_id'] == 'overlay/guild-message/close')
    prior = SimpleNamespace(generation=close['generation'])
    a._guild_message_close_receipt = prior
    assert a.click(NamedButton('GUILD_POPUP_CANCEL')) is None
    assert a._guild_message_close_receipt is prior
    assert backend.taps == []
