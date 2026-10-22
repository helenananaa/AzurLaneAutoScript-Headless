import time
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from alas_headless import AlasSemanticAdapter, SemanticGateClosed
from tests.semantic_support.adapter_fixtures import FakeOracle


@pytest.mark.parametrize('resource', ['CAMPAIGN_WITHDRAW_CONFIRM', 'GET_MISSION'])
@pytest.mark.parametrize('owned, expired, generation, blocker', [
    (True, False, 11, None), (True, False, 11, 'loading'),
    (True, False, 11, 'tactical-dock'),
    (False, False, 11, None), (True, True, 11, None),
    (True, False, 10, None), (True, False, 11, 'msgbox'),
])
def test_partial_dock_popup_probe_yields_only_after_owned_entry(
        resource, owned, expired, generation, blocker):
    oracle = FakeOracle()
    oracle.meta_character_menu_visible = lambda: False
    oracle.meta_character_sync_page_visible = lambda: False
    oracle.read_state = lambda: SimpleNamespace(generation=generation, buttons=[SimpleNamespace(
        active_in_hierarchy=True, active_and_enabled=True,
        path='OverlayCamera/Overlay/UIMain/blur_panel/adapt/top/index_button')])
    oracle._blocking_rules = lambda *_: ([] if blocker is None else [SimpleNamespace(blocker_id=blocker)])
    oracle._enhancement_dock_records = Mock(side_effect=SemanticGateClosed('partial Dock'))
    host = AlasSemanticAdapter(oracle, package_gate=lambda: None)
    if owned:
        host._main_dock_transition_receipt = SimpleNamespace(generation=10)
    host._main_dock_transition_until = time.monotonic() + (-1 if expired else 12)
    if owned and not expired and generation > 10 and blocker in (None, 'loading', 'tactical-dock'):
        assert host._appear_priority(resource) is False
    else:
        with pytest.raises(SemanticGateClosed):
            host._appear_priority(resource)
    assert oracle.click_calls == []


def test_retained_r6_dock_mount_does_not_block_unrelated_withdraw_probe():
    import json
    from pathlib import Path
    from alas_headless.semantic_oracle import SemanticOracle, OracleFingerprint
    from tests.semantic_support.observer_fixtures import FakeBackend
    path = Path(__file__).resolve().parents[1] / 'artifacts/continuity-20261004/goal-scheduler-r6.json'
    if not path.exists():
        pytest.skip('retained r6 frame unavailable')
    task = json.loads(path.read_text(encoding='utf-8'))['tasks'][-1]
    failed = task['failed_presence']
    backend = FakeBackend([])
    backend.snapshot = failed['state']['snapshot']
    backend.buttons = failed['state']['buttons_snapshot']
    backend.ui = failed['ui']['snapshot']
    oracle = SemanticOracle(backend.request, backend.foreground_component, backend.tap,
        OracleFingerprint(package=backend.snapshot['package'], component=backend.foreground,
            driver_revision=backend.snapshot['driver_revision'], expected_pid=backend.snapshot['pid']))
    host = AlasSemanticAdapter(oracle, package_gate=lambda: None)
    entry = next(action for action in task['actions'] if action['semantic_id'] == 'main/dock')
    host._main_dock_transition_receipt = SimpleNamespace(generation=entry['generation'])
    host._main_dock_transition_until = time.monotonic() + 12
    assert host._appear_priority('CAMPAIGN_WITHDRAW_CONFIRM') is False
    assert backend.taps == []


def test_dock_notice_probe_does_not_hide_actual_urgent_notice():
    oracle = FakeOracle()
    oracle.read_state = lambda: SimpleNamespace(generation=11, buttons=[SimpleNamespace(
        active_in_hierarchy=True, active_and_enabled=True,
        path='OverlayCamera/Overlay/UIMain/blur_panel/adapt/top/index_button')])
    oracle._campaign_urgent_notice_matches = lambda state: True
    host = AlasSemanticAdapter(oracle, package_gate=lambda: None)
    host._main_dock_transition_receipt = SimpleNamespace(generation=10)
    host._main_dock_transition_until = time.monotonic() + 12
    with pytest.raises(SemanticGateClosed, match='urgent commission notice'):
        host._appear_priority('GET_MISSION')
    assert oracle.click_calls == []


def test_retained_r57_awaken_dock_mount_notice_probe_yields_without_input():
    import json
    from pathlib import Path
    from alas_headless.semantic_oracle import SemanticOracle, OracleFingerprint
    from tests.semantic_support.observer_fixtures import FakeBackend
    path = Path(__file__).resolve().parents[1] / 'artifacts/continuity-20261004/goal-scheduler-r57.json'
    if not path.exists():
        pytest.skip('retained r57 frame unavailable')
    task = next(task for task in json.loads(path.read_text(encoding='utf-8'))['tasks']
                if (task.get('task_outcome') or {}).get('task') == 'awaken')
    failed = task['failed_presence']
    assert failed['name'] == 'GET_MISSION'
    backend = FakeBackend([])
    frame = failed['retained_screenshot_at_session_entry']['frame']['projections']
    backend.snapshot = frame['snapshot']
    backend.buttons = frame['buttons']
    backend.ui = frame['ui']
    oracle = SemanticOracle(backend.request, backend.foreground_component, backend.tap,
        OracleFingerprint(package=backend.snapshot['package'], component=backend.foreground,
            driver_revision=backend.snapshot['driver_revision'], expected_pid=backend.snapshot['pid']))
    host = AlasSemanticAdapter(oracle, package_gate=lambda: None)
    entry = next(action for action in task['actions'] if action['semantic_id'] == 'main/dock')
    host._main_dock_transition_receipt = SimpleNamespace(generation=entry['generation'])
    host._main_dock_transition_until = time.monotonic() + 12
    assert host._appear_priority('GET_MISSION') is False
    assert backend.taps == []


@pytest.mark.parametrize('blocker', ['tactical-dock', 'msgbox'])
def test_proven_dock_owns_notice_probe_without_entry_deadline_only_if_unobscured(blocker):
    oracle = FakeOracle()
    oracle.read_state = lambda: SimpleNamespace(generation=11, buttons=[SimpleNamespace(
        active_in_hierarchy=True, active_and_enabled=True,
        path='OverlayCamera/Overlay/UIMain/blur_panel/adapt/top/index_button')])
    oracle._blocking_rules = lambda *_: [SimpleNamespace(blocker_id=blocker)]
    oracle._enhancement_dock_records = lambda: None
    host = AlasSemanticAdapter(oracle, package_gate=lambda: None)
    if blocker == 'tactical-dock':
        assert host.appear('GET_MISSION') is False
    else:
        with pytest.raises(SemanticGateClosed):
            host.appear('GET_MISSION')
    assert oracle.click_calls == []
