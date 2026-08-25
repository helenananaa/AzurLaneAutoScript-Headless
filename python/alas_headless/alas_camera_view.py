"""Typed Unity replacement for ALAS's campaign camera-detection input.

ALAS keeps ownership of ``Camera.update()``, its wait loop, swipe prediction,
camera-coordinate update, centering decision, and global-to-local conversion.
This module supplies only the ``View`` data that ALAS normally derives from a
screenshot: grid geometry, the grid containing ``SCREEN_CENTER``, fractional
center offset, and calibrated adjacent-cell distance.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Iterable, Optional, Sequence, Tuple

import numpy as np

from .semantic_oracle import (
    Bounds,
    CampaignMapCellState,
    CampaignMapState,
    Point,
    SemanticGateClosed,
)


def _node(location: Tuple[int, int]) -> str:
    column, row = location
    if not (0 <= column < 26 and 0 <= row < 99):
        raise SemanticGateClosed("semantic ALAS camera location is outside bounds")
    return chr(ord("A") + column) + str(row + 1)


def _location(value: Iterable[Any], label: str) -> Tuple[int, int]:
    try:
        result = tuple(int(item) for item in value)
    except (TypeError, ValueError) as exc:
        raise SemanticGateClosed(label + " is malformed") from exc
    if len(result) != 2:
        raise SemanticGateClosed(label + " is malformed")
    return result


@dataclass(frozen=True)
class AlasCampaignCameraViewObservation:
    generation: int
    stage_code: str
    camera_location: Tuple[int, int]
    camera_node: str
    center_offset: Tuple[float, float]
    swipe_base: Tuple[float, float]
    cell_count: int
    projective_maximum_residual: float
    projective_rms_residual: float
    target_node: Optional[str]
    target_local_location: Optional[Tuple[int, int]]
    target_path: Optional[str]
    target_point: Optional[Point]
    target_bounds: Optional[Bounds]


class _ProjectiveCameraModel:
    def __init__(
        self,
        *,
        homography: np.ndarray,
        source_center: np.ndarray,
        source_scale: float,
        target_center: np.ndarray,
        target_scale: float,
    ) -> None:
        self.homography = homography
        self.source_center = source_center
        self.source_scale = source_scale
        self.target_center = target_center
        self.target_scale = target_scale

    def grid_to_screen(self, points: Any) -> np.ndarray:
        values = np.asarray(points, dtype=float)
        if values.ndim != 2 or values.shape[1] != 2:
            raise SemanticGateClosed(
                "semantic ALAS camera grid projection is malformed"
            )
        normalized = (values - self.source_center) / self.source_scale
        homogeneous = np.column_stack(
            (normalized, np.ones(len(normalized), dtype=float))
        )
        projected = homogeneous @ self.homography.T
        if np.any(~np.isfinite(projected)) or np.any(
            np.abs(projected[:, 2]) < 0.10
        ):
            raise SemanticGateClosed(
                "semantic ALAS camera grid projection crosses infinity"
            )
        return (
            projected[:, :2] / projected[:, 2, None] * self.target_scale
            + self.target_center
        )


class _AffineCameraModel:
    """Exact affine projector for a proven single-row or single-column map."""

    def __init__(self, matrix: np.ndarray, offset: np.ndarray) -> None:
        self.matrix = matrix
        self.offset = offset

    def grid_to_screen(self, points: Any) -> np.ndarray:
        values = np.asarray(points, dtype=float)
        if values.ndim != 2 or values.shape[1] != 2:
            raise SemanticGateClosed(
                "semantic ALAS camera grid projection is malformed"
            )
        projected = values @ self.matrix.T + self.offset
        if np.any(~np.isfinite(projected)):
            raise SemanticGateClosed(
                "semantic ALAS camera affine projection is malformed"
            )
        return projected


class AlasSemanticCampaignGrid:
    """Native-shaped grid record backed by one exact Unity map-cell quad."""

    def __init__(
        self,
        cell: CampaignMapCellState,
        *,
        state: CampaignMapState,
        projector: Any,
    ) -> None:
        self.location = (cell.column - 1, cell.row - 1)
        self.corner = np.asarray(
            (
                (cell.bounds.left, cell.bounds.top),
                (cell.bounds.right, cell.bounds.top),
                (cell.bounds.left, cell.bounds.bottom),
                (cell.bounds.right, cell.bounds.bottom),
            ),
            dtype=float,
        )
        self.button = (
            cell.bounds.left,
            cell.bounds.top,
            cell.bounds.right,
            cell.bounds.bottom,
        )
        self.is_mechanism_trigger = False
        self.mechanism_wait = 0
        self.semantic_path = cell.button_path
        self.semantic_point = cell.point
        self.semantic_bounds = cell.bounds
        self._projector = projector
        enemy = next((item for item in state.enemies if item.node == cell.node), None)
        fleet = next((item for item in state.fleets if item.node == cell.node), None)
        pickup = next((item for item in state.pickups if item.node == cell.node), None)
        self.is_enemy = enemy is not None
        self.is_siren = bool(
            enemy is not None and "siren" in enemy.genre.lower()
        )
        self.is_boss = bool(
            enemy is not None and "boss" in enemy.genre.lower()
        )
        self.is_mystery = bool(
            pickup is not None and pickup.kind.lower() == "mystery"
        )
        self.is_ammo = bool(
            pickup is not None and pickup.kind.lower() == "ammo"
        )
        self.is_fleet = fleet is not None
        self.is_current_fleet = bool(
            fleet is not None and fleet.marker == state.current_fleet_marker
        )
        # ``CampaignMap.update`` passes every detected grid through
        # ``GridInfo.merge``.  Keep the typed record structurally compatible
        # with every field that merge reads, using conservative false/empty
        # defaults for categories the observer did not prove.
        self.is_submarine = False
        self.is_caught_by_siren = False
        self.is_carrier = False
        self.is_missile_attack = False
        self.enemy_scale = int(enemy.scale) if enemy is not None else 0
        self.enemy_genre = enemy.genre if enemy is not None else None
        self.outer = self.button

    @property
    def str(self) -> str:
        if self.is_boss:
            return "BO"
        if self.is_siren:
            return "SI"
        if self.is_enemy:
            return "EN"
        if self.is_current_fleet:
            return "FL"
        if self.is_fleet:
            return "Fl"
        if self.is_mystery:
            return "MY"
        if self.is_ammo:
            return "AM"
        return "--"

    def grid2screen(self, points: Any) -> np.ndarray:
        return self._projector.grid_to_screen(
            np.asarray(points, dtype=float) + np.asarray(self.location, dtype=float)
        )

    def predict_fleet(self) -> bool:
        return self.is_fleet

    def predict_current_fleet(self) -> bool:
        return self.is_current_fleet

    def predict_submarine(self) -> bool:
        return False


class _AlasSemanticGridSelection:
    def __init__(self, grids: Iterable[AlasSemanticCampaignGrid]) -> None:
        self.grids = list(grids)

    def __iter__(self):
        return iter(self.grids)

    def add(self, other: Any) -> "_AlasSemanticGridSelection":
        if not isinstance(other, _AlasSemanticGridSelection):
            raise SemanticGateClosed("semantic ALAS camera selection is malformed")
        unique = list(self.grids)
        for grid in other.grids:
            if grid not in unique:
                unique.append(grid)
        return _AlasSemanticGridSelection(unique)


class AlasSemanticCampaignView:
    """Small ``View``-compatible typed observation consumed by ALAS Camera."""

    def __init__(
        self,
        *,
        state: CampaignMapState,
        observation: AlasCampaignCameraViewObservation,
        projector: Any,
    ) -> None:
        self.semantic_state = state
        self.semantic_observation = observation
        self.grids = {
            (cell.column - 1, cell.row - 1): AlasSemanticCampaignGrid(
                cell, state=state, projector=projector
            )
            for cell in state.cells
        }
        if len(self.grids) != len(state.cells):
            raise SemanticGateClosed("semantic ALAS camera view has duplicate cells")
        self.shape = np.asarray((state.columns - 1, state.rows - 1), dtype=int)
        self.center_loca = observation.camera_location
        self.center_offset = np.asarray(observation.center_offset, dtype=float)
        self.swipe_base = np.asarray(observation.swipe_base, dtype=float)
        column, row = observation.camera_location
        self.left_edge = column == 0
        self.right_edge = column == state.columns - 1
        self.lower_edge = row == 0
        self.upper_edge = row == state.rows - 1

    def __iter__(self):
        return iter(self.grids.values())

    def __contains__(self, item: Iterable[Any]) -> bool:
        return _location(item, "semantic ALAS camera lookup") in self.grids

    def __getitem__(self, item: Iterable[Any]) -> AlasSemanticCampaignGrid:
        key = _location(item, "semantic ALAS camera lookup")
        try:
            return self.grids[key]
        except KeyError as exc:
            raise SemanticGateClosed(
                "ALAS camera requested a cell outside the typed view"
            ) from exc

    def predict(self) -> None:
        # Enemy/fleet classification already entered ALAS through the typed map
        # projection.  Screenshot pixel prediction is intentionally absent.
        return None

    def show(self) -> None:
        return None

    def select(self, **kwargs: Any) -> _AlasSemanticGridSelection:
        return _AlasSemanticGridSelection(
            grid
            for grid in self
            if all(getattr(grid, name, None) == value for name, value in kwargs.items())
        )

    def predict_swipe(
        self,
        current: Any,
        *,
        with_current_fleet: bool = True,
        with_sea_grids: bool = True,
    ) -> Tuple[int, int]:
        del with_current_fleet, with_sea_grids
        if not isinstance(current, AlasSemanticCampaignView):
            raise SemanticGateClosed("ALAS camera swipe prediction lost typed view")
        before = self.semantic_observation
        after = current.semantic_observation
        before_signature = self.semantic_state.signature
        after_signature = current.semantic_state.signature
        before_enemies = set(self.semantic_state.enemies)
        after_enemies = set(current.semantic_state.enemies)
        added_enemies = after_enemies - before_enemies
        removed_enemies = before_enemies - after_enemies
        additive_boss = (
            before_signature[:6] + before_signature[7:]
            == after_signature[:6] + after_signature[7:]
            and not removed_enemies
            and len(added_enemies) == 1
            and next(iter(added_enemies)).genre == "Boss"
        )
        before_fleets = {
            fleet.marker: fleet for fleet in self.semantic_state.fleets
        }
        after_fleets = {
            fleet.marker: fleet for fleet in current.semantic_state.fleets
        }
        current_marker = current.semantic_state.current_fleet_marker
        before_fleet = before_fleets.get(current_marker)
        after_fleet = after_fleets.get(current_marker)
        same_static_state = (
            before_signature[:5] == after_signature[:5]
            and before_signature[7:] == after_signature[7:]
        )
        post_combat_wave = bool(
            same_static_state
            and before_fleet is not None
            and after_fleet is not None
            and set(before_fleets) == set(after_fleets)
            and all(
                before_fleets[marker] == after_fleets[marker]
                for marker in before_fleets
                if marker != current_marker
            )
            and before_fleet.node != after_fleet.node
            and after_fleet.ammo == max(0, before_fleet.ammo - 1)
            and after_fleet.ammo_capacity == before_fleet.ammo_capacity
            and len(removed_enemies) == 1
            and next(iter(removed_enemies)).node == after_fleet.node
            and all(not enemy.fighting for enemy in added_enemies)
        )
        if (
            (
                before_signature != after_signature
                and not additive_boss
                and not post_combat_wave
            )
            or after.generation <= before.generation
        ):
            raise SemanticGateClosed("ALAS camera swipe prediction changed map state")
        delta = tuple(
            after.camera_location[index] - before.camera_location[index]
            for index in range(2)
        )
        # ALAS requests at most (4, 3), but Unity clamps the camera at a map
        # edge after applying the fractional center correction.  The observed
        # logical delta can therefore be one cell larger on either axis.
        if delta == (0, 0):
            active_axes = tuple(
                index
                for index, limit in enumerate(
                    (current.semantic_state.columns, current.semantic_state.rows)
                )
                if limit > 1
            )
            fractional_delta = float(
                np.linalg.norm(
                    np.asarray(
                        [after.center_offset[index] for index in active_axes]
                    )
                    - np.asarray(
                        [before.center_offset[index] for index in active_axes]
                    )
                )
            )
            # A large requested swipe can be clamped against a map edge while
            # still moving every projected cell by a coherent fraction of one
            # grid unit.  The typed viewport proof already verifies that
            # physical displacement; preserve ALAS's integer camera location
            # for this bounded fractional-edge case.  A true no-op is also
            # valid when the exact requested target remains at the identical
            # in-screen point; the owning oracle has separately required it
            # to be the unique top raycast after the edge-clamped gesture.
            stable_target = bool(
                post_combat_wave
                or (
                    after.target_node is not None
                    and (
                        before.target_node is None
                        or (
                            before.target_node == after.target_node
                            and before.target_path == after.target_path
                            and before.target_point == after.target_point
                            and before.target_bounds == after.target_bounds
                        )
                    )
                    and after.target_point is not None
                    and after.target_bounds is not None
                    and after.target_bounds.contains(after.target_point)
                )
            )
            # A camera gesture is already committed before this postcondition
            # runs, and Unity may clamp it to an arbitrarily small coherent
            # displacement at a map edge.  Requiring a minimum of 0.05 cells
            # cannot prevent an unsafe swipe; it only rejects a valid typed
            # post-state.  Preserve the upper bound and reject a true no-op
            # unless the exact target stayed stable.
            if not (0.0 < fractional_delta <= 0.75 or stable_target):
                raise SemanticGateClosed(
                    "ALAS camera observed swipe is outside limits"
                )
        elif abs(delta[0]) > 5 or abs(delta[1]) > 4:
            raise SemanticGateClosed("ALAS camera observed swipe is outside limits")
        return delta


def _fit_projective_camera(
    state: CampaignMapState,
    screen_center: Tuple[float, float],
) -> Tuple[Tuple[float, float], float, float, Any]:
    source = np.asarray(
        [(cell.column - 0.5, cell.row - 0.5) for cell in state.cells],
        dtype=float,
    )
    target = np.asarray(
        [(cell.point.x, cell.point.y) for cell in state.cells], dtype=float
    )
    if state.rows == 1 or state.columns == 1:
        if len(source) < 3 or (state.rows == 1 and state.columns == 1):
            raise SemanticGateClosed(
                "semantic ALAS camera linear map needs at least three cells"
            )
        varying_axis = 0 if state.rows == 1 else 1
        fixed_axis = 1 - varying_axis
        coordinate = source[:, varying_axis]
        design = np.column_stack((coordinate, np.ones(len(coordinate))))
        coefficients, _, rank, _ = np.linalg.lstsq(design, target, rcond=None)
        if rank != 2:
            raise SemanticGateClosed("semantic ALAS camera linear model is singular")
        direction = coefficients[0]
        intercept = coefficients[1]
        direction_length = float(np.linalg.norm(direction))
        if not 40.0 <= direction_length <= 240.0:
            raise SemanticGateClosed(
                "semantic ALAS camera linear cell spread is outside limits"
            )
        perpendicular = np.asarray((-direction[1], direction[0]), dtype=float)
        perpendicular /= float(np.linalg.norm(perpendicular))
        if perpendicular[1] < 0.0:
            perpendicular *= -1.0
        bounds_scale = float(
            np.median(
                np.asarray(
                    [
                        (cell.bounds.bottom - cell.bounds.top)
                        if state.rows == 1
                        else (cell.bounds.right - cell.bounds.left)
                        for cell in state.cells
                    ],
                    dtype=float,
                )
            )
        )
        if not 40.0 <= bounds_scale <= 240.0:
            raise SemanticGateClosed(
                "semantic ALAS camera linear cross-axis is outside limits"
            )
        cross_direction = perpendicular * bounds_scale
        matrix = np.empty((2, 2), dtype=float)
        matrix[:, varying_axis] = direction
        matrix[:, fixed_axis] = cross_direction
        fixed_value = float(source[0, fixed_axis])
        offset = intercept - cross_direction * fixed_value
        determinant = float(np.linalg.det(matrix))
        if not math.isfinite(determinant) or abs(determinant) < 1e-4:
            raise SemanticGateClosed("semantic ALAS camera linear model collapses")
        projector = _AffineCameraModel(matrix, offset)
        predicted = projector.grid_to_screen(source)
        residuals = np.linalg.norm(predicted - target, axis=1)
        maximum_residual = float(np.max(residuals))
        rms_residual = float(np.sqrt(np.mean(residuals ** 2)))
        if maximum_residual > 2.0 or rms_residual > 1.0:
            raise SemanticGateClosed(
                "semantic ALAS camera linear geometry is incoherent"
            )
        continuous = np.linalg.solve(
            matrix, np.asarray(screen_center, dtype=float) - offset
        )
        if np.any(~np.isfinite(continuous)):
            raise SemanticGateClosed("semantic ALAS camera screen center is singular")
        return (
            (float(continuous[0]), float(continuous[1])),
            maximum_residual,
            rms_residual,
            projector,
        )
    if len(source) < 8:
        raise SemanticGateClosed("semantic ALAS camera needs at least eight cells")

    def normalize(points: np.ndarray):
        center = points.mean(axis=0)
        scale = float(np.sqrt(np.mean(np.sum((points - center) ** 2, axis=1))))
        if not math.isfinite(scale) or scale < 1.0:
            raise SemanticGateClosed("semantic ALAS camera cell spread is degenerate")
        return (points - center) / scale, center, scale

    normalized_source, source_center, source_scale = normalize(source)
    normalized_target, target_center, target_scale = normalize(target)
    rows = []
    outputs = []
    for (x, y), (u, v) in zip(normalized_source, normalized_target):
        rows.append((x, y, 1.0, 0.0, 0.0, 0.0, -u * x, -u * y))
        outputs.append(u)
        rows.append((0.0, 0.0, 0.0, x, y, 1.0, -v * x, -v * y))
        outputs.append(v)
    matrix = np.asarray(rows, dtype=float)
    values = np.asarray(outputs, dtype=float)
    parameters, _, rank, singular_values = np.linalg.lstsq(
        matrix, values, rcond=None
    )
    if rank != 8 or len(singular_values) != 8:
        raise SemanticGateClosed("semantic ALAS camera projective model is singular")
    if singular_values[-1] <= 0.0 or singular_values[0] / singular_values[-1] > 1e8:
        raise SemanticGateClosed(
            "semantic ALAS camera projective model is ill-conditioned"
        )
    homography = np.append(parameters, 1.0).reshape(3, 3)
    determinant = float(np.linalg.det(homography))
    if not math.isfinite(determinant) or abs(determinant) < 1e-4:
        raise SemanticGateClosed("semantic ALAS camera projective model collapses")

    predicted = []
    for x, y in normalized_source:
        value = homography @ np.asarray((x, y, 1.0), dtype=float)
        if not np.all(np.isfinite(value)) or abs(value[2]) < 0.10:
            raise SemanticGateClosed(
                "semantic ALAS camera projective model crosses infinity"
            )
        predicted.append(value[:2] / value[2] * target_scale + target_center)
    residuals = np.linalg.norm(np.asarray(predicted) - target, axis=1)
    maximum_residual = float(np.max(residuals))
    rms_residual = float(np.sqrt(np.mean(residuals ** 2)))
    if maximum_residual > 2.0 or rms_residual > 1.0:
        raise SemanticGateClosed(
            "semantic ALAS camera projective geometry is incoherent"
        )

    normalized_screen = (
        np.asarray(screen_center, dtype=float) - target_center
    ) / target_scale
    inverse = np.linalg.inv(homography)
    continuous = inverse @ np.asarray(
        (normalized_screen[0], normalized_screen[1], 1.0), dtype=float
    )
    if not np.all(np.isfinite(continuous)) or abs(continuous[2]) < 0.10:
        raise SemanticGateClosed("semantic ALAS camera screen center is singular")
    continuous = continuous[:2] / continuous[2] * source_scale + source_center
    model = _ProjectiveCameraModel(
        homography=homography,
        source_center=source_center,
        source_scale=source_scale,
        target_center=target_center,
        target_scale=target_scale,
    )
    return (
        (float(continuous[0]), float(continuous[1])),
        maximum_residual,
        rms_residual,
        model,
    )


def build_alas_campaign_camera_view(
    state: CampaignMapState,
    *,
    screen_center: Sequence[float],
    target_node: Optional[str] = None,
) -> AlasSemanticCampaignView:
    """Convert one stable typed map into the screenshot-equivalent ALAS View."""

    if not isinstance(state, CampaignMapState):
        raise SemanticGateClosed("semantic ALAS camera requires a typed map state")
    try:
        exact_center = tuple(float(item) for item in screen_center)
    except (TypeError, ValueError) as exc:
        raise SemanticGateClosed("semantic ALAS camera screen center is malformed") from exc
    if (
        len(exact_center) != 2
        or any(not math.isfinite(item) for item in exact_center)
        or not (0.0 <= exact_center[0] < 1280.0)
        or not (0.0 <= exact_center[1] < 720.0)
    ):
        raise SemanticGateClosed("semantic ALAS camera screen center is malformed")

    continuous, maximum_residual, rms_residual, projector = _fit_projective_camera(
        state, exact_center
    )
    # Unity can overscroll the perspective camera slightly beyond a map edge
    # while the edge cells remain coherent and actionable.  Clamp only that
    # sub-cell overshoot back to the logical edge; reject larger excursions.
    adjusted = list(continuous)
    for axis, limit in enumerate((state.columns, state.rows)):
        if -1.0 < adjusted[axis] < 0.0:
            adjusted[axis] = 0.0
        elif limit - 1.0 <= adjusted[axis] < limit:
            pass
        elif limit <= adjusted[axis] < limit + 1.0:
            adjusted[axis] = math.nextafter(float(limit), 0.0)
    continuous = (adjusted[0], adjusted[1])
    camera = (math.floor(continuous[0]), math.floor(continuous[1]))
    center_offset = (
        continuous[0] - camera[0],
        continuous[1] - camera[1],
    )
    if not (
        0 <= camera[0] < state.columns
        and 0 <= camera[1] < state.rows
        and all(0.0 <= value < 1.0 for value in center_offset)
    ):
        raise SemanticGateClosed(
            "semantic ALAS camera edge observation is not qualified"
        )

    indexed = {(cell.row, cell.column): cell for cell in state.cells}
    horizontal = []
    vertical = []
    for (row, column), cell in indexed.items():
        right = indexed.get((row, column + 1))
        below = indexed.get((row + 1, column))
        if right is not None:
            horizontal.append(
                math.hypot(
                    right.point.x - cell.point.x,
                    right.point.y - cell.point.y,
                )
            )
        if below is not None:
            vertical.append(
                math.hypot(
                    below.point.x - cell.point.x,
                    below.point.y - cell.point.y,
                )
            )
    if not horizontal and state.columns == 1:
        horizontal = [
            cell.bounds.right - cell.bounds.left for cell in state.cells
        ]
    if not vertical and state.rows == 1:
        vertical = [
            cell.bounds.bottom - cell.bounds.top for cell in state.cells
        ]
    if not horizontal or not vertical:
        raise SemanticGateClosed("semantic ALAS camera swipe base is incomplete")
    swipe_base = (
        float(np.median(np.asarray(horizontal, dtype=float))),
        float(np.median(np.asarray(vertical, dtype=float))),
    )
    if any(not 40.0 <= value <= 240.0 for value in swipe_base):
        raise SemanticGateClosed("semantic ALAS camera swipe base is outside limits")

    target = None
    if target_node is not None:
        matches = tuple(cell for cell in state.cells if cell.node == target_node)
        if len(matches) != 1:
            raise SemanticGateClosed("semantic ALAS camera target is absent")
        target = matches[0]
    observation = AlasCampaignCameraViewObservation(
        generation=state.generation,
        stage_code=state.stage_code,
        camera_location=camera,
        camera_node=_node(camera),
        center_offset=center_offset,
        swipe_base=swipe_base,
        cell_count=len(state.cells),
        projective_maximum_residual=maximum_residual,
        projective_rms_residual=rms_residual,
        target_node=target_node,
        target_local_location=(
            None if target is None else (target.column - 1, target.row - 1)
        ),
        target_path=None if target is None else target.button_path,
        target_point=None if target is None else target.point,
        target_bounds=None if target is None else target.bounds,
    )
    return AlasSemanticCampaignView(
        state=state, observation=observation, projector=projector
    )


def install_alas_campaign_camera_view(
    campaign: Any,
    state: CampaignMapState,
    *,
    target_node: Optional[str] = None,
) -> AlasCampaignCameraViewObservation:
    """Install one typed View at ALAS's existing ``_update_view`` boundary."""

    config = getattr(campaign, "config", None)
    if config is None or not hasattr(config, "SCREEN_CENTER"):
        raise SemanticGateClosed("ALAS campaign camera config is incomplete")
    view = build_alas_campaign_camera_view(
        state,
        screen_center=config.SCREEN_CENTER,
        target_node=target_node,
    )
    campaign.view = view
    # Camera._update_view_data() applies a pending ALAS swipe to the previous
    # camera coordinate.  Seed the coordinate only when no swipe is awaiting
    # that native reconciliation, otherwise the delta would be applied twice.
    if getattr(campaign, "_prev_view", None) is None:
        campaign.camera = view.semantic_observation.camera_location
    campaign.semantic_camera_view_observation = view.semantic_observation
    return view.semantic_observation
