"""Resume the original ALAS MailWhite delete branch at a retained confirmation."""

from __future__ import annotations

import dataclasses
import json
import os
from pathlib import Path
import sys
import traceback


ROOT = Path(__file__).resolve().parents[2]
ALAS_ROOT = ROOT / "artifacts/campaign-preparation/upstream"
OUTPUT = ROOT / "artifacts/semantic-cn-mail-delete-resume-20260927.json"
DRIVER = "506b76f698b5089aaa29c4e7908b48edb8532a44"


def main() -> int:
    if OUTPUT.exists():
        raise RuntimeError(f"output already exists: {OUTPUT}")
    seed = json.loads((ALAS_ROOT / "config/semantic_cn.json").read_text(encoding="utf-8"))
    if not seed["Freebies"]["Mail"]["DeleteCollected"]:
        raise RuntimeError("imported source strategy does not authorize mail deletion")
    os.environ.update(
        ALAS_SEMANTIC_MODE="1",
        ALAS_SEMANTIC_DRIVER_REVISION=DRIVER,
        ALAS_SEMANTIC_ADB="adb",
        ALAS_SEMANTIC_ALLOW_MAIL_MUTATIONS="1",
        ALAS_SEMANTIC_MAIL_MUTATION_BUDGET="2",
    )
    sys.path[:0] = [str(ROOT / "python"), str(ALAS_ROOT)]
    os.chdir(ALAS_ROOT)
    from alas import AzurLaneAutoScript
    from module.freebies.mail_white import MailWhite

    app = AzurLaneAutoScript("semantic_cn")
    app.config.bind("Freebies")
    session = app.device.semantic_adapter
    result = {"schema": "alas-headless.mail-delete-resume/v1", "passed": False, "actions": []}
    try:
        oracle = session.open().oracle
        state = oracle.read_state()
        result["before"] = {"pid": state.snapshot["pid"], "generation": state.generation,
                            "confirmation": oracle.mail_confirmation_kind()}
        if result["before"]["confirmation"] != "delete":
            raise RuntimeError("retained confirmation is not the reviewed mail deletion")
        original_click = oracle.click

        def record(target):
            receipt = original_click(target)
            result["actions"].append(dataclasses.asdict(receipt))
            OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            return receipt

        oracle.click = record
        flow = MailWhite(app.config, app.device)
        session.begin_mail()
        try:
            result["delete_return"] = flow._mail_delete(skip_first_screenshot=False)
            flow._mail_quit()
        finally:
            session.end_mail()
        state = oracle.read_state()
        result["after"] = {"pid": state.snapshot["pid"], "generation": state.generation,
                           "main_visible": oracle.main_page_visible(),
                           "confirmation": oracle.mail_confirmation_kind()}
        result["passed"] = bool(result["delete_return"] and result["after"]["main_visible"]
                                 and result["after"]["confirmation"] is None)
    except BaseException as exc:
        result["error"] = {"type": type(exc).__name__, "message": str(exc),
                           "traceback": traceback.format_exc()}
    finally:
        session.close()
        OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: result.get(key) for key in ("passed", "before", "after", "error")},
                     ensure_ascii=False, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
