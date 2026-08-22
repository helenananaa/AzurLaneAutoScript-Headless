#!/usr/bin/env python3
"""Validate and render the ALAS configuration support matrix ledger."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any, Mapping, Sequence

import yaml

try:
    from .build_alas_patch_series import validate_manifest
except ImportError:  # Direct script execution.
    from build_alas_patch_series import validate_manifest  # type: ignore[no-redef]


ROOT = Path(__file__).resolve().parents[2]
LEDGER = ROOT / "integration" / "alas" / "support-matrix-ledger.json"
MATRIX = ROOT / "docs" / "alas-config-support-matrix.md"
SERIES = ROOT / "integration" / "alas" / "series" / "series.json"
COMBINED_PATCH = ROOT / "integration" / "alas" / "0001-semantic-oracle-hooks.patch"

SCHEMA = "alas-headless.support-matrix-ledger/v1"
DIMENSIONS = ("configuration", "observation", "action", "offline", "live")
DIMENSION_STATES = frozenset(
    ("complete", "partial", "missing", "unsupported", "not_applicable")
)
FIELD_CLASSES = (
    "complete",
    "live_partial",
    "offline_only",
    "unsupported",
    "declared_only",
)
CLASS_LABELS = {
    "complete": (
        "✅ 五维完整支持",
        "配置、观察、输入、离线和实机五个维度均已完成",
    ),
    "live_partial": (
        "◐ 有实机当前值/分支证据",
        "至少一个当前值或安全停止分支在实机出现；仍不是完整支持",
    ),
    "offline_only": (
        "🧪 只有离线路径证据",
        "有设置相关离线覆盖，但没有该设置的实机值证据",
    ),
    "unsupported": (
        "⊘ 当前未适配或无效",
        "任务级语义端口缺失，或配置当前不产生对应能力",
    ),
    "declared_only": (
        "☐ 只有配置声明/读取",
        "配置可以存在，但未找到设置相关的 Headless 闭环证据",
    ),
}
SYMBOLS = {
    "complete": "☑",
    "partial": "◐",
    "missing": "☐",
    "unsupported": "⊘",
    "not_applicable": "—",
}
PANEL_CODES = frozenset(("F", "L", "O", "P", "B", "M", "R"))
FIELD_HEADING = "### 7.1 字段级审计结论"
PANEL_TABLE_HEADER = "| # | 面板 | 配置组 | 当前 | 尚未闭环的配置范围与验收重点 |"
PANEL_TABLE_SEPARATOR = "|---:|---|---|:---:|---|"


class SupportMatrixError(RuntimeError):
    """The support matrix ledger, sources, or rendered document are inconsistent."""


def canonical_json(value: Mapping[str, Any]) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        indent=2,
        separators=(",", ": "),
    ) + "\n"


def _read_json(path: Path, label: str) -> Mapping[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SupportMatrixError(label + " is not readable JSON") from exc
    if not isinstance(value, dict):
        raise SupportMatrixError(label + " root must be an object")
    return value


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise SupportMatrixError("cannot hash " + str(path)) from exc
    return digest.hexdigest()


def _run(command: Sequence[str], *, cwd: Path | None = None) -> str:
    try:
        completed = subprocess.run(
            list(command),
            cwd=str(cwd) if cwd is not None else None,
            check=True,
            capture_output=True,
            text=True,
            timeout=120,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise SupportMatrixError("support matrix command failed") from exc
    return completed.stdout.strip()


def _git_blob(repository: Path, revision: str, relative_path: str) -> bytes:
    try:
        completed = subprocess.run(
            ("git", "-C", str(repository), "show", revision + ":" + relative_path),
            check=True,
            capture_output=True,
            timeout=120,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise SupportMatrixError("cannot read pinned ALAS configuration blob") from exc
    return completed.stdout


def _field_class(field: Mapping[str, Any]) -> str:
    dimensions = field["dimensions"]
    if field["support"] == "unsupported":
        return "unsupported"
    if all(
        dimensions[dimension] in ("complete", "not_applicable")
        for dimension in DIMENSIONS
    ):
        return "complete"
    if dimensions["live"] in ("complete", "partial"):
        return "live_partial"
    if dimensions["offline"] in ("complete", "partial"):
        return "offline_only"
    return "declared_only"


def _evidence_path(reference: str, *, root: Path) -> Path:
    raw_path = reference.split("::", 1)[0]
    path = Path(raw_path)
    if path.is_absolute() or ".." in path.parts:
        raise SupportMatrixError("evidence reference is unsafe")
    resolved = root.joinpath(*path.parts).resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError as exc:
        raise SupportMatrixError("evidence reference escapes repository") from exc
    return resolved


def _validate_evidence(reference: Any, *, root: Path) -> str:
    if not isinstance(reference, str) or not reference:
        raise SupportMatrixError("evidence reference is missing")
    if not _evidence_path(reference, root=root).is_file():
        raise SupportMatrixError("evidence reference does not exist: " + reference)
    return reference


def _validate_field(raw: Any, *, root: Path) -> Mapping[str, Any]:
    expected = {
        "path",
        "panels",
        "metadata",
        "values",
        "group_code",
        "status_label",
        "support",
        "dimensions",
        "evidence",
    }
    if not isinstance(raw, dict) or set(raw) != expected:
        raise SupportMatrixError("field ledger shape is invalid")
    path = raw["path"]
    if (
        not isinstance(path, str)
        or path.count(".") != 1
        or any(not part for part in path.split("."))
    ):
        raise SupportMatrixError("field path is malformed")
    panels = raw["panels"]
    if (
        not isinstance(panels, list)
        or not panels
        or any(not isinstance(panel, str) or not panel for panel in panels)
        or panels != list(dict.fromkeys(panels))
    ):
        raise SupportMatrixError("field panels are invalid")
    if raw["group_code"] not in PANEL_CODES:
        raise SupportMatrixError("field group code is unsupported")
    if raw["support"] not in ("supported", "unsupported"):
        raise SupportMatrixError("field support state is invalid")
    for key in ("metadata", "values", "status_label"):
        if not isinstance(raw[key], str) or not raw[key]:
            raise SupportMatrixError("field text cell is invalid")
    dimensions = raw["dimensions"]
    if not isinstance(dimensions, dict) or set(dimensions) != set(DIMENSIONS):
        raise SupportMatrixError("field dimensions are not canonical")
    if any(value not in DIMENSION_STATES for value in dimensions.values()):
        raise SupportMatrixError("field dimension state is invalid")
    if raw["support"] == "unsupported" and not any(
        value == "unsupported" for value in dimensions.values()
    ):
        raise SupportMatrixError("unsupported field has no unsupported dimension")
    evidence = raw["evidence"]
    if not isinstance(evidence, list):
        raise SupportMatrixError("field evidence must be a list")
    for reference in evidence:
        _validate_evidence(reference, root=root)
    return raw


def _validate_panel(raw: Any) -> Mapping[str, Any]:
    if not isinstance(raw, dict) or set(raw) != {"name", "groups", "status", "note"}:
        raise SupportMatrixError("panel ledger shape is invalid")
    if not isinstance(raw["name"], str) or not raw["name"]:
        raise SupportMatrixError("panel name is invalid")
    if (
        not isinstance(raw["groups"], list)
        or not raw["groups"]
        or any(not isinstance(group, str) or not group for group in raw["groups"])
    ):
        raise SupportMatrixError("panel groups are invalid")
    if raw["status"] not in PANEL_CODES:
        raise SupportMatrixError("panel status is invalid")
    if not isinstance(raw["note"], str) or not raw["note"]:
        raise SupportMatrixError("panel note is invalid")
    return raw


def _validate_promotions(
    promotions: Any,
    *,
    fields: Mapping[str, Mapping[str, Any]],
    root: Path,
) -> None:
    if not isinstance(promotions, list):
        raise SupportMatrixError("promotions must be a list")
    seen = set()
    rank = {"unsupported": 0, "missing": 1, "partial": 2, "complete": 3}
    for promotion in promotions:
        if not isinstance(promotion, dict) or set(promotion) != {
            "field",
            "dimensions",
            "evidence",
            "note",
        }:
            raise SupportMatrixError("promotion shape is invalid")
        field_path = promotion["field"]
        if field_path in seen or field_path not in fields:
            raise SupportMatrixError("promotion field is missing or duplicated")
        seen.add(field_path)
        promoted = promotion["dimensions"]
        if not isinstance(promoted, dict) or not promoted:
            raise SupportMatrixError("promotion dimensions are missing")
        if any(
            dimension not in DIMENSIONS or state not in ("partial", "complete")
            for dimension, state in promoted.items()
        ):
            raise SupportMatrixError("promotion dimension is invalid")
        current = fields[field_path]["dimensions"]
        for dimension, state in promoted.items():
            if current[dimension] not in rank or rank[current[dimension]] < rank[state]:
                raise SupportMatrixError("promotion is not reflected by the field ledger")
        evidence = promotion["evidence"]
        if not isinstance(evidence, list) or not evidence:
            raise SupportMatrixError("promoted field requires evidence")
        for reference in evidence:
            _validate_evidence(reference, root=root)
        if not isinstance(promotion["note"], str) or not promotion["note"]:
            raise SupportMatrixError("promotion equivalence note is missing")


def validate_ledger(
    ledger_path: Path = LEDGER,
    *,
    root: Path = ROOT,
) -> Mapping[str, Any]:
    ledger = _read_json(ledger_path, "support matrix ledger")
    expected_keys = {"schema", "source", "expected", "panels", "fields", "promotions"}
    if set(ledger) != expected_keys or ledger.get("schema") != SCHEMA:
        raise SupportMatrixError("support matrix ledger schema is unsupported")
    expected = ledger["expected"]
    if not isinstance(expected, dict) or set(expected) != {
        "panel_count",
        "field_count",
        "panel_field_instance_count",
    }:
        raise SupportMatrixError("support matrix expected counts are malformed")
    panels = tuple(_validate_panel(panel) for panel in ledger["panels"])
    fields = tuple(_validate_field(field, root=root) for field in ledger["fields"])
    if [panel["name"] for panel in panels] != sorted(panel["name"] for panel in panels):
        raise SupportMatrixError("panel ledger must be sorted")
    if [field["path"] for field in fields] != sorted(field["path"] for field in fields):
        raise SupportMatrixError("field ledger must be sorted")
    if len({panel["name"] for panel in panels}) != len(panels):
        raise SupportMatrixError("panel names are duplicated")
    if len({field["path"] for field in fields}) != len(fields):
        raise SupportMatrixError("field paths are duplicated")
    actual_counts = {
        "panel_count": len(panels),
        "field_count": len(fields),
        "panel_field_instance_count": sum(len(field["panels"]) for field in fields),
    }
    if actual_counts != expected:
        raise SupportMatrixError("ledger counts differ from expected counts")
    field_map = {field["path"]: field for field in fields}
    _validate_promotions(ledger["promotions"], fields=field_map, root=root)
    source = ledger["source"]
    if not isinstance(source, dict) or set(source) != {
        "upstream_commit",
        "adapter_evidence_commit",
        "matrix_introduced_commit",
        "config_sha256",
        "patch_series",
    }:
        raise SupportMatrixError("ledger source metadata is malformed")
    commits = (
        source["upstream_commit"],
        source["adapter_evidence_commit"],
        source["matrix_introduced_commit"],
    )
    if any(not isinstance(commit, str) or re.fullmatch(r"[0-9a-f]{40}", commit) is None for commit in commits):
        raise SupportMatrixError("ledger commit is malformed")
    hashes = source["config_sha256"]
    if not isinstance(hashes, dict) or set(hashes) != {
        "module/config/argument/task.yaml",
        "module/config/argument/args.json",
        "config/template.json",
    }:
        raise SupportMatrixError("config hash ledger is malformed")
    if any(not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None for value in hashes.values()):
        raise SupportMatrixError("config hash is malformed")
    series = source["patch_series"]
    if not isinstance(series, dict) or set(series) != {
        "member_count",
        "manifest_sha256",
        "combined_sha256",
    }:
        raise SupportMatrixError("patch series ledger is malformed")
    return ledger


def validate_patch_series(ledger: Mapping[str, Any], *, root: Path = ROOT) -> Mapping[str, Any]:
    manifest = root / "integration" / "alas" / "series" / "series.json"
    combined = root / "integration" / "alas" / "0001-semantic-oracle-hooks.patch"
    upstream, members = validate_manifest(manifest, root=root)
    source = ledger["source"]
    recorded = source["patch_series"]
    actual = {
        "member_count": len(members),
        "manifest_sha256": _sha256(manifest),
        "combined_sha256": _sha256(combined),
    }
    if upstream != source["upstream_commit"] or actual != recorded:
        raise SupportMatrixError("patch series metadata differs from ledger")
    if combined.read_bytes() != b"".join(member[4] for member in members):
        raise SupportMatrixError("combined patch differs from authoritative members")
    return actual


def _configuration_surface(source: Path) -> Mapping[str, Any]:
    task_path = source / "module" / "config" / "argument" / "task.yaml"
    args_path = source / "module" / "config" / "argument" / "args.json"
    template_path = source / "config" / "template.json"
    try:
        task = yaml.safe_load(task_path.read_text(encoding="utf-8"))
        arguments = json.loads(args_path.read_text(encoding="utf-8"))
        json.loads(template_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError, yaml.YAMLError) as exc:
        raise SupportMatrixError("ALAS configuration source is unreadable") from exc
    if not isinstance(task, dict) or not isinstance(arguments, dict):
        raise SupportMatrixError("ALAS configuration source shape is invalid")
    panels: dict[str, list[str]] = {}
    for section in task.values():
        if not isinstance(section, dict):
            raise SupportMatrixError("task.yaml section is invalid")
        for panel, groups in section.get("tasks", {}).items():
            if panel in panels or not isinstance(groups, list):
                raise SupportMatrixError("task.yaml panel is duplicated or invalid")
            panels[panel] = list(groups)
    usage: dict[str, list[str]] = {}
    for panel, groups in panels.items():
        panel_args = arguments.get(panel)
        if not isinstance(panel_args, dict):
            raise SupportMatrixError("args.json lacks task panel " + panel)
        for group in groups:
            group_args = panel_args.get(group)
            if not isinstance(group_args, dict):
                raise SupportMatrixError("args.json lacks task group " + panel + "." + group)
            if group == "Storage":
                continue
            for field in group_args:
                path = group + "." + field
                usage.setdefault(path, []).append(panel)
    hashes = {
        "module/config/argument/task.yaml": _sha256(task_path),
        "module/config/argument/args.json": _sha256(args_path),
        "config/template.json": _sha256(template_path),
    }
    return {"panels": panels, "usage": usage, "hashes": hashes}


def validate_configuration_source(
    ledger: Mapping[str, Any],
    source: Path,
) -> Mapping[str, Any]:
    surface = _configuration_surface(source)
    expected_panels = {panel["name"]: panel["groups"] for panel in ledger["panels"]}
    if surface["panels"] != expected_panels:
        raise SupportMatrixError("task panel surface differs from ledger")
    expected_usage = {
        field["path"]: sorted(field["panels"]) for field in ledger["fields"]
    }
    actual_usage = {
        path: sorted(panels) for path, panels in surface["usage"].items()
    }
    if actual_usage != expected_usage:
        missing = sorted(set(surface["usage"]) - set(expected_usage))
        if missing:
            raise SupportMatrixError(
                "new configuration fields require explicit unsupported ledger entries: "
                + ", ".join(missing)
            )
        raise SupportMatrixError("configuration field usage differs from ledger")
    if surface["hashes"] != ledger["source"]["config_sha256"]:
        raise SupportMatrixError("configuration source hashes differ from ledger")
    return {
        "panel_count": len(surface["panels"]),
        "field_count": len(surface["usage"]),
        "panel_field_instance_count": sum(len(value) for value in surface["usage"].values()),
        "config_sha256": surface["hashes"],
    }


def validate_upstream_repository(
    ledger: Mapping[str, Any],
    repository: Path,
) -> Mapping[str, Any]:
    if not (repository / ".git").exists():
        raise SupportMatrixError("upstream repository is not a Git checkout")
    with tempfile.TemporaryDirectory(prefix="alas-support-source-") as directory:
        checkout = Path(directory)
        for relative_path in ledger["source"]["config_sha256"]:
            target = checkout.joinpath(*Path(relative_path).parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(
                _git_blob(
                    repository,
                    ledger["source"]["upstream_commit"],
                    relative_path,
                )
            )
        _run(
            (
                "git",
                "apply",
                "--include=module/config/argument/args.json",
                "--",
                str(COMBINED_PATCH.resolve()),
            ),
            cwd=checkout,
        )
        return validate_configuration_source(ledger, checkout)


def _render_panel_summary(ledger: Mapping[str, Any]) -> str:
    counts = Counter(panel["status"] for panel in ledger["panels"])
    names: dict[str, list[str]] = {code: [] for code in PANEL_CODES}
    for panel in ledger["panels"]:
        names[panel["status"]].append(panel["name"])
    labels = (
        ("F", "✅ 完整支持"),
        ("L", "🟢 主路径已完成、全配置未完成"),
        ("O", "🧪 仅离线完成"),
        ("P", "🟡 部分完成"),
        ("B", "🧱 已到边界、尚未完成"),
        ("M", "🔴 尚未完成"),
    )
    lines = ["| 完成度 | 数量 | 面板 |", "|---|---:|---|"]
    for code, label in labels:
        panel_names = "、".join(names[code]) if names[code] else "暂无"
        lines.append(
            f"| {label}（`{code}`） | **{counts[code]} / {len(ledger['panels'])}** | {panel_names} |"
        )
    return "\n".join(lines)


def _render_panel_table(ledger: Mapping[str, Any], current: str) -> str:
    """Render the duplicated human-readable panel table from the ledger.

    The table keeps the upstream UI order already recorded in the document,
    while status, groups, and notes come only from the canonical ledger.  This
    prevents a promoted panel from drifting between the summary and detail
    sections without forcing the canonical JSON to abandon sorted keys.
    """

    lines = current.splitlines()
    try:
        start = lines.index(PANEL_TABLE_HEADER)
    except ValueError as exc:
        raise SupportMatrixError("matrix panel table heading is missing") from exc
    if start + 1 >= len(lines) or lines[start + 1] != PANEL_TABLE_SEPARATOR:
        raise SupportMatrixError("matrix panel table separator is malformed")
    end = start + 2
    rows: list[tuple[int, str]] = []
    while end < len(lines) and lines[end].startswith("|"):
        match = re.match(r"^\|\s*(\d+)\s*\|\s*([^|]+?)\s*\|", lines[end])
        if match is None:
            raise SupportMatrixError("matrix panel table row is malformed")
        rows.append((int(match.group(1)), match.group(2).strip()))
        end += 1

    panel_map = {panel["name"]: panel for panel in ledger["panels"]}
    if [number for number, _name in rows] != list(range(1, len(rows) + 1)):
        raise SupportMatrixError("matrix panel table order is malformed")
    row_names = [name for _number, name in rows]
    if len(row_names) != len(set(row_names)) or set(row_names) != set(panel_map):
        raise SupportMatrixError("matrix panel table differs from ledger panels")

    rendered = [PANEL_TABLE_HEADER, PANEL_TABLE_SEPARATOR]
    for number, name in rows:
        panel = panel_map[name]
        rendered.append(
            "| "
            + " | ".join(
                (
                    str(number),
                    name,
                    ", ".join(panel["groups"]),
                    panel["status"],
                    panel["note"],
                )
            )
            + " |"
        )
    updated = "\n".join(lines[:start] + rendered + lines[end:])
    return updated + ("\n" if current.endswith("\n") else "")


def _render_field_section(ledger: Mapping[str, Any]) -> str:
    fields = ledger["fields"]
    counts = Counter(_field_class(field) for field in fields)
    lines = [
        FIELD_HEADING,
        "",
        "| 结论 | 字段数 | 含义 |",
        "|---|---:|---|",
    ]
    for classification in FIELD_CLASSES:
        label, meaning = CLASS_LABELS[classification]
        lines.append(f"| {label} | **{counts[classification]} / {len(fields)}** | {meaning} |")
    lines.extend(
        (
            "",
            "| 配置组.字段 | 使用面板 | 类型/显示元数据 | 默认值与可选值 | 组级现状 | 配置读取 | 语义观察 | 输入闭环 | 离线证据 | 实机证据 |",
            "|---|---|---|---|:---:|:---:|:---:|:---:|:---:|:---:|",
        )
    )
    for field in fields:
        dimensions = field["dimensions"]
        cells = (
            f"`{field['path']}`",
            ", ".join(field["panels"]),
            field["metadata"],
            field["values"],
            f"`{field['group_code']}`/{field['status_label']}",
            *(SYMBOLS[dimensions[dimension]] for dimension in DIMENSIONS),
        )
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines) + "\n"


def render_matrix(ledger: Mapping[str, Any], current: str) -> str:
    if FIELD_HEADING not in current:
        raise SupportMatrixError("matrix field heading is missing")
    current = _render_panel_table(ledger, current)
    prefix = current.split(FIELD_HEADING, 1)[0].rstrip() + "\n\n"
    rendered = prefix + _render_field_section(ledger)
    source = ledger["source"]
    rendered = re.sub(
        r"^Headless 适配(?:证据)?提交：`[0-9a-f]{40}`[ \t]*$",
        "Headless 适配证据提交：`" + source["adapter_evidence_commit"] + "`",
        rendered,
        count=1,
        flags=re.MULTILINE,
    )
    rendered = re.sub(
        r"当前工作树基于 `[^`]+`；[^\n]+",
        "当前账本的功能证据基线为 `"
        + source["adapter_evidence_commit"][:7]
        + "`，矩阵首次提交为 `"
        + source["matrix_introduced_commit"][:7]
        + "`；authoritative patch series 的成员数与哈希由校验器现场验证。离线通过不会自动提升任何实机复核栏。",
        rendered,
        count=1,
    )
    panel_summary = _render_panel_summary(ledger)
    rendered = re.sub(
        r"\| 完成度 \| 数量 \| 面板 \|\n\|---\|---:\|---\|\n(?:\|.*\|\n){6}",
        panel_summary + "\n",
        rendered,
        count=1,
    )
    for relative, digest in source["config_sha256"].items():
        filename = Path(relative).name
        rendered = re.sub(
            rf"(\| `{re.escape(relative)}` \| `)[0-9A-Fa-f]{{64}}(` \|)",
            rf"\g<1>{digest.upper()}\2",
            rendered,
            count=1,
        )
        if filename not in rendered:
            raise SupportMatrixError("matrix config source row is missing")
    return rendered


def verify(
    *,
    ledger_path: Path = LEDGER,
    matrix_path: Path = MATRIX,
    root: Path = ROOT,
    alas_source: Path | None = None,
    upstream_repository: Path | None = None,
) -> Mapping[str, Any]:
    ledger = validate_ledger(ledger_path, root=root)
    patch = validate_patch_series(ledger, root=root)
    try:
        current = matrix_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise SupportMatrixError("support matrix document is unreadable") from exc
    expected_document = render_matrix(ledger, current)
    if current != expected_document:
        raise SupportMatrixError("support matrix document differs from ledger rendering")
    source_result = None
    if alas_source is not None and upstream_repository is not None:
        raise SupportMatrixError("choose only one ALAS configuration source mode")
    if alas_source is not None:
        source_result = validate_configuration_source(ledger, alas_source.resolve())
    if upstream_repository is not None:
        source_result = validate_upstream_repository(ledger, upstream_repository.resolve())
    field_counts = Counter(_field_class(field) for field in ledger["fields"])
    return {
        "schema": "alas-headless.support-matrix-verification/v1",
        "counts": ledger["expected"],
        "field_classes": {key: field_counts[key] for key in FIELD_CLASSES},
        "patch_series": patch,
        "configuration_source_verified": source_result is not None,
        "configuration_source": source_result,
    }


def write_generated(
    *,
    ledger_path: Path = LEDGER,
    matrix_path: Path = MATRIX,
    root: Path = ROOT,
) -> None:
    ledger = validate_ledger(ledger_path, root=root)
    validate_patch_series(ledger, root=root)
    current = matrix_path.read_text(encoding="utf-8")
    matrix_path.write_text(render_matrix(ledger, current), encoding="utf-8", newline="\n")
    ledger_path.write_text(canonical_json(ledger), encoding="utf-8", newline="\n")


def refresh_patch_series_metadata(
    *,
    ledger_path: Path = LEDGER,
    root: Path = ROOT,
) -> None:
    ledger = dict(validate_ledger(ledger_path, root=root))
    source = dict(ledger["source"])
    manifest = root / "integration" / "alas" / "series" / "series.json"
    combined = root / "integration" / "alas" / "0001-semantic-oracle-hooks.patch"
    upstream, members = validate_manifest(manifest, root=root)
    if upstream != source["upstream_commit"]:
        raise SupportMatrixError("patch series upstream differs from ledger")
    source["patch_series"] = {
        "member_count": len(members),
        "manifest_sha256": _sha256(manifest),
        "combined_sha256": _sha256(combined),
    }
    ledger["source"] = source
    ledger_path.write_text(canonical_json(ledger), encoding="utf-8", newline="\n")


def parse_args(argv: Sequence[str] = ()) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ledger", type=Path, default=LEDGER)
    parser.add_argument("--matrix", type=Path, default=MATRIX)
    parser.add_argument("--alas-source", type=Path)
    parser.add_argument("--upstream-repository", type=Path)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--refresh-patch-series", action="store_true")
    return parser.parse_args(list(argv) if argv else None)


def main(argv: Sequence[str] = ()) -> int:
    arguments = parse_args(argv)
    if arguments.refresh_patch_series:
        if arguments.alas_source is not None or arguments.upstream_repository is not None:
            raise SupportMatrixError(
                "--refresh-patch-series does not accept an external ALAS source"
            )
        refresh_patch_series_metadata(ledger_path=arguments.ledger)
        write_generated(ledger_path=arguments.ledger, matrix_path=arguments.matrix)
        return 0
    if arguments.write:
        if arguments.alas_source is not None or arguments.upstream_repository is not None:
            raise SupportMatrixError("--write does not accept an external ALAS source")
        write_generated(ledger_path=arguments.ledger, matrix_path=arguments.matrix)
        return 0
    result = verify(
        ledger_path=arguments.ledger,
        matrix_path=arguments.matrix,
        alas_source=arguments.alas_source,
        upstream_repository=arguments.upstream_repository,
    )
    print(canonical_json(result), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
