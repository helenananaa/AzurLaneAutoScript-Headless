import json
import os
from pathlib import Path
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
UPSTREAM = ROOT.parent / 'AzurLaneAutoScript-upstream-readonly'


@pytest.fixture(scope='module')
def config_updater_runtime(tmp_path_factory):
    """Materialize the current updater from pinned source, without live config."""
    runtime = tmp_path_factory.mktemp('campaign-policy-updater')
    commit = json.loads(
        (ROOT / 'integration/alas/upstream-lock.json').read_text(encoding='utf-8')
    )['commit']
    for relative in (
        'module/config/config_updater.py',
        'module/config/argument/args.json',
        'config/template.json',
    ):
        original = subprocess.run(
            ['git', '-C', str(UPSTREAM), 'show', f'{commit}:{relative}'],
            check=True, capture_output=True, timeout=30,
        ).stdout
        target = runtime / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(original)
    subprocess.run(
        ['git', '-C', str(runtime), 'apply',
         '--include=module/config/config_updater.py', '--whitespace=nowarn',
         str(ROOT / 'integration/alas/0001-semantic-oracle-hooks.patch')],
        check=True, capture_output=True, timeout=30,
    )
    return runtime


@pytest.mark.parametrize('mode,event,expected', [
    ('1', 'event_20260908_cn', 'event_20260908_cn'),
    ('1', 'event_20260625_cn', 'event_20260625_cn'),
    ('0', 'event_20260908_cn', 'event_20260625_cn'),
])
def test_original_config_updater_preserves_semantic_campaign_identity(
    config_updater_runtime, mode, event, expected,
):
    runtime = config_updater_runtime
    script = """
import importlib.util,json,sys
sys.path.insert(0,sys.argv[3])
name='module.config.config_updater'
spec=importlib.util.spec_from_file_location(name,'module/config/config_updater.py')
module=importlib.util.module_from_spec(spec)
sys.modules[name]=module
spec.loader.exec_module(module)
seed=json.load(open('config/template.json',encoding='utf-8'))
seed['Event']['Campaign']['Event']=sys.argv[1]
u=module.ConfigUpdater()
r=u.config_update(seed)
r=u.config_update(r)
assert r['Event']['Campaign']['Event']==sys.argv[2], r['Event']['Campaign']
print(json.dumps(r['Event']['Campaign']))
"""
    env=dict(os.environ,ALAS_SEMANTIC_MODE=mode,PYTHONUTF8='1')
    result=subprocess.run([sys.executable,'-c',script,event,expected,str(UPSTREAM)],cwd=runtime,
                          env=env,capture_output=True,text=True,timeout=30)
    assert result.returncode==0, result.stdout+result.stderr
