"""One canonical patched ALAS source for native-method tests in any checkout."""
from functools import lru_cache
from pathlib import Path
import atexit
import json
import os
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


@lru_cache(maxsize=1)
def patched_alas_root():
    supplied = os.environ.get('ALAS_TEST_ROOT')
    if supplied:
        return Path(supplied).resolve()

    upstream = ROOT.parent / 'AzurLaneAutoScript-upstream-readonly'
    commit = json.loads((ROOT / 'integration/alas/upstream-lock.json').read_text())['commit']
    parent = Path(tempfile.mkdtemp(prefix='alas-native-test-')).resolve()
    target = parent / 'source'

    def cleanup():
        # Only remove this function's disposable worktree, never a supplied tree.
        assert target.resolve().is_relative_to(parent)
        result = subprocess.run(['git', '-C', str(upstream), 'worktree', 'remove',
                                 '--force', str(target)], capture_output=True)
        if result.returncode == 0:
            parent.rmdir()

    subprocess.run(['git', '-C', str(upstream), 'worktree', 'add', '--detach',
                    str(target), commit], check=True, capture_output=True, timeout=120)
    atexit.register(cleanup)
    subprocess.run(['git', '-C', str(target), 'apply',
                    str(ROOT / 'integration/alas/0001-semantic-oracle-hooks.patch')],
                   check=True, capture_output=True, timeout=60)
    return target
