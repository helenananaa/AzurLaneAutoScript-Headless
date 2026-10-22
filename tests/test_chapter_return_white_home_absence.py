"""Native chapter-back discovery must not acquire unrelated recovery owners."""
import pytest
from alas_headless import SemanticGateClosed, AlasSemanticUnmapped
from tests.test_game_tips_loading_presence import host
from tests.semantic_support.observer_fixtures import make_button


@pytest.mark.parametrize('fixture', ['chapter-before-return-r23.json', 'chapter-menu-after-return-r23.json'])
@pytest.mark.parametrize('alias', ['GOTO_MAIN_WHITE', 'RPG_HOME'])
@pytest.mark.parametrize('drift', [False, True])
def test_actual_native_return_frames_keep_unrelated_home_aliases_absent(fixture, alias, drift):
    backend, _, adapter = host(drift, fixture)
    assert adapter.appear(alias) is False
    assert adapter._mail_context is None
    with pytest.raises((SemanticGateClosed, AlasSemanticUnmapped)):
        adapter.click(alias)
    assert not backend.taps


@pytest.mark.parametrize('case', ['foreign-popup', 'foreign-package', 'missing-back'])
def test_unproven_chapter_does_not_supply_home_alias_absence(case):
    backend, _, adapter = host(fixture='chapter-menu-after-return-r23.json')
    if case == 'foreign-popup':
        backend.buttons['buttons'].append(make_button('custom_button_1(Clone)',
            'OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/button_container/custom_button_1(Clone)'))
    elif case == 'foreign-package': backend.snapshot['package'] = 'unrelated.package'
    else:
        backend.buttons['buttons'] = [b for b in backend.buttons['buttons'] if b['name'] != 'back_button']
    backend.buttons['button_count'] = len(backend.buttons['buttons'])
    with pytest.raises((SemanticGateClosed, AlasSemanticUnmapped)):
        adapter.appear('GOTO_MAIN_WHITE')
    assert not backend.taps
