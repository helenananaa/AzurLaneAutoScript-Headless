"""A native equipment stack spends its item count atomically before input."""
import pytest

from alas_headless.adapter import ActionNotDispatched
from alas_headless.adapter.errors import ActionGrantExhausted, ActionLeaseError
from tests import test_adapter_ledger as ledger_support


def ledger(amount):
    return ledger_support.ActionLedgerTests().ledger(grants={'campaign.grid_click': amount})


def test_quantity_reserved_before_backend_and_default_unit_stays_one():
    book = ledger(24)
    result = book.dispatch('campaign.grid_click', lambda: book.remaining('campaign.grid_click'), units=23)
    assert result.value == 1 and result.remaining_after_dispatch == 1
    book.dispatch('campaign.grid_click', lambda: None)
    assert book.remaining('campaign.grid_click') == 0


def test_insufficient_quantity_never_calls_backend_or_debits_partially():
    book = ledger(22)
    called = []
    with pytest.raises((ActionGrantExhausted, ActionLeaseError)):
        book.dispatch('campaign.grid_click', lambda: called.append(True), units=23)
    assert book.remaining('campaign.grid_click') == 22 and not called


@pytest.mark.parametrize('units', [0, -1, True, 1.5])
def test_invalid_quantity_cannot_turn_into_free_input(units):
    book = ledger(23)
    with pytest.raises((ValueError, TypeError)):
        book.dispatch('campaign.grid_click', lambda: pytest.fail('input'), units=units)
    assert book.remaining('campaign.grid_click') == 23


@pytest.mark.parametrize('no_input', [False, True])
def test_only_explicit_zero_input_refunds_the_whole_quantity(no_input):
    book = ledger(23)
    def operation():
        error = RuntimeError('backend outcome')
        if no_input: raise ActionNotDispatched(error)
        raise error
    with pytest.raises(RuntimeError): book.dispatch('campaign.grid_click', operation, units=23)
    assert book.remaining('campaign.grid_click') == (23 if no_input else 0)
