from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from tests.test_alas_config_branch_compatibility import method


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
    if isfile.called:
        isfile.assert_called_once_with(f'./campaign/{folder}/{name.lower()}.py')
