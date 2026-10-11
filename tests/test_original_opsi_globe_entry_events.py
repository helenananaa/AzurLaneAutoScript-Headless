from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from alas_headless import SemanticGateClosed
from tests.test_alas_config_branch_compatibility import method


def native_entry(map_visible):
    oracle = SimpleNamespace(operation_siren_globe_zone_locked=Mock(return_value=False),
                             click_operation_siren_globe_zone_enter=Mock())
    adapter = SimpleNamespace(open=lambda: SimpleNamespace(oracle=oracle),
                              click_operation_siren_globe_zone_enter=oracle.click_operation_siren_globe_zone_enter,
                              operation_siren_map_visible=Mock(side_effect=map_visible))
    host = SimpleNamespace(device=SimpleNamespace(semantic_adapter=adapter,
                               sleep=Mock(), screenshot=Mock()),
                           get_zone_pinned_name=lambda: 'DANGEROUS',
                           handle_action_point=Mock(return_value=False),
                           handle_map_event=Mock(return_value=False),
                           handle_popup_confirm=Mock(return_value=False),
                           appear_then_click=Mock(return_value=False))
    run = method('module/os/globe_operation.py', 'GlobeOperation', 'globe_enter',
                 AUTO_SEARCH_REWARD=object())
    return host, oracle, lambda: run(host, SimpleNamespace(cn='直布罗特'))


def test_native_entry_keeps_first_visit_story_with_original_event_handler():
    host, oracle, run = native_entry([False, True])
    host.handle_map_event.return_value = True
    run()
    assert host.device.screenshot.call_count == 2
    host.handle_map_event.assert_called_once()
    oracle.click_operation_siren_globe_zone_enter.assert_called_once_with(expected_zone_name='直布罗特')


def test_unobstructed_baseline_entry_does_not_run_optional_handlers():
    host, oracle, run = native_entry([True])
    run()
    host.device.screenshot.assert_called_once()
    host.handle_map_event.assert_not_called()
    oracle.click_operation_siren_globe_zone_enter.assert_called_once()


def test_ambiguous_story_stops_original_entry_without_retrying_old_globe():
    host, oracle, run = native_entry([False])
    host.handle_map_event.side_effect = SemanticGateClosed('ambiguous story')
    with pytest.raises(SemanticGateClosed, match='ambiguous story'):
        run()
    oracle.click_operation_siren_globe_zone_enter.assert_called_once()
