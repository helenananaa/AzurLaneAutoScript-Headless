"""A shop transaction budget must not suppress original storage observation."""
import ast
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest


@pytest.mark.parametrize('semantic', [False, True])
def test_native_voucher_keeps_storage_flow_without_shop_purchase_authority(semantic):
    path = Path(__file__).resolve().parents[1] / 'artifacts/campaign-preparation/upstream/module/os/tasks/voucher.py'
    tree = ast.parse(path.read_text(encoding='utf-8'))
    cls = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == 'OpsiVoucher')
    method = next(node for node in cls.body if isinstance(node, ast.FunctionDef) and node.name == 'os_voucher')
    events = []
    adapter = SimpleNamespace(shop_purchase_allowed=Mock(side_effect=AssertionError('storage is not a shop purchase'))) if semantic else None
    owner = SimpleNamespace(
        config=SimpleNamespace(task_delay=lambda **kwargs: events.append(('delay', kwargs))),
        device=SimpleNamespace(semantic_adapter=adapter),
        _os_voucher_enter=lambda: events.append('enter'),
        _os_voucher_exit=lambda: events.append('exit'),
        logger_use=lambda: events.append('storage'),
    )
    ns = {
        'logger': Mock(),
        'VoucherShop': lambda config, device: SimpleNamespace(run=lambda: events.append('shop')),
        'get_os_next_reset': lambda: 'native-month-reset',
    }
    exec(compile(ast.Module(body=[method], type_ignores=[]), str(path), 'exec'), ns)
    ns['os_voucher'](owner)
    assert events == ['enter', 'shop', 'exit', 'storage', ('delay', {'target': 'native-month-reset'})]
    if semantic:
        adapter.shop_purchase_allowed.assert_not_called()
