from __future__ import annotations

import importlib.util
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "python" / "normalize_android_sbom.py"
SPEC = importlib.util.spec_from_file_location("normalize_android_sbom", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class AndroidSbomNormalizeTests(unittest.TestCase):
    def test_created_time_uses_locked_epoch(self) -> None:
        with TemporaryDirectory() as raw:
            path = Path(raw) / "sbom.spdx.json"
            path.write_text(json.dumps({
                "spdxVersion": "SPDX-2.3",
                "creationInfo": {"created": "2026-08-12T00:00:00Z"},
            }), encoding="utf-8")
            self.assertEqual(MODULE.main([
                "--sbom", str(path), "--source-date-epoch", "1731467710",
            ]), 0)
            value = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(value["creationInfo"]["created"], "2024-11-13T03:15:10Z")


if __name__ == "__main__":
    unittest.main()
