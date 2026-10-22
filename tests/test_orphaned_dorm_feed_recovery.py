"""A ended task's Feed panel has a reviewed native unknown-page return."""
import copy
import pytest
from alas_headless import SemanticGateClosed, AlasSemanticUnmapped, AlasSemanticSession
from tests.test_game_tips_loading_presence import host
from tests.semantic_support.observer_fixtures import make_button


@pytest.mark.parametrize('drift', [False, True])
def test_native_home_recovery_exposes_only_the_existing_feed_close(drift):
    backend, _, adapter = host(drift, 'dorm-feed-orphan-r187.json')
    assert adapter.appear('GOTO_MAIN') is True
    assert adapter.appear('GOTO_MAIN_WHITE') is False
    assert adapter.appear('RPG_HOME') is False
    assert adapter.appear('DORM_CHECK') is False
    receipt = adapter.click('GOTO_MAIN')
    assert receipt.semantic_id == 'dorm/feed/close'
    assert len(backend.taps) == 1
    assert adapter._dorm_context is None


def test_unrelated_food_counter_failure_does_not_disable_close():
    backend, _, adapter = host(fixture='dorm-feed-orphan-r187.json')
    backend.ui['texts'] = []
    assert adapter.appear('GOTO_MAIN') is True
    assert adapter.click('GOTO_MAIN').semantic_id == 'dorm/feed/close'
    assert len(backend.taps) == 1


@pytest.mark.parametrize('case', ['foreign-package', 'duplicate-close', 'foreign-modal'])
def test_orphaned_close_keeps_genuine_input_boundary(case):
    backend, _, adapter = host(fixture='dorm-feed-orphan-r187.json')
    if case == 'foreign-package': backend.snapshot['package'] = 'unrelated.package'
    elif case == 'duplicate-close':
        backend.buttons['buttons'].append(copy.deepcopy(next(b for b in backend.buttons['buttons']
            if b['path'].endswith('BackYardFeedUI(Clone)/close'))))
        backend.buttons['button_count'] += 1
    else:
        backend.buttons['buttons'].append(make_button('custom_button_1(Clone)',
            'root/Msgbox(Clone)/window/button_container/custom_button_1(Clone)'))
        backend.buttons['button_count'] += 1
    with pytest.raises((SemanticGateClosed, AlasSemanticUnmapped)):
        adapter.click('GOTO_MAIN')
    assert not backend.taps


@pytest.mark.parametrize('case', ['complete-return', 'foreign-modal'])
def test_existing_refresh_reclassifies_campaign_probe_after_feed_unmount(case):
    before_backend, _, before = host(fixture='dorm-feed-unmount-r188.json')
    backend, _, after = host(fixture='dorm-feed-return-r188.json')
    if case == 'foreign-modal':
        backend.buttons['buttons'].append(make_button('custom_button_1(Clone)',
            'root/Msgbox(Clone)/window/button_container/custom_button_1(Clone)'))
        backend.buttons['button_count'] += 1
    session = AlasSemanticSession.__new__(AlasSemanticSession)
    current, refreshes = [before], []
    session.open = lambda: current[0]
    def refresh():
        refreshes.append(True)
        current[0] = after
    session.refresh_frame = refresh
    if case == 'complete-return':
        assert session.appear('CAMPAIGN_WITHDRAW_CONFIRM') is False
        assert after.appear('DORM_CHECK') is True
    else:
        with pytest.raises((SemanticGateClosed, AlasSemanticUnmapped)):
            session.appear('CAMPAIGN_WITHDRAW_CONFIRM')
    assert len(refreshes) == 1
    assert not backend.taps and not before_backend.taps


@pytest.mark.parametrize('drift', [False, True])
def test_completed_return_owns_unrelated_native_popup_probes(drift):
    backend, _, adapter = host(drift, 'dorm-feed-return-r188.json')
    assert adapter.appear('DORM_CHECK') is True
    for name in ('POPUP_SINGLE_WHITE', 'GAME_TIPS', 'DORM_TROPHY_CONFIRM',
                 'DORM_INFO', 'MEOWFFICER_INFO', 'MEOWFFICER_BUY',
                 'MAP_PREPARATION', 'FLEET_PREPARATION', 'RAID_FLEET_PREPARATION',
                 'AUTO_SEARCH_MENU_EXIT', 'AUTO_SEARCH_REWARD', 'WITHDRAW'):
        assert adapter.appear(name) is False, name
    with pytest.raises((SemanticGateClosed, AlasSemanticUnmapped)):
        adapter.click('POPUP_SINGLE_WHITE')
    assert not backend.taps
