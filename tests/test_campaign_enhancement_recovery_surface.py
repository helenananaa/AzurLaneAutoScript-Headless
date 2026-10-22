import json
import itertools
from pathlib import Path
from types import SimpleNamespace
import pytest
from alas_headless import AlasSemanticAdapter
from alas_headless.semantic_oracle import SemanticGateClosed
from tests.semantic_support.adapter_fixtures import FakeOracle
from tests.semantic_support.observer_fixtures import FakeBackend, make_ui, make_oracle


def test_retained_native_enhancement_dock_is_a_readonly_recovery_surface():
    p = Path(__file__).resolve().parents[1] / 'artifacts/semantic-cn-r30-combat-readonly-2-20260930.json'
    if not p.exists():
        pytest.skip('native r30 retained Dock observation unavailable')
    r = json.loads(p.read_text(encoding='utf-8'))
    backend = FakeBackend(r['state']['buttons_snapshot']['buttons'])
    ui = r['ui']['snapshot']
    backend.ui = make_ui(ui['texts'], images=ui['images'], toggles=ui['toggles'])
    oracle = make_oracle(backend)
    assert oracle.enhancement_dock_visible() is True
    assert oracle.campaign_is_in_map() is False
    assert backend.taps == []


def test_absent_enhancement_dock_does_not_parse_foreign_ui():
    oracle = make_oracle(FakeBackend([]))
    oracle.read_ui_state = lambda **kw: (_ for _ in ()).throw(AssertionError('foreign UI'))
    assert oracle.enhancement_dock_visible() is False


@pytest.mark.parametrize('dock', [True, False])
def test_auto_search_dispatches_original_recovery_only_on_proven_dock(dock, monkeypatch):
    from alas_headless.adapter.semantic import campaign
    clock = itertools.count(0, 10)
    monkeypatch.setattr(campaign.time, 'monotonic', lambda: next(clock))
    monkeypatch.setattr(campaign.time, 'sleep', lambda _: None)
    oracle = FakeOracle()
    oracle.campaign_dock_full_visible = lambda *_: False
    oracle.retirement_selection_visible = lambda: False
    oracle.enhancement_dock_visible = lambda: dock
    oracle.campaign_official_combat_auto_state = lambda: None
    adapter = AlasSemanticAdapter(oracle, package_gate=lambda: None)
    adapter.begin_campaign_pre_sortie('D3', mode='hard')
    adapter._campaign_context.sortie_proof = SimpleNamespace(map_generation=1)
    adapter._campaign_context.auto_search_role_state = SimpleNamespace()
    calls = []
    class Recovered(Exception):
        pass
    def original_handler():
        calls.append('original')
        raise Recovered()
    if dock:
        with pytest.raises(Recovered):
            adapter.wait_campaign_auto_search_completion('d3', timeout_seconds=60, recovery_handler=original_handler)
        assert calls == ['original']
    else:
        with pytest.raises(SemanticGateClosed):
            adapter.wait_campaign_auto_search_completion('d3', timeout_seconds=60, recovery_handler=original_handler)
        assert calls == []
    assert oracle.click_calls == []
