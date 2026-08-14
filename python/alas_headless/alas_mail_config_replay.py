"""Input-free replay for the pinned ALAS white-mail configuration branches."""

from __future__ import annotations

import hashlib
import importlib
import itertools
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from .alas_mail_config_contract import validate_alas_mail_config
from .semantic_oracle import SemanticGateClosed


SCHEMA = "alas-headless.mail-config-replay/v1"


class _SemanticAdapterProbe:
    def __init__(self) -> None:
        self.events: list[str] = []

    def validate_mail_config(self, **values: object) -> None:
        validate_alas_mail_config(**values)
        self.events.append("validate")

    def begin_mail(self) -> None:
        self.events.append("begin")

    def end_mail(self) -> None:
        self.events.append("end")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_mail_class(alas_root: Path) -> type[Any]:
    root = str(alas_root.resolve())
    sys.path.insert(0, root)
    try:
        for name in tuple(sys.modules):
            if name == "module" or name.startswith("module."):
                del sys.modules[name]
        return importlib.import_module("module.freebies.mail_white").MailWhite
    finally:
        sys.path.remove(root)


def _run_case(mail_class: type[Any], values: tuple[bool, bool, bool, bool]) -> dict[str, Any]:
    merit, maintenance, trade_license, delete = values
    probe = _SemanticAdapterProbe()
    instance = mail_class.__new__(mail_class)
    instance.config = SimpleNamespace(
        Mail_ClaimMerit=merit,
        Mail_ClaimMaintenance=maintenance,
        Mail_ClaimTradeLicense=trade_license,
        Mail_DeleteCollected=delete,
    )
    instance.device = SimpleNamespace(semantic_adapter=probe)
    calls: list[dict[str, bool]] = []
    instance.ui_ensure = lambda page: None
    instance.appear = lambda button, **kwargs: True
    instance.mail_claim = lambda **kwargs: calls.append(dict(kwargs))
    result = instance.run()
    selected = merit or maintenance or trade_license
    if selected:
        if result is not True or probe.events != ["validate", "begin", "end"]:
            raise AssertionError("selected mail branch did not preserve run ownership")
        if calls != [{
            "merit": merit,
            "maintenance": maintenance,
            "trade_license": trade_license,
            "delete": delete,
        }]:
            raise AssertionError("mail selection changed before the final input stub")
    elif result is not False or probe.events != ["validate"] or calls:
        raise AssertionError("empty mail selection did not stop before navigation")
    return {
        "values": [merit, maintenance, trade_license, delete],
        "will_navigate": selected,
        "delete_requested": bool(selected and delete),
    }


def verify_mail_config(alas_root: Path) -> dict[str, Any]:
    alas_root = alas_root.resolve()
    mail_class = _load_mail_class(alas_root)
    cases = [
        _run_case(mail_class, values)
        for values in itertools.product((False, True), repeat=4)
    ]
    for bad in (None, 0, 1, "true"):
        try:
            validate_alas_mail_config(
                claim_merit=bad,
                claim_maintenance=False,
                claim_trade_license=False,
                delete_collected=False,
            )
        except SemanticGateClosed:
            continue
        raise AssertionError("invalid mail toggle was admitted")
    source = alas_root / "module" / "freebies" / "mail_white.py"
    return {
        "schema": SCHEMA,
        "passed": True,
        "field_count": 4,
        "combination_count": len(cases),
        "invalid_case_count": 4,
        "cases": cases,
        "mutation_budget": 0,
        "android_input_injected": False,
        "source_sha256": _sha256(source),
    }
