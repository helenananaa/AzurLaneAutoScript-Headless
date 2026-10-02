import pytest

from alas_headless import SemanticGateClosed, SemanticTargetMissing
from tests.semantic_support.observer_fixtures import FakeBackend, make_button, make_oracle, make_text, make_ui, make_image


def prepare_backend(counter='0/40'):
    root = 'UICamera/Canvas/UIMain/'
    buttons = [make_button(name, root + suffix, raycast_top=None) for name, suffix in (
        ('back', 'GameRoomFushun2UI(Clone)/back'),
        ('btn_start', 'GameRoomFushun2UI(Clone)/btn_start'),
        ('btn_help', 'GameRoomFushun2UI(Clone)/btn_help'),
        ('sub', 'GameRoomCoinUI(Clone)/ad/window/sub'),
        ('add', 'GameRoomCoinUI(Clone)/ad/window/add'),
    )]
    backend = FakeBackend(buttons)
    backend.ui = make_ui([make_text(counter, root + 'GameRoomCoinUI(Clone)/ad/window/text')])
    return backend


def test_fushun_zero_selection_identifies_prepare_and_back_uses_native_point():
    backend = prepare_backend()
    oracle = make_oracle(backend)
    assert oracle.new_year_challenge_prepare_visible()
    receipt = oracle.click_new_year_challenge_prepare_control('back')
    assert receipt.semantic_id == 'minigame/new-year/back'
    assert backend.taps == [(int(receipt.point.x), int(receipt.point.y))]

def test_capped_selector_can_be_observed_but_disabled_add_cannot_be_clicked():
    backend = prepare_backend('1/1')
    for button in backend.buttons['buttons']:
        if button['name'] in ('sub', 'add'):
            button['interactable'] = False
    oracle = make_oracle(backend)
    assert oracle.new_year_challenge_ticket_count() == (1, 1)
    with pytest.raises(SemanticGateClosed):
        oracle.click_new_year_challenge_prepare_control('add')
    assert not backend.taps


def test_absent_fushun_does_not_require_its_counter_capability():
    oracle = make_oracle(FakeBackend([]))
    assert not oracle.new_year_challenge_prepare_visible()


def test_present_fushun_malformed_counter_remains_closed():
    backend = prepare_backend('unknown')
    with pytest.raises(SemanticGateClosed, match='malformed'):
        make_oracle(backend).new_year_challenge_prepare_visible()
    assert not backend.taps


def test_fushun_prepare_back_rejects_foreign_message():
    backend = prepare_backend()
    backend.buttons['buttons'].append(make_button('custom_button_1(Clone)',
        'OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/button_container/custom_button_1(Clone)'))
    backend.buttons['button_count'] += 1
    with pytest.raises(SemanticGateClosed, match='blocked'):
        make_oracle(backend).click_new_year_challenge_prepare_control('back')
    assert not backend.taps


def test_postplay_fushun_home_back_does_not_require_coin_selector():
    backend = prepare_backend()
    backend.buttons['buttons'] = [b for b in backend.buttons['buttons']
                                 if 'GameRoomCoinUI(Clone)' not in b['path']]
    backend.buttons['button_count'] = len(backend.buttons['buttons'])
    backend.ui = make_ui([])
    oracle = make_oracle(backend)
    assert oracle.new_year_challenge_home_visible()
    assert oracle.click_new_year_challenge_prepare_control('back').semantic_id == 'minigame/new-year/back'
    with pytest.raises(SemanticGateClosed, match='prepare controls'):
        oracle.click_new_year_challenge_prepare_control('start')


def test_active_fushun_result_cannot_be_treated_as_idle_home():
    backend = prepare_backend()
    backend.buttons['buttons'].append(make_button('close',
        'UICamera/Canvas/UIMain/GameRoomFushun2UI(Clone)/FushunAdventureGame(Clone)/UI/result_panel/frame/close'))
    backend.buttons['button_count'] += 1
    oracle = make_oracle(backend)
    assert not oracle.new_year_challenge_home_visible()
    with pytest.raises(SemanticGateClosed, match='idle home'):
        oracle.click_new_year_challenge_prepare_control('back')
    assert not backend.taps


@pytest.mark.parametrize('blocker', [None, 'award', 'msgbox', 'stale'])
def test_result_close_requires_coherent_unobscured_result(blocker):
    root = 'UICamera/Canvas/UIMain/GameRoomFushun2UI(Clone)/FushunAdventureGame(Clone)/UI/result_panel/frame/'
    buttons = [make_button('close', root + 'close', raycast_top=None)]
    if blocker == 'award':
        buttons.append(make_button('close', 'OverlayCamera/Overlay/UIMain/AwardInfoUI(Clone)/items/close'))
    elif blocker == 'msgbox':
        buttons.append(make_button('custom_button_1(Clone)', 'OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/button_container/custom_button_1(Clone)'))
    backend = FakeBackend(buttons)
    backend.ui = make_ui([make_text('90', root + 'score/Text'), make_text('4935', root + 'highest/Text')])
    if blocker == 'stale':
        backend.ui['generation'] = 20
    oracle = make_oracle(backend)
    if blocker is None:
        assert oracle.click_new_year_challenge_result_close().semantic_id == 'minigame/new-year/result-close'
        assert len(backend.taps) == 1
    else:
        with pytest.raises(SemanticGateClosed):
            oracle.click_new_year_challenge_result_close()
        assert not backend.taps


def poke_backend():
    return FakeBackend([make_button(name, 'UICamera/Canvas/UIMain/GameRoomPokeUI(Clone)/pop/menuUI/' + name,
                                   raycast_top=None) for name in ('btnStart', 'btnRule', 'btnBack')])


def test_poke_recovery_only_clicks_exact_native_back():
    backend = poke_backend()
    back = backend.buttons['buttons'][-1]
    back['adb_point'] = {'x': 10.333, 'y': 20.667}
    back['adb_bounds'] = {'left': 10.333, 'top': 20.667, 'right': 110.333, 'bottom': 120.667}
    oracle = make_oracle(backend)
    assert oracle.poke_minigame_prepare_visible()
    assert oracle.click_poke_minigame_back().semantic_id == 'minigame/poke/back'
    assert backend.taps == [(60, 71)]


def test_poke_ambiguous_back_remains_closed():
    backend = poke_backend()
    backend.buttons['buttons'].append(backend.buttons['buttons'][-1].copy())
    backend.buttons['button_count'] += 1
    with pytest.raises(SemanticGateClosed, match='ambiguous'):
        make_oracle(backend).click_poke_minigame_back()
    assert not backend.taps


def test_poke_known_back_still_rejects_foreign_message():
    backend = poke_backend()
    backend.buttons['buttons'].append(make_button('custom_button_1(Clone)',
        'OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/button_container/custom_button_1(Clone)'))
    backend.buttons['button_count'] += 1
    with pytest.raises(SemanticGateClosed, match='blocked'):
        make_oracle(backend).click_poke_minigame_back()
    assert not backend.taps


def test_list_entry_cannot_click_through_its_already_open_overlay():
    backend = FakeBackend([])
    oracle = make_oracle(backend)
    oracle.game_room_list_visible = lambda: True
    with pytest.raises(SemanticGateClosed, match='covered by its open list'):
        oracle.click('game-room/list')
    assert not backend.taps


def shooting_backend():
    root = 'UICamera/Canvas/UIMain/'
    backend = FakeBackend([make_button(name, root + suffix, raycast_top=None) for name, suffix in (
        ('back', 'GameRoomShootingUI(Clone)/noAdaptPanel/blur_panel/top/back'),
        ('ruleGame', 'GameRoomShootingUI(Clone)/noAdaptPanel/blur_panel/start_mask/ruleGame'),
        ('startGame', 'GameRoomShootingUI(Clone)/noAdaptPanel/blur_panel/start_mask/startGame'),
    )])
    backend.ui = make_ui([make_text('0/40', root + 'GameRoomCoinUI(Clone)/ad/window/text')])
    return backend


def test_shooting_known_prepare_back_uses_owned_native_button():
    backend = shooting_backend()
    oracle = make_oracle(backend)
    assert oracle.click_shooting_minigame_back().semantic_id == 'minigame/shooting/back'
    assert len(backend.taps) == 1


def test_shooting_prepare_back_still_rejects_foreign_message():
    backend = shooting_backend()
    backend.buttons['buttons'].append(make_button('custom_button_1(Clone)',
        'OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/button_container/custom_button_1(Clone)'))
    backend.buttons['button_count'] += 1
    with pytest.raises(SemanticGateClosed, match='blocked'):
        make_oracle(backend).click_shooting_minigame_back()
    assert not backend.taps


def game_hall_back_backend():
    root = 'UICamera/Canvas/UIMain/GameHallUI(Clone)/ad/'
    backend = FakeBackend([
        make_button('btnBack', root + 'topPanel/btnBack', x=205.8, y=60.6,
                    bounds={'left':0.8,'top':-0.067,'right':410.8,'bottom':121.267}, raycast_top=None),
        make_button('btnPlay', root + 'btnPlay', raycast_top=None),
    ])
    graphic = make_image(root + 'topPanel/btnBack/img2', 'resource_bg',
                         bounds={'left':0.828,'top':-0.054,'right':108.905,'bottom':106.987})
    graphic['raycast_target'] = True
    backend.ui = make_ui([], images=[graphic])
    return backend


@pytest.mark.parametrize('sprite', ['resource_bg', 'white_dot'])
def test_game_hall_back_uses_its_owned_hit_graphic_not_decorative_button_centre(sprite):
    backend = game_hall_back_backend()
    backend.ui['images'][0]['sprite'] = sprite
    receipt = make_oracle(backend).click('game-room/back')
    assert backend.taps == [(55,53)]
    assert receipt.point.x != 205.8


def test_game_hall_back_missing_hit_graphic_stays_closed():
    backend = game_hall_back_backend()
    backend.ui['images'][0]['raycast_target'] = False
    with pytest.raises(SemanticGateClosed, match='hit graphic is absent'):
        make_oracle(backend).click('game-room/back')
    assert not backend.taps


def test_game_hall_back_duplicate_hit_graphic_stays_closed():
    backend = game_hall_back_backend()
    backend.ui['images'].append(dict(backend.ui['images'][0]))
    backend.ui['image_count'] = 2
    with pytest.raises(SemanticGateClosed, match='hit graphic is absent'):
        make_oracle(backend).click('game-room/back')
    assert not backend.taps


def entry_backend(y=627.9):
    root = 'UICamera/Canvas/UIMain/GameHallUI(Clone)/ad/listPanel/ad/viewport'
    row = root + '/content/listTpl(Clone)'
    backend = FakeBackend([make_button('listTpl(Clone)', row, x=898.1, y=y,
                                      bounds={'left':630.767,'top':y-141,'right':1165.433,'bottom':y+141},
                                      raycast_top=None)])
    backend.ui = make_ui([], images=[
        make_image(row + '/mask/gameIcon', 'fushun2',
                   bounds={'left':685.98,'top':y-120,'right':1138.647,'bottom':y+114}),
        make_image(root, 'btn_settings',bounds={'left':0,'top':54.52,'right':1280,'bottom':720.026}),
    ])
    oracle = make_oracle(backend)
    oracle.game_room_list_visible = lambda: True
    return backend, oracle


def test_fushun_entry_uses_original_native_point_instead_of_clipping_visible_rectangle():
    backend, oracle = entry_backend()
    receipt = oracle.click_new_year_challenge_entry()
    assert backend.taps == [(898,628)]
    assert receipt.point.y == 627.9


def test_fushun_entry_above_native_viewport_is_not_clicked():
    backend, oracle = entry_backend(39.9)
    with pytest.raises(SemanticTargetMissing, match='outside the viewport'):
        oracle.click_new_year_challenge_entry()
    assert not backend.taps


def test_fushun_entry_obscured_native_button_is_not_clicked():
    backend, oracle = entry_backend()
    backend.buttons['buttons'][0]['raycast_top'] = False
    with pytest.raises(SemanticGateClosed, match='obscured'):
        oracle.click_new_year_challenge_entry()
    assert not backend.taps
