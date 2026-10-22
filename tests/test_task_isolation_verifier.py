"""Keep the device-free verifier aligned with the native scheduler boundary."""

from scripts.python.verify_alas_task_isolation import verify_source
from tests.test_alas_config_branch_compatibility import source


def test_current_patch_runs_task_isolation_without_android_or_installed_runtime():
    result = verify_source(source('alas.py'))
    assert result['passed'] is True
    assert len(result['scenarios']) == 4
