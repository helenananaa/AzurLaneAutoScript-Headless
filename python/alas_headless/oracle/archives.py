"""Archives for the typed ALAS boundary."""

from __future__ import annotations

import re
from typing import Optional, Tuple
from .contracts import (
    ActionReceipt,
    Bounds,
    ButtonState,
    CampaignPageState,
    CampaignStageState,
    ImageState,
    OracleState,
    Point,
    TextState,
    UiState,
    WAR_ARCHIVES_CAMPAIGN_CARDS,
)
from .errors import SemanticGateClosed


class ArchivesOracle:
    """Archives operations sharing the oracle frame and input boundary."""

    def war_archives_page_visible(self) -> bool:
        """Prove the War Archives landing page from its exact typed UI root."""

        state = self.read_ui_state()
        root = "OverlayCamera/Overlay/UIMain/LevelRemasterView(Clone)"
        toggles = tuple(
            toggle
            for toggle in state.toggles
            if toggle.path in (root + "/toggles/EX", root + "/toggles/SP")
            and toggle.active_in_hierarchy
            and toggle.active_and_enabled
            and toggle.interactable
            and toggle.bounds is not None
        )
        if len(toggles) != 2 or {toggle.name for toggle in toggles} != {"EX", "SP"}:
            return False
        if sum(toggle.checked for toggle in toggles) != 1:
            raise SemanticGateClosed("war archives category selection is inconsistent")
        counters = tuple(
            text
            for text in state.texts
            if text.path == root + "/nums/text"
            and text.active_in_hierarchy
            and text.active_and_enabled
            and not text.truncated
            and text.bounds is not None
            and re.fullmatch(r"[0-9]+/[0-9]+", text.text.strip()) is not None
        )
        if len(counters) != 1:
            return False
        current, total = (int(value) for value in counters[0].text.strip().split("/"))
        if total <= 0 or current < 0 or current > total:
            raise SemanticGateClosed("war archives data-key counter is invalid")
        return True

    @staticmethod
    def war_archives_campaign_identity(event: str) -> Tuple[str, str]:
        """Return the reviewed category and banner sprite for one ALAS folder."""

        try:
            return WAR_ARCHIVES_CAMPAIGN_CARDS[event]
        except KeyError as exc:
            raise SemanticGateClosed(
                "war archives campaign is unavailable in the pinned game: " + str(event)
            ) from exc

    def war_archives_category(self) -> str:
        """Return the exactly selected EX/SP landing-page category."""

        if not self.war_archives_page_visible():
            raise SemanticGateClosed("war archives page identity is not proven")
        root = "OverlayCamera/Overlay/UIMain/LevelRemasterView(Clone)/toggles/"
        state = self.read_ui_state()
        selected = tuple(
            toggle.name.lower()
            for toggle in state.toggles
            if toggle.path in (root + "EX", root + "SP")
            and toggle.active_in_hierarchy
            and toggle.active_and_enabled
            and toggle.interactable
            and toggle.checked
            and toggle.bounds is not None
        )
        if len(selected) != 1 or selected[0] not in ("ex", "sp"):
            raise SemanticGateClosed("war archives category is absent or ambiguous")
        return selected[0]

    def click_war_archives_category(self, category: str) -> ActionReceipt:
        """Select one exact archive category toggle."""

        if category not in ("ex", "sp"):
            raise SemanticGateClosed("war archives category is invalid")
        if not self.war_archives_page_visible():
            raise SemanticGateClosed("war archives category requires landing page")
        if self.war_archives_category() == category:
            raise SemanticGateClosed("war archives category is already selected")
        state = self.read_state()
        ui_state = self.read_ui_state()
        path = (
            "OverlayCamera/Overlay/UIMain/LevelRemasterView(Clone)/toggles/"
            + category.upper()
        )
        matches = tuple(
            toggle
            for toggle in ui_state.toggles
            if toggle.path == path
            and toggle.name == category.upper()
            and toggle.active_in_hierarchy
            and toggle.active_and_enabled
            and toggle.interactable
            and not toggle.checked
            and toggle.bounds is not None
        )
        if len(matches) != 1:
            raise SemanticGateClosed("war archives category target is ambiguous")
        if not (
            state.generation <= ui_state.generation <= state.generation + 2
        ):
            raise SemanticGateClosed("war archives category snapshots are incoherent")
        semantic_id = "archive/category/" + category
        if self._blocking_rules(state, semantic_id):
            raise SemanticGateClosed("war archives category input is blocked")
        target = matches[0]
        assert target.bounds is not None
        point = Point(
            x=(target.bounds.left + target.bounds.right) / 2.0,
            y=(target.bounds.top + target.bounds.bottom) / 2.0,
        )
        if not target.bounds.contains(point):
            raise SemanticGateClosed("war archives category geometry is invalid")
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("foreground changed before archive category input")
        self._tap(int(round(point.x)), int(round(point.y)))
        return ActionReceipt(
            semantic_id=semantic_id,
            generation=ui_state.generation,
            point=point,
            bounds=target.bounds,
            path=target.path,
        )

    def _war_archives_campaign_card(
        self, event: str
    ) -> Tuple[OracleState, ImageState, ButtonState]:
        expected_category, sprite = self.war_archives_campaign_identity(event)
        if self.war_archives_category() != expected_category:
            raise SemanticGateClosed("war archives campaign category is not selected")
        button_state = self.read_state()
        ui_state = self.read_ui_state()
        if not (
            button_state.generation
            <= ui_state.generation
            <= button_state.generation + 2
        ):
            raise SemanticGateClosed("war archives card snapshots are incoherent")
        root = "OverlayCamera/Overlay/UIMain/LevelRemasterView(Clone)/list/content/"
        images = tuple(
            image
            for image in ui_state.images
            if image.path.startswith(root)
            and image.path.endswith("/bg/icon")
            and image.name == "icon"
            and image.sprite == sprite
            and image.active_in_hierarchy
            and image.active_and_enabled
            and not image.truncated
            and image.bounds is not None
        )
        if len(images) != 1:
            raise SemanticGateClosed(
                "war archives campaign card is absent or ambiguous: " + event
            )
        image = images[0]
        buttons = tuple(
            button
            for button in button_state.buttons
            if button.path == image.path
            and button.name == "icon"
            and button.active_in_hierarchy
            and button.active_and_enabled
            and button.interactable
            and button.bounds == image.bounds
        )
        if len(buttons) != 1:
            raise SemanticGateClosed("war archives campaign control is ambiguous")
        return button_state, image, buttons[0]

    def war_archives_campaign_card_position(self, event: str) -> str:
        """Classify an exact campaign card relative to the safe list viewport."""

        _state, image, _button = self._war_archives_campaign_card(event)
        assert image.bounds is not None
        if image.bounds.top >= 110.0 and image.bounds.bottom <= 680.0:
            return "visible"
        if image.bounds.bottom < 110.0:
            return "above"
        if image.bounds.top > 680.0:
            return "below"
        raise SemanticGateClosed("war archives campaign card clips the safe viewport")

    def war_archives_campaign_card_geometry(
        self, event: str
    ) -> Tuple[int, Bounds]:
        """Return the coherent generation and exact card bounds."""

        state, image, _button = self._war_archives_campaign_card(event)
        assert image.bounds is not None
        return state.generation, image.bounds

    def swipe_war_archives_campaign_toward(self, event: str) -> ActionReceipt:
        """Move the typed archive list one page toward an exact off-screen card."""

        if self._swipe is None:
            raise SemanticGateClosed("war archives campaign search requires typed swipe")
        button_state, _image, _button = self._war_archives_campaign_card(event)
        position = self.war_archives_campaign_card_position(event)
        if position == "visible":
            raise SemanticGateClosed("war archives campaign card is already visible")
        ui_state = self.read_ui_state()
        handle_path = (
            "OverlayCamera/Overlay/UIMain/LevelRemasterView(Clone)/"
            "list/scroll_bar/Handle/Image"
        )
        handles = tuple(
            image
            for image in ui_state.images
            if image.path == handle_path
            and image.name == "Image"
            and image.sprite == "scroll_bar"
            and image.active_in_hierarchy
            and image.active_and_enabled
            and not image.truncated
            and image.bounds is not None
        )
        if len(handles) != 1:
            raise SemanticGateClosed("war archives scroll identity is ambiguous")
        semantic_id = "archive/campaign/search/" + event
        if self._blocking_rules(button_state, semantic_id):
            raise SemanticGateClosed("war archives campaign search is blocked")
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("foreground changed before archive list swipe")
        if position == "below":
            start, end = Point(640.0, 620.0), Point(640.0, 250.0)
        else:
            start, end = Point(640.0, 220.0), Point(640.0, 590.0)
        self._swipe(
            int(start.x), int(start.y), int(end.x), int(end.y), 350
        )
        handle = handles[0]
        assert handle.bounds is not None
        return ActionReceipt(
            semantic_id=semantic_id,
            generation=button_state.generation,
            point=start,
            bounds=handle.bounds,
            path=handle.path,
        )

    def click_war_archives_campaign(self, event: str) -> ActionReceipt:
        """Click one exact, fully visible archive campaign card."""

        state, _image, target = self._war_archives_campaign_card(event)
        if self.war_archives_campaign_card_position(event) != "visible":
            raise SemanticGateClosed("war archives campaign card is outside viewport")
        if (
            target.point is None
            or target.bounds is None
            or not target.bounds.contains(target.point)
            or target.raycast_top is not None
        ):
            raise SemanticGateClosed("war archives campaign card is not actionable")
        semantic_id = "archive/campaign/" + event
        if self._blocking_rules(state, semantic_id):
            raise SemanticGateClosed("war archives campaign input is blocked")
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("foreground changed before archive campaign input")
        self._tap(int(round(target.point.x)), int(round(target.point.y)))
        return ActionReceipt(
            semantic_id=semantic_id,
            generation=state.generation,
            point=target.point,
            bounds=target.bounds,
            path=target.path,
        )

    def war_archives_data_key_text(self) -> str:
        """Return the exact typed data-key counter on a proven archives page."""

        if not self.war_archives_page_visible():
            raise SemanticGateClosed("war archives page identity is not proven")
        state = self.read_ui_state()
        path = "OverlayCamera/Overlay/UIMain/LevelRemasterView(Clone)/nums/text"
        matches = tuple(
            text
            for text in state.texts
            if text.path == path
            and text.active_in_hierarchy
            and text.active_and_enabled
            and not text.truncated
            and text.bounds is not None
            and re.fullmatch(r"[0-9]+/[0-9]+", text.text.strip()) is not None
        )
        if len(matches) != 1:
            raise SemanticGateClosed("war archives data-key counter is ambiguous")
        return matches[0].text.strip()

    def war_archives_data_key_collected(self) -> bool:
        """Read the exact daily key-claim state without enabling a click."""

        if not self.war_archives_page_visible():
            raise SemanticGateClosed("war archives page identity is not proven")
        state = self.read_state()
        before = self._matches(state, "archive/key/collect")
        after = tuple(
            button
            for button in state.buttons
            if button.name == "state_after"
            and button.path.endswith("LevelRemasterView(Clone)/getBtn/state_after")
            and button.active_in_hierarchy
            and button.active_and_enabled
        )
        ui_state = self.read_ui_state()
        after_images = tuple(
            image
            for image in ui_state.images
            if image.name == "state_after"
            and image.path.endswith("LevelRemasterView(Clone)/getBtn/state_after")
            and image.sprite == "remaster_key_got"
            and image.active_in_hierarchy
            and image.active_and_enabled
            and not image.truncated
            and image.bounds is not None
        )
        after_present = bool(after or after_images)
        if (
            bool(before) == after_present
            or len(before) > 1
            or len(after) > 1
            or len(after_images) > 1
        ):
            raise SemanticGateClosed("war archives data-key claim state is ambiguous")
        return after_present

    def click_war_archives_data_key_collect(self) -> ActionReceipt:
        """Click the exact uncollected daily-key control on the Archives page."""

        if not self.war_archives_page_visible():
            raise SemanticGateClosed("war archives page identity is not proven")
        if self.war_archives_data_key_collected():
            raise SemanticGateClosed("war archives data key is already collected")
        state = self.read_state()
        matches = self._matches(state, "archive/key/collect")
        if len(matches) != 1:
            raise SemanticGateClosed("war archives data-key claim is ambiguous")
        target = matches[0]
        if not (
            target.active_in_hierarchy
            and target.active_and_enabled
            and target.interactable
            and target.raycast_top is None
            and target.point is not None
            and target.bounds is not None
            and target.bounds.contains(target.point)
            and not self._blocking_rules(state, "archive/key/collect")
        ):
            raise SemanticGateClosed("war archives data-key claim is not actionable")
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("game activity changed before data-key input")
        self._tap(int(round(target.point.x)), int(round(target.point.y)))
        return ActionReceipt(
            semantic_id="archive/key/collect",
            generation=state.generation,
            point=target.point,
            bounds=target.bounds,
            path=target.path,
        )

    def data_key_limit_prompt_visible(self) -> bool:
        """Identify the exact full-capacity zero-key confirmation prompt."""

        state = self.read_state()
        ui_state = self.read_ui_state()
        if not state.generation <= ui_state.generation <= state.generation + 2:
            raise SemanticGateClosed("data-key limit snapshots are not coherent")
        archive_roots = tuple(
            button
            for button in state.buttons
            if button.name == "bg"
            and button.path.endswith("UIOrigin/LevelRemasterView(Clone)/bg")
            and button.active_in_hierarchy
            and button.active_and_enabled
        )
        if len(archive_roots) != 1:
            return False
        confirm = self._matches(state, "archive/key-limit/confirm")
        cancel = self._matches(state, "archive/key-limit/cancel")
        if len(confirm) != 1 or len(cancel) != 1:
            return False
        labels = {
            text.path
            for text in ui_state.texts
            if text.active_in_hierarchy
            and text.active_and_enabled
            and not text.truncated
            and text.bounds is not None
            and text.path.startswith(
                "OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/"
            )
        }
        content = tuple(
            text.text
            for text in ui_state.texts
            if text.path
            == "OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/msg_panel/content"
            and text.active_in_hierarchy
            and text.active_and_enabled
            and not text.truncated
        )
        if len(content) != 1:
            return False
        counters = tuple(
            text.text.strip()
            for text in ui_state.texts
            if text.path.endswith("LevelRemasterView(Clone)/nums/text")
            and text.active_in_hierarchy
            and text.active_and_enabled
            and not text.truncated
            and re.fullmatch(r"[0-9]+/[0-9]+", text.text.strip())
        )
        full = False
        if len(counters) == 1:
            current, total = (int(value) for value in counters[0].split("/"))
            full = current == total and total > 0
        return bool(
            full
            and (
                "OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/"
                "button_container/custom_button_1(Clone)/pic"
            )
            in labels
            and (
                "OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/"
                "button_container/custom_button_2(Clone)/pic"
            )
            in labels
            and content[0].count("<color=#ffde38>") == 2
            and "<color=#ff5c5c>0</color>" in content[0]
        )

    def click_data_key_limit_choice(self, *, confirm: bool) -> ActionReceipt:
        """Resolve the exact full-capacity prompt; confirm intentionally loses one key."""

        if not self.data_key_limit_prompt_visible():
            raise SemanticGateClosed("data-key limit prompt is absent")
        state = self.read_state()
        semantic_id = (
            "archive/key-limit/confirm"
            if confirm
            else "archive/key-limit/cancel"
        )
        target = self._unique(state, semantic_id)
        if not target.actionable:
            raise SemanticGateClosed("data-key limit choice is not actionable")
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("game activity changed before data-key choice")
        assert target.point is not None and target.bounds is not None
        self._tap(int(round(target.point.x)), int(round(target.point.y)))
        return ActionReceipt(
            semantic_id=semantic_id,
            generation=state.generation,
            point=target.point,
            bounds=target.bounds,
            path=target.path,
        )

    @staticmethod
    def _war_archives_campaign_counter_records(
        ui_state: UiState,
    ) -> Tuple[TextState, ...]:
        suffix = (
            "LevelMainScene(Clone)/main/right_chapter/"
            "event_btns/tickets/Text"
        )
        return tuple(
            item
            for item in ui_state.texts
            if item.path.endswith(suffix)
            and item.active_in_hierarchy
            and item.active_and_enabled
            and not item.truncated
            and item.bounds is not None
        )

    def _war_archives_campaign_page_state(
        self, button_state: OracleState, ui_state: UiState
    ) -> CampaignPageState:
        """Read the letter-coded stage nodes mounted in LevelMainScene."""

        counters = self._war_archives_campaign_counter_records(ui_state)
        if len(counters) != 1 or re.fullmatch(
            r"[0-9]+\s*/\s*[0-9]+", counters[0].text.strip()
        ) is None:
            raise SemanticGateClosed("war archives campaign key counter is malformed")
        title_suffix = "LevelMainScene(Clone)/top/top_chapter/title_chapter/name"
        titles = tuple(
            item
            for item in ui_state.texts
            if item.path.endswith(title_suffix)
            and item.active_in_hierarchy
            and item.active_and_enabled
            and not item.truncated
            and item.text.strip()
        )
        if len(titles) != 1:
            raise SemanticGateClosed(
                "war archives campaign title is absent or ambiguous"
            )
        prefix = "LevelMainScene(Clone)/float/levels/items/Chapter_"
        control_pattern = re.compile(re.escape(prefix) + r"([1-9][0-9]*)/main$")
        controls = []
        for button in button_state.buttons:
            match = control_pattern.search(button.path)
            if match is None or button.name != "main":
                continue
            if (
                not button.active_in_hierarchy
                or not button.active_and_enabled
                or button.bounds is None
            ):
                continue
            controls.append((int(match.group(1)), button))
        if not controls or len({stage_id for stage_id, _ in controls}) != len(controls):
            raise SemanticGateClosed(
                "war archives campaign stages are absent or ambiguous"
            )
        stages = []
        for stage_id, button in sorted(controls, key=lambda item: item[0]):
            root = button.path + "/info/bk/title_form/"
            indexes = tuple(
                item
                for item in ui_state.texts
                if item.path == root + "title_index"
                and item.active_in_hierarchy
                and item.active_and_enabled
                and not item.truncated
            )
            stage_titles = tuple(
                item
                for item in ui_state.texts
                if item.path == root + "title"
                and item.active_in_hierarchy
                and item.active_and_enabled
                and not item.truncated
                and item.text.strip()
            )
            if len(indexes) != 1 or len(stage_titles) != 1:
                raise SemanticGateClosed(
                    "war archives campaign stage text is absent or ambiguous"
                )
            stage_code = indexes[0].text.strip().lower()
            if re.fullmatch(r"[a-z]+[1-9][0-9]*", stage_code) is None:
                raise SemanticGateClosed(
                    "war archives campaign stage text is malformed"
                )
            stages.append(
                CampaignStageState(
                    stage_id=stage_id,
                    stage_code=stage_code,
                    title=stage_titles[0].text.strip(),
                    button=button,
                )
            )
        chapters = {self._campaign_stage_chapter(stage.stage_code) for stage in stages}
        return CampaignPageState(
            generation=button_state.generation,
            chapter_name="/".join(sorted(chapters)),
            stages=tuple(stages),
        )

    def war_archives_campaign_page_visible(self) -> bool:
        """Return whether the exact archive campaign stage page is mounted."""

        ui_state = self.read_ui_state()
        if not self._war_archives_campaign_counter_records(ui_state):
            return False
        state = self.campaign_page_state()
        if not state.stages:
            raise SemanticGateClosed("war archives campaign has no typed stages")
        return True

    def war_archives_campaign_data_key_count(self) -> Tuple[int, int]:
        """Return current and maximum archive keys from the stage-page HUD."""

        if not self.war_archives_campaign_page_visible():
            raise SemanticGateClosed("war archives campaign page is absent")
        ui_state = self.read_ui_state()
        counters = self._war_archives_campaign_counter_records(ui_state)
        if len(counters) != 1:
            raise SemanticGateClosed("war archives campaign key counter is ambiguous")
        match = re.fullmatch(
            r"([0-9]+)\s*/\s*([0-9]+)", counters[0].text.strip()
        )
        if match is None:
            raise SemanticGateClosed("war archives campaign key counter is malformed")
        current, total = map(int, match.groups())
        if total <= 0 or current < 0 or current > total:
            raise SemanticGateClosed("war archives campaign key count is invalid")
        return current, total

    def war_archives_entry_confirmation_cost(self) -> Optional[int]:
        """Return the exact ordinary Data Key cost, or None without a Msgbox."""

        state = self.read_state()
        if not any("/Msgbox(Clone)/" in button.path for button in state.buttons):
            return None
        parts = self._msgbox_prompt_parts(state)
        if parts is None:
            raise SemanticGateClosed("war archives entry prompt is incomplete")
        content, cancel, confirm = parts
        normalized = "".join(re.sub(r"<[^>]*>", "", content).split())
        match = re.fullmatch(
            r"进入所选关卡需要消耗档案秘钥x([0-9]+)，是否进入？",
            normalized,
        )
        if match is None or cancel != "取消" or confirm != "确定":
            raise SemanticGateClosed("war archives entry prompt identity changed")
        cost = int(match.group(1))
        if cost != 5:
            raise SemanticGateClosed("war archives entry cost changed")
        counters = self._war_archives_campaign_counter_records(
            self.read_ui_state()
        )
        counter_match = (
            re.fullmatch(r"([0-9]+)\s*/\s*([0-9]+)", counters[0].text.strip())
            if len(counters) == 1
            else None
        )
        if counter_match is None or int(counter_match.group(1)) < cost:
            raise SemanticGateClosed("war archives entry Data Keys are insufficient")
        return cost

    def confirm_war_archives_entry(self) -> ActionReceipt:
        """Confirm one exact five-key archive sortie prompt."""

        if self.war_archives_entry_confirmation_cost() != 5:
            raise SemanticGateClosed("war archives entry prompt is absent")
        return self.click("archive/entry/confirm")

    def cancel_war_archives_entry(self) -> ActionReceipt:
        """Cancel one exact archive sortie prompt without spending keys."""

        if self.war_archives_entry_confirmation_cost() != 5:
            raise SemanticGateClosed("war archives entry prompt is absent")
        return self.click("archive/entry/cancel")
