import pytest
from unittest.mock import Mock
from types import SimpleNamespace
from alas_headless import AlasSemanticAdapter, AlasSemanticSession, SemanticGateClosed
from tests.semantic_support.adapter_fixtures import NamedButton
from tests.semantic_support.observer_fixtures import FakeBackend, make_button, make_buttons, make_image, make_oracle, make_ui, make_text

PATH = 'UICamera/Canvas/UIMain/WorldBossUI(Clone)/pages/CurrentWorldBossChallengeUI(Clone)/main/award_btn'
CHARACTER = 'UICamera/Canvas/UIMain/MetaCharacterUI(Clone)/HidePanel/PTPanel/'


def test_meta_home_retries_only_observation_then_dispatches_once():
    backend = FakeBackend([make_button('option', 'root/WorldBossUI(Clone)/option',
                                       1230, 50, raycast_top=None)])
    oracle = make_oracle(backend)
    oracle.meta_page_visible = Mock(side_effect=[False, True])
    receipt = oracle.click_meta_home()
    assert receipt.semantic_id == 'meta/home'
    assert oracle.meta_page_visible.call_count == 2
    assert backend.taps == [(1230, 50)]

    backend.taps.clear()
    oracle.meta_page_visible = Mock(return_value=False)
    with pytest.raises(SemanticGateClosed, match='page identity is absent'):
        oracle.click_meta_home()
    assert oracle.meta_page_visible.call_count == 4 and backend.taps == []

    oracle.meta_page_visible = Mock(return_value=True)
    backend.buttons['buttons'][0]['raycast_top'] = False
    with pytest.raises(SemanticGateClosed, match='not actionable'):
        oracle.click_meta_home()
    assert backend.taps == []


def test_meta_home_checks_foreground_again_at_input_boundary():
    backend = FakeBackend([make_button('option', 'root/WorldBossUI(Clone)/option',
                                       1230, 50, raycast_top=None)])
    oracle = make_oracle(backend)
    oracle.meta_page_visible = Mock(return_value=True)
    read = oracle._retry_transition_read
    def change_foreground_after_proof(reader):
        result = read(reader)
        oracle._foreground_component = Mock(return_value='other/activity')
        return result
    oracle._retry_transition_read = change_foreground_after_proof
    with pytest.raises(SemanticGateClosed, match='foreground changed before'):
        oracle.click_meta_home()
    assert backend.taps == []


@pytest.mark.parametrize('create', [False, True])
def test_assist_navigation_is_independent_of_personal_beacon_creation(create):
    root = 'UICamera/Canvas/UIMain/WorldBossUI(Clone)/pages/CurrentWorldBossEmptyUI(Clone)/'
    buttons = [make_button('list_btn', root+'list_btn', raycast_top=None)]
    if create:
        buttons.append(make_button('tpl', root+'useItem/list/tpl', raycast_top=None))
    backend_ = FakeBackend(buttons)
    backend_.ui = make_ui([make_text('90/200', root+'progress/value')])
    oracle = make_oracle(backend_)
    adapter = AlasSemanticAdapter(oracle, package_gate=lambda: None)
    assert oracle.meta_current_empty_points() == (90, 200)
    assert oracle.meta_page_visible()
    assert adapter.appear(SimpleNamespace(name='BEACON_LIST'))
    assert adapter.appear(SimpleNamespace(name='META_BEGIN_ENTRANCE')) is create
    if not create:
        with pytest.raises(SemanticGateClosed):
            oracle.click_meta_current_create()
    assert backend_.taps == []


def character_backend(progress='1830/2000'):
    b = FakeBackend([make_button(n, CHARACTER+n) for n in ['ShowWayBtn', 'PreviewBtn']])
    b.ui = make_ui([make_text(progress, CHARACTER+'Progress/PT/PTProgressText')], images=[
        make_image(CHARACTER+'ShowWayBtn', 'ptpanel_btn_showway'),
        make_image(CHARACTER+'PreviewBtn', 'ptpanel_btn_preview')])
    return b


@pytest.mark.parametrize('raycast,allowed', [(None, True), (False, False)])
def test_character_back_requires_owner_and_preserves_header_contract(raycast, allowed):
    b = character_backend()
    path = 'OverlayCamera/Overlay/UIMain/blur_panel/adapt/top/back'
    b.buttons['buttons'].append(make_button('back', path, raycast_top=raycast))
    b.buttons['button_count'] += 1
    o = make_oracle(b)
    if allowed:
        assert o.click_meta_character_back().semantic_id == 'meta/character/back'
    else:
        with pytest.raises(SemanticGateClosed, match='actionable'):
            o.click_meta_character_back()
        assert b.taps == []
    other = FakeBackend([make_button('back', path)])
    with pytest.raises(SemanticGateClosed, match='page is absent'):
        make_oracle(other).click_meta_character_back()
    assert other.taps == []


def test_meta_character_header_back_is_not_routed_as_dock_back():
    b = character_backend()
    path = 'OverlayCamera/Overlay/UIMain/blur_panel/adapt/top/back'
    b.buttons['buttons'].append(make_button('back', path, raycast_top=None))
    b.buttons['button_count'] += 1
    oracle = make_oracle(b)
    adapter = AlasSemanticAdapter(oracle, package_gate=lambda: None)
    session = AlasSemanticSession.__new__(AlasSemanticSession)
    session.adapter = adapter
    session.open = lambda: adapter
    frame = SimpleNamespace(frame_id='meta-header-input')
    session._frame_clock = SimpleNamespace(borrow=Mock(return_value=frame))
    session.refresh_frame = lambda: frame
    adapter._require_frame_observation_oracle = lambda: oracle

    receipt = session.click(NamedButton('GOTO_MAIN'))

    assert receipt.semantic_id == 'meta/character/back'
    assert len(b.taps) == 1
    session._frame_clock.borrow.assert_called_with('meta-header-input', require_fresh=True)


def test_sync_page_and_worldboss_preview_are_distinct():
    a = AlasSemanticAdapter(make_oracle(character_backend()), package_gate=lambda: None)
    assert a.appear(SimpleNamespace(name='META_CHECK'))
    assert a.appear(SimpleNamespace(name='SYNC_ENTER'))
    assert not a.appear(SimpleNamespace(name='META_REWARD_NOTICE'))
    b = AlasSemanticAdapter(make_oracle(backend()), package_gate=lambda: None)
    assert not b.appear(SimpleNamespace(name='META_CHECK'))
    with pytest.raises(SemanticGateClosed, match='phase'):
        b.appear(SimpleNamespace(name='META_REWARD_NOTICE'))


@pytest.mark.parametrize('progress', ['2000/2000', '2200/2000', 'unknown'])
def test_unknown_or_ready_rewards_cannot_silently_become_no_reward(progress):
    b = character_backend(progress)
    with pytest.raises(SemanticGateClosed):
        make_oracle(b).meta_character_pending_sync()
    assert b.taps == []


def backend(raycast=True, sprite='btn_award'):
    b = FakeBackend([make_button('award_btn', PATH, raycast_top=raycast)])
    b.ui = make_ui([], images=[make_image(PATH, sprite)])
    return b


def test_reward_entry_uses_exact_button_and_tolerates_unrelated_image():
    b = backend()
    b.ui['images'].append(make_image('unrelated/NewPanel/icon', 'new_sprite'))
    b.ui['image_count'] += 1
    o = make_oracle(b)
    assert o.meta_reward_preview_entry_visible()
    assert o.click_meta_reward_preview_entry().path == PATH
    assert len(b.taps) == 1


@pytest.mark.parametrize('raycast', [False, None])
def test_reward_entry_requires_proven_hit_for_input(raycast):
    b = backend(raycast)
    with pytest.raises(SemanticGateClosed, match='actionable'):
        make_oracle(b).click_meta_reward_preview_entry()
    assert b.taps == []


def test_reward_entry_rejects_changed_identity_and_overlay():
    b = backend(sprite='unknown')
    with pytest.raises(SemanticGateClosed, match='unsupported'):
        make_oracle(b).meta_reward_preview_entry_visible()
    b = backend()
    b.buttons['buttons'].append(make_button('confirm', 'root/Msgbox(Clone)/window/button_container/custom_button_1(Clone)'))
    b.buttons['button_count'] += 1
    assert not make_oracle(b).meta_reward_preview_entry_visible()
    assert b.taps == []


MENU = 'UICamera/Canvas/UIMain/MetaCharacterUI(Clone)/HidePanel/MenuPanel/SynBtn'


def test_inherited_meta_menu_does_not_admit_campaign_withdrawal():
    b = FakeBackend([make_button('SynBtn', MENU)])
    b.ui = make_ui([], images=[make_image(MENU, 'menu_syn_btn')])
    a = AlasSemanticAdapter(make_oracle(b), package_gate=lambda: None)
    assert not a.appear(NamedButton('CAMPAIGN_WITHDRAW_CONFIRM'))
    for name in ('GET_ITEMS_1', 'GET_ITEMS_2', 'GET_ITEMS_3'):
        assert not a.appear(NamedButton(name))
    assert not b.taps
    b.ui['images'][0]['sprite'] = 'unknown'
    with pytest.raises(SemanticGateClosed):
        a.appear(NamedButton('CAMPAIGN_WITHDRAW_CONFIRM'))

@pytest.mark.parametrize('raycast', [True, False, None])
def test_meta_menu_sync_requires_exact_raycast(raycast):
    b = FakeBackend([make_button('SynBtn', MENU, raycast_top=raycast)])
    b.ui = make_ui([], images=[make_image(MENU, 'menu_syn_btn')])
    o = make_oracle(b)
    assert o.meta_character_menu_visible()
    a = AlasSemanticAdapter(o, package_gate=lambda: None)
    assert a.appear(SimpleNamespace(name='META_MENU_CHECK'))
    assert a.appear(SimpleNamespace(name='META_CHECK'))
    assert not a.appear(SimpleNamespace(name='GET_MISSION'))
    if raycast is True:
        assert o.click_meta_character_sync().semantic_id == 'meta/character/sync'
        assert len(b.taps) == 1
    else:
        with pytest.raises(SemanticGateClosed):
            o.click_meta_character_sync()
        assert b.taps == []


def test_meta_menu_drift_and_unknown_identity_remain_local():
    b = FakeBackend([make_button('SynBtn', MENU)])
    b.ui = make_ui([], images=[make_image(MENU, 'menu_syn_btn'), make_image('other/icon', 'additive')])
    o = make_oracle(b)
    assert o.meta_character_menu_visible()
    b.ui['images'][0]['sprite'] = 'unknown'
    with pytest.raises(SemanticGateClosed, match='identity'):
        o.click_meta_character_sync()
    assert b.taps == []
    b = character_backend()
    assert not make_oracle(b).meta_character_menu_visible()
    assert make_oracle(b).meta_character_pending_sync() == (1830, 2000)


SYN = 'OverlayCamera/Overlay/UIMain/MetaCharacterSynUI(Clone)/'
ROW = SYN+'TaskPanel/Scroll/Viewport/Content/TaskTpl(Clone)/'

def sync_backend(claimed=2):
    b = FakeBackend([make_button('BtnGetMore', SYN+'TaskPanel/BtnGetMore')])
    texts = [make_text('250', SYN+'PTPanel/Count/NumText')]
    for index, threshold in [(7,100), (9,200), (12,300)]:
        texts += [make_text(str(threshold), ROW+'PT/Count/NumText'),
                  make_text(str(index), ROW+'Target/IndexText')]
    images = [make_image(SYN+'TaskPanel/BtnGetMore', 'btn_getall')]
    for i in range(claimed):
        images += [make_image(ROW+'Info/AwardInfo/Award/Tag/Got','tag_got'), make_image(ROW+'GotMask','bg')]
    b.ui = make_ui(texts, images=images)
    return b


def settle_sync_claim(backend):
    def settle():
        backend.buttons['generation'] = 11
        backend.snapshot['generation'] = 11
        backend.ui['generation'] = 11
        backend.ui['images'] += [make_image(ROW+'Info/AwardInfo/Award/Tag/Got', 'tag_got'),
                                 make_image(ROW+'GotMask', 'bg')]
        backend.ui['image_count'] = len(backend.ui['images'])
    backend.on_tap = settle


def test_modern_sync_no_reward_is_order_independent_and_legacy_remains_valid():
    b = sync_backend(); b.ui['texts'].reverse(); b.ui['images'].reverse()
    o = make_oracle(b)
    assert o.meta_character_sync_rewards() == (250, 2, 2)
    a = AlasSemanticAdapter(o, package_gate=lambda: None)
    assert a.appear(SimpleNamespace(name='META_CHECK'))
    assert a.appear(SimpleNamespace(name='REWARD_ENTER'))
    assert not a.appear(SimpleNamespace(name='META_REWARD_NOTICE'))
    assert not a.appear(SimpleNamespace(name='SYNC_REWARD_NOTICE'))
    assert not b.taps
    assert make_oracle(character_backend()).meta_character_pending_sync() == (1830,2000)


def test_modern_sync_get_all_alias_preserves_identity_and_ambiguity_checks():
    b = sync_backend()
    b.buttons = make_buttons([make_button('BtnGetAll', SYN+'TaskPanel/BtnGetAll')])
    b.ui['images'][0]['path'] = SYN+'TaskPanel/BtnGetAll'
    b.ui['images'][0]['name'] = 'BtnGetAll'
    o = make_oracle(b)
    assert o.meta_character_sync_page_visible()
    assert o.meta_character_sync_rewards() == (250,2,2)
    a = AlasSemanticAdapter(o, package_gate=lambda: None)
    assert a.appear(SimpleNamespace(name='REWARD_ENTER'))
    assert not a.appear(SimpleNamespace(name='META_REWARD_NOTICE'))
    b.ui['images'][0]['sprite'] = 'unknown'
    with pytest.raises(SemanticGateClosed, match='identity'):
        o.meta_character_sync_rewards()
    b.ui['images'][0]['sprite'] = 'btn_getall'
    b.buttons = make_buttons(b.buttons['buttons'] + [
        make_button('BtnGetMore', SYN+'TaskPanel/BtnGetMore')])
    with pytest.raises(SemanticGateClosed, match='ambiguous'):
        o.meta_character_sync_page_visible()
    with pytest.raises(SemanticGateClosed, match='identity'):
        o.meta_character_sync_rewards()
    assert b.taps == []


def test_modern_claimable_reward_is_not_silently_no_reward():
    b = sync_backend(claimed=1)
    a = AlasSemanticAdapter(make_oracle(b), package_gate=lambda: None)
    assert a.appear(SimpleNamespace(name='SYNC_REWARD_NOTICE'))
    assert not a.appear(SimpleNamespace(name='META_REWARD_NOTICE'))
    assert not a.appear(SimpleNamespace(name='REWARD_ENTER'))
    assert not b.taps


@pytest.mark.parametrize('control', ['BtnGetMore', 'BtnGetAll'])
@pytest.mark.parametrize('raycast', [None, True, False])
def test_sync_claim_uses_exact_control_and_native_notice(control, raycast):
    b = sync_backend(claimed=1)
    settle_sync_claim(b)
    path = SYN+'TaskPanel/'+control
    button = make_button(control, path, raycast_top=raycast)
    b.buttons = make_buttons([button])
    b.ui['images'][0] = make_image(path, 'btn_getall', button['adb_bounds'])
    b.ui['images'][0]['raycast_target'] = True
    o = make_oracle(b)
    a = AlasSemanticAdapter(o, package_gate=lambda: None)
    if raycast is False:
        with pytest.raises(SemanticGateClosed, match='not actionable'):
            a.click(NamedButton('SYNC_ENTER'))
        assert b.taps == []
    else:
        receipt = a.click(NamedButton('SYNC_ENTER'))
        assert receipt.semantic_id == 'meta/character/rewards'
        assert receipt.path == path and b.taps == [(640, 360)]


@pytest.mark.parametrize('failure', ['no-reward', 'sprite', 'graphic', 'duplicate', 'foreground', 'blocker'])
def test_sync_claim_rejects_unsafe_or_unneeded_input(failure):
    b = sync_backend(claimed=2 if failure == 'no-reward' else 1)
    button = b.buttons['buttons'][0]
    b.ui['images'][0]['adb_bounds'] = button['adb_bounds']
    b.ui['images'][0]['raycast_target'] = True
    if failure == 'sprite':
        b.ui['images'][0]['sprite'] = 'unknown'
    if failure == 'graphic':
        b.ui['images'][0]['raycast_target'] = False
    if failure == 'duplicate':
        b.buttons = make_buttons([button, make_button('BtnGetAll', SYN+'TaskPanel/BtnGetAll')])
    if failure == 'foreground':
        b.foreground = 'other/activity'
    oracle = make_oracle(b)
    if failure == 'blocker':
        oracle._blocking_rules = Mock(return_value=[SimpleNamespace(blocker_id='foreign')])
    with pytest.raises(SemanticGateClosed):
        oracle.click_meta_character_sync_rewards()
    assert b.taps == []


def test_sync_claim_session_reaches_the_reviewed_adapter_port():
    b = sync_backend(claimed=1)
    settle_sync_claim(b)
    button = b.buttons['buttons'][0]
    b.ui['images'][0]['adb_bounds'] = button['adb_bounds']
    b.ui['images'][0]['raycast_target'] = True
    adapter = AlasSemanticAdapter(make_oracle(b), package_gate=lambda: None)
    session = AlasSemanticSession.__new__(AlasSemanticSession)
    session.adapter = adapter
    session.open = lambda: adapter
    session.refresh_frame = Mock()
    receipt = session.click(NamedButton('SYNC_ENTER'))
    assert receipt.semantic_id == 'meta/character/rewards'
    session.refresh_frame.assert_called_once()
    assert b.taps == [(640,360)]
    b.taps.clear()
    b.ui['images'][0]['sprite'] = 'unknown'
    with pytest.raises(SemanticGateClosed):
        session.click(NamedButton('SYNC_ENTER'))
    assert b.taps == []


@pytest.mark.parametrize('arrived', [True, False])
def test_sync_claim_waits_for_popup_without_repeating_input(monkeypatch, arrived):
    from alas_headless.oracle import meta
    clock = [0.0]
    monkeypatch.setattr(meta.time, 'monotonic', lambda: clock[0])
    b = sync_backend(claimed=1)
    button = b.buttons['buttons'][0]
    b.ui['images'][0]['adb_bounds'] = button['adb_bounds']
    b.ui['images'][0]['raycast_target'] = True
    def advance():
        b.snapshot['generation'] = b.buttons['generation'] = b.ui['generation'] = 11
    b.on_tap = advance
    o = make_oracle(b)
    o._sleep = lambda seconds: clock.__setitem__(0, clock[0] + seconds)
    o.award_info_page_visible = lambda: arrived and clock[0] >= 0.4
    if arrived:
        assert o.click_meta_character_sync_rewards().semantic_id == 'meta/character/rewards'
    else:
        with pytest.raises(SemanticGateClosed, match='postcondition'):
            o.click_meta_character_sync_rewards()
    assert b.taps == [(640,360)] and o.input_dispatch_count == 1


def test_modern_sync_incomplete_rows_rejected_without_global_failure():
    b = sync_backend(); b.ui['images'][1]['sprite'] = 'unknown'
    o = make_oracle(b)
    with pytest.raises(SemanticGateClosed, match='rows'):
        o.meta_character_sync_rewards()
    assert not o.meta_character_menu_visible()
    assert not b.taps
