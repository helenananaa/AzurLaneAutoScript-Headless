from __future__ import annotations

import unittest
from pathlib import Path


class RedroidRollbackScriptTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = (
            Path(__file__).resolve().parents[1]
            / "scripts" / "wsl" / "qualify-redroid-image-rollback.sh"
        ).read_text(encoding="utf-8")

    def test_cross_arch_privileged_execution_is_forbidden(self) -> None:
        self.assertIn("privileged Redroid rollback requires a native-architecture host", self.text)
        self.assertNotIn("binfmt-emulated-functional-only", self.text)

    def test_docker_platform_is_explicit(self) -> None:
        self.assertIn('docker pull --platform "$platform"', self.text)
        self.assertIn('docker run -d --name "$container" --platform "$platform"', self.text)


if __name__ == "__main__":
    unittest.main()
