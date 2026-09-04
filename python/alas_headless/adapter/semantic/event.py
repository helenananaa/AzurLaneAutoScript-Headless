"""Event for the typed ALAS boundary."""

from __future__ import annotations

import time
from ...semantic_oracle import SemanticGateClosed, SemanticTargetMissing
from .dispatch_result import UNHANDLED
from .resources import CAMPAIGN_VIRTUAL_RESOURCES, EVENT_CAMPAIGN_ASIDE_RESOURCES


class EventPorts:
    """Event ports on the shared adapter context."""

    def _appear_event(self, name, semantic_id):
        if semantic_id == "campaign-menu/event":
            if not self.oracle.campaign_menu_is_entry():
                return False
            return self.oracle.enabled("campaign-menu/event")
        if semantic_id == "event/mode/story":
            if name == "EVENT_CHECK":
                context = self._campaign_context
                if context is not None:
                    # `enter_map_cancel()` first asks whether it is already
                    # back on the event selector.  A strictly proven
                    # preparation layer legitimately covers that selector;
                    # report only this passive presence as absent so the
                    # original ALAS loop can continue to its existing
                    # MAP_PREPARATION/FLEET_PREPARATION cancel branch.  Do not
                    # use the transition-grace helper here: stale, duplicate,
                    # remounted, partial, or wrong-stage preparation state
                    # must remain fail-closed.
                    try:
                        preparation, _stage_code = (
                            self._campaign_preparation_state_with_stage()
                        )
                    except SemanticGateClosed as exc:
                        # `appear()` grants a short transition grace to a few
                        # generic observer errors.  Preparation identity is the
                        # deciding proof for this shadow case, so keep even
                        # those exact errors fail-closed at this boundary.
                        raise SemanticGateClosed(
                            "EVENT_CHECK campaign preparation proof failed: {0}".format(
                                exc
                            )
                        ) from exc
                    if preparation is not None:
                        kind = getattr(preparation, "kind", None)
                        if kind in ("map", "fleet"):
                            return False
                        raise SemanticGateClosed(
                            "campaign preparation overlay kind is invalid"
                        )
                try:
                    self.oracle.event_campaign_page_state()
                except SemanticTargetMissing:
                    return False
                if (
                    context is not None
                    and context.event_page_back_receipt is not None
                    and time.monotonic() <= context.passive_transition_until
                ):
                    # LevelSelectSPFullUI can retain its event-page identity for
                    # several frames after the exact back control has committed.
                    # Hide that stale source page so ui_goto() waits for the
                    # destination instead of submitting the one-shot back input
                    # a second time.
                    return False
                return True
            return self.oracle.exists("event/mode/battle")
        if semantic_id == "event/mode/battle":
            return self.oracle.exists("event/mode/story")
        return UNHANDLED

    def _appear_event_selector(self, name, semantic_id):
        event_campaign_selector_visible = self.oracle.event_campaign_page_visible()
        if event_campaign_selector_visible and self._campaign_context is not None:
            try:
                event_campaign_selector_visible = (
                    self._campaign_preparation_state_with_stage()[0] is None
                )
            except SemanticGateClosed:
                if name in (
                    "MAP_PREPARATION",
                    "FLEET_PREPARATION",
                    "MAP_PREPARATION_CANCEL",
                ):
                    context = self._require_campaign_context()
                    if (
                        context.map_preparation_receipt is not None
                        and time.monotonic() <= context.passive_transition_until
                    ):
                        # Unity can reparent the just-closed LevelInfoSPUI
                        # under UIOrigin for a few frames while the selector
                        # remains mounted.  Do not classify that transient as
                        # the selector page; the preparation-specific branch
                        # below still requires the reviewed fleet root before
                        # any input.
                        event_campaign_selector_visible = False
                    else:
                        # A still-mounted selector can coexist beneath a partial
                        # or foreign preparation view.  Preparation resources
                        # must reach their strict typed proof below instead of
                        # being hidden as generic selector-page misses.
                        raise
            except SemanticTargetMissing:
                pass
        if event_campaign_selector_visible:
            # The event battle/story selector keeps the generic campaign root
            # mounted. EVENT_CHECK was already resolved above through the
            # complete event_campaign_page_state contract. Unrelated page
            # probes (including CAMPAIGN_CHECK) are known absent here.
            if name == "SWITCH_20241219_COMBAT":
                return self.oracle.exists("event/mode/story")
            if name == "SWITCH_20241219_STORY":
                return self.oracle.exists("event/mode/battle")
            if name in EVENT_CAMPAIGN_ASIDE_RESOURCES:
                return self.oracle.event_campaign_aside_selected(
                    EVENT_CAMPAIGN_ASIDE_RESOURCES[name]
                )
            if name not in (
                "SWITCH_20241219_COMBAT",
                "SWITCH_20241219_STORY",
                *EVENT_CAMPAIGN_ASIDE_RESOURCES.keys(),
            ):
                return False
        if (
            semantic_id is None
            and self._campaign_context is not None
            and name not in CAMPAIGN_VIRTUAL_RESOURCES
            and self._campaign_preparation_kind() is not None
        ):
            # An exact owned map/fleet preparation overlay makes Daemon's
            # unrelated legacy image probes known absences.  Resolve this
            # before probing independent pages such as Battle Pass: their
            # separately sampled observer trees can be transiently incoherent
            # while the campaign overlay is mounting.  Campaign virtual
            # resources still reach their strict typed branches below and
            # unknown input remains rejected by click().
            return False
        return UNHANDLED
