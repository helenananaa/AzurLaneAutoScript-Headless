import ast
import copy
import textwrap
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from alas_headless import AlasSemanticAdapter, AlasSemanticSession, SemanticGateClosed
from tests.semantic_support.observer_fixtures import (
    FakeBackend, make_button, make_buttons, make_oracle, make_snapshot, make_text, make_ui,
)


ROOT = 'OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/'
MESSAGE = '第一舰队中「福煦」「大黄蜂·META」处于低心情状态，强制出击将降低好感且获得经验减半'


def setup(message=MESSAGE):
    backend = FakeBackend([
        make_button('custom_button_1(Clone)', ROOT + 'button_container/custom_button_1(Clone)', 790, 515),
        make_button('custom_button_2(Clone)', ROOT + 'button_container/custom_button_2(Clone)', 490, 515),
    ])
    backend.ui = make_ui([
        make_text(message, ROOT + 'msg_panel/content'),
        make_text('确 定', ROOT + 'button_container/custom_button_1(Clone)/pic'),
        make_text('取 消', ROOT + 'button_container/custom_button_2(Clone)/pic'),
    ])
    oracle = make_oracle(backend)

    def departed():
        backend.snapshot = make_snapshot(generation=11)
        backend.buttons = make_buttons([], generation=11)
        backend.ui = make_ui([], generation=11)

    backend.on_tap = departed
    return backend, oracle


@pytest.mark.parametrize('message', [MESSAGE, MESSAGE.replace('第一', '第二').replace('福煦', '<color=#fff>新舰名</color>')])
@pytest.mark.parametrize('confirm', [False, True])
def test_typed_choice_uses_fresh_identity_and_proves_departure(message, confirm):
    backend, oracle = setup(message)
    assert oracle.combat_low_emotion_prompt_visible()
    # The normal AUTO_SEARCH_MOVING popup handler must not claim this prompt.
    assert not oracle.enabled('overlay/network-reconnect/confirm')
    receipt = oracle.click_combat_low_emotion(confirm=confirm)
    assert receipt.semantic_id == 'combat/low-emotion/' + ('confirm' if confirm else 'cancel')
    assert backend.taps == [(790 if confirm else 490, 515)]
    assert not oracle.combat_low_emotion_prompt_visible()


@pytest.mark.parametrize('fault', ['different-message', 'covered', 'duplicate', 'stale', 'wrong-pid', 'wrong-package', 'foreground', 'loading', 'incoherent'])
def test_unsafe_or_unrelated_prompt_has_no_input(fault):
    backend, oracle = setup()
    if fault == 'different-message':
        backend.ui['texts'][0]['text'] = '消耗500钻石继续？'
        assert not oracle.exists('combat/low-emotion/cancel')
        assert not oracle.enabled('combat/low-emotion/cancel')
    elif fault == 'covered':
        backend.buttons['buttons'][1]['raycast_top'] = False
    elif fault == 'duplicate':
        backend.buttons['buttons'].append(copy.deepcopy(backend.buttons['buttons'][1]))
        backend.buttons['button_count'] += 1
    elif fault == 'stale':
        backend.snapshot['age_ms'] = 100000
    elif fault == 'wrong-pid':
        backend.snapshot['pid'] = 9999
    elif fault == 'wrong-package':
        backend.snapshot['package'] = 'other.package'
    elif fault == 'foreground':
        backend.foreground = 'other/package.Activity'
    elif fault == 'loading':
        backend.buttons['buttons'].append(make_button('Loading(Clone)', 'OverlayCamera/Overlay/UIOverlay/Loading(Clone)'))
        backend.buttons['button_count'] += 1
    elif fault == 'incoherent':
        backend.ui['generation'] = 40
    with pytest.raises(SemanticGateClosed):
        oracle.click_combat_low_emotion(confirm=False)
    assert backend.taps == []


def test_unchanged_prompt_never_repeats_unknown_input():
    backend, oracle = setup()
    backend.on_tap = None
    ticks = iter([0, 1, 6])
    oracle._monotonic = lambda: next(ticks)
    with pytest.raises(SemanticGateClosed, match='did not close'):
        oracle.click_combat_low_emotion(confirm=False)
    assert backend.taps == [(490, 515)]


def test_session_routes_exact_named_port_before_combat_aliases():
    backend, oracle = setup()
    adapter = AlasSemanticAdapter(oracle, package_gate=lambda: None)
    adapter.begin_campaign_pre_sortie('12-4')
    session = AlasSemanticSession.__new__(AlasSemanticSession)
    session.adapter = adapter
    session.open = lambda: adapter
    session.refresh_frame = Mock()
    assert session.appear('COMBAT_LOW_EMOTION')
    session.click('COMBAT_LOW_EMOTION_CANCEL')
    session.refresh_frame.assert_called_once()
    assert backend.taps == [(490, 515)]


def native_handler():
    # Compile the actual integration member's complete method, not a duplicate
    # of the implementation. The patch-tree gate checks its upstream context.
    patch = (Path(__file__).parents[1] / 'integration/alas/series/1556-combat-native-low-emotion-deferral.patch').read_text(encoding='utf-8')
    lines = [line[1:] for line in patch.splitlines() if line.startswith((' ', '+')) and not line.startswith('+++')]
    source = '\n'.join(lines)
    start = source.index('    def handle_combat_low_emotion(self):')
    end = source.index('    def handle_use_data_key(self):', start)
    namespace = {'logger': Mock(), 'AUTO_SEARCH_MAP_OPTION_OFF': object()}
    exec(compile(ast.parse(textwrap.dedent(source[start:end])), '<native-low-emotion>', 'exec'), namespace)
    return namespace['handle_combat_low_emotion']


class TaskEnd(Exception):
    pass


@pytest.mark.parametrize('ignore', [False, True])
def test_native_policy_owns_cancel_delay_and_explicit_ignore(ignore):
    adapter = Mock()
    adapter.appear.return_value = True
    config = Mock()
    config.task_stop.side_effect = TaskEnd
    handler = SimpleNamespace(device=SimpleNamespace(semantic_adapter=adapter), emotion=SimpleNamespace(is_ignore=ignore), config=config, interval_reset=Mock())
    if ignore:
        assert native_handler()(handler)
        adapter.click.assert_called_once_with('COMBAT_LOW_EMOTION_CONFIRM')
        config.task_delay.assert_not_called()
    else:
        with pytest.raises(TaskEnd):
            native_handler()(handler)
        adapter.click.assert_called_once_with('COMBAT_LOW_EMOTION_CANCEL')
        config.task_delay.assert_called_once_with(success=False)
        handler.interval_reset.assert_not_called()


def test_native_unrelated_surface_and_pixel_path_remain_unchanged():
    adapter = Mock()
    adapter.appear.return_value = False
    handler = SimpleNamespace(device=SimpleNamespace(semantic_adapter=adapter), emotion=SimpleNamespace(is_ignore=False), config=Mock())
    assert not native_handler()(handler)
    adapter.click.assert_not_called()
    handler.device = SimpleNamespace()
    assert not native_handler()(handler)
    handler.config.task_delay.assert_not_called()
    handler.emotion.is_ignore = True
    handler.handle_popup_confirm = Mock(return_value=True)
    handler.interval_reset = Mock()
    assert native_handler()(handler)
    handler.handle_popup_confirm.assert_called_once_with('IGNORE_LOW_EMOTION')


def test_absent_prompt_does_not_require_unrelated_ui_capabilities():
    backend = FakeBackend([])
    backend.ui = {'status': 'unavailable'}
    oracle = make_oracle(backend)
    assert not oracle.combat_low_emotion_prompt_visible()
    assert 'GET /v1/ui\n' not in backend.requests
    assert backend.taps == []
