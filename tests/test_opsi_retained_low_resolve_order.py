"""Retained exact low-resolve modal closes before native map navigation."""
from unittest.mock import Mock
import pytest
from alas_headless import SemanticGateClosed
from tests.test_opsi_retained_room_identity import native_init, NativeBoundary
from tests.test_game_tips_loading_presence import host


@pytest.mark.parametrize('drift', [False, True])
def test_actual_retained_prompt_uses_existing_exact_cancel_and_selected_fleet(drift):
    backend, oracle, adapter = host(drift, 'opsi-retained-low-resolve-r180.json')
    # Replay the original immutable STATE/UI pair. Repeating its older STATE
    # as a later transport response would correctly fail generation monotonicity.
    state, ui = oracle.read_state(), oracle.read_ui_state()
    oracle.read_state = lambda: state
    oracle.read_ui_state = lambda: ui
    assert oracle.operation_siren_low_resolve_prompt_visible()
    assert oracle.operation_siren_current_fleet() == 2
    receipt = adapter.click_operation_siren_low_resolve_cancel()
    assert receipt.semantic_id == 'os/combat/low-resolve/cancel'
    assert backend.taps == [(640, 515)]
    assert adapter.operation_siren_fleet_already_defeated(2)


@pytest.mark.parametrize('case', ['foreign-package', 'blocked', 'ambiguous', 'foreign-message'])
def test_actual_prompt_does_not_authorize_unproven_cancel(case):
    backend, oracle, _ = host(fixture='opsi-retained-low-resolve-r180.json')
    if case == 'foreign-package':
        backend.snapshot['package'] = 'unrelated.package'
    elif case == 'foreign-message':
        next(t for t in backend.ui['texts'] if t['path'].endswith('/msg_panel/content'))['text'] = '是否购买物品？'
    else:
        target = next(b for b in backend.buttons['buttons'] if b['path'].endswith('/custom_button_2(Clone)'))
        if case == 'blocked': target['raycast_top'] = False
        else:
            backend.buttons['buttons'].append(dict(target))
            backend.buttons['button_count'] += 1
    with pytest.raises(SemanticGateClosed):
        oracle.click_operation_siren_low_resolve_cancel()
    assert not backend.taps


def test_retained_prompt_is_cancelled_before_first_map_probe():
    run, host, adapter = native_init('NA海域西B-深渊海域')
    adapter.operation_siren_low_resolve_prompt_visible = Mock(return_value=True)
    adapter.click_operation_siren_low_resolve_cancel = Mock()
    adapter.refresh_frame = Mock()
    host.device.sleep = Mock()

    def map_visible():
        adapter.click_operation_siren_low_resolve_cancel.assert_called_once_with()
        adapter.refresh_frame.assert_called_once_with()
        return True

    host.is_in_map = map_visible
    with pytest.raises(NativeBoundary, match='original-special-exit'):
        run()
    adapter.operation_siren_low_resolve_prompt_visible.assert_called_once_with()
    host.device.sleep.assert_called_once_with(0.5)
    host.map_exit.assert_called_once_with()


def test_no_prompt_keeps_native_special_exit_without_cancel():
    run, host, adapter = native_init('NA海域西B-深渊海域')
    adapter.click_operation_siren_low_resolve_cancel = Mock()
    with pytest.raises(NativeBoundary, match='original-special-exit'):
        run()
    adapter.click_operation_siren_low_resolve_cancel.assert_not_called()


def test_unproven_prompt_action_does_not_fall_through_to_navigation():
    run, host, adapter = native_init('NA海域西B-深渊海域')
    adapter.operation_siren_low_resolve_prompt_visible = Mock(return_value=True)
    adapter.click_operation_siren_low_resolve_cancel = Mock(
        side_effect=SemanticGateClosed('foreground changed before low-resolve cancellation'))
    host.is_in_map = Mock()
    with pytest.raises(SemanticGateClosed, match='foreground changed'):
        run()
    host.is_in_map.assert_not_called()
    host.map_exit.assert_not_called()
