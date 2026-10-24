import ast
import re
from functools import reduce
from pathlib import PurePosixPath
from types import MethodType, SimpleNamespace
from unittest.mock import Mock

import pytest

from tests.test_alas_config_branch_compatibility import method, source


@pytest.mark.parametrize('semantic,folder,name,installed,expected', [
    (True, 'event_20261022_cn', 'T6', True, 't6'),
    (True, 'event_future_cn', 'HT6', True, 'ht6'),
    (True, 'event_20261022_cn', 'T6', False, 'b3'),
    (False, 'event_20261022_cn', 'T6', True, 'b3'),
    (True, 'event_20200917_cn', 'B3', False, 't6'),
    (True, 'event_20200917_cn', 'T6', False, 't6'),
    (True, 'event_20240912_cn', 'B3', True, 'b3'),
])
def test_exact_installed_t_stage_survives_legacy_alias_normalization(
    semantic, folder, name, installed, expected,
):
    isfile = Mock(return_value=installed)
    normalize = method(
        'module/campaign/run.py', 'CampaignRun', 'handle_stage_name',
        to_map_file_name=lambda value: value.lower(),
        os=SimpleNamespace(path=SimpleNamespace(isfile=isfile)),
    )
    host = SimpleNamespace(
        device=SimpleNamespace(semantic_adapter=object() if semantic else None),
        config=SimpleNamespace(task=SimpleNamespace(command='Event2'),
                               STAGE_LOOP_ALIAS={}, StopCondition_MapAchievement='non_stop'),
    )
    assert normalize(host, name, folder) == (expected, folder)
    if isfile.called and name.lower() in ('t6', 'ht6'):
        isfile.assert_called_once_with(f'./campaign/{folder}/{name.lower()}.py')


def installed_normalizer(installed, *, semantic=True, command='Event2'):
    normalize = method(
        'module/campaign/run.py', 'CampaignRun', 'handle_stage_name',
        to_map_file_name=lambda value: value.lower(),
        os=SimpleNamespace(path=SimpleNamespace(
            isfile=lambda path: PurePosixPath(path).name in installed)),
    )
    host = SimpleNamespace(
        device=SimpleNamespace(semantic_adapter=object() if semantic else None),
        config=SimpleNamespace(task=SimpleNamespace(command=command),
                               STAGE_LOOP_ALIAS={}, StopCondition_MapAchievement='non_stop',
                               Campaign_Event='event_20261022_cn'),
    )
    host.handle_stage_name = MethodType(normalize, host)
    return host


@pytest.mark.parametrize('name,installed,expected', [
    ('A1', {'t1.py', 't6.py'}, 't1'),
    ('B3', {'t1.py', 't6.py'}, 't6'),
    ('C1', {'ht1.py'}, 'ht1'),
    ('D3', {'ht6.py'}, 'ht6'),
    ('A1', {'a1.py', 't1.py'}, 'a1'),
    ('B3', {'b3.py', 't6.py'}, 'b3'),
    ('C1', {'t1.py'}, 'c1'),
    ('A2', {'t1.py', 't6.py'}, 'a2'),
    ('SP', {'t1.py', 't6.py'}, 'sp'),
])
def test_newer_map_alias_requires_its_installed_target_and_preserves_native_name(
    name, installed, expected,
):
    host = installed_normalizer(installed)
    assert host.handle_stage_name(name, host.config.Campaign_Event) == (
        expected, host.config.Campaign_Event)


def test_legacy_pixel_mode_keeps_original_date_based_alias_policy():
    host = installed_normalizer({'t1.py'}, semantic=False)
    assert host.handle_stage_name('A1', host.config.Campaign_Event)[0] == 'a1'


def original_class(relative, name, **namespace):
    node = next(node for node in ast.parse(source(relative)).body
                if isinstance(node, ast.ClassDef) and node.name == name)
    exec(compile(ast.Module(body=[node], type_ignores=[]), relative, 'exec'), namespace)
    return namespace[name]


@pytest.mark.parametrize('command,stage_filter,expected', [
    ('EventA', 'A1 > A2 > A3', ['t1']),
    ('EventB', 'B1 > B2 > B3', ['t6']),
    ('EventC', 'C1 > C2 > C3', []),
    ('EventD', 'D1 > D2 > D3', []),
])
def test_original_daily_filter_uses_available_newer_maps_without_inventing_missing_ones(
    command, stage_filter, expected,
):
    files = {'campaign_base.py', 't1.py', 't6.py'}
    host = installed_normalizer(files, command=command)
    event_stage = original_class('module/event/base.py', 'EventStage')
    filter_type = original_class('module/base/filter.py', 'Filter',
                                 re=re, reduce=reduce, logger=Mock())
    convert = method('module/event/base.py', 'EventBase', 'convert_stages',
                     EventStage=event_stage, Filter=filter_type)
    stages = convert(host, [event_stage(file) for file in files])
    original_filter = filter_type(regex=re.compile('^(.*?)$'), attr=('stage',))
    original_filter.load(stage_filter)
    convert(host, original_filter)
    assert [str(stage) for stage in original_filter.apply(stages)] == expected
