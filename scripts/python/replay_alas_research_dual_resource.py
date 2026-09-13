"""Offline original-ALAS start/queue chain with explicit contract observations."""

import argparse
import ast
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "python"), str(ROOT)]
from alas_headless.alas_adapter import AlasSemanticAdapter
from alas_headless.semantic_oracle import ResearchProjectStatus
from alas_headless.semantic_sources import semantic_source_hashes
from tests.test_alas_adapter import FakeOracle, NamedButton


def replay(alas_root):
    sources = {}
    namespace = {
        "logger": SimpleNamespace(hr=lambda *a: None, info=lambda *a: None),
        "RESEARCH_QUEUE_ADD": NamedButton("RESEARCH_QUEUE_ADD"),
        "RESET_AVAILABLE": NamedButton("RESET_AVAILABLE"),
    }
    methods = {}
    for filename, names in {
        "research.py": ("research_project_start", "research_reset"),
        "rqueue.py": ("research_queue_add", "_research_queue_add_available"),
    }.items():
        path = alas_root / "module" / "research" / filename
        source = path.read_bytes()
        sources[str(path)] = hashlib.sha256(source).hexdigest()
        tree = ast.parse(source)
        for name in names:
            matches = [node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name == name]
            assert len(matches) == 1, name
            exec(compile(ast.Module(body=matches, type_ignores=[]), str(path), "exec"), namespace)
            methods[name] = namespace[name]

    oracle = FakeOracle()
    project = SimpleNamespace(name="Q-068-UL")
    oracle.research_project_values = [SimpleNamespace(
        slot=1, unity_index=1, code=project.name, status=ResearchProjectStatus.DETAIL,
    )]
    oracle.research_detail_value = SimpleNamespace(
        code=project.name, can_start=True, is_running=False, can_queue=False,
        is_finished=False, duration_seconds=1800,
        subtitle="小型项目", resource_id="gold", resource_owned=6000,
        resource_required=5000, requirement="",
        resource_costs=(SimpleNamespace(resource_id="gold", owned=6000, required=5000),
                        SimpleNamespace(resource_id="17033", owned=30, required=20)),
    )
    oracle.research_start_prompt_costs = lambda: (("17033", 20), ("gold", 5000))
    oracle.research_reset_available = lambda: False
    adapter = AlasSemanticAdapter(oracle, lambda: None, research_start_budget=1)
    adapter.begin_research()
    state = {"queued": False, "queue_prompt": False, "screenshots": 0}
    original_click = oracle.click
    def click(semantic_id):
        receipt = original_click(semantic_id)
        if semantic_id == "research/start/confirm":
            oracle.research_detail_value.is_running = True
            oracle.research_detail_value.can_queue = True
        elif semantic_id == "research/detail/queue":
            state["queue_prompt"] = True
            oracle.research_detail_value.can_queue = False
            oracle.enabled_values["research/detail/queue"] = False
        elif semantic_id == "research/queue/confirm":
            state["queued"] = True
        return receipt
    oracle.click = click
    def screenshot():
        state["screenshots"] += 1
        assert state["screenshots"] <= 5, "original queue loop did not advance"
    def handle_popup(_):
        if state["queue_prompt"]:
            adapter.click(NamedButton("POPUP_CONFIRM"))
            state["queue_prompt"] = False
            return True
        return False
    host = SimpleNamespace(
        projects=[project], device=SimpleNamespace(click=adapter.click, screenshot=screenshot),
        popup_interval_clear=lambda: None, interval_clear=lambda *a: None,
        interval_reset=lambda *a: None, is_research_stabled=lambda: state["queued"],
        ensure_research_center_stable=lambda: None, appear=lambda button, **kw: adapter.appear(button),
        handle_popup_confirm=handle_popup,
    )
    for name, method in methods.items():
        setattr(host, name, method.__get__(host))
    with patch("alas_headless.current_semantic_session", return_value=adapter), \
         patch("socket.socket", side_effect=AssertionError("offline replay network")), \
         patch("subprocess.Popen", side_effect=AssertionError("offline replay process")):
        assert host.research_reset() is False
        assert oracle.click_calls == []
        assert host.research_project_start(project)
    assert state["queued"] and host.research_project_started is project
    assert adapter._action_ledger.remaining("research.start") == 0
    assert oracle.click_calls == ["research/project/1", "research/detail/start", "research/start/confirm",
                                  "research/detail/queue", "research/queue/confirm"]
    return dict(passed=True, scope="original start and queue methods; contract observations; not full Research.run or live input",
                original_sources=sources, source_sha256=semantic_source_hashes(ROOT),
                exhausted_reset_returned_false=True, simulated_actions=oracle.click_calls,
                remaining_start_grant=0, android_input_injected=False)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--alas-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = replay(args.alas_root.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("PASS: original research start -> dual-resource confirm -> queue")
