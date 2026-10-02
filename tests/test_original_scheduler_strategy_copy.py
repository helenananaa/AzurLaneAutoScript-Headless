"""Scheduler qualification preserves task admission, order and runtime state."""

import copy
import importlib.util
from pathlib import Path
import sys

scripts = Path(__file__).resolve().parents[1] / 'scripts' / 'python'
sys.path.insert(0, str(scripts))
spec = importlib.util.spec_from_file_location('scheduler_live', scripts / 'run_alas_configured_scheduler_live.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_campaign_bound_keeps_enabled_tasks_timers_filters_and_device_binding():
    seed = {'Alas': {'Error': {'HandleError': True, 'SaveError': True, 'OnePushConfig': 'provider'},
                     'Emulator': {'Serial': 'discovered-device'}},
            'Main': {'Scheduler': {'Enable': True, 'NextRun': '2026-09-30 01:00:00'},
                     'StopCondition': {'RunCount': 0, 'OilLimit': 3000}},
            'Event': {'Scheduler': {'Enable': False}, 'StopCondition': {'RunCount': 9999}},
            'Hard': {'Scheduler': {'Enable': True}, 'Hard': {'Campaign': '12-4'}},
            'Research': {'Scheduler': {'Enable': True}, 'Research': {'Filter': 'source-filter'}}}
    before = copy.deepcopy(seed)
    config, overrides = module.prepare_config(seed, 1)
    assert seed == before
    assert config['Main']['Scheduler'] == seed['Main']['Scheduler']
    assert config['Main']['StopCondition']['OilLimit'] == 3000
    assert config['Event'] == seed['Event']
    assert config['Hard'] == seed['Hard']
    assert config['Research'] == seed['Research']
    assert config['Alas']['Emulator'] == seed['Alas']['Emulator']
    assert overrides == {'Main': {'original': 0, 'qualification': 1}}


def test_unbounded_scheduler_preserves_original_campaign_policy():
    seed = {'Alas': {'Error': {}}, 'Main': {'Scheduler': {'Enable': True}, 'StopCondition': {'RunCount': 0}}}
    config, overrides = module.prepare_config(seed, None)
    assert config['Main'] == seed['Main']
    assert overrides == {}
