"""The active awakening icon may blink without changing its input owner."""
import copy
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from alas_headless.semantic_oracle import SemanticGateClosed
from tests.semantic_support.observer_fixtures import (
    FakeBackend, make_button, make_image, make_oracle, make_text, make_ui,
)

LEVEL = 'root/ShipDetailView(Clone)/attrs/attrs/property/level_bg'
BOUNDS = dict(left=620, top=340, right=660, bottom=380)


def entry(alpha):
    backend = FakeBackend([make_button('level_bg', LEVEL, bounds=BOUNDS)])
    icon = make_image(LEVEL + '/tip', 'renzhijuexing_icon', bounds=BOUNDS)
    icon['color']['alpha'] = alpha
    backend.ui = make_ui([
        make_text('Example', 'root/blur_panel/adapt/name/nameRect/name_mask/Text'),
        make_text('115', LEVEL + '/level_label/Text'),
        make_text('100/Max', LEVEL + '/exp_info'),
    ], images=[icon])
    oracle = make_oracle(backend)
    # This test opens only the resource modal; no resource confirmation runs.
    oracle.awaken_cost_state = Mock(return_value=SimpleNamespace(current_level=115, use_array=False))
    return backend, oracle


@pytest.mark.parametrize('alpha', [1.0, 0.109738, 0.0])
def test_active_blinking_icon_opens_same_typed_parent(alpha):
    backend, oracle = entry(alpha)
    detail = oracle._awaken_detail_state(123, 'Example', expected_level=115)
    _, receipt = oracle.open_awaken_confirmation(detail)
    assert receipt.semantic_id == 'awaken/detail/open'
    assert backend.taps == [(640, 360)]


@pytest.mark.parametrize('change', ['duplicate', 'wrong_sprite', 'inactive', 'truncated', 'missing_parent', 'disabled_parent'])
def test_animation_tolerance_does_not_allow_unknown_or_unactionable_entry(change):
    backend, oracle = entry(0.109738)
    detail = oracle._awaken_detail_state(123, 'Example', expected_level=115)
    if change == 'duplicate':
        backend.ui['images'].append(copy.deepcopy(backend.ui['images'][0]))
        backend.ui['image_count'] += 1
    elif change == 'wrong_sprite':
        backend.ui['images'][0]['sprite'] = 'unknown'
    elif change == 'inactive':
        backend.ui['images'][0]['active_in_hierarchy'] = False
    elif change == 'truncated':
        backend.ui['images'][0]['flags'] |= 0x10
    elif change == 'missing_parent':
        backend.buttons['buttons'].clear()
        backend.buttons['button_count'] = 0
    else:
        backend.buttons['buttons'][0]['interactable'] = False
    with pytest.raises(SemanticGateClosed):
        oracle.open_awaken_confirmation(detail)
    assert backend.taps == []
