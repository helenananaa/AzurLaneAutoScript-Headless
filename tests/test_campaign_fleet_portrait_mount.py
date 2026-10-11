import copy
import json
from pathlib import Path
from unittest.mock import Mock

import pytest

from alas_headless import AlasSemanticAdapter, SemanticGateClosed
from alas_headless.oracle.errors import SemanticCampaignFleetIncomplete
from alas_headless.semantic_oracle import SemanticOracle, OracleFingerprint
from tests.semantic_support.observer_fixtures import FakeBackend, make_image
from tests.semantic_support.adapter_cases import AlasSemanticAdapterTestsSupport


def retained_backend():
    path = Path(__file__).resolve().parents[1] / 'artifacts/continuity-20261004/goal-scheduler-r14.json'
    if not path.exists():
        pytest.skip('retained r14 frame unavailable')
    row = next(t for t in json.loads(path.read_text(encoding='utf-8'))['tasks'] if t['selected_task'] == 'Main')
    assert row['native_error']['message'] == 'campaign fleet row ship identity is inconsistent: fleet1'
    frame = row['failed_presence']
    b = FakeBackend([])
    b.snapshot = copy.deepcopy(frame['state']['snapshot'])
    b.buttons = copy.deepcopy(frame['state']['buttons_snapshot'])
    b.ui = copy.deepcopy(frame['ui']['snapshot'])
    o = SemanticOracle(b.request, b.foreground_component, b.tap,
        OracleFingerprint(package=b.snapshot['package'], component=b.foreground,
            driver_revision=b.snapshot['driver_revision'], expected_pid=b.snapshot['pid']), sleep=Mock())
    return b, o


def complete_portraits(b):
    # Counterexample fixture: represent mounted portraits without claiming
    # these synthetic sprites are evidence of the live account's identities.
    paths = {i['path'] for i in b.ui['images']}
    for index, t in enumerate(b.ui['texts']):
        if '/ShipList/' in t['path'] and t['path'].endswith('/icon_bg/lv/Text'):
            p = t['path'][:-len('lv/Text')] + 'icon'
            if p not in paths:
                b.ui['images'].append(make_image(p, 'counterexample_ship_' + str(index)))
                paths.add(p)
    # The live prefab siblings share path names. Match the number per row,
    # preserving every observed portrait rather than deduplicating exports.
    for row in ['fleet/1', 'fleet/2', 'sub/1']:
        prefix = '/ShipList/' + row + '/'
        levels = [t for t in b.ui['texts'] if prefix in t['path'] and t['path'].endswith('/icon_bg/lv/Text')]
        icons = [i for i in b.ui['images'] if prefix in i['path'] and i['path'].endswith('/icon_bg/icon')]
        for n in range(len(levels) - len(icons)):
            b.ui['images'].append(make_image(levels[n]['path'][:-len('lv/Text')] + 'icon', 'counterexample_slot_' + str(n)))
    b.ui['image_count'] = len(b.ui['images'])


def test_actual_partial_frame_is_classified_without_relaxing_fleet_input():
    b, o = retained_backend()
    with pytest.raises(SemanticCampaignFleetIncomplete):
        o._campaign_fleet_selection_state_once('12-4')
    a = AlasSemanticAdapter(o, package_gate=lambda: None, campaign_fleet_mutation_budget=24)
    a.begin_campaign_pre_sortie('12-4')
    AlasSemanticAdapterTestsSupport.seed_owned_campaign_fleet_overlay(a)
    assert a._appear_campaign('FLEET_PREPARATION') is False
    assert a._campaign_context.initial_fleet_state is None
    with pytest.raises(SemanticCampaignFleetIncomplete):
        a.authorize_campaign_fleet_preparation(1, 2, 0)
    assert a._campaign_context.initial_fleet_state is None
    assert b.taps == []


def test_complete_compatible_panel_is_admitted_in_next_native_frame():
    b, o = retained_backend()
    complete_portraits(b)
    state = o._campaign_fleet_selection_state_once('12-4')
    assert [r.ship_levels for r in state.rows] == [
        (100, 115, 116, 117, 117, 119), (100, 100, 107, 107, 116, 117), (125, 125, 125)]
    a = AlasSemanticAdapter(o, package_gate=lambda: None, campaign_fleet_mutation_budget=24)
    a.begin_campaign_pre_sortie('12-4')
    AlasSemanticAdapterTestsSupport.seed_owned_campaign_fleet_overlay(a)
    assert a._appear_campaign('FLEET_PREPARATION') is True
    assert b.taps == []


@pytest.mark.parametrize('case', ['extra-icon', 'bad-level', 'truncated', 'skipped'])
def test_malformed_or_inconsistent_panel_is_not_treated_as_portrait_wait(case):
    b, o = retained_backend()
    if case == 'extra-icon':
        complete_portraits(b)
        image = next(i for i in b.ui['images'] if '/ShipList/fleet/1/' in i['path'] and i['path'].endswith('/icon_bg/icon'))
        b.ui['images'].append(copy.deepcopy(image)); b.ui['image_count'] += 1
    elif case == 'bad-level':
        next(t for t in b.ui['texts'] if '/ShipList/fleet/1/' in t['path'] and t['path'].endswith('/icon_bg/lv/Text'))['text'] = '999'
    elif case == 'truncated':
        b.ui['image_truncated'] = True
    else:
        b.ui['skipped_count'] = 1
    with pytest.raises(SemanticGateClosed) as caught:
        o._campaign_fleet_selection_state_once('12-4')
    assert not isinstance(caught.value, SemanticCampaignFleetIncomplete)
    assert b.taps == []
