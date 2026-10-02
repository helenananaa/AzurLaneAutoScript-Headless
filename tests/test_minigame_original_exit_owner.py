import ast
from types import SimpleNamespace
import pytest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

@pytest.mark.parametrize('owned,selected,expected', [(36, 1, 5), (3, 1, 3), (1, 1, 1), (36, 0, 0)])
def test_native_coin_owner_selects_five_or_available_stock(owned, selected, expected):
    tree = ast.parse((ROOT / 'artifacts/campaign-preparation/upstream/module/minigame/new_year_challenge.py').read_text(encoding='utf-8'))
    methods = [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name in ('use_coin', 'use_coin_new_year_challenge')]
    counter = [selected, owned]
    clicks = []
    def click(button):
        assert 0 < counter[0] < counter[1]
        clicks.append(button)
        counter[0] += 1
    env = {'logger': SimpleNamespace(info=lambda *a: None),
           'NEW_YEAR_CHALLENGE_ADD_COIN': 'add', 'NEW_YEAR_CHALLENGE_DEC_COIN': 'sub',
           'OCR_GAME_NEW_YEAR_COIN_COST': SimpleNamespace(ocr=lambda image: counter[0])}
    exec(compile(ast.fix_missing_locations(ast.Module(body=methods, type_ignores=[])), '<native-minigame>', 'exec'), env)
    owner = SimpleNamespace(device=SimpleNamespace(semantic_adapter=SimpleNamespace(minigame_play_allowed=lambda: True, minigame_ticket_selection=lambda: tuple(counter)), click=click, screenshot=lambda: None, image=None), deal_popup=lambda: False, appear=lambda *a, **k: True)
    owner.use_coin_new_year_challenge = lambda **kwargs: env['use_coin_new_year_challenge'](owner, **kwargs)
    assert env['use_coin'](owner) is (expected > 0)
    assert counter == [expected, owned]
    assert len(clicks) == max(0, expected-selected)

def test_original_exit_loop_owns_result_back_and_retries():
    tree = ast.parse((ROOT / 'artifacts/campaign-preparation/upstream/module/minigame/new_year_challenge.py').read_text(encoding='utf-8'))
    owner = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == 'exit_game')
    text = ast.unparse(owner)
    assert 'minigame_exit_new_year' not in text
    assert 'while 1:' in text
    assert 'self.device.screenshot()' in text
    assert 'self.deal_popup()' in text
    assert 'self.appear(GOTO_CHOOSE_GAME' in text
    assert 'self.appear_then_click(NEW_YEAR_CHALLENGE_END' in text
    assert 'self.appear_then_click(BACK' in text

def test_retained_result_recovery_uses_original_exit_before_page_navigation():
    tree = ast.parse((ROOT / 'artifacts/campaign-preparation/upstream/module/minigame/minigame.py').read_text(encoding='utf-8'))
    owner = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == '_run')
    text = ast.unparse(owner)
    assert 'semantic_adapter.minigame_result() is not None' in text
    assert text.index('.exit_game(skip_first_screenshot=False)') < text.index('self.ui_ensure(page_academy)')
