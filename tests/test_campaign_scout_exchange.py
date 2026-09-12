"""Original slot exchanges use typed hero identity and proven drag endpoints."""

from types import SimpleNamespace
import pytest

from alas_headless import AlasSemanticAdapter, SemanticGateClosed
from alas_headless.adapter.semantic.contracts import _CampaignFlowContext
from alas_headless.oracle.campaign_health import PRECOMBAT
from tests.semantic_support.observer_fixtures import (
    FakeBackend, make_button, make_image, make_oracle, make_ui,
)


def backend_for_scouts():
    buttons = [make_button('start', PRECOMBAT + 'adapt/right/start')]
    portraits = []
    for slot, name in enumerate(('alpha', 'bravo', 'charlie')):
        portraits.append(make_image(PRECOMBAT + 'adapt/middle/fleet/vanguard/shiptpl(Clone)/icon_bg/icon',
            name, bounds=dict(left=200 + slot * 100, right=280 + slot * 100, top=600, bottom=690)))
        buttons.append(make_button('mouseChild', PRECOMBAT + 'adapt/middle/HeroContainer/info/' + name + '_root/mouseChild',
                                   x=350 + slot * 180, y=420 - slot * 45))
    backend = FakeBackend(buttons)
    backend.ui = make_ui([], images=portraits)
    return backend


def test_slot_mapping_tolerates_enumeration_order_and_uses_proven_points():
    backend = backend_for_scouts()
    backend.ui['images'].reverse()
    receipt = make_oracle(backend).drag_campaign_scout(0, 2)
    assert receipt['before'] == ('alpha', 'bravo', 'charlie')
    assert backend.swipes == [(350, 420, 710, 330, 600)]
    assert backend.taps == []


@pytest.mark.parametrize('failure', ['duplicate', 'wrong-hero', 'occluded', 'unknown-hit', 'invalid-slot'])
def test_ambiguous_or_unactionable_exchange_never_sends_input(failure):
    backend = backend_for_scouts()
    if failure == 'duplicate':
        backend.ui['images'][1]['sprite'] = 'alpha'
    elif failure == 'wrong-hero':
        backend.buttons['buttons'][1]['path'] = 'OtherUI/alpha_root/mouseChild'
    elif failure in ('occluded', 'unknown-hit'):
        backend.buttons['buttons'][1]['raycast_top'] = False if failure == 'occluded' else None
    with pytest.raises(SemanticGateClosed):
        make_oracle(backend).drag_campaign_scout(0, 3 if failure == 'invalid-slot' else 1)
    assert backend.swipes == []


def test_completed_swap_has_one_input_and_a_newer_postcondition():
    backend = backend_for_scouts()
    def swapped():
        images = backend.ui['images']
        positions = [i['adb_bounds'] for i in images]
        for slot, image_index in enumerate((1, 2, 0)):
            images[image_index]['adb_bounds'] = positions[slot]
        for value in (backend.snapshot, backend.buttons, backend.ui):
            value['generation'] = 11
    backend.on_swipe = swapped
    adapter = AlasSemanticAdapter(make_oracle(backend), package_gate=lambda: None)
    context = _CampaignFlowContext(stage_code='10-2')
    context.combat_admission = SimpleNamespace(fleet_index=1)
    adapter._campaign_context = context
    result = adapter.change_campaign_scout_position(0, 2)
    assert result['after'] == ('bravo', 'charlie', 'alpha')
    assert result['post_generation'] > result['generation']
    assert context.scout_drag_pending is None
    assert len(context.scout_swap_history) == len(backend.swipes) == 1


def test_unknown_dispatch_outcome_is_not_retried():
    backend = backend_for_scouts()
    def uncertain():
        raise TimeoutError('delivery outcome unknown')
    backend.on_swipe = uncertain
    adapter = AlasSemanticAdapter(make_oracle(backend), package_gate=lambda: None)
    context = _CampaignFlowContext(stage_code='10-2')
    context.combat_admission = SimpleNamespace(fleet_index=1)
    adapter._campaign_context = context
    with pytest.raises(TimeoutError):
        adapter.change_campaign_scout_position(0, 1)
    with pytest.raises(SemanticGateClosed, match='unresolved'):
        adapter.change_campaign_scout_position(0, 1)
    assert len(backend.swipes) == 1

def test_sparse_scout_exchange_never_targets_the_empty_slot():
    backend = backend_for_scouts()
    backend.ui['images'] = backend.ui['images'][:2]
    backend.ui['image_count'] = 2
    oracle = make_oracle(backend)
    receipt = oracle.drag_campaign_scout(0, 1)
    assert receipt['before'] == ('alpha', 'bravo')
    assert backend.swipes == [(350, 420, 530, 375, 600)]
    with pytest.raises(SemanticGateClosed):
        oracle.drag_campaign_scout(0, 2)
    assert len(backend.swipes) == 1

@pytest.mark.parametrize('count', [2, 3])
@pytest.mark.parametrize('fail_refresh', [False, True])
def test_scout_probe_restores_cached_weighted_hp_before_next_decision(count, fail_refresh):
    from dataclasses import make_dataclass
    from scripts.python.campaign_scout_live_probe import exercise_scouts
    snapshot = make_dataclass('Snapshot', [('generation', int)])(10)
    ships = list(('alpha', 'bravo', 'charlie')[:count])
    config = SimpleNamespace(HpControl_HpBalanceWeight='1000,1000,1000',
        HpControl_HpBalanceThreshold=0.2, HpControl_UseHpBalance=True)
    config.override = lambda **kw: [setattr(config, k, v) for k, v in kw.items()]
    host = SimpleNamespace(config=config)
    reads = []
    def hp_get():
        reads.append(True)
        if fail_refresh and len(reads) == 2:
            raise RuntimeError('fresh HP unavailable')
        weights = [float(v) for v in config.HpControl_HpBalanceWeight.split(',')]
        host.hp = [1., 1., 0.] + [weights[i]/max(weights) if i < count else 0. for i in range(3)]
        return host.hp
    def plan(target):
        positions = list(range(3))
        for index, wanted in enumerate(target):
            source = positions.index(wanted)
            if source != index:
                yield source, index
                positions.insert(index, positions.pop(source))
    host.hp_get = hp_get
    host._expected_scout_order = lambda hp: [1, 0, 2] if count == 2 else [2, 0, 1]
    host._gen_exchange_step = plan
    host._scout_position_change = lambda source, destination: ships.insert(destination, ships.pop(source))
    def balance():
        for step in plan(host._expected_scout_order(host.hp[3:])): host._scout_position_change(*step)
    host.hp_balance = balance
    oracle = SimpleNamespace(campaign_scout_order=lambda:dict(ships=tuple(ships), generation=10),
        read_state=lambda:snapshot, read_ui_state=lambda:snapshot)
    adapter = SimpleNamespace(_fresh_input_oracle=lambda:oracle,
        _campaign_context=SimpleNamespace(scout_swap_history=[]))
    record = {}
    if fail_refresh:
        with pytest.raises(RuntimeError, match='fresh HP unavailable'):
            exercise_scouts(host, adapter, record)
        assert not record['passed']
        return
    exercise_scouts(host, adapter, record)
    assert record['passed'] and record['before']['ships'] == record['restored']['ships']
    assert record['original_policy_hp'][3] == 0.1
    assert record['restored_policy_hp'][3:] == [1.] * count + [0.] * (3-count)
    assert host.hp[3:] == record['restored_policy_hp'][3:]
