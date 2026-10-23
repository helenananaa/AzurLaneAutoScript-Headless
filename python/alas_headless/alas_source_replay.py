"""Compile original ALAS decision methods without loading their device bases.

Only offline verifiers use this helper. Method bodies and decorators are kept
unchanged; callers supply original lightweight dependencies and replay hosts.
This does not instantiate an ALAS task or qualify its runtime inheritance tree.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any


def load_class_methods(
    path: Path,
    owner: str,
    methods: tuple[str, ...],
    namespace: dict[str, Any],
    *,
    optional: tuple[str, ...] = (),
) -> type[Any]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    original = next(
        (node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == owner),
        None,
    )
    if original is None:
        raise AssertionError(f"missing ALAS class {owner} in {path}")
    selected = [
        node for node in original.body
        if isinstance(node, ast.FunctionDef) and node.name in methods + optional
    ]
    missing = set(methods) - {node.name for node in selected}
    if missing:
        raise AssertionError(f"missing ALAS methods {owner}: {sorted(missing)}")
    replay = ast.ClassDef(
        name=owner, bases=[], keywords=[], body=selected, decorator_list=[]
    )
    module = ast.fix_missing_locations(ast.Module(body=[replay], type_ignores=[]))
    exec(compile(module, str(path), "exec"), namespace)
    return namespace[owner]
