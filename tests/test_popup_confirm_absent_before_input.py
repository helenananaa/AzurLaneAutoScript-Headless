"""A fresh missing popup has no input, while an unreviewed popup still fails."""
import pytest
from alas_headless import AlasSemanticSession, SemanticGateClosed
from alas_headless.oracle.errors import SemanticInputTargetMissing
from tests.semantic_support.midmap_replay import ReplayRuntime, REVISION, fixture_payload
from tests.semantic_support.observer_fixtures import FakeBackend, make_oracle, make_button, make_ui, make_text


@pytest.mark.parametrize('target', ['confirm', 'cancel'])
def test_absent_reconnect_control_is_a_classified_fresh_no_input_miss(target):
    backend = FakeBackend([])
    oracle = make_oracle(backend)
    with pytest.raises(SemanticInputTargetMissing) as missing:
        oracle.click('overlay/network-reconnect/' + target)
    assert missing.value.semantic_id.endswith('/' + target)
    assert missing.value.generation == backend.snapshot['generation']
    assert not backend.taps


def test_native_unconditional_popup_confirm_can_continue_without_input_outside_mail():
    runtime = ReplayRuntime(fixture_payload([
        make_button('battle', 'root/frame/right/1/battle'),
        make_button('formation', 'root/frame/right/1/formation')]))
    session = AlasSemanticSession(runtime_handle=runtime, driver_revision=REVISION)
    try:
        session.refresh_frame()
        assert session.open()._mail_context is None
        assert session.click('POPUP_CONFIRM') is None
        assert not runtime.actions
        # The unrelated native page remains discoverable after the old edge.
        assert session.appear('MAIN_GOTO_FLEET')
    finally:
        session.close()


@pytest.mark.parametrize('case', ['foreign-text', 'stale', 'truncated'])
def test_no_input_miss_does_not_swallow_unreviewed_or_invalid_state(case):
    root = 'OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/'
    backend = FakeBackend([make_button('custom_button_1(Clone)', root + 'button_container/custom_button_1(Clone)')])
    backend.ui = make_ui([make_text('是否购买资源？', root + 'msg_panel/content')])
    if case == 'stale':
        backend.snapshot['age_ms'] = 10001
    elif case == 'truncated':
        backend.buttons['truncated'] = True
    with pytest.raises(SemanticGateClosed) as denied:
        make_oracle(backend).click('overlay/network-reconnect/confirm')
    assert not isinstance(denied.value, SemanticInputTargetMissing)
    assert not backend.taps
