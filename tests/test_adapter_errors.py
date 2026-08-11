import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from alas_headless.adapter import (
    ActionLeaseError,
    AdapterContractError,
    CapabilityClosureError,
    FlowScopeError,
    StaleFrameError,
    UnknownObservationError,
    UnsupportedPixelRead,
)
from alas_headless.semantic_oracle import SemanticGateClosed


ERRORS = (
    AdapterContractError,
    FlowScopeError,
    UnknownObservationError,
    UnsupportedPixelRead,
    StaleFrameError,
    CapabilityClosureError,
    ActionLeaseError,
)


class AdapterErrorTests(unittest.TestCase):
    def test_errors_are_classified_under_existing_fail_closed_boundary(self):
        codes = []
        messages = []
        for error_type in ERRORS:
            with self.subTest(error_type=error_type.__name__):
                error = error_type()
                self.assertIsInstance(error, SemanticGateClosed)
                self.assertIsInstance(error, AdapterContractError)
                self.assertEqual(str(error), error_type.safe_message)
                self.assertTrue(error_type.code)
                self.assertNotIn(" ", error_type.code)
                codes.append(error_type.code)
                messages.append(str(error))
        self.assertEqual(len(codes), len(set(codes)))
        self.assertEqual(len(messages), len(set(messages)))

    def test_messages_cannot_accept_payloads_or_sensitive_details(self):
        forbidden = (
            "account",
            "token",
            "password",
            "cookie",
            "phone",
            "email",
            "credential",
            "secret",
            "stdout",
            "stderr",
            "payload",
            "{",
            "}",
        )
        for error_type in ERRORS:
            with self.subTest(error_type=error_type.__name__):
                message = str(error_type()).lower()
                self.assertFalse(any(value in message for value in forbidden))
                with self.assertRaises(TypeError):
                    error_type("untrusted detail")

    def test_adapter_import_has_no_external_or_current_directory_side_effects(self):
        root = Path(__file__).resolve().parents[1]
        code = """
import builtins
import os
import socket
import subprocess

def reject(*args, **kwargs):
    raise AssertionError("external side effect during import")

builtins.open = reject
os.getenv = reject
socket.socket = reject
subprocess.run = reject

import alas_headless.adapter
"""
        with tempfile.TemporaryDirectory() as directory:
            environment = dict(os.environ)
            environment["PYTHONPATH"] = str(root / "python")
            environment["PYTHONDONTWRITEBYTECODE"] = "1"
            completed = subprocess.run(
                (sys.executable, "-c", code),
                cwd=directory,
                env=environment,
                capture_output=True,
                text=True,
                timeout=30,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual(list(Path(directory).iterdir()), [])


if __name__ == "__main__":
    unittest.main()
