"""Regression coverage for the Campaign HP and original withdrawal boundary."""


import pytest

from alas_headless import AlasSemanticAdapter, SemanticGateClosed
from alas_headless.adapter.semantic.contracts import _CampaignFlowContext
from tests.semantic_support.observer_fixtures import (
    FakeBackend, make_button, make_image, make_oracle, make_text, make_ui,
)
from tests.semantic_support.fake_oracle import FakeOracle

ROOT = 'OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/'
RETREAT = 'OverlayCamera/Overlay/UIMain/top/LevelStageView(Clone)/bottom_stage/Normal/retreat_button'


def withdrawal_oracle(confirm=False, raycast=True):
    path = ROOT + 'button_container/custom_button_1(Clone)' if confirm else RETREAT
    button = make_button('confirm' if confirm else 'retreat_button', path,
                         raycast_top=raycast)
    backend = FakeBackend([button])
    backend.ui = make_ui(texts=[
        make_text('真的要撤退吗？', ROOT + 'msg_panel/content')
    ] if confirm else [])
    oracle = make_oracle(backend)
    oracle.campaign_is_in_map = lambda: not confirm
    return backend, oracle


@pytest.mark.parametrize('confirm', [False, True])
def test_withdrawal_has_exact_single_typed_target(confirm):
    backend, oracle = withdrawal_oracle(confirm)
    receipt = oracle.click_campaign_withdraw(confirm=confirm)
    assert receipt.semantic_id.endswith('/confirm' if confirm else '/open')
    assert len(backend.taps) == 1


@pytest.mark.parametrize('raycast', [None, False])
@pytest.mark.parametrize('confirm', [False, True])
def test_withdrawal_never_accepts_unproven_top_target(confirm, raycast):
    backend, oracle = withdrawal_oracle(confirm, raycast)
    with pytest.raises(SemanticGateClosed, match='not actionable'):
        oracle.click_campaign_withdraw(confirm=confirm)
    assert backend.taps == []


def test_withdrawal_does_not_confirm_an_unrelated_purchase():
    backend, oracle = withdrawal_oracle(True)
    backend.ui['texts'][0]['text'] = '是否购买钻石？'
    assert oracle.campaign_withdraw_control(confirm=True) is None
    assert backend.taps == []


def test_withdrawal_rejects_duplicate_confirmation_text():
    backend, oracle = withdrawal_oracle(True)
    backend.ui['texts'].append(dict(backend.ui['texts'][0]))
    backend.ui['text_count'] += 1
    with pytest.raises(SemanticGateClosed, match='ambiguous'):
        oracle.click_campaign_withdraw(confirm=True)
    assert backend.taps == []


def hp_oracle():
    backend = FakeBackend([])
    images = []
    root = 'OverlayCamera/Overlay/UIMain/top/LevelStageView(Clone)/left_stage/fleet/'
    for slot in range(6):
        prefix = root + ('main' if slot < 3 else 'vanguard') + '/shiptpl(Clone)'
        top = 124.467 + 100 * slot
        images.append(make_image(prefix + '/icon_bg/icon', 'ship_' + str(slot),
            bounds=dict(left=17.1, top=top, right=104.9, bottom=top + 87.733)))
        hp = 0.1 if slot == 0 else 1.0
        images.append(make_image(prefix + '/blood/fillarea/green', 'blood',
            bounds=dict(left=35.1, top=204.8 + 100 * slot,
                        right=35.1 + 66.333 * hp, bottom=209.067 + 100 * slot)))
        images[-1]['fill_amount'] = hp
    backend.ui = make_ui([], images=images)
    oracle = make_oracle(backend)
    oracle.campaign_map_entry_state = lambda: None
    oracle.campaign_map_displayed_fleet_index = lambda: 1
    return backend, oracle


def test_low_hp_ship_remains_present_and_input_order_is_irrelevant():
    backend, oracle = hp_oracle()
    backend.ui['images'].reverse()
    hp, presence = oracle.campaign_hp_control_snapshot(1)
    assert hp[0] == pytest.approx(0.1)
    assert presence == (True,) * 6
    assert backend.taps == []


def test_native_red_hp_is_read_instead_of_assuming_six_green_bars():
    backend, oracle = hp_oracle()
    bar = backend.ui['images'][1]
    bar['path'] = bar['path'].removesuffix('/green') + '/red'
    bar['name'] = 'red'
    hp, presence = oracle.campaign_hp_control_snapshot(1)
    assert hp[0] == pytest.approx(0.1)
    assert presence[0] is True


def test_map_does_not_use_unused_prefab_image_fill_amount_as_hp():
    backend, oracle = hp_oracle()
    for image in backend.ui['images']:
        image['fill_amount'] = 0.191
    hp, _ = oracle.campaign_hp_control_snapshot(1)
    assert hp == pytest.approx((0.1, 1, 1, 1, 1, 1))


def test_hp_control_rejects_another_fleets_display():
    _, oracle = hp_oracle()
    with pytest.raises(SemanticGateClosed, match='another displayed fleet'):
        oracle.campaign_hp_control_snapshot(2)


def test_missing_portrait_is_unknown_not_an_empty_slot():
    backend, oracle = hp_oracle()
    backend.ui['images'].pop(0)
    backend.ui['image_count'] -= 1
    with pytest.raises(SemanticGateClosed, match='occupied slots'):
        oracle.campaign_hp_control_snapshot(1)


def test_withdrawal_receipts_prevent_repeated_input_from_old_animation():
    backend, oracle = withdrawal_oracle()
    adapter = AlasSemanticAdapter(oracle, package_gate=lambda: None)
    adapter._campaign_context = _CampaignFlowContext(stage_code='12-4')
    adapter._click_campaign_strategy('WITHDRAW')
    assert adapter._appear_campaign('WITHDRAW') is False
    with pytest.raises(SemanticGateClosed, match='already submitted'):
        adapter._click_campaign_strategy('WITHDRAW')
    assert len(backend.taps) == 1


def test_withdrawal_uses_the_observer_hit_point_not_an_assumed_center():
    backend, oracle = withdrawal_oracle()
    backend.buttons['buttons'][0]['adb_point']['x'] += 5
    oracle.click_campaign_withdraw()
    assert backend.taps == [(645, 360)]


@pytest.mark.parametrize('menu, expected', [(True, 'CAMPAIGN_MENU_CHECK'), (False, 'CAMPAIGN_CHECK')])
def test_campaign_destination_wins_over_departing_main_hierarchy(menu, expected):
    oracle = FakeOracle()
    oracle._blocking_rules = lambda state, semantic_id: ()
    oracle.exists_values['campaign-menu/page/back'] = True
    oracle.main_page_visible_value = True
    oracle.campaign_menu_is_entry = lambda: menu
    oracle.campaign_page_is_normal = lambda: not menu
    adapter = AlasSemanticAdapter(oracle, package_gate=lambda: None)
    from tests.semantic_support.adapter_shapes import NamedButton
    assert adapter.appear(NamedButton(expected)) is True
    assert adapter._appear_priority('MAIN_GOTO_CAMPAIGN_WHITE') is False
    assert adapter._appear_priority('MAIN_GOTO_FLEET') is False
    assert oracle.click_calls == []


@pytest.mark.parametrize('top', [True, False, None])
def test_precombat_recovery_requires_positive_top_raycast(top):
    path = 'OverlayCamera/Overlay/UIMain/ChapterPreCombatUI(Clone)/adapt/top/back_btn'
    backend = FakeBackend([make_button('back_btn', path, raycast_top=top)])
    backend.ui = make_ui([], images=[
        make_image(path, 'icon_bg_front_1920'),
        make_image(path + '/mask', 'icon_bg_mask_1920'),
        make_image(path + '/mask/Image', 'back_btn'),
    ])
    if top is True:
        make_oracle(backend).click_campaign_precombat_back()
        assert len(backend.taps) == 1
    else:
        with pytest.raises(SemanticGateClosed, match='absent or ambiguous'):
            make_oracle(backend).click_campaign_precombat_back()
        assert backend.taps == []


def test_main_battle_receipt_also_covers_a_resumed_map():
    oracle = FakeOracle()
    adapter = AlasSemanticAdapter(oracle, package_gate=lambda: None)
    from tests.semantic_support.adapter_shapes import NamedButton
    first = adapter.click(NamedButton('MAIN_GOTO_CAMPAIGN_WHITE'))
    oracle.campaign_in_map_value = True
    oracle.enabled_values['main/battle'] = False
    assert adapter.click(NamedButton('MAIN_GOTO_CAMPAIGN_WHITE')) is first
    assert oracle.click_calls == ['main/battle']
