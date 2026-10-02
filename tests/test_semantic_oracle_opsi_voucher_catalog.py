import pytest

from alas_headless import SemanticGateClosed
from tests.semantic_support.observer_fixtures import (
    FakeBackend, make_button, make_image, make_oracle, make_text, make_ui,
)


ROOT = 'OverlayCamera/Overlay/UIMain/WorldShopUI(Clone)/'
CARD = ROOT + 'adapt/middle/content/world_shop/content/item_tpl/'
BOUNDS = {'left': 300, 'top': 300, 'right': 450, 'bottom': 450}
INNER = {'left': 330, 'top': 330, 'right': 360, 'bottom': 360}


def catalog_backend(*, card=True, icon='tebiezuozhan'):
    buttons = [make_button('back_button', ROOT + 'adapt/top/title/back_button',
                           raycast_top=None)]
    texts = [
        make_text('100', ROOT + 'adapt/middle/content/res/number'),
        make_text('3', ROOT + 'adapt/middle/content/resetTimer/number'),
    ]
    images = [make_image(ROOT + 'adapt/middle/content/res/icon',
                         'Wdashijiezhanbeiwuzi')]
    if card:
        buttons.append(make_button('item_tpl', CARD[:-1], bounds=BOUNDS))
        texts.extend([
            make_text('高效作战指令书', CARD + 'name_mask/name', INNER),
            make_text('1', CARD + 'icon_bg/count', INNER),
            make_text('30/30', CARD + 'count_contain/count', INNER),
            make_text('100', CARD + 'consume/contain/Text', INNER),
        ])
        images.extend([
            make_image(CARD + 'icon_bg/icon', icon, INNER),
            make_image(CARD + 'consume/contain/icon',
                       'Wdashijiezhanbeiwuzi', INNER),
        ])
    backend = FakeBackend(buttons)
    backend.ui = make_ui(texts, images=images)
    return backend


def test_voucher_catalog_accepts_structurally_complete_variable_count():
    backend = catalog_backend()
    items = make_oracle(backend).operation_siren_voucher_items()
    assert len(items) == 1
    assert (items[0].canonical_name, items[0].price, items[0].remaining) == (
        'HECombatPlan', 100, 30,
    )
    assert backend.taps == []


@pytest.mark.parametrize('card,icon', [(False, 'tebiezuozhan'), (True, 'unknown')])
def test_voucher_catalog_rejects_absent_or_unknown_cards(card, icon):
    backend = catalog_backend(card=card, icon=icon)
    with pytest.raises(SemanticGateClosed):
        make_oracle(backend).operation_siren_voucher_items()
    assert backend.taps == []
