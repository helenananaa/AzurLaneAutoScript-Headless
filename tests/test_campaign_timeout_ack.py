"""Only the observed expired-map message admits the native generic acknowledgement."""
import pytest
from types import SimpleNamespace
from unittest.mock import Mock
from alas_headless import AlasSemanticAdapter, SemanticGateClosed
from tests.semantic_support.observer_fixtures import (
    FakeBackend, make_button, make_oracle, make_text, make_ui,
)

ROOT = 'OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/'
TARGET = 'campaign/map-timeout/confirm'
TEXT = '作战<color=#92fc63>时间用尽</color>，作战失败，点击确定返回选关界面'


def host():
    backend = FakeBackend([
        make_button('custom_button_1(Clone)', ROOT + 'button_container/custom_button_1(Clone)'),
        make_button('retreat', 'LevelCamera/Canvas/UIMain/LevelGrid/DragLayer/op1/retreat'),
    ])
    backend.ui = make_ui([
        make_text(TEXT, ROOT + 'msg_panel/content'),
        make_text('确 定', ROOT + 'button_container/custom_button_1(Clone)/pic'),
    ])
    oracle = make_oracle(backend)
    adapter = AlasSemanticAdapter(oracle, lambda: None)
    adapter._frame_observation_oracle = lambda: oracle
    return backend, oracle, adapter


@pytest.mark.parametrize('drift', [False, True])
def test_native_expired_map_popup_owns_passive_probes_and_exact_ack(drift):
    backend, oracle, adapter = host()
    if drift:
        backend.buttons['buttons'].reverse()
        backend.ui['texts'][0]['text'] = TEXT.replace('<color=#92fc63>', '').replace('</color>', '')
        backend.ui['additive_metadata'] = True
    assert oracle.campaign_timeout_prompt_visible()
    # Original InfoHandler uses its WHITE single-button branch because the
    # two-button CANCEL+CONFIRM branch is absent on this exact message.
    assert adapter.appear('POPUP_CONFIRM_WHITE') is True
    assert adapter.appear('POPUP_CANCEL') is False
    for name in ('GAME_ROOM_CHECK', 'CAMPAIGN_WITHDRAW_CONFIRM', 'WITHDRAW', 'GAME_TIPS'):
        assert adapter.appear(name) is False
    assert oracle.click(TARGET).semantic_id == TARGET
    assert len(backend.taps) == 1


@pytest.mark.parametrize('case', ['premium', 'withdraw', 'wrong-label', 'duplicate',
                                  'no-map', 'covered', 'foreign', 'stale'])
def test_unreviewed_or_unsafe_timeout_ack_does_not_send_input(case):
    backend, oracle, _ = host()
    if case == 'premium': backend.ui['texts'][0]['text'] = '是否花费钻石返回选关界面'
    elif case == 'withdraw': backend.ui['texts'][0]['text'] = '真的要撤退吗？'
    elif case == 'wrong-label': backend.ui['texts'][1]['text'] = '购买'
    elif case == 'duplicate':
        backend.buttons['buttons'].append(dict(backend.buttons['buttons'][0]))
        backend.buttons['button_count'] += 1
    elif case == 'no-map':
        backend.buttons['buttons'].pop(); backend.buttons['button_count'] -= 1
    elif case == 'covered': backend.buttons['buttons'][0]['raycast_top'] = False
    elif case == 'foreign': backend.snapshot['package'] = 'unrelated.package'
    else: backend.snapshot['age_ms'] = 100000
    with pytest.raises(SemanticGateClosed): oracle.click(TARGET)
    assert not backend.taps


def test_original_single_button_handler_uses_reviewed_ack_and_waits_for_selection():
    from tests.test_alas_config_branch_compatibility import method
    backend, oracle, adapter = host()
    popup = SimpleNamespace(name='POPUP_CONFIRM')
    cancel = SimpleNamespace(name='POPUP_CANCEL')
    white = SimpleNamespace(name='POPUP_CONFIRM_WHITE')
    handler = method('module/handler/info_handler.py', 'InfoHandler', 'handle_popup_confirm',
                     POPUP_CONFIRM=popup, POPUP_CANCEL=cancel, POPUP_CONFIRM_WHITE=white)
    def publish_selection():
        backend.snapshot['generation'] = backend.buttons['generation'] = backend.ui['generation'] = 11
        backend.buttons['buttons'] = []
        backend.buttons['button_count'] = 0
    backend.on_tap = publish_selection
    oracle.campaign_page_is_normal = Mock(side_effect=lambda: backend.snapshot['generation'] == 11)
    native = SimpleNamespace(device=SimpleNamespace(semantic_adapter=adapter, click=adapter.click),
                             appear=lambda b, **kw: adapter.appear(b), _popup_offset=(3, 30))
    assert handler(native, 'UI_ADDITIONAL') is True
    assert white.name == 'POPUP_CONFIRM_WHITE'
    assert len(backend.taps) == 1


def test_ack_is_not_reported_complete_while_map_remains(monkeypatch):
    from alas_headless.adapter.semantic import dispatch_actions
    backend, _, adapter = host()
    ticks = iter((0, 1, 100))
    monkeypatch.setattr(dispatch_actions.time, 'monotonic', lambda: next(ticks))
    monkeypatch.setattr(dispatch_actions.time, 'sleep', lambda _: None)
    with pytest.raises(SemanticGateClosed, match='did not return to selection'):
        adapter._click_priority('POPUP_CONFIRM_WHITE')
    assert len(backend.taps) == 1


def test_unrelated_popup_does_not_acquire_timeout_text_dependency():
    backend, oracle, _ = host()
    backend.buttons['buttons'].pop()
    backend.buttons['button_count'] -= 1
    oracle._stable_msgbox_ui_state = Mock(side_effect=AssertionError('unrelated popup'))
    assert oracle.campaign_timeout_prompt_visible() is False
    oracle._stable_msgbox_ui_state.assert_not_called()
    assert not backend.taps


@pytest.mark.parametrize('alias', ['POPUP_CONFIRM_WHITE_UI_ADDITIONAL',
                                  'POPUP_CONFIRM_WHITE_CAMPAIGN_RECONNECT'])
def test_native_annotated_alias_passes_session_mapping_admission(alias):
    _, _, adapter = host()
    assert adapter._button_name(alias) == 'POPUP_CONFIRM_WHITE'
    assert adapter.semantic_id_for(alias) == adapter.semantic_id_for('POPUP_CONFIRM_WHITE')
    assert adapter.appear(alias) is True
    assert adapter.supports(alias)


def test_unknown_white_alias_does_not_gain_mapping_admission():
    _, _, adapter = host()
    assert not adapter.supports('POPUP_CONFIRM_WHITE_UNREVIEWED')
