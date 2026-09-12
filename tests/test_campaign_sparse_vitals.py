"""Sparse slots need the already observed preparation count, never absence alone."""

from types import SimpleNamespace
import pytest
from alas_headless import AlasSemanticAdapter, SemanticGateClosed
from alas_headless.adapter.semantic.contracts import _CampaignFlowContext
from tests.test_campaign_hp_control_ports import hp_oracle
from tests.semantic_support.observer_fixtures import make_text


def sparse_oracle():
    backend, oracle = hp_oracle()
    backend.ui['images'] = [image for index, image in enumerate(backend.ui['images'])
                            if index // 2 not in (2, 5)]
    backend.ui['image_count'] = len(backend.ui['images'])
    texts = []
    for portrait in backend.ui['images'][::2]:
        box = portrait['adb_bounds']
        texts.append(make_text('107', portrait['path'].replace('/icon_bg/icon', '/icon_bg/lv/Text'),
            bounds=dict(left=box['left'], top=box['top'] + 50,
                        right=box['right'], bottom=box['top'] + 65)))
    backend.ui['texts'] = texts
    backend.ui['text_count'] = len(texts)
    return backend, oracle


def test_sparse_hp_levels_and_low_hp_presence_preserve_alas_group_slots():
    backend, oracle = sparse_oracle()
    backend.ui['images'].reverse()
    hp, present = oracle.campaign_hp_control_snapshot(1, expected_occupied=4)
    assert hp == pytest.approx((0.1, 1, 0, 1, 1, 0))
    assert present == (True, True, False, True, True, False)
    assert oracle.campaign_sparse_fleet_levels(1, expected_occupied=4) == (107, 107, 0, 107, 107, 0)
    assert backend.taps == []


@pytest.mark.parametrize('count', [None, 5, 6])
def test_missing_pair_is_not_empty_without_matching_preparation_count(count):
    backend, oracle = sparse_oracle()
    with pytest.raises(SemanticGateClosed, match='occupied slots'):
        oracle.campaign_hp_control_snapshot(1, expected_occupied=count)
    assert backend.taps == []


def test_sparse_missing_bar_and_duplicate_level_fail_locally():
    backend, oracle = sparse_oracle()
    backend.ui['texts'].append(dict(backend.ui['texts'][0]))
    backend.ui['text_count'] += 1
    with pytest.raises(SemanticGateClosed, match='levels'):
        oracle.campaign_sparse_fleet_levels(1, expected_occupied=4)
    assert oracle.campaign_hp_control_snapshot(1, expected_occupied=4)[1][0]
    backend.ui['images'].pop()
    backend.ui['image_count'] -= 1
    with pytest.raises(SemanticGateClosed, match='occupied slots'):
        oracle.campaign_hp_control_snapshot(1, expected_occupied=4)


def test_adapter_uses_selected_preparation_row_and_refuses_sparse_resume_without_it():
    _, oracle = sparse_oracle()
    adapter = AlasSemanticAdapter(oracle, package_gate=lambda: None)
    adapter._campaign_context = _CampaignFlowContext(stage_code='10-2')
    oracle.campaign_emergency_repair_state = lambda: None
    with pytest.raises(SemanticGateClosed, match='occupied slots'):
        adapter.campaign_hp_control_snapshot(1)
    adapter._campaign_context.prepared_fleet_state = SimpleNamespace(rows=(
        SimpleNamespace(row_key='fleet1', ship_levels=(107,) * 4),
        SimpleNamespace(row_key='fleet2', ship_levels=(120,) * 6)))
    assert adapter.campaign_hp_control_snapshot(1)[1] == (True, True, False, True, True, False)
    assert adapter.campaign_fleet_levels() == (107, 107, 0, 107, 107, 0)


def test_sparse_precombat_reads_live_fill_amount_in_horizontal_groups():
    from alas_headless.oracle.campaign_health import PRECOMBAT
    backend, oracle = sparse_oracle()
    for index, image in enumerate(backend.ui['images']):
        image['path'] = PRECOMBAT + 'adapt/middle/fleet/' + image['path'].split('/left_stage/fleet/')[1]
        left = 200 + index // 2 * 100
        image['adb_bounds'] = (dict(left=left, top=300, right=left + 87.733, bottom=387.733)
            if index % 2 == 0 else dict(left=left + 18, top=380, right=left + 75, bottom=384))
    oracle.campaign_emergency_repair_state = lambda: {'count': 3}
    hp, presence = oracle.campaign_hp_control_snapshot(1, precombat=True, expected_occupied=4)
    assert hp == pytest.approx((0.1, 1, 0, 1, 1, 0))
    assert presence == (True, True, False, True, True, False)


def test_sparse_levels_use_the_same_immutable_frame_as_hp(monkeypatch):
    _, frame = sparse_oracle()
    _, live = sparse_oracle()
    adapter = AlasSemanticAdapter(live, package_gate=lambda: None)
    adapter._campaign_context = _CampaignFlowContext(stage_code='10-2')
    adapter._campaign_context.prepared_fleet_state = SimpleNamespace(rows=(
        SimpleNamespace(row_key='fleet1', ship_levels=(107,) * 4),))
    monkeypatch.setattr(adapter, '_frame_or_live_observation_oracle', lambda: frame)
    def reject_live():
        raise AssertionError('sparse read crossed the screenshot frame')
    monkeypatch.setattr(live, 'campaign_map_displayed_fleet_index', reject_live)
    assert adapter.campaign_fleet_levels() == (107, 107, 0, 107, 107, 0)
    assert adapter.campaign_fleet_hp() == pytest.approx((0.1, 1, 0, 1, 1, 0))


def test_level_label_may_extend_above_its_portrait_with_center_inside():
    backend, oracle = sparse_oracle()
    for text, portrait in zip(backend.ui['texts'], backend.ui['images'][::2]):
        top = portrait['adb_bounds']['top'] - 1.03
        text['adb_bounds'].update(top=top, bottom=top + 25)
    assert oracle.campaign_sparse_fleet_levels(1, expected_occupied=4) == (107, 107, 0, 107, 107, 0)
    backend.ui['texts'][0]['adb_bounds'].update(top=0, bottom=25)
    with pytest.raises(SemanticGateClosed, match='levels'):
        oracle.campaign_sparse_fleet_levels(1, expected_occupied=4)
