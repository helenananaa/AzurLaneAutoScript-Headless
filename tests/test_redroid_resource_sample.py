import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "resource_sample", Path(__file__).parents[1] / "scripts/python/sample_redroid_wsl_resources.py")
sample = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sample)


def test_empty_io_and_process_name_with_parentheses():
    fields = ["S"] + ["0"] * 21
    fields[11], fields[12], fields[19], fields[21] = "20", "30", "123", "42"
    raw = "10.0 20.0\nCPU\nusage_usec 100\nMEMORY\n4096\nanon 1024\nIO\nPROCESSES\n"
    result = sample.parse_snapshot(raw + "8 (name (worker)) " + " ".join(fields) + "\n")
    assert result["io_raw"] == ""
    assert result["processes"]["8"] == {
        "name": "name (worker)", "ticks": 50, "start_ticks": 123, "rss_pages": 42}


def test_cpu_normalization_and_pid_reuse():
    before = {"uptime": 10, "cpu": {"usage_usec": 0}, "processes": {
        "1": {"name": "worker", "ticks": 0, "start_ticks": 1},
        "2": {"name": "old", "ticks": 99, "start_ticks": 2}}}
    after = {"uptime": 12, "cpu": {"usage_usec": 3000000}, "processes": {
        "1": {"name": "worker", "ticks": 100, "start_ticks": 1},
        "2": {"name": "new", "ticks": 1, "start_ticks": 3}}}
    result = sample.interval(before, after, 100)
    assert result["cpu_percent"] == 150
    assert result["top_processes"] == [{"pid": "1", "name": "worker", "cpu_percent": 50}]
    with pytest.raises(ValueError):
        sample.interval(after, after, 100)
