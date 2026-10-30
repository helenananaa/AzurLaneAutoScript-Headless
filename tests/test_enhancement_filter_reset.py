"""Generic enhancement filters must preserve original ALAS Setting.reset_first."""
import pytest
from alas_headless.oracle.enhancement import EnhancementOracle
from alas_headless.semantic_oracle import SemanticGateClosed
from tests.semantic_support.native_filter_model import NativeMultiSelect

def defaults():
    return {'sort': {'1'}, 'index': {'tpl'}, 'camp': {'tpl'},
            'rarity': {'tpl'}, 'extraindex': {'tpl'}}

def expected(index, extra):
    value=defaults();value.update(index={index},extraindex={extra});return value

def apply(model, ship_type=None, enhanceable_only=True):
    return EnhancementOracle.set_enhancement_dock_filter(
        model, ship_type, enhanceable_only=enhanceable_only)

def test_stale_native_ship_type_and_extra_are_reset_before_confirm():
    initial=defaults();initial.update(index={'3'},extraindex={'4'},camp={'1'},rarity={'3'})
    model=NativeMultiSelect(initial)
    apply(model,'cv')
    assert model.selected==expected('7','3')
    assert model.inputs[-1]=='enhancement/dock/filter/confirm'

def test_already_selected_requested_type_still_clears_old_other_type():
    initial=defaults();initial.update(index={'3','7'},extraindex={'3','4'})
    model=NativeMultiSelect(initial)
    apply(model,'cv')
    assert model.selected==expected('7','3')

def test_pinned_default_all_category_remains_usable():
    model=NativeMultiSelect(defaults())
    apply(model)
    assert model.selected==expected('tpl','3')

def test_retaining_maxed_ships_resets_to_no_extra_restriction():
    initial=defaults();initial.update(index={'5'},extraindex={'3','4'})
    model=NativeMultiSelect(initial)
    apply(model,None,enhanceable_only=False)
    assert model.selected==defaults()

def test_additive_inactive_choice_and_unrelated_dock_tail_cap_remain_allowed():
    model=NativeMultiSelect(defaults())
    model.extra_options=[('index','future_choice','btn_index_grey',False)]
    model.unrelated_images_truncated=True
    apply(model,'cv')
    assert model.selected==expected('7','3')

def test_unresolved_extra_selection_rejects_before_confirm():
    model=NativeMultiSelect(defaults())
    model.extra_options=[('index','future_choice','btn_index_blue',False)]
    with pytest.raises(SemanticGateClosed,match='filter selected set'):
        apply(model,'cv')
    assert 'enhancement/dock/filter/confirm' not in model.inputs

def test_incomplete_relevant_selected_record_rejects_before_confirm():
    model=NativeMultiSelect(defaults())
    model.extra_options=[('index','future_choice','btn_index_blue',True)]
    with pytest.raises(SemanticGateClosed,match='filter selection'):
        apply(model,'cv')
    assert 'enhancement/dock/filter/confirm' not in model.inputs
