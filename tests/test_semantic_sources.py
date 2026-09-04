import ast
import hashlib
from pathlib import Path

from alas_headless.semantic_sources import semantic_source_hashes, semantic_source_paths
from scripts.python.audit_alas_adapter_baseline import _class_methods, _parse_python


def test_inventory_includes_new_modules_and_detects_task_edits(tmp_path):
    package = tmp_path / "python" / "alas_headless"
    files = {
        "alas_adapter.py": "# adapter facade\n",
        "semantic_oracle.py": "# oracle facade\n",
        "adapter/semantic/research.py": "answer = 1\n",
        "adapter/task_lifecycle.py": "# shared task boundary\n",
        "oracle/research.py": "answer = 2\n",
    }
    for name, text in files.items():
        path = package / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    before = semantic_source_hashes(tmp_path)
    assert len(before) == 5
    task = package / "oracle" / "research.py"
    task.write_text("answer = 3\n", encoding="utf-8")
    new_task = package / "oracle" / "commission.py"
    new_task.write_text("# new capability\n", encoding="utf-8")
    after = semantic_source_hashes(tmp_path)
    key = task.relative_to(tmp_path).as_posix()
    assert after[key] == hashlib.sha256(task.read_bytes()).hexdigest()
    assert before[key] != after[key]
    facade = "python/alas_headless/alas_adapter.py"
    assert after[facade] == before[facade]
    assert new_task.relative_to(tmp_path).as_posix() in after
    assert list(after) == sorted(after)
    assert semantic_source_paths(tmp_path, "adapter") == (
        package / "adapter" / "semantic" / "research.py",
        package / "adapter" / "task_lifecycle.py",
        package / "alas_adapter.py",
    )


def test_baseline_lists_inherited_public_ports_after_module_split():
    root = Path(__file__).resolve().parents[1]
    tree = ast.Module(
        body=[
            node
            for path in semantic_source_paths(root, "adapter")
            for node in _parse_python(path)[1].body
        ],
        type_ignores=[],
    )
    adapter = _class_methods(tree, "AlasSemanticAdapter")
    session = _class_methods(tree, "AlasSemanticSession")
    expected = {"appear", "click", "research_projects", "operation_siren_state"}
    assert expected <= set(adapter)
    assert {"from_environment", "refresh_frame", "research_projects"} <= set(session)
    assert adapter == tuple(sorted(set(adapter)))
