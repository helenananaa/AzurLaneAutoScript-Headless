from unittest.mock import Mock
import pytest
from alas_headless.oracle.campaign_map import CampaignMapOracle
from alas_headless.semantic_oracle import SemanticGateClosed
from alas_headless import AlasSemanticAdapter
from tests.semantic_support.adapter_fixtures import FakeOracle
from types import SimpleNamespace
import time
from alas_headless.adapter.semantic.dispatch_result import UNHANDLED


def non_map_oracle():
    oracle = Mock()
    oracle.read_state.return_value = SimpleNamespace(buttons=())
    oracle._retry_transition_read.side_effect = lambda reader: reader()
    for name in ('meta_page_visible', 'meta_character_menu_visible', 'meta_character_page_visible'):
        getattr(oracle, name).return_value = False
    return oracle


def test_ready_opsi_globe_returns_non_campaign_without_input():
    oracle = non_map_oracle()
    oracle.campaign_map_entry_state.side_effect = SemanticGateClosed('map entry absent')
    oracle.daily_battle_result_visible.return_value = False
    oracle.operation_siren_globe_visible.return_value = True
    assert CampaignMapOracle.campaign_is_in_map(oracle) is False
    oracle.operation_siren_globe_visible.assert_not_called()
    oracle._tap.assert_not_called()


def test_complete_non_map_surface_needs_no_other_task_allowlist():
    oracle = non_map_oracle()
    oracle.campaign_map_entry_state.side_effect = SemanticGateClosed('map entry absent')
    oracle.daily_battle_result_visible.return_value = False
    oracle.operation_siren_globe_visible.return_value = False
    oracle.retirement_selection_visible.return_value = False
    oracle.enhancement_dock_visible.return_value = False
    oracle._matches.return_value = ()
    assert CampaignMapOracle.campaign_is_in_map(oracle) is False
    oracle._paired_ui_after_state.assert_not_called()
    oracle._tap.assert_not_called()


def test_non_map_probe_is_independent_of_optional_shop_parser():
    oracle = non_map_oracle()
    oracle.campaign_map_entry_state.side_effect = SemanticGateClosed('map entry absent')
    oracle.daily_battle_result_visible.return_value = False
    oracle.operation_siren_globe_visible.return_value = False
    oracle.retirement_selection_visible.return_value = False
    oracle.enhancement_dock_visible.return_value = False
    oracle._matches.side_effect = lambda state, target: (object(),) if target == 'shop/home' else ()
    oracle.recommendation_shop_visible.return_value = True
    assert CampaignMapOracle.campaign_is_in_map(oracle) is False
    oracle.recommendation_shop_visible.side_effect = AssertionError('unrelated capability')
    assert CampaignMapOracle.campaign_is_in_map(oracle) is False
    oracle.recommendation_shop_visible.assert_not_called()
    oracle._tap.assert_not_called()


@pytest.mark.parametrize('error', ['observer snapshot is stale', 'Button snapshot is truncated'])
def test_map_absence_does_not_hide_invalid_button_frames(error):
    oracle = non_map_oracle()
    oracle.read_state.side_effect = SemanticGateClosed(error)
    with pytest.raises(SemanticGateClosed, match=error):
        CampaignMapOracle.campaign_is_in_map(oracle)
    oracle._tap.assert_not_called()


def test_active_map_root_still_requires_complete_map_identity():
    oracle = non_map_oracle()
    oracle.read_state.return_value = SimpleNamespace(buttons=(SimpleNamespace(
        path='LevelCamera/Canvas/UIMain/LevelGrid/DragLayer/op1/retreat',
        active_in_hierarchy=True, active_and_enabled=True),))
    oracle._campaign_map_entry_state_from_snapshots.side_effect = SemanticGateClosed('incomplete map')
    with pytest.raises(SemanticGateClosed, match='incomplete map'):
        CampaignMapOracle.campaign_is_in_map(oracle)
    oracle._tap.assert_not_called()


def test_native_home_recovery_uses_one_exact_globe_return_edge():
    oracle = FakeOracle()
    host = AlasSemanticAdapter(oracle, package_gate=lambda: None)
    host._goto_main_target = Mock(return_value='os/globe/map')
    receipt = SimpleNamespace(semantic_id='os/globe/map', generation=10)
    oracle.click_operation_siren_globe_map = Mock(return_value=receipt)
    assert host._click_main('GOTO_MAIN', None) is receipt
    oracle.click_operation_siren_globe_map.assert_called_once_with()
    assert host._operation_siren_page_remount_until > time.monotonic()


@pytest.mark.parametrize('name', ['GET_ITEMS_1', 'GET_ITEMS_2', 'GET_ITEMS_3', 'GET_SHIP'])
def test_dorm_return_absence_does_not_admit_reward_input(name):
    oracle = FakeOracle()
    host = AlasSemanticAdapter(oracle, package_gate=lambda: None)
    host._dorm_return_transition_until = time.monotonic() + 1
    assert host._appear_priority(name) is False
    with pytest.raises((SemanticGateClosed, RuntimeError)):
        host.click(name)
    assert oracle.click_calls == []
    oracle.blocking_rules = (SimpleNamespace(blocker_id='award-info'),)
    assert host._appear_priority(name) is UNHANDLED
    oracle.blocking_rules = ()
    host._dorm_return_transition_until = 0
    assert host._appear_priority(name) is UNHANDLED


def test_tactical_home_uses_only_actionable_unique_mapped_back():
    oracle = FakeOracle()
    host = AlasSemanticAdapter(oracle, package_gate=lambda: None)
    oracle.observation_target_present = lambda name: name == 'tactical/page/back'
    oracle.enabled_values['tactical/page/back'] = True
    assert host._goto_main_target() == 'tactical/page/back'
    oracle.enabled_values['tactical/page/back'] = False
    assert host._goto_main_target() is None
    assert oracle.click_calls == []


@pytest.mark.parametrize('sortie', [None, object()])
def test_inherited_opsi_is_not_resumed_as_campaign_sortie(sortie):
    oracle = FakeOracle()
    host = AlasSemanticAdapter(oracle, package_gate=lambda: None)
    host._campaign_context = SimpleNamespace(sortie_receipt=sortie)
    host._operation_siren_allows_passive_probe = Mock(return_value=True)
    oracle.operation_siren_local_map_visible = Mock(return_value=True)
    host.campaign_dock_full_visible = Mock(side_effect=AssertionError('unrelated campaign capability'))
    # A retained campaign receipt cannot make the current OpSi map a
    # campaign map. The fresh typed owner determines this observation.
    assert host._appear_priority('IN_MAP') is False
    host.campaign_dock_full_visible.assert_not_called()


@pytest.mark.parametrize('change', [None, 'metadata', 'ambiguous', 'unknown'])
def test_retained_meta_sync_owner_returns_non_campaign_without_claiming_any_input(change):
    import json
    import copy
    from pathlib import Path
    from alas_headless.semantic_oracle import SemanticOracle, OracleFingerprint
    from tests.semantic_support.observer_fixtures import FakeBackend
    path = Path(__file__).resolve().parents[1] / 'artifacts/continuity-20261004/goal-scheduler-r28.json'
    if not path.exists():
        pytest.skip('retained r28 frame unavailable')
    task = next(t for t in json.loads(path.read_text(encoding='utf-8'))['tasks']
                if t['selected_task'] == 'Main')
    frame = task['failure_observation']
    b = FakeBackend([])
    b.snapshot = frame['state']['snapshot']
    b.buttons = frame['state']['buttons_snapshot']
    b.ui = frame['ui']['snapshot']
    # The live diagnostic endpoints are coherent but one generation apart.
    # Freeze this captured shape at their newest generation so replaying an
    # older state endpoint cannot move the fake clock backwards after UI.
    assert b.snapshot['generation'] <= b.ui['generation'] <= b.snapshot['generation'] + 2
    generation = max(s['generation'] for s in (b.snapshot, b.buttons, b.ui))
    for snapshot in (b.snapshot, b.buttons, b.ui):
        snapshot['generation'] = generation
    if change == 'metadata':
        b.buttons['compatible_optional_field'] = {'unrelated': True}
        b.buttons['buttons'].reverse()
        b.ui['images'].reverse()
        b.ui['texts'].reverse()
    elif change == 'ambiguous':
        controls = [button for button in b.buttons['buttons']
                    if '/MetaCharacterSynUI(Clone)/TaskPanel/BtnGet' in button['path']]
        assert len(controls) == 1
        b.buttons['buttons'].append(copy.deepcopy(controls[0]))
        b.buttons['button_count'] += 1
    elif change == 'unknown':
        b.buttons['buttons'] = []
        b.buttons['button_count'] = 0
    o = SemanticOracle(b.request, b.foreground_component, b.tap,
        OracleFingerprint(package=b.snapshot['package'], component=b.foreground,
            driver_revision=b.snapshot['driver_revision'], expected_pid=b.snapshot['pid']))
    adapter = AlasSemanticAdapter(o, package_gate=lambda: None)
    assert adapter.appear(SimpleNamespace(name='IN_MAP')) is False
    if change in ('ambiguous', 'unknown'):
        # Local map absence must not weaken the unrelated action's contract.
        with pytest.raises(SemanticGateClosed):
            o.click_meta_character_sync_rewards()
    assert b.taps == []
