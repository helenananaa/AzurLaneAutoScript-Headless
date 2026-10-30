"""Common-CV ports for original ALAS; no task/search/retirement state machine."""
from contextlib import contextmanager
import time

from ...oracle.errors import SemanticGateClosed, SemanticOracleError
from ...oracle.retirement_cv import RetirementCvDeselectionReceipt


class CommonCvRetirementPorts:
    def _require_common_cv_capability(self):
        self._common_cv_fresh().require_retirement_common_cv_capability()
        if self.open()._dock_equipment_options().get('preserve_equipment', True):
            raise SemanticGateClosed('common-CV native retirement requires disassemble equipment policy')

    def retire_ships_with_common_cv_policy(self, *, keep_limit_break, native_keep):
        """New functional entry: old native shortcut remains guarded/closed."""
        if not callable(native_keep):
            raise SemanticGateClosed('original common-CV preservation callback is unavailable')
        self._require_common_cv_capability()
        def preserve():
            before = self._retirement_cv_completed_scopes
            self._retirement_cv_last_receipt = None
            native_keep()
            if self._retirement_cv_completed_scopes != before + 1:
                raise SemanticGateClosed('original common-CV preservation scope did not complete')
            return self._retirement_cv_last_receipt
        return self.open().retire_ships_one_click(
            keep_limit_break, before_ship_confirmation=preserve)

    def require_old_retirement_with_cv_policy(self):
        self._require_common_cv_capability()
        self._old_retirement_cv_required = True
        self._old_retirement_cv_kept = False

    def _init_common_cv_state(self):
        self._retirement_cv_scope = None
        self._retirement_cv_last_pending = None
        self._retirement_cv_last_receipt = None
        self._retirement_cv_receipts = []
        self._retirement_cv_completed_scopes = 0
        self._old_retirement_cv_required = False
        self._old_retirement_cv_kept = False

    @contextmanager
    def retirement_preconfirm_scope(self, native_scroll):
        if self._retirement_cv_scope is not None or self._retirement_cv_last_pending is not None:
            raise SemanticGateClosed('common-CV preservation already has an owned or unresolved input')
        scope = dict(native_scroll=native_scroll, requested=False, pending=None)
        self._retirement_cv_scope = scope
        try:
            yield
            self._retirement_cv_completed_scopes += 1
            dialog = getattr(self, '_old_retirement_dialog', None)
            if dialog is not None:
                dialog.cv_policy_completed = True
            if scope['requested']:
                self._old_retirement_cv_kept = True
        finally:
            if scope['pending'] is not None:
                self._retirement_cv_last_pending = scope['pending']
            self._retirement_cv_scope = None

    def retirement_preconfirm_scroll_active(self, scroll):
        # Logical ownership of the ORIGINAL Scroll object, not a security
        # handshake or a generic name/asset-rectangle runtime allowlist.
        scope = self._retirement_cv_scope
        return scope is not None and scope['native_scroll'] is scroll

    def _common_cv_observe(self):
        return self.open()._frame_or_live_observation_oracle()

    def _common_cv_fresh(self):
        return self.open()._fresh_input_oracle()

    def _require_common_cv_scope(self):
        if self._retirement_cv_scope is None:
            raise SemanticGateClosed('common-CV port has no original native preservation scope')
        return self._retirement_cv_scope

    def retirement_preconfirm_scroll_state(self):
        self._require_common_cv_scope()
        return self._common_cv_observe().retirement_preconfirm_scrollbar_state()

    def retirement_preconfirm_scroll_visible(self):
        self._require_common_cv_scope()
        return self._common_cv_observe().retirement_preconfirm_scrollbar_visible()

    def retirement_preconfirm_scroll_position(self, state):
        self._require_common_cv_scope()
        return self.open().oracle._storage_vertical_position(state)

    def retirement_preconfirm_scroll_drag_toward(self, position):
        self._require_common_cv_scope()
        self.refresh_frame()
        adapter = self.open()
        adapter._package_gate()
        # The existing shared live query proves actual IDragHandler routing
        # and progress; the original Scroll.set loop owns further attempts.
        return adapter.oracle.drag_retirement_preconfirm_scroll_toward(position)

    def retirement_match_common_cv(self, native_name):
        self._require_common_cv_scope()
        return self._common_cv_observe().retirement_match_common_cv(native_name)

    def retirement_deselect_common_cv(self, target):
        scope = self._require_common_cv_scope()
        if scope['requested']:
            raise SemanticGateClosed('common-CV deselection was already requested; no input replay')

        def before_input(action):
            scope['requested'] = True
            scope['pending'] = dict(target=target, requested_action=action,
                                    input_requested=True, result_proven=False)

        action = self._common_cv_fresh().click_retirement_common_cv(target, before_input=before_input)
        last_error = None
        for _ in range(50):
            time.sleep(.1)
            try:
                self.refresh_frame()
                oracle = self._common_cv_observe()
                state, ui = oracle._retirement_records()
                selected = oracle.retirement_selection_state((state, ui))
                scope['pending']['last_observation'] = dict(state=state, ui=ui)
                if (state.snapshot['pid'] != target.pid
                        or (selected.capacity_used, selected.capacity_total)
                        != (target.capacity_used, target.capacity_total)):
                    raise SemanticGateClosed('common-CV owner or capacity changed after input')
                if ui.generation <= action.generation or selected.selected_count != target.selected_count - 1:
                    continue
                identity_resolved, reused_template = oracle.retirement_cv_deselection_instance_postcondition(
                    target, (state, ui))
                if not identity_resolved:
                    continue
                receipt = RetirementCvDeselectionReceipt(
                    action, target.pid, target.card.instance_id, target.card.template_id,
                    target.card.name, target.card.level, target.selected_count, selected.selected_count,
                    target.capacity_used, target.capacity_total, ui.generation,
                    post_instance_reused_by_template=reused_template)
                scope['pending'].update(result_proven=True, receipt=receipt)
                self._retirement_cv_last_receipt = receipt
                self._retirement_cv_receipts.append(receipt)
                dialog = getattr(self, '_old_retirement_dialog', None)
                if dialog is not None:
                    # Accounting is after the observed deselection, before
                    # final submission; failure preserves the known receipt.
                    dialog.record_common_cv_preservation(receipt)
                scope['pending'] = None
                return receipt
            except SemanticOracleError as exc:
                if scope['pending'] is not None and scope['pending'].get('result_proven'):
                    raise  # Proven input with failed accounting is not another observation attempt.
                last_error = exc
        raise SemanticGateClosed('common-CV deselection result is unproven; input not repeated') from last_error

    def retirement_cv_pending_evidence(self):
        scope = self._retirement_cv_scope
        return scope['pending'] if scope is not None else self._retirement_cv_last_pending

    def retirement_cv_receipts(self):
        return tuple(self._retirement_cv_receipts)

    def discard_common_cv_task_state(self):
        if self._retirement_cv_scope is not None:
            self._retirement_cv_last_pending = self._retirement_cv_scope['pending']
        self._retirement_cv_scope = None
        self._old_retirement_cv_required = False
        self._old_retirement_cv_kept = False
