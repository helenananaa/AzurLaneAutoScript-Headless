import ast
import re
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from alas_headless import SemanticGateClosed
from tests.test_alas_config_branch_compatibility import source


@pytest.mark.parametrize('index,raw', [(0, 'NY City'), (1, 'NY'), (2, 'NY'), (3, 'NY-安全海域')])
@pytest.mark.parametrize('semantic', [False, True])
def test_original_locale_zone_name_uses_exact_title_and_keeps_native_processing(index, raw, semantic):
    owner = next(node for node in ast.parse(source('module/os/map_operation.py')).body
                 if isinstance(node, ast.ClassDef) and node.name == 'OSMapOperation')
    nodes = [node for node in owner.body if isinstance(node, ast.FunctionDef) and node.name == 'get_zone_name']
    node = nodes[index]
    node.decorator_list = []
    ocr = SimpleNamespace(ocr=Mock(return_value=raw))
    namespace = dict(Ocr=lambda *args, **kw: ocr, MAP_NAME=object(), re=re)
    exec(compile(ast.fix_missing_locations(ast.Module(body=[node], type_ignores=[])), '<zone-title>', 'exec'), namespace)
    adapter = SimpleNamespace(operation_siren_state=Mock(return_value=SimpleNamespace(zone_name=raw)))
    host = SimpleNamespace(device=SimpleNamespace(semantic_adapter=adapter if semantic else None, image=object()))
    result = namespace['get_zone_name'](host)
    assert 'ny' in result.lower()
    if semantic:
        ocr.ocr.assert_not_called()
        adapter.operation_siren_state.assert_called_once_with()
        adapter.operation_siren_state.side_effect = SemanticGateClosed('ambiguous title')
        with pytest.raises(SemanticGateClosed):
            namespace['get_zone_name'](host)
        ocr.ocr.assert_not_called()
    else:
        ocr.ocr.assert_called_once_with(host.device.image)
