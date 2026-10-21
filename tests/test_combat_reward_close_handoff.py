"""A committed AwardInfo close yields to the original result loop."""
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from alas_headless import SemanticGateClosed
from tests.test_frame_post_input_foreground import session_for_meta
from tests.test_alas_config_branch_compatibility import method


@pytest.mark.parametrize('drift', [False, True])
def test_committed_close_hides_departing_award_then_allows_a_new_award(drift):
    backend, session, _ = session_for_meta('commission-award-close-r77.json')
    adapter = session.open()
    adapter._operation_siren_combat_active = True
    adapter._meta_assist_active = True
    if drift:
        backend.buttons['buttons'].reverse()
        backend.ui['optional_metadata'] = {'new_field': True}
    path = 'OverlayCamera/Overlay/UIMain/AwardInfoUI(Clone)/items/close'
    receipt = SimpleNamespace(semantic_id='combat/resource/GET_ITEMS_1',
                              path=path, generation=backend.snapshot['generation'])
    commit = SimpleNamespace(commit_generation=receipt.generation,
                             action_name='GET_ITEMS_1', receipt=receipt)
    with patch('alas_headless.adapter.semantic.session_combat.'
               'commit_alas_combat_resource_action_for_evidence', return_value=commit):
        assert session._live_combat_click('GET_ITEMS_1') is receipt
    for part in (backend.snapshot, backend.buttons, backend.ui):
        part['generation'] += 1
    native = method('module/combat/combat.py', 'Combat', 'handle_get_items',
                    **{name: name for name in ('GET_ITEMS_1', 'GET_ITEMS_2', 'GET_ITEMS_3')})
    native_host = SimpleNamespace(appear=lambda name, **_: session.appear(name), device=SimpleNamespace(click=Mock()),
                                  battle_status_click_interval=1, interval_reset=Mock())
    assert native(native_host) is False
    native_host.device.click.assert_not_called()
    assert session._combat_reward_close_pending is receipt
    # An absent source clears only the pending close; it does not complete
    # the task. A later independent AwardInfo remains observable normally.
    original = backend.buttons['buttons']
    backend.buttons['buttons'] = [b for b in original if b['path'] != path]
    backend.buttons['button_count'] = len(backend.buttons['buttons'])
    for part in (backend.snapshot, backend.buttons, backend.ui):
        part['generation'] += 1
    session.refresh_frame()
    # The later classification is unrelated to the pending-source handoff.
    with patch.object(session, '_live_combat_visible', return_value=()):
        session.appear('GET_ITEMS_1')
    assert session._combat_reward_close_pending is None
    backend.buttons['buttons'] = original
    backend.buttons['button_count'] = len(original)
    for part in (backend.snapshot, backend.buttons, backend.ui):
        part['generation'] += 1
    session.refresh_frame()
    assert session.appear('GET_ITEMS_1')
    assert not backend.taps


def test_pending_close_does_not_acknowledge_a_second_direct_input():
    backend, session, _ = session_for_meta('commission-award-close-r77.json')
    adapter = session.open()
    adapter._operation_siren_combat_active = True
    session._combat_reward_close_pending = SimpleNamespace(path='old/close')
    with patch('alas_headless.adapter.semantic.session_combat.'
               'commit_alas_combat_resource_action_for_evidence',
               side_effect=SemanticGateClosed('combat action resource is not visible')) as dispatch:
        with pytest.raises(SemanticGateClosed, match='not visible'):
            session._live_combat_click('GET_ITEMS_1')
    dispatch.assert_called_once()
    assert not backend.taps
