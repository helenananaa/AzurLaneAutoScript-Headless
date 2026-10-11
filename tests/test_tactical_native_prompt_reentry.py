from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from alas_headless import AlasSemanticAdapter, AlasSemanticSession, SemanticGateClosed
from tests.semantic_support.adapter_fixtures import FakeOracle
from tests.test_adapter_session_runtime_handle import FakeRuntimeHandle, REVISION
from tests.test_alas_config_branch_compatibility import method


@pytest.mark.parametrize('semantic,recovered,dock', [(False, False, False), (True, False, False), (True, True, False), (True, False, True)])
def test_original_tactical_reenters_its_popup_before_navigation(semantic, recovered, dock):
    events = []
    adapter = SimpleNamespace(
        begin_tactical=lambda: events.append('begin'),
        end_tactical=lambda: events.append('end'),
        cancel_tactical_continue_if_present=lambda: events.append('popup') or recovered,
        open=lambda: SimpleNamespace(oracle=SimpleNamespace(exists=lambda target: dock and target == 'tactical/page/back')),
    ) if semantic else None
    run = method('module/tactical/tactical_class.py', 'RewardTacticalClass', 'run', page_reward='reward', DOCK_CHECK='dock', TACTICAL_CLASS_START='book', POPUP_CONFIRM='course')
    host = SimpleNamespace(device=SimpleNamespace(semantic_adapter=adapter,
        screenshot=lambda: events.append('frame')), config=Mock(), tactical_finish=None,
        ui_ensure=lambda _: events.append('navigate'), appear=lambda *a, **kw: dock,
        tactical_class_receive=lambda: events.append('receive'))
    run(host)
    assert events == (['begin', 'frame', 'popup'] if semantic else []) + ([] if recovered or dock else ['navigate']) + ['receive'] + (['end'] if semantic else [])


@pytest.mark.parametrize('underlay', [True, False])
@pytest.mark.parametrize('resource', ['book', 'course'])
def test_native_book_reentry_requires_the_tactical_underlay(underlay, resource):
    run = method('module/tactical/tactical_class.py', 'RewardTacticalClass', 'run',
                 page_reward='reward', DOCK_CHECK='dock', TACTICAL_CLASS_START='book', POPUP_CONFIRM='course')
    adapter = Mock()
    adapter.cancel_tactical_continue_if_present.return_value = False
    adapter.open.return_value.oracle.exists.side_effect = lambda target: underlay and target == 'tactical/page/back'
    navigate = Mock()
    receive = Mock()
    host = SimpleNamespace(device=SimpleNamespace(semantic_adapter=adapter, screenshot=Mock()),
        config=Mock(), tactical_finish=None, ui_ensure=navigate,
        appear=lambda target, **kw: target == resource, tactical_class_receive=receive)
    run(host)
    assert navigate.call_count == (0 if underlay else 1)
    receive.assert_called_once()


def test_native_book_chooser_refreshes_before_yielding_to_existing_course_prompt():
    choose = method('module/tactical/tactical_class.py', 'RewardTacticalClass', '_tactical_books_choose', POPUP_CONFIRM='course')
    frame = Mock()
    books = Mock(side_effect=AssertionError('confirmed course no longer needs book metadata'))
    host = SimpleNamespace(device=SimpleNamespace(semantic_adapter=object(), screenshot=frame),
        _validate_tactical_config=Mock(), appear=lambda *a, **kw: True, _tactical_books_get=books)
    assert choose(host) is True
    frame.assert_called_once()
    books.assert_not_called()


@pytest.mark.parametrize('bad_frame', [False, True])
def test_tactical_book_metadata_reuses_its_observation_frame(bad_frame):
    live = FakeOracle()
    live.tactical_books = Mock(side_effect=AssertionError('advancing live metadata'))
    frame = Mock()
    if bad_frame:
        frame.tactical_books.side_effect = SemanticGateClosed('invalid semantic frame')
    else:
        frame.tactical_books.return_value = ('leased book metadata',)
    adapter = AlasSemanticAdapter(live, lambda: None, frame_observation_oracle=lambda: frame)
    adapter.begin_tactical()
    if bad_frame:
        with pytest.raises(SemanticGateClosed): adapter.tactical_books()
    else:
        assert adapter.tactical_books() == ('leased book metadata',)
    live.tactical_books.assert_not_called()


def test_course_confirmation_couples_before_slots_and_input_to_one_fresh_frame():
    live = FakeOracle()
    frame = FakeOracle()
    live.tactical_slots = Mock(side_effect=AssertionError('repeated advancing live observation'))
    live.click = Mock(side_effect=AssertionError('input lost its prepared frame'))
    frame.tactical_slots = Mock(return_value=())
    refresh = Mock()
    adapter = AlasSemanticAdapter(live, lambda: None, tactical_assign_budget=1,
        frame_observation_oracle=lambda: frame, input_frame_refresher=refresh)
    adapter.begin_tactical()
    receipt = adapter._click_tactical('POPUP_CONFIRM')
    assert receipt.semantic_id == 'tactical/course/confirm'
    assert frame.click_calls == ['tactical/course/confirm']
    assert adapter._commission_context.tactical_confirm_before_slots == set()
    refresh.assert_called_once()
    live.tactical_slots.assert_not_called()
    live.click.assert_not_called()


@pytest.mark.parametrize('kind,deadline,message,allowed', [
    ('tactical', 112.0, 'observer snapshot is stale', True),
    ('tactical', 112.0, 'semantic frame mixes UI and state generations', True),
    ('tactical', 90.0, 'observer snapshot is stale', False),
    ('commission', 112.0, 'observer snapshot is stale', False),
    ('tactical', 112.0, 'observer PID differs from bound package', False),
])
def test_existing_tactical_transition_retries_reads_only(kind, deadline, message, allowed):
    session = AlasSemanticSession(driver_revision=REVISION, runtime_handle=FakeRuntimeHandle())
    session.adapter = SimpleNamespace(_commission_context=SimpleNamespace(
        flow_kind=kind, passive_transition_until=deadline),
        _login_flow=SimpleNamespace(snapshot=lambda: SimpleNamespace(active=False, passive_transition_until=0.0)))
    expected = Mock(generation=82, frame_id='frame-82')
    session._frame_clock = Mock(current_frame_id='frame-81')
    session._frame_clock.acquire.side_effect = [SemanticGateClosed(message)] * 3 + [expected]
    with patch('alas_headless.alas_adapter.time.monotonic', return_value=100.0), \
            patch('alas_headless.alas_adapter.time.sleep'):
        if allowed:
            assert session.refresh_frame() is expected
        else:
            with pytest.raises(SemanticGateClosed):
                session.refresh_frame()
    assert session._frame_clock.acquire.call_count == (4 if allowed else (1 if 'PID' in message else 3))


@pytest.mark.parametrize('target', ['reward/tactical/finish', 'reward/tactical/go'])
def test_actual_tactical_entry_records_existing_passive_window(target):
    adapter = AlasSemanticAdapter(FakeOracle(), lambda: None, allow_tactical_rewards=True)
    adapter.begin_tactical()
    adapter._commission_context.passive_transition_until = 0.0
    receipt = SimpleNamespace(semantic_id=target, generation=10)
    with patch('alas_headless.alas_adapter.time.monotonic', return_value=100.0):
        assert adapter._record_mission_transition(receipt) is receipt
    assert adapter._commission_context.passive_transition_until == 112.0


def test_pending_empty_slot_input_yields_to_native_screenshots_without_repeat():
    oracle = FakeOracle()
    receipt = SimpleNamespace(semantic_id='tactical/slot/first-empty', generation=10)
    oracle.click_tactical_first_empty_slot = Mock(return_value=receipt)
    oracle.exists = lambda _: False
    oracle.enabled = lambda _: False
    adapter = AlasSemanticAdapter(oracle, lambda: None, tactical_assign_budget=1)
    adapter.begin_tactical()
    with patch('alas_headless.alas_adapter.time.monotonic', return_value=100.0):
        assert adapter._click_tactical('ADD_NEW_STUDENT') is receipt
        assert adapter._appear_tactical('ADD_NEW_STUDENT', None) is False
        assert adapter._click_tactical('ADD_NEW_STUDENT') is None
    oracle.click_tactical_first_empty_slot.assert_called_once()
    oracle.tactical_candidate_ships = lambda: [object()]
    oracle.read_state = lambda: SimpleNamespace(generation=11)
    assert adapter._appear_tactical('DOCK_CHECK', None) is True
    assert adapter._commission_context.tactical_empty_slot_receipt is None


def test_missing_empty_slot_destination_remains_an_error_after_native_window():
    oracle = FakeOracle()
    oracle.exists = lambda _: False
    oracle.enabled = lambda _: False
    adapter = AlasSemanticAdapter(oracle, lambda: None, tactical_assign_budget=1)
    adapter.begin_tactical()
    adapter._commission_context.tactical_empty_slot_receipt = SimpleNamespace(generation=10)
    adapter._commission_context.passive_transition_until = 90.0
    with patch('alas_headless.alas_adapter.time.monotonic', return_value=100.0):
        with pytest.raises(SemanticGateClosed, match='destination was not observed'):
            adapter._appear_tactical('ADD_NEW_STUDENT', None)
        with pytest.raises(SemanticGateClosed, match='destination was not observed'):
            adapter._click_tactical('ADD_NEW_STUDENT')
    assert oracle.click_calls == []


@pytest.mark.parametrize('owned,newer,book', [(True, True, True), (False, True, True), (True, False, True), (True, True, False)])
def test_skill_reentry_requires_accepted_input_and_newer_exact_book_page(owned,newer,book):
    oracle = FakeOracle()
    oracle.enabled = lambda target: target == 'tactical/book/start' and book
    oracle.read_state = lambda: SimpleNamespace(generation=11 if newer else 10)
    oracle.tactical_skills = Mock(side_effect=SemanticGateClosed('skill page is absent'))
    adapter = AlasSemanticAdapter(oracle, lambda: None, tactical_assign_budget=1)
    adapter.begin_tactical()
    if owned:
        adapter._commission_context.tactical_skill_confirm_receipt = SimpleNamespace(generation=10)
    if owned and newer and book:
        assert adapter.tactical_select_first_trainable_skill() is True
        oracle.tactical_skills.assert_not_called()
    else:
        with pytest.raises(SemanticGateClosed):
            adapter.tactical_select_first_trainable_skill()
    assert oracle.click_calls == []
