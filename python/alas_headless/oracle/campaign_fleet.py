"""Campaign fleet for the typed ALAS boundary."""

from __future__ import annotations

import re
from typing import Optional, Tuple
from .contracts import (
    ActionReceipt,
    CampaignAutoSearchRoleState,
    CampaignFleetDropdownState,
    CampaignFleetRowState,
    CampaignFleetSelectionState,
    CampaignHardRequirementState,
    CampaignPreparationState,
    OracleState,
    UNCAPPED_CAMPAIGN_SORTIE_OIL_RESERVE,
    UiState,
)
from .errors import SemanticGateClosed


class CampaignFleetOracle:
    """Campaign fleet operations sharing the oracle frame and input boundary."""

    def campaign_fleet_preparation_state(
        self, stage_code: str
    ) -> CampaignPreparationState:
        """Read exact fleet preparation, including its separately gated sortie."""

        return self._retry_transition_read(
            lambda: self._campaign_fleet_preparation_state_once(stage_code),
            attempts=12,
            interval_seconds=0.05,
        )

    def _campaign_fleet_preparation_state_once(
        self,
        stage_code: str,
        *,
        button_state: Optional[OracleState] = None,
        ui_state: Optional[UiState] = None,
    ) -> CampaignPreparationState:
        match = re.fullmatch(r"([1-9][0-9]*)-([1-9][0-9]*)", stage_code)
        event_match = re.fullmatch(r"[a-z]+[0-9]*", stage_code)
        if match is None and event_match is None:
            raise SemanticGateClosed("campaign stage code is not canonical")
        stage_id = (
            int(match.group(1)) * 100 + int(match.group(2))
            if match is not None
            else None
        )
        if (button_state is None) != (ui_state is None):
            raise ValueError("fleet preparation snapshots must be supplied together")
        if button_state is None:
            button_state = self.read_state()
            ui_state = self.read_ui_state()
        assert ui_state is not None
        map_roots, fleet_roots = self._campaign_preparation_roots(
            button_state, ui_state
        )
        if map_roots or len(fleet_roots) != 1:
            raise SemanticGateClosed(
                "campaign fleet-preparation root is absent or ambiguous"
            )
        fleet_root = fleet_roots[0]
        cancel_matches = tuple(
            button
            for button in button_state.buttons
            if button.name == "btnBack"
            and button.path == fleet_root + "Fixed/btnBack"
        )
        if len(cancel_matches) != 1:
            raise SemanticGateClosed(
                "campaign fleet-preparation cancel is absent or ambiguous"
            )
        cancel = cancel_matches[0]
        if (
            not cancel.active_in_hierarchy
            or not cancel.active_and_enabled
            or not cancel.interactable
            or cancel.point is None
            or cancel.bounds is None
            or self._blocking_rules(button_state, "campaign/fleet-preparation/cancel")
        ):
            raise SemanticGateClosed("campaign fleet-preparation cancel is not proven")
        sortie_matches = tuple(
            button
            for button in button_state.buttons
            if button.name == "start_button"
            and button.path == fleet_root + "Fixed/start_button"
        )
        if len(sortie_matches) != 1:
            raise SemanticGateClosed(
                "campaign fleet-preparation sortie is absent or ambiguous"
            )
        sortie = sortie_matches[0]
        if not sortie.actionable or self._blocking_rules(
            button_state, "campaign/fleet-preparation/sortie"
        ):
            raise SemanticGateClosed("campaign fleet-preparation sortie is not proven")
        stage_button, title_index, title = self._campaign_underlay_identity_texts(
            button_state,
            ui_state,
            stage_code,
            event=stage_id is None
            and not self._war_archives_campaign_counter_records(ui_state),
            archive=stage_id is None
            and bool(self._war_archives_campaign_counter_records(ui_state)),
        )
        self._campaign_fleet_underlay_pair_is_reviewed(
            fleet_root,
            stage_button,
            event=stage_id is None
            and not self._war_archives_campaign_counter_records(ui_state),
        )

        if (
            ui_state.generation < button_state.generation
            or ui_state.generation > button_state.generation + 2
        ):
            raise SemanticGateClosed(
                "campaign fleet-preparation snapshots are not coherent"
            )
        fleet_titles = tuple(
            item
            for item in ui_state.texts
            if item.path == fleet_root + "Fixed/title/Image/text"
            and item.text.strip() == "舰队选择"
            and item.active_in_hierarchy
            and item.active_and_enabled
            and not item.truncated
        )
        if len(fleet_titles) != 1:
            raise SemanticGateClosed(
                "campaign fleet-preparation identity is absent or ambiguous"
            )
        observed_stage = title_index.text.strip().lower()
        observed = re.fullmatch(r"([1-9][0-9]*)[\-–—]([1-9][0-9]*)", observed_stage)
        if observed is not None:
            observed_stage = "{0}-{1}".format(*observed.groups())
        if observed_stage != stage_code:
            raise SemanticGateClosed(
                "campaign fleet-preparation stage identity changed"
            )
        return CampaignPreparationState(
            generation=button_state.generation,
            kind="fleet",
            stage_code=stage_code,
            title=title.text.strip(),
            proceed_button=sortie,
            cancel_button=cancel,
        )

    @staticmethod
    def _campaign_fleet_row_definition(
        row_key: str,
    ) -> Tuple[str, str, str]:
        definitions = {
            "fleet1": (
                "campaign/fleet-preparation/fleet/1",
                "LevelFleetSelectView(Clone)/panel/ShipList/fleet/1",
                "surface",
            ),
            "fleet2": (
                "campaign/fleet-preparation/fleet/2",
                "LevelFleetSelectView(Clone)/panel/ShipList/fleet/2",
                "surface",
            ),
            "submarine": (
                "campaign/fleet-preparation/submarine/1",
                "LevelFleetSelectView(Clone)/panel/ShipList/sub/1",
                "submarine",
            ),
        }
        try:
            return definitions[row_key]
        except KeyError as exc:
            raise SemanticGateClosed(
                "campaign fleet row is not reviewed: {0}".format(row_key)
            ) from exc

    def campaign_fleet_selection_state(
        self, stage_code: str, fallback_oil_cost: Optional[int] = None
    ) -> CampaignFleetSelectionState:
        """Read the closed fleet-selection panel and its gated sortie target."""

        return self._retry_transition_read(
            lambda: self._campaign_fleet_selection_state_once(
                stage_code, fallback_oil_cost=fallback_oil_cost
            ),
            # SP rebuilds LevelFleetSelectView from Overlay to UIOrigin after
            # clearing one row; its exact btnBack/raycast identity can remain
            # transitional for several seconds.  Retry only the full typed
            # read and retain every original final-frame input gate.
            attempts=32,
        )

    def campaign_auto_search_role_state(self) -> CampaignAutoSearchRoleState:
        """Read the official auto-search duties for both surface fleets."""

        return self._retry_transition_read(
            self._campaign_auto_search_role_state_once,
            attempts=12,
        )

    def _campaign_auto_search_role_state_once(
        self,
    ) -> CampaignAutoSearchRoleState:
        button_state = self.read_state()
        ui_state = self.read_ui_state()
        if (
            not button_state.generation <= ui_state.generation <= button_state.generation + 2
            or ui_state.image_truncated
            or ui_state.method_mask & 0xF != 0xF
        ):
            raise SemanticGateClosed(
                "campaign auto-search role snapshots are incomplete"
            )
        tabs = self._toggle_matches(
            ui_state, "campaign/fleet-preparation/roles/tab"
        )
        if not tabs:
            hard_requirements = tuple(
                item
                for item in ui_state.texts
                if "LevelFleetSelectView(Clone)/panel/Fixed/limit_list/"
                "limit_elite/limit_list/" in item.path
                and item.path.endswith("/Text")
                and item.active_in_hierarchy
                and item.active_and_enabled
                and not item.truncated
            )
            right_tab_root = (
                "LevelFleetSelectView(Clone)/panel/Fixed/RightTabs/"
            )
            expected_tabs = {
                "formation_btn": "编队",
                "commander_btn": "指挥喵",
                "adjustment_btn": "编队调整",
            }
            right_tabs = tuple(
                toggle
                for toggle in ui_state.toggles
                if toggle.name in expected_tabs
                and toggle.path.endswith(right_tab_root + toggle.name)
                and toggle.active_in_hierarchy
                and toggle.active_and_enabled
                and toggle.interactable
            )
            labels = {
                item.path.rsplit("/", 2)[-2]: item.text.strip()
                for item in ui_state.texts
                if (
                    "OverlayCamera/Overlay/UIMain/LevelFleetSelectView(Clone)/panel/"
                    "Fixed/RightTabs/"
                ) in item.path
                and item.path.endswith("/text")
                and item.active_in_hierarchy
                and item.active_and_enabled
                and not item.truncated
            }
            legacy_duty_objects = tuple(
                item
                for item in (*button_state.buttons, *ui_state.toggles, *ui_state.images)
                if "/DutySelect/" in item.path or item.name == "duty_btn"
            )
            if (
                not hard_requirements
                or len(right_tabs) != 3
                or sum(toggle.checked for toggle in right_tabs) != 1
                or labels != expected_tabs
                or legacy_duty_objects
            ):
                raise SemanticGateClosed(
                    "campaign hard game-managed auto-search surface is not proven"
                )
            return CampaignAutoSearchRoleState(
                generation=button_state.generation,
                fleet1_role="game-managed",
                fleet2_role="game-managed",
            )
        if len(tabs) != 1 or not tabs[0].checked:
            raise SemanticGateClosed(
                "campaign auto-search role tab is not selected"
            )
        roles = ("mob", "boss", "all", "standby")
        selected = []
        for fleet_index in (1, 2):
            root = (
                "LevelFleetSelectView(Clone)/panel/ShipList/fleet/{0}/"
                "DutySelect/"
            ).format(fleet_index)
            controls = []
            for item_index, role in enumerate(roles, 1):
                semantic_id = (
                    "campaign/fleet-preparation/roles/fleet{0}/{1}"
                ).format(fleet_index, role)
                matches = self._matches(button_state, semantic_id)
                if len(matches) != 1 or not matches[0].actionable:
                    raise SemanticGateClosed(
                        "campaign auto-search role control is incomplete"
                    )
                controls.append(matches[0])
            checkmarks = tuple(
                image
                for image in ui_state.images
                if image.name == "Checkmark"
                and ("/" + root) in image.path
                and image.path.endswith("/Checkmark")
                and image.active_in_hierarchy
                and image.active_and_enabled
                and not image.truncated
                and image.color[3] > 0.99
            )
            if len(checkmarks) != 1:
                raise SemanticGateClosed(
                    "campaign auto-search role selection is ambiguous"
                )
            match = re.search(
                re.escape(root) + r"Item([1-4])/Checkmark$",
                checkmarks[0].path,
            )
            if match is None:
                raise SemanticGateClosed(
                    "campaign auto-search role selection path is malformed"
                )
            selected.append(roles[int(match.group(1)) - 1])
        return CampaignAutoSearchRoleState(
            generation=button_state.generation,
            fleet1_role=selected[0],
            fleet2_role=selected[1],
        )

    def _campaign_fleet_selection_state_once(
        self, stage_code: str, *, fallback_oil_cost: Optional[int] = None
    ) -> CampaignFleetSelectionState:
        button_state = self.read_state()
        ui_state = self.read_ui_state()
        preparation = self._campaign_fleet_preparation_state_once(
            stage_code,
            button_state=button_state,
            ui_state=ui_state,
        )
        if (
            ui_state.generation < button_state.generation
            or ui_state.generation > button_state.generation + 2
            or ui_state.image_truncated
            or ui_state.method_mask & 0x8 == 0
        ):
            raise SemanticGateClosed(
                "campaign fleet-selection snapshots are incomplete"
            )
        visible_options = tuple(
            toggle
            for toggle in ui_state.toggles
            if toggle.path.endswith(
                tuple(
                    "LevelFleetSelectView(Clone)/mask/list/item{0}".format(index)
                    for index in range(1, 7)
                )
            )
        )
        if visible_options:
            raise SemanticGateClosed("campaign fleet-selection dropdown is still open")

        def exact_text(suffix: str, pattern: str) -> re.Match[str]:
            matches = tuple(
                text
                for text in ui_state.texts
                if text.path.endswith(suffix)
                and text.active_in_hierarchy
                and text.active_and_enabled
                and not text.truncated
            )
            if len(matches) != 1:
                raise SemanticGateClosed(
                    "campaign fleet summary text is absent or ambiguous"
                )
            match = re.fullmatch(pattern, matches[0].text.strip())
            if match is None:
                raise SemanticGateClosed("campaign fleet summary text is malformed")
            return match

        hard_requirement_texts = tuple(
            item
            for item in ui_state.texts
            if "LevelFleetSelectView(Clone)/panel/Fixed/limit_list/"
            "limit_elite/limit_list/" in item.path
            and item.path.endswith("/Text")
            and item.active_in_hierarchy
            and item.active_and_enabled
            and not item.truncated
        )
        hard_mode = bool(hard_requirement_texts)
        hard_requirements = []
        if hard_mode:
            for item in hard_requirement_texts:
                requirement = re.fullmatch(
                    r"(.+?)(大于|小于)([0-9]+)[（(]([0-9]+)[）)]",
                    re.sub(r"\s+", "", item.text),
                )
                if requirement is None:
                    raise SemanticGateClosed(
                        "hard campaign fleet requirement is malformed"
                    )
                hard_requirements.append(
                    CampaignHardRequirementState(
                        label=requirement.group(1),
                        comparator=requirement.group(2),
                        target=int(requirement.group(3)),
                        actual=int(requirement.group(4)),
                    )
                )
            if len(hard_requirements) > 8:
                raise SemanticGateClosed(
                    "hard campaign fleet requirements exceed reviewed bounds"
                )
            surface_counts = (0, 2)
            submarine_counts = (0, 0)
        else:
            surface = exact_text(
                "LevelFleetSelectView(Clone)/panel/Fixed/limit_list/limit/number",
                r"([0-9]+)/([0-9]+)",
            )
            submarine = exact_text(
                "LevelFleetSelectView(Clone)/panel/Fixed/limit_list/limit/number_sub",
                r"([0-9]+)/([0-9]+)",
            )
            surface_counts = tuple(map(int, surface.groups()))
            submarine_counts = tuple(map(int, submarine.groups()))
            if (
                not (0 <= surface_counts[0] <= surface_counts[1] <= 2)
                or not (0 <= submarine_counts[0] <= submarine_counts[1] <= 1)
                or surface_counts[1] < 1
            ):
                raise SemanticGateClosed(
                    "campaign fleet capacity is outside reviewed bounds"
                )

        numerals = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6}
        rows = []
        for row_key in ("fleet1", "fleet2", "submarine"):
            semantic_root, path_root, row_kind = self._campaign_fleet_row_definition(
                row_key
            )
            available = {
                "fleet1": surface_counts[1] >= 1,
                "fleet2": surface_counts[1] >= 2,
                "submarine": submarine_counts[1] >= 1,
            }[row_key]
            select_matches = self._matches(button_state, semantic_root + "/select")
            clear_matches = self._matches(button_state, semantic_root + "/clear")
            recommend_matches = (
                self._matches(button_state, semantic_root + "/recommend")
                if row_kind == "surface"
                else ()
            )
            if hard_mode and row_kind == "surface":
                available = bool(recommend_matches or clear_matches)
                if len(recommend_matches) != 1 or len(clear_matches) != 1:
                    raise SemanticGateClosed(
                        "hard campaign fleet row controls are absent or ambiguous: "
                        + row_key
                    )
                select_matches = recommend_matches
            hard_submarine = hard_mode and row_kind == "submarine"
            if hard_submarine:
                # Event hard maps keep the optional submarine row while the
                # ordinary 0/1 capacity summary is replaced by hard-mode
                # requirements.  This client can retain only btn_clear even
                # after the row is empty.  Accept that exact one-sided typed
                # operator, never an inferred or synthetic input target.
                if len(select_matches) > 1 or len(clear_matches) > 1:
                    raise SemanticGateClosed(
                        "hard campaign submarine controls are ambiguous"
                    )
                available = bool(select_matches or clear_matches)
            if available:
                if not hard_submarine and (
                    len(select_matches) != 1 or len(clear_matches) != 1
                ):
                    raise SemanticGateClosed(
                        "campaign fleet row controls are absent or ambiguous: " + row_key
                    )
                select_button = select_matches[0] if select_matches else None
                clear_button = clear_matches[0] if clear_matches else None
                for semantic_id, button in (
                    (semantic_root + "/select", select_button),
                    (semantic_root + "/clear", clear_button),
                ):
                    if button is None:
                        continue
                    delegated_hard_recommend = (
                        hard_mode
                        and button.name == "btn_recom"
                        and button.active_in_hierarchy
                        and button.active_and_enabled
                        and button.interactable
                        and button.raycast_top is None
                        and button.point is not None
                        and button.bounds is not None
                    )
                    if (
                        not button.actionable
                        and not delegated_hard_recommend
                    ) or self._blocking_rules(button_state, semantic_id):
                        raise SemanticGateClosed(
                            "campaign fleet row input is not proven: " + row_key
                        )
            else:
                if select_matches or clear_matches:
                    raise SemanticGateClosed(
                        "campaign unavailable fleet row exposes controls: " + row_key
                    )
                select_button = None
                clear_button = None

            names = tuple(
                text
                for text in ui_state.texts
                if text.path.endswith(path_root + "/bg/name")
                and text.active_in_hierarchy
                and text.active_and_enabled
                and not text.truncated
            )
            if len(names) > 1:
                raise SemanticGateClosed(
                    "campaign fleet row name is ambiguous: " + row_key
                )
            icons = tuple(
                image
                for image in ui_state.images
                if "/" + path_root + "/" in image.path
                and image.path.endswith("/icon_bg/icon")
                and image.name == "icon"
                and image.sprite
                and image.active_in_hierarchy
                and image.active_and_enabled
                and not image.truncated
            )
            level_texts = tuple(
                text
                for text in ui_state.texts
                if "/" + path_root + "/" in text.path
                and text.path.endswith("/icon_bg/lv/Text")
                and text.active_in_hierarchy
                and text.active_and_enabled
                and not text.truncated
                and re.fullmatch(r"[0-9]+", text.text.strip()) is not None
            )
            maximum_ships = 3 if row_kind == "submarine" else 6
            if len(icons) != len(level_texts) or len(icons) > maximum_ships:
                raise SemanticGateClosed(
                    "campaign fleet row ship identity is inconsistent: " + row_key
                )
            levels = tuple(sorted(int(text.text.strip()) for text in level_texts))
            if any(level < 1 or level > 125 for level in levels):
                raise SemanticGateClosed(
                    "campaign fleet row level is outside the pinned range"
                )
            if not available and (levels or any(name.text.strip() for name in names)):
                raise SemanticGateClosed(
                    "campaign unavailable fleet row contains a selection: " + row_key
                )

            selected_fleet = None
            if levels:
                if len(names) != 1:
                    raise SemanticGateClosed(
                        "campaign fleet row selection name is absent: " + row_key
                    )
                normalized = re.sub(r"\s+", "", names[0].text)
                pattern = (
                    r"潜艇编队([一二三四五六])"
                    if row_kind == "submarine"
                    else r"第([一二三四五六])舰队"
                )
                match = re.fullmatch(pattern, normalized)
                if match is None:
                    raise SemanticGateClosed(
                        "campaign fleet row selection name is malformed: " + row_key
                    )
                selected_fleet = numerals[match.group(1)]
            if hard_submarine and available:
                if levels and clear_button is None:
                    raise SemanticGateClosed(
                        "selected hard campaign submarine has no clear control"
                    )
            empty_slots = tuple(
                image
                for image in ui_state.images
                if "/" + path_root + "/" in image.path
                and "/emptytpl(Clone)/" in image.path
                and image.path.endswith("/icon_bg")
                and image.sprite == "tianjia_icon"
                and image.active_in_hierarchy
                and image.active_and_enabled
                and not image.truncated
            )
            required_slots = len(icons) + len(empty_slots) if hard_mode else 0
            if hard_mode and row_kind == "surface" and required_slots != 6:
                raise SemanticGateClosed(
                    "hard campaign fleet slot identity is incomplete: " + row_key
                )
            rows.append(
                CampaignFleetRowState(
                    row_key=row_key,
                    selected_fleet=selected_fleet,
                    ship_levels=levels,
                    select_button=select_button,
                    clear_button=clear_button,
                    required_slots=required_slots,
                    empty_required_slots=len(empty_slots),
                )
            )

        if hard_mode:
            surface_counts = (sum(row.in_use for row in rows[:2]), 2)
            submarine_counts = (int(rows[2].in_use), int(rows[2].available))

        cost_root = "LevelFleetSelectView(Clone)/panel/Fixed/limit_list/cost_limit/"
        cost_texts = {
            item.path: item.text.strip()
            for item in ui_state.texts
            if cost_root in item.path
            and item.path.endswith("/Text")
            and item.active_in_hierarchy
            and item.active_and_enabled
            and not item.truncated
        }
        if cost_texts:
            def optional_cost(suffix: str, pattern: str) -> Optional[int]:
                matches = tuple(
                    text
                    for text in ui_state.texts
                    if text.path.endswith(suffix)
                    and text.active_in_hierarchy
                    and text.active_and_enabled
                    and not text.truncated
                )
                if not matches:
                    return None
                if len(matches) != 1:
                    raise SemanticGateClosed(
                        "campaign fleet summary text is absent or ambiguous"
                    )
                match = re.fullmatch(pattern, matches[0].text.strip())
                if match is None:
                    raise SemanticGateClosed(
                        "campaign fleet summary text is malformed"
                    )
                return int(match.group(1))

            mob = optional_cost(cost_root + "cost_noraml/Text", r"道中\(([0-9]+)\)")
            boss = optional_cost(cost_root + "cost_boss/Text", r"旗舰\(([0-9]+)\)")
            sub_cost = optional_cost(cost_root + "cost_sub/Text", r"潜艇\(([0-9]+)\)")
            if boss is None:
                raise SemanticGateClosed(
                    "campaign fleet boss oil cost is absent or ambiguous"
                )
            # Hard 周回 fleet-select on 9.7.328 may omit the 道中/潜艇 rows
            # while still proving the boss oil cost.  Treat those rows as
            # zero for admission only in hard mode; keep the individual
            # missing observations explicit in the returned state.
            if hard_mode:
                costs = (mob, boss, sub_cost)
                sortie_oil_requirement = (mob or 0) + boss
                oil_cost_source = "fleet-summary-hard-omitted-zero"
            else:
                if mob is None or sub_cost is None:
                    raise SemanticGateClosed(
                        "campaign fleet summary text is absent or ambiguous"
                    )
                costs = (mob, boss, sub_cost)
                sortie_oil_requirement = mob + boss
                oil_cost_source = "observed-fleet-summary"
        else:
            numeric_stage = re.fullmatch(
                r"[1-9][0-9]*-[1-9][0-9]*", stage_code
            ) is not None
            event_stage = re.fullmatch(r"[a-z]+[0-9]*", stage_code) is not None
            archive_stage = bool(
                event_stage
                and self._war_archives_campaign_counter_records(ui_state)
            )
            valid_fallback = (
                fallback_oil_cost is not None
                and not isinstance(fallback_oil_cost, bool)
                and isinstance(fallback_oil_cost, int)
                and fallback_oil_cost > 0
            )
            if not numeric_stage and not archive_stage and not (
                event_stage and valid_fallback
            ):
                raise SemanticGateClosed(
                    "campaign fleet oil cost is absent or ambiguous"
                )
            if valid_fallback:
                costs = (None, None, None)
                sortie_oil_requirement = fallback_oil_cost * 2
                oil_cost_source = "map-preparation-two-fight-reserve"
            else:
                costs = (None, None, None)
                sortie_oil_requirement = UNCAPPED_CAMPAIGN_SORTIE_OIL_RESERVE
                oil_cost_source = "conservative-uncapped-reserve"
        if (
            surface_counts[0] != sum(row.in_use for row in rows[:2])
            or submarine_counts[0] != int(rows[2].in_use)
            or not (0 <= surface_counts[0] <= surface_counts[1] <= 2)
            or not (0 <= submarine_counts[0] <= submarine_counts[1] <= 1)
        ):
            raise SemanticGateClosed(
                "campaign fleet counts do not match the typed rows"
            )
        return CampaignFleetSelectionState(
            generation=button_state.generation,
            stage_code=stage_code,
            title=preparation.title,
            surface_fleets=surface_counts,
            submarine_fleets=submarine_counts,
            mob_oil_cost=costs[0],
            boss_oil_cost=costs[1],
            submarine_oil_cost=costs[2],
            rows=tuple(rows),
            sortie_button=preparation.proceed_button,
            hard_mode=hard_mode,
            hard_requirements=tuple(hard_requirements),
            sortie_oil_requirement=sortie_oil_requirement,
            oil_cost_source=oil_cost_source,
        )

    def campaign_fleet_dropdown_state(
        self,
    ) -> Optional[CampaignFleetDropdownState]:
        """Read the exact six-option fleet dropdown, or return None if closed."""

        return self._retry_transition_read(
            self._campaign_fleet_dropdown_state_once,
            attempts=8,
        )

    def _campaign_fleet_dropdown_state_once(
        self,
    ) -> Optional[CampaignFleetDropdownState]:
        """Read one coherent Button/Toggle generation pair for the dropdown."""

        button_state = self.read_state()
        ui_state = self.read_ui_state()
        option_matches = tuple(
            self._toggle_matches(
                ui_state, "campaign/fleet-preparation/option/{0}".format(index)
            )
            for index in range(1, 7)
        )
        if all(not matches for matches in option_matches):
            return None
        if any(len(matches) != 1 for matches in option_matches):
            raise SemanticGateClosed(
                "campaign fleet dropdown options are incomplete or ambiguous"
            )
        if (
            ui_state.generation < button_state.generation
            or ui_state.generation > button_state.generation + 2
        ):
            raise SemanticGateClosed(
                "campaign fleet dropdown snapshots are not coherent"
            )
        masks = tuple(
            button
            for button in button_state.buttons
            if button.name == "mask"
            and button.path.endswith("LevelFleetSelectView(Clone)/mask")
            and button.active_in_hierarchy
            and button.active_and_enabled
        )
        if len(masks) != 1:
            raise SemanticGateClosed("campaign fleet dropdown mask is absent")
        options = tuple(matches[0] for matches in option_matches)
        for index, option in enumerate(options, 1):
            semantic_id = "campaign/fleet-preparation/option/{0}".format(index)
            if not option.actionable or self._blocking_rules(button_state, semantic_id):
                raise SemanticGateClosed(
                    "campaign fleet dropdown option is not actionable"
                )
        active_indices = []
        for index in range(1, 7):
            prefix = "LevelFleetSelectView(Clone)/mask/list/item{0}/".format(index)
            states = tuple(
                state
                for state in ("on", "off")
                if any(
                    text.path.endswith(prefix + state + "/mask/number")
                    and text.text.strip() == str(index)
                    and text.active_in_hierarchy
                    and text.active_and_enabled
                    and not text.truncated
                    for text in ui_state.texts
                )
            )
            if len(states) != 1:
                raise SemanticGateClosed(
                    "campaign fleet dropdown option state is ambiguous"
                )
            if states[0] == "on":
                active_indices.append(index)
        return CampaignFleetDropdownState(
            generation=ui_state.generation,
            active_indices=tuple(active_indices),
            options=options,
        )

    def click_campaign_fleet_row(self, row_key: str, action: str) -> ActionReceipt:
        if action not in ("select", "clear"):
            raise SemanticGateClosed("campaign fleet row action is not reviewed")
        semantic_root, _, _ = self._campaign_fleet_row_definition(row_key)
        return self.click(semantic_root + "/" + action)

    def click_campaign_hard_recommend(
        self, stage_code: str, row_key: str
    ) -> ActionReceipt:
        """Apply the game's own recommendation to one empty hard-mode fleet."""

        if row_key not in ("fleet1", "fleet2"):
            raise SemanticGateClosed("hard campaign recommendation row is invalid")
        observed = self.campaign_fleet_selection_state(stage_code)
        if not observed.hard_mode:
            raise SemanticGateClosed("hard campaign fleet surface is not active")
        rows = {row.row_key: row for row in observed.rows}
        target = rows[row_key].select_button
        expected_suffix = (
            "LevelFleetSelectView(Clone)/panel/ShipList/fleet/{0}/btn_recom"
        ).format(1 if row_key == "fleet1" else 2)
        if (
            target is None
            or target.name != "btn_recom"
            or not target.path.endswith(expected_suffix)
            or not target.active_in_hierarchy
            or not target.active_and_enabled
            or not target.interactable
            or target.raycast_top is not None
            or target.point is None
            or target.bounds is None
            or self._blocking_rules(
                self.read_state(),
                "campaign/fleet-preparation/{0}/recommend".format(
                    "fleet/1" if row_key == "fleet1" else "fleet/2"
                ),
            )
        ):
            raise SemanticGateClosed(
                "hard campaign recommendation target is not proven"
            )
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("foreground changed immediately before input")
        self._tap(int(round(target.point.x)), int(round(target.point.y)))
        semantic_id = "campaign/fleet-preparation/{0}/recommend".format(
            "fleet/1" if row_key == "fleet1" else "fleet/2"
        )
        return ActionReceipt(
            semantic_id=semantic_id,
            generation=observed.generation,
            point=target.point,
            bounds=target.bounds,
            path=target.path,
        )

    def click_campaign_fleet_option(self, index: int) -> ActionReceipt:
        if index not in range(1, 7):
            raise SemanticGateClosed("campaign fleet option is outside 1 through 6")
        if self.campaign_fleet_dropdown_state() is None:
            raise SemanticGateClosed("campaign fleet dropdown is not open")
        return self.click_toggle("campaign/fleet-preparation/option/{0}".format(index))

    def cancel_campaign_fleet_preparation(self, stage_code: str) -> ActionReceipt:
        """Cancel fleet preparation without exposing or touching sortie."""

        observed = self.campaign_fleet_preparation_state(stage_code)
        target = observed.cancel_button
        if not target.actionable or target.point is None or target.bounds is None:
            raise SemanticGateClosed(
                "campaign fleet-preparation cancel is not actionable"
            )
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("foreground changed immediately before input")
        self._tap(int(round(target.point.x)), int(round(target.point.y)))
        return ActionReceipt(
            semantic_id="campaign/fleet-preparation/cancel",
            generation=observed.generation,
            point=target.point,
            bounds=target.bounds,
            path=target.path,
        )

    def click_campaign_sortie(
        self, stage_code: str, fallback_oil_cost: Optional[int] = None
    ) -> ActionReceipt:
        """Inject the one exact fleet-preparation sortie after caller preflight."""

        observed = self.campaign_fleet_selection_state(
            stage_code, fallback_oil_cost=fallback_oil_cost
        )
        target = observed.sortie_button
        if not target.actionable or target.point is None or target.bounds is None:
            raise SemanticGateClosed("campaign sortie is not actionable")
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("foreground changed immediately before input")
        self._tap(int(round(target.point.x)), int(round(target.point.y)))
        return ActionReceipt(
            semantic_id="campaign/fleet-preparation/sortie",
            generation=observed.generation,
            point=target.point,
            bounds=target.bounds,
            path=target.path,
        )

    def click_campaign_auto_search_sortie(
        self, stage_code: str
    ) -> ActionReceipt:
        """Click sortie from the official duty tab after caller preflight."""

        observed = self.campaign_fleet_preparation_state(stage_code)
        target = observed.proceed_button
        if not target.actionable or target.point is None or target.bounds is None:
            raise SemanticGateClosed("campaign auto-search sortie is not actionable")
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("foreground changed immediately before input")
        self._tap(int(round(target.point.x)), int(round(target.point.y)))
        return ActionReceipt(
            semantic_id="campaign/fleet-preparation/sortie",
            generation=observed.generation,
            point=target.point,
            bounds=target.bounds,
            path=target.path,
        )

    def click_campaign_stage(self, stage_code: str) -> ActionReceipt:
        """Click one exact stage after revalidating its typed Unity identity."""

        observed = self.campaign_stage_state(stage_code)
        if observed.remaining_attempts == 0:
            raise SemanticGateClosed("campaign stage attempts are exhausted")
        state = None
        target = None
        for attempt in range(12):
            candidate_state = self.read_state()
            matches = tuple(
                button
                for button in candidate_state.buttons
                if button.name == observed.button.name
                and button.path == observed.button.path
            )
            if len(matches) != 1:
                raise SemanticGateClosed("campaign stage changed before input")
            candidate = matches[0]
            event_node = (
                "LevelSelectSPFullUI(Clone)/Battle/Nodes/Chapter_" in candidate.path
                or re.search(
                    r"LevelMainScene\(Clone\)/float/levels/items/"
                    r"Chapter_21[0-9]{5}/main$",
                    candidate.path,
                )
                is not None
            )
            candidate_actionable = candidate.actionable or (
                event_node
                and candidate.active_in_hierarchy
                and candidate.active_and_enabled
                and candidate.interactable
                and candidate.raycast_top is None
            )
            if (
                candidate_actionable
                and candidate.point is not None
                and candidate.bounds is not None
            ):
                state = candidate_state
                target = candidate
                break
            if attempt < 11:
                self._sleep(0.1)
        if state is None or target is None:
            raise SemanticGateClosed("campaign stage is not actionable")
        if not (
            0 <= target.point.x < self.fingerprint.width
            and 0 <= target.point.y < self.fingerprint.height
        ):
            raise SemanticGateClosed("campaign stage point is outside the screen")
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("foreground changed immediately before input")
        point = target.point
        self._tap(int(round(point.x)), int(round(point.y)))
        return ActionReceipt(
            semantic_id="campaign/stage/" + stage_code,
            generation=state.generation,
            point=point,
            bounds=target.bounds,
            path=target.path,
        )
