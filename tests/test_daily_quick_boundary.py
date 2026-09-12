import pytest
from alas_headless import SemanticGateClosed
from tests.semantic_support.observer_fixtures import FakeBackend, make_oracle, make_button, make_image, make_text, make_ui
from types import SimpleNamespace
from alas_headless import AlasSemanticAdapter


def test_normal_run_preserves_legacy_observer_without_optional_raycast():
    path = 'OverlayCamera/Overlay/UIMain/selected/stagetpl/quickly/bg/challenge'
    backend = FakeBackend([make_button('challenge', path, raycast_top=None)])
    receipt = make_oracle(backend).click_daily_run_choice('normal')
    assert receipt.semantic_id == 'daily/run/normal'
    assert len(backend.taps) == 1


@pytest.mark.parametrize('raycast', [False, None])
def test_bulk_skip_refuses_unproven_top_hit(raycast):
    path = 'OverlayCamera/Overlay/UIMain/selected/stagetpl/quickly/bg/mult'
    backend = FakeBackend([make_button('mult', path, raycast_top=raycast)])
    with pytest.raises(SemanticGateClosed, match='top-raycast'):
        make_oracle(backend).click_daily_run_choice('skip')
    assert backend.taps == []


def test_bulk_skip_requires_foreground_and_keeps_other_popups_blocking():
    path = 'OverlayCamera/Overlay/UIMain/selected/stagetpl/quickly/bg/mult'
    backend = FakeBackend([make_button('mult', path)])
    oracle = make_oracle(backend)
    oracle._foreground_component = lambda: 'other/package'
    with pytest.raises(SemanticGateClosed, match='foreground|top-resumed'):
        oracle.click_daily_run_choice('skip')
    oracle._foreground_component = lambda: oracle.fingerprint.component
    backend.buttons['buttons'].append(make_button('confirm', 'root/Msgbox(Clone)/window/button_container/custom_button_1(Clone)'))
    backend.buttons['button_count'] += 1
    with pytest.raises(SemanticGateClosed, match='obscured'):
        oracle.click_daily_run_choice('skip')
    assert backend.taps == []


def test_remaining_follows_challenge_identity_after_reordering_and_rejects_duplicates():
    root = 'UICamera/Canvas/UIMain/DailyLevelUI(Clone)/list_panel/list/'
    backend = FakeBackend([])
    backend.ui = make_ui([make_text('0/3', root+'401/count'), make_text('3/3',root+'201/count')],
        images=[make_image(root+'201/icon/card/title','shangchuanhuwei_zi'),
                make_image(root+'401/icon/card/title','zhanshouxingdong_zi')])
    oracle = make_oracle(backend)
    oracle.daily_page_visible = lambda: True
    assert oracle.daily_remaining_for_kind('fierce_assault') == 0
    assert oracle.daily_remaining_for_kind('escort_mission') == 3
    backend.ui['images'].append(dict(backend.ui['images'][-1]))
    backend.ui['image_count'] += 1
    with pytest.raises(SemanticGateClosed, match='ambiguous'):
        oracle.daily_remaining_for_kind('fierce_assault')
    assert backend.taps == []


def test_original_goto_main_can_leave_daily_through_its_reviewed_back_port():
    root = 'UICamera/Canvas/UIMain/DailyLevelUI(Clone)'
    backend = FakeBackend([make_button('back_button', root+'/blur_panel/adapt/top/back_button', raycast_top=None)])
    oracle = make_oracle(backend)
    oracle.daily_page_visible = lambda: True
    adapter = AlasSemanticAdapter(oracle, package_gate=lambda: None)
    assert adapter._goto_main_target() == 'daily/page/back'
    receipt = adapter.click(SimpleNamespace(name='GOTO_MAIN'))
    assert receipt.semantic_id == 'daily/page/back'
    assert len(backend.taps) == 1
