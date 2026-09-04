"""Source inventory shared by semantic audits and future validation receipts.

Historical receipts retain their original hashes. New receipts record the
implementation files as well as the public adapter/oracle entry points.
"""

from __future__ import annotations

import hashlib
from pathlib import Path


def semantic_source_paths(root: Path, component: str | None = None) -> tuple[Path, ...]:
    """Return deterministic source paths, including newly added task modules."""
    package = root / "python" / "alas_headless"
    components = {
        "adapter": (
            package / "alas_adapter.py", package / "adapter" / "semantic",
            package / "adapter" / "task_lifecycle.py",
        ),
        "oracle": (package / "semantic_oracle.py", package / "oracle"),
    }
    selected = components.values() if component is None else (components[component],)
    paths = []
    for sources in selected:
        for source in sources:
            if source.suffix == ".py":
                paths.append(source)
            else:
                paths.extend(source.rglob("*.py"))
    return tuple(sorted(paths, key=lambda path: path.relative_to(root).as_posix()))


def semantic_source_hashes(root: Path) -> dict[str, str]:
    """Hash each source separately so a capability change remains reviewable."""
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in semantic_source_paths(root)
    }
