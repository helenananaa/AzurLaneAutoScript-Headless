import pytest
from types import SimpleNamespace
from unittest.mock import Mock
from alas_headless import AlasSemanticAdapter, SemanticGateClosed
from alas_headless.oracle.errors import SemanticNavigationPending
from alas_headless.adapter.task_lifecycle import semantic_task_scope, TaskCapabilityUnavailable
from tests.semantic_support.observer_fixtures import (
    FakeBackend, make_button, make_buttons, make_image, make_oracle, make_snapshot, make_ui,
)

ROOT = 'OverlayCamera/Overlay/UIMain/CommissionInfoUI4Mellow(Clone)'
TARGET = 'reward/tactical/finish'


def fixture(y=766):
    target = make_button('finish_btn', ROOT + '/frame/main/content/class/frame/finish_btn',
                         465, y, raycast_top=False)
    backend = FakeBackend([make_button('CommissionInfoUI4Mellow(Clone)', ROOT, 827, 622), target])
    images = [
        make_image(ROOT + '/frame', 'bg', bounds=dict(left=2, top=46, right=574, bottom=672)),
        make_image(ROOT + '/frame/resources/class', 'icon_class', bounds=dict(left=377, top=67, right=551, bottom=212)),
        make_image(ROOT + '/frame/main/content/event/list/mission_1(Clone)', 'frame_lock',
                   bounds=dict(left=32, top=615, right=543, bottom=697)),
        make_image(ROOT + '/frame/main/content/event/list/mission_2(Clone)', 'frame_lock',
                   bounds=dict(left=32, top=524, right=543, bottom=606)),
    ]
    # The first row is clipped and cannot own a gesture; the next full row can.
    for i in images:
        i['raycast_target'] = True
    backend.ui = make_ui([], images=images)
    oracle = make_oracle(backend)
    adapter = AlasSemanticAdapter(oracle, lambda: None, allow_tactical_rewards=True)
    adapter.begin_tactical()
    return backend, oracle, adapter


@pytest.mark.parametrize('y', [766, 710])
def test_native_receive_click_scrolls_then_claims_only_on_next_loop(y):
    backend, oracle, adapter = fixture(y)
    def scrolled():
        backend.snapshot = make_snapshot(generation=11)
        backend.snapshot['harmless_metadata'] = 'new upstream'
        backend.buttons = make_buttons([make_button('CommissionInfoUI4Mellow(Clone)', ROOT, 827, 622),
            make_button('finish_btn', ROOT + '/frame/main/content/class/frame/finish_btn', 465, 550)], generation=11)
        backend.ui['generation'] = 11
        backend.ui['images'].reverse()
    backend.on_swipe = scrolled
    assert adapter.appear('REWARD_2')
    receipt = adapter.click('REWARD_2')
    assert receipt.semantic_id == 'reward/sidebar/scroll'
    assert len(backend.swipes) == 1 and backend.taps == []
    assert backend.swipes[0][-1] == 1500
    assert adapter._commission_context.tactical_reward_receipt is None
    assert adapter._action_ledger.allowed('tactical.reward')
    assert adapter.appear('REWARD_2')
    claim = adapter.click('REWARD_2')
    assert claim.semantic_id == TARGET
    assert backend.taps == [(465, 550)]
    assert len(backend.swipes) == 1
    assert not adapter._action_ledger.allowed('tactical.reward')


@pytest.mark.parametrize('case', ['foreign', 'stale', 'truncated', 'incoherent',
                                'duplicate_target', 'duplicate_anchor', 'modal', 'missing_anchor'])
def test_unsafe_scroll_proof_rejects_without_any_input(case):
    backend, oracle, adapter = fixture()
    if case == 'foreign': backend.snapshot['package'] = 'unrelated.package'
    elif case == 'stale': backend.snapshot['age_ms'] = 100000
    elif case == 'truncated': backend.ui['image_truncated'] = True
    elif case == 'incoherent': backend.ui['generation'] = 20
    elif case == 'duplicate_target': backend.buttons['buttons'].append(dict(backend.buttons['buttons'][-1]))
    elif case == 'duplicate_anchor': backend.ui['images'].append(dict(backend.ui['images'][-1]))
    elif case == 'missing_anchor': backend.ui['images'] = backend.ui['images'][:2]
    elif case == 'modal': backend.buttons['buttons'].append(make_button('confirm',
        'OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/button_container/custom_button_1(Clone)'))
    with pytest.raises(SemanticGateClosed):
        oracle.scroll_reward_sidebar_control(TARGET)
    assert backend.swipes == [] and backend.taps == [] and oracle.input_dispatch_count == 0


def test_on_screen_covered_control_never_authorizes_scroll_or_tap():
    backend, oracle, adapter = fixture(550)
    assert not oracle.reward_sidebar_control_offscreen(TARGET)
    with pytest.raises(SemanticGateClosed): oracle.scroll_reward_sidebar_control(TARGET)
    assert backend.swipes == [] and backend.taps == []


def test_unobserved_scroll_is_uncertain_and_not_repeated(monkeypatch):
    backend, oracle, adapter = fixture()
    clocks = iter((0, 0, 6))
    monkeypatch.setattr('alas_headless.oracle.rewards.time.monotonic', lambda: next(clocks))
    monkeypatch.setattr('alas_headless.oracle.rewards.time.sleep', lambda _: None)
    with pytest.raises(SemanticGateClosed, match='do not retry'):
        oracle.scroll_reward_sidebar_control(TARGET)
    assert len(backend.swipes) == 1 and backend.taps == []
    assert oracle.input_dispatch_count == 1


def test_unrelated_task_does_not_gain_tactical_scroll_authority():
    backend, oracle, adapter = fixture()
    adapter._commission_context = None
    assert not adapter.appear('REWARD_2')
    assert backend.swipes == [] and backend.taps == []


def test_fresh_unchanged_sidebar_defers_only_tactical_and_retains_gesture(monkeypatch):
    backend, oracle, _ = fixture()
    def still_here():
        for part in (backend.snapshot, backend.buttons, backend.ui):
            part['generation'] += 1
        backend.ui['images'].reverse()
        backend.buttons['upstream_metadata'] = True
    backend.on_swipe = still_here
    clock = [0.0]
    monkeypatch.setattr('alas_headless.oracle.rewards.time.monotonic', lambda: clock[0])
    monkeypatch.setattr('alas_headless.oracle.rewards.time.sleep',
                        lambda seconds: clock.__setitem__(0, clock[0]+seconds))
    session = SimpleNamespace(discard_task_state=Mock(), trace=None)
    with pytest.raises(TaskCapabilityUnavailable) as caught:
        with semantic_task_scope(session, 'tactical'):
            oracle.scroll_reward_sidebar_control(TARGET)
    cause = caught.value.cause
    assert isinstance(cause, SemanticNavigationPending)
    assert tuple(cause.receipt['points']) == backend.swipes[0]
    assert cause.receipt['before_target_point'] == cause.receipt['after_target_point']
    assert session.last_task_error['navigation_receipt'] == cause.receipt
    assert session.last_task_outcome['outcome'] == 'navigation-pending'
    assert len(backend.swipes) == 1 and not backend.taps
    with semantic_task_scope(session, 'daily'):
        pass
    assert session.last_task_outcome['outcome'] == 'returned'


@pytest.mark.parametrize('case', ['foreign', 'stale', 'modal', 'truncated'])
def test_post_input_unhealthy_sidebar_is_not_classified_as_healthy_delay(monkeypatch, case):
    backend, oracle, _ = fixture()
    def unsafe():
        for part in (backend.snapshot, backend.buttons, backend.ui):
            part['generation'] += 1
        if case == 'foreign': backend.foreground = 'unrelated/.Activity'
        elif case == 'stale': backend.snapshot['age_ms'] = 10001
        elif case == 'truncated': backend.ui['image_truncated'] = True
        else:
            backend.buttons['buttons'].append(make_button('custom_button_1(Clone)',
                'OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/button_container/custom_button_1(Clone)'))
            backend.buttons['button_count'] += 1
    backend.on_swipe = unsafe
    clock = [0.0]
    monkeypatch.setattr('alas_headless.oracle.rewards.time.monotonic', lambda: clock[0])
    monkeypatch.setattr('alas_headless.oracle.rewards.time.sleep',
                        lambda seconds: clock.__setitem__(0, clock[0]+seconds))
    with pytest.raises(SemanticGateClosed) as caught:
        oracle.scroll_reward_sidebar_control(TARGET)
    assert not isinstance(caught.value, SemanticNavigationPending)
    assert len(backend.swipes) == 1 and not backend.taps
