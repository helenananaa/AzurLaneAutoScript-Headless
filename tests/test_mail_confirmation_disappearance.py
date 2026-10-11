import ast
from pathlib import Path
from types import MethodType, SimpleNamespace
import pytest
from alas_headless import AlasSemanticAdapter, AlasSemanticSession, SemanticGateClosed
from alas_headless.semantic_oracle import SemanticTargetMissing
from alas_headless.adapter.semantic.contracts import _MailFlowContext
from tests.test_game_tips_loading_presence import host
from tests.semantic_support.adapter_fixtures import FakeOracle
from tests.semantic_support.adapter_fixtures import NamedButton
from tests.test_presence_driven_reward_refresh import session_for


@pytest.mark.parametrize('drift', [False, True])
def test_actual_reward_after_confirmation_classifies_missing_without_input(drift):
    b, o, a = host(drift, 'mail-award-after-confirm-r144.json')
    a._mail_context = _MailFlowContext(pending_confirmation='claim', recovered_confirmation=True)
    assert o.mail_confirmation_kind() is None
    with pytest.raises(SemanticTargetMissing):
        a.click('POPUP_CONFIRM')
    assert not b.taps


def test_confirm_disappearing_after_positive_probe_does_not_consume_grant():
    o = FakeOracle()
    o.mail_confirmation_kind_value = 'claim'
    a = AlasSemanticAdapter(o, lambda: None, allow_mail_mutations=True)
    a.begin_mail()
    assert a.appear('POPUP_CONFIRM')
    o.mail_confirmation_kind_value = None
    with pytest.raises(SemanticTargetMissing):
        a.click('POPUP_CONFIRM')
    assert not o.click_calls
    assert a._action_ledger.allowed('mail.mutation')
    session = AlasSemanticSession.__new__(AlasSemanticSession)
    session.click = lambda button, require_present: a.click(button)
    assert session.click_if_present('POPUP_CONFIRM') is None
    assert not o.click_calls


def test_changed_confirmation_kind_still_rejects_without_input():
    o = FakeOracle()
    o.mail_confirmation_kind_value = 'claim'
    a = AlasSemanticAdapter(o, lambda: None, allow_mail_mutations=True)
    a.begin_mail()
    assert a.appear('POPUP_CONFIRM')
    o.mail_confirmation_kind_value = 'delete'
    with pytest.raises(SemanticGateClosed, match='identity changed'):
        a.click('POPUP_CONFIRM')
    assert not o.click_calls


@pytest.mark.parametrize('kind', [None, 'delete'])
def test_original_direct_mail_popup_click_preserves_transition_and_wrong_kind(kind):
    o = FakeOracle()
    s, a = session_for(o)
    a._minigame_context = None
    a._mail_context = _MailFlowContext(pending_confirmation='claim')
    o.mail_confirmation_kind_value = kind
    button = NamedButton('POPUP_CONFIRM_MAIL_CLAIM')
    if kind is None:
        assert s.click(button) is None
    else:
        with pytest.raises(SemanticGateClosed, match='identity changed'):
            s.click(button)
    assert not o.click_calls


def test_retained_native_info_handler_continues_after_no_input_disappearance():
    path = Path(__file__).parents[1] / 'artifacts/continuity-20261004/alas-runtime/module/handler/info_handler.py'
    if not path.exists():
        pytest.skip('retained native ALAS handler unavailable')
    tree = ast.parse(path.read_text(encoding='utf8'))
    method = next(v for v in ast.walk(tree) if isinstance(v, ast.FunctionDef) and v.name == 'handle_popup_confirm')
    names = {n: SimpleNamespace(name=n) for n in ('POPUP_CONFIRM', 'POPUP_CANCEL', 'POPUP_CONFIRM_WHITE')}
    exec(compile(ast.Module(body=[method], type_ignores=[]), str(path), 'exec'), names)
    o = FakeOracle()
    s, a = session_for(o)
    a._minigame_context = None
    a._mail_context = _MailFlowContext(pending_confirmation='empty')
    o.mail_confirmation_kind_value = None
    host = SimpleNamespace(device=SimpleNamespace(semantic_adapter=s, click=s.click),
                           appear=lambda *args, **kwargs: True, _popup_offset=(3, 30))
    control = path.parents[1] / 'device/control.py'
    control_method = next(v for v in ast.walk(ast.parse(control.read_text(encoding='utf8')))
                          if isinstance(v, ast.FunctionDef) and v.name == 'click')
    messages = []
    control_names = {'logger': SimpleNamespace(info=messages.append)}
    exec(compile(ast.Module(body=[control_method], type_ignores=[]), str(control), 'exec'), control_names)
    host.device.handle_control_check = lambda button: None
    host.device.click = MethodType(control_names['click'], host.device)
    assert names['handle_popup_confirm'](host, 'MAIL_CLAIM')
    assert names['POPUP_CONFIRM'].name == 'POPUP_CONFIRM'
    assert not o.click_calls
    assert messages and 'without input' in messages[-1]
