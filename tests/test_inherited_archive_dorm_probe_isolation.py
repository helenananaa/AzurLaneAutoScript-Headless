"""Actual inherited pages do not require unrelated task capabilities."""
import pytest
from alas_headless import SemanticGateClosed, AlasSemanticUnmapped
from tests.test_game_tips_loading_presence import host
from tests.semantic_support.observer_fixtures import make_button


@pytest.mark.parametrize('drift', [False, True])
def test_uncovered_archive_allows_native_unknown_page_home_after_other_task(drift):
    backend, _, adapter = host(drift, 'archives-passive-probe-r178.json')
    adapter.begin_research()
    assert adapter.appear('CAMPAIGN_WITHDRAW_CONFIRM') is False
    assert adapter.appear('EXERCISE_CHECK') is False
    assert adapter.appear('GAME_TIPS') is False
    assert adapter._goto_main_target() == 'archive/activity-list/home'
    assert adapter.appear('GOTO_MAIN') is True
    assert not backend.taps


@pytest.mark.parametrize('drift', [False, True])
def test_uncovered_dorm_keeps_main_notices_absent_after_dorm_task(drift):
    backend, _, adapter = host(drift, 'dorm-monthly-notice-r178.json')
    for name in ('MONTHLY_PASS_NOTICE', 'BATTLE_PASS_NOTICE', 'BATTLE_PASS_NEW_SEASON'):
        assert adapter.appear(name) is False
    assert not backend.taps


@pytest.mark.parametrize('case', ['blocked', 'wrong-graphic', 'foreign-package', 'truncated'])
def test_archive_absence_is_not_inferred_from_unproven_home(case):
    backend, _, adapter = host(fixture='archives-passive-probe-r178.json')
    if case == 'blocked':
        backend.buttons['buttons'].append(make_button('custom_button_1(Clone)',
            'root/OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/button_container/custom_button_1(Clone)'))
        backend.buttons['button_count'] += 1
    elif case == 'wrong-graphic':
        next(i for i in backend.ui['images'] if i['path'].endswith('/top/homeBtn'))['sprite'] = 'purchase_button'
    elif case == 'foreign-package': backend.snapshot['package'] = 'unrelated.package'
    else: backend.ui['image_truncated'] = True
    with pytest.raises((SemanticGateClosed, AlasSemanticUnmapped)):
        adapter.appear('CAMPAIGN_WITHDRAW_CONFIRM')
    assert not backend.taps
