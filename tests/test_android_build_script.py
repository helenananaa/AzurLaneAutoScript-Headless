from __future__ import annotations

import unittest
from pathlib import Path


class AndroidBuildScriptTests(unittest.TestCase):
    def test_aosp_envsetup_runs_without_nounset(self) -> None:
        script = (
            Path(__file__).resolve().parents[1]
            / "scripts"
            / "wsl"
            / "build-redroid-images.sh"
        ).read_text(encoding="utf-8")
        expected = """set +u
    # shellcheck disable=SC1091
    source build/envsetup.sh
    lunch \"$lunch_target\"
    set -u"""
        self.assertIn(expected, script)


if __name__ == "__main__":
    unittest.main()
