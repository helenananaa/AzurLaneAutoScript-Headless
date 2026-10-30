"""Runner evidence survives a failed native task without reattributing cached results."""
from dataclasses import dataclass
from types import MappingProxyType, SimpleNamespace
import json

from scripts.python.run_alas_configured_task_live import storage_disassembly_evidence, parse_action_budgets


@dataclass(frozen=True)
class Result:
    data: object


def test_generic_budget_entry_accepts_gear_units_without_new_runner_task_logic():
    assert parse_action_budgets(['ALAS_SEMANTIC_STORAGE_DISASSEMBLE_BUDGET=17']) == {
        'ALAS_SEMANTIC_STORAGE_DISASSEMBLE_BUDGET': '17'}


def test_new_results_and_pending_mapping_proxies_are_serializable():
    session = SimpleNamespace(storage_equipment_disassembly_receipts=lambda: ('old', Result(MappingProxyType({'quantity':17}))),
        storage_equipment_disassembly_pending=lambda: Result(MappingProxyType({'already_spent':23})),
        _storage_equipment_destroy_last_observation={'generation':123})
    value = storage_disassembly_evidence(session, 1)
    assert value['storage_equipment_disassembly_receipts'] == [{'data':{'quantity':17}}]
    assert value['storage_equipment_disassembly_pending'] == {'data':{'already_spent':23}}
    assert json.loads(json.dumps(value))['storage_equipment_disassembly_last_observation']['generation'] == 123


def test_unknown_baseline_does_not_present_cached_history_as_new_task_results():
    session = SimpleNamespace(storage_equipment_disassembly_receipts=lambda: ('old',),
                              storage_equipment_disassembly_pending=lambda: None)
    assert storage_disassembly_evidence(session, None)['storage_equipment_disassembly_receipts'] is None


def test_one_failed_reader_does_not_hide_an_accepted_pending_input():
    def bad(): raise RuntimeError('result unavailable')
    session = SimpleNamespace(storage_equipment_disassembly_receipts=bad,
                              storage_equipment_disassembly_pending=lambda: {'quantity':23})
    value = storage_disassembly_evidence(session)
    assert value['storage_equipment_disassembly_pending'] == {'quantity':23}
    assert value['storage_equipment_disassembly_receipts_error'] == 'result unavailable'


def test_unrelated_or_older_session_needs_no_storage_port_to_record_other_tasks():
    assert storage_disassembly_evidence(object()) == {}
