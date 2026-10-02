"""Research for the typed ALAS boundary."""

from __future__ import annotations

import re
import time
from typing import Callable, List, Optional, Tuple
from ...semantic_oracle import (
    ActionReceipt,
    ResearchDetailState,
    ResearchProjectState,
    ResearchProjectStatus,
    ResearchQueueState,
    SemanticGateClosed,
    SemanticOracleError,
    ShipyardState,
)
from .contracts import _ResearchFlowContext, _research_detail_costs
from .dispatch_result import UNHANDLED
from .resources import RESEARCH_CLICK_RESOURCES, RESEARCH_VIRTUAL_RESOURCES


class ResearchAdapterPorts:
    """Research ports on the shared adapter context."""

    def begin_research(self) -> None:
        self._package_gate()
        if self._login_flow.active or any(
            context is not None
            for context in (
                self._mission_context,
                self._mail_context,
                self._commission_context,
                self._research_context,
                self._dorm_context,
                self._supply_pack_context,
                self._minigame_context,
                self._build_context,
                self._campaign_context,
            )
        ):
            raise SemanticGateClosed("nested semantic ALAS flow is not allowed")
        self._research_context = _ResearchFlowContext(
            passive_transition_until=time.monotonic() + 20.0,
        )

    def end_research(self) -> None:
        self._research_context = None

    def _research_entry_completed(self) -> Optional[ActionReceipt]:
        """Acknowledge an actual entry after the destination replaces its source."""
        context = self._research_context
        receipt = context.navigation_receipts.get("research-menu/research") if context else None
        if receipt is None:
            return None
        if (
            self.oracle.enabled("research/page/back")
            and len(self.oracle.research_projects()) == 5
            and self.oracle.read_state().generation > receipt.generation
        ):
            return receipt
        return None

    def _known_research_surface_exists(self) -> bool:
        return any(
            self.oracle.exists(semantic_id)
            for semantic_id in (
                "reward/page/back",
                "main/tech",
                "research-menu/page/back",
                "research-menu/research",
                "research/page/back",
                "research/queue/enter",
                "research/detail/root",
            )
        )

    def _shipyard_page_visible(self) -> bool:
        """Read the optional shipyard probe without breaking narrow test ports."""

        probe = getattr(self.oracle, "shipyard_page_visible", None)
        return bool(probe()) if callable(probe) else False

    def research_projects(self) -> Tuple[ResearchProjectState, ...]:
        self._package_gate()
        if self._research_context is None:
            raise SemanticGateClosed("research projects used outside ALAS research flow")
        try:
            projects = self.oracle.research_projects()
        except SemanticGateClosed:
            if (
                self._research_context.last_projects is None
                or time.monotonic()
                - self._research_context.last_projects_observed_at
                > 5.0
            ):
                raise
            return self._research_context.last_projects
        self._research_context.last_projects = projects
        self._research_context.last_projects_observed_at = time.monotonic()
        return projects

    def research_projects_for_alas(
        self, project_factory: Callable[..., object]
    ) -> Tuple[object, ...]:
        """Convert one complete typed five-card snapshot into ALAS projects.

        The upstream ``ResearchProject`` remains the owner of project metadata
        and consumption flags.  This boundary only rejects incomplete typed
        snapshots and project codes which the pinned upstream cannot resolve.
        """

        states = self.research_projects()
        if len(states) != 5:
            raise SemanticGateClosed("research decision requires exactly five cards")
        if {state.slot for state in states} != set(range(1, 6)):
            raise SemanticGateClosed("research card slots are incomplete or ambiguous")
        if {state.unity_index for state in states} != set(range(1, 6)):
            raise SemanticGateClosed("research Unity card identities are ambiguous")

        projects = []
        for state in states:
            if (
                not isinstance(state.code, str)
                or not state.code.strip()
                or not isinstance(state.series, int)
                or state.series < 1
                or not isinstance(state.duration_seconds, int)
                or state.duration_seconds < 0
            ):
                raise SemanticGateClosed("research card decision input is malformed")
            project = project_factory(name=state.code, series=state.series)
            if getattr(project, "valid", None) is not True:
                raise SemanticGateClosed(
                    "research project is unknown to pinned ALAS: " + state.code
                )
            projects.append(project)
        return tuple(projects)

    def click_research_project_code(
        self, code: str, *, position: Optional[int] = None
    ) -> ActionReceipt:
        """Click the one current card selected by upstream's project code.

        Upstream makes the policy decision over its previously typed project
        objects.  The client can reorder the visible Unity children before the
        later ``ENTRANCE_n`` input, so preserve that decision by resolving the
        selected code against one fresh semantic card snapshot at input time.
        """

        self._package_gate()
        if self._research_context is None:
            raise SemanticGateClosed("research project selection used outside ALAS research flow")
        normalized = code.strip() if isinstance(code, str) else ""
        if not normalized:
            raise SemanticGateClosed("research project code is absent")
        # Input cannot reuse the five-second observation cache: re-resolve the
        # selected policy identity from a fresh live card snapshot.
        input_oracle = self._fresh_input_oracle()
        for attempt in range(2):
            try:
                projects = input_oracle.research_projects()
                break
            except SemanticGateClosed:
                if attempt:
                    raise
                time.sleep(0.1)
        if position is None:
            matches = tuple(
                project for project in projects if project.code == normalized
            )
            if len(matches) != 1:
                raise SemanticGateClosed(
                    "selected research project code is ambiguous: " + normalized
                )
            project = matches[0]
        else:
            if not isinstance(position, int) or isinstance(position, bool):
                raise SemanticGateClosed("selected research project position is invalid")
            if position < 0 or position >= len(projects):
                raise SemanticGateClosed("selected research project position is out of range")
            project = projects[position]
            if project.code != normalized:
                raise SemanticGateClosed(
                    "selected research project position no longer matches its code"
                )
        if project.status == ResearchProjectStatus.FINISHED:
            raise SemanticGateClosed("research policy cannot select a finished project")
        receipt = input_oracle.click_research_project(
            project.slot,
            expected_code=normalized,
        )
        context = self._research_context
        context.selected_slot = project.slot
        context.selected_code = project.code
        context.selected_status = project.status
        context.start_receipt = None
        context.start_confirm_receipt = None
        context.pending_resource_id = None
        context.pending_resource_required = None
        context.pending_resource_costs = ()
        context.queue_add_receipt = None
        context.queue_confirm_receipt = None
        context.queue_add_requires_start_grant = False
        return receipt

    def start_research_project_code(
        self, code: str, *, position: Optional[int] = None
    ) -> bool:
        """Start the upstream-selected current research card atomically.

        ALAS still chooses ``code`` through its own filter and resource-policy
        logic. Once that decision has been made, the selected-detail panel
        hides the card-list checker used by its pixel retry loop. Drive the
        typed card, start button, and exact resource-confirmation prompt as
        one semantic transition instead of letting that loop wait indefinitely.
        """

        self._package_gate()
        if self._research_context is None:
            raise SemanticGateClosed("research start used outside ALAS research flow")
        self.click_research_project_code(code, position=position)
        self.research_detail_stable()
        context = self._research_context
        detail = self.oracle.research_detail_state()
        if detail.code != context.selected_code:
            raise SemanticGateClosed("selected research project identity changed")
        # The original Research command also selects an already-running sixth
        # project when a queue slot becomes free, then sends it through the
        # ordinary queue-add branch. It is not a new start and must not open a
        # resource confirmation here.
        if detail.is_running:
            return True
        if not detail.can_start:
            self.oracle.click("research/detail/root")
            return False
        if not self._action_ledger.allowed("research.start"):
            raise SemanticGateClosed("research start requires a positive budget")

        detail_costs = _research_detail_costs(detail)
        expected_costs = tuple(
            (resource_id, required)
            for resource_id, _owned, required in detail_costs
        )
        context.pending_resource_costs = tuple(sorted(expected_costs))
        if expected_costs:
            context.pending_resource_id, context.pending_resource_required = (
                expected_costs[0]
            )
        else:
            context.pending_resource_id = None
            context.pending_resource_required = None
        if not expected_costs:
            # Resource-free projects have no confirmation modal.  The exact
            # typed Start control is the one budgeted mutation in this path.
            receipt = self._dispatch_mutation(
                "research.start",
                lambda: self.oracle.click("research/detail/start"),
            )
            context.start_receipt = receipt
            context.start_confirm_receipt = receipt
            context.last_queue_state = None
            context.last_projects = None
        else:
            start_receipt = self.oracle.click("research/detail/start")
            context.start_receipt = start_receipt
            context.start_confirm_receipt = None
            expected_cost = tuple(sorted(expected_costs))

            deadline = time.monotonic() + 8.0
            last_prompt_error: Optional[SemanticGateClosed] = None
            while time.monotonic() < deadline:
                try:
                    prompt_cost = self.oracle.research_start_prompt_costs()
                except SemanticGateClosed as exc:
                    # The message box mounts its Button and typed text in separate
                    # Unity updates. Keep the exact-cost gate, but retry this
                    # documented transient until the bounded start transition ends.
                    last_prompt_error = exc
                    time.sleep(0.25)
                    continue
                if prompt_cost == expected_cost:
                    receipt = self._confirm_research_start(expected_cost)
                    context.start_confirm_receipt = receipt
                    context.last_queue_state = None
                    context.last_projects = None
                    break
                time.sleep(0.25)
            else:
                raise SemanticGateClosed(
                    "research start confirmation did not show the selected exact cost"
                ) from last_prompt_error

        deadline = time.monotonic() + 8.0
        last_error: Optional[SemanticOracleError] = None
        while time.monotonic() < deadline:
            try:
                running = self.oracle.research_detail_state()
                if running.code == context.selected_code and running.is_running:
                    return True
            except SemanticOracleError as exc:
                last_error = exc
            time.sleep(0.25)
        raise SemanticGateClosed(
            "research did not enter running state after exact-cost confirmation"
        ) from last_error

    def _confirm_research_start(self, expected_costs: Tuple[Tuple[str, int], ...]) -> ActionReceipt:
        """Bind the complete cost match and input to the same fresh frame."""
        oracle = self._fresh_input_oracle()
        if not expected_costs or oracle.research_start_prompt_costs() != expected_costs:
            raise SemanticGateClosed("research costs changed before confirmation input")
        return self._dispatch_mutation(
            "research.start", lambda: oracle.click("research/start/confirm")
        )

    def validate_research_filter(self, filter_: object, value: str) -> None:
        """Fail closed on tokens that upstream's permissive parser would ignore."""

        if not isinstance(value, str):
            raise SemanticGateClosed("research filter must be text")
        normalized = re.sub(r"[ \t\r\n]", "", value)
        normalized = re.sub(r"[＞﹥›˃ᐳ❯]", ">", normalized)
        normalized = re.sub(r"[‐‑‒–—―−－﹣﹘⁃]", "-", normalized)
        tokens = normalized.split(">")
        regex = getattr(filter_, "regex", None)
        is_preset = getattr(filter_, "is_preset", None)
        if not hasattr(regex, "fullmatch") or not callable(is_preset):
            raise SemanticGateClosed("research filter contract is unavailable")
        invalid = tuple(
            token
            for token in tokens
            if not token
            or (not is_preset(token) and regex.fullmatch(token.lower()) is None)
        )
        if invalid:
            raise SemanticGateClosed(
                "research filter contains invalid token(s): " + ", ".join(invalid)
            )

    def shipyard_select_series(self, series: int) -> ActionReceipt:
        self._package_gate()
        if not 1 <= series <= 9:
            raise ValueError("shipyard series must be in [1, 9]")
        self.oracle.click("shipyard/series/open")
        deadline = time.monotonic() + 8.0
        target = "shipyard/series/{0}".format(series)
        while not self.oracle.enabled(target):
            if time.monotonic() >= deadline:
                raise SemanticGateClosed("shipyard series choices did not become actionable")
            time.sleep(0.25)
        receipt = self.oracle.click(target)
        deadline = time.monotonic() + 8.0
        while time.monotonic() < deadline:
            if self._shipyard_page_visible() and not self.oracle.exists(
                "shipyard/series/1"
            ):
                try:
                    if self.oracle.shipyard_series() == series:
                        return receipt
                except SemanticGateClosed:
                    pass
            time.sleep(0.25)
        raise SemanticGateClosed("shipyard series transition timed out")

    def shipyard_select_ship(self, index: int) -> ShipyardState:
        self._package_gate()
        for attempt in range(3):
            try:
                receipt = self.oracle.click_shipyard_ship(index)
                break
            except SemanticGateClosed as exc:
                # This exact failure is raised before any tap. Reacquire the
                # two endpoints; never retry a dispatched/ambiguous action.
                if str(exc) != "shipyard input snapshots are not coherent" or attempt == 2:
                    raise
                time.sleep(0.1)
        if not receipt.semantic_id.endswith('/already'):
            # Preserve original ShipyardUI's 1.5-second detail transition
            # delay: the checked toggle can precede the new title/DEV pane.
            time.sleep(1.5)
        deadline = time.monotonic() + 8.0
        last_error: Optional[SemanticOracleError] = None
        while time.monotonic() < deadline:
            try:
                return self.oracle.shipyard_state(index)
            except SemanticOracleError as exc:
                last_error = exc
                time.sleep(0.25)
        raise SemanticGateClosed("shipyard ship transition timed out") from last_error

    def shipyard_state(self, index: int) -> ShipyardState:
        self._package_gate()
        return self._frame_or_live_observation_oracle().shipyard_state(index)

    def research_detail_state(self) -> ResearchDetailState:
        self._package_gate()
        return self.oracle.research_detail_state()

    def research_detail_available(self) -> bool:
        self._package_gate()
        if self._research_context is None:
            raise SemanticGateClosed("research detail used outside ALAS research flow")
        try:
            detail = self.oracle.research_detail_state()
            return bool(
                detail.can_start
                and self._action_ledger.allowed("research.start")
                and self._research_context.start_receipt is None
            )
        except SemanticGateClosed:
            if self._active_flow_allows_passive_probe():
                return False
            raise

    def research_detail_is_running(self) -> bool:
        self._package_gate()
        if self._research_context is None:
            raise SemanticGateClosed("research detail used outside ALAS research flow")
        return self.oracle.enabled("research/detail/stop")

    def research_detail_can_queue(self) -> bool:
        self._package_gate()
        if self._research_context is None:
            raise SemanticGateClosed("research detail used outside ALAS research flow")
        return self.oracle.research_queue_add_available()

    def research_queue_state(self) -> ResearchQueueState:
        self._package_gate()
        if self._research_context is None:
            raise SemanticGateClosed("research queue used outside ALAS research flow")
        try:
            state = self.oracle.research_queue_state()
        except SemanticGateClosed:
            if (
                self._research_context.last_queue_state is None
                or time.monotonic()
                - self._research_context.last_queue_observed_at
                > 30.0
            ):
                raise
            return self._research_context.last_queue_state
        self._research_context.last_queue_state = state
        self._research_context.last_queue_observed_at = time.monotonic()
        return state

    def research_queue_empty_slots(self) -> int:
        return self.research_queue_state().empty_slots

    def research_queue_fill_slots(self) -> int:
        """Return the slots ALAS may fill under this run's mutation budget."""

        if self._research_context is None:
            raise SemanticGateClosed("research queue used outside ALAS research flow")
        if not self._action_ledger.allowed("research.start"):
            return 0
        if self.oracle.enabled("research/queue/enter"):
            # ALAS calls get_queue_slot() from its card page. The queue modal
            # is not open there, so use its current five typed status marks.
            return self.oracle.research_queue_indicator_empty_slots()
        return self.research_queue_empty_slots()

    def research_queue_remaining_seconds(self) -> int:
        return self.research_queue_state().first_remaining_seconds

    def research_series(self) -> List[int]:
        return [project.series for project in self.research_projects()]

    def research_statuses(self) -> List[str]:
        return [project.status.value for project in self.research_projects()]

    def research_detail_stable(self) -> None:
        """Require two identical typed detail snapshots after card selection."""

        self._package_gate()
        if self._research_context is None:
            raise SemanticGateClosed("research detail stability used outside ALAS research flow")
        deadline = time.monotonic() + 6.0
        previous: Optional[Tuple[object, ...]] = None
        last_error: Optional[SemanticGateClosed] = None
        while time.monotonic() < deadline:
            try:
                detail = self.oracle.research_detail_state()
                signature = (
                    detail.code,
                    detail.subtitle,
                    detail.duration_seconds,
                    detail.resource_id,
                    detail.resource_owned,
                    detail.resource_required,
                    _research_detail_costs(detail),
                    detail.requirement,
                    detail.can_start,
                    detail.can_queue,
                    detail.is_running,
                    detail.is_finished,
                )
                if signature == previous:
                    return
                previous = signature
                last_error = None
            except SemanticGateClosed as exc:
                last_error = exc
                previous = None
            time.sleep(0.25)
        raise SemanticGateClosed("research detail did not become stably typed") from last_error

    def research_page_stable(self) -> None:
        """Require two coherent identical typed research-card snapshots.

        Upstream uses a fixed image checker after leaving the queue.  In
        semantic mode the complete five-card projection is the equivalent
        observation: it must stay structurally identical across two fresh
        reads before ALAS continues its existing state machine.
        """

        self._package_gate()
        if self._research_context is None:
            raise SemanticGateClosed("research stability used outside ALAS research flow")
        deadline = time.monotonic() + 6.0
        previous: Optional[Tuple[Tuple[object, ...], ...]] = None
        last_error: Optional[SemanticGateClosed] = None
        while time.monotonic() < deadline:
            try:
                states = self.oracle.research_projects()
                if len(states) != 5 or {state.slot for state in states} != set(
                    range(1, 6)
                ):
                    raise SemanticGateClosed(
                        "research stability requires exactly five card slots"
                    )
                if {state.unity_index for state in states} != set(range(1, 6)):
                    raise SemanticGateClosed(
                        "research stability requires unique Unity card identities"
                    )
                signature = tuple(
                    sorted(
                        (
                            state.slot,
                            state.unity_index,
                            state.code,
                            state.series,
                            state.duration_seconds,
                            state.status.value,
                        )
                        for state in states
                    )
                )
                if signature == previous:
                    self._research_context.last_projects = states
                    self._research_context.last_projects_observed_at = time.monotonic()
                    return
                previous = signature
                last_error = None
            except SemanticGateClosed as exc:
                last_error = exc
                previous = None
            time.sleep(0.25)
        raise SemanticGateClosed("research page did not become stably typed") from last_error

    def research_finished_index(self) -> Optional[int]:
        finished = [
            project.slot - 1
            for project in self.research_projects()
            if project.status == ResearchProjectStatus.FINISHED
        ]
        if len(finished) > 1:
            raise SemanticGateClosed("multiple finished research projects are ambiguous")
        return finished[0] if finished else None

    def _appear_research(self, name):
        if name in RESEARCH_VIRTUAL_RESOURCES and self._research_context is not None:
            if name == "RESET_AVAILABLE":
                return self.oracle.research_reset_available()
            if name == "QUEUE_CHECK":
                try:
                    # The retained post-exit capacity is not page identity.
                    # ALAS must see the current queue before skipping entry.
                    self.oracle.research_queue_state()
                    return True
                except SemanticGateClosed:
                    return False
            if name == "RESEARCH_GOTO_QUEUE":
                return self.oracle.enabled("research/queue/enter")
            if name in ("DETAIL_NEXT", "RESEARCH_COST_CHECKER"):
                try:
                    self.oracle.research_detail_state()
                    return True
                except SemanticGateClosed:
                    return False
            if name == "RESEARCH_START":
                try:
                    detail = self.oracle.research_detail_state()
                except SemanticGateClosed:
                    return False
                return (
                    detail.can_start
                    and self._action_ledger.allowed("research.start")
                    and self._research_context.start_receipt is None
                )
            if name in ("POPUP_CANCEL", "POPUP_CONFIRM"):
                context = self._research_context
                if context.queue_add_receipt is not None:
                    target = (
                        "research/queue/cancel"
                        if name == "POPUP_CANCEL"
                        else "research/queue/confirm"
                    )
                    return bool(
                        context.queue_confirm_receipt is None
                        and self.oracle.enabled(target)
                    )
                cost = self.oracle.research_start_prompt_costs()
                return bool(
                    context.start_receipt is not None
                    and context.start_confirm_receipt is None
                    and self._action_ledger.allowed("research.start")
                    and cost is not None
                    and cost == context.pending_resource_costs
                )
            if name == "RESEARCH_UNAVAILABLE":
                try:
                    self.oracle.research_detail_state()
                except SemanticGateClosed:
                    return False
                return not self.research_detail_available()
            if name == "RESEARCH_STOP":
                return self.research_detail_is_running()
            if name == "RESEARCH_QUEUE_ADD":
                return self.research_detail_can_queue()
            if name == "RESEARCH_DETAIL_QUIT":
                return self.oracle.enabled("research/detail/root")
            if name == "QUEUE_CLAIM_REWARD":
                try:
                    queue = self.research_queue_state()
                except SemanticGateClosed:
                    return False
                return queue.reward_claimable and self._action_ledger.allowed(
                    "research.reward"
                )
            if name in ("GET_ITEMS_1", "GET_ITEMS_2", "GET_ITEMS_3", "GET_ITEMS_RESEARCH_SAVE"):
                return bool(
                    self._research_context.reward_receipts
                    and self._award_close_target() is not None
                )
            if name == "BACK_ARROW":
                return self.oracle.enabled("research/page/back")
        research_entrance = re.fullmatch(r"ENTRANCE_([1-5])", name)
        if research_entrance is not None and self._research_context is not None:
            slot = int(research_entrance.group(1))
            try:
                return any(
                    project.slot == slot and project.button.actionable
                    for project in self.oracle.research_projects()
                )
            except SemanticGateClosed:
                return False
        return UNHANDLED

    def _click_research(self, name):
        if self._research_context is not None and name in RESEARCH_CLICK_RESOURCES:
            context = self._research_context
            if name in ('POPUP_CONFIRM', 'POPUP_CANCEL'):
                prompt_kind = self.oracle.observation_prompt_kind()
                if ((prompt_kind == 'opsi-exit'
                        and self.oracle.operation_siren_exit_prompt_visible())
                        or (name == 'POPUP_CONFIRM' and prompt_kind is None
                            and self._operation_siren_exit_receipt is not None
                            and time.monotonic() <= self._operation_siren_entry_transition_until)):
                    # The shared OS port also owns repeated old confirmation
                    # probes after exit; it proves the destination and returns
                    # its existing receipt without submitting another input.
                    return UNHANDLED
            if name == "RESEARCH_GOTO_QUEUE":
                target = "research/queue/enter"
                cached = context.navigation_receipts.get(target)
                if (
                    cached is not None
                    and time.monotonic() <= context.passive_transition_until
                ):
                    self.oracle.research_queue_state()
                    return cached
                deadline = time.monotonic() + 6.0
                while True:
                    if self._input_frame_refresher is not None:
                        self._input_frame_refresher()
                    try:
                        receipt = self._record_mission_transition(
                            self.oracle.click(target)
                        )
                        break
                    except SemanticGateClosed as exc:
                        if (
                            str(exc) != "semantic target is not actionable"
                            or time.monotonic() >= deadline
                        ):
                            raise
                        time.sleep(0.25)
                context.navigation_receipts[target] = receipt
                # A new entry ends the previous exit transaction. The shared
                # transition deadline must not revive its cached BACK_ARROW.
                context.navigation_receipts.pop("research/page/back", None)
                # ALAS may poll again before the queue panel has mounted.
                # Wait for its exact typed identity here so a second click
                # cannot close the panel or repeat an input without progress.
                self.oracle.research_queue_state()
                return receipt
            if name == "RESEARCH_DETAIL_QUIT":
                return self.oracle.click("research/detail/root")
            if name == "RESEARCH_START":
                detail = self.oracle.research_detail_state()
                if (
                    not self._action_ledger.allowed("research.start")
                    or context.start_receipt is not None
                    or not detail.can_start
                ):
                    raise SemanticGateClosed(
                        "research start requires sufficient resources and a positive budget"
                    )
                if context.selected_code is not None and detail.code != context.selected_code:
                    raise SemanticGateClosed("selected research project identity changed")
                detail_costs = _research_detail_costs(detail)
                expected_costs = tuple(
                    (resource_id, required)
                    for resource_id, _owned, required in detail_costs
                )
                receipt = self.oracle.click("research/detail/start")
                context.start_receipt = receipt
                context.start_confirm_receipt = None
                context.pending_resource_costs = tuple(sorted(expected_costs))
                if expected_costs:
                    context.pending_resource_id, context.pending_resource_required = (
                        expected_costs[0]
                    )
                else:
                    context.pending_resource_id = None
                    context.pending_resource_required = None
                return receipt
            if name == "POPUP_CONFIRM":
                if context.queue_add_receipt is not None:
                    if context.queue_confirm_receipt is not None:
                        return context.queue_confirm_receipt
                    if (
                        context.queue_add_requires_start_grant
                        and not self._action_ledger.allowed("research.start")
                    ):
                        raise SemanticGateClosed(
                            "research queue confirmation requires a positive budget"
                        )
                    if context.queue_add_requires_start_grant:
                        receipt = self._dispatch_mutation(
                            "research.start",
                            lambda: self.oracle.click("research/queue/confirm"),
                        )
                    else:
                        receipt = self.oracle.click("research/queue/confirm")
                    context.queue_confirm_receipt = receipt
                    context.last_queue_state = None
                    context.last_projects = None
                    return receipt
                expected = context.pending_resource_costs
                if (
                    context.start_receipt is None
                    or context.start_confirm_receipt is not None
                    or not self._action_ledger.allowed("research.start")
                    or self.oracle.research_start_prompt_costs() != expected
                ):
                    raise SemanticGateClosed(
                        "research start confirmation does not match the budgeted project"
                    )
                receipt = self._confirm_research_start(expected)
                context.start_confirm_receipt = receipt
                context.last_queue_state = None
                context.last_projects = None
                return receipt
            if name == "RESEARCH_QUEUE_ADD":
                if (
                    context.queue_add_receipt is not None
                    and time.monotonic() <= context.passive_transition_until
                ):
                    return context.queue_add_receipt
                confirmed_start = context.start_confirm_receipt is not None
                existing_running = (
                    context.selected_status in (
                        ResearchProjectStatus.RUNNING, ResearchProjectStatus.WAITING
                    )
                    and self._action_ledger.allowed("research.start")
                    and self.research_detail_is_running()
                    and self.research_detail_can_queue()
                )
                if not confirmed_start and not existing_running:
                    raise SemanticGateClosed(
                        "research queue add requires a confirmed start or one budgeted running project"
                    )
                receipt = self.oracle.click_research_queue_add()
                context.queue_add_receipt = receipt
                context.queue_confirm_receipt = None
                context.queue_add_requires_start_grant = existing_running
                context.last_queue_state = None
                context.last_projects = None
                return self._record_mission_transition(receipt)
            if name == "RESEARCH_STOP":
                raise SemanticGateClosed("semantic research cancellation is not enabled")
            if name == "QUEUE_CLAIM_REWARD":
                queue = self.oracle.research_queue_state()
                if not queue.reward_claimable or not self._action_ledger.allowed(
                    "research.reward"
                ):
                    raise SemanticGateClosed("research reward requires a positive budget")
                receipt = self._dispatch_mutation(
                    "research.reward",
                    lambda: self.oracle.click("research/queue/claim"),
                )
                context.reward_receipts.append(receipt)
                context.last_queue_state = None
                context.last_projects = None
                return receipt
            if name in (
                "GET_ITEMS_1",
                "GET_ITEMS_2",
                "GET_ITEMS_3",
                "GET_ITEMS_RESEARCH_SAVE",
            ):
                if not context.reward_receipts:
                    raise SemanticGateClosed(
                        "research reward popup requires a budgeted queue claim"
                    )
                target = self._award_close_target()
                if target is None:
                    if (context.popup_close_receipts
                            and not self.oracle.observation_target_present('reward/award-info/close')
                            and not self.oracle.observation_target_present('reward/award-info1/close')):
                        previous = context.popup_close_receipts[-1]
                        self.oracle.research_queue_state()
                        if self.oracle.read_state().generation > previous.generation:
                            return previous
                    raise SemanticGateClosed("reviewed research reward popup is absent")
                receipt = self.oracle.click(target)
                context.popup_close_receipts.append(receipt)
                return receipt
            if name == "BACK_ARROW":
                cached = context.navigation_receipts.get("research/page/back")
                if (
                    cached is not None
                    and time.monotonic() <= context.passive_transition_until
                ):
                    return cached
                # ALAS asks for queue capacity immediately after leaving the
                # queue page. Preserve the last complete typed snapshot so the
                # post-exit query neither guesses nor falls back to pixels.
                try:
                    queue_state = self.oracle.research_queue_state()
                except SemanticGateClosed:
                    pass
                else:
                    context.last_queue_state = queue_state
                    context.last_queue_observed_at = time.monotonic()
                receipt = self._record_mission_transition(
                    self.oracle.click("research/page/back")
                )
                context.navigation_receipts["research/page/back"] = receipt
                # ALAS may return to the queue again within the same task.
                # Duplicate suppression belongs only to this navigation leg.
                context.navigation_receipts.pop("research/queue/enter", None)
                return receipt
        return UNHANDLED
