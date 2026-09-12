"""Archive letter stages share the native chapter-detail difficulty control."""
from types import SimpleNamespace
import pytest
from alas_headless import SemanticGateClosed
from tests.semantic_support.observer_fixtures import FakeBackend, make_oracle, make_button


@pytest.mark.parametrize('stage', ['10-2', 'a1', 'c1'])
@pytest.mark.parametrize('destination,active', [('normal', 'hard'), ('hard', 'normal')])
def test_native_detail_uses_observed_chapter_mode_for_numeric_and_archive_stages(stage, destination, active):
    oracle = make_oracle(FakeBackend([]))
    oracle.campaign_map_preparation_state = lambda selected: SimpleNamespace(
        proceed_button=SimpleNamespace(path='root/LevelStageInfoView(Clone)/panel/start'))
    oracle.campaign_mode_switch_state = lambda: destination
    assert oracle.campaign_map_preparation_mode_state(stage) == active


def test_unknown_detail_does_not_inherit_archive_mode():
    oracle = make_oracle(FakeBackend([]))
    oracle.campaign_map_preparation_state = lambda selected: SimpleNamespace(
        proceed_button=SimpleNamespace(path='root/Unknown/panel/start'))
    with pytest.raises(SemanticGateClosed, match='not on an event stage'):
        oracle.campaign_map_preparation_mode_state('a1')


@pytest.mark.parametrize('name,destination', [('btn_elite','hard'), ('btn_act_elite','hard'),
                                            ('btn_normal','normal'), ('btn_act_normal','normal')])
def test_mode_observation_under_detail_does_not_require_clickable_chapter(name, destination):
    root = 'root/LevelMainScene(Clone)/main/left_chapter/buttons/'
    backend = FakeBackend([make_button(name, root + name, raycast_top=False)])
    oracle = make_oracle(backend)
    def hidden_page():
        raise AssertionError('chapter page is covered by exact detail')
    oracle.war_archives_campaign_page_visible = hidden_page
    assert oracle.campaign_mode_switch_state() == destination
    backend.buttons['buttons'].append(make_button(name, root + name))
    backend.buttons['button_count'] += 1
    with pytest.raises(SemanticGateClosed, match='ambiguous'):
        oracle.campaign_mode_switch_state()
    assert backend.taps == []
