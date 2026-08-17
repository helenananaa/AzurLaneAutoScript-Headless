import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

import yaml

from scripts.python.verify_alas_support_matrix import (
    LEDGER,
    MATRIX,
    ROOT,
    SupportMatrixError,
    canonical_json,
    parse_args,
    render_matrix,
    validate_configuration_source,
    validate_ledger,
    verify,
)


class AlasSupportMatrixTests(unittest.TestCase):
    def test_checked_in_ledger_renders_exact_document_and_counts(self):
        result = verify()
        self.assertEqual(
            result["counts"],
            {
                "panel_count": 60,
                "field_count": 278,
                "panel_field_instance_count": 1217,
            },
        )
        self.assertEqual(sum(result["field_classes"].values()), 278)
        self.assertEqual(result["field_classes"]["complete"], 19)
        self.assertEqual(result["patch_series"]["member_count"], 40)
        ledger = validate_ledger()
        document = MATRIX.read_text(encoding="utf-8")
        self.assertEqual(render_matrix(ledger, document), document)

    def test_ledger_is_canonical_and_promotions_have_real_evidence(self):
        ledger = validate_ledger()
        self.assertEqual(LEDGER.read_text(encoding="utf-8"), canonical_json(ledger))
        self.assertTrue(ledger["promotions"])
        for promotion in ledger["promotions"]:
            self.assertTrue(promotion["evidence"])
            self.assertTrue(promotion["note"])
            for reference in promotion["evidence"]:
                self.assertTrue((ROOT / reference.split("::", 1)[0]).is_file())

    def test_missing_promotion_evidence_is_rejected(self):
        ledger = copy.deepcopy(validate_ledger())
        ledger["promotions"][0]["evidence"] = []
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ledger.json"
            path.write_text(canonical_json(ledger), encoding="utf-8")
            with self.assertRaisesRegex(SupportMatrixError, "requires evidence"):
                validate_ledger(path, root=ROOT)

    def test_configuration_surface_matches_ledger_and_rejects_new_fields(self):
        ledger = copy.deepcopy(validate_ledger())
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory)
            task_path = source / "module" / "config" / "argument" / "task.yaml"
            args_path = source / "module" / "config" / "argument" / "args.json"
            template_path = source / "config" / "template.json"
            task_path.parent.mkdir(parents=True)
            template_path.parent.mkdir(parents=True)
            task_document = {
                "All": {
                    "menu": "collapse",
                    "page": "setting",
                    "tasks": {
                        panel["name"]: panel["groups"] for panel in ledger["panels"]
                    },
                }
            }
            argument_document = {
                panel["name"]: {group: {} for group in panel["groups"]}
                for panel in ledger["panels"]
            }
            for field in ledger["fields"]:
                group, name = field["path"].split(".")
                for panel in field["panels"]:
                    argument_document[panel][group][name] = {
                        "type": "input",
                        "value": None,
                    }
            task_path.write_text(
                yaml.safe_dump(task_document, allow_unicode=True, sort_keys=False),
                encoding="utf-8",
            )
            args_path.write_text(
                json.dumps(argument_document, ensure_ascii=False, sort_keys=True),
                encoding="utf-8",
            )
            template_path.write_text("{}\n", encoding="utf-8")
            ledger["source"]["config_sha256"] = {
                "module/config/argument/task.yaml": hashlib.sha256(
                    task_path.read_bytes()
                ).hexdigest(),
                "module/config/argument/args.json": hashlib.sha256(
                    args_path.read_bytes()
                ).hexdigest(),
                "config/template.json": hashlib.sha256(
                    template_path.read_bytes()
                ).hexdigest(),
            }
            result = validate_configuration_source(ledger, source)
            self.assertEqual(result["field_count"], 278)
            self.assertEqual(result["panel_field_instance_count"], 1217)

            first_panel = ledger["panels"][0]
            first_group = first_panel["groups"][0]
            argument_document[first_panel["name"]][first_group]["NewField"] = {
                "type": "input",
                "value": None,
            }
            args_path.write_text(
                json.dumps(argument_document, ensure_ascii=False, sort_keys=True),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(SupportMatrixError, "explicit unsupported"):
                validate_configuration_source(ledger, source)

    def test_document_drift_is_detected(self):
        ledger = validate_ledger()
        document = MATRIX.read_text(encoding="utf-8")
        drifted = document.replace(
            "`OneClickRetire.KeepLimitBreak`",
            "`OneClickRetire.KeepLimitBreak_DRIFT`",
            1,
        )
        self.assertNotEqual(render_matrix(ledger, drifted), drifted)

    def test_write_and_patch_refresh_are_explicit_exclusive_modes(self):
        self.assertTrue(parse_args(("--write",)).write)
        self.assertTrue(
            parse_args(("--refresh-patch-series",)).refresh_patch_series
        )
        with self.assertRaises(SystemExit):
            parse_args(("--write", "--refresh-patch-series"))


if __name__ == "__main__":
    unittest.main()
