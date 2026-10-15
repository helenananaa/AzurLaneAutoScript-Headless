import copy
import json
from pathlib import Path
from unittest.mock import Mock

import pytest
from alas_headless import AlasSemanticAdapter, AlasSemanticSession, AlasSemanticUnmapped, SemanticGateClosed
from alas_headless.adapter.semantic.dispatch_result import UNHANDLED
from alas_headless.semantic_oracle import OracleFingerprint, SemanticOracle
from tests.semantic_support.adapter_cases import AlasSemanticAdapterTestsSupport
from tests.semantic_support.observer_fixtures import FakeBackend, make_button, make_oracle

ROOT='OverlayCamera/Overlay/UIMain/SelectTechnologyUI(Clone)/'


def menu():
    backend=FakeBackend([make_button('back',ROOT+'blur_panel/adapt/top/back'),
                         make_button('technology_btn',ROOT+'frame/bg/technology_btn')])
    adapter=AlasSemanticAdapter(make_oracle(backend),lambda:None,
        frame_identity_provider=AlasSemanticAdapterTestsSupport.frame_identity)
    adapter._frame_observation_oracle=lambda:adapter._live_oracle
    return backend,adapter


@pytest.mark.parametrize('resource',['CAMPAIGN_WITHDRAW_CONFIRM','WITHDRAW','MAP_PREPARATION','FLEET_PREPARATION','RAID_FLEET_PREPARATION','AUTO_SEARCH_MENU_EXIT','AUTO_SEARCH_REWARD'])
def test_unobscured_research_menu_owns_unrelated_passive_campaign_probe(resource):
    backend,adapter=menu()
    backend.buttons['buttons'].reverse()
    backend.snapshot['new_metadata']='compatible additive release'
    assert adapter.appear(resource) is False
    with pytest.raises(SemanticGateClosed):adapter.click(resource)
    assert backend.taps==[]
    assert adapter.appear('RESHMENU_CHECK')


@pytest.mark.parametrize('case',['foreign','stale','duplicate','covered','popup'])
def test_unknown_or_obscured_menu_does_not_hide_withdraw_probe(case):
    backend,adapter=menu()
    if case=='foreign':backend.snapshot['package']='unrelated.package'
    elif case=='stale':backend.snapshot['age_ms']=100000
    elif case=='duplicate':
        backend.buttons['buttons'].append(dict(backend.buttons['buttons'][0]))
        backend.buttons['button_count']+=1
    elif case=='covered':backend.buttons['buttons'][0]['raycast_top']=False
    else:
        backend.buttons['buttons'].append(make_button('custom_button_1(Clone)',
            'OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/button_container/custom_button_1(Clone)'))
        backend.buttons['button_count']+=1
    if case in ('foreign','stale','duplicate'):
        with pytest.raises(SemanticGateClosed):adapter._appear_priority('CAMPAIGN_WITHDRAW_CONFIRM')
    else:
        assert adapter._appear_priority('CAMPAIGN_WITHDRAW_CONFIRM') is UNHANDLED
    with pytest.raises(SemanticGateClosed):adapter.click('CAMPAIGN_WITHDRAW_CONFIRM')
    assert backend.taps==[]


def retained_return_menu():
    path = Path(__file__).resolve().parents[1] / 'artifacts/adapter-fixes-live-20261015/research-menu-return-failure-live.json'
    if not path.exists():
        pytest.skip('retained post-failure research menu unavailable; portable cases remain active')
    payload = json.loads(path.read_text(encoding='utf8'))
    backend = FakeBackend([])
    backend.snapshot = copy.deepcopy(payload['state']['snapshot'])
    backend.buttons = copy.deepcopy(payload['state']['buttons'])
    backend.ui = copy.deepcopy(payload['ui'])
    oracle = SemanticOracle(backend.request, backend.foreground_component, backend.tap,
        OracleFingerprint(package=backend.snapshot['package'], component=backend.foreground,
            driver_revision=backend.snapshot['driver_revision'], expected_pid=backend.snapshot['pid']),
        sleep=lambda _: None)
    adapter = AlasSemanticAdapter(oracle, lambda: None)
    adapter._frame_observation_oracle = lambda: oracle
    return backend, oracle, adapter


def test_retained_post_failure_menu_already_classifies_unowned_withdraw_absent():
    # This is the observed settled destination, not the uncaptured earlier
    # screenshot that raised the original unknown-page exception.
    backend, oracle, adapter = retained_return_menu()
    assert oracle.read_state().generation == 7049
    assert oracle.enabled('research-menu/page/back')
    assert [rule.blocker_id for rule in oracle._blocking_rules(
        oracle.read_state(), 'ui/absence-probe')] == ['research-menu']
    assert adapter.appear('CAMPAIGN_WITHDRAW_CONFIRM') is False
    with pytest.raises(SemanticGateClosed):
        adapter.click('CAMPAIGN_WITHDRAW_CONFIRM')
    assert not backend.taps


@pytest.mark.parametrize('destination', ['portable-menu', 'retained-menu', 'foreign-modal', 'active-campaign'])
def test_session_existing_single_refresh_reclassifies_only_unowned_menu(destination):
    if destination == 'portable-menu':
        backend, adapter = menu()
        oracle = adapter.oracle
    else:
        backend, oracle, adapter = retained_return_menu()
    if destination == 'foreign-modal':
        backend.buttons['buttons'].append(make_button('custom_button_1(Clone)',
            'OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/button_container/custom_button_1(Clone)'))
        backend.buttons['button_count'] += 1
    if destination == 'active-campaign':
        adapter.begin_campaign_pre_sortie('12-4')
    session = AlasSemanticSession(serial='offline-test', driver_revision=oracle.fingerprint.driver_revision)
    session.adapter = adapter
    session.open = lambda: adapter
    session.refresh_frame = Mock()
    original = adapter.appear

    def classify(button):
        if adapter.appear.call_count == 1:
            # Controlled transition: the initial unknown screenshot was not
            # retained in the live receipt. Its existing classified exception
            # is followed by the independently retained menu on one refresh.
            raise AlasSemanticUnmapped('unmapped during native page return')
        return original(button)

    adapter.appear = Mock(side_effect=classify)
    if destination in ('portable-menu', 'retained-menu'):
        assert session.appear('CAMPAIGN_WITHDRAW_CONFIRM') is False
        assert adapter.appear.call_count == 2
    else:
        with pytest.raises((AlasSemanticUnmapped, SemanticGateClosed)):
            session.appear('CAMPAIGN_WITHDRAW_CONFIRM')
        assert adapter.appear.call_count == 1
    session.refresh_frame.assert_called_once()
    assert not backend.taps and not backend.swipes


@pytest.mark.parametrize('case', ['known-loading', 'foreign-modal', 'active-campaign'])
def test_loading_owns_only_unowned_passive_withdraw_probe(case):
    backend = FakeBackend([make_button('Loading(Clone)',
        'OverlayCamera/Overlay/UIOverlay/Loading(Clone)')])
    adapter = AlasSemanticAdapter(make_oracle(backend), lambda: None)
    if case == 'foreign-modal':
        backend.buttons['buttons'].append(make_button('custom_button_1(Clone)',
            'OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/button_container/custom_button_1(Clone)'))
        backend.buttons['button_count'] += 1
    if case == 'active-campaign':
        adapter.begin_campaign_pre_sortie('12-4')
    expected = False if case == 'known-loading' else UNHANDLED
    assert adapter._appear_priority('CAMPAIGN_WITHDRAW_CONFIRM') is expected
    with pytest.raises(SemanticGateClosed):
        adapter.click('CAMPAIGN_WITHDRAW_CONFIRM')
    assert not backend.taps


def test_real_inherited_withdraw_confirmation_retains_its_positive_probe():
    from tests.test_inherited_campaign_withdraw import retained_prompt
    backend = retained_prompt()
    adapter = AlasSemanticAdapter(make_oracle(backend), lambda: None)
    assert adapter.appear('CAMPAIGN_WITHDRAW_CONFIRM') is True
    assert not backend.taps
