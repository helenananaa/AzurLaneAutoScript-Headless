import json
from pathlib import Path
from types import SimpleNamespace
import pytest
from alas_headless import AlasSemanticAdapter, SemanticGateClosed
from alas_headless.adapter.semantic.dispatch_result import UNHANDLED
from alas_headless.semantic_oracle import SemanticOracle, OracleFingerprint
from tests.semantic_support.observer_fixtures import FakeBackend, make_button, make_oracle


@pytest.mark.parametrize('foreign', [False, True])
@pytest.mark.parametrize('name', ['GET_ITEMS_1', 'GET_ITEMS_2', 'GET_ITEMS_3'])
def test_main_reward_absence_is_resolved_before_unrelated_task_readers(monkeypatch, foreign, name):
    path = Path(__file__).resolve().parents[1] / 'artifacts/continuity-20261004/goal-scheduler-r13.json'
    if not path.exists():
        pytest.skip('retained r13 frame unavailable')
    data = json.loads(path.read_text(encoding='utf-8'))
    frame = next(t for t in data['tasks'] if t['selected_task'] == 'Daily')['failed_presence']
    backend = FakeBackend([])
    backend.snapshot = frame['state']['snapshot']
    backend.buttons = frame['state']['buttons_snapshot']
    backend.ui = frame['ui']['snapshot']
    if foreign:
        backend.buttons['buttons'].append(make_button('confirm',
            'OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/button_container/custom_button_1(Clone)'))
        backend.buttons['button_count'] += 1
    frozen = SemanticOracle(backend.request, backend.foreground_component, backend.tap,
        OracleFingerprint(package=backend.snapshot['package'], component=backend.foreground,
            driver_revision=backend.snapshot['driver_revision'], expected_pid=backend.snapshot['pid']))
    # The passive answer belongs to the leased screenshot. An unrelated task
    # reader must not run after that owner already proves reward absence.
    live = FakeBackend([])
    a = AlasSemanticAdapter(make_oracle(live), package_gate=lambda: None)
    monkeypatch.setattr(a, '_frame_or_live_observation_oracle', lambda: frozen)
    if foreign:
        assert a._appear_priority(name) is UNHANDLED
    else:
        def unrelated_reader(*args):
            pytest.fail('proven main-page absence reached unrelated task reader')
        monkeypatch.setattr(a, '_appear_campaign_stage', unrelated_reader)
        assert a._appear_priority(name) is False
        assert not a.appear(SimpleNamespace(name=name))
    assert backend.taps == [] and live.taps == []


@pytest.mark.parametrize('task', ['Exercise', 'Guild'])
@pytest.mark.parametrize('foreign', [False, True])
def test_retained_r9_passive_page_does_not_require_unrelated_popup_mapping(task, foreign):
    path = Path(__file__).resolve().parents[1] / 'artifacts/continuity-20261004/goal-scheduler-r9.json'
    if not path.exists():
        pytest.skip('retained r9 frame unavailable')
    data = json.loads(path.read_text(encoding='utf-8'))
    frame = next(t for t in data['tasks'] if t['selected_task'] == task)['failed_presence']
    backend = FakeBackend([])
    backend.snapshot = frame['state']['snapshot']
    backend.buttons = frame['state']['buttons_snapshot']
    backend.ui = frame['ui']['snapshot']
    if foreign:
        backend.buttons['buttons'].append(make_button('confirm',
            'OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/button_container/custom_button_1(Clone)'))
        backend.buttons['button_count'] += 1
    oracle = SemanticOracle(backend.request, backend.foreground_component, backend.tap,
        OracleFingerprint(package=backend.snapshot['package'], component=backend.foreground,
            driver_revision=backend.snapshot['driver_revision'], expected_pid=backend.snapshot['pid']))
    a = AlasSemanticAdapter(oracle, package_gate=lambda: None)
    outcome = a._appear_priority(frame['name'])
    assert outcome is (UNHANDLED if foreign else False)
    if not foreign:
        assert not a.appear(SimpleNamespace(name=frame['name']))
    assert backend.taps == []


@pytest.mark.parametrize('foreign', [False, True])
def test_generic_ship_reward_probe_waits_behind_loading_without_admitting_ship_input(foreign):
    buttons = [make_button('Loading(Clone)', 'OverlayCamera/Overlay/UIOverlay/Loading(Clone)')]
    if foreign:
        buttons.append(make_button('confirm',
            'OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/button_container/custom_button_1(Clone)'))
    backend = FakeBackend(buttons)
    a = AlasSemanticAdapter(make_oracle(backend), package_gate=lambda: None)
    assert a._appear_priority('GET_SHIP') is (UNHANDLED if foreign else False)
    with pytest.raises(SemanticGateClosed):
        a.click(SimpleNamespace(name='GET_SHIP'))
    assert backend.taps == []


def test_retained_shop_probe_uses_the_actual_loading_frame_without_claiming_purchase_exhaustion():
    path = Path(__file__).resolve().parents[1] / 'artifacts/continuity-20261004/goal-scheduler-r11.json'
    if not path.exists():
        pytest.skip('retained r11 frame unavailable')
    row = next(t for t in json.loads(path.read_text(encoding='utf-8'))['tasks'] if t['command']=='shop_frequent')
    frame = row['failed_presence']
    assert frame['name'] == 'GET_SHIP'
    assert 'outside mission flow' in row['native_error']['message']
    backend = FakeBackend([])
    backend.snapshot = frame['state']['snapshot']
    backend.buttons = frame['state']['buttons_snapshot']
    backend.ui = frame['ui']['snapshot']
    oracle = SemanticOracle(backend.request, backend.foreground_component, backend.tap,
        OracleFingerprint(package=backend.snapshot['package'], component=backend.foreground,
            driver_revision=backend.snapshot['driver_revision'], expected_pid=backend.snapshot['pid']))
    a = AlasSemanticAdapter(oracle, package_gate=lambda: None)
    assert not a.appear(SimpleNamespace(name='GET_SHIP'))
    assert backend.taps == []


@pytest.mark.parametrize('foreign', [False, True])
def test_retained_daily_ship_probe_resolves_only_unobscured_navigation_absence(foreign):
    from unittest.mock import Mock
    path = Path(__file__).resolve().parents[1] / 'artifacts/continuity-20261004/goal-scheduler-r15.json'
    if not path.exists():
        pytest.skip('retained r15 frame unavailable')
    row = next(t for t in json.loads(path.read_text(encoding='utf-8'))['tasks'] if t['selected_task'] == 'Daily')
    frame = row['failed_presence']
    assert frame['name'] == 'GET_SHIP'
    backend = FakeBackend([])
    backend.snapshot = frame['state']['snapshot']
    backend.buttons = frame['state']['buttons_snapshot']
    backend.ui = frame['ui']['snapshot']
    if foreign:
        backend.buttons['buttons'].append(make_button('confirm',
            'OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/button_container/custom_button_1(Clone)'))
        backend.buttons['button_count'] += 1
    oracle = SemanticOracle(backend.request, backend.foreground_component, backend.tap,
        OracleFingerprint(package=backend.snapshot['package'], component=backend.foreground,
            driver_revision=backend.snapshot['driver_revision'], expected_pid=backend.snapshot['pid']))
    a = AlasSemanticAdapter(oracle, package_gate=lambda: None)
    oracle.campaign_menu_is_entry = Mock(wraps=oracle.campaign_menu_is_entry)
    assert a._appear_priority('GET_SHIP') is False
    # The new atomic absence handles only the unobscured owner. A foreign
    # modal reaches the pre-existing generic navigation/reward dispatch;
    # that dispatch may also answer False, and still authorizes no input.
    assert oracle.campaign_menu_is_entry.call_count == (1 if foreign else 0)
    with pytest.raises(SemanticGateClosed):
        a.click(SimpleNamespace(name='GET_SHIP'))
    assert backend.taps == []


@pytest.mark.parametrize('name', ['GET_ITEMS_1', 'CAMPAIGN_WITHDRAW_CONFIRM', 'UNKNOWN_RESOURCE'])
@pytest.mark.parametrize('destination', ['main', 'unknown'])
def test_session_unmapped_refresh_reclassifies_restored_main_without_input(name, destination):
    from unittest.mock import Mock
    from alas_headless import AlasSemanticSession
    from alas_headless.adapter.semantic.contracts import AlasSemanticUnmapped
    from tests.test_adapter_session_runtime_handle import FakeRuntimeHandle, REVISION
    path = Path(__file__).resolve().parents[1] / 'artifacts/continuity-20261004/goal-scheduler-r26.json'
    if not path.exists():
        pytest.skip('retained r26 frame unavailable')
    task = next(t for t in json.loads(path.read_text(encoding='utf-8'))['tasks']
                if t['selected_task'] == 'Daily')
    projections = task['failed_presence']['retained_screenshot_before_diagnostic_reads']['frame']['projections']
    backend = FakeBackend([])
    backend.snapshot = projections['snapshot']
    backend.buttons = projections['buttons']
    backend.ui = projections['ui']
    oracle = SemanticOracle(backend.request, backend.foreground_component, backend.tap,
        OracleFingerprint(package=backend.snapshot['package'], component=backend.foreground,
            driver_revision=backend.snapshot['driver_revision'], expected_pid=backend.snapshot['pid']))
    adapter = AlasSemanticAdapter(oracle, package_gate=lambda: None)
    adapter._frame_observation_oracle = lambda: oracle
    session = AlasSemanticSession(driver_revision=REVISION, runtime_handle=FakeRuntimeHandle())
    session.adapter = adapter
    session.open = lambda: adapter
    session.refresh_frame = Mock()
    if destination == 'unknown':
        oracle.main_page_visible = lambda: False
    original = adapter.appear
    def classify(button):
        if adapter.appear.call_count == 1 or name == 'UNKNOWN_RESOURCE':
            raise AlasSemanticUnmapped('unmapped during owner transition')
        return original(button)
    adapter.appear = Mock(side_effect=classify)
    if destination == 'main' and name != 'UNKNOWN_RESOURCE':
        assert session.appear(SimpleNamespace(name=name)) is False
        assert adapter.appear.call_count == 2
    else:
        with pytest.raises(AlasSemanticUnmapped):
            session.appear(SimpleNamespace(name=name))
    session.refresh_frame.assert_called_once()
    assert backend.taps == []
