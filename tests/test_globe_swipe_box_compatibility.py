from unittest.mock import Mock

import pytest

from alas_headless import AlasSemanticAdapter, SemanticGateClosed
from tests.test_semantic_oracle_opsi_port_geometry import fixture
from tests.semantic_support.observer_fixtures import make_buttons


START = (620, 350)
END = (920, 367)


def arm(adapter, box):
    return adapter.begin_operation_siren_globe_swipe_vector(
        (300, 17), box=box, random_range=(0, 0, 0, 0), padding=15,
        duration=(.1, .2), whitelist_area=None, blacklist_area=None,
        name='GLOBE_SWIPE_300_17', distance_check=True)


def dispatch(adapter):
    return adapter.swipe(START, END, duration=.35,
                         name='GLOBE_SWIPE_300_17', distance_check=True)


@pytest.mark.parametrize('box', [
    (20, 220, 980, 620), (600, 220, 980, 620),
    (610, 330, 960, 590), (610.5, 330.5, 960.5, 590.5),
    (0, 0, 1280, 720)])
def test_baseline_and_adjusted_sampling_boxes_keep_native_path_and_postcondition(box):
    backend, oracle = fixture()
    oracle._sleep = lambda _: None
    oracle.operation_siren_globe_drag_owned = Mock(return_value=True)
    backend.on_swipe = lambda: setattr(backend, 'buttons',
        make_buttons(backend.buttons['buttons'], generation=13))
    adapter = AlasSemanticAdapter(oracle, lambda: None)
    intent = arm(adapter, box)
    assert intent.box == box
    receipt = dispatch(adapter)
    oracle.operation_siren_globe_drag_owned.assert_called_once_with(START, END)
    assert backend.swipes == [(*START, *END, 2000)]
    assert receipt.post_generation > receipt.pre_generation
    adapter.end_operation_siren_globe_swipe_vector(intent)


def test_adjusted_sampling_box_cannot_bypass_unowned_plane():
    backend, oracle = fixture()
    oracle.operation_siren_globe_drag_owned = Mock(return_value=False)
    adapter = AlasSemanticAdapter(oracle, lambda: None)
    arm(adapter, (610, 330, 960, 590))
    with pytest.raises(SemanticGateClosed, match='outside the owned plane'):
        dispatch(adapter)
    assert backend.swipes == backend.taps == []


def test_adjusted_box_does_not_authorize_endpoints_outside_that_box():
    backend, oracle = fixture()
    oracle.operation_siren_globe_drag_owned = Mock(return_value=True)
    adapter = AlasSemanticAdapter(oracle, lambda: None)
    arm(adapter, (630, 330, 960, 590))
    with pytest.raises(SemanticGateClosed, match='endpoint left its box'):
        dispatch(adapter)
    oracle.operation_siren_globe_drag_owned.assert_not_called()
    assert backend.swipes == backend.taps == []


@pytest.mark.parametrize('box', [
    (-1, 220, 980, 620), (20, 220, 1281, 620), (20, 220, 980, 721),
    (20, 620, 980, 220), (20, 220, float('nan'), 620)])
def test_offscreen_or_malformed_sampling_box_never_arms(box):
    backend, oracle = fixture()
    adapter = AlasSemanticAdapter(oracle, lambda: None)
    with pytest.raises(SemanticGateClosed):
        arm(adapter, box)
    assert adapter._operation_siren_globe_swipe_intent is None
    assert backend.swipes == backend.taps == []
