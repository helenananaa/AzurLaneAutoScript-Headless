import ast
from types import SimpleNamespace

import pytest

from tests.test_alas_config_branch_compatibility import source


@pytest.mark.parametrize('semantic,handle_error', [(False, True), (True, True), (True, False)])
def test_original_device_start_obeys_recovery_policy_and_semantic_launch(semantic, handle_error):
    tree = ast.parse(source('module/device/device.py'))
    original = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'Device')
    method = next(n for n in original.body if isinstance(n, ast.FunctionDef) and n.name == 'app_start')
    events = []
    class Legacy:
        def app_start(self): events.append('legacy-start')
    class HumanTakeover(Exception): pass
    namespace = dict(Legacy=Legacy, validate_alas_handle_error_config=lambda value: value,
                     RequestHumanTakeover=HumanTakeover, logger=SimpleNamespace(critical=lambda _: None))
    cls = ast.ClassDef(name='Device', bases=[ast.Name(id='Legacy', ctx=ast.Load())],
                      keywords=[], body=[method], decorator_list=[])
    exec(compile(ast.fix_missing_locations(ast.Module(body=[cls], type_ignores=[])), '<original-device>', 'exec'), namespace)
    device = namespace['Device']()
    device.config = SimpleNamespace(Error_HandleError=handle_error)
    device.semantic_adapter = SimpleNamespace(restart_game_for_manager=lambda: events.append('owned-headless-restart')) if semantic else None
    device.stuck_record_clear = lambda: events.append('clear-stuck')
    device.click_record_clear = lambda: events.append('clear-click')
    if not handle_error:
        with pytest.raises(HumanTakeover): device.app_start()
        assert events == []
    else:
        device.app_start()
        assert events == [('owned-headless-restart' if semantic else 'legacy-start'), 'clear-stuck', 'clear-click']
