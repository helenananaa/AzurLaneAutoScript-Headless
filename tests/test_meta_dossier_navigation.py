import pytest
from alas_headless import SemanticGateClosed
from tests.semantic_support.observer_fixtures import FakeBackend, make_oracle, make_button, make_text, make_ui

ROOT = 'UICamera/Canvas/UIMain/WorldBossUI(Clone)/pages/ArchivesWorldBossDetailUI(Clone)'


@pytest.mark.parametrize('hp', ['0/1600000', '100/<color=#CF4E24>1600000</color>'])
def test_dossier_list_navigation_accepts_defeated_and_active_hp(hp):
    backend = FakeBackend([make_button('list_btn', ROOT+'/list_btn')])
    backend.ui = make_ui([make_text(hp, ROOT+'/hp/Text')])
    oracle = make_oracle(backend)
    assert oracle.meta_dossier_detail_visible()
    assert oracle.click_meta_dossier_list().semantic_id == 'meta/dossier/list'
    assert len(backend.taps) == 1


def test_dossier_list_rejects_unknown_hit_and_malformed_health():
    backend = FakeBackend([make_button('list_btn', ROOT+'/list_btn', raycast_top=None)])
    backend.ui = make_ui([make_text('0/1600000', ROOT+'/hp/Text')])
    oracle = make_oracle(backend)
    with pytest.raises(SemanticGateClosed, match='not actionable'):
        oracle.click_meta_dossier_list()
    backend.ui['texts'][0]['text'] = 'unknown'
    with pytest.raises(SemanticGateClosed, match='malformed'):
        oracle.meta_dossier_detail_visible()
    assert backend.taps == []


def test_archive_assist_list_routes_back_to_current_without_reward_or_battle_input():
    root = 'UICamera/Canvas/UIMain/WorldBossUI(Clone)/pages/ArchivesWorldBossChallengeUI(Clone)'
    backend = FakeBackend([make_button('current_list_btn', root+'/current_list_btn'),
                           make_button('refresh_btn', root+'/list_panel/frame/filter/refresh_btn')])
    oracle = make_oracle(backend)
    assert oracle.meta_dossier_assist_visible()
    assert oracle.click_meta_dossier_current().semantic_id == 'meta/dossier/current'
    backend.buttons['buttons'][0]['raycast_top'] = False
    with pytest.raises(SemanticGateClosed, match='not actionable'):
        oracle.click_meta_dossier_current()
    assert len(backend.taps) == 1
