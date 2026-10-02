"""Mail for the typed ALAS boundary."""

from __future__ import annotations

import re
from typing import Optional, Tuple
from .contracts import OracleState
from .errors import SemanticGateClosed


def classify_mail_confirmation_text(value: str) -> str:
    plain = "".join(value.split())
    if plain == "※是否领取所有选中的邮件":
        return "claim"
    if plain in (
        "※是否删除所有选中的邮件",
        "确定要删除选中的已读邮件吗？<color=#238c40>（未领取附件的邮件将会保留）</color>",
    ):
        return "delete"
    if plain == "没有符合条件的邮件":
        return "empty"
    raise SemanticGateClosed("mail confirmation text is unsupported")


class MailOracle:
    """Mail operations sharing the oracle frame and input boundary."""

    def mail_count(self) -> Tuple[int, int]:
        """Return the explicit ``used/capacity`` marker from the pinned mail page."""

        button_state = self.read_state()
        return self._mail_count_from_state(button_state)

    def _mail_count_from_state(self, button_state: OracleState) -> Tuple[int, int]:
        page_back = self._unique(button_state, "mail/page/back")
        if not page_back.actionable or self._blocking_rules(
            button_state, "mail/page/back"
        ):
            raise SemanticGateClosed("mail page identity is not safely actionable")

        ui_state = self.read_text_state()
        suffix = "MailUI(Clone)/adapt/main/content/left/left_content/top/count"
        matches = tuple(
            item
            for item in ui_state.texts
            if item.path.endswith(suffix)
            and item.name == "count"
            and item.active_in_hierarchy
            and item.active_and_enabled
            and not item.truncated
            and item.bounds is not None
        )
        if len(matches) != 1:
            raise SemanticGateClosed("mail count marker is absent or ambiguous")
        plain = re.sub(r"<[^>]*>", "", matches[0].text).strip()
        count_match = re.fullmatch(r"(\d{1,3})/(\d{1,3})", plain)
        if count_match is None:
            raise SemanticGateClosed("mail count marker is malformed")
        used = int(count_match.group(1))
        capacity = int(count_match.group(2))
        if capacity <= 0 or used > capacity:
            raise SemanticGateClosed("mail count marker is inconsistent")
        return used, capacity

    def mail_surface_kind(self) -> Optional[str]:
        """Classify the exact mail layer from one atomic button snapshot."""

        state = self.read_state()
        if self._matches(state, "mail/confirm/claim") or self._matches(
            state, "mail/confirm/cancel"
        ):
            return "confirmation"
        if self._matches(state, "overlay/network-reconnect/confirm") or self._matches(
            state, "overlay/network-reconnect/cancel"
        ):
            # Text/label validation remains mandatory in enabled()/click().
            # This layer marker only prevents an underlying MailUI button from
            # being selected while a standard Msgbox owns the raycast surface.
            return "blocked"
        manager = self._matches(state, "mail/manage/back")
        if len(manager) > 1:
            raise SemanticGateClosed("mail manager back target is ambiguous")
        if manager and self._mail_manager_back_delegated_raycast_proven(state):
            return "manager"
        page = self._matches(state, "mail/page/back")
        if len(page) > 1:
            raise SemanticGateClosed("mail page back target is ambiguous")
        if page:
            return "page"
        return None

    def _mail_manager_back_delegated_raycast_proven(self, state: OracleState) -> bool:
        """Accept the exact UIOrigin manager back control despite false top-raycast."""

        matches = self._matches(state, "mail/manage/back")
        return bool(
            len(matches) == 1
            and matches[0].path.endswith("MailMgrMsgboxUI(Clone)/window/top/btnBack")
            and matches[0].active_in_hierarchy
            and matches[0].active_and_enabled
            and matches[0].interactable
            and matches[0].point is not None
            and matches[0].bounds is not None
            and not any("/Msgbox(Clone)/" in button.path for button in state.buttons)
        )

    def mail_is_empty(self) -> bool:
        """Classify empty mail only from the explicit typed counter."""

        state = self.read_state()
        if (self._mail_manager_back_delegated_raycast_proven(state)
                and not self._blocking_rules(state, "mail/manage/back")):
            # The manager can mount after ALAS' preceding batch-claim probe.
            # It owns this screenshot's foreground, so the empty-page sentinel
            # is absent. Do not parse its covered MailUI counter or grant input.
            return False
        used, _ = self._mail_count_from_state(state)
        return used == 0

    def mail_confirmation_kind(self) -> Optional[str]:
        """Recognize the exact white-mail batch claim/delete confirmation."""

        state = self.read_state()
        confirm = self._matches(state, "mail/confirm/claim")
        cancel = self._matches(state, "mail/confirm/cancel")
        if not confirm and not cancel:
            return None
        ui_state = self.read_ui_state()
        texts = tuple(
            item
            for item in ui_state.texts
            if any(
                item.path.endswith(suffix)
                for suffix in (
                    "MailConfirmationMsgboxUI(Clone)/adapt/window/item_panel/tip/confire_text",
                    "MailConfirmationMsgboxUI(Clone)/adapt/window/msg_panel/content",
                )
            )
            and item.active_in_hierarchy
            and item.active_and_enabled
            and not item.truncated
        )
        confirm_labels = tuple(
            item
            for item in ui_state.texts
            if item.path.endswith(
                "MailConfirmationMsgboxUI(Clone)/adapt/window/button_container/btn_ok/Text"
            )
            and item.active_in_hierarchy
            and item.active_and_enabled
            and not item.truncated
        )
        cancel_labels = tuple(
            item
            for item in ui_state.texts
            if item.path.endswith(
                "MailConfirmationMsgboxUI(Clone)/adapt/window/button_container/btn_not/Text"
            )
            and item.active_in_hierarchy
            and item.active_and_enabled
            and not item.truncated
        )
        if (
            len(confirm) != 1
            or len(cancel) != 1
            or len(texts) != 1
            or len(confirm_labels) != 1
            or len(cancel_labels) != 1
            or "".join(confirm_labels[0].text.split()) != "确定"
            or "".join(cancel_labels[0].text.split()) != "取消"
        ):
            raise SemanticGateClosed("mail confirmation is incomplete or ambiguous")
        return classify_mail_confirmation_text(texts[0].text)

    def main_mail_unread_count(self) -> int:
        """Read the exact numeric badge attached to the pinned main mail Button."""

        button_state = self.read_state()
        mail = self._unique(button_state, "main/mail")
        if not mail.actionable or self._blocking_rules(button_state, "main/mail"):
            raise SemanticGateClosed("main mail identity is not safely actionable")
        ui_state = self.read_ui_state()
        suffix = "NewMainMellowTheme(Clone)/frame/top/btns/mail/Text"
        matches = tuple(
            item
            for item in ui_state.texts
            if item.name == "Text"
            and item.path.endswith(suffix)
            and item.active_in_hierarchy
            and item.active_and_enabled
            and not item.truncated
            and item.bounds is not None
        )
        if not matches:
            return 0
        if len(matches) != 1 or re.fullmatch(r"[1-9]\d{0,2}", matches[0].text) is None:
            raise SemanticGateClosed("main mail unread badge is malformed or ambiguous")
        return int(matches[0].text)
