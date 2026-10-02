"""Generic native navigation reward probes on an inherited commission list."""
from types import SimpleNamespace
import pytest
from alas_headless import AlasSemanticAdapter, AlasSemanticUnmapped
from tests.semantic_support.observer_fixtures import FakeBackend, make_button, make_oracle


@pytest.mark.parametrize('name', ['GET_ITEMS_1', 'GET_ITEMS_2', 'GET_ITEMS_3', 'GET_SHIP', 'MONTHLY_PASS_NOTICE'])
@pytest.mark.parametrize('foreign', [False, True])
def test_exact_commission_page_proves_only_uncovered_reward_absence(name, foreign):
    buttons = [make_button('back_btn', 'UICamera/Canvas/UIMain/EventUI(Clone)/blur_panel/adapt/top/back_btn')]
    if foreign:
        buttons.append(make_button('confirm', 'OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/button_container/custom_button_1(Clone)'))
    backend = FakeBackend(buttons)
    adapter = AlasSemanticAdapter(make_oracle(backend), package_gate=lambda: None)
    if foreign:
        with pytest.raises(AlasSemanticUnmapped):
            adapter.appear(SimpleNamespace(name=name))
    else:
        assert not adapter.appear(SimpleNamespace(name=name))
    assert backend.taps == []


@pytest.mark.parametrize('change', ['unknown', 'duplicate', 'loading', 'stale', 'foreground'])
def test_commission_monthly_absence_requires_existing_page_guards(change):
    from alas_headless import SemanticGateClosed
    target = make_button('back_btn', 'UICamera/Canvas/UIMain/EventUI(Clone)/blur_panel/adapt/top/back_btn')
    if change == 'unknown': target['path'] = target['path'].replace('EventUI', 'UnknownUI')
    records = [target, dict(target)] if change == 'duplicate' else [target]
    if change == 'loading': records.append(make_button('Loading(Clone)', 'OverlayCamera/Overlay/UIOverlay/Loading(Clone)'))
    backend = FakeBackend(records)
    if change == 'stale': backend.snapshot['age_ms'] = backend.buttons['age_ms'] = 99999
    if change == 'foreground': backend.foreground = 'com.android.settings/.Settings'
    adapter = AlasSemanticAdapter(make_oracle(backend), package_gate=lambda: None)
    with pytest.raises((AlasSemanticUnmapped, SemanticGateClosed)):
        # Inspect the boundary directly: appear() has existing bounded stale
        # observation grace so ALAS can take its next screenshot.
        adapter._appear_once(SimpleNamespace(name='MONTHLY_PASS_NOTICE'))
    assert backend.taps == []


def test_retained_r198_commission_frame_proves_monthly_absence():
    import json
    from pathlib import Path
    source = Path(__file__).resolve().parents[1] / 'artifacts/semantic-cn-r198-probe-failures.jsonl'
    if not source.exists(): pytest.skip('retained r198 frame unavailable')
    row = next(json.loads(line) for line in source.read_text(encoding='utf-8').splitlines()
               if json.loads(line)['resource'] == 'MONTHLY_PASS_NOTICE')
    backend = FakeBackend(row['state']['buttons_snapshot']['buttons'])
    adapter = AlasSemanticAdapter(make_oracle(backend), package_gate=lambda: None)
    assert adapter.appear(SimpleNamespace(name='MONTHLY_PASS_NOTICE')) is False
    assert backend.taps == []


def test_unidentified_return_page_does_not_prove_ship_reward_absence():
    backend = FakeBackend([make_button('back_btn', 'UICamera/Canvas/UIMain/UnknownUI(Clone)/blur_panel/adapt/top/back_btn')])
    adapter = AlasSemanticAdapter(make_oracle(backend), package_gate=lambda: None)
    with pytest.raises(AlasSemanticUnmapped):
        adapter.appear(SimpleNamespace(name='GET_SHIP'))
    assert backend.taps == []
