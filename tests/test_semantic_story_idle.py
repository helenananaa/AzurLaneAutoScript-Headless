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
    # Exercise the shipped semantic hook without a mutable replay checkout.
    # Other replay tests may legitimately create/clean that disposable tree.
    source = Path(__file__).resolve().parents[1] / 'integration/alas/0001-semantic-oracle-hooks.patch'
    patch = source.read_text(encoding='utf-8')
    hunks = [part.splitlines()[1:] for part in patch.split('\n@@ ')[1:]]
    inserted_hunks = [lines for lines in hunks
                      if '+            if oracle.event_story_dialogue_visible():' in lines]
    assert len(inserted_hunks) == 1
    body = ''.join(line[1:] + '\n' for line in inserted_hunks[0]
                   if line.startswith('+') and not line.startswith('+++'))
    # The later series member completes the idle exit in that same block.
    idle_hunks = [lines for lines in hunks
                  if '+            if oracle.event_story_surface_absent():' in lines]
    assert len(idle_hunks) == 1
    before, after = [], []
    for line in idle_hunks[0]:
        if line[1:].startswith('        if self.story_popup_timeout.started()'):
            break
        if line.startswith((' ', '-')):
            before.append(line[1:] + '\n')
        if line.startswith((' ', '+')):
            after.append(line[1:] + '\n')
    old = ''.join(before)
    assert body.count(old) == 1
    body = body.replace(old, ''.join(after))
    namespace = {}
    exec(compile('def story_skip(self):\n' + body
                 + "        raise AssertionError('semantic hook reached legacy pixel path')\n",
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
