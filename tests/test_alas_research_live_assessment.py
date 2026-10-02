"""The native queue can start free projects before a paid policy sample."""

import importlib.util
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/python/run_alas_research_resource_policy_live_validation.py"
SPEC = importlib.util.spec_from_file_location("research_live_assessment", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_paid_project_after_free_projects_counts_as_policy_sample():
    free = {"expected_prompt_costs": [], "expected_prompt_cost": {"resource_id": None}}
    paid = {"expected_prompt_costs": [{"resource_id": "gold", "required": 3000}]}
    assert MODULE._has_resource_cost([free, free, paid])
    assert not MODULE._has_resource_cost([free, free])
