"""Archives for the typed ALAS boundary."""

from __future__ import annotations

import time
from ...semantic_oracle import SemanticGateClosed
from .dispatch_result import UNHANDLED


class ArchivesPorts:
    """Archives ports on the shared adapter context."""

    def _click_archives(self, name):
        if name == "DATA_KEY_COLLECT":
            if self._data_key_context is not None:
                target = self._award_close_target()
                if target is not None:
                    return self.oracle.click(target)
                receipt = self.oracle.click_war_archives_data_key_collect()
                self._data_key_context.collect_receipt = receipt
                self._data_key_context.passive_transition_until = (
                    time.monotonic() + 60.0
                )
                return receipt
            return self.oracle.click_war_archives_data_key_collect()
        if self._data_key_context is not None and name in (
            "GET_ITEMS_1",
            "GET_ITEMS_2",
        ):
            target = self._award_close_target()
            if target is None:
                raise SemanticGateClosed("Data Key reward popup is absent")
            receipt = self.oracle.click(target)
            self._data_key_context.passive_transition_until = (
                time.monotonic() + 60.0
            )
            return receipt
        if self._data_key_context is not None and name in (
            "POPUP_CONFIRM",
            "POPUP_CANCEL",
            "POPUP_CONFIRM_DATA_KEY_LIMIT",
            "POPUP_CANCEL_DATA_KEY_LIMIT",
        ):
            context = self._data_key_context
            if not self.oracle.data_key_limit_prompt_visible():
                raise SemanticGateClosed("data-key limit prompt is absent")
            if name in ("POPUP_CONFIRM", "POPUP_CONFIRM_DATA_KEY_LIMIT"):
                if not context.force_collect or context.collect_receipt is None:
                    raise SemanticGateClosed(
                        "data-key limit confirmation requires ForceCollect and a preceding claim"
                    )
                if context.confirmation_receipt is not None:
                    return context.confirmation_receipt
                receipt = self.oracle.click_data_key_limit_choice(confirm=True)
                context.confirmation_receipt = receipt
                context.passive_transition_until = time.monotonic() + 60.0
                return receipt
            receipt = self.oracle.click_data_key_limit_choice(confirm=False)
            context.passive_transition_until = time.monotonic() + 60.0
            return receipt
        return UNHANDLED
