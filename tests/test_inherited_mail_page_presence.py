import copy
import pytest
from alas_headless import AlasSemanticUnmapped, SemanticGateClosed
from tests.test_game_tips_loading_presence import host
from tests.semantic_support.observer_fixtures import make_button


@pytest.mark.parametrize('drift', [False, True])
def test_actual_inherited_mail_page_exposes_original_exact_return(drift):
    b, o, a = host(drift, 'mail-inherited-page-r145.json')
    assert o.read_state().generation == 3319
    assert a._mail_context is None
    assert o.enabled('mail/page/back')
    assert a.appear('GOTO_MAIN_WHITE')
    assert not b.taps


@pytest.mark.parametrize('case', ['foreign-package', 'truncated', 'duplicate-back', 'covered-back'])
def test_inherited_mail_return_requires_existing_typed_target(case):
    b, o, a = host(fixture='mail-inherited-page-r145.json')
    if case == 'foreign-package':
        b.snapshot['package'] = 'unrelated.package'
    elif case == 'truncated':
        b.buttons['truncated'] = True
    elif case == 'duplicate-back':
        b.buttons['buttons'].append(copy.deepcopy(next(v for v in b.buttons['buttons'] if '/CommonTitleAndBack/back_btn' in v['path'])))
        b.buttons['button_count'] += 1
    else:
        next(v for v in b.buttons['buttons'] if '/CommonTitleAndBack/back_btn' in v['path'])['raycast_top'] = False
    with pytest.raises((AlasSemanticUnmapped, SemanticGateClosed)):
        a.appear('GOTO_MAIN_WHITE')
    assert not b.taps
