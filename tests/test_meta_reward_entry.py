import pytest
from types import SimpleNamespace
from alas_headless import AlasSemanticAdapter, SemanticGateClosed
from tests.semantic_support.observer_fixtures import FakeBackend, make_button, make_image, make_oracle, make_ui, make_text

PATH = 'UICamera/Canvas/UIMain/WorldBossUI(Clone)/pages/CurrentWorldBossChallengeUI(Clone)/main/award_btn'
CHARACTER = 'UICamera/Canvas/UIMain/MetaCharacterUI(Clone)/HidePanel/PTPanel/'


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

@pytest.mark.parametrize('raycast', [True, False, None])
def test_meta_menu_sync_requires_exact_raycast(raycast):
    b = FakeBackend([make_button('SynBtn', MENU, raycast_top=raycast)])
    b.ui = make_ui([], images=[make_image(MENU, 'menu_syn_btn')])
    o = make_oracle(b)
    assert o.meta_character_menu_visible()
    a = AlasSemanticAdapter(o, package_gate=lambda: None)
    assert a.appear(SimpleNamespace(name='META_MENU_CHECK'))
    assert not a.appear(SimpleNamespace(name='META_CHECK'))
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


def test_modern_claimable_reward_is_not_silently_no_reward():
    b = sync_backend(claimed=1)
    a = AlasSemanticAdapter(make_oracle(b), package_gate=lambda: None)
    with pytest.raises(SemanticGateClosed, match='claimable'):
        a.appear(SimpleNamespace(name='META_REWARD_NOTICE'))
    assert not b.taps


def test_modern_sync_incomplete_rows_rejected_without_global_failure():
    b = sync_backend(); b.ui['images'][1]['sprite'] = 'unknown'
    o = make_oracle(b)
    with pytest.raises(SemanticGateClosed, match='rows'):
        o.meta_character_sync_rewards()
    assert not o.meta_character_menu_visible()
    assert not b.taps
