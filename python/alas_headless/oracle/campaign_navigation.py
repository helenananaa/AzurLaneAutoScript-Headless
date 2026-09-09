"""Campaign navigation for the typed ALAS boundary."""

from __future__ import annotations

import math
import re
import re
from typing import List, Optional, Sequence, Tuple
from .contracts import (
    ActionReceipt,
    ButtonState,
    CampaignAutoSearchActiveState,
    CampaignMapEntryState,
    CampaignMapState,
    CampaignMapViewportSwipeIntent,
    CampaignMapViewportSwipeProof,
    OracleState,
    Point,
    UiState,
)
from .errors import SemanticGateClosed, SemanticTargetMissing


class CampaignNavigationOracle:
    """Campaign navigation operations sharing the oracle frame and input boundary."""

    def _campaign_fleet_lock_control(self):
        state = self.read_state()
        suffix = "OverlayCamera/Overlay/UIMain/top/LevelStageView(Clone)/right_stage/event/collapse/lock_fleet"
        buttons = tuple(b for b in state.buttons if b.path == suffix and b.name == "lock_fleet")
        if not buttons:
            return state, None, None
        ui = self.read_ui_state(check_foreground=False)
        if ui.image_truncated or ui.generation < state.generation or ui.generation > state.generation + 2:
            raise SemanticGateClosed("campaign fleet-lock snapshots are not coherent")
        images = tuple(i for i in ui.images if i.path == suffix
                       and i.active_in_hierarchy and i.active_and_enabled and not i.truncated)
        if len(buttons) != 1 or len(images) != 1 or images[0].sprite not in ("auto_battle_on", "auto_battle_off"):
            raise SemanticGateClosed("campaign fleet-lock identity is absent or ambiguous")
        return state, buttons[0], images[0].sprite == "auto_battle_on"

    def campaign_fleet_lock_selected(self) -> Optional[bool]:
        return self._retry_transition_read(self._campaign_fleet_lock_control)[2]

    def click_campaign_fleet_lock(self, expected: bool) -> ActionReceipt:
        state, button, selected = self._retry_transition_read(self._campaign_fleet_lock_control)
        if type(expected) is not bool or button is None or selected is not expected:
            raise SemanticGateClosed("campaign fleet-lock state changed before input")
        if not button.actionable or self._blocking_rules(state, "campaign/fleet-lock"):
            raise SemanticGateClosed("campaign fleet-lock target is not actionable")
        if not (0 <= button.point.x < self.fingerprint.width and 0 <= button.point.y < self.fingerprint.height):
            raise SemanticGateClosed("campaign fleet-lock target is outside the screen")
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("foreground changed before fleet-lock input")
        self._tap(int(round(button.point.x)), int(round(button.point.y)))
        return ActionReceipt(semantic_id="campaign/fleet-lock/" + ("on" if expected else "off"),
                             generation=state.generation, point=button.point,
                             bounds=button.bounds, path=button.path)

    def campaign_map_entry_state(self) -> CampaignMapEntryState:
        """Read the exact map-scene root without exposing any map input."""

        return self._retry_transition_read(
            self._campaign_map_entry_state_once,
            attempts=12,
        )

    def campaign_auto_search_active_state(
        self,
    ) -> CampaignAutoSearchActiveState:
        """Prove official auto-search has reached an owned battle surface.

        A plain ``LevelGrid`` only proves that the sortie entered a campaign
        map; manual map control presents the same root.  Accepting it here can
        therefore turn a disabled/ignored auto-search toggle into a false
        positive.  The official flow must advance to one exact pre-combat,
        combat, or result root before ownership is proven.
        """

        ui_state = self.read_ui_state()
        markers = (
            "ChapterPreCombatUI(Clone)",
            "CombatUIStandard(Clone)",
            "NewBattleResultEmptyUI(Clone)",
        )
        paths = tuple(
            item.path
            for item in (*ui_state.texts, *ui_state.images)
            if item.active_in_hierarchy
            and item.active_and_enabled
            and any(("/" + marker + "/") in item.path for marker in markers)
        )
        roots = {
            path[: path.index("(Clone)") + len("(Clone)")]
            for path in paths
        }
        if not roots:
            raise SemanticTargetMissing(
                "campaign official auto-search surface is absent"
            )
        if len(roots) != 1:
            raise SemanticGateClosed(
                "campaign official auto-search surface is ambiguous"
            )
        return CampaignAutoSearchActiveState(
            generation=ui_state.generation,
            root_path=next(iter(roots)),
        )

    def campaign_official_combat_auto_state(
        self,
    ) -> Optional[Tuple[int, bool]]:
        """Read the official combat AutoBtn when a battle is visible."""

        ui_state = self.read_ui_state()
        suffix = "CombatUIStandard(Clone)/AutoBtn"
        matches = tuple(
            toggle
            for toggle in ui_state.toggles
            if toggle.path.endswith(suffix)
            and toggle.active_in_hierarchy
            and toggle.active_and_enabled
        )
        if not matches:
            return None
        if len(matches) != 1:
            raise SemanticGateClosed(
                "campaign official combat auto toggle is ambiguous"
            )
        return ui_state.generation, matches[0].checked

    def _campaign_map_entry_state_once(self) -> CampaignMapEntryState:
        button_state = self.read_state()
        ui_state = self.read_ui_state()
        return self._campaign_map_entry_state_from_snapshots(button_state, ui_state)

    @staticmethod
    def _campaign_map_entry_state_from_snapshots(
        button_state: OracleState,
        ui_state: UiState,
        *, allow_deployment: bool = False,
    ) -> CampaignMapEntryState:
        if (
            ui_state.generation < button_state.generation
            or ui_state.generation > button_state.generation + 2
            or ui_state.method_mask & 0x8 == 0
        ):
            raise SemanticGateClosed("campaign map-entry snapshots are incomplete")

        grid_root = "LevelCamera/Canvas/UIMain/LevelGrid"
        grid_button = re.compile(
            re.escape(grid_root)
            + r"/DragLayer/plane/quads/chapter_cell_quad_[0-9]+_[0-9]+"
        )
        stage_roots = (
            "OverlayCamera/Overlay/UIMain/top/LevelStageView(Clone)",
            "LevelCamera/Canvas/LevelOrigin/top/LevelStageView(Clone)",
        )
        required_images = {
            grid_root + "/DragLayer/plane/display/mask/sea": (
                "sea_day",
                "sea_benningdun_1",
                "sea_benningdun_2",
                "sea_YW",
                "sea_BW",
                "sea_YX",
            ),
        }
        retreat_variants = (
            (
                grid_root + "/DragLayer/op1/retreat",
                grid_root + "/DragLayer/op1/retreat/retreat",
                "reteat_popo",
            ),
            *tuple(
                (
                    stage_root + "/bottom_stage/Normal/retreat_button",
                    stage_root + "/bottom_stage/Normal/retreat_button",
                    "chetui_butten",
                )
                for stage_root in stage_roots
            ),
        )
        blocking_scene_markers = (
            "/LevelMainScene(Clone)/",
            "/LevelStageInfoView(Clone)/",
            "/LevelFleetSelectView(Clone)/",
            "/ChapterPreCombatUI(Clone)/",
            "/CombatUIStandard(Clone)/",
            "/NewBattleResultEmptyUI(Clone)/",
        )
        active_buttons = tuple(
            button
            for button in button_state.buttons
            if button.active_in_hierarchy and button.active_and_enabled
        )
        grid_button_paths = tuple(
            sorted(
                button.path
                for button in active_buttons
                if grid_button.fullmatch(button.path)
            )
        )
        active_images = tuple(
            image
            for image in ui_state.images
            if image.active_in_hierarchy
            and image.active_and_enabled
            and not image.truncated
        )
        required_image_paths = tuple(sorted(required_images))
        required_image_matches = tuple(
            (
                allowed_sprites,
                tuple(image for image in active_images if image.path == path),
            )
            for path, allowed_sprites in required_images.items()
        )
        stage_back_matches = tuple(
            (
                stage_root + "/top_stage/back_button",
                stage_root + "/top_stage/back_button/mask/Image",
            )
            for stage_root in stage_roots
            if sum(
                button.path == stage_root + "/top_stage/back_button"
                for button in active_buttons
            )
            == 1
            and sum(
                image.path == stage_root + "/top_stage/back_button/mask/Image"
                and image.sprite == "back_btn"
                for image in active_images
            )
            == 1
        )
        retreat_variant_matches = tuple(
            (button_path, image_path)
            for button_path, image_path, sprite in retreat_variants
            if sum(button.path == button_path for button in active_buttons) == 1
            and sum(
                image.path == image_path and image.sprite == sprite
                for image in active_images
            )
            == 1
        )
        deployment_proven = False
        if allow_deployment and len(stage_back_matches) == 1:
            deployment_root = stage_back_matches[0][0].removesuffix('/top_stage/back_button') + '/bottom_stage/Action/MissileStrike/'
            deployment_proven = all(
                sum(b.path == deployment_root+name for b in active_buttons) == 1
                and sum(t.path == deployment_root+name+'/Text' and t.text.strip() == label
                        and t.active_in_hierarchy and t.active_and_enabled and not t.truncated
                        for t in ui_state.texts) == 1
                for name, label in (('cancel_button', '取消部署'), ('confirm_button', '确认部署')))
        if (
            len(stage_back_matches) != 1
            or not (retreat_variant_matches or deployment_proven)
            or not grid_button_paths
            or any(
                len(matches) != 1 or matches[0].sprite not in allowed_sprites
                for allowed_sprites, matches in required_image_matches
            )
        ):
            raise SemanticGateClosed("campaign map-scene identity is absent")
        stage_back_button_path, stage_back_image_path = stage_back_matches[0]
        retreat_button_paths = tuple(item[0] for item in retreat_variant_matches)
        retreat_image_paths = tuple(item[1] for item in retreat_variant_matches)
        fixed_button_paths = (*retreat_button_paths, stage_back_button_path)
        if any(
            marker in item.path
            for marker in blocking_scene_markers
            for item in (*button_state.buttons, *ui_state.texts)
            if item.active_in_hierarchy and item.active_and_enabled
        ):
            raise SemanticGateClosed("campaign map and blocking identities overlap")
        return CampaignMapEntryState(
            generation=button_state.generation,
            root_path=grid_root,
            button_paths=tuple(sorted((*fixed_button_paths, *grid_button_paths))),
            image_paths=tuple(
                sorted(
                    (
                        *required_image_paths,
                        *retreat_image_paths,
                        stage_back_image_path,
                    )
                )
            ),
        )

    @staticmethod
    def _campaign_map_node(row: int, column: int) -> str:
        if row < 1 or column < 1:
            raise SemanticGateClosed("campaign map coordinate is invalid")
        value = column
        letters = ""
        while value:
            value, remainder = divmod(value - 1, 26)
            letters = chr(ord("A") + remainder) + letters
        return letters + str(row)

    def campaign_map_state(
        self,
        stage_code: str,
        *,
        columns: int,
        rows: int,
        land_cells: Sequence[Tuple[int, int]],
        expected_fleet_count: int,
        allow_deployment: bool = False,
    ) -> CampaignMapState:
        """Build a stable, complete, read-only map model from typed Unity state.

        ``land_cells`` uses ALAS's zero-based ``CampaignMap`` locations.  The
        complete Button topology is checked against that map definition, while
        all dynamic objects require a non-truncated Image/Text snapshot.  Two
        increasing generations must expose the same logical signature.
        """

        numeric_stage = re.fullmatch(r"[1-9][0-9]*-[1-9][0-9]*", stage_code)
        event_stage = re.fullmatch(r"[a-z]+[0-9]*", stage_code)
        if numeric_stage is None and event_stage is None:
            raise SemanticGateClosed("campaign map stage code is not canonical")
        if (
            isinstance(columns, bool)
            or not isinstance(columns, int)
            or isinstance(rows, bool)
            or not isinstance(rows, int)
            or columns < 1
            or rows < 1
            or columns > 26
            or rows > 99
        ):
            raise SemanticGateClosed("campaign map shape is invalid")
        if (
            isinstance(expected_fleet_count, bool)
            or not isinstance(expected_fleet_count, int)
            or expected_fleet_count not in (1, 2)
        ):
            raise SemanticGateClosed("campaign map fleet count is invalid")

        normalized_land = []
        for location in land_cells:
            if (
                not isinstance(location, (tuple, list))
                or len(location) != 2
                or any(
                    isinstance(value, bool) or not isinstance(value, int)
                    for value in location
                )
            ):
                raise SemanticGateClosed("campaign map land topology is malformed")
            column0, row0 = location
            if not (0 <= column0 < columns and 0 <= row0 < rows):
                raise SemanticGateClosed(
                    "campaign map land coordinate is outside its shape"
                )
            normalized_land.append((row0 + 1, column0 + 1))
        land = tuple(sorted(set(normalized_land)))
        if len(land) != len(normalized_land):
            raise SemanticGateClosed("campaign map land topology contains duplicates")
        # A fully navigable map is valid (for example main campaign 1-1 is a
        # one-row corridor with no ``--`` land cells).  An all-land map still
        # cannot contain a spawn, fleet, or combat target and stays closed.
        if len(land) >= rows * columns:
            raise SemanticGateClosed("campaign map land topology is incomplete")

        reader = lambda: self._campaign_map_state_once(
            stage_code,
            columns=columns,
            rows=rows,
            land=land,
            expected_fleet_count=expected_fleet_count,
            **({'allow_deployment': True} if allow_deployment else {}),
        )
        previous = self._retry_transition_read(reader, attempts=12)
        for _ in range(11):
            self._sleep(0.25)
            current = self._retry_transition_read(
                reader, attempts=12, interval_seconds=0.05
            )
            if (
                current.generation > previous.generation
                and current.signature == previous.signature
            ):
                return current
            previous = current
        raise SemanticGateClosed("campaign map model did not stabilize")

    def _campaign_map_cell_target(
        self,
        state: CampaignMapState,
        node: str,
        *,
        require_top_raycast: bool,
        require_unblocked: bool = True,
    ) -> ButtonState:
        if not isinstance(state, CampaignMapState):
            raise SemanticGateClosed("campaign map-cell input requires a typed state")
        matches = tuple(cell for cell in state.cells if cell.node == node)
        if len(matches) != 1:
            raise SemanticGateClosed("campaign map-cell input is absent or ambiguous")
        cell = matches[0]
        observed = self.read_state()
        if observed.generation < state.generation:
            raise SemanticGateClosed("campaign map-cell input snapshot is stale")
        buttons = tuple(
            button for button in observed.buttons if button.path == cell.button_path
        )
        if len(buttons) != 1:
            raise SemanticGateClosed("campaign map-cell Button identity changed")
        target = buttons[0]
        if target.point is not None and target.bounds is not None:
            geometry_delta = max(
                abs(target.point.x - cell.point.x),
                abs(target.point.y - cell.point.y),
                abs(target.bounds.left - cell.bounds.left),
                abs(target.bounds.top - cell.bounds.top),
                abs(target.bounds.right - cell.bounds.right),
                abs(target.bounds.bottom - cell.bounds.bottom),
            )
        else:
            geometry_delta = math.inf
        # A viewport move does not tap this coordinate.  Unity can continue a
        # sub-pixel easing step between the stabilized map read and this final
        # identity check, so allow only a tightly bounded drift there.  Actual
        # grid taps retain exact geometry below.
        geometry_matches = (
            geometry_delta == 0.0
            if require_top_raycast
            else geometry_delta <= 5.0
        )
        if (
            not target.active_in_hierarchy
            or not target.active_and_enabled
            or not target.interactable
            or target.raycast_top not in (True, False)
            or target.point is None
            or target.bounds is None
            or not target.bounds.contains(target.point)
            or not geometry_matches
        ):
            raise SemanticGateClosed(
                "campaign map-cell geometry or actionability changed"
            )
        if require_top_raycast and target.raycast_top is not True:
            raise SemanticGateClosed(
                "campaign map-cell geometry or actionability changed"
            )
        if require_unblocked and self._blocking_rules(observed, "campaign/map/grid"):
            raise SemanticGateClosed("campaign map-cell input is blocked")
        if require_top_raycast and not (
            0 <= target.point.x < self.fingerprint.width
            and 0 <= target.point.y < self.fingerprint.height
        ):
            raise SemanticGateClosed("campaign map-cell point is outside the screen")
        return target

    def campaign_map_cell_viewport_target(
        self,
        state: CampaignMapState,
        node: str,
    ) -> ButtonState:
        """Revalidate exact cell geometry for an ALAS-owned camera move.

        This read is only an input to the owning ALAS camera state machine.  A
        false top-raycast result is preserved, but neither a covered nor an
        already-visible cell can authorize the eventual grid tap through this
        read.  The separate one-use viewport lease controls movement.
        """

        # This is a geometry-only read used to plan a separately leased
        # viewport swipe.  Enemy/fleet models legitimately cover their cell
        # quads, so blocker admission belongs to the later exact input target,
        # not to this read-only coordinate lookup.
        return self._campaign_map_cell_target(
            state,
            node,
            require_top_raycast=False,
            require_unblocked=False,
        )

    def campaign_map_cell_input(
        self,
        state: CampaignMapState,
        node: str,
        *,
        allow_expected_enemy_coverage: bool = False,
    ) -> ButtonState:
        """Revalidate one exact actionable map cell without injecting input.

        A map-cell quad may be active while its center is covered by the map
        HUD.  Requiring the exact cell to remain the top raycast target keeps
        the semantic coordinate fail-closed; a covered center must be exposed
        by the owning ALAS camera state machine before it can be clicked.
        """

        if not allow_expected_enemy_coverage:
            return self._campaign_map_cell_target(
                state, node, require_top_raycast=True
            )

        # A live enemy's typed map object normally owns the top raycast at the
        # centre of its cell.  Permit that one covered quad only after the
        # caller has already admitted the exact combat node.  This does not
        # weaken ordinary map-cell input: the node must still contain exactly
        # one non-fighting enemy, the quad identity/geometry must be exact,
        # and all campaign blockers remain fail-closed.
        enemies = tuple(
            enemy
            for enemy in state.enemies
            if enemy.node == node and not enemy.fighting
        )
        if len(enemies) != 1:
            raise SemanticGateClosed(
                "campaign enemy-covered input lacks one exact enemy"
            )
        return self._campaign_map_cell_target(
            state,
            node,
            require_top_raycast=False,
            require_unblocked=True,
        )

    @staticmethod
    def _median(values: Sequence[float]) -> float:
        ordered = sorted(values)
        middle = len(ordered) // 2
        if len(ordered) % 2:
            return float(ordered[middle])
        return float((ordered[middle - 1] + ordered[middle]) / 2.0)

    @staticmethod
    def _solve_linear_system(
        matrix: Sequence[Sequence[float]], values: Sequence[float]
    ) -> Tuple[float, ...]:
        size = len(values)
        if len(matrix) != size or any(len(row) != size for row in matrix):
            raise SemanticGateClosed("campaign map projective model is malformed")
        augmented = [
            [float(item) for item in row] + [float(value)]
            for row, value in zip(matrix, values)
        ]
        for column in range(size):
            pivot = max(
                range(column, size),
                key=lambda row: abs(augmented[row][column]),
            )
            if abs(augmented[pivot][column]) < 1e-10:
                raise SemanticGateClosed("campaign map projective model is singular")
            augmented[column], augmented[pivot] = (
                augmented[pivot],
                augmented[column],
            )
            divisor = augmented[column][column]
            augmented[column] = [item / divisor for item in augmented[column]]
            for row in range(size):
                if row == column:
                    continue
                factor = augmented[row][column]
                if factor == 0.0:
                    continue
                augmented[row] = [
                    item - factor * pivot_item
                    for item, pivot_item in zip(augmented[row], augmented[column])
                ]
        return tuple(row[-1] for row in augmented)

    @classmethod
    def _campaign_projective_residuals(
        cls,
        before_points: Sequence[Point],
        after_points: Sequence[Point],
    ) -> Tuple[Tuple[float, ...], float]:
        """Fit one normalized planar homography and return pixel residuals."""

        if len(before_points) != len(after_points) or len(before_points) < 4:
            raise SemanticGateClosed(
                "campaign map projective model needs at least four cells"
            )

        before_x_span = max(point.x for point in before_points) - min(
            point.x for point in before_points
        )
        before_y_span = max(point.y for point in before_points) - min(
            point.y for point in before_points
        )
        major_span = max(before_x_span, before_y_span)
        minor_span = min(before_x_span, before_y_span)
        if major_span >= 10.0 and minor_span <= max(1.0, major_span * 0.01):
            horizontal = before_x_span >= before_y_span
            parameters = tuple(
                point.x if horizontal else point.y for point in before_points
            )
            parameter_mean = sum(parameters) / len(parameters)
            denominator = sum(
                (value - parameter_mean) ** 2 for value in parameters
            )
            if not math.isfinite(denominator) or denominator < 1.0:
                raise SemanticGateClosed(
                    "campaign map affine cell spread is degenerate"
                )
            after_x_mean = sum(point.x for point in after_points) / len(after_points)
            after_y_mean = sum(point.y for point in after_points) / len(after_points)
            slope_x = sum(
                (value - parameter_mean) * (point.x - after_x_mean)
                for value, point in zip(parameters, after_points)
            ) / denominator
            slope_y = sum(
                (value - parameter_mean) * (point.y - after_y_mean)
                for value, point in zip(parameters, after_points)
            ) / denominator
            forward_scale = slope_x if horizontal else slope_y
            if (
                not math.isfinite(slope_x)
                or not math.isfinite(slope_y)
                or forward_scale < 0.10
            ):
                raise SemanticGateClosed(
                    "campaign map affine model collapses or reverses geometry"
                )
            intercept_x = after_x_mean - slope_x * parameter_mean
            intercept_y = after_y_mean - slope_y * parameter_mean
            residuals = tuple(
                math.hypot(
                    point.x - (slope_x * value + intercept_x),
                    point.y - (slope_y * value + intercept_y),
                )
                for value, point in zip(parameters, after_points)
            )
            rms = math.sqrt(
                sum(value * value for value in residuals) / len(residuals)
            )
            return residuals, rms

        def normalize(points: Sequence[Point]):
            center_x = sum(point.x for point in points) / len(points)
            center_y = sum(point.y for point in points) / len(points)
            scale = math.sqrt(
                sum(
                    (point.x - center_x) ** 2 + (point.y - center_y) ** 2
                    for point in points
                )
                / len(points)
            )
            if not math.isfinite(scale) or scale < 1.0:
                raise SemanticGateClosed(
                    "campaign map projective cell spread is degenerate"
                )
            normalized = tuple(
                (
                    (point.x - center_x) / scale,
                    (point.y - center_y) / scale,
                )
                for point in points
            )
            return normalized, center_x, center_y, scale

        before, _, _, _ = normalize(before_points)
        after, after_center_x, after_center_y, after_scale = normalize(after_points)
        rows: List[Tuple[float, ...]] = []
        outputs: List[float] = []
        for (x, y), (u, v) in zip(before, after):
            rows.append((x, y, 1.0, 0.0, 0.0, 0.0, -u * x, -u * y))
            outputs.append(u)
            rows.append((0.0, 0.0, 0.0, x, y, 1.0, -v * x, -v * y))
            outputs.append(v)

        normal = [[0.0 for _ in range(8)] for _ in range(8)]
        right = [0.0 for _ in range(8)]
        for row, output in zip(rows, outputs):
            for left_index in range(8):
                right[left_index] += row[left_index] * output
                for right_index in range(8):
                    normal[left_index][right_index] += (
                        row[left_index] * row[right_index]
                    )
        parameters = cls._solve_linear_system(normal, right)
        a, b, c, d, e, f, g, h = parameters
        determinant = a * (e - f * h) - b * (d - f * g) + c * (d * h - e * g)
        if not math.isfinite(determinant) or abs(determinant) < 1e-4:
            raise SemanticGateClosed("campaign map projective model collapses geometry")

        denominators = tuple(g * x + h * y + 1.0 for x, y in before)
        if any(
            not math.isfinite(value) or abs(value) < 0.10 for value in denominators
        ) or any(value * denominators[0] <= 0.0 for value in denominators):
            raise SemanticGateClosed("campaign map projective model crosses infinity")

        residuals = []
        for (x, y), denominator, actual in zip(before, denominators, after_points):
            predicted_x = (
                a * x + b * y + c
            ) / denominator * after_scale + after_center_x
            predicted_y = (
                d * x + e * y + f
            ) / denominator * after_scale + after_center_y
            residuals.append(
                math.hypot(
                    actual.x - predicted_x,
                    actual.y - predicted_y,
                )
            )
        rms = math.sqrt(sum(value * value for value in residuals) / len(residuals))
        return tuple(residuals), rms

    def campaign_map_viewport_swipe(
        self,
        state: CampaignMapState,
        target_node: str,
        intent: CampaignMapViewportSwipeIntent,
        *,
        start: Tuple[int, int],
        end: Tuple[int, int],
        duration_ms: int,
        columns: int,
        rows: int,
        land_cells: Sequence[Tuple[int, int]],
        expected_fleet_count: int,
        allow_enemy_additions: bool = False,
        allow_deployment: bool = False,
    ) -> CampaignMapViewportSwipeProof:
        """Inject and prove one typed ALAS-requested campaign viewport swipe."""

        if self._swipe is None:
            raise SemanticGateClosed("campaign map viewport input backend is absent")
        if not isinstance(intent, CampaignMapViewportSwipeIntent):
            raise SemanticGateClosed("campaign map viewport intent is not typed")
        before_target = self.campaign_map_cell_viewport_target(state, target_node)
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("foreground changed immediately before input")
        input_generation = self._last_generation or state.generation

        # This is the only state-changing statement in the method.  Callers
        # consume their one-use lease before entering here, so a failed
        # postcondition can never replay the gesture.
        self._swipe(start[0], start[1], end[0], end[1], duration_ms)

        post_state = self.campaign_map_state(
            state.stage_code,
            columns=columns,
            rows=rows,
            land_cells=land_cells,
            expected_fleet_count=expected_fleet_count,
            **({'allow_deployment': True} if allow_deployment else {}),
        )
        if post_state.generation <= input_generation:
            raise SemanticGateClosed("campaign map viewport post-state predates input")
        before_signature = state.signature
        post_signature = post_state.signature
        # Boss appearance is an asynchronous map event which can race the
        # camera gesture ALAS performs immediately after a battle.  Admit only
        # the exact additive transition: every non-enemy field is unchanged,
        # every previous enemy remains byte-for-byte identical, and exactly
        # one newly observed enemy is typed as Boss.  A swipe still cannot
        # hide, replace, move, or otherwise mutate logical map state.
        same_non_enemy_state = (
            before_signature[:6] + before_signature[7:]
            == post_signature[:6] + post_signature[7:]
        )
        removed_enemies = tuple(
            enemy for enemy in state.enemies if enemy not in post_state.enemies
        )
        added_enemies = tuple(
            enemy for enemy in post_state.enemies if enemy not in state.enemies
        )
        boss_appeared = bool(
            same_non_enemy_state
            and not removed_enemies
            and len(added_enemies) == 1
            and added_enemies[0].genre == "Boss"
        )
        post_combat_wave_appeared = bool(
            allow_enemy_additions
            and same_non_enemy_state
            and not removed_enemies
            and added_enemies
            and all(not enemy.fighting for enemy in added_enemies)
        )
        if (
            post_signature != before_signature
            and not boss_appeared
            and not post_combat_wave_appeared
        ):
            raise SemanticGateClosed("campaign map viewport changed logical map state")
        before_cells = {cell.node: cell for cell in state.cells}
        after_cells = {cell.node: cell for cell in post_state.cells}
        if set(before_cells) != set(after_cells) or len(before_cells) < 4:
            raise SemanticGateClosed("campaign map viewport cell set changed")
        after_target = after_cells[target_node]
        if after_target.button_path != before_target.path:
            raise SemanticGateClosed("campaign map viewport target identity changed")
        ordered_nodes = sorted(before_cells)
        deltas = tuple(
            (
                after_cells[node].point.x - before_cells[node].point.x,
                after_cells[node].point.y - before_cells[node].point.y,
            )
            for node in ordered_nodes
        )
        median_dx = self._median(tuple(delta[0] for delta in deltas))
        median_dy = self._median(tuple(delta[1] for delta in deltas))
        median_norm = math.hypot(median_dx, median_dy)
        finger_dx = float(end[0] - start[0])
        finger_dy = float(end[1] - start[1])
        finger_norm = math.hypot(finger_dx, finger_dy)
        if finger_norm < 10.0:
            raise SemanticGateClosed("campaign map viewport did not move")
        if median_norm < 10.0:
            # Unity clamps an ALAS-requested gesture to a true no-op at the
            # map edge even when the destination cell is already exposed.
            # Admit only that exact case: every projected cell is stationary
            # and the independently re-read destination is still the unique
            # top raycast at the identical path, point and bounds.  A covered
            # target or any partial displacement remains fail-closed.
            post_target = self.campaign_map_cell_viewport_target(
                post_state, target_node
            )
            target_fleets = tuple(
                fleet for fleet in post_state.fleets if fleet.node == target_node
            )
            current_fleet_covers_target = bool(
                len(target_fleets) == 1
                and target_fleets[0].marker == post_state.current_fleet_marker
                and not any(enemy.node == target_node for enemy in post_state.enemies)
            )
            assert before_target.point is not None
            assert before_target.bounds is not None
            if (
                any(math.hypot(dx, dy) > 1.0 for dx, dy in deltas)
                or (
                    not current_fleet_covers_target
                    and (
                        before_target.raycast_top is not True
                        or post_target.raycast_top is not True
                    )
                )
                or post_target.path != before_target.path
                or post_target.point != before_target.point
                or post_target.bounds != before_target.bounds
            ):
                raise SemanticGateClosed("campaign map viewport did not move")
            return CampaignMapViewportSwipeProof(
                semantic_id="campaign/map/viewport/" + target_node,
                target_node=target_node,
                pre_generation=state.generation,
                input_generation=input_generation,
                post_generation=post_state.generation,
                name=intent.name,
                grid_vector=intent.grid_vector,
                pixel_vector=intent.pixel_vector,
                start=start,
                end=end,
                duration_ms=duration_ms,
                coherent_cell_count=len(deltas),
                median_cell_delta=(median_dx, median_dy),
                maximum_delta_residual=max(
                    (math.hypot(dx, dy) for dx, dy in deltas), default=0.0
                ),
                target_path=post_target.path,
                target_before_point=before_target.point,
                target_after_point=post_target.point,
                target_after_bounds=post_target.bounds,
                post_state=post_state,
            )
        alignment = (median_dx * finger_dx + median_dy * finger_dy) / (
            median_norm * finger_norm
        )
        # A boss or authorized post-combat wave can trigger Unity's own camera
        # focus while the ALAS gesture is in flight.  The independently read
        # map is otherwise identical/additive and its cell displacement must
        # remain projectively coherent below; the subsequent typed ALAS camera
        # observation proves the signed logical delta.  Without that exact
        # spawn transition, retain the physical gesture-axis requirement.
        if (
            not boss_appeared
            and not post_combat_wave_appeared
            and abs(alignment) < 0.75
        ):
            raise SemanticGateClosed(
                "campaign map viewport did not align with the physical gesture axis"
            )
        residuals, root_mean_square_residual = self._campaign_projective_residuals(
            tuple(before_cells[node].point for node in ordered_nodes),
            tuple(after_cells[node].point for node in ordered_nodes),
        )
        maximum_residual = max(residuals)
        residual_limit = max(12.0, median_norm * 0.10)
        rms_limit = max(6.0, median_norm * 0.05)
        if maximum_residual > residual_limit or root_mean_square_residual > rms_limit:
            worst_index = residuals.index(maximum_residual)
            worst_node = ordered_nodes[worst_index]
            raise SemanticGateClosed(
                "campaign map viewport projective displacement is incoherent: "
                "median=({0:.3f},{1:.3f}), maximum_residual={2:.3f}, "
                "rms={3:.3f}, limits=({4:.3f},{5:.3f}), "
                "worst={6}:{7}, cells={8}".format(
                    median_dx,
                    median_dy,
                    maximum_residual,
                    root_mean_square_residual,
                    residual_limit,
                    rms_limit,
                    worst_node,
                    deltas[worst_index],
                    len(deltas),
                )
            )
        if any(dx * median_dx + dy * median_dy <= 0.0 for dx, dy in deltas):
            raise SemanticGateClosed(
                "campaign map viewport contains a contradictory cell displacement"
            )
        assert before_target.point is not None
        assert after_target.point is not None and after_target.bounds is not None
        if after_target.point == before_target.point:
            raise SemanticGateClosed("campaign map viewport target did not move")

        return CampaignMapViewportSwipeProof(
            semantic_id="campaign/map/viewport/" + target_node,
            target_node=target_node,
            pre_generation=state.generation,
            input_generation=input_generation,
            post_generation=post_state.generation,
            name=intent.name,
            grid_vector=intent.grid_vector,
            pixel_vector=intent.pixel_vector,
            start=start,
            end=end,
            duration_ms=duration_ms,
            coherent_cell_count=len(deltas),
            median_cell_delta=(median_dx, median_dy),
            maximum_delta_residual=maximum_residual,
            target_path=after_target.button_path,
            target_before_point=before_target.point,
            target_after_point=after_target.point,
            target_after_bounds=after_target.bounds,
            post_state=post_state,
        )

    def click_campaign_map_cell(
        self,
        state: CampaignMapState,
        node: str,
        *,
        allow_expected_enemy_coverage: bool = False,
    ) -> ActionReceipt:
        """Inject one exact map-cell tap after a fresh typed revalidation."""

        target = self.campaign_map_cell_input(
            state,
            node,
            allow_expected_enemy_coverage=allow_expected_enemy_coverage,
        )
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("foreground changed immediately before input")
        assert target.point is not None and target.bounds is not None
        self._tap(int(round(target.point.x)), int(round(target.point.y)))
        return ActionReceipt(
            semantic_id="campaign/map/grid/" + node,
            generation=self._last_generation or state.generation,
            point=target.point,
            bounds=target.bounds,
            path=target.path,
        )

    @staticmethod
    def _campaign_ambush_roots(state: OracleState) -> Tuple[str, ...]:
        roots = set()
        for button in state.buttons:
            if not button.active_in_hierarchy or not button.active_and_enabled:
                continue
            if button.name == "LevelAmbushView(Clone)" and button.path.endswith("/LevelAmbushView(Clone)"):
                roots.add(button.path)
            elif button.name in ("dodge_button", "fight_button") and button.path.endswith(
                "/LevelAmbushView(Clone)/window/" + button.name
            ):
                roots.add(button.path.rsplit("/window/", 1)[0])
        if len(roots) > 1:
            raise SemanticGateClosed("campaign ambush root is ambiguous")
        return tuple(roots)

    def _campaign_ambush_target(self, *, evade: bool) -> Optional[ButtonState]:
        """Return the exact live ambush action, including delegated Buttons."""

        if type(evade) is not bool:
            raise SemanticGateClosed("campaign ambush choice must be bool")
        state = self.read_state()
        roots = self._campaign_ambush_roots(state)
        if not roots:
            return None
        if len(roots) != 1:
            raise SemanticGateClosed("campaign ambush root is ambiguous")
        name = "dodge_button" if evade else "fight_button"
        target_path = roots[0] + "/window/" + name
        matches = tuple(
            button
            for button in state.buttons
            if button.name == name and button.path == target_path
        )
        if len(matches) != 1:
            raise SemanticGateClosed("campaign ambush action is absent or ambiguous")
        target = matches[0]
        if (
            not target.active_in_hierarchy
            or not target.active_and_enabled
            or not target.interactable
            or target.raycast_top is not True
            or target.point is None
            or target.bounds is None
            or not target.bounds.contains(target.point)
            or not (0 <= target.point.x < self.fingerprint.width)
            or not (0 <= target.point.y < self.fingerprint.height)
            or self._blocking_rules(state, "campaign/ambush/action")
        ):
            raise SemanticGateClosed("campaign ambush action is not actionable")
        return target

    def campaign_ambush_visible(self, *, evade: bool) -> bool:
        return self._campaign_ambush_target(evade=evade) is not None

    def campaign_ambush_present(self) -> bool:
        return bool(self._campaign_ambush_roots(self.read_state()))

    def campaign_ambush_notice(self) -> Optional[str]:
        ui = self.read_ui_state()
        path = "OverlayCamera/Overlay/UIOverlay/TipPanel(Clone)/Grid/toolTip(Clone)/Text"
        notices = [re.sub(r"<[^>]*>", "", t.text).strip() for t in ui.texts
                   if t.path.endswith(path) and t.active_in_hierarchy and not t.truncated]
        results = {"success" if t == "规避成功" else "failed" for t in notices
                   if t in ("规避成功", "规避失败")}
        if len(results) > 1:
            raise SemanticGateClosed("campaign ambush notices conflict")
        return next(iter(results)) if results else ("unknown" if notices else None)

    def click_campaign_ambush(self, *, evade: bool) -> ActionReceipt:
        target = self._campaign_ambush_target(evade=evade)
        if target is None:
            raise SemanticTargetMissing("campaign ambush action is absent")
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("foreground changed immediately before input")
        assert target.point is not None and target.bounds is not None
        self._tap(int(round(target.point.x)), int(round(target.point.y)))
        return ActionReceipt(
            semantic_id=(
                "campaign/ambush/evade" if evade else "campaign/ambush/fight"
            ),
            generation=self._last_generation or 0,
            point=target.point,
            bounds=target.bounds,
            path=target.path,
        )
