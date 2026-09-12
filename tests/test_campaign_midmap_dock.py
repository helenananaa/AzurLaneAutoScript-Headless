"""A full dock must remain owned by retirement after a battle commits."""

from alas_headless import AlasSemanticAdapter, AlasSemanticSession, SemanticGateClosed
from tests.semantic_support.oracle_cases import CampaignDockFullTestsSupport
from tests.semantic_support.observer_fixtures import make_oracle
from types import SimpleNamespace
import pytest


def test_full_dock_overrides_combat_queries_and_routes_only_nonpremium_inputs():
    backend = CampaignDockFullTestsSupport._backend()
    oracle = make_oracle(backend)
    adapter = AlasSemanticAdapter(oracle, package_gate=lambda: None)
    adapter.begin_campaign_pre_sortie('10-2')
    adapter.campaign_combat_committed = lambda: True
    session = AlasSemanticSession.__new__(AlasSemanticSession)
    session.adapter = adapter
    session.open = lambda: adapter
    session.refresh_frame = lambda: None
    def forbidden(*args):
        raise AssertionError('full-dock modal reached generic combat parser')
    session._live_combat_visible = lambda: (_ for _ in ()).throw(
        SemanticGateClosed('combat Unity selector path is ambiguous'))
    session._live_combat_click = forbidden
    for name, expected in [('BATTLE_PREPARATION', False), ('RETIRE_APPEAR_1', True),
                           ('RETIRE_APPEAR_2', False), ('RETIRE_APPEAR_3', True)]:
        assert session.appear(SimpleNamespace(name=name)) is expected
    with pytest.raises(SemanticGateClosed, match='expansion'):
        session.click(SimpleNamespace(name='RETIRE_APPEAR_2'))
    assert backend.taps == []
    session.click(SimpleNamespace(name='RETIRE_APPEAR_1'))
    assert backend.taps == [(440, 515)]


@pytest.mark.parametrize('fresh_is_dock', [True, False])
def test_new_dock_modal_refreshes_stale_screenshot_before_reclassification(fresh_is_dock):
    backend = CampaignDockFullTestsSupport._backend()
    oracle = make_oracle(backend)
    adapter = AlasSemanticAdapter(oracle, package_gate=lambda: None)
    adapter.begin_campaign_pre_sortie('10-2')
    adapter.campaign_combat_committed = lambda: True
    frame = {'fresh': False}
    adapter._frame_or_live_observation_oracle = lambda: SimpleNamespace(
        observation_surface_present=lambda surface: False,
        campaign_dock_full_visible=lambda stage: frame['fresh'] and fresh_is_dock)
    session = AlasSemanticSession.__new__(AlasSemanticSession)
    session.adapter = adapter
    session.open = lambda: adapter
    session.refresh_frame = lambda: frame.update(fresh=True)
    session._live_combat_visible = lambda: (_ for _ in ()).throw(
        SemanticGateClosed('combat Unity selector path is ambiguous'))
    if fresh_is_dock:
        assert session.appear(SimpleNamespace(name='BATTLE_PREPARATION')) is False
    else:
        with pytest.raises(SemanticGateClosed, match='selector path is ambiguous'):
            session.appear(SimpleNamespace(name='BATTLE_PREPARATION'))
    assert frame['fresh']
    assert backend.taps == []
