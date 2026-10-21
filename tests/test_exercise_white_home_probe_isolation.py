"""A native Exercise page sweep does not acquire an unrelated Mail owner."""
import pytest
from types import SimpleNamespace
from unittest.mock import Mock, patch
from alas_headless import SemanticGateClosed, AlasSemanticUnmapped, AlasSemanticSession
from tests.test_game_tips_loading_presence import host
from tests.semantic_support.observer_fixtures import make_button


@pytest.mark.parametrize('alias', ['GOTO_MAIN_WHITE', 'RPG_HOME'])
@pytest.mark.parametrize('transition_active', [False, True])
def test_accepted_exercise_entry_can_wait_for_its_counter(alias, transition_active):
    backend, _, adapter = host(fixture='exercise-retained-r185.json')
    backend.ui['texts'] = [t for t in backend.ui['texts']
                           if not t['path'].endswith('/season_info/count')]
    backend.ui['text_count'] = len(backend.ui['texts'])
    adapter._exercise_entry_receipt = SimpleNamespace(generation=1)
    adapter._exercise_entry_transition_until = 101.0 if transition_active else 99.0
    with patch('alas_headless.adapter.semantic.dispatch_observation.time.monotonic', return_value=100.0):
        if transition_active:
            assert adapter.appear(alias) is False
        else:
            with pytest.raises((SemanticGateClosed, AlasSemanticUnmapped)):
                adapter.appear(alias)
        with pytest.raises((SemanticGateClosed, AlasSemanticUnmapped)):
            adapter.click(alias)
    assert not backend.taps


@pytest.mark.parametrize('drift', [False, True])
@pytest.mark.parametrize('fixture', ['exercise-white-home-r182.json', 'exercise-no-home-r184.json'])
def test_actual_exercise_page_keeps_white_and_rpg_home_absent(drift, fixture):
    backend, oracle, adapter = host(drift, fixture)
    assert oracle.exercise_page_visible()
    assert adapter.appear('GOTO_MAIN_WHITE') is False
    assert adapter.appear('RPG_HOME') is False
    assert adapter.appear('EXERCISE_CHECK') is True
    assert adapter._mail_context is None
    assert not backend.taps


@pytest.mark.parametrize('case', ['complete', 'missing-rival', 'foreign-modal'])
def test_session_reclassifies_actual_empty_entry_frame_after_existing_refresh(case):
    alias = 'GOTO_MAIN_WHITE'
    before_backend, _, before = host(fixture='exercise-entry-mount-r185.json')
    # Test the session's existing unmapped-observation refresh seam explicitly.
    # This retained entrance is now independently recognized as a known page,
    # so it no longer supplies an unknown-page exception by itself.
    before.appear = Mock(side_effect=AlasSemanticUnmapped('transient page observation'))
    backend, _, after = host(fixture='exercise-retained-r185.json')
    if case == 'missing-rival':
        backend.buttons['buttons'] = [b for b in backend.buttons['buttons'] if b['name'] != 'rivaltpl_4']
        backend.buttons['button_count'] = len(backend.buttons['buttons'])
    elif case == 'foreign-modal':
        backend.buttons['buttons'].append(make_button('custom_button_1(Clone)',
            'root/Msgbox(Clone)/window/button_container/custom_button_1(Clone)'))
        backend.buttons['button_count'] += 1
    session = AlasSemanticSession.__new__(AlasSemanticSession)
    current, refreshes = [before], []
    session.open = lambda: current[0]
    def refresh():
        refreshes.append(True)
        current[0] = after
    session.refresh_frame = refresh
    if case == 'complete':
        assert session.appear(alias) is False
    else:
        with pytest.raises((SemanticGateClosed, AlasSemanticUnmapped)):
            session.appear(alias)
    assert len(refreshes) == 1
    assert not backend.taps and not before_backend.taps


@pytest.mark.parametrize('case', ['foreign-package', 'missing-rival', 'foreign-modal'])
@pytest.mark.parametrize('fixture', ['exercise-white-home-r182.json', 'exercise-no-home-r184.json'])
def test_unproven_exercise_owner_does_not_grant_a_home_input(case, fixture):
    backend, _, adapter = host(fixture=fixture)
    if case == 'foreign-package': backend.snapshot['package'] = 'unrelated.package'
    elif case == 'missing-rival':
        backend.buttons['buttons'] = [b for b in backend.buttons['buttons'] if b['name'] != 'rivaltpl_4']
        backend.buttons['button_count'] = len(backend.buttons['buttons'])
    else:
        backend.buttons['buttons'].append(make_button('custom_button_1(Clone)',
            'root/Msgbox(Clone)/window/button_container/custom_button_1(Clone)'))
        backend.buttons['button_count'] += 1
    with pytest.raises((SemanticGateClosed, AlasSemanticUnmapped)):
        adapter.click('GOTO_MAIN_WHITE')
    assert not backend.taps
