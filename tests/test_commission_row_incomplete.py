"""Only a proven commission row awaiting its type Image can defer a task."""
import pytest

from alas_headless import SemanticGateClosed
from alas_headless.oracle.errors import SemanticCommissionRowIncomplete
from alas_headless.adapter.task_lifecycle import TaskCapabilityUnavailable, semantic_task_scope
from tests.test_commission_urgent_rows import ROW, backend_for
from tests.test_adapter_task_lifecycle import session_with_task
from tests.semantic_support.observer_fixtures import make_image, make_oracle


def missing_type_backend():
    backend = backend_for('bgEmergence$')
    backend.ui['images'] = backend.ui['images'][:1]
    backend.ui['image_count'] = 1
    return backend


def test_missing_type_defers_only_commission_and_next_task_runs():
    backend = missing_type_backend()
    oracle = make_oracle(backend)
    session, adapter, _, _ = session_with_task()
    remaining = adapter._action_ledger.remaining('campaign.grid_click')
    with pytest.raises(TaskCapabilityUnavailable) as caught:
        with semantic_task_scope(session, 'commission'):
            oracle.commission_rows()
    assert isinstance(caught.value.cause, SemanticCommissionRowIncomplete)
    assert caught.value.cause.path == ROW + '/iconType$'
    assert caught.value.cause.generation == 10
    assert session.last_task_outcome['outcome'] == 'observation-not-ready'
    assert backend.taps == []
    assert adapter._action_ledger.remaining('campaign.grid_click') == remaining
    with semantic_task_scope(session, 'research'):
        pass
    assert session.last_task_error is None
    backend.ui['images'].append(make_image(ROW + '/iconType$', 'jianduixunlian'))
    backend.ui['image_count'] = 2
    assert oracle.commission_rows()[0].type_sprite == 'jianduixunlian'


@pytest.mark.parametrize('damage', ['duplicate', 'identity', 'status', 'truncated', 'foreign'])
def test_ambiguous_malformed_or_foreign_state_stays_fatal(damage):
    backend = missing_type_backend()
    if damage == 'duplicate':
        backend.ui['images'] += [make_image(ROW + '/iconType$', 'jianduixunlian')] * 2
        backend.ui['image_count'] = 3
    elif damage == 'identity':
        backend.ui['texts'][1]['text'] = 'unknown'
    elif damage == 'status':
        backend.ui['images'][0]['sprite'] = 'unreviewed'
    elif damage == 'truncated':
        backend.ui['image_truncated'] = True
    else:
        backend.foreground = 'other.package/OtherActivity'
    with pytest.raises(SemanticGateClosed) as caught:
        make_oracle(backend).commission_rows()
    assert not isinstance(caught.value, SemanticCommissionRowIncomplete)
    assert backend.taps == []


def test_readiness_exception_does_not_defer_an_unrelated_task():
    session, _, _, _ = session_with_task()
    error = SemanticCommissionRowIncomplete(ROW + '/iconType$', 10)
    with pytest.raises(SemanticCommissionRowIncomplete):
        with semantic_task_scope(session, 'research'):
            raise error
    assert session.last_task_outcome['outcome'] == 'raised'
