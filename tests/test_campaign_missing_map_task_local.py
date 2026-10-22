import copy
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from alas_headless import AlasSemanticUnmapped
from alas_headless.adapter.task_lifecycle import semantic_task_scope, TaskCapabilityUnavailable
from tests.test_alas_config_branch_compatibility import method


class HumanTakeover(RuntimeError):
    pass


def loader(error=None, module=None):
    importer = Mock(side_effect=error, return_value=module)
    original = method('module/campaign/run.py', 'CampaignRun', 'load_campaign',
        importlib=SimpleNamespace(import_module=importer), copy=copy,
        os=SimpleNamespace(path=SimpleNamespace(exists=lambda _: False)),
        RequestHumanTakeover=HumanTakeover)
    return original, importer


@pytest.mark.parametrize('missing', ['campaign.event_20260908_cn', 'campaign.event_20260908_cn.d3'])
def test_missing_requested_map_defers_only_native_task_without_input(missing):
    load, importer = loader(ModuleNotFoundError(name=missing))
    device = SimpleNamespace(semantic_adapter=object(), click=Mock())
    host = SimpleNamespace(device=device)
    session = SimpleNamespace(discard_task_state=Mock(), trace=None)
    with pytest.raises(TaskCapabilityUnavailable) as caught:
        with semantic_task_scope(session, 'event'):
            load(host, 'd3', 'event_20260908_cn')
    assert isinstance(caught.value.cause, AlasSemanticUnmapped)
    assert 'select an existing map' in str(caught.value)
    importer.assert_called_once_with('.d3', 'campaign.event_20260908_cn')
    device.click.assert_not_called()
    with semantic_task_scope(session, 'research'):
        pass
    assert session.last_task_outcome['outcome'] == 'returned'


@pytest.mark.parametrize('semantic,missing', [
    (False, 'campaign.event_20260908_cn'),
    (True, 'missing_dependency'),
    (True, 'campaign'),
    (True, None),
])
def test_other_import_failures_keep_original_human_takeover(semantic, missing):
    load, _ = loader(ModuleNotFoundError(name=missing))
    with pytest.raises(HumanTakeover):
        load(SimpleNamespace(device=SimpleNamespace(semantic_adapter=object() if semantic else None)),
             'd3', 'event_20260908_cn')


def test_available_newer_map_still_uses_original_loader_and_campaign_constructor():
    config = Mock()
    module = SimpleNamespace(Config=Mock(return_value='map config'), Campaign=Mock(return_value='native campaign'))
    load, importer = loader(module=module)
    device = SimpleNamespace(semantic_adapter=object())
    host = SimpleNamespace(device=device, config=config)
    assert load(host, 'd3', 'event_newer_cn')
    importer.assert_called_once_with('.d3', 'campaign.event_newer_cn')
    module.Campaign.assert_called_once()
    assert module.Campaign.call_args.kwargs['device'] is device
    assert host.campaign == 'native campaign'
