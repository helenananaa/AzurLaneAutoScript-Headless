"""Mail for the typed ALAS boundary."""

from __future__ import annotations

import time
from ...alas_mail_config_contract import (
    AlasMailConfigSnapshot,
    validate_alas_mail_config,
)
from ...semantic_oracle import SemanticGateClosed, SemanticTargetMissing
from .contracts import AlasSemanticUnmapped, _MailFlowContext
from .dispatch_result import UNHANDLED
from .resources import (
    MAIL_CLICK_RESOURCES,
    MAIL_TOGGLE_TARGETS,
    MAIL_VIRTUAL_RESOURCES,
    MISSION_VIRTUAL_RESOURCES,
)


class MailAdapterPorts:
    """Mail ports on the shared adapter context."""

    def mail_reward_active(self) -> bool:
        """Return whether ALAS currently owns the white-mail flow."""

        return self._mail_context is not None

    def validate_mail_config(self, **values: object) -> AlasMailConfigSnapshot:
        return validate_alas_mail_config(**values)

    def begin_mail(self) -> None:
        """Open one ALAS-owned mail state-machine invocation."""

        self._package_gate()
        if (
            self._mail_context is not None
            or self._login_flow.active
            or self._mission_context is not None
            or self._research_context is not None
            or self._dorm_context is not None
            or self._supply_pack_context is not None
            or self._minigame_context is not None
            or self._build_context is not None
            or self._commission_context is not None
            or self._campaign_context is not None
        ):
            raise SemanticGateClosed("nested semantic ALAS flow is not allowed")
        self._mail_context = _MailFlowContext(
            passive_transition_until=time.monotonic() + 20.0,
        )

    def end_mail(self) -> None:
        self._mail_context = None

    def _known_mail_surface_exists(self) -> bool:
        return any(
            self.oracle.exists(semantic_id)
            for semantic_id in (
                "main/mail",
                "mail/page/back",
                "mail/manage",
                "mail/manage/back",
                "mail/manage/claim",
                "mail/manage/delete",
                "reward/award-info/close",
                "reward/award-info1/close",
            )
        )

    def _appear_mail_entry(self, name):
        if self._mail_context is not None:
            context = self._mail_context
            if time.monotonic() <= context.leaving_page_until:
                if name in (
                    "MAIN_GOTO_CAMPAIGN",
                    "MAIN_GOTO_CAMPAIGN_WHITE",
                ):
                    return self.oracle.main_page_visible()
                return False
            if not context.initial_surface_probed:
                context.surface_kind = self.oracle.mail_surface_kind()
                context.initial_surface_probed = True
                if context.surface_kind in ("manager", "page", "confirmation"):
                    context.recovered_existing_page = True
            surface = context.surface_kind
            if surface == "blocked":
                if name == "POPUP_CONFIRM":
                    return self.oracle.enabled("overlay/network-reconnect/confirm")
                if name == "POPUP_CANCEL":
                    return self.oracle.enabled("overlay/network-reconnect/cancel")
                return False
            if surface in ("manager", "page"):
                if name == "MAIL_CHECK":
                    return True
                if name == "MAIL_MANAGE":
                    return surface == "manager"
                if name == "GOTO_MAIN_WHITE":
                    return True
                if name in (
                    "MAIN_GOTO_CAMPAIGN",
                    "MAIN_GOTO_CAMPAIGN_WHITE",
                ):
                    return False
                if name not in (
                    "POPUP_CONFIRM",
                    "POPUP_CANCEL",
                    "POPUP_CONFIRM_UI_ADDITIONAL",
                    "POPUP_CONFIRM_MAIL_CLAIM",
                    "POPUP_CONFIRM_MAIL_QUIT",
                    *MAIL_VIRTUAL_RESOURCES,
                ):
                    return False
        return UNHANDLED

    def _appear_mail(self, name):
        if (self._mail_context is None and name == "GOTO_MAIN_WHITE"
                and any(self.oracle.observation_target_present(target)
                        and self.oracle.enabled(target)
                        for target in ('mail/manage/back', 'mail/page/back'))):
            # Other tasks can inherit this overlay. The native page recovery
            # owns its exact back edge, then rediscovers the underlying MailUI.
            return True
        if self._mail_context is not None and name == "MAIL_MANAGE":
            return bool(
                self.oracle.enabled("mail/manage")
                or self.oracle.enabled("mail/manage/back")
            )
        if self._mail_context is not None and name in ("POPUP_CONFIRM", "POPUP_CANCEL"):
            kind = self.oracle.mail_confirmation_kind()
            if (
                kind is not None
                and self._mail_context.pending_confirmation is None
            ):
                self._mail_context.recovered_existing_page = True
                if kind == "empty":
                    self._mail_context.pending_confirmation = kind
                    self._mail_context.recovered_confirmation = False
                elif self._action_ledger.allowed("mail.mutation"):
                    self._mail_context.pending_confirmation = kind
                    self._mail_context.recovered_confirmation = True
            matched = bool(
                kind is not None
                and (
                    kind == self._mail_context.pending_confirmation
                    or (
                        kind == "empty"
                        and self._mail_context.pending_confirmation in ("claim", "delete")
                    )
                )
            )
            return matched
        if self._mail_context is not None and name == "MAIL_CHECK":
            # MailMgrMsgboxUI overlays, but does not replace, the MailUI page.
            # Preserve ALAS' page identity only while the exact manager back
            # control proves that this is the owned mail overlay.
            if self.oracle.enabled("mail/manage/back"):
                self._mail_context.recovered_existing_page = True
                return self.oracle.exists("mail/page/back")
            if self.oracle.enabled("mail/page/back"):
                # An interrupted prior invocation may leave the exact MailUI
                # page itself foregrounded with no manager overlay.
                self._mail_context.recovered_existing_page = True
                return True
        if (
            self._mail_context is not None
            and name in ("MAIN_GOTO_CAMPAIGN", "MAIN_GOTO_CAMPAIGN_WHITE")
        ):
            # ALAS uses the battle entrance as the new-main page identity.  On
            # return from MailUI it can mount one frame before the formation
            # entrance; only the complete exact main-page pair is a stable
            # destination for this flow.
            if self.oracle.enabled("mail/manage/back"):
                return False
            if self.oracle.enabled("mail/page/back"):
                return False
            return self.oracle.main_page_visible()
        if self._mail_context is not None and name in MAIL_VIRTUAL_RESOURCES:
            if name == "GOTO_MAIN_WHITE":
                return bool(
                    self.oracle.enabled("mail/manage/back")
                    or self.oracle.enabled("mail/page/back")
                )
            if name in ("GET_ITEMS_1", "GET_ITEMS_2"):
                return self._award_close_target() is not None
            if name == "MAIL_BATCH_CLAIM":
                return self.oracle.enabled("mail/manage/claim")
            if name == "MAIL_BATCH_DELETE":
                return self.oracle.enabled("mail/manage/delete")
            if name == "MAIL_WHITE_EMPTY":
                if (self.oracle.exists("mail/manage/back")
                        and self.oracle.enabled("mail/manage/back")):
                    # The manager can finish mounting between ALAS' claim
                    # probe and this empty-page probe. The next native loop
                    # owns its claim sentinel; never read the covered page.
                    return False
                # MailWhite probes this while it is still waiting for the
                # navigation click to mount MailUI.  An empty-mail reading
                # needs the exact page tree (and its count text), whereas a
                # pre-mount probe is only an ALAS control-flow sentinel.
                # Treat that transient state as a passive non-match.
                if not self.oracle.exists("mail/page/back"):
                    return False
                return self.oracle.mail_is_empty()
            return False
        if (
            self._mail_context is None
            and name in MAIL_VIRTUAL_RESOURCES
            and name not in MISSION_VIRTUAL_RESOURCES
        ):
            if name == 'GOTO_MAIN_WHITE':
                reader = self._frame_or_live_observation_oracle()
                if not any(reader.exists(target) for target in
                           ('mail/manage/back', 'mail/page/back')):
                    # Native UI discovery probes this before campaign's
                    # withdrawal confirmation. A complete frame without a
                    # Mail back control proves absence, not flow misuse.
                    return False
            if self._inherited_login_allows_passive_probe():
                # Native page discovery can inherit LoginUI2 while another
                # task still owns the adapter. This is only a mail absence
                # probe; the reviewed login input port keeps its own checks.
                return False
            if (
                self.oracle.daily_page_visible()
                or self.oracle.daily_precombat_visible()
            ):
                # ui_get_current_page() probes the white-theme mail escape
                # before DAILY_CHECK.  A typed Daily root proves that this is
                # only a page-enumeration miss, not mail-flow misuse.
                return False
            if self._commission_context is not None:
                # ui_get_current_page() probes Mail's white-theme escape while
                # a restarted Commission invocation may still be inside one
                # of the typed multi-reward popups. It is presence-only here.
                return False
            raise AlasSemanticUnmapped(
                "ALAS mail resource used outside mail flow: {0}".format(name)
            )
        return UNHANDLED

    def _click_mail_blocked(self, name):
        if (
            self._mail_context is not None
            and self._mail_context.surface_kind == "blocked"
            and name in ("POPUP_CONFIRM", "POPUP_CANCEL")
        ):
            target = (
                "overlay/network-reconnect/confirm"
                if name == "POPUP_CONFIRM"
                else "overlay/network-reconnect/cancel"
            )
            receipt = self.oracle.click(target)
            self._mail_context.initial_surface_probed = False
            self._mail_context.surface_kind = None
            return receipt
        return UNHANDLED

    def _click_mail_manager(self, name):
        if self._mail_context is not None and name == "MAIL_MANAGE":
            if self.oracle.enabled("mail/manage/back"):
                return self.oracle.click("mail/manage/back")
            return self.oracle.click("mail/manage")
        if self._mail_context is not None and name == "POPUP_CONFIRM":
            # Route the shared ALAS popup asset through the owned mail flow
            # before the generic mapping can interpret it as a network
            # reconnect confirmation.
            context = self._mail_context
            kind = self.oracle.mail_confirmation_kind()
            if kind is None:
                # The positive screenshot may precede an already accepted
                # confirmation producing its reward. No current prompt means
                # no input; native click_if_present returns to its own loop.
                raise SemanticTargetMissing('mail confirmation disappeared before input')
            if not (
                kind == context.pending_confirmation
                or (
                    kind == "empty"
                    and context.pending_confirmation in ("claim", "delete")
                )
            ):
                raise SemanticGateClosed("mail confirmation identity changed")
            if context.recovered_confirmation and kind != "empty":
                receipt = self._dispatch_mutation(
                    "mail.mutation",
                    lambda: self.oracle.click("mail/confirm/claim"),
                )
            else:
                receipt = self.oracle.click("mail/confirm/claim")
            context.pending_confirmation = None
            context.recovered_confirmation = False
            return receipt
        return UNHANDLED

    def _click_mail(self, name):
        if (name == "GOTO_MAIN_WHITE" and self._mail_context is None
                and self.oracle.observation_target_present("mail/manage/back")
                and self.oracle.enabled("mail/manage/back")):
            receipt = self.oracle.click("mail/manage/back")
            deadline = time.monotonic() + 12.0
            while time.monotonic() < deadline:
                if (self.oracle.read_state().generation > receipt.generation
                        and not self.oracle.observation_target_present("mail/manage/back")
                        and self.oracle.enabled("mail/page/back")):
                    return receipt
                time.sleep(0.2)
            raise SemanticGateClosed("mail manager return did not restore mail page")
        if (name == "GOTO_MAIN_WHITE" and self._mail_context is None
                and self.oracle.observation_target_present("mail/page/back")
                and self.oracle.enabled("mail/page/back")):
            # ALAS may start another task while an earlier Mail invocation
            # left its page open. The generic page graph still owns this
            # exact return edge; it need not enter the Mail reward flow.
            receipt = self.oracle.click("mail/page/back")
            deadline = time.monotonic() + 12.0
            while time.monotonic() < deadline:
                if (self.oracle.read_state().generation > receipt.generation
                        and self.oracle.main_page_visible()
                        and not self.oracle.observation_target_present("mail/page/back")):
                    return receipt
                time.sleep(0.2)
            raise SemanticGateClosed("mail page return did not reach main")
        if self._mail_context is not None and name in MAIL_CLICK_RESOURCES:
            toggle_target = MAIL_TOGGLE_TARGETS.get(name)
            if toggle_target is not None:
                return self.oracle.click_toggle(toggle_target)
            if name in ("MAIL_BATCH_CLAIM", "MAIL_BATCH_DELETE"):
                # MailWhite reuses MAIL_BATCH_CLAIM as its generic dismiss
                # input after a successful claim has opened an award popup.
                # That input is a read-only popup-close continuation, not a
                # second manager mutation.  The manager action is no longer
                # actionable behind that foreground popup, which gives this
                # otherwise overloaded ALAS input an exact typed meaning.
                target = (
                    "mail/manage/claim"
                    if name == "MAIL_BATCH_CLAIM"
                    else "mail/manage/delete"
                )
                if name == "MAIL_BATCH_CLAIM" and not self.oracle.enabled(target):
                    award_target = self._award_close_target()
                    if award_target is not None:
                        return self.oracle.click(award_target)
                receipt = self._dispatch_mutation(
                    "mail.mutation",
                    lambda: self.oracle.click(target),
                )
                self._mail_context.pending_confirmation = (
                    "claim" if name == "MAIL_BATCH_CLAIM" else "delete"
                )
                return receipt
            if name == "GOTO_MAIN_WHITE":
                if self._mail_context.surface_kind == "manager" or self.oracle.enabled("mail/manage/back"):
                    # Recovery may begin on a manager overlay left by an
                    # interrupted prior ALAS invocation. Its exact enabled
                    # back target is sufficient to dismiss only that overlay.
                    receipt = self.oracle.click("mail/manage/back")
                    self._mail_context.initial_surface_probed = False
                    self._mail_context.surface_kind = None
                    return receipt
                if not (
                    self._mail_context.entry_clicked
                    or self._mail_context.recovered_existing_page
                ):
                    raise SemanticGateClosed("mail entry identity is not proven")
                receipt = self.oracle.click("mail/page/back")
                self._mail_context.initial_surface_probed = False
                self._mail_context.surface_kind = None
                self._mail_context.leaving_page_until = time.monotonic() + 12.0
                return receipt
            if name in ("GET_ITEMS_1", "GET_ITEMS_2"):
                target = self._award_close_target()
                if target is None:
                    raise SemanticGateClosed("reviewed mail reward popup is absent")
                return self.oracle.click(target)
        return UNHANDLED
