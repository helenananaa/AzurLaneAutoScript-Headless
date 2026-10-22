import pytest
from types import SimpleNamespace
from alas_headless import AlasSemanticAdapter, SemanticGateClosed, AlasSemanticUnmapped
from tests.semantic_support.observer_fixtures import make_button, make_image, make_text, make_oracle
from tests.test_meta_dossier_empty import dossier_backend, ROOT


def backend():
    b = dossier_backend()
    b.buttons['buttons'].append(make_button('archives_btn', ROOT+'archives_btn', raycast_top=None))
    b.buttons['button_count'] += 1
    b.ui['texts'].append(make_text('53590/70000', ROOT+'archives_btn/Text'))
    b.ui['text_count'] += 1
    b.ui['images'].append(make_image(ROOT+'archives_btn', 'btn'))
    b.ui['image_count'] += 1
    return b


def test_native_archive_progress_entry_uses_one_reviewed_target():
    b = backend()
    a = AlasSemanticAdapter(make_oracle(b), package_gate=lambda: None)
    a.begin_meta_beacon()
    assert a.click(SimpleNamespace(name='DOSSIER_REWARD_ENTER')).semantic_id == 'meta/dossier/sync/open'
    assert len(b.taps) == 1


@pytest.mark.parametrize('change', ['sprite', 'text', 'generation', 'raycast'])
def test_archive_progress_entry_rejects_unknown_or_covered_state(change):
    b = backend()
    if change == 'sprite': b.ui['images'][-1]['sprite'] = 'unknown'
    if change == 'text': b.ui['texts'][-1]['text'] = 'unknown'
    if change == 'generation': b.ui['generation'] += 3
    if change == 'raycast': b.buttons['buttons'][-1]['raycast_top'] = False
    with pytest.raises(SemanticGateClosed): make_oracle(b).click_meta_dossier_sync_open()
    assert not b.taps


@pytest.mark.parametrize('change', [None, 'inactive', 'covered', 'outside', 'duplicate', 'foreground', 'stale_post', 'unchanged_post'])
def test_archive_reward_claim_uses_one_reviewed_control_and_fresh_postcondition(change, monkeypatch):
    from tests.semantic_support.observer_fixtures import FakeBackend, make_ui
    root = ROOT.replace('ArchivesWorldBossEmptyUI', 'ArchivesWorldBossListUI')
    path = root+'main/award/get_all'
    claim = make_button('get_all', path, raycast_top=None)
    b = FakeBackend([make_button('back', root+'blur_panel/adapt/top/back', raycast_top=None), claim])
    marker = make_image(path, 'claim', bounds=dict(claim['adb_bounds']))
    b.ui = make_ui([make_text('53590', root+'main/award/pt/Text'),
                    make_text('同步值(53590/70000)', root+'main/list/scrollrect/content/0/underway/label')], images=[marker])
    if change == 'inactive':
        marker['active_in_hierarchy'] = marker['active_and_enabled'] = False
        marker['flags'] &= ~3
    if change == 'covered': claim['raycast_top'] = False
    if change == 'outside': claim['adb_point']['x'] = 999
    if change == 'duplicate':
        b.buttons['buttons'].append(dict(claim)); b.buttons['button_count'] += 1
    o = make_oracle(b)
    if change == 'foreground': o._foreground_component = lambda: 'other/package'
    def claimed():
        if change != 'unchanged_post':
            marker['active_in_hierarchy'] = marker['active_and_enabled'] = False
            marker['flags'] &= ~3
        if change != 'stale_post':
            for frame in (b.buttons, b.ui, b.snapshot): frame['generation'] = 11
    b.on_tap = claimed
    a = AlasSemanticAdapter(o, package_gate=lambda: None)
    if change in ('stale_post', 'unchanged_post'):
        import alas_headless.oracle.meta as module
        from itertools import count
        ticks = count(0, 4)
        monkeypatch.setattr(module.time, 'monotonic', lambda: next(ticks))
        with pytest.raises(SemanticGateClosed, match='reward postcondition'):
            a.click(SimpleNamespace(name='DOSSIER_REWARD_RECEIVE'))
        assert len(b.taps) == 1
    elif change:
        with pytest.raises(SemanticGateClosed): a.click(SimpleNamespace(name='DOSSIER_REWARD_RECEIVE'))
        assert not b.taps
    else:
        receipt = a.click(SimpleNamespace(name='DOSSIER_REWARD_RECEIVE'))
        assert receipt.semantic_id == 'meta/dossier/sync/rewards'
        assert len(b.taps) == 1


def test_unknown_archive_reward_probe_cannot_be_reported_as_empty():
    a = AlasSemanticAdapter(make_oracle(backend()), package_gate=lambda: None)
    with pytest.raises(SemanticGateClosed): a.appear(SimpleNamespace(name='DOSSIER_REWARD_RECEIVE'))


def test_archive_sync_page_retries_a_generation_gap_without_input():
    from tests.semantic_support.observer_fixtures import FakeBackend, make_ui, make_snapshot
    root = ROOT.replace('ArchivesWorldBossEmptyUI', 'ArchivesWorldBossListUI')
    b = FakeBackend([make_button('back', root+'blur_panel/adapt/top/back', raycast_top=None)])
    texts = [make_text('53590', root+'main/award/pt/Text'),
             make_text('同步值(53590/70000)', root+'main/list/scrollrect/content/0/underway/label')]
    b.snapshot = make_snapshot(generation=13)
    b.snapshot_sequence = [make_snapshot(generation=10), make_snapshot(generation=10),
                           make_snapshot(generation=13)]
    b.ui = make_ui(texts, generation=14)
    b.ui_sequence = [make_ui(texts, generation=13), make_ui(texts, generation=14)]
    assert make_oracle(b).meta_dossier_sync_page_visible()
    assert b.requests.count('GET /v1/ui\n') == 2
    assert not b.taps


@pytest.mark.parametrize('name', ['DOSSIER_REWARD_RECEIVE', 'DOSSIER_REWARD_CHECK'])
@pytest.mark.parametrize('foreign', [False, True])
def test_archive_reward_overlay_yields_to_original_handler(name, foreign):
    from tests.semantic_support.observer_fixtures import FakeBackend, make_ui
    root = ROOT.replace('ArchivesWorldBossEmptyUI', 'ArchivesWorldBossListUI')
    buttons = [make_button('back', root+'blur_panel/adapt/top/back'),
               make_button('close', 'OverlayCamera/Overlay/UIMain/AwardInfoUI(Clone)/items/close')]
    if foreign:
        buttons.append(make_button('confirm', 'OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/button_container/custom_button_1(Clone)'))
    b = FakeBackend(buttons)
    b.ui = make_ui([])
    a = AlasSemanticAdapter(make_oracle(b), package_gate=lambda: None)
    if foreign:
        with pytest.raises(SemanticGateClosed):
            a.appear(SimpleNamespace(name=name))
    else:
        assert not a.appear(SimpleNamespace(name=name))
        with pytest.raises(SemanticGateClosed):
            a.click(SimpleNamespace(name='DOSSIER_REWARD_RECEIVE'))
    assert not b.taps


@pytest.mark.parametrize('change', [None, 'counter', 'duplicate', 'generation'])
def test_archive_sync_page_identity_is_independent_of_reward_completeness(change):
    from tests.semantic_support.observer_fixtures import FakeBackend, make_ui
    root = ROOT.replace('ArchivesWorldBossEmptyUI', 'ArchivesWorldBossListUI')
    b = FakeBackend([make_button('back', root+'blur_panel/adapt/top/back', raycast_top=None)])
    b.ui = make_ui([make_text('53590', root+'main/award/pt/Text'),
                    make_text('同步值(53590/70000)', root+'main/list/scrollrect/content/0/underway/label')])
    if change == 'counter': b.ui['texts'][0]['text'] = '53500'
    if change == 'duplicate':
        b.ui['texts'].append(dict(b.ui['texts'][0])); b.ui['text_count'] += 1
    if change == 'generation': b.ui['generation'] += 3
    a = AlasSemanticAdapter(make_oracle(b), package_gate=lambda: None)
    if change:
        with pytest.raises(SemanticGateClosed): a.appear(SimpleNamespace(name='DOSSIER_REWARD_CHECK'))
    else:
        assert a.appear(SimpleNamespace(name='DOSSIER_REWARD_CHECK'))
        assert not a.appear(SimpleNamespace(name='FLEET_CHECK'))
        assert a.oracle.meta_page_visible()
        with pytest.raises(SemanticGateClosed): a.appear(SimpleNamespace(name='DOSSIER_REWARD_RECEIVE'))
    assert not b.taps


@pytest.mark.parametrize('sync_page', [False, True])
@pytest.mark.parametrize('active', [False, True])
@pytest.mark.parametrize('change', [None, 'missing', 'duplicate', 'truncated', 'disabled', 'generation'])
def test_explicit_archive_eligibility_keeps_inactive_and_unknown_distinct(sync_page, active, change):
    from tests.semantic_support.observer_fixtures import FakeBackend, make_ui
    if sync_page:
        root = ROOT.replace('ArchivesWorldBossEmptyUI', 'ArchivesWorldBossListUI')
        b = FakeBackend([make_button('back', root+'blur_panel/adapt/top/back', raycast_top=None)])
        b.ui = make_ui([make_text('53590', root+'main/award/pt/Text'),
                        make_text('同步值(53590/70000)', root+'main/list/scrollrect/content/0/underway/label')])
        path = root+'main/award/get_all'
    else:
        b = backend()
        path = ROOT+'archives_btn/tip'
    image = make_image(path, 'tip')
    image['active_in_hierarchy'] = image['active_and_enabled'] = active
    if not active: image['flags'] &= ~3
    if change == 'truncated': image['flags'] |= 0x10
    if change == 'disabled':
        image['active_in_hierarchy'] = True
        image['active_and_enabled'] = False
    if change != 'missing': b.ui['images'].append(image)
    if change == 'duplicate': b.ui['images'].append(dict(image))
    b.ui['image_count'] = len(b.ui['images'])
    if change == 'generation': b.ui['generation'] += 3
    a = AlasSemanticAdapter(make_oracle(b), package_gate=lambda: None)
    if change:
        with pytest.raises(SemanticGateClosed): a.appear(SimpleNamespace(name='DOSSIER_REWARD_RECEIVE'))
    else:
        assert a.appear(SimpleNamespace(name='DOSSIER_REWARD_RECEIVE')) is active
    assert not b.taps
