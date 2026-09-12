"""Campaign state for the typed ALAS boundary."""

from __future__ import annotations

import re
from typing import Any, Dict, Tuple
from .contracts import (
    ActionReceipt,
    ButtonState,
    CampaignPageState,
    CampaignStageState,
    Point,
    TextState,
)
from .errors import SemanticGateClosed, SemanticTargetMissing
from .campaign_health import CampaignHealthOracle


class CampaignStateOracle(CampaignHealthOracle):
    """Campaign state operations sharing the oracle frame and input boundary."""

    def campaign_menu_is_entry(self) -> bool:
        """Identify the campaign entrance without conflating the chapter page."""

        if not self.exists("campaign-menu/normal"):
            return False
        state = self.read_ui_state()
        chapter_titles = tuple(
            item
            for item in state.texts
            if item.path.endswith(
                "LevelMainScene(Clone)/top/top_chapter/title_chapter/name"
            )
            and item.active_in_hierarchy
            and item.active_and_enabled
            and item.bounds is not None
        )
        if chapter_titles:
            raise SemanticGateClosed(
                "campaign entrance and chapter title are visible together"
            )
        return True

    def campaign_daily_entrance_available(self) -> bool:
        """Admit the reviewed menu button whose child graphics own raycasts."""

        if not self.campaign_menu_is_entry():
            return False
        state = self.read_state()
        matches = self._matches(state, "campaign-menu/daily")
        if len(matches) != 1:
            return False
        target = matches[0]
        return bool(
            target.active_in_hierarchy
            and target.active_and_enabled
            and target.interactable
            and target.raycast_top is None
            and target.point is not None
            and target.bounds is not None
            and target.bounds.contains(target.point)
            and not self._blocking_rules(state, "campaign-menu/daily")
        )

    def click_campaign_daily_entrance(self) -> ActionReceipt:
        """Click only the exact proven Daily button on the campaign entry menu."""

        if not self.campaign_daily_entrance_available():
            raise SemanticGateClosed("campaign daily entrance is not actionable")
        state = self.read_state()
        target = self._unique(state, "campaign-menu/daily")
        if target.point is None or target.bounds is None:
            raise SemanticGateClosed("campaign daily entrance geometry is absent")
        self._tap(int(round(target.point.x)), int(round(target.point.y)))
        return ActionReceipt(
            semantic_id="campaign-menu/daily",
            generation=state.generation,
            point=target.point,
            bounds=target.bounds,
            path=target.path,
        )

    def click_campaign_exercise_entrance(self) -> ActionReceipt:
        """Click the exact Exercise button whose child graphics own raycasts."""

        if not self.campaign_menu_is_entry():
            raise SemanticGateClosed("campaign exercise entrance requires menu")
        state = self.read_state()
        target = self._unique(state, "campaign-menu/exercise")
        if not (
            target.active_in_hierarchy
            and target.active_and_enabled
            and target.interactable
            and target.raycast_top is None
            and target.point is not None
            and target.bounds is not None
            and target.bounds.contains(target.point)
            and not self._blocking_rules(state, "campaign-menu/exercise")
        ):
            raise SemanticGateClosed("campaign exercise entrance is not actionable")
        self._tap(int(round(target.point.x)), int(round(target.point.y)))
        return ActionReceipt(
            semantic_id="campaign-menu/exercise",
            generation=state.generation,
            point=target.point,
            bounds=target.bounds,
            path=target.path,
        )

    def click_campaign_archive_entrance(self) -> ActionReceipt:
        """Click the exact War Archives menu control with delegated raycast."""

        if not self.campaign_menu_is_entry():
            raise SemanticGateClosed("campaign archive entrance requires menu")
        state = self.read_state()
        target = self._unique(state, "campaign-menu/archive")
        blockers = self._blocking_rules(state, "campaign-menu/archive")
        if not (
            target.active_in_hierarchy
            and target.active_and_enabled
            and target.interactable
            and target.raycast_top is None
            and target.point is not None
            and target.bounds is not None
            and target.bounds.contains(target.point)
            and not blockers
        ):
            raise SemanticGateClosed(
                "campaign archive entrance is not actionable: "
                "active={0}, enabled={1}, interactable={2}, raycast_top={3}, "
                "point={4}, bounds={5}, blockers={6}".format(
                    target.active_in_hierarchy,
                    target.active_and_enabled,
                    target.interactable,
                    target.raycast_top,
                    target.point,
                    target.bounds,
                    tuple(rule.blocker_id for rule in blockers),
                )
            )
        self._tap(int(round(target.point.x)), int(round(target.point.y)))
        return ActionReceipt(
            semantic_id="campaign-menu/archive",
            generation=state.generation,
            point=target.point,
            bounds=target.bounds,
            path=target.path,
        )

    def campaign_os_entrance_available(self) -> bool:
        """Admit the exact Operation Siren card on the campaign menu."""

        if not self.campaign_menu_is_entry():
            return False
        state = self.read_state()
        matches = self._matches(state, "campaign-menu/os")
        if len(matches) != 1:
            return False
        target = matches[0]
        return bool(
            target.active_in_hierarchy
            and target.active_and_enabled
            and target.interactable
            and target.raycast_top is None
            and target.point is not None
            and target.bounds is not None
            and target.bounds.contains(target.point)
            and not self._blocking_rules(state, "campaign-menu/os")
        )

    def click_campaign_os_entrance(self) -> ActionReceipt:
        """Click the proven Operation Siren card with delegated raycast."""

        if not self.campaign_os_entrance_available():
            raise SemanticGateClosed("operation siren entrance is not actionable")
        state = self.read_state()
        target = self._unique(state, "campaign-menu/os")
        assert target.point is not None and target.bounds is not None
        self._tap(int(round(target.point.x)), int(round(target.point.y)))
        return ActionReceipt(
            semantic_id="campaign-menu/os",
            generation=state.generation,
            point=target.point,
            bounds=target.bounds,
            path=target.path,
        )

    def campaign_battle_reward_visible(self) -> bool:
        """Prove an award popup belongs to the active battle-result stack."""

        state = self.read_state()
        close_targets = []
        for semantic_id in (
            "reward/award-info/close",
            "reward/award-info1/close",
        ):
            matches = self._matches(state, semantic_id)
            if len(matches) > 1:
                raise SemanticGateClosed(
                    "campaign battle reward close target is ambiguous"
                )
            if (
                matches
                and matches[0].actionable
                and not self._blocking_rules(state, semantic_id)
            ):
                close_targets.append(semantic_id)
        if len(close_targets) != 1:
            return False
        ui_state = self.read_ui_state()
        return any(
            text.path.startswith(
                "UICamera/Canvas/UIOrigin/NewBattleResultEmptyUI(Clone)/"
            )
            and text.active_in_hierarchy
            and text.active_and_enabled
            for text in ui_state.texts
        )

    def campaign_page_state(self) -> CampaignPageState:
        """Read the visible chapter and stage labels without enabling a stage click."""

        # The three observer endpoints are independently refreshed on the
        # Unity main thread.  Keep the original <=2-generation contract, but
        # sample long enough to obtain one actually coherent pair under the
        # campaign page's heavier UI collection load.
        return self._retry_transition_read(
            self._campaign_page_state_once,
            attempts=12,
            interval_seconds=0.05,
        )

    def _campaign_page_state_once(self) -> CampaignPageState:
        """Read one generation-coherent campaign chapter view."""

        button_state = self.read_state()
        back = self._unique(button_state, "campaign-menu/page/back")
        # Page identity is an observation boundary, not authorization to click
        # the chapter back control.  The live hard page can briefly report the
        # exact active back control below the stage canvas (raycast_top=False)
        # after the fleet overlay closes, while its chapter title and nodes are
        # already coherent.  Accept that structural anchor here; ``click``
        # continues to require the full actionable predicate, and reviewed
        # blockers still prevent the page from impersonating an unobstructed
        # chapter surface.
        if (
            not back.active_in_hierarchy
            or not back.active_and_enabled
            or not back.interactable
            or back.point is None
            or back.bounds is None
            or not back.bounds.contains(back.point)
            or self._blocking_rules(button_state, "campaign-menu/page/back")
        ):
            raise SemanticGateClosed("campaign page identity is not proven")
        if self._matches(button_state, "campaign-menu/normal"):
            raise SemanticGateClosed("campaign entrance is not a chapter page")
        ui_state = self.read_ui_state()
        if (
            ui_state.generation < button_state.generation
            or ui_state.generation > button_state.generation + 2
        ):
            raise SemanticGateClosed("campaign snapshots are not coherent")

        if self._war_archives_campaign_counter_records(ui_state):
            return self._war_archives_campaign_page_state(button_state, ui_state)

        if self._event_campaign_page_visible_in_state(button_state):
            return self._event_campaign_page_state(button_state, ui_state)

        title_path = "LevelMainScene(Clone)/top/top_chapter/title_chapter/name"
        chapter_titles = tuple(
            item
            for item in ui_state.texts
            if item.path.endswith(title_path)
            and item.active_in_hierarchy
            and item.active_and_enabled
            and not item.truncated
            and item.text.strip()
        )
        if len(chapter_titles) != 1:
            raise SemanticGateClosed("campaign chapter title is absent or ambiguous")

        prefix = "LevelMainScene(Clone)/float/levels/items/Chapter_"
        stage_control = re.compile(re.escape(prefix) + r"([1-9][0-9]*)/main$")
        stage_buttons = []
        for button in button_state.buttons:
            match = stage_control.search(button.path)
            if match is None or button.name != "main":
                continue
            if (
                not button.active_in_hierarchy
                or not button.active_and_enabled
                or button.bounds is None
            ):
                continue
            stage_buttons.append((int(match.group(1)), button))
        stage_buttons.sort(key=lambda item: item[0])
        if not stage_buttons or len({item[0] for item in stage_buttons}) != len(
            stage_buttons
        ):
            raise SemanticGateClosed("campaign stage buttons are absent or ambiguous")

        stages = []
        for stage_id, button in stage_buttons:
            root = button.path + "/info/bk/title_form/"
            fields: Dict[str, TextState] = {}
            for field in ("title_index", "title"):
                matches = tuple(
                    item
                    for item in ui_state.texts
                    if item.path == root + field
                    and item.active_in_hierarchy
                    and item.active_and_enabled
                    and not item.truncated
                )
                if len(matches) != 1:
                    raise SemanticGateClosed(
                        "campaign stage text is absent or ambiguous: " + field
                    )
                fields[field] = matches[0]
            code_match = re.fullmatch(
                r"([0-9]+)[\-–—]([0-9]+)", fields["title_index"].text.strip()
            )
            title = fields["title"].text.strip()
            if code_match is None or not title:
                raise SemanticGateClosed("campaign stage text is malformed")
            chapter, stage = map(int, code_match.groups())
            normal_stage_id = chapter * 100 + stage
            hard_stage_id = 10000 + normal_stage_id
            if stage_id not in (normal_stage_id, hard_stage_id):
                raise SemanticGateClosed("campaign stage identity is inconsistent")
            if (
                stage_id == hard_stage_id
                and self.campaign_mode_switch_state() != "normal"
            ):
                raise SemanticGateClosed("hard campaign stage identity is inconsistent")
            stages.append(
                CampaignStageState(
                    stage_id=stage_id,
                    stage_code="{0}-{1}".format(chapter, stage),
                    title=title,
                    button=button,
                )
            )
        return CampaignPageState(
            generation=button_state.generation,
            chapter_name=chapter_titles[0].text.strip(),
            stages=tuple(stages),
        )

    @staticmethod
    def _campaign_stage_chapter(stage_code: str) -> str:
        numeric = re.fullmatch(r"([0-9]+)-[0-9]+", stage_code)
        if numeric is not None:
            return numeric.group(1)
        event = re.fullmatch(r"([a-z]+)[0-9]*", stage_code)
        if event is not None:
            code = event.group(1)
            return "ex_sp" if code == "sp" else code
        raise SemanticGateClosed("campaign stage code is not canonical")

    def campaign_mode_switch_state(self) -> str:
        """Return the exact destination exposed by the normal/hard switch."""

        state = self.read_state()
        # Both chapter families expose the destination in the native control.
        # Reading that control remains valid under its stage-detail overlay;
        # clicking it still requires the separate unobscured page contract.
        controls = {'hard': ('btn_elite', 'btn_act_elite'),
                    'normal': ('btn_normal', 'btn_act_normal')}
        observed = []
        for destination, names in controls.items():
            matches = tuple(
                button
                for button in state.buttons
                if button.name in names
                and button.path.endswith('LevelMainScene(Clone)/main/left_chapter/buttons/' + button.name)
                and button.active_in_hierarchy
                and button.active_and_enabled
                and button.bounds is not None
            )
            if len(matches) > 1:
                raise SemanticGateClosed("campaign mode switch is ambiguous")
            if matches:
                observed.append(destination)
        if len(observed) != 1:
            raise SemanticGateClosed("campaign mode switch is absent or ambiguous")
        return observed[0]

    def click_campaign_mode_switch(self, destination: str) -> ActionReceipt:
        """Click the exact normal/hard destination exposed by campaign UI."""

        archive = self.war_archives_campaign_page_visible()
        paths = {
            "hard": (
                "btn_act_elite" if archive else "btn_elite",
                "LevelMainScene(Clone)/main/left_chapter/buttons/"
                + ("btn_act_elite" if archive else "btn_elite"),
            ),
            "normal": (
                "btn_act_normal" if archive else "btn_normal",
                "LevelMainScene(Clone)/main/left_chapter/buttons/"
                + ("btn_act_normal" if archive else "btn_normal"),
            ),
        }
        control = paths.get(destination)
        if control is None:
            raise SemanticGateClosed("campaign mode destination is invalid")
        if self.campaign_mode_switch_state() != destination:
            raise SemanticGateClosed("campaign mode destination changed")
        state = self.read_state()
        name, suffix = control
        matches = tuple(
            button
            for button in state.buttons
            if button.name == name
            and button.path.endswith(suffix)
            and button.active_in_hierarchy
            and button.active_and_enabled
            and button.interactable
            and button.point is not None
            and button.bounds is not None
        )
        if len(matches) != 1:
            raise SemanticGateClosed("campaign mode switch is absent or ambiguous")
        button = matches[0]
        if self._blocking_rules(state, "campaign/mode/" + destination):
            raise SemanticGateClosed("campaign mode switch is blocked")
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("game activity changed before campaign mode input")
        x = (button.bounds.left + button.bounds.right) / 2.0
        y = (button.bounds.top + button.bounds.bottom) / 2.0
        self._tap(int(round(x)), int(round(y)))
        return ActionReceipt(
            semantic_id="campaign/mode/" + destination,
            generation=state.generation,
            point=Point(x=x, y=y),
            bounds=button.bounds,
            path=button.path,
        )

    def click_campaign_chapter(self, direction: str) -> ActionReceipt:
        """Click one exact main-campaign chapter navigation button."""

        controls = {
            "previous": (
                "btn_prev",
                "LevelMainScene(Clone)/main/left_chapter/btn_prev",
            ),
            "next": (
                "btn_next",
                "LevelMainScene(Clone)/main/right_chapter/btn_next",
            ),
        }
        control = controls.get(direction)
        if control is None:
            raise SemanticGateClosed("campaign chapter direction is invalid")
        state = self.read_state()
        name, suffix = control
        matches = tuple(
            button
            for button in state.buttons
            if button.name == name
            and button.path.endswith(suffix)
            and button.active_in_hierarchy
            and button.active_and_enabled
            and button.interactable
            and button.point is not None
            and button.bounds is not None
        )
        if len(matches) != 1:
            raise SemanticGateClosed("campaign chapter control is absent or ambiguous")
        button = matches[0]
        if self._blocking_rules(state, "campaign/chapter/" + direction):
            raise SemanticGateClosed("campaign chapter control is blocked")
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("game activity changed before chapter input")
        x = (button.bounds.left + button.bounds.right) / 2.0
        y = (button.bounds.top + button.bounds.bottom) / 2.0
        self._tap(int(round(x)), int(round(y)))
        return ActionReceipt(
            semantic_id="campaign/chapter/" + direction,
            generation=state.generation,
            point=Point(x=x, y=y),
            bounds=button.bounds,
            path=button.path,
        )

    def campaign_hard_remain(self) -> int:
        """Read the exact hard-mode daily quota numerator."""

        if self.campaign_mode_switch_state() != "normal":
            raise SemanticGateClosed("hard campaign mode is not active")
        state = self.read_ui_state()
        suffix = "LevelMainScene(Clone)/main/left_chapter/elite_quota/bg/Text"
        matches = tuple(
            item
            for item in state.texts
            if item.path.endswith(suffix)
            and item.active_in_hierarchy
            and item.active_and_enabled
            and not item.truncated
            and item.bounds is not None
        )
        if len(matches) != 1:
            raise SemanticGateClosed("hard campaign quota is absent or ambiguous")
        value = re.fullmatch(r"([0-3])/3", matches[0].text.strip())
        if value is None:
            raise SemanticGateClosed("hard campaign quota is malformed")
        return int(value.group(1))

    def campaign_oil(self) -> int:
        """Read the exact global oil counter on a proven campaign surface."""

        return self._retry_transition_read(self._campaign_oil_once)

    def _campaign_oil_once(self) -> int:
        """Read the oil counter from one fully proven campaign generation."""

        try:
            self.campaign_page_state()
        except SemanticTargetMissing:
            if self.main_page_visible():
                pass
            elif self.enabled("reward/campaign-total/exit"):
                pass
            elif self.event_campaign_page_visible():
                pass
            else:
                # The global resource panel remains visible after sortie.  A
                # resumed ALAS run performs its oil stop-condition check from
                # the map, so admit the same typed counter only after the exact
                # map root/anchor proof succeeds.
                self.campaign_map_entry_state()
        except SemanticGateClosed as exc:
            if self.main_page_visible():
                pass
            elif self.enabled("reward/campaign-total/exit"):
                pass
            elif self._event_campaign_detail_visible(self.read_state()):
                pass
            elif self.event_campaign_page_visible():
                # Event selectors use LevelSelectSPFullUI rather than the
                # normal chapter root, but retain the same exact global
                # ResPanel counter. This is also the stable page restored by
                # a successful NetworkDown reconnect during Event startup.
                pass
            elif str(exc) != "campaign entrance is not a chapter page":
                raise
            # Coalition checks its oil stop condition from the proven campaign
            # entrance before navigating into the event page.
            elif not self.campaign_menu_is_entry():
                raise
        return self._campaign_oil_counter(self.read_ui_state())

    def campaign_deployment_oil(self):
        state = self.read_state(); ui = self.read_ui_state()
        self._campaign_map_entry_state_from_snapshots(state, ui, allow_deployment=True)
        return self._campaign_oil_counter(ui)

    @staticmethod
    def _campaign_oil_counter(state):
        paths = (
            "OverlayCamera/Overlay/UIMain/ResPanel(Clone)/frame/oil/oil_value",
            "UICamera/Canvas/UIOrigin/ResPanel(Clone)/frame/oil/oil_value",
            "LevelCamera/Canvas/LevelOrigin/ResPanel(Clone)/frame/oil/oil_value",
            "OverlayCamera/Overlay/UIMain/NewMainMellowTheme(Clone)/frame/top/res/oil/Text",
        )
        matches = tuple(
            item
            for item in state.texts
            if item.path in paths
            and item.active_in_hierarchy
            and item.active_and_enabled
            and not item.truncated
            and re.fullmatch(r"[0-9]+", item.text.strip()) is not None
        )
        if len(matches) != 1:
            raise SemanticGateClosed("campaign oil counter is absent or ambiguous")
        return int(matches[0].text.strip())

    def campaign_map_formation(self) -> str:
        """Read the active fleet formation from the proven map buff list."""

        self.campaign_map_entry_state()
        state = self.read_ui_state()
        suffix = "/top_stage/icon_list/fleet_buffs/"
        sprite_to_formation = {
            "1": "line_ahead",
            "2": "double_line",
            "3": "diamond",
        }
        matches = tuple(
            sprite_to_formation[item.sprite]
            for item in state.images
            if suffix in item.path
            and item.active_in_hierarchy
            and item.active_and_enabled
            and not item.truncated
            and item.sprite in sprite_to_formation
        )
        if len(matches) != 1:
            raise SemanticGateClosed("campaign fleet formation is absent or ambiguous")
        return matches[0]

    def click_campaign_strategy_open(self) -> ActionReceipt:
        """Open the exact in-map strategy panel from a proven map surface."""

        entry = self.campaign_map_entry_state()
        stage_roots = tuple(
            root
            for root in (
                "OverlayCamera/Overlay/UIMain/top/LevelStageView(Clone)",
                "LevelCamera/Canvas/LevelOrigin/top/LevelStageView(Clone)",
            )
            if root + "/top_stage/back_button" in entry.button_paths
        )
        if len(stage_roots) != 1:
            raise SemanticGateClosed(
                "campaign strategy stage root is absent or ambiguous"
            )
        path = stage_roots[0] + "/right_stage/event/collapse"
        button_state = self.read_state()
        button_matches = tuple(
            button
            for button in button_state.buttons
            if button.path == path
            and button.active_in_hierarchy
            and button.active_and_enabled
            and button.interactable
            and button.raycast_top is True
            and button.point is not None
            and button.bounds is not None
            and button.bounds.contains(button.point)
        )
        ui_state = self.read_ui_state()
        image_contract = {
            path + "/Image": "zhanlue_kuang02",
            path + "/arr": "zhanlue_ICON",
            path + "/bg": "zhanlue_kuang01",
        }
        image_matches = tuple(
            image
            for image in ui_state.images
            if image.path in image_contract
            and image.active_in_hierarchy
            and image.active_and_enabled
            and not image.truncated
            and image.sprite == image_contract[image.path]
            and image.bounds is not None
        )
        if len(button_matches) != 1 or {image.path for image in image_matches} != set(
            image_contract
        ):
            raise SemanticGateClosed(
                "campaign strategy open identity is absent or ambiguous"
            )
        target = button_matches[0]
        if abs(ui_state.generation - button_state.generation) > 2:
            raise SemanticGateClosed("campaign strategy open snapshots are not coherent")
        if self._blocking_rules(button_state, "campaign/map/strategy/open") or self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("campaign strategy open is blocked")
        assert target.bounds is not None
        # The strategy collapse control anchors its pivot on the right edge;
        # use the centre of its exact visible bounds.
        point = Point(
            (target.bounds.left + target.bounds.right) / 2.0,
            (target.bounds.top + target.bounds.bottom) / 2.0,
        )
        self._tap(int(round(point.x)), int(round(point.y)))
        return ActionReceipt(
            semantic_id="campaign/map/strategy/open",
            generation=max(button_state.generation, ui_state.generation),
            point=point,
            bounds=target.bounds,
            path=target.path,
        )

    def _campaign_strategy_stage_root(self) -> str:
        entry = self.campaign_map_entry_state()
        roots = tuple(
            root
            for root in (
                "OverlayCamera/Overlay/UIMain/top/LevelStageView(Clone)",
                "LevelCamera/Canvas/LevelOrigin/top/LevelStageView(Clone)",
            )
            if root + "/top_stage/back_button" in entry.button_paths
        )
        if len(roots) != 1:
            raise SemanticGateClosed(
                "campaign strategy stage root is absent or ambiguous"
            )
        return roots[0]

    def campaign_strategy_panel_visible(self) -> bool:
        root = self._campaign_strategy_stage_root()
        path = root + "/right_stage/event/detail/show_detail"
        state = self.read_ui_state()
        matches = tuple(
            image
            for image in state.images
            if image.path == path
            and image.active_in_hierarchy
            and image.active_and_enabled
            and not image.truncated
            and image.sprite == "show_detail"
            and image.bounds is not None
        )
        if len(matches) != 1:
            raise SemanticGateClosed(
                "campaign strategy panel identity is absent or ambiguous"
            )
        bounds = matches[0].bounds
        assert bounds is not None
        return bool(
            0.0 <= bounds.left < bounds.right <= 1280.0
            and 0.0 <= bounds.top < bounds.bottom <= 720.0
        )

    def _campaign_strategy_selected_formation(
        self,
    ) -> Tuple[str, Any, Any, int]:
        if not self.campaign_strategy_panel_visible():
            raise SemanticGateClosed("campaign strategy panel is closed")
        root = self._campaign_strategy_stage_root()
        icon_pattern = re.compile(
            re.escape(root + "/right_stage/event/detail/items/")
            + r"item(?:\(Clone\))*/icon/icon$"
        )
        state = self.read_ui_state()
        sprite_to_formation = {
            "1": "line_ahead",
            "2": "double_line",
            "3": "diamond",
        }
        candidates = []
        for image in state.images:
            if (
                icon_pattern.fullmatch(image.path) is None
                or not image.active_in_hierarchy
                or not image.active_and_enabled
                or image.truncated
                or image.sprite not in sprite_to_formation
                or image.bounds is None
            ):
                continue
            selected_path = image.path.rsplit("/", 1)[0] + "/selected"
            selected = tuple(
                marker
                for marker in state.images
                if marker.path == selected_path
                and marker.active_in_hierarchy
                and marker.active_and_enabled
                and not marker.truncated
                and marker.sprite == "zhanlue_kuang03"
                and marker.bounds is not None
            )
            if len(selected) == 1:
                candidates.append(
                    (sprite_to_formation[image.sprite], image, selected[0])
                )
        if len(candidates) != 1:
            raise SemanticGateClosed(
                "campaign strategy formation is absent or ambiguous"
            )
        return (*candidates[0], state.generation)

    def campaign_strategy_formation(self) -> str:
        formation, _, _, _ = self._campaign_strategy_selected_formation()
        return formation

    def campaign_submarine_move_confirmation(self):
        state = self.read_state(); ui = self.read_ui_state()
        path = 'OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/'
        texts = [t for t in ui.texts if t.path == path+'msg_panel/content'
                 and t.active_in_hierarchy and t.active_and_enabled]
        if not texts:
            return None
        if len(texts) != 1 or texts[0].truncated:
            raise SemanticGateClosed('submarine move confirmation text is incomplete')
        text = re.sub(r'<[^>]*>', '', texts[0].text).strip()
        match = re.fullmatch(r'发布指令：将潜艇编队从([A-Z][1-9][0-9]*)区域调动到([A-Z][1-9][0-9]*)区域，需要移动([0-9]+)格，消耗([0-9]+)点石油，是否确认？', text)
        if match is None:
            return None
        if not state.generation <= ui.generation <= state.generation+2:
            raise SemanticGateClosed('submarine move confirmation frame is incoherent')
        buttons = []
        for index, label in ((1, '确定'), (2, '取消')):
            button_path = path+f'button_container/custom_button_{index}(Clone)'
            targets = [b for b in state.buttons if b.path == button_path and b.active_in_hierarchy and b.active_and_enabled]
            labels = [t for t in ui.texts if t.path == button_path+'/pic' and t.active_in_hierarchy
                      and t.active_and_enabled]
            if len(targets) > 1 or len(labels) > 1:
                raise SemanticGateClosed('submarine move confirmation buttons are ambiguous')
            # The body can mount one frame before custom buttons and labels.
            # Absence is not readiness: original ALAS waits for its next screenshot.
            if not targets or not labels or not labels[0].text.strip():
                return None
            if labels[0].truncated or ''.join(labels[0].text.split()) != label:
                raise SemanticGateClosed('submarine move confirmation button label is unsupported')
            buttons.append(targets[0])
        return state, ui.generation, match.group(1), match.group(2), int(match.group(3)), int(match.group(4)), tuple(buttons)

    def click_campaign_submarine_move_confirmation(self, origin, destination, *, confirm):
        observed = self.campaign_submarine_move_confirmation()
        if observed is None or observed[2:4] != (origin, destination) or type(confirm) is not bool:
            raise SemanticGateClosed('submarine move confirmation differs from selected movement')
        state, generation, _, _, _, cost, buttons = observed
        target = buttons[0 if confirm else 1]
        if not target.actionable:
            raise SemanticGateClosed('submarine move confirmation is not actionable')
        if confirm and self.campaign_deployment_oil() < cost:
            raise SemanticGateClosed('submarine movement oil is insufficient')
        if confirm:
            refreshed = self.campaign_submarine_move_confirmation()
            if refreshed is None or refreshed[2:6] != observed[2:6]:
                raise SemanticGateClosed('submarine oil prompt changed before input')
            state, generation, _, _, _, _, buttons = refreshed
            target = buttons[0]
            if not target.actionable:
                raise SemanticGateClosed('submarine move confirmation is not actionable')
        semantic_id = 'campaign/map/submarine/oil/' + ('confirm' if confirm else 'cancel')
        if self._blocking_rules(state, semantic_id) or self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed('submarine move confirmation is blocked')
        self._tap(int(round(target.point.x)), int(round(target.point.y)))
        return ActionReceipt(semantic_id=semantic_id, generation=generation,
                             point=target.point, bounds=target.bounds, path=target.path)

    def campaign_deployment_controls(self):
        state = self.read_state()
        suffix = '/LevelStageView(Clone)/bottom_stage/Action/MissileStrike/'
        cancels = [b for b in state.buttons if b.path.endswith(suffix+'cancel_button')
                   and b.active_in_hierarchy and b.active_and_enabled]
        if not cancels:
            return None
        if len(cancels) != 1:
            raise SemanticGateClosed('campaign deployment root is ambiguous')
        root = cancels[0].path.rsplit('/', 1)[0] + '/'
        confirms = [b for b in state.buttons if b.path == root+'confirm_button'
                    and b.active_in_hierarchy and b.active_and_enabled]
        ui = self.read_ui_state()
        if not state.generation <= ui.generation <= state.generation+2:
            raise SemanticGateClosed('campaign deployment frame is incoherent')
        for control, label in (('cancel_button', '取消部署'), ('confirm_button', '确认部署')):
            texts = [t for t in ui.texts if t.path == root+control+'/Text'
                     and t.active_in_hierarchy and t.active_and_enabled]
            if len(texts) != 1 or texts[0].truncated or texts[0].text.strip() != label:
                raise SemanticGateClosed('campaign deployment label is unproven')
        if len(confirms) != 1:
            raise SemanticGateClosed('campaign deployment confirm is ambiguous')
        return state, ui.generation, cancels[0], confirms[0]

    def click_campaign_submarine_destination(self, state, node, entry_receipt):
        if (not isinstance(entry_receipt, ActionReceipt)
                or entry_receipt.semantic_id != 'campaign/map/strategy/submarine/move'
                or state.generation <= entry_receipt.generation or state.submarine is None):
            raise SemanticGateClosed('submarine destination requires this deployment entry')
        if self.campaign_deployment_controls() is None:
            raise SemanticGateClosed('submarine destination requires deployment controls')
        target = self._campaign_map_cell_target(state, node, require_top_raycast=True)
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed('submarine destination foreground changed')
        self._tap(int(round(target.point.x)), int(round(target.point.y)))
        return ActionReceipt(semantic_id='campaign/map/submarine/destination/'+node,
                             generation=self._last_generation, point=target.point,
                             bounds=target.bounds, path=target.path)

    def click_campaign_deployment_cancel(self):
        controls = self.campaign_deployment_controls()
        if controls is None or not controls[2].actionable:
            raise SemanticGateClosed('campaign deployment cancel is not actionable')
        state, generation, target, _ = controls
        semantic_id = 'campaign/map/deployment/cancel'
        if self._blocking_rules(state, semantic_id) or self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed('campaign deployment cancel is blocked')
        self._tap(int(round(target.point.x)), int(round(target.point.y)))
        return ActionReceipt(semantic_id=semantic_id, generation=generation,
                             point=target.point, bounds=target.bounds, path=target.path)

    def click_campaign_submarine_deployment_confirm(self, state, destination_receipt):
        if (not isinstance(destination_receipt, ActionReceipt)
                or not destination_receipt.semantic_id.startswith('campaign/map/submarine/destination/')
                or state.submarine_destination_node != destination_receipt.semantic_id.rsplit('/',1)[1]
                or state.generation <= destination_receipt.generation):
            raise SemanticGateClosed('submarine deployment destination is not acknowledged')
        controls = self.campaign_deployment_controls()
        if controls is None or not controls[3].actionable:
            raise SemanticGateClosed('submarine deployment confirm is not actionable')
        frame, generation, _, target = controls
        semantic_id = 'campaign/map/submarine/deployment/confirm'
        if self._blocking_rules(frame, semantic_id) or self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed('submarine deployment confirm is blocked')
        self._tap(int(round(target.point.x)), int(round(target.point.y)))
        return ActionReceipt(semantic_id=semantic_id, generation=generation,
                             point=target.point, bounds=target.bounds, path=target.path)

    def click_campaign_strategy_details(self):
        if not self.campaign_strategy_panel_visible():
            raise SemanticGateClosed('campaign strategy details requires open strategy')
        path = self._campaign_strategy_stage_root() + '/right_stage/event/detail/show_detail'
        state = self.read_state()
        targets = [b for b in state.buttons if b.path == path
                   and b.active_in_hierarchy and b.active_and_enabled]
        if len(targets) != 1 or not targets[0].actionable:
            raise SemanticGateClosed('campaign strategy details is not uniquely actionable')
        target = targets[0]
        semantic_id = 'campaign/map/strategy/details'
        if self._blocking_rules(state, semantic_id) or self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed('campaign strategy details is blocked')
        self._tap(int(round(target.point.x)), int(round(target.point.y)))
        return ActionReceipt(semantic_id=semantic_id, generation=state.generation,
                             point=target.point, bounds=target.bounds, path=target.path)

    def _campaign_submarine_strategy_control(self, feature):
        sprites = {'hunt': {'sub_dont_auto_attack': False, 'sub_auto_attack': True},
                   'view': {'range_visible': True, 'range_invisible': False},
                   'move': {'11': False}}
        if feature not in sprites:
            raise SemanticGateClosed('unknown submarine strategy feature')
        if not self.campaign_strategy_panel_visible():
            return None
        root = self._campaign_strategy_stage_root() + '/right_stage/event/detail/items/'
        state = self.read_state()
        ui = self.read_ui_state()
        if not state.generation <= ui.generation <= state.generation + 2 or ui.image_truncated:
            raise SemanticGateClosed('submarine strategy frame is incomplete')
        images = [i for i in ui.images if i.path.startswith(root) and i.path.endswith('/icon/icon')
                  and i.sprite in sprites[feature] and i.active_in_hierarchy and i.active_and_enabled
                  and not i.truncated and i.bounds is not None]
        if not images:
            return None
        if len(images) != 1:
            raise SemanticGateClosed('submarine strategy icon is ambiguous')
        icon = images[0]
        point = Point((icon.bounds.left + icon.bounds.right)/2, (icon.bounds.top + icon.bounds.bottom)/2)
        matches = [b for b in state.buttons if b.path == icon.path.rsplit('/', 1)[0]
                   and b.active_in_hierarchy and b.active_and_enabled and b.bounds is not None
                   and b.bounds.contains(point)]
        if len(matches) != 1:
            raise SemanticGateClosed('submarine strategy button binding is ambiguous')
        return sprites[feature][icon.sprite], matches[0], ui.generation

    def campaign_submarine_strategy_state(self, feature):
        value = self._retry_transition_read(lambda: self._campaign_submarine_strategy_control(feature))
        return value[0] if value is not None else None

    def click_campaign_submarine_strategy(self, feature, expected):
        value = self._campaign_submarine_strategy_control(feature)
        if value is None or type(expected) is not bool or value[0] is not expected:
            raise SemanticGateClosed('submarine strategy changed before input')
        _, target, generation = value
        semantic_id = 'campaign/map/strategy/submarine/' + feature
        state = self.read_state()
        if state.generation - generation not in (0, 1, 2) or not target.actionable:
            raise SemanticGateClosed('submarine strategy is not actionable')
        if self._blocking_rules(state, semantic_id) or self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed('submarine strategy is blocked')
        self._tap(int(round(target.point.x)), int(round(target.point.y)))
        return ActionReceipt(semantic_id=semantic_id, generation=generation,
            point=target.point, bounds=target.bounds, path=target.path)

    def click_campaign_strategy_formation(self, expected_current: str) -> ActionReceipt:
        formation, icon, _, formation_generation = self._campaign_strategy_selected_formation()
        if formation != expected_current:
            raise SemanticGateClosed("campaign strategy formation changed before input")
        button_path = icon.path.rsplit("/", 1)[0]
        button_state = self.read_state()
        matches = tuple(
            button
            for button in button_state.buttons
            if button.path == button_path
            and button.active_in_hierarchy
            and button.active_and_enabled
            and button.interactable
            and button.raycast_top is True
            and button.point is not None
            and button.bounds is not None
        )
        if len(matches) != 1:
            raise SemanticGateClosed(
                "campaign strategy formation control is absent or ambiguous"
            )
        target = matches[0]
        if abs(button_state.generation - formation_generation) > 2:
            raise SemanticGateClosed("campaign strategy formation snapshots are not coherent")
        if self._blocking_rules(button_state, "campaign/map/strategy/formation/" + formation) or self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("campaign strategy formation is blocked")
        assert target.bounds is not None
        point = Point(
            (target.bounds.left + target.bounds.right) / 2.0,
            (target.bounds.top + target.bounds.bottom) / 2.0,
        )
        self._tap(int(round(point.x)), int(round(point.y)))
        return ActionReceipt(
            semantic_id="campaign/map/strategy/formation/" + formation,
            generation=max(button_state.generation, formation_generation),
            point=point,
            bounds=target.bounds,
            path=target.path,
        )

    def click_campaign_strategy_close(self) -> ActionReceipt:
        if not self.campaign_strategy_panel_visible():
            raise SemanticGateClosed("campaign strategy panel is already closed")
        root = self._campaign_strategy_stage_root()
        path = root + "/right_stage/event/detail/click"
        button_state = self.read_state()
        matches = tuple(
            button
            for button in button_state.buttons
            if button.path == path
            and button.active_in_hierarchy
            and button.active_and_enabled
            and button.interactable
            and button.raycast_top is True
            and button.point is not None
            and button.bounds is not None
        )
        ui_state = self.read_ui_state()
        dock_matches = tuple(
            image
            for image in ui_state.images
            if image.path == root + "/right_stage/event/detail/dock"
            and image.active_in_hierarchy
            and image.active_and_enabled
            and not image.truncated
            and image.sprite == "zhanlue_kuang02"
            and image.bounds is not None
        )
        if len(matches) != 1 or len(dock_matches) != 1:
            raise SemanticGateClosed(
                "campaign strategy close identity is absent or ambiguous"
            )
        target = matches[0]
        if abs(ui_state.generation - button_state.generation) > 2:
            raise SemanticGateClosed("campaign strategy close snapshots are not coherent")
        if self._blocking_rules(button_state, "campaign/map/strategy/close") or self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("campaign strategy close is blocked")
        assert target.bounds is not None
        point = Point(
            (target.bounds.left + target.bounds.right) / 2.0,
            (target.bounds.top + target.bounds.bottom) / 2.0,
        )
        self._tap(int(round(point.x)), int(round(point.y)))
        return ActionReceipt(
            semantic_id="campaign/map/strategy/close",
            generation=max(button_state.generation, ui_state.generation),
            point=point,
            bounds=target.bounds,
            path=target.path,
        )

    def campaign_precombat_visible(self) -> bool:
        """Observe the Campaign preparation page without depending on repair stock."""
        state = self.read_state()
        roots = (
            "OverlayCamera/Overlay/UIMain/ChapterPreCombatUI(Clone)",
            "LevelCamera/Canvas/LevelOrigin/ChapterPreCombatUI(Clone)",
        )
        starts = [b for b in state.buttons
                  if b.path in {root + '/adapt/right/start' for root in roots}
                  and b.active_in_hierarchy and b.active_and_enabled]
        if not starts:
            return False
        if len(starts) != 1:
            raise SemanticGateClosed('campaign precombat identity is ambiguous')
        return True

    def click_campaign_precombat_back(self) -> ActionReceipt:
        """Cancel the exact campaign formation page during safe recovery."""

        button_state = self.read_state()
        roots = (
            "OverlayCamera/Overlay/UIMain/ChapterPreCombatUI(Clone)",
            "LevelCamera/Canvas/LevelOrigin/ChapterPreCombatUI(Clone)",
        )
        matches = tuple(
            button
            for button in button_state.buttons
            if button.path in {root + "/adapt/top/back_btn" for root in roots}
            and button.active_in_hierarchy
            and button.active_and_enabled
            and button.interactable
            and button.raycast_top is True
            and button.point is not None
            and button.bounds is not None
            and button.bounds.contains(button.point)
        )
        if len(matches) != 1:
            raise SemanticGateClosed(
                "campaign precombat back identity is absent or ambiguous"
            )
        target = matches[0]
        root = target.path[: -len("/adapt/top/back_btn")]
        ui_state = self.read_ui_state()
        image_contract = {
            target.path: "icon_bg_front_1920",
            target.path + "/mask": "icon_bg_mask_1920",
            target.path + "/mask/Image": "back_btn",
        }
        images = tuple(
            image
            for image in ui_state.images
            if image.path in image_contract
            and image.active_in_hierarchy
            and image.active_and_enabled
            and not image.truncated
            and image.sprite == image_contract[image.path]
            and image.bounds is not None
        )
        if {image.path for image in images} != set(image_contract):
            raise SemanticGateClosed(
                "campaign precombat back image identity is incomplete"
            )
        assert target.point is not None
        assert target.bounds is not None
        if abs(button_state.generation - ui_state.generation) > 2:
            raise SemanticGateClosed('campaign precombat back frames are incoherent')
        if (self._blocking_rules(button_state, 'campaign/precombat/back')
                or self._foreground_component() != self.fingerprint.component):
            raise SemanticGateClosed('campaign precombat back is blocked')
        self._tap(int(round(target.point.x)), int(round(target.point.y)))
        return ActionReceipt(
            semantic_id="campaign/precombat/back",
            generation=max(button_state.generation, ui_state.generation),
            point=target.point,
            bounds=target.bounds,
            path=target.path,
        )

    def campaign_map_displayed_fleet_index(self) -> int:
        buttons = self.read_state()
        state = self.read_ui_state()
        return self._campaign_displayed_fleet_index_from_states(buttons, state)

    @staticmethod
    def _campaign_displayed_fleet_index_from_states(buttons, state) -> int:
        if not buttons.generation <= state.generation <= buttons.generation+2:
            raise SemanticGateClosed('campaign fleet index frame is incoherent')
        stage_roots = tuple(
            root
            for root in (
                "OverlayCamera/Overlay/UIMain/top/LevelStageView(Clone)",
                "LevelCamera/Canvas/LevelOrigin/top/LevelStageView(Clone)",
            )
            if sum(b.path == root + '/top_stage/back_button' and b.active_in_hierarchy
                   and b.active_and_enabled for b in buttons.buttons) == 1
            and any(t.path == root+'/top_stage/msg_panel/fleet_info/number'
                    and t.active_in_hierarchy and t.active_and_enabled for t in state.texts)
        )
        if len(stage_roots) != 1:
            raise SemanticGateClosed(
                "campaign map fleet status root is absent or ambiguous"
            )
        path = stage_roots[0] + "/top_stage/msg_panel/fleet_info/number"
        matches = tuple(
            item
            for item in state.texts
            if item.path == path
            and item.active_in_hierarchy
            and item.active_and_enabled
            and not item.truncated
            and re.fullmatch(r"[12]", item.text.strip()) is not None
        )
        if len(matches) != 1:
            raise SemanticGateClosed(
                "campaign map displayed fleet index is absent or ambiguous"
            )
        return int(matches[0].text.strip())

    def close_campaign_battle_fail_tip_if_present(self) -> bool:
        """Close the exact post-defeat recommendation panel, if visible."""

        button_state = self.read_state()
        path = "OverlayCamera/Overlay/UIMain/BattleFailTipUI(Clone)/Main/CloseBtn"
        matches = tuple(
            button for button in button_state.buttons if button.path == path
        )
        if not matches:
            return False
        if len(matches) != 1:
            raise SemanticGateClosed("campaign defeat close control is ambiguous")
        button = matches[0]
        ui_state = self.read_ui_state()
        defeat_path = (
            "OverlayCamera/Overlay/UIMain/BattleFailTipUI(Clone)/"
            "BG/BG/bg_fail/bg03/Text"
        )
        defeat = tuple(
            item
            for item in ui_state.texts
            if item.path == defeat_path
            and item.text.strip() == "DEFEAT"
            and item.active_in_hierarchy
            and item.active_and_enabled
            and not item.truncated
        )
        if (
            len(defeat) != 1
            or not button.active_in_hierarchy
            or not button.active_and_enabled
            or not button.interactable
            or button.raycast_top is False
            or button.bounds is None
        ):
            raise SemanticGateClosed("campaign defeat tip identity is incomplete")
        point = Point(
            x=(button.bounds.left + button.bounds.right) / 2.0,
            y=(button.bounds.top + button.bounds.bottom) / 2.0,
        )
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("foreground changed immediately before input")
        self._tap(int(round(point.x)), int(round(point.y)))
        return True

    def close_campaign_fleet_invalid_tip_if_present(self) -> bool:
        """Acknowledge the exact post-defeat fleet auto-switch notice."""

        button_state = self.read_state()
        confirm_path = (
            "OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/button_container/"
            "custom_button_1(Clone)"
        )
        matches = tuple(
            button
            for button in button_state.buttons
            if button.path == confirm_path or button.path.startswith(confirm_path + "/")
        )
        if not matches:
            return False
        actionable = tuple(
            button
            for button in matches
            if button.active_in_hierarchy
            and button.active_and_enabled
            and button.interactable
            and button.raycast_top is not False
            and button.bounds is not None
        )
        ui_state = self.read_ui_state()
        content_path = (
            "OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/msg_panel/content"
        )
        content = tuple(
            item
            for item in ui_state.texts
            if item.path == content_path
            and "当前选中舰队无法成型" in item.text
            and "第一舰队" in item.text
            and item.active_in_hierarchy
            and item.active_and_enabled
            and not item.truncated
        )
        if len(actionable) != 1 or len(content) != 1:
            raise SemanticGateClosed("campaign fleet-invalid tip is ambiguous")
        button = actionable[0]
        assert button.bounds is not None
        point = Point(
            x=(button.bounds.left + button.bounds.right) / 2.0,
            y=(button.bounds.top + button.bounds.bottom) / 2.0,
        )
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("foreground changed immediately before input")
        self._tap(int(round(point.x)), int(round(point.y)))
        return True

    def campaign_withdraw_control(self, *, confirm: bool = False):
        """Observe the exact map retreat or its own confirmation, without input."""
        state = self.read_state()
        ui = self.read_ui_state()
        if not state.generation <= ui.generation <= state.generation + 2:
            raise SemanticGateClosed('campaign withdrawal frames are incoherent')
        if confirm:
            root = 'OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/'
            texts = [t for t in ui.texts if t.path == root + 'msg_panel/content'
                     and t.active_in_hierarchy and t.active_and_enabled]
            if not texts:
                return None
            if len(texts) != 1 or texts[0].truncated:
                raise SemanticGateClosed('campaign withdrawal content is ambiguous')
            if '真的要' not in texts[0].text or '撤退' not in texts[0].text:
                return None
            path = root + 'button_container/custom_button_1(Clone)'
        else:
            if not self.campaign_is_in_map():
                return None
            paths = [b.path for b in state.buttons if b.path.endswith(
                '/LevelStageView(Clone)/bottom_stage/Normal/retreat_button')
                and b.active_in_hierarchy and b.active_and_enabled]
            if len(paths) != 1:
                raise SemanticGateClosed('campaign withdrawal control is ambiguous')
            path = paths[0]
        targets = [b for b in state.buttons if b.path == path
                   and b.active_in_hierarchy and b.active_and_enabled]
        if len(targets) != 1:
            raise SemanticGateClosed('campaign withdrawal control is ambiguous')
        target = targets[0]
        if (not target.interactable or target.raycast_top is not True
                or target.bounds is None or target.point is None
                or not target.bounds.contains(target.point)):
            return None
        return target, max(state.generation, ui.generation)

    def click_campaign_withdraw(self, *, confirm: bool = False) -> ActionReceipt:
        control = self.campaign_withdraw_control(confirm=confirm)
        if control is None:
            raise SemanticGateClosed('campaign withdrawal target is not actionable')
        target, generation = control
        semantic_id = 'campaign/map/withdraw/' + ('confirm' if confirm else 'open')
        state = self.read_state()
        if abs(state.generation - generation) > 2:
            raise SemanticGateClosed('campaign withdrawal input frame changed')
        if (self._blocking_rules(state, semantic_id)
                or self._foreground_component() != self.fingerprint.component):
            raise SemanticGateClosed('campaign withdrawal input is blocked')
        point = target.point
        self._tap(int(round(point.x)), int(round(point.y)))
        return ActionReceipt(semantic_id=semantic_id, generation=generation,
                             point=point, bounds=target.bounds, path=target.path)

    def open_campaign_withdraw_confirmation(self) -> bool:
        """Open, but do not confirm, the exact active campaign withdrawal."""

        entry = self.campaign_map_entry_state()
        paths = tuple(
            path
            for path in entry.button_paths
            if path.endswith(
                "/LevelStageView(Clone)/bottom_stage/Normal/retreat_button"
            )
        )
        if len(paths) != 1:
            raise SemanticGateClosed("campaign withdrawal control is ambiguous")
        state = self.read_state()
        matches = tuple(button for button in state.buttons if button.path == paths[0])
        if len(matches) != 1:
            raise SemanticGateClosed("campaign withdrawal control changed")
        button = matches[0]
        if (
            not button.active_in_hierarchy
            or not button.active_and_enabled
            or not button.interactable
            or button.raycast_top is False
            or button.bounds is None
        ):
            raise SemanticGateClosed("campaign withdrawal control is not actionable")
        point = Point(
            x=(button.bounds.left + button.bounds.right) / 2.0,
            y=(button.bounds.top + button.bounds.bottom) / 2.0,
        )
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("foreground changed immediately before input")
        self._tap(int(round(point.x)), int(round(point.y)))
        return True

    def confirm_campaign_withdrawal_if_present(self) -> bool:
        """Confirm only the exact campaign withdrawal dialog."""

        button_state = self.read_state()
        ui_state = self.read_ui_state()
        content_path = (
            "OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/msg_panel/content"
        )
        content = tuple(
            item
            for item in ui_state.texts
            if item.path == content_path
            and "真的要" in item.text
            and "撤退" in item.text
            and item.active_in_hierarchy
            and item.active_and_enabled
            and not item.truncated
        )
        path = (
            "OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/button_container/"
            "custom_button_1(Clone)"
        )
        buttons = tuple(
            button for button in button_state.buttons if button.path == path
        )
        if not content and not buttons:
            return False
        if len(content) != 1 or len(buttons) != 1:
            raise SemanticGateClosed("campaign withdrawal dialog is ambiguous")
        button = buttons[0]
        if (
            not button.active_in_hierarchy
            or not button.active_and_enabled
            or not button.interactable
            or button.raycast_top is not True
            or button.bounds is None
        ):
            raise SemanticGateClosed(
                "campaign withdrawal confirmation is not actionable"
            )
        point = Point(
            x=(button.bounds.left + button.bounds.right) / 2.0,
            y=(button.bounds.top + button.bounds.bottom) / 2.0,
        )
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("foreground changed immediately before input")
        self._tap(int(round(point.x)), int(round(point.y)))
        return True

    def _campaign_map_fleet_switch_button(self) -> ButtonState:
        entry = self.campaign_map_entry_state()
        stage_roots = tuple(
            root
            for root in (
                "OverlayCamera/Overlay/UIMain/top/LevelStageView(Clone)",
                "LevelCamera/Canvas/LevelOrigin/top/LevelStageView(Clone)",
            )
            if root + "/top_stage/back_button" in entry.button_paths
        )
        if len(stage_roots) != 1:
            raise SemanticGateClosed(
                "campaign map fleet-switch root is absent or ambiguous"
            )
        path = stage_roots[0] + "/bottom_stage/Normal/switch_button"
        state = self.read_state()
        matches = tuple(button for button in state.buttons if button.path == path)
        if len(matches) != 1:
            raise SemanticGateClosed(
                "campaign map fleet-switch control is absent or ambiguous"
            )
        button = matches[0]
        if (
            not button.active_in_hierarchy
            or not button.active_and_enabled
            or not button.interactable
            or button.raycast_top is not True
            or button.point is None
            or button.bounds is None
        ):
            raise SemanticGateClosed(
                "campaign map fleet-switch control is not actionable"
            )
        return button

    def campaign_map_fleet_switch_available(self) -> bool:
        self._campaign_map_fleet_switch_button()
        return True

    def click_campaign_map_fleet_switch(self) -> ActionReceipt:
        button = self._campaign_map_fleet_switch_button()
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("foreground changed immediately before input")
        assert button.bounds is not None
        point = Point(
            x=(button.bounds.left + button.bounds.right) / 2.0,
            y=(button.bounds.top + button.bounds.bottom) / 2.0,
        )
        self._tap(int(round(point.x)), int(round(point.y)))
        return ActionReceipt(
            semantic_id="campaign/map/fleet/switch",
            generation=self._last_generation or 0,
            point=point,
            bounds=button.bounds,
            path=button.path,
        )

    def campaign_fleet_hp(self) -> Tuple[float, ...]:
        """Read the six visible campaign HP bars in ALAS slot order."""

        self.campaign_map_entry_state()
        state = self.read_ui_state()
        suffix = "/left_stage/fleet/"
        bars = tuple(
            item
            for item in state.images
            if suffix in item.path
            and item.path.endswith(("/blood/fillarea/green", "/blood/fillarea/red"))
            and item.active_in_hierarchy
            and item.active_and_enabled
            and not item.truncated
            and item.bounds is not None
        )
        if len(bars) != 6:
            raise SemanticGateClosed("campaign fleet HP bars are absent or incomplete")
        ordered = tuple(sorted(bars, key=lambda item: item.bounds.top))
        top_values = tuple(item.bounds.top for item in ordered)
        if any(
            not 95.0 <= later - earlier <= 105.0
            for earlier, later in zip(top_values, top_values[1:])
        ):
            raise SemanticGateClosed("campaign fleet HP slot order is invalid")
        full_width = 66.333
        values = tuple(
            max(
                0.0,
                min(1.0, (item.bounds.right - item.bounds.left) / full_width),
            )
            for item in ordered
        )
        return values

    def _campaign_vitals_slots(self, fleet_index: int, *, precombat=False, expected_occupied=None,
                               expected_identity=None):
        """Pair each occupied portrait with its surface's actual HP encoding."""
        before = self.read_state()
        if precombat:
            from .campaign_health import PRECOMBAT
            if self.campaign_emergency_repair_state() is None:
                raise SemanticGateClosed('campaign HP precombat is unavailable')
            prefix = PRECOMBAT + 'adapt/middle/fleet/'
            axis = 'left'
        else:
            self.campaign_map_entry_state()
            if self.campaign_map_displayed_fleet_index() != fleet_index:
                raise SemanticGateClosed('campaign HP belongs to another displayed fleet')
            prefix = '/LevelStageView(Clone)/left_stage/fleet/'
            axis = 'top'
        ui = self.read_ui_state()
        if not before.generation <= ui.generation <= before.generation + 2:
            raise SemanticGateClosed('campaign HP-control frames are incoherent')
        count = 6 if expected_occupied is None else expected_occupied
        if type(count) is not int or not 2 <= count <= 6:
            raise SemanticGateClosed('campaign occupied ship count is invalid')
        def collect(endings):
            items = [i for i in ui.images if prefix in i.path and i.path.endswith(endings)
                     and i.active_in_hierarchy and i.active_and_enabled]
            if len(items) != count or any(i.truncated or not i.sprite or i.bounds is None for i in items):
                raise SemanticGateClosed('campaign HP-control occupied slots are incomplete')
            return sorted(items, key=lambda i: (0 if '/main/' in i.path else 1,
                                                getattr(i.bounds, axis)))
        portraits = collect('/icon_bg/icon')
        bars = collect(('/blood/fillarea/green', '/blood/fillarea/red'))
        if expected_identity is not None:
            identity = tuple(tuple(sorted(i.sprite for i in portraits if '/' + group + '/' in i.path))
                             for group in ('main', 'vanguard'))
            if identity != expected_identity:
                raise SemanticGateClosed('campaign inherited fleet identity changed')
        slots = []
        for group in ('main', 'vanguard'):
            ships = [i for i in portraits if '/' + group + '/' in i.path]
            health = [i for i in bars if '/' + group + '/' in i.path]
            if not 1 <= len(ships) <= 3 or len(ships) != len(health):
                raise SemanticGateClosed('campaign HP-control group membership is incomplete')
            for items in (ships, health):
                positions = [getattr(i.bounds, axis) for i in items]
                if any(a >= b for a, b in zip(positions, positions[1:])):
                    raise SemanticGateClosed('campaign HP-control slot identity is ambiguous')
            for portrait, bar in zip(ships, health):
                if (not portrait.bounds.top < bar.bounds.top < portrait.bounds.bottom
                        or not portrait.bounds.left < bar.bounds.left < portrait.bounds.right
                        or not 0.0 <= bar.fill_amount <= 1.0):
                    raise SemanticGateClosed('campaign HP-control portrait and HP slot disagree')
                slots.append((portrait, bar))
            slots.extend([None] * (3 - len(ships)))
        if sum(slot is not None for slot in slots) != count:
            raise SemanticGateClosed('campaign HP-control group identity is unknown')
        return slots, ui

    def campaign_hp_control_snapshot(self, fleet_index: int, *, precombat=False, expected_occupied=None,
                                     expected_identity=None):
        slots, _ = self._campaign_vitals_slots(fleet_index, precombat=precombat,
                                              expected_occupied=expected_occupied, expected_identity=expected_identity)
        # The map's fillAmount is an unused prefab value; precombat drives it.
        hp = tuple(0.0 if slot is None else (slot[1].fill_amount if precombat else
            min(1.0, max(0.0, (slot[1].bounds.right - slot[1].bounds.left) / 66.333)))
            for slot in slots)
        return hp, tuple(slot is not None for slot in slots)

    def campaign_sparse_fleet_levels(self, fleet_index: int, *, expected_occupied: int,
                                     expected_identity=None):
        slots, ui = self._campaign_vitals_slots(fleet_index, expected_occupied=expected_occupied,
                                               expected_identity=expected_identity)
        values = []
        used = set()
        for slot in slots:
            if slot is None:
                values.append(0)
                continue
            portrait, _ = slot
            root = portrait.path.rsplit('/icon_bg/icon', 1)[0]
            matches = [(index, t) for index, t in enumerate(ui.texts)
                       if t.path == root + '/icon_bg/lv/Text'
                       and t.active_in_hierarchy and t.active_and_enabled
                       and t.bounds is not None and not t.truncated
                       and portrait.bounds.top <= (t.bounds.top + t.bounds.bottom) / 2 < portrait.bounds.bottom
                       and portrait.bounds.left <= (t.bounds.left + t.bounds.right) / 2 < portrait.bounds.right]
            if len(matches) != 1 or matches[0][0] in used:
                raise SemanticGateClosed('campaign sparse fleet levels are incomplete or ambiguous')
            index, text = matches[0]
            if re.fullmatch(r'(?:[1-9]|[1-9][0-9]|1[01][0-9]|12[0-5])', text.text.strip()) is None:
                raise SemanticGateClosed('campaign fleet level is outside the pinned range')
            used.add(index)
            values.append(int(text.text.strip()))
        return tuple(values)

    def campaign_fleet_levels(self) -> Tuple[int, ...]:
        """Read the six visible campaign levels in ALAS slot order."""

        self.campaign_map_entry_state()
        state = self.read_ui_state()
        suffix = "/left_stage/fleet/"
        levels = tuple(
            item
            for item in state.texts
            if suffix in item.path
            and item.path.endswith("/icon_bg/lv/Text")
            and item.name == "Text"
            and item.active_in_hierarchy
            and item.active_and_enabled
            and not item.truncated
            and item.bounds is not None
        )
        if len(levels) != 6:
            raise SemanticGateClosed("campaign fleet levels are absent or incomplete")
        ordered = tuple(sorted(levels, key=lambda item: item.bounds.top))
        top_values = tuple(item.bounds.top for item in ordered)
        if any(
            not 95.0 <= later - earlier <= 105.0
            for earlier, later in zip(top_values, top_values[1:])
        ):
            raise SemanticGateClosed("campaign fleet level slot order is invalid")
        values = []
        for item in ordered:
            value = item.text.strip()
            if re.fullmatch(r"(?:[1-9]|[1-9][0-9]|1[01][0-9]|12[0-5])", value) is None:
                raise SemanticGateClosed(
                    "campaign fleet level is outside the pinned range"
                )
            values.append(int(value))
        return tuple(values)

    def campaign_page_is_normal(self) -> bool:
        if self.campaign_menu_is_entry() or self.exists("reward/campaign-total/exit"):
            return False
        try:
            self.campaign_page_state()
        except SemanticTargetMissing:
            return False
        except SemanticGateClosed as exc:
            if str(exc) == "campaign entrance is not a chapter page":
                return False
            # Settlement may appear between the initial probe and the page
            # read. It is not a chapter page; the original handler owns exit.
            if (str(exc) == "campaign page identity is not proven"
                    and self.exists("reward/campaign-total/exit")):
                return False
            raise
        return True

    def _campaign_urgent_notice_matches(self, state) -> bool:
        root = "Msgbox(Clone)/window/"
        controls = [b for b in state.buttons
                    if root + "button_container/" in b.path and b.active_in_hierarchy]
        if (len(controls) != 1 or not controls[0].path.endswith(
                root + "button_container/custom_button_1(Clone)")):
            return False
        ui = self.read_ui_state()
        if abs(ui.generation - state.generation) > 2:
            raise SemanticGateClosed("campaign urgent notice generations are incoherent")
        def texts(suffix):
            return [t.text.strip() for t in ui.texts if t.path.endswith(root + suffix)
                    and t.active_in_hierarchy and t.active_and_enabled
                    and not t.truncated and t.bounds is not None]
        content = texts("msg_panel/content")
        return (len(content) == 1
                and re.fullmatch(r"出现紧急委托《[^《》\r\n]+》", content[0]) is not None
                and texts("top/bg/infomation/title_en") == ["INFORMATION"]
                and ["".join(t.split()) for t in texts(
                    "button_container/custom_button_1(Clone)/pic")] == ["确定"])

    def campaign_stage_state(self, stage_code: str) -> CampaignStageState:
        """Return one exact visible stage from the typed campaign page."""

        if (
            re.fullmatch(r"(?:[1-9][0-9]*-[1-9][0-9]*|[a-z]+[0-9]*)", stage_code)
            is None
        ):
            raise SemanticGateClosed("campaign stage code is not canonical")
        matches = tuple(
            stage
            for stage in self.campaign_page_state().stages
            if stage.stage_code == stage_code
        )
        if len(matches) != 1:
            raise SemanticGateClosed("campaign stage is absent or ambiguous")
        return matches[0]

    def campaign_stage_actionable(self, stage_code: str) -> bool:
        button = self.campaign_stage_state(stage_code).button
        if button.actionable:
            return True
        # Current LevelSelectSPFullUI event nodes expose the reviewed wide
        # ``main`` hit target without a raycast-top result.  click_campaign_stage
        # already applies this exact path-scoped admission; presence must use
        # the same predicate or ALAS can never reach the click boundary.
        return bool(
            (
                "LevelSelectSPFullUI(Clone)/Battle/Nodes/Chapter_" in button.path
                or re.search(
                    r"LevelMainScene\(Clone\)/float/levels/items/"
                    r"Chapter_21[0-9]{5}/main$",
                    button.path,
                )
                is not None
            )
            and button.path.endswith("/main")
            and button.active_in_hierarchy
            and button.active_and_enabled
            and button.interactable
            and button.raycast_top is None
            and button.point is not None
            and button.bounds is not None
        )

    def campaign_auto_search_selected(self) -> bool:
        """Return the effective auto-search state on campaign preparation."""

        state = self.read_ui_state()
        if state.method_mask & 0x1 == 0:
            raise SemanticGateClosed("typed Unity Toggle snapshot is incomplete")
        matches = self._toggle_matches(state, "campaign/map-preparation/auto-search")
        if len(matches) != 1:
            raise SemanticGateClosed(
                "campaign auto-search toggle is absent or ambiguous"
            )
        toggle = matches[0]
        auto_suffixes = {
            "LevelInfoSPUI(Clone)/panel/BottomExtra/LoopGroup/"
            "view/container/AutoFight": (
                "LevelInfoSPUI(Clone)/panel/BottomExtra/LoopGroup/Loop/Toggle/off"
            ),
            "LevelStageInfoView(Clone)/panel/BottomExtra/LoopGroup/"
            "view/container/AutoFight": (
                "LevelStageInfoView(Clone)/panel/BottomExtra/LoopGroup/Loop/"
                "Toggle/off"
            ),
        }
        loop_off_suffix = next(
            (
                off_suffix
                for auto_suffix, off_suffix in auto_suffixes.items()
                if toggle.path.endswith(auto_suffix)
            ),
            None,
        )
        if loop_off_suffix is not None:
            loop_off = tuple(
                image
                for image in state.images
                if image.name == "off"
                and image.path.endswith(loop_off_suffix)
                and image.sprite == "live2d_off"
                and image.active_in_hierarchy
                and image.active_and_enabled
                and image.bounds is not None
            )
            if len(loop_off) > 1:
                raise SemanticGateClosed("campaign loop-off identity is ambiguous")
            if loop_off:
                # Both stage-info variants retain the saved AutoFight Toggle
                # value while loop mode is off.  The nested toggle is not an
                # effective or mutable state until the outer mode is enabled.
                return False
        return toggle.checked
