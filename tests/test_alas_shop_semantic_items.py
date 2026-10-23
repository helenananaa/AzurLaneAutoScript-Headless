"""Original ALAS shop receives typed, in-stock items without pixel substitutes."""

from pathlib import Path
import ast
import json
import re
import subprocess
from types import SimpleNamespace
from unittest.mock import Mock

from alas_headless.alas_general_shop_config_replay import _assignment, _compile, _method


ROOT = Path(__file__).resolve().parents[1]


class _Grid:
    def __init__(self):
        self.buttons = [
            SimpleNamespace(button=(0, 100, 80, 180), area=(0, 100, 80, 180)),
            SimpleNamespace(button=(100, 100, 180, 180), area=(100, 100, 180, 180)),
        ]

    def __getitem__(self, _index):
        return self.buttons[0]


def _check_shop_items(namespace):
    ShopBase = namespace['ShopBase']
    ShopItem_250814 = namespace['ShopItem_250814']
    records = (
        SimpleNamespace(index=0, canonical_name="BookRedT3", amount=1,
                        cost="GuildCoins", price=100, remaining=0),
        SimpleNamespace(index=1, canonical_name="BookBlueT3", amount=1,
                        cost="GuildCoins", price=100, remaining=2),
    )
    shop = object.__new__(ShopBase)
    shop.device = SimpleNamespace(semantic_adapter=SimpleNamespace(
        general_shop_items=lambda: records))
    shop.shop_items = lambda: SimpleNamespace(grids=_Grid(), item_class=ShopItem_250814)

    items = ShopBase.shop_get_items(shop)

    assert len(items) == 1
    assert items[0].semantic_shop_index == 1
    assert items[0].name == "BookBlueT3"
    assert items[0].image_raw is None and items[0].image is None


def test_sold_out_typed_item_is_excluded_without_pixel_array(tmp_path):
    # Materialize the actual canonical method, not a historical artifacts path.
    # Execute the real method and Item classes without importing ALAS's unrelated
    # device, OCR and GUI dependencies into the portable controller test suite.
    upstream = ROOT.parent / 'AzurLaneAutoScript-upstream-readonly'
    commit = json.loads((ROOT / 'integration/alas/upstream-lock.json').read_text())['commit']
    relative = 'module/shop/base.py'
    target = tmp_path / relative
    target.parent.mkdir(parents=True)
    target.write_bytes(subprocess.check_output(
        ['git', '-C', str(upstream), 'show', f'{commit}:{relative}'], timeout=30))
    subprocess.run(['git', '-C', str(tmp_path), 'apply', f'--include={relative}',
                    '--whitespace=nowarn', str(ROOT / 'integration/alas/0001-semantic-oracle-hooks.patch')],
                   check=True, capture_output=True, timeout=30)
    item_source = subprocess.check_output(
        ['git', '-C', str(upstream), 'show', f'{commit}:module/statistics/item.py'], timeout=30)
    item = next(n for n in ast.parse(item_source).body if isinstance(n, ast.ClassDef) and n.name == 'Item')
    shop_item = next(n for n in ast.parse(target.read_text(encoding='utf-8')).body
                     if isinstance(n, ast.ClassDef) and n.name == 'ShopItem_250814')
    namespace = {'re': re, 'logger': Mock()}
    exec(compile(ast.Module(body=[item, shop_item], type_ignores=[]), str(target), 'exec'), namespace)
    namespace['FILTER_REGEX'] = _assignment(target, 'FILTER_REGEX', {'re': re})
    method = _compile(_method(target, 'ShopBase', 'shop_get_items'), namespace)
    namespace['ShopBase'] = type('ShopBase', (), {'shop_get_items': method})
    _check_shop_items(namespace)
