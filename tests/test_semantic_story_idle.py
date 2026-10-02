import ast
from pathlib import Path
from types import SimpleNamespace

import pytest
from alas_headless import SemanticGateClosed
from tests.semantic_support.observer_fixtures import FakeBackend, make_button, make_oracle


def test_empty_story_surface_is_a_typed_idle_boundary():
    backend = FakeBackend([])
    assert make_oracle(backend).event_story_surface_absent()
    assert backend.taps == []


def test_partial_or_upstream_story_family_does_not_become_idle():
    backend = FakeBackend([make_button('unknown',
        'OverlayCamera/Overlay/UIOverlay/UpdatedStoryUI(Clone)/unknown')])
    with pytest.raises(SemanticGateClosed, match='incomplete or unsupported'):
        make_oracle(backend).event_story_surface_absent()
    assert backend.taps == []


def test_story_collection_page_does_not_block_other_native_page_handlers():
    backend = FakeBackend([make_button('back',
        'OverlayCamera/Overlay/UIMain/EventStoryScene(Clone)/back')])
    assert make_oracle(backend).event_story_surface_absent()
    assert backend.taps == []


@pytest.mark.parametrize('unsupported', [False, True])
def test_original_story_handler_never_falls_through_to_pixels(unsupported):
    source = Path('artifacts/campaign-preparation/upstream/module/handler/info_handler.py')
    tree = ast.parse(source.read_text(encoding='utf-8'))
    method = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == 'story_skip')
    namespace = {}
    exec(compile(ast.fix_missing_locations(ast.Module(body=[method], type_ignores=[])),
                 str(source), 'exec'), namespace)

    def absent():
        if unsupported:
            raise SemanticGateClosed('mounted story surface is incomplete or unsupported')
        return True

    oracle = SimpleNamespace(event_story_skip_prompt_visible=lambda: False,
        event_story_dialogue_visible=lambda: False, event_story_surface_absent=absent)
    host = SimpleNamespace(device=SimpleNamespace(semantic_adapter=SimpleNamespace(
        open=lambda: SimpleNamespace(oracle=oracle))))
    # No legacy timer, screenshot, OCR or template attributes are supplied.
    if unsupported:
        with pytest.raises(SemanticGateClosed, match='unsupported'):
            namespace['story_skip'](host)
    else:
        assert namespace['story_skip'](host) is False
