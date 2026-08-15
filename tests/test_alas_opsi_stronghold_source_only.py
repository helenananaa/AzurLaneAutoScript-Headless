import ast
import unittest
from pathlib import Path
from scripts.python.verify_alas_opsi_stronghold_source_only import verify_clean_upstream

ROOT = Path(__file__).resolve().parents[1]
PINNED_UPSTREAM = Path(r"H:\program\AzurLaneAutoScript-upstream-readonly")

class AlasOpsiStrongholdSourceOnlyTests(unittest.TestCase):
    def test_pinned_source_audit_and_headless_gate(self):
        if not PINNED_UPSTREAM.joinpath("module/os/tasks/stronghold.py").is_file(): self.skipTest("local pinned ALAS verification tree is unavailable")
        result = verify_clean_upstream(PINNED_UPSTREAM)
        self.assertTrue(result["passed"]); self.assertEqual(result["outcome"], "source-only-audit; headless-fail-closed-skip"); self.assertEqual(result["gate_decisions"], {"headless": [], "raw_upstream": ["load", "stronghold"]}); self.assertEqual(result["mutation_budget"], 0); self.assertFalse(result["android_input_injected"])
    def test_sources_compile(self):
        for relative in ("python/alas_headless/alas_opsi_stronghold_admission.py", "python/alas_headless/alas_opsi_stronghold_source_audit.py", "scripts/python/verify_alas_opsi_stronghold_source_only.py"):
            ast.parse(ROOT.joinpath(relative).read_text(encoding="utf-8"))
