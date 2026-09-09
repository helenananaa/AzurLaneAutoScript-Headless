"""Campaign map for the typed ALAS boundary."""

from __future__ import annotations

import math
import re
import time
from dataclasses import replace
from numbers import Real
from typing import Any, Optional, Sequence, Tuple
from ...alas_combat_admission import (
    AlasCampaignCombatAdmission,
    AlasCampaignCombatProof,
    prepare_alas_campaign_combat_admission,
    prove_alas_campaign_combat_transition,
)
from ...alas_decision_preview import AlasCampaignDecisionPreview
from ...semantic_oracle import (
    ActionReceipt,
    CampaignMapState,
    CampaignMapViewportSwipeIntent,
    CampaignMapViewportSwipeProof,
    SemanticGateClosed,
    SemanticTargetMissing,
)
from .contracts import (
    CampaignCameraPositioningAdmission,
    CampaignMapTargetRecheckProof,
    _CampaignFlowContext,
)


class CampaignMapAdapterPorts:
    """Campaign map ports on the shared adapter context."""

    def campaign_map_state(
        self,
        *,
        columns: int,
        rows: int,
        land_cells: Sequence[Tuple[int, int]],
        expected_fleet_count: int,
    ) -> CampaignMapState:
        """Supply one read-only typed map input to the ALAS campaign flow."""

        self._package_gate()
        context = self._require_campaign_context()
        hard_event_stage = re.fullmatch(r"[cd][1-3]", context.stage_code)
        if (
            context.mode == "hard"
            and context.stage_code not in ("11-4", "12-1")
            and hard_event_stage is None
        ):
            raise SemanticGateClosed(
                "hard campaign map model is qualified only for reviewed main or "
                "reviewed shared event C/D stages"
            )
        if context.mode not in ("normal", "hard"):
            raise SemanticGateClosed(
                "campaign map model mode is not reviewed"
            )
        state = self.oracle.campaign_map_state(
            context.stage_code,
            columns=columns,
            rows=rows,
            land_cells=land_cells,
            expected_fleet_count=expected_fleet_count,
        )

        context.map_state = state
        context.map_columns = columns
        context.map_rows = rows
        context.map_land_cells = tuple(tuple(item) for item in land_cells)
        context.map_expected_fleet_count = expected_fleet_count
        return state

    def _refresh_campaign_map_state(self) -> CampaignMapState:
        context = self._require_campaign_context()
        if (
            context.map_columns is None
            or context.map_rows is None
            or context.map_expected_fleet_count is None
        ):
            raise SemanticGateClosed(
                "campaign map dimensions are unavailable for fleet switching"
            )
        state = self.oracle.campaign_map_state(
            context.stage_code,
            columns=context.map_columns,
            rows=context.map_rows,
            land_cells=context.map_land_cells,
            expected_fleet_count=context.map_expected_fleet_count,
        )
        context.map_state = state
        return state

    def authorize_campaign_camera_positioning(
        self, target_node: str, state: CampaignMapState
    ) -> CampaignCameraPositioningAdmission:
        """Arm one qualification-only camera gesture toward an empty cell."""

        self._package_gate()
        context = self._require_campaign_context()
        camera_grants = self._action_ledger.remaining(
            "campaign.camera_positioning"
        )
        if (
            not self._action_ledger.allowed("campaign.camera_positioning")
            or not 1 <= camera_grants <= 2
        ):
            raise SemanticGateClosed(
                "campaign camera positioning requires one or two budget units"
            )
        if (
            context.map_state is not state
            or context.camera_positioning_admission is not None
            or context.camera_positioning_proofs
            or context.camera_positioning_completed
            or context.viewport_swipe_intent is not None
            or context.combat_admission is not None
            or context.combat_receipt is not None
        ):
            raise SemanticGateClosed(
                "campaign camera positioning is not available"
            )
        cells = tuple(cell for cell in state.cells if cell.node == target_node)
        occupied = (
            set(state.land_nodes)
            | {item.node for item in state.fleets}
            | {item.node for item in state.enemies}
            | {item.node for item in state.pickups}
        )
        if len(cells) != 1 or target_node in occupied:
            raise SemanticGateClosed(
                "campaign camera positioning target is not one empty sea cell"
            )
        target = self.oracle.campaign_map_cell_viewport_target(
            state, target_node
        )
        cell = cells[0]
        if (
            target.path != cell.button_path
            or target.point != cell.point
            or target.bounds != cell.bounds
        ):
            raise SemanticGateClosed(
                "campaign camera positioning target changed during preflight"
            )
        assert target.point is not None and target.bounds is not None
        admission = CampaignCameraPositioningAdmission(
            target_node=target_node,
            generation=state.generation,
            map_signature=state.signature,
            path=target.path,
            point=target.point,
            bounds=target.bounds,
        )
        context.camera_positioning_admission = admission
        return admission

    def authorize_campaign_combat(
        self,
        decision: AlasCampaignDecisionPreview,
        state: CampaignMapState,
    ) -> Optional[AlasCampaignCombatAdmission]:
        """Prepare one exact combat grid input without consuming its budget."""

        self._package_gate()
        context = self._require_campaign_context()
        if not self._action_ledger.allowed("campaign.grid_click"):
            return None
        has_submarine = (context.declared_submarine_fleet or
            (context.requested_fleets and context.requested_fleets[2]) or getattr(state, 'submarine', None) is not None)
        prepared_submarine = ((context.declared_submarine_fleet or
                               (context.requested_fleets and context.requested_fleets[2]))
                              and getattr(state, 'submarine', None) is not None)
        if has_submarine and not prepared_submarine:
            raise SemanticGateClosed('manual submarine battle requires enabled configuration and an observed submarine')
        if (
            context.combat_admission is not None
            or context.combat_route_receipts
            or context.combat_receipt is not None
            or context.combat_proof is not None
        ):
            raise SemanticGateClosed("campaign combat admission is single-use")
        if context.map_state is not state:
            raise SemanticGateClosed("campaign combat map state is not current")
        admission = prepare_alas_campaign_combat_admission(
            decision,
            state,
            input_generation=state.generation,
        )
        context.submarine_planned_destination = decision.submarine_destination_node
        if self._action_ledger.remaining("campaign.grid_click") < len(
            admission.input_nodes
        ):
            return None
        targets = tuple(
            self.oracle.campaign_map_cell_viewport_target(state, node)
            for node in admission.input_nodes
        )
        # Reserve at most one ALAS-owned viewport movement for every explicit
        # goto input.  ALAS may skip a reservation when its fresh View already
        # considers that waypoint in sight.
        viewport_authorized = bool(
            self._action_ledger.allowed("campaign.viewport_swipe")
            and self._action_ledger.remaining("campaign.viewport_swipe")
            >= len(admission.input_nodes)
        )
        if any(target.raycast_top is not True for target in targets) and not viewport_authorized:
            raise SemanticGateClosed(
                "campaign combat covered input requires viewport swipe budget"
            )
        target = targets[-1]
        if (
            target.path != admission.cell_path
            or target.point != admission.point
            or target.bounds != admission.bounds
        ):
            raise SemanticGateClosed("campaign combat target changed during preflight")
        context.combat_admission = admission
        context.viewport_swipe_required = (
            targets[0].raycast_top is not True
        )
        return admission

    def complete_campaign_combat_round(
        self,
        battle_count_after: int,
    ) -> Optional[AlasCampaignCombatProof]:
        """Close the previous ALAS battle before admitting its next decision."""

        context = self._require_campaign_context()
        if context.combat_receipt is None:
            if context.combat_admission is not None:
                raise SemanticGateClosed(
                    "previous campaign combat admission was not committed"
                )
            return None
        proof = self.confirm_campaign_combat(battle_count_after)
        context.combat_admission = None
        context.combat_route_receipts.clear()
        context.viewport_swipe_required = False
        context.viewport_swipe_intent = None
        context.viewport_swipe_proof = None
        context.camera_positioning_admission = None
        context.camera_positioning_proofs.clear()
        context.camera_positioning_completed = False
        context.target_recheck_proof = None
        context.combat_receipt = None
        context.combat_proof = None
        return proof

    @staticmethod
    def _campaign_swipe_pair(value: Any, label: str) -> Tuple[float, float]:
        try:
            pair = tuple(value)
        except TypeError as exc:
            raise SemanticGateClosed(label + " is malformed") from exc
        if len(pair) != 2 or any(
            isinstance(item, bool)
            or not isinstance(item, (int, float))
            or not math.isfinite(float(item))
            for item in pair
        ):
            raise SemanticGateClosed(label + " is malformed")
        return float(pair[0]), float(pair[1])

    @staticmethod
    def _campaign_swipe_box(
        value: Any, label: str
    ) -> Tuple[float, float, float, float]:
        try:
            area = tuple(value)
        except TypeError as exc:
            raise SemanticGateClosed(label + " is malformed") from exc
        if len(area) != 4 or any(
            isinstance(item, bool)
            or not isinstance(item, Real)
            or not math.isfinite(float(item))
            for item in area
        ):
            raise SemanticGateClosed(label + " is malformed")
        result = tuple(float(item) for item in area)
        if result[0] >= result[2] or result[1] >= result[3]:
            raise SemanticGateClosed(label + " is empty")
        return result

    @classmethod
    def _campaign_swipe_areas(
        cls, value: Any, label: str
    ) -> Tuple[Tuple[float, float, float, float], ...]:
        if value is None:
            return ()
        try:
            areas = tuple(value)
        except TypeError as exc:
            raise SemanticGateClosed(label + " is malformed") from exc
        if len(areas) > 128:
            raise SemanticGateClosed(label + " is too large")
        return tuple(cls._campaign_swipe_box(area, label) for area in areas)

    def begin_campaign_map_swipe_vector(
        self,
        vector: Any,
        *,
        box: Any,
        random_range: Any,
        padding: Any,
        duration: Any,
        whitelist_area: Any,
        blacklist_area: Any,
        name: Any,
        distance_check: Any,
    ) -> CampaignMapViewportSwipeIntent:
        """Authorize ALAS's complete map-swipe selection, but no raw input."""

        self._package_gate()
        context = self._require_campaign_context()
        self._rebase_campaign_partial_route_if_proven(context)
        combat_ready = (
            self._action_ledger.allowed("campaign.viewport_swipe")
            and self._action_ledger.remaining("campaign.viewport_swipe") >= 1
            and context.combat_admission is not None
            and len(context.combat_route_receipts)
            < len(context.combat_admission.input_nodes)
            and context.camera_positioning_admission is None
            and context.combat_receipt is None
        )
        positioning_ready = (
            self._action_ledger.allowed("campaign.camera_positioning")
            and 1
            <= self._action_ledger.remaining("campaign.camera_positioning")
            <= 2
            and context.camera_positioning_admission is not None
            and context.combat_admission is None
            and not context.camera_positioning_completed
            and context.combat_receipt is None
        )
        post_combat_ready = (
            self._action_ledger.allowed("campaign.viewport_swipe")
            and self._action_ledger.remaining("campaign.viewport_swipe") >= 1
            and context.combat_admission is not None
            and context.combat_receipt is not None
            and len(context.combat_route_receipts)
            == len(context.combat_admission.input_nodes)
            and context.camera_positioning_admission is None
            and context.map_state is not None
            and self._campaign_post_combat_state_proven(context, context.map_state)
        )
        retry_ready = (
            self._action_ledger.allowed("campaign.viewport_swipe")
            and self._action_ledger.remaining("campaign.viewport_swipe") >= 1
            and self._action_ledger.allowed("campaign.grid_click")
            and self._action_ledger.remaining("campaign.grid_click") >= 1
            and context.combat_admission is not None
            and context.combat_receipt is not None
            and len(context.combat_route_receipts)
            == len(context.combat_admission.input_nodes)
            and context.combat_input_retry_count == 0
            and context.camera_positioning_admission is None
            and context.map_state is not None
            and self._campaign_combat_input_retry_state_proven(
                context, context.map_state
            )
        )
        if (
            sum((combat_ready, positioning_ready, post_combat_ready, retry_ready))
            != 1
            or context.map_state is None
            or context.viewport_swipe_intent is not None
        ):
            raise SemanticGateClosed("campaign map viewport swipe is not authorized")
        if not isinstance(name, str):
            raise SemanticGateClosed("campaign map viewport swipe name is malformed")
        match = re.fullmatch(r"MAP_SWIPE_(-?[0-9]+)_(-?[0-9]+)", name)
        if match is None:
            raise SemanticGateClosed("campaign map viewport swipe name is not canonical")
        grid_vector = tuple(int(item) for item in match.groups())
        if (
            abs(grid_vector[0]) > 4
            or abs(grid_vector[1]) > 3
            or grid_vector == (0, 0)
        ):
            raise SemanticGateClosed("campaign map viewport grid vector is outside ALAS limits")
        pixel_vector = self._campaign_swipe_pair(
            vector, "campaign map viewport pixel vector"
        )
        if not 10.0 <= math.hypot(*pixel_vector) <= 1200.0:
            raise SemanticGateClosed("campaign map viewport pixel vector is outside limits")
        for grid, pixel in zip(grid_vector, pixel_vector):
            # map_swipe() adds ALAS's fractional center correction before
            # `_map_swipe()` rounds the semantic name.  A rounded zero axis may
            # therefore retain less than half a calibrated grid of pixels.
            if (grid == 0 and abs(pixel) > 120.0) or (
                grid != 0 and grid * pixel >= 0.0
            ):
                raise SemanticGateClosed(
                    "campaign map viewport pixel vector disagrees with ALAS"
                )
        exact_box = self._campaign_swipe_box(box, "campaign map viewport box")
        if exact_box != (123.0, 159.0, 1175.0, 628.0):
            raise SemanticGateClosed("campaign map viewport box changed")
        try:
            exact_random_values = tuple(random_range)
        except TypeError as exc:
            raise SemanticGateClosed(
                "campaign map viewport random range is malformed"
            ) from exc
        if len(exact_random_values) != 4 or any(
            isinstance(item, bool)
            or not isinstance(item, (int, float))
            or not math.isfinite(float(item))
            for item in exact_random_values
        ):
            raise SemanticGateClosed(
                "campaign map viewport random range is malformed"
            )
        exact_random = tuple(float(item) for item in exact_random_values)
        if exact_random != (0.0, 0.0, 0.0, 0.0):
            raise SemanticGateClosed("campaign map viewport random range changed")
        if isinstance(padding, bool) or not isinstance(padding, int) or padding != 15:
            raise SemanticGateClosed("campaign map viewport padding changed")
        duration_range = self._campaign_swipe_pair(
            duration, "campaign map viewport duration"
        )
        if duration_range != (0.1, 0.2):
            raise SemanticGateClosed("campaign map viewport duration changed")
        if distance_check is not True:
            raise SemanticGateClosed("campaign map viewport distance check is disabled")
        intent = CampaignMapViewportSwipeIntent(
            name=name,
            grid_vector=grid_vector,
            pixel_vector=pixel_vector,
            box=tuple(int(item) for item in exact_box),
            random_range=tuple(int(item) for item in exact_random),
            padding=padding,
            duration_range=duration_range,
            whitelist_areas=self._campaign_swipe_areas(
                whitelist_area, "campaign map viewport whitelist"
            ),
            blacklist_areas=self._campaign_swipe_areas(
                blacklist_area, "campaign map viewport blacklist"
            ),
            distance_check=True,
        )
        # ALAS full_scan() may traverse two different clamped axes while it
        # reconciles newly spawned enemies after a battle.  Every gesture is
        # still independently bound to the canonical source vector, exact
        # endpoints, a proven post-combat map and the finite viewport ledger;
        # do not add an artificial same-axis pair restriction here.
        context.viewport_swipe_intent = intent
        return intent

    def _rebase_campaign_partial_route_if_proven(
        self, context: _CampaignFlowContext
    ) -> None:
        """Re-arm the same target after Unity stops at a route waypoint.

        On hard maps a single destination tap may legally move only part of
        the already-admitted route.  Re-arm no input unless the complete map
        identity is unchanged, ammunition is unchanged, and the same fleet is
        observed at one strict interior node of that route.
        """

        admission = context.combat_admission
        state = context.map_state
        if (
            admission is None
            or state is None
            or context.combat_receipt is None
            or len(context.combat_route_receipts) != len(admission.input_nodes)
            or self._campaign_post_combat_state_proven(context, state)
        ):
            return
        self._validate_campaign_combat_route_state(
            context, state, for_next_input=False
        )
        fleets = tuple(
            fleet for fleet in state.fleets if fleet.marker == admission.fleet_marker
        )
        if len(fleets) != 1:
            raise SemanticGateClosed("campaign partial route fleet is ambiguous")
        current_node = fleets[0].node
        if current_node not in admission.route_nodes[1:-1]:
            return
        route_index = admission.route_nodes.index(current_node)
        target = next(
            (cell for cell in state.cells if cell.node == admission.target_node),
            None,
        )
        if target is None:
            raise SemanticGateClosed("campaign partial route target disappeared")
        context.combat_admission = replace(
            admission,
            generation=state.generation,
            input_generation=state.generation,
            origin_node=current_node,
            route_nodes=admission.route_nodes[route_index:],
            input_nodes=(admission.target_node,),
            cell_path=target.button_path,
            point=target.point,
            bounds=target.bounds,
            map_signature=state.signature,
        )
        context.combat_route_receipts.clear()
        context.combat_receipt = None
        context.viewport_swipe_proof = None
        context.target_recheck_proof = None
        context.viewport_swipe_required = False

    def recover_campaign_map_network_reconnect(self) -> bool:
        """Dismiss one exact NetworkDown prompt before ALAS moves the camera.

        A reconnect dialog can mount after ALAS has admitted a route but before
        its camera swipe.  Keep route and camera ownership with ALAS, while
        recovering only the already-reviewed, exact reconnect prompt and
        proving that the same logical map returned before allowing the caller
        to retry its swipe.
        """

        self._package_gate()
        context = self._require_campaign_context()
        if context.map_state is None:
            raise SemanticGateClosed("campaign map state is unavailable")
        if context.viewport_swipe_intent is not None:
            raise SemanticGateClosed(
                "campaign map reconnect cannot interrupt an armed swipe"
            )
        target = "overlay/network-reconnect/confirm"
        if not self.oracle.enabled(target):
            return False

        previous = context.map_state
        self.oracle.click(target)
        context.passive_transition_until = time.monotonic() + 20.0
        deadline = time.monotonic() + 20.0
        while True:
            if time.monotonic() >= deadline:
                raise SemanticGateClosed(
                    "campaign map reconnect did not return to the map"
                )
            if self.oracle.enabled(target):
                time.sleep(0.2)
                continue
            try:
                refreshed = self.oracle.campaign_map_state(
                    context.stage_code,
                    columns=context.map_columns,
                    rows=context.map_rows,
                    land_cells=context.map_land_cells,
                    expected_fleet_count=context.map_expected_fleet_count,
                )
            except (SemanticGateClosed, SemanticTargetMissing):
                time.sleep(0.2)
                continue
            if refreshed.signature != previous.signature:
                raise SemanticGateClosed(
                    "campaign map changed while recovering network reconnect"
                )
            context.map_state = refreshed
            return True

    def end_campaign_map_swipe_vector(
        self, intent: CampaignMapViewportSwipeIntent
    ) -> None:
        context = self._require_campaign_context()
        if context.viewport_swipe_intent is not intent:
            raise SemanticGateClosed("campaign map viewport swipe token changed")
        context.viewport_swipe_intent = None

    @staticmethod
    def _campaign_point_in_area(
        point: Tuple[int, int], area: Tuple[float, float, float, float]
    ) -> bool:
        return area[0] <= point[0] <= area[2] and area[1] <= point[1] <= area[3]

    @staticmethod
    def _campaign_swipe_endpoint_area(
        intent: CampaignMapViewportSwipeIntent,
    ) -> Tuple[float, float, float, float]:
        """Reproduce ALAS's padded end-point domain before random selection."""

        half = tuple(int(round(value / 2.0)) for value in intent.pixel_vector)
        left, top, right, bottom = intent.box
        pad_x = abs(half[0]) + intent.padding
        pad_y = abs(half[1]) + intent.padding
        return (
            left + pad_x + half[0],
            top + pad_y + half[1],
            right - pad_x + half[0],
            bottom - pad_y + half[1],
        )

    def campaign_map_viewport_swipe_committed(self) -> bool:
        context = self._require_campaign_context()
        return context.viewport_swipe_proof is not None

    def campaign_map_viewport_swipe_proof(
        self,
    ) -> CampaignMapViewportSwipeProof:
        context = self._require_campaign_context()
        proof = context.viewport_swipe_proof
        if proof is None:
            raise SemanticGateClosed("campaign map viewport swipe is not proven")
        return proof

    def campaign_post_combat_arrived(self, location: Any) -> bool:
        """Prove ALAS's just-fought fleet occupies its destination grid."""

        self._package_gate()
        context = self._require_campaign_context()
        admission = context.combat_admission
        if (
            admission is None
            or context.combat_receipt is None
            or context.map_columns is None
            or context.map_rows is None
            or context.map_expected_fleet_count is None
        ):
            raise SemanticGateClosed("campaign post-combat arrival is not authorized")
        try:
            exact_location = tuple(int(value) for value in location)
        except (TypeError, ValueError) as exc:
            raise SemanticGateClosed("campaign post-combat location is malformed") from exc
        if len(exact_location) != 2:
            raise SemanticGateClosed("campaign post-combat location is malformed")
        node = self._campaign_node(exact_location)
        if node != admission.target_node:
            raise SemanticGateClosed("campaign post-combat destination changed")
        state = self.oracle.campaign_map_state(
            context.stage_code,
            columns=context.map_columns,
            rows=context.map_rows,
            land_cells=context.map_land_cells,
            expected_fleet_count=context.map_expected_fleet_count,
        )
        prove_alas_campaign_combat_transition(
            admission,
            state,
            battle_count_after=admission.battle_count + 1,
            input_path=context.combat_receipt.path,
        )
        fleets = tuple(
            fleet
            for fleet in state.fleets
            if fleet.marker == admission.fleet_marker and fleet.node == node
        )
        if len(fleets) != 1:
            raise SemanticGateClosed("campaign post-combat fleet did not arrive")
        context.map_state = state
        return True

    def campaign_camera_positioning_committed(self) -> bool:
        context = self._require_campaign_context()
        return context.camera_positioning_completed

    def complete_campaign_camera_positioning(
        self, state: CampaignMapState
    ) -> Tuple[CampaignMapViewportSwipeProof, ...]:
        """Close the setup lease only after ALAS observes its exact target."""

        self._package_gate()
        context = self._require_campaign_context()
        admission = context.camera_positioning_admission
        if (
            admission is None
            or context.camera_positioning_completed
            or context.map_state is not state
            or not 1 <= len(context.camera_positioning_proofs) <= 2
            or state.signature != admission.map_signature
        ):
            raise SemanticGateClosed(
                "campaign camera positioning cannot be completed"
            )
        target = self.oracle.campaign_map_cell_input(
            state, admission.target_node
        )
        if target.path != admission.path:
            raise SemanticGateClosed(
                "campaign camera positioning completion changed target"
            )
        context.camera_positioning_completed = True
        return tuple(context.camera_positioning_proofs)

    def campaign_camera_positioning_proof(
        self,
    ) -> CampaignMapViewportSwipeProof:
        context = self._require_campaign_context()
        if not context.camera_positioning_completed:
            raise SemanticGateClosed(
                "campaign camera positioning is not proven"
            )
        return context.camera_positioning_proofs[-1]

    def campaign_camera_positioning_proofs(
        self,
    ) -> Tuple[CampaignMapViewportSwipeProof, ...]:
        context = self._require_campaign_context()
        if not context.camera_positioning_completed:
            raise SemanticGateClosed(
                "campaign camera positioning is not proven"
            )
        return tuple(context.camera_positioning_proofs)

    def campaign_camera_state(self) -> CampaignMapState:
        """Return one fresh map observation to ALAS's original Camera.update."""

        self._package_gate()
        context = self._require_campaign_context()
        if (
            context.map_columns is None
            or context.map_rows is None
            or context.map_expected_fleet_count is None
            or context.map_state is None
        ):
            raise SemanticGateClosed("campaign camera map topology is incomplete")
        state = self.oracle.campaign_map_state(
            context.stage_code,
            columns=context.map_columns,
            rows=context.map_rows,
            land_cells=context.map_land_cells,
            expected_fleet_count=context.map_expected_fleet_count,
            **({'allow_deployment': True} if context.submarine_move_entry is not None else {}),
        )
        admission = context.combat_admission
        post_combat_state = False
        deployment = context.submarine_move_entry is not None and admission is not None
        if deployment:
            # Entering deployment recalls the hunting avatar to its station and
            # reveals ammo/range. Re-prove the entire surface-fleet route, but
            # do not mistake that game-owned sub presentation for a grid input.
            self._validate_campaign_combat_route_state(context, state, for_next_input=True)
            if (state.submarine is None or len(admission.map_signature) <= 11
                    or state.submarine.marker != admission.map_signature[11][1]):
                raise SemanticGateClosed('submarine deployment camera identity changed')
        elif admission is not None and context.combat_route_receipts:
            if (
                context.combat_receipt is not None
                and len(context.combat_route_receipts) == len(admission.input_nodes)
            ):
                try:
                    prove_alas_campaign_combat_transition(
                        admission,
                        state,
                        battle_count_after=admission.battle_count + 1,
                        input_path=context.combat_receipt.path,
                    )
                    post_combat_state = True
                except SemanticGateClosed:
                    self._validate_campaign_combat_route_state(
                        context, state, for_next_input=False
                    )
            else:
                self._validate_campaign_combat_route_state(
                    context, state, for_next_input=False
                )
        elif admission is not None and context.map_fleet_switch_receipts:
            if (
                state.current_fleet_marker != admission.fleet_marker
                or state.displayed_fleet_index != admission.fleet_index
            ):
                raise SemanticGateClosed(
                    "campaign camera observation did not prove fleet switch"
                )
        elif state.signature != context.map_state.signature:
            raise SemanticGateClosed(
                "campaign camera observation changed logical map state"
            )
        if (
            admission is not None
            and not deployment
            and not context.combat_route_receipts
            and not context.map_fleet_switch_receipts
            and state.signature != admission.map_signature
        ):
            raise SemanticGateClosed(
                "campaign camera observation changed admitted map state"
            )
        positioning = context.camera_positioning_admission
        if (
            positioning is not None
            and not post_combat_state
            and state.signature != positioning.map_signature
        ):
            raise SemanticGateClosed(
                "campaign camera observation changed positioning map state"
            )
        context.map_state = state
        return state

    def campaign_camera_target_node(self) -> Optional[str]:
        context = self._require_campaign_context()
        if context.submarine_move_entry is not None and context.submarine_planned_destination is not None:
            return context.submarine_planned_destination
        admission = context.combat_admission
        if admission is not None:
            index = len(context.combat_route_receipts)
            if index < len(admission.input_nodes):
                return admission.input_nodes[index]
            return admission.target_node
        positioning = context.camera_positioning_admission
        return None if positioning is None else positioning.target_node

    def recheck_campaign_combat_target_after_camera_view(
        self, state: CampaignMapState
    ) -> CampaignMapTargetRecheckProof:
        """Bind ALAS's fresh typed View to the exact eventual target cell."""

        self._package_gate()
        context = self._require_campaign_context()
        if context.target_recheck_proof is not None:
            if (
                context.map_state is not state
                or state.generation
                != context.target_recheck_proof.camera_state_generation
            ):
                raise SemanticGateClosed(
                    "campaign target recheck token changed"
                )
            return context.target_recheck_proof
        admission = context.combat_admission
        viewport = context.viewport_swipe_proof
        if (
            admission is None
            or viewport is None
            or context.map_state is not state
            or context.viewport_swipe_required
            or context.combat_receipt is not None
        ):
            raise SemanticGateClosed(
                "campaign target recheck requires a proven camera view"
            )
        route_index = len(context.combat_route_receipts)
        if route_index >= len(admission.input_nodes):
            raise SemanticGateClosed("campaign target recheck has no remaining input")
        target_node = admission.input_nodes[route_index]
        allow_enemy_coverage = target_node == admission.target_node
        expected_path = next(
            cell.button_path for cell in state.cells if cell.node == target_node
        )
        self._validate_campaign_combat_route_state(
            context,
            state,
            for_next_input=True,
        )
        if (
            state.generation < viewport.post_generation
            or viewport.target_node != target_node
            or viewport.target_path != expected_path
        ):
            raise SemanticGateClosed(
                "campaign target recheck changed viewport identity"
            )
        target = self.oracle.campaign_map_cell_input(
            state,
            target_node,
            allow_expected_enemy_coverage=allow_enemy_coverage,
        )
        if target.path != expected_path:
            raise SemanticGateClosed("campaign target recheck changed cell path")
        assert target.point is not None and target.bounds is not None
        context.combat_admission = replace(
            admission,
            input_generation=max(admission.input_generation, state.generation),
            point=(target.point if target_node == admission.target_node else admission.point),
            bounds=(target.bounds if target_node == admission.target_node else admission.bounds),
        )
        proof = CampaignMapTargetRecheckProof(
            target_node=target_node,
            viewport_post_generation=viewport.post_generation,
            camera_state_generation=state.generation,
            recheck_generation=state.generation,
            path=target.path,
            point=target.point,
            bounds=target.bounds,
        )
        context.target_recheck_proof = proof
        return proof

    @staticmethod
    def _campaign_grid_location(button: Any) -> Optional[Tuple[int, int]]:
        """Read ALAS `_goto()`'s explicit global-location annotation only."""

        location = getattr(button, "__str__", None)
        if callable(location) or not isinstance(location, (tuple, list)):
            return None
        if len(location) != 2 or any(
            isinstance(value, bool) or not isinstance(value, int)
            for value in location
        ):
            return None
        if not (
            hasattr(button, "corner")
            and hasattr(button, "button")
            and hasattr(button, "location")
        ):
            return None
        return tuple(location)

    @staticmethod
    def _campaign_node(location: Tuple[int, int]) -> str:
        column, row = location
        if not (0 <= column < 26 and 0 <= row < 99):
            raise SemanticGateClosed("campaign combat grid location is outside bounds")
        return chr(ord("A") + column) + str(row + 1)

    @staticmethod
    def _campaign_post_combat_state_proven(
        context: _CampaignFlowContext,
        state: CampaignMapState,
    ) -> bool:
        admission = context.combat_admission
        receipt = context.combat_receipt
        if admission is None or receipt is None:
            return False
        try:
            prove_alas_campaign_combat_transition(
                admission,
                state,
                battle_count_after=admission.battle_count + 1,
                input_path=receipt.path,
            )
        except SemanticGateClosed:
            return False
        return True

    @staticmethod
    def _validate_campaign_combat_route_state(
        context: _CampaignFlowContext,
        state: CampaignMapState,
        *,
        for_next_input: bool,
    ) -> None:
        """Keep a multi-input ALAS route bound to the admitted logical map."""

        admission = context.combat_admission
        if admission is None:
            raise SemanticGateClosed("campaign combat admission is absent")
        baseline = admission.map_signature
        if (
            state.stage_code != admission.stage_code
            or tuple((cell.node, cell.button_path) for cell in state.cells)
            != tuple(baseline[3])
            or state.land_nodes != tuple(baseline[4])
            or state.current_fleet_marker != admission.fleet_marker
            or state.displayed_fleet_index != admission.fleet_index
        ):
            raise SemanticGateClosed("campaign combat route changed map identity")

        route_index = len(context.combat_route_receipts)
        if route_index > len(admission.input_nodes):
            raise SemanticGateClosed("campaign combat route input count changed")
        previous_node = (
            admission.origin_node
            if route_index == 0
            else admission.input_nodes[route_index - 1]
        )
        fleets = tuple(
            fleet for fleet in state.fleets if fleet.marker == admission.fleet_marker
        )
        if len(fleets) != 1 or fleets[0].ammo != admission.ammo_before:
            raise SemanticGateClosed("campaign combat route fleet identity changed")
        if for_next_input:
            if fleets[0].node != previous_node:
                raise SemanticGateClosed(
                    "campaign combat route has not reached its previous input"
                )
        else:
            # A single ALAS destination click makes Unity animate the fleet
            # through every cell of the already-admitted route.  Camera and
            # arrival probes may observe any of those intermediate nodes
            # before ChapterPreCombatUI mounts.  No extra input is authorized:
            # the complete enemy/pickup/fleet identity below must remain the
            # admitted baseline and ammo cannot change.
            allowed_progress = set(admission.route_nodes)
            if fleets[0].node not in allowed_progress:
                raise SemanticGateClosed(
                    "campaign combat route fleet left its admitted progress"
                )

        # Unity may reorder sibling fleet/enemy attachments after a camera
        # movement or a fleet step.  These collections are logical sets; bind
        # every exact member while ignoring only hierarchy enumeration order.
        normalized_fleets = tuple(
            sorted(
                (
                    fleet.marker,
                    admission.origin_node
                    if fleet.marker == admission.fleet_marker
                    else fleet.node,
                    fleet.ammo,
                    fleet.ammo_capacity,
                )
                for fleet in state.fleets
            )
        )
        baseline_fleets = tuple(sorted(tuple(baseline[5])))
        current_enemies = tuple(
            sorted(
                (
                    enemy.node,
                    enemy.object_id,
                    enemy.sprite,
                    enemy.scale,
                    enemy.genre,
                    enemy.level,
                    enemy.fighting,
                    enemy.is_siren,
                )
                for enemy in state.enemies
            )
        )
        baseline_enemies = tuple(sorted(tuple(baseline[6])))
        current_pickups = tuple(
            sorted(
                (pickup.node, pickup.kind, pickup.sprite)
                for pickup in state.pickups
            )
        )
        baseline_pickups = tuple(sorted(tuple(baseline[7])))
        if (
            normalized_fleets != baseline_fleets
            or current_enemies != baseline_enemies
            or current_pickups != baseline_pickups
        ):
            raise SemanticGateClosed("campaign combat route dynamic state changed")

    @staticmethod
    def _campaign_combat_input_retry_state_proven(
        context: _CampaignFlowContext, state: CampaignMapState
    ) -> bool:
        """Prove that one committed destination tap had no game-side effect."""

        admission = context.combat_admission
        if admission is None or state.signature != admission.map_signature:
            return False
        fleets = tuple(
            fleet for fleet in state.fleets if fleet.marker == admission.fleet_marker
        )
        return bool(
            len(fleets) == 1
            and fleets[0].node == admission.origin_node
            and fleets[0].ammo == admission.ammo_before
            and context.combat_input_retry_count == 0
        )

    def click_campaign_combat_grid(self, button: Any) -> ActionReceipt:
        """Consume each budget unit at ALAS's original `device.click(grid)`."""

        self._package_gate()
        context = self._require_campaign_context()
        admission = context.combat_admission
        location = self._campaign_grid_location(button)
        if admission is None or location is None or context.map_state is None:
            raise SemanticGateClosed("campaign combat grid input is not authorized")
        if (
            context.viewport_swipe_proof is not None
            and context.target_recheck_proof is None
        ):
            raise SemanticGateClosed(
                "campaign combat grid input requires post-camera target recheck"
            )
        node = self._campaign_node(location)
        route_index = len(context.combat_route_receipts)
        if route_index >= len(admission.input_nodes):
            # After combat_status has returned to the exact stable map, ALAS's
            # goto loop submits the target grid once more while confirming the
            # fleet's arrival.  This is not another combat mutation.  Admit a
            # no-input acknowledgement only when the fresh post-state proves
            # the original enemy disappeared, the admitted fleet occupies the
            # same target, and ammunition decreased exactly once.  A missed
            # first tap, a different cell, or any ambiguous map still fails
            # closed and never receives a second physical input.
            if (
                node != admission.target_node
                or context.combat_receipt is None
                or route_index != len(admission.input_nodes)
                or context.map_columns is None
                or context.map_rows is None
                or context.map_expected_fleet_count is None
            ):
                raise SemanticGateClosed(
                    "campaign combat grid requires remaining budget"
                )
            post_state = self.oracle.campaign_map_state(
                context.stage_code,
                columns=context.map_columns,
                rows=context.map_rows,
                land_cells=context.map_land_cells,
                expected_fleet_count=context.map_expected_fleet_count,
            )
            if (
                self._campaign_combat_input_retry_state_proven(context, post_state)
                and self._action_ledger.allowed("campaign.grid_click")
                and self._action_ledger.remaining("campaign.grid_click") >= 1
            ):
                target = self.oracle.campaign_map_cell_input(
                    post_state,
                    node,
                    allow_expected_enemy_coverage=True,
                )
                assert target.point is not None and target.bounds is not None
                receipt = self._dispatch_mutation(
                    "campaign.grid_click",
                    lambda: self.oracle.click_campaign_map_cell(
                        post_state,
                        node,
                        allow_expected_enemy_coverage=True,
                    ),
                )
                if (
                    receipt.path != target.path
                    or receipt.point != target.point
                    or receipt.bounds != target.bounds
                ):
                    raise SemanticGateClosed(
                        "campaign combat retry receipt changed"
                    )
                context.map_state = post_state
                context.combat_receipt = receipt
                context.combat_input_retry_count += 1
                context.viewport_swipe_proof = None
                context.target_recheck_proof = None
                context.passive_transition_until = time.monotonic() + 30.0
                return receipt
            try:
                prove_alas_campaign_combat_transition(
                    admission,
                    post_state,
                    battle_count_after=admission.battle_count + 1,
                    input_path=context.combat_receipt.path,
                )
            except SemanticGateClosed as exc:
                raise SemanticGateClosed(
                    "campaign combat grid requires proven post-state"
                ) from exc
            context.map_state = post_state
            return context.combat_receipt
        expected_node = admission.input_nodes[route_index]
        if node != expected_node:
            raise SemanticGateClosed("campaign combat grid target changed")
        if (
            not self._action_ledger.allowed("campaign.grid_click")
            or self._action_ledger.remaining("campaign.grid_click") < 1
            or context.combat_receipt is not None
        ):
            raise SemanticGateClosed(
                "campaign combat grid requires remaining budget"
            )
        if (
            context.map_columns is None
            or context.map_rows is None
            or context.map_expected_fleet_count is None
        ):
            raise SemanticGateClosed("campaign combat map topology is incomplete")
        state = self.oracle.campaign_map_state(
            context.stage_code,
            columns=context.map_columns,
            rows=context.map_rows,
            land_cells=context.map_land_cells,
            expected_fleet_count=context.map_expected_fleet_count,
        )
        self._validate_campaign_combat_route_state(
            context, state, for_next_input=True
        )
        allow_enemy_coverage = node == admission.target_node
        if context.viewport_swipe_required:
            # The admitted frame can observe the destination under a passing
            # fleet animation even though ALAS reaches its click several
            # seconds later.  Waive the stale swipe requirement only when the
            # final fresh state proves the identical cell is now the unique
            # actionable top raycast; otherwise this exact read still fails
            # closed and no input is sent.
            target = self.oracle.campaign_map_cell_input(
                state,
                node,
                allow_expected_enemy_coverage=allow_enemy_coverage,
            )
            context.viewport_swipe_required = False
        else:
            target = self.oracle.campaign_map_cell_input(
                state,
                node,
                allow_expected_enemy_coverage=allow_enemy_coverage,
            )
        assert target.point is not None and target.bounds is not None
        receipt = self._dispatch_mutation(
            "campaign.grid_click",
            lambda: self.oracle.click_campaign_map_cell(
                state,
                node,
                allow_expected_enemy_coverage=allow_enemy_coverage,
            ),
        )
        # The ADB tap has happened.  Consume and record the lease before any
        # subsequent assertion so an anomalous receipt can never be replayed.
        context.map_state = state
        context.combat_route_receipts.append(receipt)
        if (
            receipt.path != target.path
            or receipt.point != target.point
            or receipt.bounds != target.bounds
            or receipt.generation < admission.input_generation
        ):
            raise SemanticGateClosed("campaign combat input receipt changed")
        context.combat_admission = replace(
            admission,
            input_generation=receipt.generation,
            cell_path=(target.path if node == admission.target_node else admission.cell_path),
            point=(target.point if node == admission.target_node else admission.point),
            bounds=(target.bounds if node == admission.target_node else admission.bounds),
        )
        if node == admission.target_node:
            context.combat_receipt = receipt
            context.passive_transition_until = time.monotonic() + 30.0
        else:
            # The intermediate tap has already started a passive fleet
            # transition, so the next cell cannot be re-read synchronously.
            # ALAS's next in_sight() call owns any required camera movement;
            # the eventual grid input still requires a fresh top-raycast read.
            context.viewport_swipe_proof = None
            context.target_recheck_proof = None
            context.viewport_swipe_required = False
        return receipt

    def campaign_combat_committed(self) -> bool:
        context = self._campaign_context
        # Both a grid entry and an accepted ambush choice can lead to the
        # original Combat flow. Keep their receipts separate: an ambush must
        # never count as defeating the planned map target.
        return context is not None and (
            context.combat_receipt is not None or context.ambush_receipt is not None
        )

    def campaign_combat_active(self) -> bool:
        """Report the admitted ALAS goto/combat lease, including waypoints."""

        context = self._campaign_context
        return context is not None and context.combat_admission is not None

    def handle_campaign_ambush(self, *, evade: bool) -> bool:
        """Resolve one exact official ambush popup inside the campaign lease."""

        self._package_gate()
        context = self._require_campaign_context()
        if not self.oracle.campaign_ambush_visible(evade=evade):
            return False
        if (
            not self._action_ledger.allowed("campaign.grid_click")
            or self._action_ledger.remaining("campaign.grid_click") < 1
        ):
            raise SemanticGateClosed("campaign ambush requires remaining budget")
        if context.ambush_receipt is not None:
            raise SemanticGateClosed("campaign ambush input has not reached its postcondition")
        context.ambush_receipt = self._dispatch_mutation(
            "campaign.grid_click",
            lambda: self.oracle.click_campaign_ambush(evade=evade),
        )
        context.passive_transition_until = time.monotonic() + 20.0
        return True

    def campaign_ambush_present(self) -> bool:
        self._package_gate()
        self._require_campaign_context()
        return self._frame_or_live_observation_oracle().campaign_ambush_present()

    def campaign_ambush_outcome(self) -> Optional[str]:
        context = self._require_campaign_context()
        if context.ambush_receipt is None:
            return None
        oracle = self._frame_or_live_observation_oracle()
        if oracle.campaign_ambush_present():
            return None
        if oracle.read_state().generation <= context.ambush_receipt.generation:
            raise SemanticGateClosed("ambush result predates its input")
        return oracle.campaign_ambush_notice()

    def finish_campaign_ambush(self) -> None:
        context = self._require_campaign_context()
        if context.ambush_receipt is None or self.oracle.campaign_ambush_present():
            raise SemanticGateClosed("campaign ambush completion is not proven")
        if self.oracle.read_state().generation <= context.ambush_receipt.generation:
            raise SemanticGateClosed("ambush completion predates its input")
        context.ambush_receipt = None

    def confirm_campaign_combat(
        self,
        battle_count_after: int,
    ) -> AlasCampaignCombatProof:
        """Validate ALAS's completed combat against a stable semantic map."""

        self._package_gate()
        context = self._require_campaign_context()
        if context.combat_proof is not None:
            return context.combat_proof
        if (
            context.combat_admission is None
            or context.combat_receipt is None
            or context.map_columns is None
            or context.map_rows is None
            or context.map_expected_fleet_count is None
        ):
            raise SemanticGateClosed("campaign combat input is not committed")
        state = self.oracle.campaign_map_state(
            context.stage_code,
            columns=context.map_columns,
            rows=context.map_rows,
            land_cells=context.map_land_cells,
            expected_fleet_count=context.map_expected_fleet_count,
        )
        proof = prove_alas_campaign_combat_transition(
            context.combat_admission,
            state,
            battle_count_after=battle_count_after,
            input_path=context.combat_receipt.path,
        )
        context.map_state = state
        context.combat_proof = proof
        return proof
