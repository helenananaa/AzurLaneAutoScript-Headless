"""Original native CV keep/confirm + shared ports; CONTROLLED game transitions.

The initial old-selection journal is a controlled owned source batch. Existing
old-retire tests cover its real selection ports; this covers confirmation onward.
One-click includes actual settings/quick-select ports and the native callback.
No record here is live-device qualification.
"""
import ast
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from types import MethodType, SimpleNamespace as N
from unittest.mock import Mock, patch

import pytest

from alas_headless.oracle.contracts import ActionReceipt
from alas_headless.oracle.errors import SemanticGateClosed
from alas_headless.oracle.old_retirement_contracts import OldRetirementCard, OldRetirementSelectionReceipt
from alas_headless.oracle.old_retirement_dialog import NativeOldRetirementDialogBoundary
from tests.semantic_support.observer_fixtures import set_retirement_selection, set_retirement_settings, make_text
from tests.test_dock_equipment_disassembly import equipment, confirmation, award

from tests.semantic_support.common_cv import rig as make_rig, native_host, NATIVE_FIXTURE


def test_qualified_native_methods_match_current_local_runtime_when_available():
    current = Path('E:/Runtime/ALAS/redroid-live-20261022/module/retire/retirement.py')
    if not current.is_file():
        pytest.skip('local qualified native tree unavailable')
    def methods(path):
        cls = next(node for node in ast.parse(path.read_text(encoding='utf-8')).body
                   if isinstance(node, ast.ClassDef) and node.name == 'Retirement')
        return {node.name: node for node in cls.body if isinstance(node, ast.FunctionDef)}
    expected, actual = methods(NATIVE_FIXTURE), methods(current)
    assert all(ast.dump(node, include_attributes=False) == ast.dump(actual[name], include_attributes=False)
               for name, node in expected.items())


def flow(monkeypatch, mode, *, only_one=False, unknown_ship=False, callback_noop=False):
    monkeypatch.setenv('ALAS_SEMANTIC_DOCK_EQUIPMENT_POLICY', 'disassemble')
    r = make_rig(monkeypatch, budget=1)
    actual_cards = r.oracle._retirement_cv_cards_from_records(*r.oracle._retirement_records())
    old_cards = sorted((card for card in actual_cards if card.template_id in (206011, 107041)),
                       key=lambda card: (card.template_id != 206011, card.button.bounds.top, card.button.bounds.left))
    assert len(old_cards) == 3
    modal = deepcopy((r.handle.snapshot, r.handle.buttons, r.handle.ui))
    if only_one or mode == 'old':
        root = 'OverlayCamera/Overlay/UIMain/DestoryInfoUI(Clone)/frame/sliders/content/'
        retained = {card.instance_id for card in old_cards[:1 if only_one else 3]}
        modal[1]['buttons'] = [b for b in modal[1]['buttons']
                              if not b['path'].startswith(root) or b.get('instance_id') in retained]
        modal[1]['button_count'] = len(modal[1]['buttons'])
        for text in modal[2]['texts']:
            if text['path'].endswith('/bottom_info/bg_input/count'):
                text['text'] = str(len(retained))
    source_count = 1 if only_one else (3 if mode == 'old' else 13)
    owner_pid = r.handle.pid
    revision = r.handle.snapshot['driver_revision']
    model = dict(phase='preconfirm' if mode == 'old' else 'empty', clock=0., screens=0,
                 ship_submissions=0, deselections=0)
    r.oracle._monotonic = lambda: model['clock']
    r.oracle._sleep = lambda seconds: model.update(clock=model['clock'] + seconds)
    def normalize(generation):
        for packet in (r.handle.snapshot, r.handle.buttons, r.handle.ui):
            packet.update(pid=owner_pid, driver_revision=revision, generation=generation)
        r.handle.ui['retirement_preconfirm_scroll'] = dict(
            schema='alas-headless.retirement-scroll/v1', status=0,
            scrollbar=dict(schema='alas-headless.retirement-scrollbar/v1', status=0))
    def selection(generation, used, selected=0):
        set_retirement_selection(r.handle, generation, used, selected=selected)
        for text in r.handle.ui['texts']:
            if text['path'].endswith('/capacity/Text'):
                text['text'] = str(used) + '/1010'
        if selected:
            r.handle.ui['texts'].append(make_text('确 定',
                'root/OverlayCamera/Overlay/UIMain/blur_panel/select_panel/confirm_button/confirm'))
            r.handle.ui['text_count'] = len(r.handle.ui['texts'])
        normalize(generation)
    def load_modal(generation):
        r.handle.snapshot, r.handle.buttons, r.handle.ui = deepcopy(modal)
        normalize(generation)
    if mode == 'oneclick':
        selection(r.handle.snapshot['generation'] + 1, 873)
    else:
        load_modal(r.handle.snapshot['generation'] + 1)
    r.delegate.refresh_frame()
    host = native_host(r.delegate)
    host.config.__dict__.update(OldRetire_SR=False, OldRetire_SSR=False,
        Retirement_RetireMode='old_retire' if mode == 'old' else 'one_click_retire', SERVER='cn',
        OneClickRetire_KeepLimitBreak='keep_limit_break')
    host.__dict__.update(_unable_to_enhance=False, retire_keep_common_cv=True,
        interval_clear=Mock(), interval_reset=Mock(), popup_interval_clear=Mock(),
        handle_popup_confirm=Mock(return_value=False),
        appear=lambda alias, **kw: r.delegate.appear(alias),
        match_template_color=lambda alias, **kw: r.delegate.match_template_color(alias),
        appear_then_click=lambda alias, **kw: r.delegate.click_if_present(alias) is not None)
    def screenshot():
        model['screens'] += 1
        model['clock'] += .5
        assert model['screens'] <= 60, 'controlled native observation limit'
        r.delegate.refresh_frame()
    host.device.screenshot = screenshot
    host.device.click = r.delegate.click
    namespace = host.keep_one_common_cv.__func__.__globals__
    class Timer:
        def __init__(self, seconds, **kw):
            self.seconds, self.since = seconds, model['clock']
        def start(self):
            self.since = model['clock']
            return self
        reset = start
        def reached(self):
            return model['clock'] - self.since >= self.seconds
    namespace['Timer'] = Timer
    source = NATIVE_FIXTURE.read_text(encoding='utf-8')
    cls = next(n for n in ast.parse(source).body if isinstance(n, ast.ClassDef) and n.name == 'Retirement')
    methods = [n for n in cls.body if isinstance(n, ast.FunctionDef)
               and n.name in ('_retirement_confirm', 'retire_ships_one_click', 'retire_ships_old')]
    for node in methods:
        for value in ast.walk(node):
            if isinstance(value, ast.Name) and value.id.isupper():
                namespace.setdefault(value.id, value.id)
    exec(compile(ast.fix_missing_locations(ast.Module(body=methods, type_ignores=[])),
                 'actual-native-CV-confirmation', 'exec'), namespace)
    for node in methods:
        setattr(host, node.name, MethodType(namespace[node.name], host))

    if mode == 'old':
        r.delegate.require_old_retirement_with_cv_policy()
        with r.delegate.retirement_preconfirm_scope(object()):
            target = r.delegate.retirement_match_common_cv('HERMES')
        # This setup observation does not represent an executed native policy.
        r.delegate._retirement_cv_completed_scopes = 0
        before = replace(r.oracle.retirement_selection_state(), selected_count=0,
                         generation=r.handle.snapshot['generation'] - 40)
        cards, selections = [], []
        for index in range(source_count):
            observed = old_cards[index]
            card = OldRetirementCard(observed.template_id, 10000 + index, observed.name,
                                     observed.level, 'N', observed.button)
            generation = before.generation + index * 2
            action = ActionReceipt('retirement/old/select', generation,
                card.button.point, card.button.bounds, 'controlled/Dock/source/' + str(index))
            selections.append(OldRetirementSelectionReceipt(action, owner_pid, card.template_id,
                card.instance_id, index, index + 1, 873, generation + 1))
            cards.append(card)
        r.delegate._register_old_retirement_cards(before, N(snapshot={'pid': owner_pid}),
            tuple(cards), ('N',), 14, require_common_cv=True)
        r.delegate._old_retirement_batch['selected'] = cards
        r.delegate._old_retirement_batch['selections'] = selections
        # Start original retire_ships_old at its selected Dock boundary, not an
        # impossible >10 original batch. Selection journal is controlled; its
        # input ports have separate actual shared-Session coverage.
        selection(r.handle.snapshot['generation'] + 1, 873, selected=source_count)
        r.delegate.refresh_frame()
        model['phase'] = 'selected'
        host._retirement_choose = lambda **kw: source_count
        host.handle_dock_cards_loading = Mock()
        for name in ('old_retirement_set_sort', 'old_retirement_set_favourite', 'old_retirement_set_filter'):
            monkeypatch.setattr(r.delegate, name, Mock())

    cv_tap = r.oracle._tap_backend
    def tap(x, y):
        phase = model['phase']
        generation = r.handle.snapshot['generation'] + 1
        if phase == 'preconfirm':
            cv_tap(x, y)
            model.update(phase='protected', deselections=model['deselections'] + 1)
            if only_one:
                selection(generation, 873)  # Controlled empty modal closes.
            return
        assert r.clock.current_frame_id is None, 'dispatch must invalidate source frame'
        r.handle.taps.append((x, y))
        if phase == 'empty' and (x, y) == (36, 520):
            set_retirement_settings(r.handle, generation, keep_needed=True)
            model['phase'] = 'settings'
        elif phase == 'settings':
            selection(generation, 873)
            model['phase'] = 'empty'
        elif phase == 'empty':
            load_modal(generation)
            model['phase'] = 'preconfirm'
        elif phase == 'selected':
            load_modal(generation)
            model['phase'] = 'preconfirm'
        elif phase == 'protected':
            assert not only_one, 'keep-only path must not submit a ship'
            model['ship_submissions'] += 1
            if unknown_ship:
                raise OSError('controlled final ship result unknown')
            award(r.handle, generation)
            model['phase'] = 'ship-award'
        elif phase == 'ship-award':
            equipment(r.handle, generation)
            model['phase'] = 'equipment'
        elif phase == 'equipment':
            confirmation(r.handle, generation)
            model['phase'] = 'destroy-confirm'
        elif phase == 'destroy-confirm':
            award(r.handle, generation)
            model['phase'] = 'equipment-award'
        elif phase == 'equipment-award':
            selection(generation, 873 - (source_count - 1))
            model['phase'] = 'returned'
        else:
            raise AssertionError('unexpected controlled phase ' + phase)
        normalize(generation)
    r.oracle._tap_backend = tap
    if callback_noop:
        host.keep_one_common_cv = lambda: None
    def invoke():
        with patch('alas_headless.current_semantic_session', return_value=r.delegate):
            return host.retire_ships_old(amount=source_count, rarity=('N',)) if mode == 'old' else host.retire_ships_one_click()
    return r, host, model, invoke


@pytest.mark.parametrize('mode', ['old', 'oneclick'])
def test_original_native_preservation_confirmation_disassembly_and_physical_return(monkeypatch, mode):
    r, host, model, invoke = flow(monkeypatch, mode)
    result = invoke()
    receipt = r.delegate.retirement_receipt()
    assert model['deselections'] == model['ship_submissions'] == 1
    assert model['phase'] == 'returned'
    physical = 2 if mode == 'old' else 12
    assert receipt.retired_count == physical and (receipt.capacity_before, receipt.capacity_after) == (873, 873 - physical)
    assert receipt.equipment_disassembled and not receipt.equipment_preserved
    assert receipt.equipment_quantities == ((0, 2),)
    assert len(receipt.common_cv_preservation) == 1
    assert r.delegate.action_ledger.remaining('retirement.execute') == 0
    if mode == 'old':
        assert result == 3  # Original native selected counter is preserved.
        assert len(receipt.selected_ui_instances) == 3
        assert receipt.protected_source_candidates == ((10000,),)
        assert receipt.common_cv_preservation[0].modal_instance_id not in receipt.selected_ui_instances
    else:
        assert result == 12


@pytest.mark.parametrize('mode', ['old', 'oneclick'])
def test_keep_only_path_does_not_submit_or_manufacture_retirement(monkeypatch, mode):
    r, host, model, invoke = flow(monkeypatch, mode, only_one=True)
    with pytest.raises(SemanticGateClosed, match='no ships to submit; no ship submission'):
        invoke()
    assert model['deselections'] == 1 and model['ship_submissions'] == 0
    assert r.delegate.retirement_receipt() is None
    proof, = r.delegate.retirement_cv_receipts()
    assert (proof.selected_before, proof.selected_after, proof.capacity_used) == (1, 0, 873)


def test_native_callback_cannot_silently_skip_preservation_scope(monkeypatch):
    r, host, model, invoke = flow(monkeypatch, 'oneclick', callback_noop=True)
    with pytest.raises(SemanticGateClosed, match='scope did not complete'):
        invoke()
    assert model['ship_submissions'] == model['deselections'] == 0


def test_unknown_old_final_ship_result_is_retained_without_replay(monkeypatch):
    r, host, model, invoke = flow(monkeypatch, 'old', unknown_ship=True)
    with pytest.raises(OSError, match='result unknown'):
        invoke()
    pending = r.delegate.old_retirement_pending_evidence()
    assert pending['ship_submission_requested'] and pending['uncertain_requests']
    assert pending['physical_selected_count'] == 2
    assert pending['protected_source_candidates'] == ((10000,),)
    # A later fresh observation does not authorize resubmitting the unresolved
    # accepted phase. Stale-frame refusal is independently covered elsewhere.
    for packet in (r.handle.snapshot, r.handle.buttons, r.handle.ui):
        packet['generation'] += 1
    r.delegate.refresh_frame()
    with pytest.raises(SemanticGateClosed, match='already requested'):
        r.delegate._old_retirement_dialog.click('SHIP_CONFIRM_2')
    assert model['ship_submissions'] == 1


def test_new_native_entry_refuses_legacy_observer_before_settings_or_selection(monkeypatch):
    r, host, model, invoke = flow(monkeypatch, 'oneclick')
    del r.handle.ui['retirement_preconfirm_scroll']
    r.delegate.refresh_frame()
    with pytest.raises(SemanticGateClosed, match='observer capability is unavailable'):
        invoke()
    assert not r.handle.taps and model['phase'] == 'empty'
    assert r.delegate.action_ledger.remaining('retirement.execute') == 1
    assert r.delegate.unrelated_capability_probe() == 'unrelated capability remains available'


def test_new_native_unprotected_path_keeps_older_sdk_call_shape(monkeypatch):
    r, host, model, invoke = flow(monkeypatch, 'oneclick')
    host.retire_keep_common_cv = False
    calls = []
    old_sdk = N(retire_ships_one_click=lambda **kw: calls.append(kw) or 4)
    with patch('alas_headless.current_semantic_session', return_value=old_sdk):
        assert host.retire_ships_one_click() == 4
    assert calls == [dict(keep_limit_break=True)]
    assert not r.handle.taps


def test_new_native_protected_path_classifies_missing_sdk_port_without_input(monkeypatch):
    r, host, model, invoke = flow(monkeypatch, 'oneclick')
    calls = []
    old_sdk = N(retire_ships_one_click=lambda **kw: calls.append(kw) or 4)
    with patch('alas_headless.current_semantic_session', return_value=old_sdk):
        with pytest.raises(SemanticGateClosed, match='common-CV preservation port is unavailable'):
            host.retire_ships_one_click()
    assert not calls and not r.handle.taps


def test_additive_observer_metadata_does_not_disable_native_preservation(monkeypatch):
    r, host, model, invoke = flow(monkeypatch, 'oneclick')
    r.handle.ui['retirement_preconfirm_scroll']['future_optional'] = dict(extra=[1, 2, 3])
    r.handle.ui['future_unrelated'] = dict(version='new')
    r.delegate.refresh_frame()
    assert invoke() == 12
    assert model['ship_submissions'] == 1


def test_indistinguishable_source_copies_remain_candidates_without_fabricated_uuid(monkeypatch):
    r, host, model, invoke = flow(monkeypatch, 'old')
    invoke()
    receipt = r.delegate.retirement_receipt()
    batch = r.delegate._old_retirement_batch
    cards, selections = list(batch['selected']), list(batch['selections'])
    # Controlled accounting variant with two identical source cards. The
    # modal exports a different ID space, so preserve both possible sources.
    cards[1] = replace(cards[0], instance_id=cards[1].instance_id)
    selections[1] = replace(selections[1], template_id=cards[0].template_id)
    dialog = NativeOldRetirementDialogBoundary(lambda: None, lambda: None,
        before=batch['before'], owner_pid=batch['pid'], selected_cards=cards,
        selection_receipts=selections, allowed_rarities=('N',), dispatch_retirement=Mock(),
        require_common_cv=True)
    proof, = receipt.common_cv_preservation
    dialog.record_common_cv_preservation(proof)
    assert dialog.count == 2
    assert dialog.protected_source_candidates == [(10000, 10001)]
    assert tuple(c.instance_id for c in dialog.cards) == (10000, 10001, 10002)
    assert proof.modal_instance_id not in dialog.protected_source_candidates[0]
    with pytest.raises(SemanticGateClosed, match='does not match owned batch'):
        dialog.record_common_cv_preservation(proof)
    dialog.dispatch_retirement.assert_not_called()


def test_known_deselection_with_accounting_failure_is_retained_once_without_replay(monkeypatch):
    r, host, model, invoke = flow(monkeypatch, 'old')
    selected = r.delegate._old_retirement_batch['selected']
    selected[0] = replace(selected[0], name='controlled different source identity')
    with pytest.raises(SemanticGateClosed, match='no owned source candidate'):
        invoke()
    pending = r.delegate.retirement_cv_pending_evidence()
    assert pending['result_proven'] is True
    assert (pending['receipt'].selected_before, pending['receipt'].selected_after) == (3, 2)
    assert len(r.delegate.retirement_cv_receipts()) == 1
    assert model['deselections'] == 1 and model['ship_submissions'] == 0
    r.delegate.discard_old_retirement_task_state()
    assert r.delegate.retirement_cv_pending_evidence()['result_proven']
    with pytest.raises(SemanticGateClosed, match='unresolved'):
        with r.delegate.retirement_preconfirm_scope(object()):
            pass


def test_receipt_cannot_hide_protection_or_change_the_physical_delta(monkeypatch):
    r, host, model, invoke = flow(monkeypatch, 'old')
    invoke()
    receipt = r.delegate.retirement_receipt()
    with pytest.raises(ValueError, match='identities are inconsistent'):
        replace(receipt, common_cv_preservation=(), protected_source_candidates=())
    with pytest.raises(ValueError, match='protected source evidence'):
        replace(receipt, protected_source_candidates=())
    with pytest.raises(ValueError, match='physical count disagree'):
        replace(receipt, common_cv_preservation=(replace(receipt.common_cv_preservation[0], selected_after=1),))
