"""Exercise original ALAS AUTO checkbox handling on a retained result menu."""

import argparse
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--alas-root", type=Path, required=True)
    parser.add_argument("--serial", required=True)
    parser.add_argument("--stage", required=True)
    parser.add_argument("--driver-revision", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    sys.path[:0] = [str(ROOT / "python"), str(args.alas_root.resolve())]
    os.chdir(args.alas_root)
    os.environ.update(ALAS_SEMANTIC_MODE="1", ALAS_SEMANTIC_ADB="F:/platform-tools/adb.exe",
                      ALAS_SEMANTIC_DRIVER_REVISION=args.driver_revision)
    from module.handler.fast_forward import FastForwardHandler
    from module.handler.assets import BOOK_CHECK_AUTO, BOOK_BOX_AUTO
    host = FastForwardHandler("semantic_e2e", task="Main")
    host.config.override(Emulator_Serial=args.serial)
    session = host.device.semantic_adapter
    oracle = session.open().oracle
    result = {"schema": "alas-headless.campaign-auto-book-live/v1", "passed": False,
              "serial": args.serial, "stage_context": args.stage, "cases": [],
              "sortie_inputs": 0}
    try:
        session.begin_campaign_pre_sortie(args.stage)
        state, _, before, count = oracle._campaign_2x_book_control("auto")
        if type(before) is not bool:
            raise RuntimeError("AUTO checkbox not present")
        result.update(pid=oracle.fingerprint.expected_pid, generation_before=state.generation,
                      before=before, book_count_before=count)
        for desired in (not before, before):
            host.device.screenshot()
            host.interval_clear(BOOK_CHECK_AUTO)
            handled = host._set_2x_book_status("on" if desired else "off", BOOK_CHECK_AUTO, BOOK_BOX_AUTO)
            state, button, observed, count = oracle._campaign_2x_book_control("auto")
            result["cases"].append(dict(desired=desired, observed=observed,
                handled=handled, generation=state.generation, path=button.path,
                raycast_top=button.raycast_top))
            if not handled or observed is not desired:
                raise RuntimeError("original AUTO switch postcondition failed")
        result["book_count_after"] = count
        result["passed"] = count == result["book_count_before"]
    except Exception as exc:
        result["error"] = type(exc).__name__ + ": " + str(exc)
    finally:
        session.end_campaign_pre_sortie()
        session.close()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
