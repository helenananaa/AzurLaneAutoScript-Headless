"""The startup hook keeps retirement decisions and loops in original ALAS."""

import ast
import os
from pathlib import Path
from types import SimpleNamespace
import pytest


def recovery_block():
    root = Path(__file__).resolve().parents[1]
    source = Path(os.environ.get('ALAS_MIDMAP_REPLAY_ROOT',
        root / 'artifacts/campaign-road-debug-20260913')) / 'module/campaign/run.py'
    if not source.exists():
        pytest.skip('materialized patched ALAS tree unavailable')
    tree = ast.parse(source.read_text(encoding='utf-8'))
    node = next(n for n in ast.walk(tree) if isinstance(n, ast.If)
                and isinstance(n.test, ast.BoolOp)
                and 'campaign_dock_full_visible' in ast.unparse(n.test))
    return compile(ast.fix_missing_locations(ast.Module(body=[node], type_ignores=[])), str(source), 'exec')


@pytest.mark.parametrize('full,selection', [(False, False), (True, False), (False, True)])
def test_startup_recovery_only_drives_original_handler_when_needed(full, selection):
    visible = full or selection
    events = []
    results = iter((False, True))
    def handler():
        events.append('original-retirement')
        return next(results)
    campaign = SimpleNamespace(loop=lambda **kw: range(3),
        _semantic_campaign_retirement_recovery=handler, device=SimpleNamespace(image=None))
    device = SimpleNamespace(image='fresh-semantic-frame', screenshot=lambda: events.append('screenshot'))
    exec(recovery_block(), {'self': SimpleNamespace(campaign=campaign, device=device),
        'semantic_adapter': SimpleNamespace(campaign_dock_full_visible=lambda: full,
            campaign_retirement_visible=lambda: selection),
        'ScriptEnd': RuntimeError})
    assert events == (['original-retirement', 'original-retirement', 'screenshot'] if visible else [])
    if visible:
        assert campaign.device.image == device.image


def test_legacy_startup_does_not_enter_semantic_recovery():
    exec(recovery_block(), {'self': object(), 'semantic_adapter': None, 'ScriptEnd': RuntimeError})


def test_unfinished_recovery_does_not_continue_into_sortie():
    campaign = SimpleNamespace(loop=lambda **kw: range(2),
        _semantic_campaign_retirement_recovery=lambda: False)
    with pytest.raises(RuntimeError, match='did not complete'):
        exec(recovery_block(), {'self': SimpleNamespace(campaign=campaign),
            'semantic_adapter': SimpleNamespace(campaign_dock_full_visible=lambda: True),
            'ScriptEnd': RuntimeError})
