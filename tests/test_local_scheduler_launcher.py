"""Inspect the operator launch plan without touching a device or configuration."""
import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
POWERSHELL = shutil.which('pwsh') or shutil.which('powershell')
pytestmark = pytest.mark.skipif(not POWERSHELL, reason='PowerShell is unavailable')


@pytest.mark.parametrize('mode, expected', [
    ([], ['--max-tasks', '3']),
    (['-MaxTasks', '1'], ['--max-tasks', '1']),
    (['-Continuous', '-RestartBeforeLoop'], ['--continuous', '--restart-before-loop']),
    (['-Continuous', '-ContinueAfterFailure', '-StopFile', 'operator request.stop'],
     ['--continuous', '--continue-after-failure', '--stop-file']),
])
def test_plan_uses_current_checkout_and_preserves_native_arguments(tmp_path, mode, expected):
    bundle = tmp_path / 'bundle with spaces'
    bundle.mkdir()
    manifest = {
        'repository': 'obsolete-worktree',
        'python': 'does-not-exist-python',
        'alas_root': 'existing ALAS runtime',
        'scheduler_seed': 'seed',
        'scheduler_config': 'persistent',
        'observer': {'revision': 'retained-driver'},
        'adb_directory': 'platform tools',
        'scheduler_budgets': ['ALAS_SEMANTIC_COMMISSION_START_BUDGET=4'],
    }
    source = json.dumps(manifest)
    (bundle / 'manifest.json').write_text(source, encoding='utf-8')
    result = subprocess.run([
        POWERSHELL, '-NoProfile', '-NonInteractive', '-File',
        str(ROOT / 'scripts/windows/run-alas-local-scheduler.ps1'),
        '-BundleDirectory', str(bundle), '-Plan', *mode,
    ], capture_output=True, text=True, encoding='utf-8', timeout=30)
    assert result.returncode == 0, result.stderr
    plan = json.loads(result.stdout.lstrip('\ufeff'))
    assert Path(plan['repository']) == ROOT
    assert Path(plan['arguments'][0]) == ROOT / 'scripts/python/run_alas_configured_scheduler_live.py'
    for argument in expected:
        assert argument in plan['arguments']
    assert '--continuous' in plan['arguments'] if '-Continuous' in mode else '--continuous' not in plan['arguments']
    assert ('--restart-before-loop' in plan['arguments']) == ('-RestartBeforeLoop' in mode)
    assert plan['arguments'][plan['arguments'].index('--persistent-config') + 1] == 'persistent'
    assert plan['arguments'][plan['arguments'].index('--budget') + 1] == manifest['scheduler_budgets'][0]
    if '-StopFile' in mode:
        stop_file = Path(plan['arguments'][plan['arguments'].index('--stop-file') + 1])
        assert stop_file.is_absolute() and stop_file.name == 'operator request.stop'
    assert not plan['executes_game']
    assert list(bundle.iterdir()) == [bundle / 'manifest.json']
    assert (bundle / 'manifest.json').read_text(encoding='utf-8') == source


@pytest.mark.parametrize('exit_code', [0, 23])
def test_dispatch_preserves_arguments_and_runner_exit_without_a_device(tmp_path, exit_code):
    capture = tmp_path / 'captured.json'
    stub = tmp_path / 'fake python.ps1'
    stub.write_text(
        '@{arguments=@($args); path=$env:PATH} | ConvertTo-Json -Depth 4 | '
        'Set-Content -LiteralPath $env:ALAS_LAUNCH_TEST_CAPTURE -Encoding UTF8\n'
        '$global:LASTEXITCODE = [int]$env:ALAS_LAUNCH_TEST_EXIT\n', encoding='utf-8')
    manifest = {
        'python': str(stub), 'alas_root': 'runtime with spaces',
        'scheduler_seed': 'seed', 'scheduler_config': 'persistent',
        'observer': {'revision': 'driver'}, 'adb_directory': 'adb tools',
        'scheduler_budgets': ['ALAS_SEMANTIC_RESEARCH_START_BUDGET=6'],
    }
    (tmp_path / 'manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
    result = subprocess.run([
        POWERSHELL, '-NoProfile', '-NonInteractive', '-File',
        str(ROOT / 'scripts/windows/run-alas-local-scheduler.ps1'),
        '-BundleDirectory', str(tmp_path), '-MaxTasks', '1',
        '-RestartBeforeLoop', '-Output', str(tmp_path / 'receipt with spaces.json'),
    ], env={**os.environ, 'ALAS_LAUNCH_TEST_CAPTURE': str(capture),
            'ALAS_LAUNCH_TEST_EXIT': str(exit_code)},
        capture_output=True, text=True, encoding='utf-8', timeout=30)
    assert result.returncode == exit_code, result.stdout + result.stderr
    dispatched = json.loads(capture.read_text(encoding='utf-8-sig'))
    assert dispatched['arguments'][2] == 'runtime with spaces'
    assert '--restart-before-loop' in dispatched['arguments']
    assert dispatched['arguments'][-2:] == ['--budget', manifest['scheduler_budgets'][0]]
    assert dispatched['path'].startswith('adb tools' + os.pathsep)
    assert not (tmp_path / 'receipt with spaces.json').exists()
