"""Retained skill rows use one frame for observation and fresh input proof."""
import copy
import json
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from alas_headless import AlasSemanticSession, SemanticGateClosed
from alas_headless.adapter import AdbRuntimeHandle, semantic_runtime_fingerprint_sha256
from alas_headless.adapter.errors import StaleFrameError
from alas_headless.semantic_oracle import AdbObserverBridge
from tests.semantic_support.observer_fixtures import FakeBackend, make_button


class SkillAccepted(Exception):
    """Stop after the skill tap, before the original confirm destination wait."""


def skill_page(fixture='tactical-skill-frame-r1529.json'):
    raw = json.loads((Path(__file__).parent / 'fixtures' / fixture).read_text(encoding='utf-8'))['projections']
    backend = FakeBackend([])
    backend.snapshot, backend.buttons, backend.ui = (copy.deepcopy(raw[key]) for key in ('snapshot', 'buttons', 'ui'))
    if fixture == 'tactical-skill-clone-rows-r1553.json':
        # The retained diagnostic reads were sequential. Model a coherent
        # publication for replay without altering the original fixture's
        # generations or claiming it was an immutable failing frame.
        generation = max(v['generation'] for v in (backend.snapshot, backend.buttons, backend.ui))
        for source in (backend.snapshot, backend.buttons, backend.ui):
            source['generation'] = generation
    bridge = AdbObserverBridge('offline-tactical-skill', backend.snapshot['package'])
    bridge.pid = backend.snapshot['pid']
    bridge.request = backend.request
    bridge.foreground_component = Mock(side_effect=backend.foreground_component)
    bridge.tap, bridge.swipe = backend.tap, backend.swipe
    bridge.package_pid = Mock(return_value=bridge.pid)
    revision = backend.snapshot['driver_revision']
    fingerprint = semantic_runtime_fingerprint_sha256(package=backend.snapshot['package'],
        component=backend.foreground, driver_revision=revision, required_primary_abi='x86_64')
    session = AlasSemanticSession(driver_revision=revision,
        runtime_handle=AdbRuntimeHandle(bridge, fingerprint_sha256=fingerprint),
        policy_grants={'tactical.assign': 1, 'shop.purchase': 0})
    session.refresh_frame()
    session.begin_tactical()
    adapter = session.open()
    adapter.oracle.wait_for = Mock(side_effect=SkillAccepted())
    return backend, session, adapter


@pytest.mark.parametrize('drift', [False, True])
def test_skill_observation_keeps_original_frame_without_split_live_reads(drift):
    backend, session, adapter = skill_page()
    if drift:
        backend.buttons['buttons'].reverse()
        backend.ui['texts'].reverse()
        backend.ui['images'].reverse()
        backend.ui['compatible_extra_field'] = True
        session.refresh_frame()
    adapter.oracle.tactical_skills = Mock(side_effect=AssertionError('split live read'))
    skills = session.tactical_skills()
    assert skills and any(not skill.max_level for skill in skills)
    assert not backend.taps


@pytest.mark.parametrize('drift', [False, True])
def test_distinct_clone_rows_remain_visible_and_selectable(drift):
    backend, session, adapter = skill_page('tactical-skill-clone-rows-r1553.json')
    if drift:
        backend.ui['images'].reverse()
        backend.ui['texts'].reverse()
        backend.ui['additive_compatible_field'] = True
        session.refresh_frame()
    adapter.oracle.tactical_skills = Mock(side_effect=AssertionError('split live skill read'))
    skills = session.tactical_skills()
    assert len(skills) == 3
    assert len({s.button.path for s in skills}) == 2
    assert session.appear('SKILL_CONFIRM') is True
    with pytest.raises(SkillAccepted):
        session.tactical_select_first_trainable_skill()
    assert len(backend.taps) == 1


def test_skill_selection_and_final_tap_use_fresh_coherent_frames():
    backend, session, adapter = skill_page()
    adapter.oracle.tactical_skills = Mock(side_effect=AssertionError('split live read'))
    adapter.oracle.click_tactical_skill = Mock(side_effect=AssertionError('split live input proof'))
    before = session._frame_clock._ordinal
    with pytest.raises(SkillAccepted):
        session.tactical_select_first_trainable_skill()
    assert session._frame_clock._ordinal == before + 2
    assert len(backend.taps) == 1
    assert session.action_ledger.remaining('tactical.assign') == 1
    assert adapter.oracle.wait_for.call_args.args == ('tactical/skill/confirm',)


@pytest.mark.parametrize('change', ['foreign', 'stale', 'incoherent', 'duplicate', 'covered', 'missing-text', 'loading'])
def test_final_skill_frame_rejects_unsafe_state_without_input(change):
    backend, session, adapter = skill_page()
    selected = next(s for s in adapter._require_frame_observation_oracle().tactical_skills() if not s.max_level)
    refresh = adapter._input_frame_refresher
    count = 0

    def changed_refresh():
        nonlocal count
        count += 1
        if count == 2:
            if change == 'foreign':
                backend.foreground = 'other.package/.Activity'
            elif change == 'stale':
                raise StaleFrameError()
            elif change == 'incoherent':
                backend.ui['generation'] += 100
            elif change == 'loading':
                backend.buttons['buttons'].append(make_button('Loading(Clone)', 'OverlayCamera/Overlay/UIOverlay/Loading(Clone)'))
                backend.buttons['button_count'] += 1
            elif change == 'missing-text':
                backend.ui['texts'] = [t for t in backend.ui['texts'] if t['path'] != selected.button.path + '/name/level']
                backend.ui['text_count'] = len(backend.ui['texts'])
            else:
                image = next(v for v in backend.ui['images'] if v['path'] == selected.button.path)
                if change == 'duplicate':
                    backend.ui['images'].append(copy.deepcopy(image))
                    backend.ui['image_count'] += 1
                else:
                    image['raycast_top'] = False
        return refresh()

    adapter._input_frame_refresher = changed_refresh
    with patch('alas_headless.adapter.frame.time.sleep', lambda _: None):
        with pytest.raises(SemanticGateClosed):
            session.tactical_select_first_trainable_skill()
    assert not backend.taps
    assert session.action_ledger.remaining('tactical.assign') == 1
