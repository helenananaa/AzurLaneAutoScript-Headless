"""Metadata decoration does not become another reported native dispatch."""
from dataclasses import replace
import pytest
from alas_headless.semantic_oracle import ActionReceipt, Point, Bounds
from tests.test_original_scheduler_strategy_copy import module


def receipt():
    return ActionReceipt('reward/commission/finish', 17595, Point(465, 285),
                         Bounds(400, 250, 500, 300), 'exact/event/frame/finish_btn')


def test_authorization_copy_updates_one_actual_input_record():
    raw = receipt()
    authorized = replace(raw, policy_sha256='a' * 64, capability_id='commission.reward')
    record, seen = {'actions': [], 'native_taps': [{'point': [465, 285]}]}, []
    module.record_action_receipt(record, raw, seen)
    module.record_action_receipt(record, authorized, seen)
    module.record_action_receipt(record, authorized, seen)
    assert len(record['actions']) == 1
    assert record['actions'][0]['policy_sha256'] == 'a' * 64
    assert record['actions'][0]['capability_id'] == 'commission.reward'


def test_two_real_inputs_at_the_same_generation_are_both_retained():
    record, seen = {'actions': [], 'native_taps': []}, []
    for _ in range(2):
        record['native_taps'].append({'point': [465, 285]})
        raw = receipt()
        module.record_action_receipt(record, raw, seen)
        module.record_action_receipt(record,
            replace(raw, policy_sha256='a' * 64, capability_id='commission.reward'), seen)
    assert len(record['actions']) == 2


@pytest.mark.parametrize('change', ['extra-input', 'different-target', 'different-generation', 'no-input-counter'])
def test_annotation_is_not_collapsed_without_the_same_dispatch_evidence(change):
    raw = receipt()
    record, seen = {'actions': [], 'native_taps': [{}]}, []
    if change == 'no-input-counter': record.pop('native_taps')
    module.record_action_receipt(record, raw, seen)
    if change == 'extra-input': record['native_taps'].append({})
    authorized = replace(raw, policy_sha256='a' * 64, capability_id='commission.reward',
        semantic_id='another/target' if change == 'different-target' else raw.semantic_id,
        generation=raw.generation+1 if change == 'different-generation' else raw.generation)
    module.record_action_receipt(record, authorized, seen)
    assert len(record['actions']) == 2
