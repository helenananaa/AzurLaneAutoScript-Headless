import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from alas_headless import AlasSemanticAdapter, SemanticGateClosed, SemanticTargetMissing
from alas_headless.semantic_oracle import SemanticOracle, OracleFingerprint
from tests.semantic_support.adapter_fixtures import FakeOracle
from tests.semantic_support.observer_fixtures import FakeBackend, make_button
from alas_headless.adapter.semantic.dispatch_result import UNHANDLED


def retained_task(name):
    path = Path(__file__).resolve().parents[1] / 'artifacts/continuity-20261004/goal-scheduler-r29.json'
    if not path.exists():
        pytest.skip('retained r29 frame unavailable')
    return next(t for t in json.loads(path.read_text(encoding='utf-8'))['tasks'] if t['selected_task'] == name)


def oracle_for(snapshot, buttons, ui):
    b = FakeBackend([])
    b.snapshot, b.buttons, b.ui = snapshot, buttons, ui
    generation = max(s['generation'] for s in (snapshot, buttons, ui))
    for item in (snapshot, buttons, ui):
        item['generation'] = generation
    o = SemanticOracle(b.request, b.foreground_component, b.tap,
        OracleFingerprint(package=snapshot['package'], component=b.foreground,
            driver_revision=snapshot['driver_revision'], expected_pid=snapshot['pid']))
    return b, o


def test_actual_menu_back_return_is_acknowledged_once_on_newer_unobscured_main():
    t = retained_task('Main')
    f = t['failure_observation']
    b, o = oracle_for(f['state']['snapshot'], f['state']['buttons_snapshot'], f['ui']['snapshot'])
    a = AlasSemanticAdapter(o, package_gate=lambda: None)
    prior = SimpleNamespace(**next(x for x in t['actions'] if x['semantic_id'] == 'research-menu/page/back'))
    a._record_mission_transition(prior)
    assert a._click_mapped('RESHMENU_GOTO_MAIN', 'research-menu/page/back') is prior
    with pytest.raises(SemanticGateClosed):
        a._click_mapped('RESHMENU_GOTO_MAIN', 'research-menu/page/back')
    assert b.taps == []


@pytest.mark.parametrize('case', ['ready', 'no_receipt', 'old_generation', 'foreign', 'source_present', 'unknown', 'reset'])
def test_menu_return_only_consumes_its_accepted_receipt_on_proven_main(case):
    o = FakeOracle()
    o.main_page_visible = lambda: case != 'unknown'
    o.observation_target_present = lambda target: target == 'research-menu/page/back' and case == 'source_present'
    o.read_state = lambda: SimpleNamespace(generation=10 if case == 'old_generation' else 11)
    o.blocking_rules = (SimpleNamespace(blocker_id='foreign'),) if case == 'foreign' else ()
    o.click = Mock(side_effect=SemanticTargetMissing('source absent'))
    a = AlasSemanticAdapter(o, package_gate=lambda: None)
    a._goto_main_target = lambda: None
    prior = SimpleNamespace(generation=10, semantic_id='research-menu/page/back')
    if case != 'no_receipt':
        a._record_mission_transition(prior)
    if case == 'reset':
        a.reset_task_state()
    invoke = lambda: a._click_mapped('RESHMENU_GOTO_MAIN', 'research-menu/page/back')
    if case == 'ready':
        assert invoke() is prior
        o.click.assert_not_called()
        assert a._research_back_receipt is None
    else:
        with pytest.raises(SemanticGateClosed):
            invoke()


def test_shared_home_edge_consumes_the_same_menu_return_receipt():
    o = FakeOracle()
    o.main_page_visible = lambda: True
    o.observation_target_present = lambda target: False
    o.read_state = lambda: SimpleNamespace(generation=11)
    o.click = Mock(side_effect=AssertionError('completed edge must not send input'))
    a = AlasSemanticAdapter(o, package_gate=lambda: None)
    a._goto_main_target = lambda: None
    prior = SimpleNamespace(generation=10, semantic_id='research-menu/page/back')
    a._record_mission_transition(prior)
    assert a._click_main('GOTO_MAIN', None) is prior
    assert a._research_back_receipt is None
    o.click.assert_not_called()


@pytest.mark.parametrize('input_started', [False, True])
def test_menu_destination_mount_between_check_and_dispatch_consumes_only_without_new_input(input_started):
    o = FakeOracle()
    o.main_page_visible = Mock(side_effect=[False, True])
    o.observation_target_present = lambda target: False
    o.read_state = lambda: SimpleNamespace(generation=11)
    o.input_dispatch_count = 0
    def missing(target):
        if input_started:
            o.input_dispatch_count += 1
        raise SemanticTargetMissing('source unmounted during revalidation')
    o.click = Mock(side_effect=missing)
    a = AlasSemanticAdapter(o, package_gate=lambda: None)
    prior = SimpleNamespace(generation=10, semantic_id='research-menu/page/back')
    a._record_mission_transition(prior)
    if input_started:
        with pytest.raises(SemanticTargetMissing):
            a._click_mapped('RESHMENU_GOTO_MAIN', 'research-menu/page/back')
        assert a._research_back_receipt is prior
    else:
        assert a._click_mapped('RESHMENU_GOTO_MAIN', 'research-menu/page/back') is prior
        assert a._research_back_receipt is None


@pytest.mark.parametrize('frame_source', ['entry', 'after_refresh'])
@pytest.mark.parametrize('foreign', [False, True])
def test_actual_meta_ship_probe_is_passive_absence_only_on_unobscured_known_owner(frame_source, foreign):
    f = retained_task('ShopOnce')['failed_presence']
    key = 'retained_screenshot_at_session_entry' if frame_source == 'entry' else 'retained_screenshot_before_diagnostic_reads'
    p = f[key]['frame']['projections']
    b, o = oracle_for(p['snapshot'], p['buttons'], p['ui'])
    if foreign:
        b.buttons['buttons'].append(make_button('confirm',
            'OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/button_container/custom_button_1(Clone)'))
        b.buttons['button_count'] += 1
    a = AlasSemanticAdapter(o, package_gate=lambda: None)
    assert a._appear_priority('GET_SHIP') is (UNHANDLED if foreign else False)
    with pytest.raises(SemanticGateClosed):
        a.click(SimpleNamespace(name='GET_SHIP'))
    assert b.taps == []
