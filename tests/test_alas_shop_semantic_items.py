"""Original ALAS shop receives typed, in-stock items without pixel substitutes."""

from pathlib import Path
import sys
from types import SimpleNamespace


UPSTREAM = Path(__file__).resolve().parents[1] / "artifacts/campaign-preparation/upstream"
sys.path.insert(0, str(UPSTREAM))
from module.shop.base import ShopBase, ShopItem_250814  # noqa: E402


class _Grid:
    def __init__(self):
        self.buttons = [
            SimpleNamespace(button=(0, 100, 80, 180), area=(0, 100, 80, 180)),
            SimpleNamespace(button=(100, 100, 180, 180), area=(100, 100, 180, 180)),
        ]

    def __getitem__(self, _index):
        return self.buttons[0]


def test_sold_out_typed_item_is_excluded_without_pixel_array():
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
