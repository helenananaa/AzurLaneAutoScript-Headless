"""Event for the typed ALAS boundary."""

from __future__ import annotations

import re
from typing import Optional, Tuple
from .contracts import (
    ActionReceipt,
    ButtonState,
    CampaignPageState,
    CampaignStageState,
    OracleState,
    Point,
    ToggleState,
    UiState,
)
from .errors import SemanticGateClosed, SemanticTargetMissing


class EventOracle:
    """Event operations sharing the oracle frame and input boundary."""

    def _player_profile_back_proven(self, state: OracleState) -> bool:
        buttons = self._matches(state, 'player/profile/back')
        if len(buttons) > 1:
            raise SemanticGateClosed('player profile Back is ambiguous')
        if not buttons:
            return False
        button = buttons[0]
        if not (button.active_in_hierarchy and button.active_and_enabled
                and button.interactable and button.raycast_top is not False
                and button.point is not None and button.bounds is not None
                and button.bounds.contains(button.point)):
            return False
        ui = self.read_ui_state()
        if not state.generation <= ui.generation <= state.generation + 2:
            raise SemanticGateClosed('player profile Back snapshots are not coherent')
        if ui.image_truncated:
            raise SemanticGateClosed('player profile Back image snapshot is incomplete')
        images = [image for image in ui.images
                  if image.path == button.path + '/mask/Image']
        return bool(len(images) == 1 and images[0].sprite == 'back_btn'
                    and images[0].active_in_hierarchy and images[0].active_and_enabled
                    and not images[0].truncated and images[0].raycast_top is not False
                    and images[0].bounds is not None
                    and 0 <= images[0].bounds.left < images[0].bounds.right <= self.fingerprint.width
                    and 0 <= images[0].bounds.top < images[0].bounds.bottom <= self.fingerprint.height
                    and images[0].bounds.contains(button.point))

    def _activity_archive_home_proven(self, state: OracleState) -> bool:
        target_id = 'archive/activity-list/home'
        buttons = self._matches(state, target_id)
        if len(buttons) > 1:
            raise SemanticGateClosed('activity archive Home is ambiguous')
        if not buttons:
            return False
        button = buttons[0]
        if not (button.active_in_hierarchy and button.active_and_enabled
                and button.interactable and button.raycast_top is not False
                and button.point is not None and button.bounds is not None
                and button.bounds.contains(button.point)):
            return False
        ui = self.read_ui_state()
        if not state.generation <= ui.generation <= state.generation + 2:
            raise SemanticGateClosed('activity archive Home snapshots are not coherent')
        if ui.image_truncated:
            raise SemanticGateClosed('activity archive Home image snapshot is incomplete')
        images = tuple(image for image in ui.images if image.path == button.path
                       and image.active_in_hierarchy and image.active_and_enabled)
        return bool(len(images) == 1 and not images[0].truncated
                    and images[0].sprite == 'btn_home'
                    and images[0].raycast_target and images[0].raycast_top is not False
                    and images[0].color[3] > 0 and images[0].bounds == button.bounds
                    and not self._blocking_rules(state, target_id))

    def campaign_event_entrance_available(self) -> bool:
        """Report whether the proven campaign menu exposes an event card."""

        if not self.campaign_menu_is_entry():
            raise SemanticGateClosed("campaign event availability requires menu")
        state = self.read_state()
        prefix = "UICamera/Canvas/UIMain/LevelMainScene(Clone)/entrance/enters/"
        event_buttons = tuple(
            button
            for button in state.buttons
            if button.path.startswith(prefix)
            and button.name not in ("enter_main",)
            and "/enter_world/" not in button.path
            and button.active_in_hierarchy
            and button.active_and_enabled
            and button.interactable
            and button.bounds is not None
        )
        # Current menus use a distinct event entrance under `enters`; if it is
        # absent, ALAS' CAMPAIGN_MENU_NO_EVENT condition is true.
        return bool(event_buttons)

    def click_campaign_event_entrance(self) -> ActionReceipt:
        """Click the exact current event card whose child owns the raycast."""

        if not self.campaign_menu_is_entry():
            raise SemanticGateClosed("campaign event entrance requires menu")
        state = self.read_state()
        target = self._unique(state, "campaign-menu/event")
        if not (
            target.active_in_hierarchy
            and target.active_and_enabled
            and target.interactable
            and target.raycast_top is None
            and target.point is not None
            and target.bounds is not None
            and target.bounds.contains(target.point)
            and not self._blocking_rules(state, "campaign-menu/event")
        ):
            raise SemanticGateClosed("campaign event entrance is not actionable")
        self._tap(int(round(target.point.x)), int(round(target.point.y)))
        return ActionReceipt(
            semantic_id="campaign-menu/event",
            generation=state.generation,
            point=target.point,
            bounds=target.bounds,
            path=target.path,
        )

    def event_campaign_page_visible(self) -> bool:
        return self._event_campaign_page_visible_in_state(self.read_state())

    def event_campaign_page_state(self) -> CampaignPageState:
        """Prove one complete current event battle selector without input."""

        button_state = self.read_state()
        root_marker = "/LevelSelectSPFullUI(Clone)"
        active_event_buttons = tuple(
            button
            for button in button_state.buttons
            if root_marker in button.path
            and button.active_in_hierarchy
            and button.active_and_enabled
        )
        roots = {
            button.path[: button.path.index(root_marker) + len(root_marker)]
            for button in active_event_buttons
            if button.path.count(root_marker) == 1
        }
        if not active_event_buttons:
            raise SemanticTargetMissing("event campaign page is absent")
        if len(roots) != 1 or any(
            button.path.count(root_marker) != 1
            for button in active_event_buttons
        ):
            raise SemanticGateClosed("event campaign page root is ambiguous")
        root = next(iter(roots))
        if not root.endswith(
            "/LevelMainScene(Clone)/LevelSelectSPFullUI(Clone)"
        ):
            raise SemanticGateClosed("event campaign page root is unsupported")
        page_root = root[: -len("/LevelSelectSPFullUI(Clone)")]

        markers = tuple(
            button
            for button in self._matches(button_state, "event/mode/story")
            if button.path == root + "/Battle/Mask/Story/Switch"
            and button.active_in_hierarchy
            and button.active_and_enabled
            and button.interactable
            and button.bounds is not None
        )
        if len(markers) != 1:
            raise SemanticGateClosed(
                "event campaign battle selector marker is absent or ambiguous"
            )

        back_matches = tuple(
            button
            for button in self._matches(button_state, "campaign-menu/page/back")
            if button.active_in_hierarchy
            and button.active_and_enabled
        )
        if len(back_matches) != 1:
            raise SemanticGateClosed(
                "event campaign page back identity is absent or ambiguous"
            )
        back = back_matches[0]
        if back.path != page_root + "/top/top_chapter/back_button":
            raise SemanticGateClosed(
                "event campaign page back belongs to another page root"
            )
        if not back.actionable or self._blocking_rules(
            button_state, "campaign-menu/page/back"
        ):
            raise SemanticGateClosed("event campaign page back is not available")

        if any(
            button.active_in_hierarchy
            and button.active_and_enabled
            and (
                "ActivityMainUI(Clone)/" in button.path
                or "/LevelMainScene(Clone)/float/levels/items/Chapter_"
                in button.path
            )
            for button in button_state.buttons
        ):
            raise SemanticGateClosed(
                "event campaign page overlaps another page root"
            )
        if self._event_campaign_detail_visible(button_state) or any(
            button.active_in_hierarchy
            and (
                "/LevelStageInfoView(Clone)/" in button.path
                or "/LevelInfoSPUI(Clone)/" in button.path
                or "/LevelFleetSelectView(Clone)/" in button.path
            )
            for button in button_state.buttons
        ):
            raise SemanticGateClosed(
                "event campaign page overlaps a preparation layer"
            )

        stage_control = re.compile(
            re.escape(root)
            + r"/Battle/Nodes/Chapter_([0-9]+)/main$"
        )
        stage_ids = []
        for button in button_state.buttons:
            match = stage_control.fullmatch(button.path)
            if (
                button.name == "main"
                and button.active_in_hierarchy
                and button.active_and_enabled
                and button.bounds is not None
                and match is not None
            ):
                stage_ids.append(match.group(1))
        if not stage_ids or len(set(stage_ids)) != len(stage_ids):
            raise SemanticGateClosed(
                "event campaign stage buttons are absent or ambiguous"
            )

        ui_state = self.read_ui_state()
        if (
            ui_state.generation < button_state.generation
            or ui_state.generation > button_state.generation + 2
        ):
            raise SemanticGateClosed("event campaign snapshots are not coherent")
        return self._event_campaign_page_state(button_state, ui_state)

    def event_points(self) -> int:
        """Read the exact event-point counter from a proven event selector."""

        return self._retry_transition_read(self._event_points_once)

    def event_coin(self, stage_code: Optional[str] = None) -> int:
        """Read the global coin counter on a proven selector, detail or map."""

        return self._retry_transition_read(
            lambda: self._event_coin_once(stage_code=stage_code)
        )

    def _event_coin_once(self, *, stage_code: Optional[str]) -> int:
        try:
            surface_generation = self.event_campaign_page_state().generation
            surface_kind = "selector"
        except SemanticGateClosed:
            if stage_code is None:
                raise
            preparation = self.campaign_preparation_state(stage_code)
            if preparation is None:
                # Native auto-search watches resources while the fleet moves.
                # The same global ResPanel is retained on a proven map; no
                # selector/detail underlay or pixel observation is required.
                entry = self.campaign_map_entry_state()
                if self._blocking_rules(self.read_state(), "ui/absence-probe"):
                    raise SemanticGateClosed("campaign map coin surface is obscured")
                surface_generation = entry.generation
                surface_kind = "campaign-map"
            else:
                surface_generation = preparation.generation
                surface_kind = preparation.kind
        ui_state = self.read_ui_state()
        if surface_kind == "selector":
            surface_after_generation = self.event_campaign_page_state().generation
        elif surface_kind == "campaign-map":
            surface_after_generation = self.campaign_map_entry_state().generation
            if self._blocking_rules(self.read_state(), "ui/absence-probe"):
                raise SemanticGateClosed("campaign map coin surface is obscured")
        else:
            assert stage_code is not None
            preparation_after = self.campaign_preparation_state(stage_code)
            if preparation_after is None or preparation_after.kind != surface_kind:
                raise SemanticGateClosed("event coin surface changed during observation")
            surface_after_generation = preparation_after.generation
        if (
            ui_state.generation < surface_generation
            or ui_state.generation > surface_after_generation
        ):
            raise SemanticGateClosed("event coin snapshots are not coherent")
        suffix = "ResPanel(Clone)/frame/gold/gold_value"
        matches = tuple(
            item
            for item in ui_state.texts
            if item.path.endswith(suffix)
            and item.active_in_hierarchy
            and item.active_and_enabled
            and not item.truncated
            and item.bounds is not None
        )
        if (
            len(matches) != 1
            or re.fullmatch(r"[0-9]+", matches[0].text.strip()) is None
        ):
            raise SemanticGateClosed("event coin counter is absent or malformed")
        return int(matches[0].text.strip())

    def _event_points_once(self) -> int:
        try:
            _buttons, raid_ui, raid_root, _stages = (
                self._amatsukaze_raid_page_state()
            )
        except SemanticGateClosed as exc:
            if str(exc) not in (
                "current Raid page is absent",
                "current Raid page is obscured by fleet selection",
            ):
                raise
        else:
            path = raid_root + "/adapt/right/ptaward/Text"
            matches = tuple(
                item
                for item in raid_ui.texts
                if item.path == path
                and item.active_in_hierarchy
                and item.active_and_enabled
                and not item.truncated
                and item.bounds is not None
                and re.fullmatch(r"[0-9]+", item.text.strip()) is not None
            )
            if len(matches) != 1:
                raise SemanticGateClosed(
                    "current Raid point counter is absent or ambiguous"
                )
            return int(matches[0].text.strip())

        ui_state = self.read_ui_state()
        page = self.event_campaign_page_state()
        if (
            page.generation < ui_state.generation
            or page.generation > ui_state.generation + 2
        ):
            raise SemanticGateClosed("event point snapshots are not coherent")
        suffix = (
            "LevelMainScene(Clone)/main/right_chapter/"
            "event_btns/pt_text/Text"
        )
        matches = tuple(
            item
            for item in ui_state.texts
            if item.path.endswith(suffix)
            and item.active_in_hierarchy
            and item.active_and_enabled
            and not item.truncated
            and item.bounds is not None
        )
        if len(matches) != 1:
            raise SemanticGateClosed("event point counter is absent or ambiguous")
        value = re.fullmatch(r"[xX]([0-9]+)", matches[0].text.strip())
        if value is None:
            raise SemanticGateClosed("event point counter is malformed")
        return int(value.group(1))

    def _event_campaign_page_visible_in_state(self, state: OracleState) -> bool:
        return bool(
            len(self._matches(state, "event/mode/story")) == 1
            or any(
                button.path.endswith("LevelSelectSPFullUI(Clone)/Story/Battle/Switch")
                for button in state.buttons
            )
            or self._event_campaign_detail_visible(state)
        )

    def event_campaign_stage_selector_visible(self) -> bool:
        """Require at least one concrete event-stage node, not its detail."""

        state = self.read_state()
        if self._event_campaign_detail_visible(state):
            return False
        stage_pattern = re.compile(
            r".*/LevelSelectSPFullUI\(Clone\)/Battle/Nodes/"
            r"Chapter_[1-9][0-9]*/main$"
        )
        stages = tuple(
            button
            for button in state.buttons
            if stage_pattern.fullmatch(button.path)
            and button.name == "main"
            and button.active_in_hierarchy
            and button.active_and_enabled
            and button.interactable
            and button.bounds is not None
        )
        mode_markers = tuple(
            button
            for button in state.buttons
            if button.path.endswith(
                "LevelSelectSPFullUI(Clone)/Battle/Mask/Story/Switch"
            )
            and button.active_in_hierarchy
            and button.active_and_enabled
            and button.interactable
        )
        return bool(stages and len(mode_markers) == 1)

    def _event_campaign_aside_tab(
        self, destination: str
    ) -> Tuple[OracleState, ButtonState, bool]:
        """Resolve one post-2024 event chapter tab from typed text and geometry."""

        labels = {
            "part1": "上篇",
            "part2": "下篇",
            "sp": "SP",
            "ex": "EX",
        }
        label = labels.get(destination)
        if label is None:
            raise SemanticGateClosed("event campaign aside destination is invalid")

        button_state = self.read_state()
        ui_state = self.read_ui_state()
        if (
            ui_state.generation < button_state.generation
            or ui_state.generation > button_state.generation + 2
        ):
            raise SemanticGateClosed("event campaign aside snapshots are not coherent")
        # This validates the concrete combat-stage page and prevents the
        # similarly named labels from being accepted on an unrelated surface.
        self._event_campaign_page_state(button_state, ui_state)

        root = "LevelSelectSPFullUI(Clone)/Battle/MapItems/List/"
        tab_text = re.compile(
            re.escape(root) + r"Item(?:\(Clone\))?/(Selected|Unselect)/Text$"
        )
        labels_found = []
        for text in ui_state.texts:
            match = tab_text.search(text.path)
            if (
                match is None
                or text.text.strip() != label
                or not text.active_in_hierarchy
                or not text.active_and_enabled
                or text.truncated
                or text.bounds is None
            ):
                continue
            labels_found.append((text, match.group(1) == "Selected"))
        if len(labels_found) != 1:
            raise SemanticGateClosed(
                "event campaign aside label is absent or ambiguous"
            )
        text, selected = labels_found[0]

        item_path = text.path.rsplit("/", 2)[0]
        candidates = tuple(
            button
            for button in button_state.buttons
            if button.path == item_path
            and button.name in ("Item", "Item(Clone)")
            and button.active_in_hierarchy
            and button.active_and_enabled
            and button.bounds is not None
            and not (
                button.bounds.bottom < text.bounds.top
                or button.bounds.top > text.bounds.bottom
            )
        )
        if len(candidates) != 1:
            raise SemanticGateClosed(
                "event campaign aside control is absent or ambiguous"
            )
        return button_state, candidates[0], selected

    def event_campaign_aside_selected(self, destination: str) -> bool:
        """Report whether an exact event chapter tab is currently selected."""

        _, _, selected = self._event_campaign_aside_tab(destination)
        return selected

    def click_event_campaign_aside(self, destination: str) -> ActionReceipt:
        """Select an exact post-2024 event chapter tab."""

        state, button, selected = self._event_campaign_aside_tab(destination)
        if selected:
            raise SemanticGateClosed("event campaign aside is already selected")
        if (
            not button.interactable
            or button.bounds is None
            or self._blocking_rules(state, "event/chapter/" + destination)
        ):
            raise SemanticGateClosed("event campaign aside is not actionable")
        point = Point(
            (button.bounds.left + button.bounds.right) / 2.0,
            (button.bounds.top + button.bounds.bottom) / 2.0,
        )
        if not button.bounds.contains(point) or not (
            0 <= point.x < self.fingerprint.width
            and 0 <= point.y < self.fingerprint.height
        ):
            raise SemanticGateClosed("event campaign aside geometry is invalid")
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("game activity changed before event aside input")
        self._tap(int(round(point.x)), int(round(point.y)))
        return ActionReceipt(
            semantic_id="event/chapter/" + destination,
            generation=state.generation,
            point=point,
            bounds=button.bounds,
            path=button.path,
        )

    def _event_campaign_detail_visible(self, state: OracleState) -> bool:
        roots = (
            "LevelInfoSPUI(Clone)/panel/start_button",
            "LevelInfoSPUI(Clone)/panel/btnBack",
        )
        observed = []
        for suffix in roots:
            matches = tuple(
                button
                for button in state.buttons
                if button.path.endswith(suffix)
                and button.active_in_hierarchy
                and button.active_and_enabled
                and button.interactable
                and button.bounds is not None
            )
            if len(matches) != 1:
                return False
            observed.append(matches[0])
        return all("LevelInfoSPUI(Clone)/panel/" in item.path for item in observed)

    def event_story_page_state(self) -> Tuple[int, int, Optional[int]]:
        """Return completed, total, and first visible story-node id."""

        return self._event_story_page_state(self.read_state())

    def _event_story_page_state(
        self, state: OracleState, ui: Optional[UiState] = None
    ) -> Tuple[int, int, Optional[int]]:
        story_root = "LevelSelectSPFullUI(Clone)/Story/Nodes/Viewport/Content/"
        nodes = tuple(
            button
            for button in state.buttons
            if story_root in button.path
            and button.path.rsplit("/", 1)[-1].isdigit()
            and button.active_in_hierarchy
            and button.active_and_enabled
            and button.interactable
            and button.bounds is not None
        )
        if not nodes:
            raise SemanticGateClosed("event story nodes are absent")
        if ui is None:
            ui = self.read_ui_state()
        progress = tuple(
            text.text.strip()
            for text in ui.texts
            if text.path.endswith("LevelSelectSPFullUI(Clone)/Story/Desc/Digit")
            and text.active_in_hierarchy
            and text.active_and_enabled
            and not text.truncated
            and text.bounds is not None
            and re.fullmatch(r"[0-9]+/[0-9]+", text.text.strip())
        )
        if len(progress) != 1:
            raise SemanticGateClosed("event story progress is ambiguous")
        completed, total = map(int, progress[0].split("/"))
        if completed > total or total != len(nodes):
            raise SemanticGateClosed("event story progress conflicts with nodes")
        visible = tuple(
            int(button.path.rsplit("/", 1)[-1])
            for button in nodes
            if button.point is not None
            and button.bounds is not None
            and button.bounds.contains(button.point)
            and 0 <= button.bounds.left < button.bounds.right <= self.fingerprint.width
            and 0 <= button.bounds.top < button.bounds.bottom <= self.fingerprint.height
        )
        return completed, total, min(visible) if visible else None

    def event_story_selector_visible(self) -> bool:
        """Prove the story tab for navigation without admitting battle stages."""
        state = self.read_state()
        marker = '/LevelSelectSPFullUI(Clone)'
        active = tuple(button for button in state.buttons
                       if button.active_in_hierarchy and button.active_and_enabled)
        if not any(marker + '/Story/' in button.path for button in active):
            return False
        roots = {button.path.split(marker)[0] + marker
                 for button in active if marker in button.path}
        if (len(roots) != 1
                or any(button.path.count(marker) != 1
                       for button in active if marker in button.path)):
            raise SemanticGateClosed('event story selector root is ambiguous')
        root = next(iter(roots))
        if not root.endswith('/LevelMainScene(Clone)/LevelSelectSPFullUI(Clone)'):
            raise SemanticGateClosed('event story selector root is unsupported')
        switches = tuple(button for button in self._matches(state, 'event/mode/battle')
                         if button.active_in_hierarchy and button.active_and_enabled)
        if (len(switches) != 1 or switches[0].path != root + '/Story/Battle/Switch'
                or not switches[0].interactable or switches[0].bounds is None
                or any('/Battle/' in button.path and marker in button.path
                       and '/Story/Battle/' not in button.path for button in active)):
            raise SemanticGateClosed('event story selector mode is absent or ambiguous')
        back = tuple(button for button in self._matches(state, 'campaign-menu/page/back')
                     if button.active_in_hierarchy and button.active_and_enabled)
        page = root[:-len(marker)]
        if (len(back) != 1 or back[0].path != page + '/top/top_chapter/back_button'
                or not back[0].actionable
                or self._blocking_rules(state, 'campaign-menu/page/back')):
            raise SemanticGateClosed('event story selector back is not available')
        if any(any(part in button.path for part in (
                'ActivityMainUI(Clone)/', '/LevelMainScene(Clone)/float/levels/items/Chapter_',
                '/LevelStageInfoView(Clone)/', '/LevelInfoSPUI(Clone)/',
                '/LevelFleetSelectView(Clone)/')) for button in active):
            raise SemanticGateClosed('event story selector overlaps another page')
        node_prefix = root + '/Story/Nodes/Viewport/Content/'
        nodes = tuple(button.path for button in active
                      if button.path.startswith(node_prefix)
                      and button.path[len(node_prefix):].isdigit())
        if len(nodes) != len(set(nodes)):
            raise SemanticGateClosed('event story selector nodes are ambiguous')
        ui = self.read_ui_state()
        if not state.generation <= ui.generation <= state.generation + 2:
            raise SemanticGateClosed('event story selector snapshots are not coherent')
        self._event_story_page_state(state, ui)
        return True

    def event_story_surface_absent(self) -> bool:
        """Prove the idle story boundary without entering legacy pixel probes."""
        state = self.read_state()
        ui = self.read_ui_state(check_foreground=False)
        if not state.generation <= ui.generation <= state.generation + 2:
            raise SemanticGateClosed("story absence frames are incoherent")
        records = tuple(state.buttons) + tuple(ui.texts) + tuple(ui.images)
        for record in records:
            if not record.active_in_hierarchy:
                continue
            # The dialogue UI family owns this branch even if its reviewed
            # controls have not appeared. EventStoryScene is a separate page,
            # not a dialogue overlay, and remains owned by its native task.
            if any(part.lower().endswith("storyui(clone)")
                   for part in record.path.split("/")):
                raise SemanticGateClosed("mounted story surface is incomplete or unsupported")
        return True

    def event_story_dialogue_visible(self) -> bool:
        """Return whether the current overlay is the exact modern story UI."""

        state = self.read_state()
        roots = tuple(
            button
            for button in state.buttons
            if button.path.endswith("Overlay/UIOverlay/NewStoryUI(Clone)")
            and button.name == "NewStoryUI(Clone)"
            and button.active_in_hierarchy
            and button.active_and_enabled
            and button.bounds is not None
        )
        skips = self._matches(state, "story/skip")
        return bool(len(roots) == 1 and len(skips) == 1)

    def event_story_skip_prompt_visible(self) -> bool:
        """Require the exact two-button skip prompt nested in NewStoryUI."""

        state = self.read_state()
        confirm = self._matches(state, "story/skip/confirm")
        cancel = self._matches(state, "story/skip/cancel")
        contents = tuple(
            button
            for button in state.buttons
            if button.name == "content"
            and button.path.endswith(
                "NewStoryUI(Clone)/front/Msgbox(Clone)/window/msg_panel/content"
            )
            and button.active_in_hierarchy
            and button.active_and_enabled
            and button.bounds is not None
        )
        return bool(
            len(confirm) == 1
            and len(cancel) == 1
            and len(contents) == 1
            and confirm[0].actionable
            and cancel[0].actionable
        )

    def click_event_story_skip_confirm(self) -> ActionReceipt:
        if not self.event_story_skip_prompt_visible():
            raise SemanticGateClosed("event story skip prompt identity is absent")
        state = self.read_state()
        target = self._unique(state, "story/skip/confirm")
        if target.bounds is None:
            raise SemanticGateClosed("event story skip confirmation geometry is absent")
        point = Point(
            (target.bounds.left + target.bounds.right) / 2.0,
            (target.bounds.top + target.bounds.bottom) / 2.0,
        )
        if not target.bounds.contains(point):
            raise SemanticGateClosed(
                "event story skip confirmation geometry is invalid"
            )
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("game activity changed before story confirmation")
        self._tap(int(round(point.x)), int(round(point.y)))
        return ActionReceipt(
            semantic_id="story/skip/confirm",
            generation=state.generation,
            point=point,
            bounds=target.bounds,
            path=target.path,
        )

    def event_story_option_count(self) -> int:
        """Count active modern-story choices without reading framebuffer pixels."""

        state = self.read_state()
        if not self.event_story_dialogue_visible():
            return 0
        options, _ = self._event_story_options(state)
        return len(options)

    def _event_story_options(self, state):
        candidates = [b for b in state.buttons
                      if '/NewStoryUI(Clone)/front/dialogue/1/options_panel/' in b.path
                      and b.name in ('option_tpl', 'option_tpl(Clone)')
                      and b.active_in_hierarchy and b.active_and_enabled]
        options = []
        labels = []
        ui = None
        for b in candidates:
            if not re.search(r'/options_panel/options_[cl]/option_tpl(?:\(Clone\))?$', b.path):
                raise SemanticGateClosed('story option layout is unsupported')
            if (not b.interactable or b.point is None or b.bounds is None
                    or not b.bounds.contains(b.point) or b.raycast_top is False):
                raise SemanticGateClosed('story option is not actionable')
            if any(x.path == b.path and x.bounds == b.bounds for x in options):
                raise SemanticGateClosed('story option geometry is ambiguous')
            if '/options_l/' in b.path:
                if ui is None:
                    ui = self.read_ui_state()
                    if not state.generation <= ui.generation <= state.generation + 2:
                        raise SemanticGateClosed('story option frames are incoherent')
                    if ui.image_truncated:
                        raise SemanticGateClosed('story option graphics are truncated')
                    if any(x.blocker_id not in ('event-story', 'operation-siren-map')
                           for x in self._blocking_rules(state, 'ui/absence-probe')):
                        raise SemanticGateClosed('story options have another blocker')
                # Unity clones share paths. Correlate each complete label and
                # reviewed raycast graphic with this exact Button rectangle.
                text = [t for t in ui.texts if t.path == b.path+'/content/Text'
                        and t.active_in_hierarchy and t.active_and_enabled and not t.truncated
                        and t.text.strip() and t.bounds is not None and b.bounds.contains(Point(
                            (t.bounds.left+t.bounds.right)/2, (t.bounds.top+t.bounds.bottom)/2))]
                images = [i for i in ui.images if i.path == b.path+'/content'
                          and i.sprite == 'option_bg_left' and i.active_in_hierarchy
                          and i.active_and_enabled and i.raycast_target and i.raycast_top is not False
                          and not i.truncated and i.bounds is not None and i.bounds.contains(b.point)]
                if len(text) != 1 or len(images) != 1:
                    raise SemanticGateClosed('story option label or graphic is ambiguous')
                labels.append((b.path, b.bounds, text[0].text))
            options.append(b)
        ordered = tuple(sorted(options, key=lambda b: (b.bounds.top, b.bounds.left)))
        return ordered, tuple(sorted(labels, key=lambda x: (x[1].top, x[1].left)))

    def click_event_story_option(self, option_index: int) -> ActionReceipt:
        """Choose one current story option by ALAS' configured zero-based index."""

        if not isinstance(option_index, int):
            raise TypeError("event story option index must be an integer")
        state = self.read_state()
        if not self.event_story_dialogue_visible():
            raise SemanticGateClosed("event story dialogue identity is absent")
        options, labels = self._event_story_options(state)
        if not options:
            raise SemanticGateClosed("event story options are absent")
        if not -len(options) <= option_index < len(options):
            option_index = 0
        target = options[option_index]
        assert target.bounds is not None
        point = Point(
            (target.bounds.left + target.bounds.right) / 2.0,
            (target.bounds.top + target.bounds.bottom) / 2.0,
        )
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("game activity changed before story option input")
        self._tap(int(round(point.x)), int(round(point.y)))
        receipt = ActionReceipt(
            semantic_id="story/option/{0}".format(option_index),
            generation=state.generation,
            point=point,
            bounds=target.bounds,
            path=target.path,
        )
        if labels:
            def completed():
                after = self.read_state()
                if after.generation <= state.generation:
                    raise SemanticGateClosed('story option generation did not advance')
                _, after_labels = self._event_story_options(after)
                if after_labels == labels:
                    raise SemanticGateClosed('story option selection did not advance; do not retry')
                return True
            self._retry_transition_read(completed, attempts=20, interval_seconds=0.25)
        return receipt

    def click_event_story_skip(self) -> ActionReceipt:
        """Click the exact modern-story skip control at its visible centre."""

        state = self.read_state()
        if not self.event_story_dialogue_visible():
            raise SemanticGateClosed("event story dialogue identity is absent")
        target = self._unique(state, "story/skip")
        if not (
            target.active_in_hierarchy
            and target.active_and_enabled
            and target.interactable
            and target.raycast_top is None
            and target.bounds is not None
        ):
            raise SemanticGateClosed("event story skip is not actionable")
        point = Point(
            (target.bounds.left + target.bounds.right) / 2.0,
            (target.bounds.top + target.bounds.bottom) / 2.0,
        )
        if not target.bounds.contains(point):
            raise SemanticGateClosed("event story skip geometry is invalid")
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("game activity changed before story skip input")
        self._tap(int(round(point.x)), int(round(point.y)))
        return ActionReceipt(
            semantic_id="story/skip",
            generation=state.generation,
            point=point,
            bounds=target.bounds,
            path=target.path,
        )

    def click_event_story_node(self, node_id: int) -> ActionReceipt:
        completed, total, first_visible = self.event_story_page_state()
        if completed >= total or first_visible != node_id:
            raise SemanticGateClosed("event story node is not the next visible node")
        state = self.read_state()
        suffix = "/Story/Nodes/Viewport/Content/{0}".format(node_id)
        matches = tuple(
            button for button in state.buttons if button.path.endswith(suffix)
        )
        if len(matches) != 1:
            raise SemanticGateClosed("event story node changed before input")
        target = matches[0]
        if target.point is None or target.bounds is None:
            raise SemanticGateClosed("event story node geometry is absent")
        point = Point(
            (target.bounds.left + target.bounds.right) / 2.0,
            (target.bounds.top + target.bounds.bottom) / 2.0,
        )
        self._tap(int(round(point.x)), int(round(point.y)))
        return ActionReceipt(
            semantic_id="event/story/node/{0}".format(node_id),
            generation=state.generation,
            point=point,
            bounds=target.bounds,
            path=target.path,
        )

    def click_event_story_mode(self) -> ActionReceipt:
        """Switch the current post-2024 event page to its story selector."""

        if not self.event_campaign_page_visible():
            raise SemanticGateClosed("event campaign page identity is absent")
        state = self.read_state()
        target = self._unique(state, "event/mode/story")
        if not (
            target.active_in_hierarchy
            and target.active_and_enabled
            and target.interactable
            and target.raycast_top is None
            and target.point is not None
            and target.bounds is not None
            and target.bounds.contains(target.point)
            and not self._blocking_rules(state, "event/mode/story")
        ):
            raise SemanticGateClosed("event story selector is not actionable")
        point = Point(
            (target.bounds.left + target.bounds.right) / 2.0,
            (target.bounds.top + target.bounds.bottom) / 2.0,
        )
        self._tap(int(round(point.x)), int(round(point.y)))
        return ActionReceipt(
            semantic_id="event/mode/story",
            generation=state.generation,
            point=point,
            bounds=target.bounds,
            path=target.path,
        )

    def _event_campaign_page_state(
        self, button_state: OracleState, ui_state: UiState
    ) -> CampaignPageState:
        """Read the current ``LevelSelectSPFullUI`` combat-stage layout."""

        prefix = "LevelSelectSPFullUI(Clone)/Battle/Nodes/Chapter_"
        stage_control = re.compile(re.escape(prefix) + r"([0-9]+)/main$")
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
        if not stage_buttons or len({item[0] for item in stage_buttons}) != len(
            stage_buttons
        ):
            raise SemanticGateClosed(
                "event campaign stage buttons are absent or ambiguous"
            )

        stages = []
        for stage_id, identity_button in sorted(
            stage_buttons, key=lambda item: item[0]
        ):
            node_path = identity_button.path.rsplit("/main", 1)[0]
            action_buttons = tuple(
                button
                for button in button_state.buttons
                if button.name == "Chapter_{0}".format(stage_id)
                and button.path == node_path
                and button.active_in_hierarchy
                and button.active_and_enabled
                and button.bounds is not None
            )
            if len(action_buttons) != 1:
                raise SemanticGateClosed(
                    "event campaign stage action is absent or ambiguous"
                )
            # The parent proves the active event-node identity, while Unity's
            # wide ``main`` child owns the actual stage hit area.
            button = identity_button
            root = identity_button.path + "/info/bk/title_form/"
            indexes = tuple(
                item
                for item in ui_state.texts
                if item.path == root + "title_index"
                and item.active_in_hierarchy
                and item.active_and_enabled
                and not item.truncated
            )
            titles = tuple(
                item
                for item in ui_state.texts
                if item.path == root + "title"
                and item.active_in_hierarchy
                and item.active_and_enabled
                and not item.truncated
                and item.text.strip()
            )
            if len(indexes) != 1 or len(titles) != 1:
                raise SemanticGateClosed(
                    "event campaign stage text is absent or ambiguous"
                )
            stage_code = indexes[0].text.strip().lower()
            if re.fullmatch(r"(?:[a-z]+[0-9]*|[0-9]+-[0-9]+)", stage_code) is None:
                raise SemanticGateClosed("event campaign stage text is malformed")
            remaining_attempts = None
            if stage_code == "sp":
                attempt_path = identity_button.path + "/triesLimit/Text"
                attempts = tuple(
                    item
                    for item in ui_state.texts
                    if item.path == attempt_path
                    and item.active_in_hierarchy
                    and item.active_and_enabled
                    and not item.truncated
                    and item.bounds is not None
                )
                if len(attempts) != 1:
                    raise SemanticGateClosed(
                        "event SP attempt counter is absent or ambiguous"
                    )
                remaining_attempts = self._campaign_eventsp_remaining_attempts(
                    attempts[0].text
                )
            stages.append(
                CampaignStageState(
                    stage_id=stage_id,
                    stage_code=stage_code,
                    title=titles[0].text.strip(),
                    button=button,
                    remaining_attempts=remaining_attempts,
                )
            )
        chapters = {self._campaign_stage_chapter(stage.stage_code) for stage in stages}
        # A partially unlocked event hard page can legitimately expose C1
        # beside the still-normal A2/A3 nodes (and likewise D beside B).  The
        # nodes remain individually typed and unambiguous; the active semantic
        # campaign context performs the one-way target/entrance projection.
        chapter_name = "/".join(sorted(chapters))
        return CampaignPageState(
            generation=button_state.generation,
            chapter_name=chapter_name,
            stages=tuple(stages),
        )

    def _campaign_event_auto_delegated_raycast_proven(
        self,
        button_state: OracleState,
        ui_state: UiState,
        toggle: ToggleState,
    ) -> bool:
        """Prove the SP preparation AutoFight delegated-image control."""

        event_root = "LevelInfoSPUI(Clone)/panel/BottomExtra/LoopGroup/"
        if (
            not toggle.path.endswith(event_root + "view/container/AutoFight")
            or toggle.raycast_top is not None
            or not toggle.active_in_hierarchy
            or not toggle.active_and_enabled
            or not toggle.interactable
            or toggle.point is None
            or toggle.bounds is None
            or not toggle.bounds.contains(toggle.point)
        ):
            return False
        page_markers = tuple(
            button
            for button in button_state.buttons
            if button.name == "start_button"
            and button.path.endswith("LevelInfoSPUI(Clone)/panel/start_button")
            and button.active_in_hierarchy
            and button.active_and_enabled
            and button.interactable
        )
        loop_controls = tuple(
            button
            for button in button_state.buttons
            if button.name == "Toggle"
            and button.path.endswith(event_root + "Loop/Toggle")
            and button.active_in_hierarchy
            and button.active_and_enabled
            and button.interactable
            and button.raycast_top is None
            and button.bounds is not None
        )
        loop_on = tuple(
            image
            for image in ui_state.images
            if image.name == "on"
            and image.path.endswith(event_root + "Loop/Toggle/on")
            and image.sprite == "live2d_on"
            and image.active_in_hierarchy
            and image.active_and_enabled
            and image.bounds is not None
        )
        loop_off = tuple(
            image
            for image in ui_state.images
            if image.name == "off"
            and image.path.endswith(event_root + "Loop/Toggle/off")
            and image.active_in_hierarchy
            and image.active_and_enabled
        )
        delegated_images = tuple(
            image
            for image in ui_state.images
            if image.name == "AutoFight"
            and image.path == toggle.path
            and image.sprite == "white_dot"
            and image.active_in_hierarchy
            and image.active_and_enabled
            and image.raycast_target
            and image.raycast_top is None
            and image.bounds is not None
            and image.bounds.contains(toggle.point)
        )
        return bool(
            len(page_markers) == 1
            and len(loop_controls) == 1
            and len(loop_on) == 1
            and not loop_off
            and len(delegated_images) == 1
        )
