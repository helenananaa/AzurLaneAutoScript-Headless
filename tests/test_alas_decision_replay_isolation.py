"""Offline decision replays must work without device/OCR dependencies."""

from importlib.abc import MetaPathFinder
from pathlib import Path
import sys

import pytest

from alas_test_source import patched_alas_root
from alas_headless.alas_event_general_config_replay import verify_event_general_config
from alas_headless.alas_hp_control_config_replay import verify_hp_control_config
from alas_headless.alas_submarine_config_replay import verify_submarine_config


class _RejectDeviceImports(MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        for prefix in ("module.device", "module.ocr", "lxml", "cnocr"):
            if fullname == prefix or fullname.startswith(prefix + "."):
                raise AssertionError(f"offline decision replay imported {fullname}")
        return None


@pytest.mark.parametrize("patched", [False, True], ids=["pinned", "patched"])
@pytest.mark.parametrize("verify", [
    verify_hp_control_config, verify_submarine_config, verify_event_general_config,
], ids=["hp", "submarine", "event"])
def test_original_decisions_run_without_device_imports(patched, verify, monkeypatch):
    root = Path(__file__).resolve().parents[2] / "AzurLaneAutoScript-upstream-readonly"
    if not (root / "module/config/config.py").is_file():
        pytest.skip("pinned ALAS checkout is unavailable")
    if patched:
        root = patched_alas_root()
    monkeypatch.setattr(sys, "meta_path", [_RejectDeviceImports(), *sys.meta_path])
    result = verify(root)
    assert result["passed"]
    assert result["mutation_budget"] == 0
    assert result["android_input_injected"] is False
    assert result["original_decisions"]
