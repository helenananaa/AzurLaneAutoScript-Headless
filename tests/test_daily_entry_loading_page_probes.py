"""A captured Daily-entry transition yields page discovery to native ALAS."""
import pytest

from alas_headless import SemanticGateClosed, AlasSemanticUnmapped
from tests.test_game_tips_loading_presence import host
from tests.semantic_support.observer_fixtures import make_button


@pytest.mark.parametrize('resource', ['MAP_PREPARATION', 'FLEET_PREPARATION',
    'RAID_FLEET_PREPARATION', 'AUTO_SEARCH_MENU_EXIT', 'AUTO_SEARCH_REWARD'])
@pytest.mark.parametrize('fixture', ['daily-entry-map-probe-r366.json', 'daily-entry-fleet-probe-r389.json'])
@pytest.mark.parametrize('drift', [False, True])
def test_actual_daily_entry_and_loading_do_not_offer_campaign_preparation(drift, fixture, resource):
    backend, oracle, adapter = host(drift, fixture)
    generation = max(p['generation'] for p in (backend.snapshot, backend.buttons, backend.ui))
    for p in (backend.snapshot, backend.buttons, backend.ui):
        p['generation'] = generation
    assert {r.blocker_id for r in oracle._blocking_rules(oracle.read_state(), 'ui/absence-probe')} == (
        {'loading', 'campaign-menu'} if fixture.endswith('r366.json') else {'daily-page'})
    assert adapter.appear(resource) is False
    assert not backend.taps
    backend.buttons['buttons'].append(make_button('custom_button_1(Clone)',
        'OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/button_container/custom_button_1(Clone)'))
    backend.buttons['button_count'] += 1
    if fixture.endswith('r366.json') and resource == 'MAP_PREPARATION':
        # Preserve the original captured unknown-Msgbox rejection. Other
        # optional probes may already yield to that popup's native owner.
        with pytest.raises((SemanticGateClosed, AlasSemanticUnmapped)):
            adapter.appear(resource)
    with pytest.raises((SemanticGateClosed, AlasSemanticUnmapped)):
        adapter.click(resource)
    assert not backend.taps


@pytest.mark.parametrize('resource', ['GAME_ROOM_CHECK', 'DAILY_CHECK', 'STORAGE_CHECK',
                                     'WITHDRAW', 'CAMPAIGN_WITHDRAW_CONFIRM', 'MAP_PREPARATION'])
@pytest.mark.parametrize('drift', [False, True])
def test_known_menu_under_loading_yields_unrelated_page_probes(resource, drift):
    backend, oracle, adapter = host(drift, 'campaign-menu-loading-r17.json')
    blockers = oracle._blocking_rules(oracle.read_state(), 'ui/absence-probe')
    assert {rule.blocker_id for rule in blockers} == {'loading', 'campaign-menu'}
    assert adapter.appear(resource) is False
    with pytest.raises(SemanticGateClosed):
        oracle.click('campaign-menu/daily')
    assert not backend.taps


@pytest.mark.parametrize('case', ['foreign-popup', 'foreign-package', 'stale'])
def test_loading_does_not_swallow_other_boundary_failures(case):
    backend, oracle, adapter = host(fixture='campaign-menu-loading-r17.json')
    if case == 'foreign-popup':
        backend.buttons['buttons'].append(make_button('custom_button_1(Clone)',
            'OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/button_container/custom_button_1(Clone)'))
        backend.buttons['button_count'] += 1
        assert {r.blocker_id for r in
                oracle._blocking_rules(oracle.read_state(), 'ui/absence-probe')} - {
                    'campaign-menu', 'loading'}
    elif case == 'foreign-package':
        backend.snapshot['package'] = 'unrelated.package'
    else:
        backend.snapshot['age_ms'] = 100000
    if case == 'foreign-package':
        with pytest.raises((SemanticGateClosed, AlasSemanticUnmapped)):
            adapter.appear('GAME_ROOM_CHECK')
    elif case == 'stale':
        # Existing passive discovery may return absence on a stale screenshot;
        # the independent input reader must still reject it.
        with pytest.raises(SemanticGateClosed):
            oracle.read_state()
    with pytest.raises(SemanticGateClosed):
        oracle.click('campaign-menu/daily')
    assert not backend.taps
