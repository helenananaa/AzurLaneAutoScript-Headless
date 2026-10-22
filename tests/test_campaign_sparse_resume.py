"""A new process rebuilds sparse cardinality from independent live UI owners."""
from copy import deepcopy
from types import SimpleNamespace

import pytest

from alas_headless import AlasSemanticAdapter, SemanticGateClosed
from alas_headless.adapter.semantic.contracts import _CampaignFlowContext
from alas_headless.oracle.campaign_health import PRECOMBAT
from tests.semantic_support.observer_fixtures import make_button
from tests.test_campaign_sparse_vitals import sparse_oracle


def recovery_oracle():
    backend, oracle = sparse_oracle()
    buttons = [make_button('start', PRECOMBAT + 'adapt/right/start')]
    for image in list(backend.ui['images']):
        if not image['path'].endswith('/icon_bg/icon'):
            continue
        portrait = deepcopy(image)
        portrait['path'] = PRECOMBAT + 'adapt/middle/fleet/' + image['path'].split('/left_stage/fleet/')[1]
        backend.ui['images'].append(portrait)
        buttons.append(make_button('mouseChild', PRECOMBAT + 'adapt/middle/HeroContainer/info/'
                                   + image['sprite'] + '_root/mouseChild'))
    backend.buttons['buttons'] = buttons
    backend.buttons['button_count'] = len(buttons)
    backend.ui['image_count'] = len(backend.ui['images'])
    oracle._campaign_displayed_fleet_index_from_states = lambda state, ui: 1
    return backend, oracle


def test_new_context_recovers_sparse_hp_and_levels_without_preparation_record():
    backend, oracle = recovery_oracle()
    index, identity = oracle.campaign_precombat_fleet_identity()
    assert index == 1
    # Recreate the post-back map frame.
    backend.ui['images'] = [i for i in backend.ui['images'] if PRECOMBAT not in i['path']]
    backend.ui['image_count'] = len(backend.ui['images'])
    oracle.campaign_emergency_repair_state = lambda: None
    adapter = AlasSemanticAdapter(oracle, package_gate=lambda: None)
    adapter._campaign_context = _CampaignFlowContext(stage_code='10-2',
        inherited_fleet_index=index, inherited_fleet_identity=identity)
    assert adapter._campaign_context.prepared_fleet_state is None
    assert adapter.campaign_hp_control_snapshot(1)[1] == (True, True, False, True, True, False)
    assert adapter.campaign_fleet_levels() == (107, 107, 0, 107, 107, 0)
    assert adapter._campaign_vitals_kwargs(2) == {}
    backend.ui['images'][0]['sprite'] = 'different_ship'
    with pytest.raises(SemanticGateClosed, match='identity changed'):
        adapter.campaign_hp_control_snapshot(1)
    assert backend.taps == []


@pytest.mark.parametrize('identity_available', [True, False])
def test_session_capture_is_optional_and_installed_only_after_back(identity_available):
    from alas_headless.adapter.semantic.session_tasks import SessionTasksPorts
    context = _CampaignFlowContext(stage_code='10-2')
    identity = (('main_a', 'main_b'), ('scout_a', 'scout_b'))
    def read_identity():
        if not identity_available:
            raise SemanticGateClosed('incomplete optional identity')
        return 1, identity
    receipt = object()
    oracle = SimpleNamespace(campaign_precombat_fleet_identity=read_identity,
                             click_campaign_precombat_back=lambda: receipt)
    adapter = SimpleNamespace(_require_campaign_context=lambda: context,
                               _fresh_input_oracle=lambda: oracle)
    session = SimpleNamespace(open=lambda: adapter)
    assert SessionTasksPorts.click_campaign_precombat_back(session) is receipt
    assert context.inherited_fleet_identity == (identity if identity_available else None)
    context.inherited_fleet_identity = None
    def fail_back():
        raise SemanticGateClosed('blocked back')
    oracle.click_campaign_precombat_back = fail_back
    with pytest.raises(SemanticGateClosed, match='blocked back'):
        SessionTasksPorts.click_campaign_precombat_back(session)
    assert context.inherited_fleet_identity is None


@pytest.mark.parametrize('mutation', ['missing_hero', 'duplicate_hero', 'missing_portrait', 'truncated', 'wrong_map'])
def test_missing_export_cannot_be_reinterpreted_as_an_empty_slot(mutation):
    backend, oracle = recovery_oracle()
    if mutation == 'missing_hero':
        backend.buttons['buttons'].pop()
    elif mutation == 'duplicate_hero':
        backend.buttons['buttons'].append(deepcopy(backend.buttons['buttons'][-1]))
    elif mutation == 'missing_portrait':
        backend.ui['images'].pop()
    elif mutation == 'truncated':
        backend.ui['image_truncated'] = True
    else:
        backend.ui['images'][0]['sprite'] = 'wrong_map_ship'
    backend.buttons['button_count'] = len(backend.buttons['buttons'])
    backend.ui['image_count'] = len(backend.ui['images'])
    with pytest.raises(SemanticGateClosed):
        oracle.campaign_precombat_fleet_identity()
    assert backend.taps == []
