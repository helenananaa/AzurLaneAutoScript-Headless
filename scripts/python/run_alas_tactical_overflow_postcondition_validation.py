#!/usr/bin/env python3
"""Validate a completed Tactical overflow dispatch without another assignment."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
import traceback
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[2]
for path in (ROOT, ROOT / "python"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from alas_headless.alas_adapter import AlasSemanticSession
from scripts.python.run_alas_tactical_new_student_live_validation import (
    _read_json,
    _write_json,
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate(
    *,
    prior_receipt: Path,
    serial: str,
    driver_revision: str,
    expected_skill: str,
) -> Mapping[str, Any]:
    result: dict[str, Any] = {"passed": False}
    actions: list[str] = []
    try:
        prior = _read_json(prior_receipt)
        dispatches = prior.get("dispatches")
        applications = prior.get("overflow_filter_applications")
        if not (
            prior.get("passed") is False
            and prior.get("error")
            == "AssertionError: configured filter selected no typed tactical book"
            and isinstance(dispatches, list)
            and len(dispatches) == 1
            and dispatches[0].get("capability") == "tactical.assign"
            and dispatches[0].get("receipt", {}).get("semantic_id")
            == "tactical/course/confirm"
            and isinstance(applications, list)
            and len(applications) == 1
            and applications[0].get("progress") == "5750/5800"
        ):
            raise AssertionError("prior receipt is not the reviewed overflow dispatch")
        after_books = applications[0].get("after", [])
        if not any(
            book.get("tier") == 4 and book.get("exp_value") == 1500
            for book in after_books
        ):
            raise AssertionError("configured T4 overflow did not retain its book")

        with AlasSemanticSession(
            serial=serial, driver_revision=driver_revision
        ) as adapter:
            oracle = adapter.oracle
            if oracle.main_page_visible():
                receipt = oracle.click("main/more")
                actions.append(receipt.semantic_id)
                oracle.wait_for(
                    "reward/page/back", 15, minimum_generation=receipt.generation
                )
            receipt = oracle.click("reward/tactical/go")
            actions.append(receipt.semantic_id)
            oracle.wait_for(
                "tactical/page/back", 15, minimum_generation=receipt.generation
            )
            ui_state = oracle.read_ui_state()
            suffix = "/skill/name_Text"
            matches = tuple(
                text
                for text in ui_state.texts
                if text.active_in_hierarchy
                and text.active_and_enabled
                and text.path.endswith(suffix)
                and text.text.strip() == expected_skill
            )
            if len(matches) != 1:
                raise AssertionError("expected running overflow skill is not unique")
            root = matches[0].path[: -len(suffix)]

            def exact_text(path_suffix: str) -> str:
                values = tuple(
                    text.text.strip()
                    for text in ui_state.texts
                    if text.active_in_hierarchy
                    and text.active_and_enabled
                    and text.path == root + path_suffix
                )
                if len(values) != 1:
                    raise AssertionError("running card text is absent or ambiguous")
                return values[0]

            progress = exact_text("/skill/next")
            timer = exact_text("/timer_Text")
            if progress != "5750/5800" or re.fullmatch(
                r"[0-9]{2}:[0-9]{2}:[0-9]{2}", timer
            ) is None:
                raise AssertionError("overflow course postcondition is malformed")
            back = oracle.click("tactical/page/back")
            actions.append(back.semantic_id)
            oracle.wait_for(
                "reward/page/back", 15, minimum_generation=back.generation
            )
            exit_receipt = oracle.click("reward/page/back")
            actions.append(exit_receipt.semantic_id)
            time.sleep(0.75)
            if not oracle.main_page_visible():
                raise AssertionError("overflow postcondition did not restore main")
            result.update(
                {
                    "prior_receipt": prior_receipt.name,
                    "prior_receipt_sha256": _sha256(prior_receipt),
                    "prior_source_sha256": prior.get("source_sha256"),
                    "expected_skill": expected_skill,
                    "physical_card_root": root,
                    "progress": progress,
                    "remaining": timer,
                    "anonymous_card_identity_boundary": True,
                    "actions": actions,
                    "main_page_visible": True,
                    "passed": True,
                }
            )
    except BaseException as exc:
        result["error"] = type(exc).__name__ + ": " + str(exc)
        result["traceback"] = traceback.format_exc()
    return {
        "schema": "alas-headless.tactical-overflow-postcondition-validation/v1",
        "serial": serial,
        "driver_revision": driver_revision,
        **result,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prior-receipt", type=Path, required=True)
    parser.add_argument("--serial", required=True)
    parser.add_argument("--driver-revision", required=True)
    parser.add_argument("--expected-skill", required=True)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    result = validate(
        prior_receipt=arguments.prior_receipt.resolve(),
        serial=arguments.serial,
        driver_revision=arguments.driver_revision,
        expected_skill=arguments.expected_skill,
    )
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    _write_json(arguments.output.resolve(), result)
    print(json.dumps(result, ensure_ascii=False, indent=2), end="\n")
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
