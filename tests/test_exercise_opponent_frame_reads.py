"""Inspect four changing rivals without re-polling a frame's projections."""
import copy
import pytest

from alas_headless import SemanticGateClosed
from alas_headless.adapter.frame import _FrameBoundSemanticOracle
from tests.test_frame_post_input_foreground import session_for_meta
from tests.semantic_support.observer_fixtures import make_button, make_buttons, make_text, make_ui


def workflow(drift=False, foreign_on_detail=False):
    backend, session, _ = session_for_meta('exercise-retained-r185.json')
    overview = copy.deepcopy((backend.snapshot, backend.buttons, backend.ui))
    powers = tuple(session.open().oracle.exercise_opponent_power(i) for i in range(1, 5))
    generation = max(p['generation'] for p in overview)
    detail = 'root/OverlayCamera/Overlay/UIMain/RivalInfoUI(Clone)/'

    def transition():
        nonlocal generation
        generation += 1
        if len(backend.taps) % 2:
            rival = (len(backend.taps) + 1) // 2
            backend.snapshot = copy.deepcopy(overview[0])
            backend.buttons = make_buttons([
                make_button('bg', detail+'bg', bounds={
                    'left': 0, 'top': 0, 'right': 1280, 'bottom': 720}, raycast_top=None),
                make_button('start_btn', detail+'ships_container/start_btn', raycast_top=None),
            ])
            backend.ui = make_ui([
                make_text('rival', detail+'info/title_miex'),
                *[make_text(str(level), detail+'ships_container/ships/'+fleet+
                           '/ShipCardTpl(Clone)/content/dockyard/lv/Text')
                  for fleet, level in [('main', 100+rival), ('vanguard', 120+rival)]],
            ])
            if foreign_on_detail:
                backend.foreground = 'unrelated/.Activity'
        else:
            backend.snapshot, backend.buttons, backend.ui = copy.deepcopy(overview)
        for p in (backend.snapshot, backend.buttons, backend.ui):
            p.update(generation=generation, pid=overview[0]['pid'],
                     driver_revision=overview[0]['driver_revision'])
        if drift:
            backend.buttons['buttons'].reverse()
            backend.ui['texts'].reverse()
            backend.buttons['optional_upstream_metadata'] = True

    backend.on_tap = transition
    backend.foreground_requests = 0
    backend.requests.clear()
    return backend, session, powers


@pytest.mark.parametrize('drift', [False, True])
def test_four_rivals_use_coherent_frame_reads_and_preserve_values(drift):
    backend, session, powers = workflow(drift)
    assert session.exercise_opponents() == tuple(
        (power, (100+i, 0, 0, 120+i, 0, 0)) for i, power in enumerate(powers, 1))
    assert len(backend.taps) == 8
    assert session.open().oracle.input_dispatch_count == 8
    # Includes actual-input foreground checks; repeated passive parsing adds none.
    assert backend.foreground_requests < 60


def test_foreground_loss_after_selection_never_closes_or_selects_another_rival(monkeypatch):
    backend, session, _ = workflow(foreign_on_detail=True)
    # This is an established runtime, not initial game startup; avoid spending
    # its long startup observation allowance on an offline foreign activity.
    session._INITIAL_GAME_STARTUP_RETRY_ATTEMPTS = 0
    clock = [0.0]
    monkeypatch.setattr('alas_headless.adapter.semantic.session_tasks.time.monotonic', lambda: clock[0])
    monkeypatch.setattr('alas_headless.adapter.semantic.session_tasks.time.sleep',
                        lambda seconds: clock.__setitem__(0, clock[0]+seconds))
    with pytest.raises(SemanticGateClosed):
        session.exercise_opponents()
    assert len(backend.taps) == 1


def test_expired_overview_is_reacquired_before_first_rival_input(monkeypatch):
    backend, session, powers = workflow()
    now = [session._frame_clock.borrow().captured_monotonic_ns]
    session._frame_clock._monotonic_ns = lambda: now[0]
    original = _FrameBoundSemanticOracle.exercise_opponent_power
    expired = []
    def slow_powers(reader, index):
        result = original(reader, index)
        if index == 4:
            assert not backend.taps
            now[0] += 11_000_000_000
            expired.append(reader)
        return result
    monkeypatch.setattr(_FrameBoundSemanticOracle, 'exercise_opponent_power', slow_powers)
    assert session.exercise_opponents() == tuple(
        (power, (100+i, 0, 0, 120+i, 0, 0)) for i, power in enumerate(powers, 1))
    assert len(expired) == 1
    assert len(backend.taps) == session.open().oracle.input_dispatch_count == 8


def closing_detail_workflow(monkeypatch, drift=False, stuck=False):
    backend, session, powers = workflow(drift)
    overview_buttons = copy.deepcopy(backend.buttons['buttons'])
    overview_texts = copy.deepcopy(backend.ui['texts'])
    transition = backend.on_tap
    closing = [False]
    waits = []
    clock = [0.0]
    def tap():
        if closing[0]:
            raise AssertionError('next rival selected through closing detail underlay')
        if len(backend.taps) % 2:
            transition()
        else:
            # A real closing frame keeps both its detail and overview alive.
            backend.buttons['buttons'].extend(copy.deepcopy(overview_buttons))
            backend.buttons['button_count'] = len(backend.buttons['buttons'])
            backend.ui['texts'].extend(copy.deepcopy(overview_texts))
            backend.ui['text_count'] = len(backend.ui['texts'])
            for payload in (backend.snapshot, backend.buttons, backend.ui):
                payload['generation'] += 1
            closing[0] = True
    def settle(interval):
        assert closing[0] and len(backend.taps) % 2 == 0
        waits.append(interval)
        clock[0] += 21 if stuck else interval
        if not stuck:
            transition()
            closing[0] = False
    backend.on_tap = tap
    monkeypatch.setattr('alas_headless.adapter.semantic.session_tasks.time.sleep', settle)
    monkeypatch.setattr('alas_headless.adapter.semantic.session_tasks.time.monotonic', lambda: clock[0])
    return backend, session, powers, waits


@pytest.mark.parametrize('drift', [False, True])
def test_closing_detail_underlay_is_not_a_completed_return(monkeypatch, drift):
    backend, session, powers, waits = closing_detail_workflow(monkeypatch, drift)
    assert session.exercise_opponents() == tuple(
        (power, (100+i, 0, 0, 120+i, 0, 0)) for i, power in enumerate(powers, 1))
    assert waits == [.25] * 4
    assert len(backend.taps) == session.open().oracle.input_dispatch_count == 8


def test_stuck_closing_detail_never_selects_next_rival(monkeypatch):
    backend, session, _, waits = closing_detail_workflow(monkeypatch, stuck=True)
    with pytest.raises(SemanticGateClosed, match='detail did not close'):
        session.exercise_opponents()
    assert waits == [.25]
    assert len(backend.taps) == session.open().oracle.input_dispatch_count == 2
