"""A missing optional row type stays unavailable without hiding known rows."""
import pytest
from unittest.mock import Mock

from alas_headless import SemanticGateClosed
from alas_headless.oracle.errors import SemanticCommissionRowIncomplete
from alas_headless.adapter.task_lifecycle import semantic_task_scope
from tests.test_commission_urgent_rows import ROW, backend_for
from tests.test_adapter_task_lifecycle import session_with_task
from tests.semantic_support.observer_fixtures import make_image, make_oracle
from alas_headless import AlasSemanticAdapter
from alas_headless.adapter.semantic import commission as commission_ports


def test_missing_type_is_explicit_and_recovers_on_a_later_observation(monkeypatch):
    backend = missing_type_backend()
    oracle = make_oracle(backend)
    adapter = AlasSemanticAdapter(oracle, lambda: None)
    adapter.begin_commission()
    sleep = Mock(side_effect=AssertionError('known row fields must not wait for an unused type'))
    monkeypatch.setattr(commission_ports.time, 'sleep', sleep)
    row, = adapter.commission_rows()
    assert row.type_sprite is None
    assert row.name == 'NYB装备研发'
    with pytest.raises(SemanticGateClosed, match='type is unavailable'):
        oracle.click_commission_row(row.signature)
    backend.ui['images'].append(make_image(ROW + '/iconType$', 'jianduixunlian'))
    backend.ui['image_count'] = 2
    assert adapter.commission_rows()[0].type_sprite == 'jianduixunlian'
    sleep.assert_not_called()
    assert backend.taps == []


def test_persistently_incomplete_row_does_not_renew_navigation_window(monkeypatch):
    oracle = Mock()
    error = SemanticCommissionRowIncomplete(ROW + '/iconType$', 10)
    oracle.commission_rows.side_effect = error
    adapter = AlasSemanticAdapter(oracle, lambda: None)
    adapter.begin_commission()
    adapter._commission_context.passive_transition_until = 12.
    now = [11.95]
    monkeypatch.setattr(commission_ports.time, 'monotonic', lambda: now[0])
    monkeypatch.setattr(commission_ports.time, 'sleep', lambda interval: now.__setitem__(0, now[0]+interval))
    with pytest.raises(SemanticCommissionRowIncomplete) as caught:
        adapter.commission_rows()
    assert caught.value is error
    assert oracle.commission_rows.call_count == 1
    assert adapter._commission_context.passive_transition_until == 12.


def test_tab_click_refreshes_window_only_after_accepted_input(monkeypatch):
    oracle = Mock()
    adapter = AlasSemanticAdapter(oracle, lambda: None)
    adapter.begin_commission()
    monkeypatch.setattr(commission_ports.time, 'monotonic', lambda: 50.)
    receipt = adapter._click_commission('COMMISSION_URGENT', None, None, None)
    assert receipt is oracle.click_image.return_value
    oracle.click_image.assert_called_once_with('commission/nav/urgent')
    assert adapter._commission_context.passive_transition_until == 62.
    oracle.click_image.side_effect = SemanticGateClosed('blocked')
    monkeypatch.setattr(commission_ports.time, 'monotonic', lambda: 100.)
    with pytest.raises(SemanticGateClosed):
        adapter._click_commission('COMMISSION_DAILY', None, None, None)
    assert adapter._commission_context.passive_transition_until == 62.


def test_unclassified_row_failure_is_not_retried(monkeypatch):
    oracle = Mock()
    oracle.commission_rows.side_effect = SemanticGateClosed('ambiguous')
    adapter = AlasSemanticAdapter(oracle, lambda: None)
    adapter.begin_commission()
    sleep = Mock()
    monkeypatch.setattr(commission_ports.time, 'sleep', sleep)
    with pytest.raises(SemanticGateClosed, match='ambiguous'):
        adapter.commission_rows()
    assert oracle.commission_rows.call_count == 1
    sleep.assert_not_called()


def missing_type_backend():
    backend = backend_for('bgEmergence$')
    backend.ui['images'] = backend.ui['images'][:1]
    backend.ui['image_count'] = 1
    return backend


def test_missing_type_no_longer_defers_commission_or_unrelated_tasks():
    backend = missing_type_backend()
    oracle = make_oracle(backend)
    session, adapter, _, _ = session_with_task()
    remaining = adapter._action_ledger.remaining('campaign.grid_click')
    with semantic_task_scope(session, 'commission'):
        assert oracle.commission_rows()[0].type_sprite is None
    assert session.last_task_error is None
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
