"""Typed retirement Scrollbar ports; original ALAS owns page-search loops."""
from collections.abc import Mapping
from .errors import SemanticGateClosed
from .linked_scrollbar_owner import RETIREMENT_SCROLLBAR_OWNER


class RetirementScrollOracle:
    def require_retirement_common_cv_capability(self):
        # Optional export capability, not a version/hash allowlist. Specific
        # modal, card and drag proofs are checked again at each actual action.
        _, ui = self._retirement_records()
        family = ui.snapshot.get(RETIREMENT_SCROLLBAR_OWNER.family_key)
        if (not isinstance(family, Mapping)
                or family.get('schema') != 'alas-headless.retirement-scroll/v1'
                or not isinstance(family.get('scrollbar'), Mapping)
                or family['scrollbar'].get('schema') != RETIREMENT_SCROLLBAR_OWNER.bar_schema):
            raise SemanticGateClosed('retirement common-CV observer capability is unavailable')

    def _linked_scrollbar_records(self, owner):
        if owner != RETIREMENT_SCROLLBAR_OWNER:
            return super()._linked_scrollbar_records(owner)
        if self._retirement_preconfirm() is None:
            raise SemanticGateClosed('retirement preconfirmation owner is absent')
        # Unrelated Dock images may exhaust their global cap. The linked
        # Scrollbar family has its OWN complete records and does not use them.
        return self._retirement_records()

    def retirement_preconfirm_scrollbar_visible(self):
        _, ui = self._linked_scrollbar_records(RETIREMENT_SCROLLBAR_OWNER)
        family = ui.snapshot.get(RETIREMENT_SCROLLBAR_OWNER.family_key)
        raw = family.get('scrollbar') if isinstance(family, Mapping) else None
        if (isinstance(raw, Mapping) and raw.get('schema') == RETIREMENT_SCROLLBAR_OWNER.bar_schema
                and type(raw.get('status')) is int and raw['status'] == 3
                and raw.get('class_found') is True and type(raw.get('matches')) is int
                and raw['matches'] == 0):
            return False
        state = self.retirement_preconfirm_scrollbar_state()
        return state.size < 1 and all(c.active_in_hierarchy for c in state.controls)

    def retirement_preconfirm_scrollbar_state(self):
        return self._linked_scrollbar_state(RETIREMENT_SCROLLBAR_OWNER)

    def retirement_preconfirm_scrollbar_input_proof(self, point):
        return self._linked_scrollbar_input_proof(point, RETIREMENT_SCROLLBAR_OWNER)

    def retirement_preconfirm_scroll_position(self):
        return self._storage_vertical_position(self.retirement_preconfirm_scrollbar_state())

    def drag_retirement_preconfirm_scroll_toward(self, position):
        return self._drag_linked_scrollbar_toward(position, RETIREMENT_SCROLLBAR_OWNER)
