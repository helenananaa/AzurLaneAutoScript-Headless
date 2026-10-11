"""Deterministic replay of pinned ALAS tactical configuration decisions."""

from __future__ import annotations

import ast
import hashlib
import importlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from .alas_tactical_config_contract import validate_alas_tactical_config
from .semantic_oracle import SemanticGateClosed


SCHEMA = "alas-headless.tactical-config-replay/v1"
EXPECTED_CONSUMERS = {
    "Tactical.TacticalFilter": {"_tactical_books_choose"},
    "Tactical.RapidTrainingSlot": {"handle_rapid_training"},
    "ControlExpOverflow": {"_tactical_books_filter_exp"},
    "AddNewStudent.Enable": {"tactical_class_receive"},
    "AddNewStudent.Favorite": {"select_suitable_ship"},
    "AddNewStudent.MinLevel": {"select_suitable_ship"},
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _defaults() -> dict[str, object]:
    return {
        "tactical_filter": "SameT4 > SameT3 > SameT2 > SameT1 > first",
        "rapid_training_slot": "do_not_use",
        "control_exp_overflow_enable": True,
        "t1_allow": 200,
        "t2_allow": 200,
        "t3_allow": 100,
        "t4_allow": 100,
        "add_new_student_enable": False,
        "add_new_student_favorite": False,
        "add_new_student_min_level": 50,
    }


def _config(**overrides: object) -> SimpleNamespace:
    values = {
        "Tactical_TacticalFilter": "SameT4 > SameT3 > SameT2 > SameT1 > first",
        "Tactical_RapidTrainingSlot": "do_not_use",
        "ControlExpOverflow_Enable": True,
        "ControlExpOverflow_T1Allow": 200,
        "ControlExpOverflow_T2Allow": 200,
        "ControlExpOverflow_T3Allow": 100,
        "ControlExpOverflow_T4Allow": 100,
        "AddNewStudent_Enable": False,
        "AddNewStudent_Favorite": False,
        "AddNewStudent_MinLevel": 50,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _verify_args(alas_root: Path) -> None:
    path = alas_root / "module" / "config" / "argument" / "args.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    panel = document.get("Tactical")
    if not isinstance(panel, dict):
        raise AssertionError("Tactical panel is absent")
    tactical = panel.get("Tactical")
    if not isinstance(tactical, dict):
        raise AssertionError("Tactical configuration group is absent")
    tactical_filter = tactical.get("TacticalFilter")
    rapid_slot = tactical.get("RapidTrainingSlot")
    overflow = panel.get("ControlExpOverflow")
    student = panel.get("AddNewStudent")
    if not isinstance(overflow, dict) or set(overflow) != {
        "Enable",
        "T1Allow",
        "T2Allow",
        "T3Allow",
        "T4Allow",
    }:
        raise AssertionError("ControlExpOverflow field surface drifted")
    if not isinstance(student, dict) or set(student) != {
        "Enable",
        "Favorite",
        "MinLevel",
    }:
        raise AssertionError("AddNewStudent field surface drifted")
    if overflow["Enable"].get("type") != "checkbox":
        raise AssertionError("ControlExpOverflow.Enable type drifted")
    if student["Enable"].get("type") != "checkbox" or student["Favorite"].get(
        "type"
    ) != "checkbox":
        raise AssertionError("AddNewStudent boolean surface drifted")
    if not isinstance(tactical_filter, dict) or tactical_filter.get("type") != "textarea":
        raise AssertionError("TacticalFilter surface drifted")
    expected_slots = ["do_not_use", "slot_1", "slot_2", "slot_3", "slot_4"]
    if (
        not isinstance(rapid_slot, dict)
        or rapid_slot.get("type") != "select"
        or rapid_slot.get("option") != expected_slots
    ):
        raise AssertionError("RapidTrainingSlot surface drifted")


def _verify_consumers(path: Path) -> dict[str, list[str]]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found = {name: set() for name in EXPECTED_CONSUMERS}
    tactical_class = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "RewardTacticalClass"
    )
    for node in tactical_class.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.name == "_validate_tactical_config":
            continue
        attributes = {
            child.attr
            for child in ast.walk(node)
            if isinstance(child, ast.Attribute) and isinstance(child.ctx, ast.Load)
        }
        if "Tactical_TacticalFilter" in attributes or "tactical_filter" in attributes:
            found["Tactical.TacticalFilter"].add(node.name)
        if (
            "Tactical_RapidTrainingSlot" in attributes
            or "rapid_training_slot" in attributes
        ):
            found["Tactical.RapidTrainingSlot"].add(node.name)
        if (
            "ControlExpOverflow_Enable" in attributes
            or "control_exp_overflow_enable" in attributes
            or any(
                isinstance(child, ast.JoinedStr)
                and "ControlExpOverflow_T" in ast.unparse(child)
                for child in ast.walk(node)
            )
        ):
            found["ControlExpOverflow"].add(node.name)
        for suffix, snapshot_name in (
            ("Enable", "add_new_student_enable"),
            ("Favorite", "add_new_student_favorite"),
            ("MinLevel", "add_new_student_min_level"),
        ):
            if f"AddNewStudent_{suffix}" in attributes or snapshot_name in attributes:
                found[f"AddNewStudent.{suffix}"].add(node.name)
    if found != EXPECTED_CONSUMERS:
        raise AssertionError("Tactical runtime consumer surface drifted")
    return {name: sorted(values) for name, values in found.items()}


def _load_original(alas_root: Path):
    root = str(alas_root.resolve())
    sys.path.insert(0, root)
    try:
        for name in tuple(sys.modules):
            if name == "module" or name.startswith("module."):
                del sys.modules[name]
        module = importlib.import_module("module.tactical.tactical_class")
        return module, module.RewardTacticalClass
    finally:
        sys.path.remove(root)


def _book_filter_case(
    module: Any,
    tactical_type: type[Any],
    *,
    enabled: bool,
    total: int = 5_800,
) -> list[str]:
    allowances = {1: 200, 2: 200, 3: 100, 4: 100}
    books = [SimpleNamespace(identifier="special", tier=1, exp_value=100)]
    for tier, allowance in allowances.items():
        books.append(
            SimpleNamespace(
                identifier=f"t{tier}-boundary",
                tier=tier,
                exp_value=100 + allowance,
            )
        )
        books.append(
            SimpleNamespace(
                identifier=f"t{tier}-over",
                tier=tier,
                exp_value=101 + allowance,
            )
        )
    host = object.__new__(tactical_type)
    host.config = _config(ControlExpOverflow_Enable=enabled)
    host.device = SimpleNamespace(image=None)
    host.books = module.SelectedGrids(books)
    old_skill_exp = module.SKILL_EXP
    module.SKILL_EXP = SimpleNamespace(
        ocr=lambda image: (5_700, max(total - 5_700, 0), total)
    )
    try:
        tactical_type._tactical_books_filter_exp(host)
    finally:
        module.SKILL_EXP = old_skill_exp
    return [book.identifier for book in host.books]


def _semantic_student_case(module: Any, tactical_type: type[Any]) -> dict[str, Any]:
    calls = []

    class Session:
        def tactical_select_suitable_ship(self, *values: object) -> bool:
            calls.append(tuple(values))
            return True

    host = object.__new__(tactical_type)
    host.config = _config(
        AddNewStudent_Enable=True,
        AddNewStudent_Favorite=True,
        AddNewStudent_MinLevel="50",
    )
    host.dock_select_index = 2
    package = importlib.import_module("alas_headless")
    old_current = package.current_semantic_session
    package.current_semantic_session = lambda: Session()
    try:
        result = tactical_type.select_suitable_ship(host)
    finally:
        package.current_semantic_session = old_current
    if result is not True or len(calls) != 1:
        raise AssertionError("original tactical student selection drifted")
    guard_present = hasattr(tactical_type, "_validate_tactical_config")
    expected = (True, 50, 2) if guard_present else (50, 2)
    if calls[0] != expected:
        raise AssertionError("tactical favorite/min-level forwarding drifted")
    return {
        "call": calls[0],
        "favorite_forwarded": guard_present,
        "min_level": 50,
        "start_index": 2,
    }


class ReplayBook:
    def __init__(self, identifier: str, *, same: bool, genre: str, tier: int):
        self.identifier = identifier
        self.same_str = "same" if same else "unknown"
        self.genre_str = genre
        self.tier_str = f"T{tier}"

    def __str__(self) -> str:
        prefix = "Same" if self.same_str == "same" else ""
        return f"{prefix}{self.genre_str}{self.tier_str}"


def _book_filter_fixtures() -> list[ReplayBook]:
    return [
        ReplayBook("first-red-t1", same=False, genre="Red", tier=1),
        ReplayBook("same-blue-t4", same=True, genre="Blue", tier=4),
        ReplayBook("same-red-t3", same=True, genre="Red", tier=3),
        ReplayBook("blue-t2", same=False, genre="Blue", tier=2),
        ReplayBook("yellow-t2", same=False, genre="Yellow", tier=2),
        ReplayBook("red-t2", same=False, genre="Red", tier=2),
    ]


def _book_choose_case(
    module: Any, tactical_type: type[Any], expression: str
) -> dict[str, Any]:
    events: list[tuple[object, ...]] = []
    host = object.__new__(tactical_type)
    host.config = _config(Tactical_TacticalFilter=expression)
    host.books = module.SelectedGrids(_book_filter_fixtures())
    host._tactical_books_get = lambda: host.books
    host._tactical_books_filter_exp = lambda: None
    host._tactical_book_select = lambda book: events.append(
        ("select", getattr(book, "identifier", str(book)))
    )

    class Device:
        @staticmethod
        def click_record_clear() -> None:
            events.append(("clear",))

        @staticmethod
        def click(button: object) -> None:
            events.append(("click", getattr(button, "name", str(button))))

    host.device = Device()
    if tactical_type._tactical_books_choose(host) is not True:
        raise AssertionError("original tactical book chooser did not finish")
    selected = [event[1] for event in events if event[0] == "select"]
    final_click = events[-1][1]
    return {"selected": selected, "final_click": final_click}


def _rapid_training_case(
    tactical_type: type[Any], slot: str, *, available: bool
) -> dict[str, Any]:
    events: list[tuple[object, ...]] = []
    host = object.__new__(tactical_type)
    host.config = _config(Tactical_RapidTrainingSlot=slot)

    def appear(button: object, **kwargs: object) -> bool:
        events.append(("appear", kwargs.get("offset"), kwargs.get("interval")))
        return available

    host.appear = appear
    host.interval_clear = lambda button, **kwargs: events.append(
        ("interval_clear", getattr(button, "name", str(button)), kwargs.get("interval"))
    )
    host.device = SimpleNamespace(
        click=lambda button: events.append(
            ("click", getattr(button, "name", str(button)))
        )
    )
    result = tactical_type.handle_rapid_training(host)
    return {"result": result, "events": events}


def _verify_original(module: Any, tactical_type: type[Any]) -> dict[str, Any]:
    disabled = _book_filter_case(module, tactical_type, enabled=False)
    enabled = _book_filter_case(module, tactical_type, enabled=True)
    not_max = _book_filter_case(module, tactical_type, enabled=False, total=4_000)
    if disabled != ["special"]:
        raise AssertionError("disabled tactical overflow decision drifted")
    expected_enabled = ["special"] + [
        f"t{tier}-boundary" for tier in range(1, 5)
    ]
    if enabled != expected_enabled:
        raise AssertionError("enabled tactical overflow boundaries drifted")
    if len(not_max) != 9:
        raise AssertionError("non-max tactical book list was filtered")

    student = _semantic_student_case(module, tactical_type)
    filter_cases = {
        expression: _book_choose_case(module, tactical_type, expression)
        for expression in (
            "SameT4 > first",
            "BlueT2 > first",
            "Yellow > first",
            "T1 > first",
            "first",
            "RedT4",
            "Blue‑T2 ＞ first",
        )
    }
    expected_filter_targets = {
        "SameT4 > first": "same-blue-t4",
        "BlueT2 > first": "blue-t2",
        "Yellow > first": "yellow-t2",
        "T1 > first": "first-red-t1",
        "first": "first-red-t1",
        "Blue‑T2 ＞ first": "blue-t2",
    }
    for expression, target in expected_filter_targets.items():
        if filter_cases[expression]["selected"][-1] != target:
            raise AssertionError("original tactical filter priority drifted")
    if "TACTICAL_CLASS_CANCEL" not in filter_cases["RedT4"]["final_click"]:
        raise AssertionError("original tactical no-match cancellation drifted")

    rapid_cases = {
        slot: _rapid_training_case(tactical_type, slot, available=True)
        for slot in ("do_not_use", "slot_1", "slot_2", "slot_3", "slot_4")
    }
    expected_offsets = {
        "slot_1": (-20, -20, 20, 20),
        "slot_2": (200, -20, 240, 20),
        "slot_3": (420, -20, 460, 20),
        "slot_4": (640, -20, 680, 20),
    }
    if rapid_cases["do_not_use"] != {"result": False, "events": []}:
        raise AssertionError("do-not-use rapid training drifted")
    for slot, offset in expected_offsets.items():
        case = rapid_cases[slot]
        if case["result"] is not True or case["events"][0] != (
            "appear",
            offset,
            1,
        ):
            raise AssertionError("rapid training slot mapping drifted")
    unavailable = _rapid_training_case(tactical_type, "slot_3", available=False)
    if unavailable["result"] is not False or len(unavailable["events"]) != 1:
        raise AssertionError("unavailable rapid training branch drifted")
    guard_present = hasattr(tactical_type, "_validate_tactical_config")
    if guard_present:
        host = object.__new__(tactical_type)
        host.config = _config(AddNewStudent_Enable=1)
        try:
            tactical_type.tactical_class_receive(host)
        except SemanticGateClosed:
            pass
        else:
            raise AssertionError("patched tactical receive admitted invalid config")
        host = object.__new__(tactical_type)
        host.config = _config(Tactical_RapidTrainingSlot="slot_5")
        host.appear = lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("invalid rapid slot reached observation")
        )
        try:
            tactical_type.handle_rapid_training(host)
        except SemanticGateClosed:
            pass
        else:
            raise AssertionError("patched rapid training admitted invalid config")
        host = object.__new__(tactical_type)
        host.config = _config(Tactical_TacticalFilter="BlueT2junk")
        host._tactical_books_get = lambda: (_ for _ in ()).throw(
            AssertionError("invalid tactical filter reached book observation")
        )
        try:
            tactical_type._tactical_books_choose(host)
        except SemanticGateClosed:
            pass
        else:
            raise AssertionError("patched tactical chooser admitted invalid config")
    return {
        "overflow_disabled": disabled,
        "overflow_enabled": enabled,
        "non_max_count": len(not_max),
        "student": student,
        "filters": filter_cases,
        "rapid_training": rapid_cases,
        "rapid_training_unavailable": unavailable,
        "patched_guard_present": guard_present,
    }


def verify_tactical_config(alas_root: Path) -> dict[str, Any]:
    alas_root = alas_root.resolve()
    _verify_args(alas_root)
    source = alas_root / "module" / "tactical" / "tactical_class.py"
    consumers = _verify_consumers(source)
    module, tactical_type = _load_original(alas_root)
    decisions = _verify_original(module, tactical_type)

    accepted = 0
    for overflow in (False, True):
        for add_student in (False, True):
            for favorite in (False, True):
                for min_level in (1, 50, 125):
                    values = _defaults()
                    values.update(
                        control_exp_overflow_enable=overflow,
                        add_new_student_enable=add_student,
                        add_new_student_favorite=favorite,
                        add_new_student_min_level=min_level,
                    )
                    validate_alas_tactical_config(**values)
                    accepted += 1
    for field in ("t1_allow", "t2_allow", "t3_allow", "t4_allow"):
        for value in (0, 5_800):
            values = _defaults()
            values[field] = value
            validate_alas_tactical_config(**values)
            accepted += 1
    for value in ("1", "125"):
        values = _defaults()
        values["add_new_student_enable"] = True
        values["add_new_student_min_level"] = value
        validate_alas_tactical_config(**values)
        accepted += 1
    for value in ("do_not_use", "slot_1", "slot_2", "slot_3", "slot_4"):
        values = _defaults()
        values["rapid_training_slot"] = value
        validate_alas_tactical_config(**values)
        accepted += 1
    for value in (
        "first",
        "SameT4 > BlueT2 > first",
        "sameblue-t4 ＞ first",
        "Red",
        "T1",
        "Same",
    ):
        values = _defaults()
        values["tactical_filter"] = value
        validate_alas_tactical_config(**values)
        accepted += 1

    invalid_count = 0
    invalids = (
        ("control_exp_overflow_enable", 1),
        ("t1_allow", -1),
        ("t2_allow", 5_801),
        ("t3_allow", True),
        ("t4_allow", "100"),
        ("add_new_student_enable", 0),
        ("add_new_student_favorite", 1),
        ("add_new_student_min_level", 0),
        ("add_new_student_min_level", 126),
        ("add_new_student_min_level", True),
        ("add_new_student_min_level", "1e2"),
        ("add_new_student_min_level", None),
        ("rapid_training_slot", "slot_5"),
        ("rapid_training_slot", 1),
        ("rapid_training_slot", None),
        ("tactical_filter", ""),
        ("tactical_filter", "BlueT2 >> first"),
        ("tactical_filter", "BlueT2junk"),
        ("tactical_filter", "-"),
        ("tactical_filter", None),
    )
    for field, value in invalids:
        values = _defaults()
        values["add_new_student_enable"] = True
        values[field] = value
        try:
            validate_alas_tactical_config(**values)
        except SemanticGateClosed:
            invalid_count += 1
        else:
            raise AssertionError("invalid tactical configuration was admitted")

    return {
        "schema": SCHEMA,
        "passed": True,
        "field_count": 10,
        "panel_count": 1,
        "accepted_case_count": accepted,
        "invalid_case_count": invalid_count,
        "runtime_consumers": consumers,
        "original_decisions": decisions,
        "temporary_config_only": True,
        "mutation_budget": 0,
        "android_input_injected": False,
        "source_sha256": {
            "args": _sha256(
                alas_root / "module" / "config" / "argument" / "args.json"
            ),
            "tactical_class": _sha256(source),
        },
    }
