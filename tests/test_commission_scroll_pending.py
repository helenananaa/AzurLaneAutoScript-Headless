"""A proven missed list drag defers its task without inventing exhaustion."""
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from alas_headless.adapter.task_lifecycle import semantic_task_scope, TaskCapabilityUnavailable
from alas_headless.oracle.errors import SemanticGateClosed, SemanticNavigationPending
from tests.test_game_tips_loading_presence import host
from tests.semantic_support.observer_fixtures import make_button


def scroll_host(drift=False):
    backend, oracle, _ = host(drift, 'commission-scrolled-r155.json')
    oracle._swipe = backend.swipe
    clock = [0.0]
    oracle._monotonic = lambda: clock[0]
    oracle._sleep = lambda seconds: clock.__setitem__(0, clock[0] + seconds)
    def fresh():
        for part in (backend.snapshot, backend.buttons, backend.ui):
            part['generation'] += 1
    backend.on_swipe = fresh
    return backend, oracle, fresh


@pytest.mark.parametrize('drift', [False, True])
def test_same_fresh_list_after_one_missed_drag_defers_only_native_task(drift):
    backend, oracle, _ = scroll_host(drift)
    session = SimpleNamespace(discard_task_state=Mock(), trace=None)
    with pytest.raises(TaskCapabilityUnavailable) as pending:
        with semantic_task_scope(session, 'commission'):
            oracle.commission_scroll_next()
    cause = pending.value.cause
    assert isinstance(cause, SemanticNavigationPending)
    assert cause.semantic_id == 'commission/scroll'
    assert cause.receipt['before_position'] == cause.receipt['after_position']
    assert 0.5 < cause.receipt['before_position'] < 0.6
    assert cause.generation > cause.receipt['before_generation']
    assert tuple(cause.receipt['points']) == backend.swipes[0]
    assert backend.swipes[0][-1] == 1500
    assert session.last_task_error['navigation_receipt'] == cause.receipt
    assert session.last_task_error['generation'] == cause.generation
    assert len(backend.swipes) == 1
    assert session.last_task_outcome['outcome'] == 'navigation-pending'
    with semantic_task_scope(session, 'daily'):
        pass
    assert session.last_task_outcome['outcome'] == 'returned'


@pytest.mark.parametrize('case', ['stale', 'foreign-modal', 'ambiguous-handle',
                                'changed-type', 'foreground', 'same-generation'])
def test_unproven_or_unsafe_scroll_result_is_not_healthy_navigation(case):
    backend, oracle, fresh = scroll_host()
    def change():
        if case != 'same-generation':
            fresh()
        if case == 'stale':
            backend.snapshot['age_ms'] = 10001
        elif case == 'foreign-modal':
            backend.buttons['buttons'].append(make_button('custom_button_1(Clone)',
                'OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/button_container/custom_button_1(Clone)'))
            backend.buttons['button_count'] += 1
        elif case == 'ambiguous-handle':
            handle = next(i for i in backend.ui['images'] if i['path'].endswith('/scroll_bar/Image'))
            backend.ui['images'].append(deepcopy(handle))
            backend.ui['image_count'] += 1
        elif case == 'changed-type':
            for image in backend.ui['images']:
                if image['path'].endswith('/iconType$'):
                    image['sprite'] = 'different-row-type'
        elif case == 'foreground':
            backend.foreground = 'unrelated.package/Activity'
    backend.on_swipe = change
    with pytest.raises(SemanticGateClosed) as denied:
        oracle.commission_scroll_next()
    assert not isinstance(denied.value, SemanticNavigationPending)
    assert len(backend.swipes) == 1


@pytest.mark.parametrize('appears', [False, True])
def test_type_image_publication_does_not_turn_missed_scroll_into_global_failure(appears):
    backend, oracle, fresh = scroll_host()
    types = [deepcopy(i) for i in backend.ui['images'] if i['path'].endswith('/iconType$')]
    def remove_types():
        backend.ui['images'] = [i for i in backend.ui['images'] if not i['path'].endswith('/iconType$')]
        backend.ui['image_count'] = len(backend.ui['images'])
    if appears:
        remove_types()
    def change():
        fresh()
        if appears:
            backend.ui['images'].extend(types)
            backend.ui['image_count'] = len(backend.ui['images'])
        else:
            remove_types()
    backend.on_swipe = change
    with pytest.raises(SemanticNavigationPending) as pending:
        oracle.commission_scroll_next()
    assert pending.value.receipt['before_position'] == pending.value.receipt['after_position']
    assert len(backend.swipes) == 1
