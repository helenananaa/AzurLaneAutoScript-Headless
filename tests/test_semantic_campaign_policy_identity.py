import json
import os
from pathlib import Path
import subprocess
import sys

import pytest


@pytest.mark.parametrize('mode,event,expected', [
    ('1', 'event_20260908_cn', 'event_20260908_cn'),
    ('1', 'event_20260625_cn', 'event_20260625_cn'),
    ('0', 'event_20260908_cn', 'event_20260625_cn'),
])
def test_original_config_updater_preserves_semantic_campaign_identity(mode,event,expected):
    runtime = Path('artifacts/campaign-preparation/upstream').resolve()
    script = """
import json,sys
from module.config.config_updater import ConfigUpdater
seed=json.load(open('config/semantic_cn.json',encoding='utf-8'))
seed['Event']['Campaign']['Event']=sys.argv[1]
u=ConfigUpdater()
r=u.config_update(seed)
r=u.config_update(r)
assert r['Event']['Campaign']['Event']==sys.argv[2], r['Event']['Campaign']
print(json.dumps(r['Event']['Campaign']))
"""
    env=dict(os.environ,ALAS_SEMANTIC_MODE=mode,PYTHONUTF8='1')
    result=subprocess.run([sys.executable,'-c',script,event,expected],cwd=runtime,
                          env=env,capture_output=True,text=True)
    assert result.returncode==0, result.stdout+result.stderr
