"""Owners for the common typed linked-Scrollbar observation/input boundary."""
from dataclasses import dataclass


@dataclass(frozen=True)
class LinkedScrollbarOwner:
    family_key: str
    bar_schema: str
    input_schema: str
    input_endpoint: str
    input_scope: str
    bar_roots: tuple[str, ...]
    drag_semantic_id: str


STORAGE_SCROLLBAR_OWNER = LinkedScrollbarOwner(
    'storage_scroll', 'alas-headless.storage-scrollbar/v1',
    'alas-headless.storage-scrollbar-input/v1', '/v1/storage-scrollbar-input',
    'read-only-storage-scrollbar-input',
    ('UICamera/Canvas/UIMain/StoreHouseUI(Clone)/adapt/item_scrollview/Scrollbar',
     'UICamera/Canvas/UIMain/StoreHouseUI(Clone)/item_scrollview/Scrollbar'),
    'storage/material/scroll')

EQUIPMENT_SCROLLBAR_OWNER = LinkedScrollbarOwner(
    STORAGE_SCROLLBAR_OWNER.family_key, STORAGE_SCROLLBAR_OWNER.bar_schema,
    STORAGE_SCROLLBAR_OWNER.input_schema, STORAGE_SCROLLBAR_OWNER.input_endpoint,
    STORAGE_SCROLLBAR_OWNER.input_scope,
    ('UICamera/Canvas/UIMain/StoreHouseUI(Clone)/adapt/equipment_scrollview/Scrollbar',
     'UICamera/Canvas/UIMain/StoreHouseUI(Clone)/equipment_scrollview/Scrollbar'),
    'storage/equipment/scroll')

RETIREMENT_SCROLLBAR_OWNER = LinkedScrollbarOwner(
    'retirement_preconfirm_scroll', 'alas-headless.retirement-scrollbar/v1',
    'alas-headless.retirement-scrollbar-input/v1', '/v1/retirement-scrollbar-input',
    'read-only-retirement-scrollbar-input',
    ('OverlayCamera/Overlay/UIMain/DestoryInfoUI(Clone)/frame/sliders/scroll_bar',),
    'retirement/preconfirm/scroll')
