import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from alas_headless import AlasSemanticAdapter, AlasSemanticSession, SemanticGateClosed
from alas_headless.semantic_oracle import SemanticOracle, OracleFingerprint
from tests.semantic_support.observer_fixtures import FakeBackend
from tests.semantic_support.adapter_fixtures import FakeOracle


@pytest.mark.parametrize('name', ['GET_ITEMS_1', 'GET_ITEMS_2'])
@pytest.mark.parametrize('change', [None, 'no_receipt', 'old_generation', 'owner'])
def test_retained_sync_return_consumes_only_existing_close_receipt(name, change):
    p = Path(__file__).resolve().parents[1] / 'artifacts/continuity-20261004/goal-scheduler-r17.json'
    if not p.exists():
        pytest.skip('retained r17 frame unavailable')
    t = next(t for t in json.loads(p.read_text(encoding='utf-8'))['tasks']
             if t['selected_task'] == 'OpsiAshBeacon')
    frame = t['failure_observation']
    previous = next(a for a in reversed(t['actions'])
                    if a['semantic_id'] == 'reward/award-info/close')
    b = FakeBackend([])
    b.snapshot = frame['state']['snapshot']
    b.buttons = frame['state']['buttons_snapshot']
    b.ui = frame['ui']['snapshot']
    # Separate live endpoints were captured one generation apart. Replaying
    # them repeatedly would move the fake clock backwards after a UI read;
    # hold this read-only shape at the newest captured coherent generation.
    generation = max(b.snapshot['generation'], b.buttons['generation'], b.ui['generation'])
    for snapshot in (b.snapshot, b.buttons, b.ui):
        snapshot['generation'] = generation
    o = SemanticOracle(b.request, b.foreground_component, b.tap,
        OracleFingerprint(package=b.snapshot['package'], component=b.foreground,
            driver_revision=b.snapshot['driver_revision'], expected_pid=b.snapshot['pid']))
    a = AlasSemanticAdapter(o, package_gate=lambda: None)
    a.begin_meta_beacon()
    receipt = SimpleNamespace(**previous)
    if change == 'old_generation':
        receipt.generation = b.snapshot['generation']
    if change != 'no_receipt':
        a._meta_reward_close_receipt = receipt
    if change == 'owner':
        a._meta_beacon_active = False
    if change:
        with pytest.raises(SemanticGateClosed):
            a.click(SimpleNamespace(name=name))
    else:
        assert a.click(SimpleNamespace(name=name)) is receipt
        assert a._meta_reward_close_receipt is None
    assert b.taps == []


def test_meta_sync_close_records_receipt_for_native_repeat():
    o = FakeOracle()
    o.award_info_page_visible = lambda: True
    o.meta_character_sync_page_visible = lambda: False
    receipt = SimpleNamespace(generation=10, semantic_id='reward/award-info/close')
    o.click = Mock(return_value=receipt)
    a = AlasSemanticAdapter(o, package_gate=lambda: None)
    a.begin_meta_beacon()
    a._award_close_target = lambda: 'reward/award-info/close'
    assert a._click_priority('GET_ITEMS_1') is receipt
    assert a._meta_reward_close_receipt is receipt
    o.click.assert_called_once_with('reward/award-info/close')


@pytest.mark.parametrize('change', [None, 'no_receipt', 'old_generation', 'owner', 'malformed'])
def test_character_sync_return_reuses_only_accepted_close(change):
    p = Path(__file__).resolve().parents[1] / 'artifacts/continuity-20261004/goal-scheduler-r26.json'
    if not p.exists():
        pytest.skip('retained r26 frame unavailable')
    task = next(t for t in json.loads(p.read_text(encoding='utf-8'))['tasks']
                if t['selected_task'] == 'OpsiAshAssist')
    frame = task['failure_observation']
    previous = next(a for a in reversed(task['actions'])
                    if a['semantic_id'] == 'reward/award-info/close')
    b = FakeBackend([])
    b.snapshot = frame['state']['snapshot']
    b.buttons = frame['state']['buttons_snapshot']
    b.ui = frame['ui']['snapshot']
    generation = max(b.snapshot['generation'], b.buttons['generation'], b.ui['generation'])
    for snapshot in (b.snapshot, b.buttons, b.ui):
        snapshot['generation'] = generation
    o = SemanticOracle(b.request, b.foreground_component, b.tap,
        OracleFingerprint(package=b.snapshot['package'], component=b.foreground,
            driver_revision=b.snapshot['driver_revision'], expected_pid=b.snapshot['pid']))
    a = AlasSemanticAdapter(o, package_gate=lambda: None)
    a.begin_meta_assist()
    receipt = SimpleNamespace(**previous)
    if change == 'old_generation':
        receipt.generation = generation
    if change != 'no_receipt':
        a._meta_reward_close_receipt = receipt
    if change == 'owner':
        a._meta_assist_active = False
    if change == 'malformed':
        b.ui['images'] = []
    if change:
        with pytest.raises(SemanticGateClosed):
            a.click(SimpleNamespace(name='GET_ITEMS_1'))
    else:
        assert a.click(SimpleNamespace(name='GET_ITEMS_1')) is receipt
        assert a._meta_reward_close_receipt is None
    assert b.taps == []


@pytest.mark.parametrize('meta_owner', ['assist', 'beacon', None])
def test_shared_session_reward_close_hands_receipt_to_active_meta_owner(meta_owner):
    from tests.test_adapter_session_runtime_handle import FakeRuntimeHandle, REVISION
    session = AlasSemanticSession(driver_revision=REVISION, runtime_handle=FakeRuntimeHandle())
    oracle = FakeOracle()
    oracle.campaign_battle_reward_visible = lambda: True
    oracle.enabled_values['reward/award-info/close'] = True
    oracle.click = Mock(return_value=SimpleNamespace(generation=10, semantic_id='reward/award-info/close'))
    adapter = AlasSemanticAdapter(oracle, package_gate=lambda: None)
    if meta_owner == 'assist':
        adapter.begin_meta_assist()
    elif meta_owner == 'beacon':
        adapter.begin_meta_beacon()
    session.adapter = adapter
    session.open = lambda: adapter
    session._combat_result_action_oracle = lambda _: oracle
    session._arm_combat_result_transition = Mock()
    receipt = session.click(SimpleNamespace(name='GET_ITEMS_1'))
    assert adapter._meta_reward_close_receipt is (receipt if meta_owner else None)
    oracle.click.assert_called_once_with('reward/award-info/close')
