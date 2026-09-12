import pytest
from types import SimpleNamespace
from alas_headless import AlasSemanticAdapter, SemanticGateClosed
from tests.semantic_support.observer_fixtures import FakeBackend, make_button, make_image, make_oracle, make_ui, make_text

PATH = 'UICamera/Canvas/UIMain/WorldBossUI(Clone)/pages/CurrentWorldBossChallengeUI(Clone)/main/award_btn'
CHARACTER = 'UICamera/Canvas/UIMain/MetaCharacterUI(Clone)/HidePanel/PTPanel/'


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
