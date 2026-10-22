"""An inherited completed exit needs no new tap to satisfy native map_exit."""
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from alas_headless import SemanticGateClosed
from tests.test_alas_config_branch_compatibility import method


class Waiting(Exception):
    pass


class ConfirmationTimer:
    def __init__(self, *args, **kwargs):
        self.scans = 0

    def reached(self):
        self.scans += 1
        return self.scans >= 2

    def reset(self):
        self.scans = 0


def native_exit(*, semantic=True, exit_visible=False, map_visible=True, read_error=None):
    adapter = SimpleNamespace(
        operation_siren_post_search_loot_visible=lambda: False,
        operation_siren_obscure_exit_passage_position=lambda: None,
        refresh_frame=Mock(),
        try_click_operation_siren_map_exit_confirm=Mock(return_value=None),
    )
    def appear(target, **kwargs):
        if read_error is not None:
            raise read_error
        return target == 'MAP_EXIT' and exit_visible

    def loop():
        for _ in range(5):
            yield None
        raise Waiting('original loop awaits a real return')

    host = SimpleNamespace(
        device=SimpleNamespace(semantic_adapter=adapter if semantic else None),
        loop=loop, appear=appear, is_in_map=lambda: map_visible,
        appear_then_click=Mock(return_value=False),
        handle_popup_confirm=Mock(return_value=False),
        handle_map_event=Mock(return_value=False), interval_reset=Mock(),
        zone_init=Mock(),
    )
    run = method('module/os/map_operation.py', 'OSMapOperation', 'map_exit',
                 Timer=ConfirmationTimer, MAP_EXIT='MAP_EXIT', AUTO_SEARCH_REWARD='REWARD')
    return lambda: run(host), host, adapter


def test_restored_regular_map_completes_through_original_timer_without_confirmation():
    run, host, adapter = native_exit()
    run()
    host.zone_init.assert_called_once_with()
    adapter.try_click_operation_siren_map_exit_confirm.assert_called_once_with()
    host.handle_popup_confirm.assert_not_called()
    host.appear_then_click.assert_any_call('MAP_EXIT', offset=(20, 20), interval=3)


@pytest.mark.parametrize('exit_visible,map_visible', [(True, True), (False, False), (True, False)])
def test_present_exit_or_missing_native_map_keeps_original_loop_waiting(exit_visible, map_visible):
    run, host, _ = native_exit(exit_visible=exit_visible, map_visible=map_visible)
    with pytest.raises(Waiting):
        run()
    host.zone_init.assert_not_called()


def test_pixel_mode_still_requires_original_change_event():
    run, host, _ = native_exit(semantic=False)
    with pytest.raises(Waiting):
        run()
    host.zone_init.assert_not_called()


def test_invalid_typed_presence_is_not_treated_as_exit_disappearance():
    error = SemanticGateClosed('observer endpoints are not generation-coherent')
    run, host, adapter = native_exit(read_error=error)
    with pytest.raises(SemanticGateClosed) as rejected:
        run()
    assert rejected.value is error
    host.zone_init.assert_not_called()
    host.appear_then_click.assert_not_called()
    adapter.try_click_operation_siren_map_exit_confirm.assert_not_called()


def test_exit_reappearing_after_one_absent_frame_resets_native_confirmation():
    run, host, _ = native_exit()
    frames = iter([False, True, True, True, True])
    visible = [False]

    def loop():
        for value in frames:
            visible[0] = value
            yield None
        raise Waiting('exit returned before native confirmation')

    host.loop = loop
    host.appear = lambda target, **kwargs: target == 'MAP_EXIT' and visible[0]
    with pytest.raises(Waiting):
        run()
    host.zone_init.assert_not_called()
