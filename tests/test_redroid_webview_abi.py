from __future__ import annotations

import importlib.util
import unittest
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "python" / (
    "verify_redroid_webview_abi.py"
)
SPEC = importlib.util.spec_from_file_location("verify_redroid_webview_abi", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class RedroidWebViewAbiTests(unittest.TestCase):
    def make_apk(self, directory: Path, entries: dict[str, bytes]) -> Path:
        apk = directory / "webview.apk"
        with zipfile.ZipFile(apk, "w") as archive:
            for name, payload in entries.items():
                archive.writestr(name, payload)
        return apk

    def test_accepts_x86_64_only_webview(self) -> None:
        with TemporaryDirectory() as raw:
            apk = self.make_apk(Path(raw), {
                "AndroidManifest.xml": b"manifest",
                "lib/x86_64/libwebviewchromium.so": b"x86-64-webview",
                "lib/x86_64/libcrashpad_handler_trampoline.so": b"crashpad",
            })
            result = MODULE.verify(apk)
            self.assertEqual(result["outcome"], "pass")
            self.assertEqual(result["blockers"], [])
            self.assertEqual(result["unexpected_native_entries"], [])

    def test_rejects_retained_x86_payload(self) -> None:
        with TemporaryDirectory() as raw:
            apk = self.make_apk(Path(raw), {
                "lib/x86/libwebviewchromium.so": b"x86-webview",
                "lib/x86_64/libwebviewchromium.so": b"x86-64-webview",
            })
            result = MODULE.verify(apk)
            self.assertEqual(result["outcome"], "fail")
            self.assertIn("non-x86_64-native-payload-present", result["blockers"])
            self.assertEqual(
                result["unexpected_native_entries"],
                ["lib/x86/libwebviewchromium.so"],
            )

    def test_rejects_missing_x86_64_provider_library(self) -> None:
        with TemporaryDirectory() as raw:
            apk = self.make_apk(Path(raw), {
                "lib/x86_64/libcrashpad_handler_trampoline.so": b"crashpad",
            })
            result = MODULE.verify(apk)
            self.assertEqual(result["outcome"], "fail")
            self.assertIn("x86_64-webview-library-missing", result["blockers"])


if __name__ == "__main__":
    unittest.main()
