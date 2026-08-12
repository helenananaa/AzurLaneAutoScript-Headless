from __future__ import annotations

import unittest
from pathlib import Path


class AndroidBuildScriptTests(unittest.TestCase):
    @classmethod
    def script(cls) -> str:
        return (
            Path(__file__).resolve().parents[1]
            / "scripts"
            / "wsl"
            / "build-redroid-images.sh"
        ).read_text(encoding="utf-8")

    def test_aosp_envsetup_runs_without_nounset(self) -> None:
        script = self.script()
        expected = """set +u
    # shellcheck disable=SC1091
    source build/envsetup.sh
    lunch \"$lunch_target\"
    m -j\"$(nproc)\"
    m sbom -j\"$(nproc)\"
    set -u"""
        self.assertIn(expected, script)

    def test_build_caches_stay_on_the_dedicated_source_device(self) -> None:
        script = self.script()
        self.assertIn('export HOME="$source_root/.alas-build-home"', script)
        self.assertIn('export XDG_CACHE_HOME="$HOME/.cache"', script)
        self.assertIn('export GOCACHE="$XDG_CACHE_HOME/go-build"', script)
        self.assertIn('export CCACHE_DIR="$XDG_CACHE_HOME/ccache"', script)


if __name__ == "__main__":
    unittest.main()
