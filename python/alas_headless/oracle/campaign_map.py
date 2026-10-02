"""Campaign map for the typed ALAS boundary."""

from __future__ import annotations

import re
from typing import Dict, Mapping, Tuple
from .contracts import (
    CampaignMapCellState,
    CampaignMapEnemyState,
    CampaignMapFleetState,
    CampaignMapSubmarineState,
    CampaignMapPickupState,
    CampaignMapState,
)
from .errors import SemanticGateClosed


class CampaignMapOracle:
    """Campaign map operations sharing the oracle frame and input boundary."""

    def _campaign_map_state_once(
        self,
        stage_code: str,
        *,
        columns: int,
        rows: int,
        land: Tuple[Tuple[int, int], ...],
        expected_fleet_count: int,
        allow_deployment: bool = False,
    ) -> CampaignMapState:
        button_state = self.read_state()
        ui_state = self.read_ui_state()
        entry = self._campaign_map_entry_state_from_snapshots(button_state, ui_state, allow_deployment=allow_deployment)
        if ui_state.image_truncated:
            raise SemanticGateClosed("campaign map Image snapshot is truncated")

        grid_root = entry.root_path
        cell_pattern = re.compile(
            re.escape(grid_root)
            + r"/DragLayer/plane/quads/chapter_cell_quad_([0-9]+)_([0-9]+)$"
        )
        expected_cells = {
            (row, column)
            for row in range(1, rows + 1)
            for column in range(1, columns + 1)
            if (row, column) not in land
        }
        raw_coordinates = tuple(
            (int(match.group(1)), int(match.group(2)))
            for button in button_state.buttons
            for match in (cell_pattern.fullmatch(button.path),)
            if match is not None
        )
        # Unity may center small campaign maps inside a larger backing grid.
        # Derive one exact row/column translation from the complete topology
        # instead of assuming normal stages are already one-based (1-1 is
        # exposed as raw row 4 while remaining logical row 1).
        coordinate_offsets = tuple(
            (row_offset, column_offset)
            for row_offset, column_offset in {
                (expected_row - raw_row, expected_column - raw_column)
                for raw_row, raw_column in raw_coordinates
                for expected_row, expected_column in expected_cells
            }
            if {
                (raw_row + row_offset, raw_column + column_offset)
                for raw_row, raw_column in raw_coordinates
            }
            == expected_cells
        )
        if len(coordinate_offsets) != 1:
            raise SemanticGateClosed("campaign map grid topology disagrees with ALAS")
        row_offset, column_offset = coordinate_offsets[0]

        def logical_coordinate(raw_row: int, raw_column: int) -> Tuple[int, int]:
            row = raw_row + row_offset
            column = raw_column + column_offset
            if row < 1 or column < 1:
                raise SemanticGateClosed("campaign map grid topology is invalid")
            return row, column

        cells_by_coordinate: Dict[Tuple[int, int], CampaignMapCellState] = {}
        cell_world_positions: Dict[Tuple[int, int], Tuple[float, float, float]] = {}
        for button in button_state.buttons:
            match = cell_pattern.fullmatch(button.path)
            if match is None:
                continue
            raw_row, raw_column = (int(match.group(1)), int(match.group(2)))
            row, column = logical_coordinate(raw_row, raw_column)
            coordinate = (row, column)
            if (
                coordinate in cells_by_coordinate
                or row > rows
                or column > columns
                or not button.active_in_hierarchy
                or not button.active_and_enabled
                or not button.interactable
                or button.point is None
                or button.bounds is None
                or not button.bounds.contains(button.point)
            ):
                raise SemanticGateClosed("campaign map grid topology is invalid")
            world_value = button.raw.get("world_position")
            if not isinstance(world_value, Mapping):
                raise SemanticGateClosed("campaign map grid world position is absent")
            cell_world_positions[coordinate] = tuple(
                self._finite_number(
                    world_value.get(axis), "campaign map grid world position." + axis
                )
                for axis in ("x", "y", "z")
            )
            cells_by_coordinate[coordinate] = CampaignMapCellState(
                row=row,
                column=column,
                node=self._campaign_map_node(row, column),
                button_path=button.path,
                point=button.point,
                bounds=button.bounds,
            )
        if set(cells_by_coordinate) != expected_cells:
            raise SemanticGateClosed("campaign map grid topology disagrees with ALAS")

        active_images = tuple(
            image
            for image in ui_state.images
            if image.active_in_hierarchy
            and image.active_and_enabled
            and not image.truncated
        )
        active_texts = tuple(
            item
            for item in ui_state.texts
            if item.active_in_hierarchy
            and item.active_and_enabled
            and not item.truncated
        )
        cell_root = grid_root + "/DragLayer/plane/cells/"
        attachment_pattern = re.compile(
            re.escape(cell_root) + r"chapter_cell_([0-9]+)_([0-9]+)/attachment/([^/]+)"
        )
        attachment_roots = set()
        for item in (*active_images, *active_texts):
            match = attachment_pattern.match(item.path)
            if match is not None:
                row, column = logical_coordinate(
                    int(match.group(1)), int(match.group(2))
                )
                attachment_roots.add((row, column, match.group(3)))

        enemy_icon_pattern = re.compile(
            re.escape(cell_root)
            + r"chapter_cell_([0-9]+)_([0-9]+)/attachment/"
            + r"enemy_([1-9][0-9]*)/icon$"
        )
        # The game exposes both light-cruiser (qx, 轻巡) and destroyer
        # (qz, 驱逐) pieces.  ALAS intentionally groups both under its
        # existing Light enemy genre.
        genre_names = {
            "qx": "Light",
            "qz": "Light",
            "zl": "Main",
            "hm": "Carrier",
            "ys": "Treasure",
        }
        enemies = []
        enemy_roots = set()
        cleared_enemy_roots = set()
        for image in active_images:
            match = enemy_icon_pattern.fullmatch(image.path)
            if match is None:
                continue
            raw_row, raw_column, object_id = map(int, match.groups())
            row, column = logical_coordinate(raw_row, raw_column)
            coordinate = (row, column)
            root_name = "enemy_{0}".format(object_id)
            root = cell_root + "chapter_cell_{0}_{1}/attachment/{2}".format(
                raw_row, raw_column, root_name
            )
            # The current 2026 event uses an ``sr`` art-family prefix for
            # otherwise ordinary size/genre enemy pieces (for example
            # ``srhm3`` on static and movable Carrier nodes).  Siren identity
            # remains a separate typed-node contract; this prefix alone must
            # never set ``is_siren``.
            sprite_match = re.fullmatch(r"(?:sr)?(qx|qz|zl|hm|ys)([123])", image.sprite)
            emotion_match = re.fullmatch(r"(?:emotion_|ghost)(qx|qz|zl|hm|ys)", image.sprite)
            cleared_sprite_match = re.fullmatch(
                r"(?:(?:sr)?(?:qx|qz|zl|hm|ys)[123]|(?:emotion_|ghost)(?:qx|qz|zl|hm|ys))_d_blue",
                image.sprite,
            )
            boss_title_images = tuple(
                item
                for item in active_images
                if item.path == root + "/titleContain/bg_boss"
            )
            boss_marker = bool(
                image.sprite == "bossicon"
                or (
                    emotion_match is not None
                    and len(boss_title_images) == 1
                    and boss_title_images[0].sprite == "enemy_boss"
                )
            )
            if cleared_sprite_match is not None:
                cleared_details = tuple(
                    item
                    for item in (*active_images, *active_texts)
                    if item.path.startswith(root + "/")
                    and (
                        item.path.startswith(root + "/lv/")
                        or item.path == root + "/fighting"
                        or item.path == root + "/fighting/Text"
                    )
                )
                if (
                    coordinate not in expected_cells
                    or (row, column, root_name) in cleared_enemy_roots
                    or image.bounds is None
                    or cleared_details
                ):
                    raise SemanticGateClosed(
                        "campaign map cleared-enemy identity is unsupported"
                    )
                cleared_enemy_roots.add((row, column, root_name))
                continue
            if (
                coordinate not in expected_cells
                or (row, column, root_name) in enemy_roots
                or (sprite_match is None and emotion_match is None and not boss_marker)
                or image.bounds is None
                or (
                    boss_marker
                    and (
                        len(boss_title_images) != 1
                        or boss_title_images[0].sprite != "enemy_boss"
                    )
                )
                or (not boss_marker and boss_title_images)
            ):
                raise SemanticGateClosed("campaign map enemy identity is unsupported")
            level_matches = tuple(
                item for item in active_texts if item.path == root + "/lv/Text"
            )
            label_matches = tuple(
                item for item in active_texts if item.path == root + "/lv/lv_label"
            )
            fighting_images = tuple(
                item for item in active_images if item.path == root + "/fighting"
            )
            fighting_texts = tuple(
                item for item in active_texts if item.path == root + "/fighting/Text"
            )
            if (
                len(level_matches) != 1
                or re.fullmatch(r"[1-9][0-9]{0,2}", level_matches[0].text.strip())
                is None
                or len(label_matches) != 1
                or label_matches[0].text.strip() != "Lv."
                or bool(fighting_images) != bool(fighting_texts)
                or (fighting_images and len(fighting_images) != 1)
                or (fighting_texts and len(fighting_texts) != 1)
                or (
                    fighting_images
                    and (
                        fighting_images[0].sprite != "xingdongzhong"
                        or fighting_texts[0].text.strip() != "行动中"
                    )
                )
            ):
                raise SemanticGateClosed("campaign map enemy details are incomplete")
            if boss_marker:
                sprite = image.sprite
                scale = 0
                genre = "Boss"
            elif emotion_match is not None:
                size_matches = tuple(
                    item
                    for item in active_images
                    if item.path == root + "/random_buff_container/1"
                )
                size_by_sprite = {"xiao": 1, "zhong": 2, "da": 3}
                if (
                    len(size_matches) != 1
                    or size_matches[0].sprite not in size_by_sprite
                    or size_matches[0].bounds is None
                ):
                    raise SemanticGateClosed(
                        "campaign map event-enemy size identity is unsupported"
                    )
                sprite = image.sprite
                scale = size_by_sprite[size_matches[0].sprite]
                genre = genre_names[emotion_match.group(1)]
            else:
                prefix, scale_text = sprite_match.groups()
                sprite = image.sprite
                scale = int(scale_text)
                genre = genre_names[prefix]
            enemies.append(
                CampaignMapEnemyState(
                    row=row,
                    column=column,
                    node=self._campaign_map_node(row, column),
                    object_id=object_id,
                    sprite=sprite,
                    scale=scale,
                    genre=genre,
                    level=int(level_matches[0].text.strip()),
                    fighting=bool(fighting_images),
                )
            )
            enemy_roots.add((row, column, root_name))

        champion_icon_pattern = re.compile(
            re.escape(cell_root) + r"(cell_champion_emotion_(qx|qz|zl|hm))/icon$"
        )
        champion_roots = set()
        for image in active_images:
            match = champion_icon_pattern.fullmatch(image.path)
            if match is None:
                continue
            root_name, prefix = match.groups()
            root = cell_root + root_name
            if root_name in champion_roots or image.bounds is None:
                raise SemanticGateClosed(
                    "campaign map elite-enemy identity is unsupported"
                )
            title_matches = tuple(
                item
                for item in active_images
                if item.path == root + "/titleContain/bg_boss"
            )
            level_matches = tuple(
                item for item in active_texts if item.path == root + "/lv/Text"
            )
            label_matches = tuple(
                item for item in active_texts if item.path == root + "/lv/lv_label"
            )
            fighting_images = tuple(
                item for item in active_images if item.path == root + "/fighting"
            )
            fighting_texts = tuple(
                item for item in active_texts if item.path == root + "/fighting/Text"
            )
            matched_cells = tuple(
                cell
                for cell in cells_by_coordinate.values()
                if image.bounds.contains(cell.point)
            )
            if (
                image.sprite != "emotion_" + prefix
                or len(title_matches) != 1
                or title_matches[0].sprite != "enemy_elite"
                or title_matches[0].bounds is None
                or len(level_matches) != 1
                or re.fullmatch(r"[1-9][0-9]{0,2}", level_matches[0].text.strip())
                is None
                or len(label_matches) != 1
                or label_matches[0].text.strip() != "Lv."
                or len(matched_cells) != 1
                or bool(fighting_images) != bool(fighting_texts)
                or (fighting_images and len(fighting_images) != 1)
                or (fighting_texts and len(fighting_texts) != 1)
                or (
                    fighting_images
                    and (
                        fighting_images[0].sprite != "xingdongzhong"
                        or fighting_texts[0].text.strip() != "行动中"
                    )
                )
            ):
                raise SemanticGateClosed(
                    "campaign map elite-enemy details are incomplete"
                )
            matched_cell = matched_cells[0]
            if any(enemy.node == matched_cell.node for enemy in enemies):
                raise SemanticGateClosed(
                    "campaign map elite-enemy location is ambiguous"
                )
            enemies.append(
                CampaignMapEnemyState(
                    row=matched_cell.row,
                    column=matched_cell.column,
                    node=matched_cell.node,
                    object_id=0,
                    sprite=image.sprite,
                    scale=0,
                    genre="Siren",
                    level=int(level_matches[0].text.strip()),
                    fighting=bool(fighting_images),
                    is_siren=True,
                )
            )
            champion_roots.add(root_name)

        pickups = []
        supply_roots = set()
        supply_pattern = re.compile(
            re.escape(cell_root)
            + r"chapter_cell_([0-9]+)_([0-9]+)/attachment/"
            + r"supply/Tpl_Supply\(Clone\)/normal$"
        )
        for image in active_images:
            match = supply_pattern.fullmatch(image.path)
            if match is None:
                continue
            raw_row, raw_column = map(int, match.groups())
            row, column = logical_coordinate(raw_row, raw_column)
            if (
                (row, column) not in expected_cells
                or (row, column, "supply") in supply_roots
                or image.sprite != "event4"
                or image.bounds is None
            ):
                raise SemanticGateClosed("campaign map pickup identity is unsupported")
            pickups.append(
                CampaignMapPickupState(
                    row=row,
                    column=column,
                    node=self._campaign_map_node(row, column),
                    kind="ammo",
                    sprite=image.sprite,
                )
            )
            supply_roots.add((row, column, "supply"))
        if attachment_roots != enemy_roots | cleared_enemy_roots | supply_roots:
            raise SemanticGateClosed("campaign map contains an unsupported attachment")

        submarine_destination_node = None
        if allow_deployment:
            destination_pattern = re.compile(re.escape(cell_root) + r'chapter_cell_([0-9]+)_([0-9]+)/Tpl_Destination_Mark\(Clone\)$')
            destinations = [image for image in active_images if destination_pattern.fullmatch(image.path)
                            and image.sprite == 'destination_mark']
            if len(destinations) > 1:
                raise SemanticGateClosed('submarine destination is ambiguous')
            if destinations:
                match = destination_pattern.fullmatch(destinations[0].path)
                row, column = logical_coordinate(int(match.group(1)), int(match.group(2)))
                if (row, column) not in cells_by_coordinate:
                    raise SemanticGateClosed('submarine destination is outside ALAS topology')
                submarine_destination_node = cells_by_coordinate[(row, column)].node
        fleet_marker_pattern = re.compile(
            re.escape(cell_root) + r"(cell_fleet_[A-Za-z0-9_]+)/"
        )
        fleet_markers = {
            match.group(1)
            for item in (*active_images, *active_texts)
            for match in (fleet_marker_pattern.match(item.path),)
            if match is not None
        }
        submarine_markers = {marker for marker in fleet_markers if any(
            image.path == cell_root + marker + '/mark' and image.sprite == 'qianting_icon'
            for image in active_images)}
        if len(submarine_markers) > 1:
            raise SemanticGateClosed('campaign submarine identity is ambiguous')
        all_fleet_markers = fleet_markers
        fleet_markers = fleet_markers - submarine_markers
        if len(fleet_markers) != expected_fleet_count:
            raise SemanticGateClosed("campaign map fleet count is unexpected")
        fleets = []
        submarine = None
        occupied_nodes = set()
        for marker in sorted(all_fleet_markers):
            root = cell_root + marker
            ammo_matches = tuple(
                item for item in active_texts if item.path == root + "/ammo/text"
            )
            anchor_matches = tuple(
                image for image in active_images if image.path == root + "/ammo/bg"
            )
            hidden_submarine_ammo = (marker in submarine_markers
                                     and not ammo_matches and not anchor_matches)
            if hidden_submarine_ammo:
                # Both widgets are hidden during hunting. The observer exports
                # the same cell_fleet ancestor position on its exact sub mark.
                anchor_matches = tuple(image for image in active_images
                    if image.path == root + '/mark' and image.sprite == 'qianting_icon')
            if (
                (not hidden_submarine_ammo and len(ammo_matches) != 1)
                or len(anchor_matches) != 1
                or (not hidden_submarine_ammo and anchor_matches[0].sprite != "danyao_bar")
            ):
                raise SemanticGateClosed("campaign map fleet details are incomplete")
            if hidden_submarine_ammo:
                ammo = capacity = None
            else:
                ammo_text = ammo_matches[0].text.strip()
                zero_ammo = re.fullmatch(
                    r"<color=#FF5C5CFF>(0/[1-9][0-9]*)</color>", ammo_text
                )
                if zero_ammo is not None:
                    ammo_text = zero_ammo.group(1)
                ammo_match = re.fullmatch(r"([0-9]+)/([1-9][0-9]*)", ammo_text)
                if ammo_match is None:
                    raise SemanticGateClosed("campaign map fleet ammo is malformed")
                ammo, capacity = map(int, ammo_match.groups())
                if ammo > capacity:
                    raise SemanticGateClosed("campaign map fleet ammo exceeds capacity")
            anchor_value = anchor_matches[0].raw.get("anchor_world_position")
            if not isinstance(anchor_value, Mapping):
                raise SemanticGateClosed("campaign map fleet world anchor is absent")
            anchor = tuple(
                self._finite_number(
                    anchor_value.get(axis), "campaign map fleet world anchor." + axis
                )
                for axis in ("x", "y", "z")
            )
            distances = sorted(
                (
                    sum((anchor[index] - world[index]) ** 2 for index in range(3)),
                    coordinate,
                )
                for coordinate, world in cell_world_positions.items()
            )
            if not distances or distances[0][0] > 0.05**2:
                raise SemanticGateClosed("campaign map fleet world anchor is unmatched")
            if len(distances) > 1 and abs(distances[1][0] - distances[0][0]) <= 0.05**2:
                raise SemanticGateClosed("campaign map fleet world anchor is ambiguous")
            matched_cell = cells_by_coordinate[distances[0][1]]
            if marker in submarine_markers:
                # A submarine may share a cell with a surface fleet; it is
                # not a third surface fleet or a duplicate map model.
                submarine = CampaignMapSubmarineState(marker=marker, node=matched_cell.node,
                    ammo=ammo, ammo_capacity=capacity)
                continue
            if matched_cell.node in occupied_nodes:
                raise SemanticGateClosed("campaign map fleet location is ambiguous")
            fleets.append(
                CampaignMapFleetState(
                    marker=marker,
                    node=matched_cell.node,
                    ammo=ammo,
                    ammo_capacity=capacity,
                )
            )
            occupied_nodes.add(matched_cell.node)

        # Fleet status belongs to the same reviewed stage hierarchy as the
        # exact map back control.  Binding both views to one root avoids a
        # stale camera/canvas alias after a Unity process restart.
        fleet_status_roots = tuple(
            root
            for root in (
                "OverlayCamera/Overlay/UIMain/top/LevelStageView(Clone)",
                "LevelCamera/Canvas/LevelOrigin/top/LevelStageView(Clone)",
            )
            if root + "/top_stage/back_button" in entry.button_paths
        )
        if len(fleet_status_roots) != 1:
            raise SemanticGateClosed(
                "campaign map fleet status root is absent or ambiguous"
            )
        fleet_status_root = fleet_status_roots[0]
        fleet_number_path = fleet_status_root + "/top_stage/msg_panel/fleet_info/number"
        fleet_number_matches = tuple(
            item for item in active_texts if item.path == fleet_number_path
        )
        if (
            len(fleet_number_matches) != 1
            or re.fullmatch(r"[12]", fleet_number_matches[0].text.strip()) is None
        ):
            raise SemanticGateClosed(
                "campaign map displayed fleet index is absent or ambiguous"
            )
        displayed_fleet_index = int(fleet_number_matches[0].text.strip())

        roster_icon_pattern = re.compile(
            re.escape(fleet_status_root)
            + r"/left_stage/fleet/(?:vanguard|main)/shiptpl\(Clone\)"
            + r"/icon_bg/icon$"
        )
        roster_icons = tuple(
            image
            for image in active_images
            if roster_icon_pattern.fullmatch(image.path) is not None
        )
        roster_sprites = tuple(sorted(image.sprite for image in roster_icons))
        if (
            not roster_sprites
            or len(roster_sprites) > 6
            or any(
                re.fullmatch(r"[A-Za-z0-9_]+", sprite) is None
                for sprite in roster_sprites
            )
        ):
            raise SemanticGateClosed(
                "campaign map displayed fleet roster is incomplete"
            )
        current_marker_candidates = []
        for marker in fleet_markers:
            marker_prefix = "cell_fleet_"
            marker_sprite = (
                marker[len(marker_prefix) :]
                if marker.startswith(marker_prefix)
                else marker
            )
            matches = sum(sprite == marker_sprite for sprite in roster_sprites)
            if matches > 1:
                raise SemanticGateClosed(
                    "campaign map current fleet roster identity is ambiguous"
                )
            if matches == 1:
                current_marker_candidates.append(marker)
        if len(current_marker_candidates) != 1:
            raise SemanticGateClosed(
                "campaign map current fleet marker is absent or ambiguous"
            )
        current_fleet_marker = current_marker_candidates[0]
        current_fleet_node = next(
            fleet.node for fleet in fleets if fleet.marker == current_fleet_marker
        )
        fighting_nodes = tuple(enemy.node for enemy in enemies if enemy.fighting)
        if fighting_nodes and fighting_nodes != (current_fleet_node,):
            raise SemanticGateClosed(
                "campaign map fighting enemy disagrees with current fleet"
            )

        hunting_nodes = set()
        for image in active_images:
            match = re.fullmatch(re.escape(grid_root) + r'/DragLayer/plane/buttomMarks/chapter_cell_mark_([0-9]+)_([0-9]+)#[0-9]+', image.path)
            if match and image.sprite == 'cell_hunting_range':
                coordinate = logical_coordinate(*map(int, match.groups()))
                if coordinate not in expected_cells:
                    raise SemanticGateClosed('submarine hunting range lies outside the map')
                hunting_nodes.add(self._campaign_map_node(*coordinate))
        return CampaignMapState(
            generation=max(button_state.generation, ui_state.generation),
            stage_code=stage_code,
            rows=rows,
            columns=columns,
            cells=tuple(
                cells_by_coordinate[key] for key in sorted(cells_by_coordinate)
            ),
            land_nodes=tuple(
                self._campaign_map_node(row, column) for row, column in land
            ),
            fleets=tuple(sorted(fleets, key=lambda item: (item.node, item.marker))),
            enemies=tuple(
                sorted(
                    enemies, key=lambda item: (item.row, item.column, item.object_id)
                )
            ),
            pickups=tuple(
                sorted(pickups, key=lambda item: (item.row, item.column, item.kind))
            ),
            displayed_fleet_index=displayed_fleet_index,
            current_fleet_marker=current_fleet_marker,
            current_fleet_roster_sprites=roster_sprites,
            submarine=submarine,
            submarine_destination_node=submarine_destination_node,
            submarine_hunting_nodes=tuple(sorted(hunting_nodes)) if hunting_nodes else None,
        )

    def campaign_is_in_map(self) -> bool:
        """Prove an exact map root or one reviewed non-map startup surface."""

        try:
            # Reuse the exact map-entry reader's bounded transition sampling.
            # The observer can expose the LevelGrid Button tree one refresh
            # before the independently collected Image anchors; a single read
            # would incorrectly classify that reviewed map as an unknown
            # startup surface.  This remains read-only and every successful
            # attempt still satisfies the original exact identity checks.
            self.campaign_map_entry_state()
        except SemanticGateClosed as exc:
            if str(exc) in (
                "campaign map and blocking identities overlap",
                "campaign map and preparation identities overlap",
            ):
                return False
        else:
            return True

        # Unity can keep CombatUIStandard mounted for a short interval after
        # the exact campaign result hierarchy becomes actionable.  That
        # overlap is a reviewed combat-to-map transition, not an unknown
        # startup surface.  Reuse the exact result-button identities rather
        # than admitting the broad CombatUIStandard hierarchy here.
        if self.daily_battle_result_visible():
            return False

        # A scheduler task can inherit the ready Operation Siren globe.
        # Report this reviewed non-campaign surface to ALAS; its own UI graph
        # chooses how to leave it before starting the campaign.
        if self.operation_siren_globe_visible():
            return False

        if self.retirement_selection_visible() or self.enhancement_dock_visible():
            # Original retirement recovery navigates through these exact
            # non-map surfaces before returning to the campaign map.
            return False

        state = self.read_state()
        non_map_targets = (
            "login/enter",
            "event-list/page/back",
            "main/battle",
            "campaign-menu/normal",
            "campaign-menu/page/back",
            "task/page/back",
            "reward/page/back",
            "commission/page/back",
            "mail/page/back",
            "build/page/start",
            "build/page/back",
            "dorm-menu/page/root",
            "dorm/page/back",
            "research-menu/page/back",
            "research/page/back",
            "tactical/page/back",
            "daily/page/back",
        )
        observed = tuple(
            semantic_id
            for semantic_id in non_map_targets
            if self._matches(state, semantic_id)
        )
        if observed:
            return False
        if (self._matches(state, "shop/home")
                and self.recommendation_shop_visible()):
            # Freebies leaves the reviewed Shop shell mounted. The native
            # Campaign page graph owns leaving it before stage admission.
            return False
        raise SemanticGateClosed("campaign startup surface is not reviewed")
