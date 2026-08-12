from __future__ import annotations

import importlib.util
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from alas_headless.android_image_source import AndroidImageSourceLock


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "python" / (
    "rebind_android_build_source_lock.py"
)
SPEC = importlib.util.spec_from_file_location("source_lock_rebind", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class AndroidSourceLockRebindTests(unittest.TestCase):
    def test_only_legacy_lunch_targets_may_be_rebound(self) -> None:
        root = Path(__file__).resolve().parents[1]
        new_path = root / "integration" / "runtime" / "android-image-source-lock.example.json"
        new_value = json.loads(new_path.read_text(encoding="utf-8"))
        old_value = json.loads(json.dumps(new_value))
        old_value["products"] = MODULE.LEGACY_PRODUCTS
        old_sha = MODULE.canonical_sha256(old_value)
        with TemporaryDirectory() as raw:
            directory = Path(raw)
            old_path = directory / "old.json"
            old_path.write_text(json.dumps(old_value), encoding="utf-8")
            marker = directory / "marker"
            marker.write_text(old_sha + "\n", encoding="utf-8")
            projects = new_value["redroid"]["projects"] + new_value["redroid"]["webview_projects"]
            manifest = directory / "resolved.xml"
            manifest.write_text(
                "<manifest>" + "".join(
                    "<project name='{0}' path='{1}' revision='{2}'/>".format(
                        item["name"], item["path"], item["commit"]
                    ) for item in projects
                ) + "</manifest>",
                encoding="utf-8",
            )
            output = directory / "rebind.json"
            self.assertEqual(MODULE.main([
                "--old-source-lock", str(old_path), "--new-source-lock", str(new_path),
                "--resume-marker", str(marker), "--resolved-manifest", str(manifest),
                "--output", str(output),
            ]), 0)
            self.assertEqual(
                marker.read_text(encoding="utf-8").strip(),
                AndroidImageSourceLock.from_path(new_path).sha256,
            )
            self.assertFalse(json.loads(output.read_text())["source_content_changed"])


if __name__ == "__main__":
    unittest.main()
