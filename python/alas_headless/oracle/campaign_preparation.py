"""Campaign preparation for the typed ALAS boundary."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple
from .campaign_mappings import (
    _CAMPAIGN_EVENT_UNDERLAY_ROOTS,
    _CAMPAIGN_FLEET_UNDERLAY_ROOT_PAIRS,
    _CAMPAIGN_LIVE_B2_MAP_BUTTON_ADDITIONS,
    _CAMPAIGN_LIVE_B2_MAP_IMAGE_ADDITIONS,
    _CAMPAIGN_LIVE_D1_MAP_BUTTON_ADDITIONS,
    _CAMPAIGN_LIVE_D1_MAP_IMAGE_ADDITIONS,
    _CAMPAIGN_LIVE_D1_MAP_TEXT_ADDITIONS,
    _CAMPAIGN_LIVE_EVENTA2_STAGE_ROOT,
    _CAMPAIGN_LIVE_EVENTA3_STAGE_ROOT,
    _CAMPAIGN_LIVE_EVENTB2_STAGE_ROOT,
    _CAMPAIGN_LIVE_EVENTB3_STAGE_ROOT,
    _CAMPAIGN_LIVE_EVENTC1_STAGE_ROOT,
    _CAMPAIGN_LIVE_EVENTC2_STAGE_ROOT,
    _CAMPAIGN_LIVE_EVENTC3_STAGE_ROOT,
    _CAMPAIGN_LIVE_EVENTD1_STAGE_ROOT,
    _CAMPAIGN_LIVE_EVENTD2_STAGE_ROOT,
    _CAMPAIGN_LIVE_EVENTD3_STAGE_ROOT,
    _CAMPAIGN_LIVE_EVENTSP_SELECTED_ROOT,
    _CAMPAIGN_LIVE_EVENTSP_STAGE_ROOT,
    _CAMPAIGN_LIVE_EVENTSP_UNDERLAY_ROOT,
    _CAMPAIGN_LIVE_FLEET_DIRECT_ANCHORS,
    _CAMPAIGN_LIVE_FLEET_PANEL_ROOT,
    _CAMPAIGN_LIVE_MAP_BUTTON_SPECS,
    _CAMPAIGN_LIVE_MAP_IMAGE_SPECS,
    _CAMPAIGN_LIVE_MAP_PANEL_ROOT,
    _CAMPAIGN_LIVE_MAP_TEXT_COUNTS,
    _CAMPAIGN_LIVE_MAP_TOGGLE_SPECS,
    _CAMPAIGN_LIVE_MAP_UIORIGIN_PANEL_ROOT,
    _CAMPAIGN_LIVE_MAP_UIORIGIN_VIEW_ROOT,
    _CAMPAIGN_LIVE_MAP_VIEW_ROOT,
    _CAMPAIGN_LIVE_NORMAL_MAP_PANEL_ROOT,
    _CAMPAIGN_LIVE_NORMAL_MAP_VIEW_ROOT,
    _CAMPAIGN_MAP_UNDERLAY_ROOT_PAIRS,
    _CAMPAIGN_NORMAL_UNDERLAY_ROOTS,
    _CAMPAIGN_PREPARATION_FAMILIES,
    _CAMPAIGN_PREPARATION_REVIEWED_ROOTS,
)
from .contracts import (
    ActionReceipt,
    ButtonState,
    CampaignMapAchievementState,
    CampaignPreparationState,
    OracleState,
    Point,
    TextState,
    UiState,
)
from .errors import SemanticGateClosed


class CampaignPreparationOracle:
    """Campaign preparation operations sharing the oracle frame and input boundary."""

    def _campaign_clear_mode_control(self):
        return self._retry_transition_read(self._campaign_clear_mode_control_once)

    def _campaign_clear_mode_control_once(self):
        state = self.read_state()
        # read_state already checked foreground. Avoid an intervening ADB
        # round trip between the two snapshots; input checks foreground again.
        ui = self.read_ui_state(check_foreground=False)
        if (ui.generation < state.generation
                or ui.generation > state.generation + 8 or ui.image_truncated):
            raise SemanticGateClosed("campaign clear-mode frame is incomplete")
        suffixes = tuple(
            root + "/panel/BottomExtra/LoopGroup/Loop/Toggle"
            for root in (
                _CAMPAIGN_LIVE_NORMAL_MAP_VIEW_ROOT,
                _CAMPAIGN_LIVE_MAP_VIEW_ROOT,
                _CAMPAIGN_LIVE_MAP_UIORIGIN_VIEW_ROOT,
            )
        )
        controls = tuple(b for b in state.buttons if b.path in suffixes)
        if not controls:
            return state, None, None
        if len(controls) != 1:
            raise SemanticGateClosed("campaign clear-mode control is ambiguous")
        button = controls[0]
        markers = tuple(
            image for image in ui.images
            if image.path in (button.path + "/on", button.path + "/off")
            and image.active_in_hierarchy and image.active_and_enabled
        )
        if len(markers) != 1 or any(
            image.sprite != "live2d_" + image.name
            or image.path != button.path + "/" + image.name
            for image in markers
        ):
            raise SemanticGateClosed("campaign clear-mode state is absent or ambiguous")
        return state, button, markers[0].name == "on"

    def campaign_clear_mode_selected(self) -> Optional[bool]:
        """Read the current client's official loop-mode switch."""
        return self._campaign_clear_mode_control()[2]

    def _campaign_2x_book_control(self, mode=None):
        if mode not in (None, "prep", "auto"):
            raise ValueError("campaign book mode must be prep or auto")
        def read_once():
            state = self.read_state()
            ui = self.read_ui_state(check_foreground=False)
            if ui.generation < state.generation or ui.generation > state.generation + 8 or ui.image_truncated:
                raise SemanticGateClosed("campaign 2x-book frame is incomplete")
            roots = {
                "prep": _CAMPAIGN_LIVE_FLEET_PANEL_ROOT + "Fixed/sp",
                "auto": "OverlayCamera/Overlay/UIMain/LevelStageTotalRewardPanel(Clone)/Window/Fixed/SpList/Item",
            }
            present = [key for key, path in roots.items() if any(b.path == path for b in state.buttons)]
            if len(present) > 1:
                raise SemanticGateClosed("campaign book preparation surfaces are ambiguous")
            active_mode = mode or (present[0] if present else "prep")
            root = roots[active_mode]
            buttons = tuple(b for b in state.buttons if b.path == root)
            if not buttons:
                return state, None, None, 0
            item = root + ("/item" if active_mode == "prep" else "/Active/Item/IconTpl/icon_bg")
            checkbox = root + ("/checkbox" if active_mode == "prep" else "/Active/Checkbox")
            icons = tuple(i for i in ui.images if i.path == item + "/icon" and i.sprite == "tebiezuozhan")
            boxes = tuple(i for i in ui.images if i.path == checkbox and i.sprite == "bg_rect")
            counts = tuple(t for t in ui.texts if t.path == item + "/count" and not t.truncated)
            if len(buttons) != 1 or len(icons) != 1 or len(boxes) != 1 or len(counts) != 1:
                raise SemanticGateClosed("campaign 2x-book identity is incomplete or ambiguous")
            if re.fullmatch(r"[0-9]+", counts[0].text.strip()) is None:
                raise SemanticGateClosed("campaign 2x-book inventory is malformed")
            markers = tuple(i for i in ui.images if i.path.startswith(checkbox + "/"))
            if len(markers) > 1 or any(i.path.rsplit("/", 1)[0] != checkbox or i.sprite != "gou" for i in markers):
                raise SemanticGateClosed("campaign 2x-book selected marker is not reviewed")
            if active_mode == "prep" and any(i.path != checkbox + "/mark" for i in markers):
                raise SemanticGateClosed("campaign 2x-book selected marker is not reviewed")
            return state, buttons[0], bool(markers), int(counts[0].text.strip())
        return self._retry_transition_read(read_once)

    def _campaign_auto_search_reentry_target(self):
        state = self.read_state()
        root = "OverlayCamera/Overlay/UIMain/LevelStageTotalRewardPanel(Clone)/Window/Fixed/"
        matches = tuple(b for b in state.buttons if b.path == root + "ButtonGO" and b.name == "ButtonGO")
        if not matches:
            return state, None
        if len(matches) != 1:
            raise SemanticGateClosed("campaign reentry target is ambiguous")
        ui = self.read_ui_state(check_foreground=False)
        if ui.generation < state.generation or ui.generation > state.generation + 8:
            raise SemanticGateClosed("campaign reentry frame is incomplete")
        labels = tuple("".join(t.text.split()) for t in ui.texts
                       if t.path == root + "ButtonGO/pic" and not t.truncated)
        if labels != ("再次前往",):
            raise SemanticGateClosed("campaign reentry label is not proven")
        return state, matches[0]

    def campaign_auto_search_reentry_available(self) -> bool:
        try:
            state, target = self._campaign_auto_search_reentry_target()
        except SemanticGateClosed:
            # Optional reentry may degrade to the independently checked Exit
            # route. This never admits input; clicking still proves everything.
            return False
        return bool(target is not None and target.actionable
                    and not self._blocking_rules(state, "reward/campaign-total/go"))

    def click_campaign_auto_search_reentry(self) -> ActionReceipt:
        state, target = self._campaign_auto_search_reentry_target()
        if target is None or not target.actionable or self._blocking_rules(state, "reward/campaign-total/go"):
            raise SemanticGateClosed("campaign reentry is not actionable")
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("foreground changed before campaign reentry")
        self._tap(int(round(target.point.x)), int(round(target.point.y)))
        return ActionReceipt(semantic_id="reward/campaign-total/go", generation=state.generation,
                             point=target.point, bounds=target.bounds, path=target.path)

    def campaign_2x_book_selected(self, mode=None) -> Optional[bool]:
        return self._campaign_2x_book_control(mode)[2]

    def click_campaign_2x_book(self, expected: bool, mode=None) -> ActionReceipt:
        state, button, selected, count = self._campaign_2x_book_control(mode)
        if type(expected) is not bool or button is None or selected is not expected:
            raise SemanticGateClosed("campaign 2x-book state changed before input")
        if not expected and count == 0:
            raise SemanticGateClosed("campaign 2x-book inventory is empty")
        semantic_id = "campaign/2x-book-auto" if "/LevelStageTotalRewardPanel(Clone)/" in button.path else "campaign/2x-book"
        if not button.actionable:
            raise SemanticGateClosed("campaign 2x-book target is not actionable")
        blockers = self._blocking_rules(state, semantic_id)
        if blockers:
            raise SemanticGateClosed("campaign 2x-book blocked by " + ", ".join(rule.blocker_id for rule in blockers))
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("foreground changed before 2x-book input")
        self._tap(int(round(button.point.x)), int(round(button.point.y)))
        return ActionReceipt(semantic_id=semantic_id, generation=state.generation,
                             point=button.point, bounds=button.bounds, path=button.path)

    def _campaign_2x_book_prompt(self, confirm: bool):
        state = self.read_state()
        root = "OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/"
        if not any(b.path.startswith(root) for b in state.buttons):
            return state, None
        ui = self._stable_msgbox_ui_state(state)
        def texts(suffix):
            return tuple(t.text.strip() for t in ui.texts if t.path == root + suffix
                         and t.active_in_hierarchy and t.active_and_enabled and not t.truncated)
        title = texts("single_item_panel/display_panel/name_container/name/Text")
        if title != ("高效作战指令书",):
            return state, None
        description = texts("single_item_panel/display_panel/desc/Text")
        inventory = texts("single_item_panel/left/own/Text")
        quantity = texts("single_item_panel/left/IconTpl/icon_bg/count")
        if (len(description) != 1 or not description[0].startswith("是否使用高效作战指令书")
                or "石油消耗增加100%" not in description[0]
                or quantity != ("1",) or len(inventory) != 1
                or re.fullmatch(r"[0-9]+", inventory[0]) is None or int(inventory[0]) < 1):
            raise SemanticGateClosed("campaign 2x-book confirmation terms are not proven")
        name = "custom_button_1(Clone)" if confirm else "custom_button_2(Clone)"
        path = root + "button_container/" + name
        label = texts("button_container/" + name + "/pic")
        if len(label) != 1 or "".join(label[0].split()) != ("确定" if confirm else "取消"):
            raise SemanticGateClosed("campaign 2x-book confirmation label is ambiguous")
        buttons = tuple(b for b in state.buttons if b.path == path and b.name == name)
        if len(buttons) != 1 or not buttons[0].actionable:
            raise SemanticGateClosed("campaign 2x-book confirmation is not actionable")
        return state, buttons[0]

    def campaign_2x_book_prompt_visible(self) -> bool:
        return self._campaign_2x_book_prompt(True)[1] is not None

    def _campaign_2x_book_warning(self):
        state = self.read_state()
        root = "OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/"
        if not any(b.path.startswith(root) for b in state.buttons):
            return state, None
        ui = self._stable_msgbox_ui_state(state)
        content = [re.sub(r"<[^>]*>", "", t.text) for t in ui.texts
                   if t.path == root + "msg_panel/content" and not t.truncated]
        if len(content) != 1 or not all(s in content[0] for s in
                ("已为您取消高效作战指令书", "自律寻敌模式", "再次手动选择使用")):
            return state, None
        path = root + "button_container/custom_button_1(Clone)"
        buttons = tuple(b for b in state.buttons if b.path == path)
        labels = ["".join(t.text.split()) for t in ui.texts if t.path == path + "/pic" and not t.truncated]
        if len(buttons) != 1 or not buttons[0].actionable or labels != ["确定"]:
            raise SemanticGateClosed("campaign 2x-book cancellation notice is ambiguous")
        return state, buttons[0]

    def campaign_2x_book_cancelled(self) -> bool:
        return self._campaign_2x_book_warning()[1] is not None

    def dismiss_campaign_2x_book_warning(self) -> ActionReceipt:
        state, button = self._campaign_2x_book_warning()
        semantic_id = "campaign/2x-book/warning-dismiss"
        if button is None or self._blocking_rules(state, semantic_id):
            raise SemanticGateClosed("campaign 2x-book cancellation notice is blocked")
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("foreground changed before book notice dismissal")
        self._tap(int(round(button.point.x)), int(round(button.point.y)))
        return ActionReceipt(semantic_id=semantic_id, generation=state.generation,
                             point=button.point, bounds=button.bounds, path=button.path)

    def click_campaign_2x_book_prompt(self, confirm: bool) -> ActionReceipt:
        if type(confirm) is not bool:
            raise SemanticGateClosed("campaign 2x-book confirmation choice must be bool")
        state, button = self._campaign_2x_book_prompt(confirm)
        semantic_id = "campaign/2x-book/" + ("confirm" if confirm else "cancel")
        if button is None or self._blocking_rules(state, semantic_id):
            raise SemanticGateClosed("campaign 2x-book confirmation is blocked")
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("foreground changed before 2x-book confirmation")
        self._tap(int(round(button.point.x)), int(round(button.point.y)))
        return ActionReceipt(semantic_id=semantic_id, generation=state.generation,
                             point=button.point, bounds=button.bounds, path=button.path)

    def click_campaign_clear_mode(self, expected: bool) -> ActionReceipt:
        if type(expected) is not bool:
            raise SemanticGateClosed("campaign clear-mode expected state must be bool")
        state, button, selected = self._campaign_clear_mode_control()
        if button is None or selected is not expected:
            raise SemanticGateClosed("campaign clear-mode state changed before input")
        if not button.actionable or self._blocking_rules(state, "campaign/clear-mode"):
            raise SemanticGateClosed("campaign clear-mode target is not actionable")
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("foreground changed before clear-mode input")
        self._tap(int(round(button.point.x)), int(round(button.point.y)))
        return ActionReceipt(
            semantic_id="campaign/clear-mode/" + ("on" if expected else "off"),
            generation=state.generation, point=button.point,
            bounds=button.bounds, path=button.path,
        )

    def campaign_preparation_state(
        self, stage_code: str
    ) -> Optional[CampaignPreparationState]:
        """Return the one exact pre-sortie layer, or None before it appears."""

        button_state = self.read_state()
        ui_state = self.read_ui_state(check_foreground=False, _preserve_partial_toggles=True)
        map_roots, fleet_roots = self._campaign_preparation_roots(
            button_state, ui_state
        )
        if (map_roots or fleet_roots) and ui_state.snapshot.get('toggle_truncated') is not False:
            raise SemanticGateClosed("campaign preparation toggle snapshot is truncated")
        if map_roots and fleet_roots:
            raise SemanticGateClosed(
                "campaign preparation layers are simultaneously active"
            )
        if len(map_roots) > 1 or len(fleet_roots) > 1:
            raise SemanticGateClosed("campaign preparation root is ambiguous")
        if fleet_roots:
            return self._campaign_fleet_preparation_state_once(
                stage_code,
                button_state=button_state,
                ui_state=ui_state,
            )
        if map_roots:
            return self._campaign_map_preparation_state_once(
                stage_code,
                button_state=button_state,
                ui_state=ui_state,
            )
        return None

    @staticmethod
    def _campaign_preparation_record_root(
        path: str,
        *,
        record_kind: str,
    ) -> Optional[Tuple[str, str]]:
        """Return a reviewed preparation view root for one active UI record."""

        live_map_prefix = _CAMPAIGN_LIVE_MAP_VIEW_ROOT + "/"
        live_map_uiorigin_prefix = _CAMPAIGN_LIVE_MAP_UIORIGIN_VIEW_ROOT + "/"
        live_normal_map_prefix = _CAMPAIGN_LIVE_NORMAL_MAP_VIEW_ROOT + "/"
        if path.startswith(live_map_prefix) or path.startswith(
            live_map_uiorigin_prefix
        ):
            matched_prefix, matched_panel_root = (
                (live_map_prefix, _CAMPAIGN_LIVE_MAP_PANEL_ROOT)
                if path.startswith(live_map_prefix)
                else (
                    live_map_uiorigin_prefix,
                    _CAMPAIGN_LIVE_MAP_UIORIGIN_PANEL_ROOT,
                )
            )
            relative = path[len(matched_prefix) :]
            reviewed = {
                "button": {
                    **_CAMPAIGN_LIVE_MAP_BUTTON_SPECS,
                    **_CAMPAIGN_LIVE_D1_MAP_BUTTON_ADDITIONS,
                    **_CAMPAIGN_LIVE_B2_MAP_BUTTON_ADDITIONS,
                },
                "toggle": _CAMPAIGN_LIVE_MAP_TOGGLE_SPECS,
                "text": {
                    **_CAMPAIGN_LIVE_MAP_TEXT_COUNTS,
                    **_CAMPAIGN_LIVE_D1_MAP_TEXT_ADDITIONS,
                },
                "image": {
                    **_CAMPAIGN_LIVE_MAP_IMAGE_SPECS,
                    **_CAMPAIGN_LIVE_D1_MAP_IMAGE_ADDITIONS,
                    **_CAMPAIGN_LIVE_B2_MAP_IMAGE_ADDITIONS,
                },
            }.get(record_kind)
            if reviewed is None or relative not in reviewed:
                raise SemanticGateClosed(
                    "campaign live map-preparation record is not reviewed"
                )
            observed = (("map", matched_panel_root),)
        elif path.startswith(live_normal_map_prefix):
            # The reviewed normal-stage live surface contains active records
            # beside ``panel`` (for example the view-owned background).  They
            # are harmless evidence for the same exact view; the actionable
            # controls and stage identity remain proven separately below.
            observed = (("map", _CAMPAIGN_LIVE_NORMAL_MAP_PANEL_ROOT),)
        elif path in _CAMPAIGN_LIVE_FLEET_DIRECT_ANCHORS:
            observed = (("fleet", _CAMPAIGN_LIVE_FLEET_PANEL_ROOT),)
        else:
            observed = tuple(
                (kind, root)
                for kind, root in _CAMPAIGN_PREPARATION_REVIEWED_ROOTS
                if path.startswith(root)
            )
        if len(observed) > 1:
            raise SemanticGateClosed("campaign preparation root is ambiguous")
        family_evidence = any(
            family.lower() in path.lower() for family in _CAMPAIGN_PREPARATION_FAMILIES
        )
        if not observed and family_evidence:
            raise SemanticGateClosed("campaign preparation root is not reviewed")
        if observed and any(
            component in ("", ".", "..") for component in path.split("/")
        ):
            raise SemanticGateClosed("campaign preparation path is not canonical")
        if (
            observed
            and sum(
                path.lower().count(family.lower())
                for family in _CAMPAIGN_PREPARATION_FAMILIES
            )
            != 1
        ):
            raise SemanticGateClosed(
                "campaign preparation path is nested or duplicated"
            )
        return observed[0] if observed else None

    @staticmethod
    def _validate_campaign_live_map_records(
        records: Mapping[str, Sequence[Any]],
        view_root: str,
    ) -> None:
        """Require one exact reviewed LevelInfoSPUI live profile."""

        if view_root not in (
            _CAMPAIGN_LIVE_MAP_VIEW_ROOT,
            _CAMPAIGN_LIVE_MAP_UIORIGIN_VIEW_ROOT,
        ):
            raise SemanticGateClosed("campaign live map-preparation root changed")
        root_prefix = view_root + "/"

        def by_relative(kind: str) -> Dict[str, List[Any]]:
            grouped: Dict[str, List[Any]] = {}
            for record in records.get(kind, ()):
                if not record.path.startswith(root_prefix):
                    continue
                grouped.setdefault(record.path[len(root_prefix) :], []).append(record)
            return grouped

        buttons = by_relative("button")
        toggles = by_relative("toggle")
        texts = by_relative("text")
        images = by_relative("image")
        title_path = "panel/title_form/title_index"
        if title_path not in texts or len(texts[title_path]) != 1:
            raise SemanticGateClosed(
                "campaign live map-preparation stage identity is incomplete"
            )
        stage_identity = texts[title_path][0].text.strip().lower()
        if stage_identity == "sp":
            button_specs = _CAMPAIGN_LIVE_MAP_BUTTON_SPECS
            text_counts = _CAMPAIGN_LIVE_MAP_TEXT_COUNTS
            image_specs = _CAMPAIGN_LIVE_MAP_IMAGE_SPECS
        elif stage_identity in ("c1", "c2", "c3", "d1", "d2", "d3"):
            profile = {
                "c1": {
                    "head": "emotion_zhongxun",
                    "level": "LV 75",
                    "points": "90",
                    "cost_limit": False,
                },
                "c2": {
                    "head": "emotion_zhanlie",
                    "level": "LV 80",
                    "points": "100",
                    "cost_limit": False,
                },
                "c3": {
                    "head": "emotion_hangmu",
                    "level": "LV 85",
                    "points": "110",
                    "cost_limit": False,
                },
                "d1": {
                    "head": "haorenlichade_m_qianting",
                    "level": "LV 95",
                    "points": "120",
                    "cost_limit": True,
                },
                "d2": {
                    "head": "haorenlichade_m_zhanlie",
                    "level": "LV 100",
                    "points": "150",
                    "cost_limit": True,
                },
                "d3": {
                    "head": "haorenlichade_m_hangmu",
                    "level": "LV 105",
                    "points": "180",
                    "cost_limit": True,
                },
            }[stage_identity]
            button_specs = {
                **_CAMPAIGN_LIVE_MAP_BUTTON_SPECS,
                **_CAMPAIGN_LIVE_D1_MAP_BUTTON_ADDITIONS,
            }
            text_counts = {
                **_CAMPAIGN_LIVE_MAP_TEXT_COUNTS,
                **_CAMPAIGN_LIVE_D1_MAP_TEXT_ADDITIONS,
            }
            image_specs = {
                **_CAMPAIGN_LIVE_MAP_IMAGE_SPECS,
                **{
                    path: value
                    for path, value in _CAMPAIGN_LIVE_D1_MAP_IMAGE_ADDITIONS.items()
                    if profile["cost_limit"]
                    or path
                    != "panel/BottomExtra/LoopGroup/view/container/CostLimit"
                },
                "panel/head/Image": ((profile["head"],), True),
            }
        elif stage_identity in ("a2", "a3", "b2", "b3"):
            profile = {
                "a2": {
                    "clone_bgs": ("bg1", "bg1", "bg2", "bg2"),
                    "clone_icons": ("30002", "54000", "54012", "55000"),
                    "head": "emotion_zhanlie",
                },
                "a3": {
                    "clone_bgs": ("bg1", "bg1", "bg2", "bg2"),
                    "clone_icons": ("30002", "54000", "54012", "55000"),
                    "head": "emotion_hangmu",
                },
                "b2": {
                    "clone_bgs": ("bg1", "bg1", "bg2", "bg3"),
                    "clone_icons": ("30003", "54000", "54012", "55000"),
                    "head": "haorenlichade_m_zhanlie",
                },
                "b3": {
                    "clone_bgs": ("bg1", "bg1", "bg2", "bg4"),
                    "clone_icons": ("30004", "54000", "54012", "55000"),
                    "head": "haorenlichade_m_hangmu",
                },
            }[stage_identity]
            button_specs = {
                **_CAMPAIGN_LIVE_MAP_BUTTON_SPECS,
                **_CAMPAIGN_LIVE_B2_MAP_BUTTON_ADDITIONS,
            }
            text_counts = {
                **_CAMPAIGN_LIVE_MAP_TEXT_COUNTS,
                **_CAMPAIGN_LIVE_D1_MAP_TEXT_ADDITIONS,
            }
            image_specs = {
                **{
                    path: value
                    for path, value in _CAMPAIGN_LIVE_MAP_IMAGE_SPECS.items()
                    if path not in ("panel/Level/Hard", "panel/title/Hard")
                },
                **_CAMPAIGN_LIVE_B2_MAP_IMAGE_ADDITIONS,
                "panel/Level/Normal": (("bg_lv_normal",), False),
                "panel/title/Normal": (("bg_title_normal",), False),
                "panel/drops/frame/list/item(Clone)/icon_bg": (
                    profile["clone_bgs"],
                    True,
                ),
                "panel/drops/frame/list/item(Clone)/icon_bg/icon": (
                    profile["clone_icons"],
                    False,
                ),
                "panel/head/Image": ((profile["head"],), True),
            }
        else:
            raise SemanticGateClosed(
                "campaign live map-preparation stage profile is not reviewed"
            )
        if set(buttons) != set(button_specs):
            raise SemanticGateClosed(
                "campaign live map-preparation button surface is incomplete"
            )
        for path, (name, count) in button_specs.items():
            observed = buttons[path]
            if len(observed) != count or any(
                button.name != name
                or not button.active_in_hierarchy
                or not button.active_and_enabled
                or not button.interactable
                or button.raycast_top is not None
                or button.point is None
                or button.bounds is None
                or not button.bounds.contains(button.point)
                for button in observed
            ):
                raise SemanticGateClosed(
                    "campaign live map-preparation button identity is malformed"
                )

        if set(toggles) != set(_CAMPAIGN_LIVE_MAP_TOGGLE_SPECS):
            raise SemanticGateClosed(
                "campaign live map-preparation toggle surface is incomplete"
            )
        for path, count in _CAMPAIGN_LIVE_MAP_TOGGLE_SPECS.items():
            observed = toggles[path]
            if len(observed) != count or any(
                not toggle.active_in_hierarchy
                or not toggle.active_and_enabled
                or not toggle.interactable
                or (path == "panel/quickPlay" and not toggle.checked)
                or toggle.raycast_top is not None
                or toggle.point is None
                or toggle.bounds is None
                for toggle in observed
            ):
                raise SemanticGateClosed(
                    "campaign live map-preparation toggle identity is malformed"
                )

        if set(texts) != set(text_counts):
            raise SemanticGateClosed(
                "campaign live map-preparation text surface is incomplete"
            )
        title_en_path = "panel/title_form/title_en"
        for path, count in text_counts.items():
            observed = texts[path]
            if len(observed) != count or any(
                text.kind != "ugui-text"
                or not text.active_in_hierarchy
                or not text.active_and_enabled
                or text.truncated
                or (
                    path == title_en_path
                    and (text.text != "" or text.bounds is not None)
                )
                or (path != title_en_path and text.bounds is None)
                for text in observed
            ):
                raise SemanticGateClosed(
                    "campaign live map-preparation text identity is malformed"
                )
        if stage_identity == "sp":
            exact_text = {
                "panel/Level/Text": "LV 110",
                "panel/cost/text": "10",
                "panel/drops/frame/list/item/icon_bg/count": "800",
                "panel/title_form/title_en": "",
            }
        elif stage_identity in ("c1", "c2", "c3", "d1", "d2", "d3"):
            exact_text = {
                "panel/Level/Text": profile["level"],
                "panel/cost/text": "10",
                "panel/drops/frame/list/item/icon_bg/count": profile["points"],
                "panel/progress/Text/value": "100%",
                "panel/title_form/title_en": "",
            }
        else:
            level, points = {
                "a2": ("LV 30", "40"),
                "a3": ("LV 35", "50"),
                "b2": ("LV 55", "70"),
                "b3": ("LV 60", "80"),
            }[stage_identity]
            exact_text = {
                "panel/Level/Text": level,
                "panel/cost/text": "10",
                "panel/drops/frame/list/item/icon_bg/count": points,
                "panel/progress/Text/value": "100%",
                "panel/title_form/title_en": "",
            }
        for path, expected in exact_text.items():
            if texts[path][0].text != expected:
                raise SemanticGateClosed(
                    "campaign live map-preparation text value changed"
                )
        if texts[title_path][0].text.strip().lower() != stage_identity:
            raise SemanticGateClosed(
                "campaign live map-preparation stage identity changed"
            )
        if any(
            item.text != ""
            for item in texts["panel/drops/frame/list/item(Clone)/icon_bg/count"]
        ):
            raise SemanticGateClosed(
                "campaign live map-preparation clone count changed"
            )
        for path in (
            "panel/BottomExtra/LoopGroup/Loop/Text",
            "panel/BottomExtra/LoopGroup/view/container/AutoFight/Text",
            "panel/cost/label",
            "panel/drops/title_bg/Text",
            "panel/intro",
            "panel/lose_conditions/desc",
            "panel/quickPlay/desc",
            "panel/title_form/title",
            "panel/win_conditions/desc",
            *(
                (
                    "panel/achieves/achieve(Clone)/desc",
                    "panel/progress/Text",
                )
                if stage_identity
                in (
                    "c1",
                    "c2",
                    "c3",
                    "d1",
                    "d2",
                    "d3",
                    "a2",
                    "a3",
                    "b2",
                    "b3",
                )
                else ()
            ),
        ):
            if any(not item.text.strip() for item in texts[path]):
                raise SemanticGateClosed(
                    "campaign live map-preparation required text is empty"
                )

        optional_bonus_group = (
            {
                "panel/Difficulty/Normal/Bonus1",
                "panel/Difficulty/Normal/Bonus1/Image",
            }
            if stage_identity in ("a2", "a3", "b2", "b3")
            else (
                {
                    "panel/Difficulty/Hard/Bonus1",
                    "panel/Difficulty/Hard/Bonus1/Image",
                }
                if stage_identity in ("c1", "c2", "c3", "d1", "d2", "d3")
                else set()
            )
        )
        optional_image_paths = {
            "panel/BottomExtra/LoopGroup/view/container/AutoFight/Flag"
        } | optional_bonus_group
        required_image_paths = set(image_specs) - optional_image_paths
        observed_image_paths = set(images)
        if not (
            required_image_paths <= observed_image_paths
            and observed_image_paths <= required_image_paths | optional_image_paths
            and (
                not (observed_image_paths & optional_bonus_group)
                or optional_bonus_group <= observed_image_paths
            )
        ):
            raise SemanticGateClosed(
                "campaign live map-preparation image surface is incomplete"
            )
        for path, (sprites, raycast_target) in image_specs.items():
            if path not in images and path in optional_image_paths:
                continue
            observed = images[path]
            if (
                sprites
                and tuple(sorted(image.sprite for image in observed))
                != tuple(sorted(sprites))
            ) or any(
                not image.active_in_hierarchy
                or not image.active_and_enabled
                or image.truncated
                or not image.sprite
                or image.raycast_target is not raycast_target
                or image.raycast_top is not None
                or (sprites and image.bounds is None)
                for image in observed
            ):
                raise SemanticGateClosed(
                    "campaign live map-preparation image identity is malformed"
                )

    def _campaign_preparation_roots(
        self,
        button_state: OracleState,
        ui_state: UiState,
    ) -> Tuple[Tuple[str, ...], Tuple[str, ...]]:
        """Collect all active prep-family evidence without joining roots."""

        records_by_kind = {
            "button": tuple(button_state.buttons),
            "toggle": tuple(ui_state.toggles),
            "text": tuple(ui_state.texts),
            "image": tuple(ui_state.images),
        }
        roots = {"map": set(), "fleet": set()}
        active_by_kind: Dict[str, List[Any]] = {kind: [] for kind in records_by_kind}
        for record_kind, records in records_by_kind.items():
            for record in records:
                if not record.active_in_hierarchy:
                    continue
                active_by_kind[record_kind].append(record)
                resolved = self._campaign_preparation_record_root(
                    record.path, record_kind=record_kind
                )
                if resolved is not None:
                    kind, root = resolved
                    roots[kind].add(root)
        for panel_root, view_root in (
            (_CAMPAIGN_LIVE_MAP_PANEL_ROOT, _CAMPAIGN_LIVE_MAP_VIEW_ROOT),
            (
                _CAMPAIGN_LIVE_MAP_UIORIGIN_PANEL_ROOT,
                _CAMPAIGN_LIVE_MAP_UIORIGIN_VIEW_ROOT,
            ),
        ):
            if panel_root in roots["map"]:
                self._validate_campaign_live_map_records(active_by_kind, view_root)
        return tuple(sorted(roots["map"])), tuple(sorted(roots["fleet"]))

    @staticmethod
    def _campaign_underlay_path_is_reviewed(path: str, *, event: bool) -> bool:
        """Reject remounted/foreign campaign roots before suffix matching."""

        roots = (
            _CAMPAIGN_EVENT_UNDERLAY_ROOTS
            if event
            else _CAMPAIGN_NORMAL_UNDERLAY_ROOTS
        )
        suffix_pattern = (
            r"Battle/Nodes/Chapter_[0-9]+/main"
            if event
            else r"float/levels/items/Chapter_[0-9]+/main"
        )
        if any(
            re.fullmatch(re.escape(root) + suffix_pattern, path) is not None
            for root in roots
        ):
            return True
        family = "LevelSelectSPFullUI" if event else "LevelMainScene"
        if family.lower() in path.lower():
            raise SemanticGateClosed("campaign preparation underlay is not reviewed")
        return False

    @staticmethod
    def _campaign_underlay_identity_texts(
        button_state: OracleState,
        ui_state: UiState,
        stage_code: str,
        *,
        event: bool,
        archive: bool = False,
    ) -> Tuple[ButtonState, TextState, TextState]:
        """Select one exact stage pair after validating every family record."""

        if event and archive:
            raise ValueError("campaign underlay cannot be event and archive")
        family = "LevelSelectSPFullUI" if event else "LevelMainScene"
        roots = (
            _CAMPAIGN_EVENT_UNDERLAY_ROOTS
            if event
            else _CAMPAIGN_NORMAL_UNDERLAY_ROOTS
        )
        stage_pattern = (
            r"Battle/Nodes/Chapter_[0-9]+/main"
            if event
            else r"float/levels/items/Chapter_[0-9]+/main"
        )
        identity_pattern = re.compile(
            r"(?P<stage_path>"
            + r"(?:"
            + "|".join(re.escape(root) for root in roots)
            + r")"
            + stage_pattern
            + r")/info/bk/title_form/(?P<field>title_index|title)"
        )
        text_groups: Dict[str, Dict[str, List[TextState]]] = {}
        for item in ui_state.texts:
            if not item.active_in_hierarchy or not item.active_and_enabled:
                continue
            components = tuple(item.path.split("/"))
            lowered = tuple(component.lower() for component in components)
            if (
                family.lower() not in item.path.lower()
                or "title_form" not in lowered
                or not lowered
                or lowered[-1] not in ("title_index", "title")
            ):
                continue
            identity = identity_pattern.fullmatch(item.path)
            if identity is None:
                raise SemanticGateClosed(
                    "campaign preparation underlay is not reviewed"
                )
            stage_path = identity.group("stage_path")
            field = identity.group("field")
            text_groups.setdefault(stage_path, {}).setdefault(field, []).append(item)

        button_groups: Dict[str, List[ButtonState]] = {}
        for button in button_state.buttons:
            if (
                button.name != "main"
                or not button.active_in_hierarchy
                or not button.active_and_enabled
                or family.lower() not in button.path.lower()
            ):
                continue
            if not CampaignPreparationOracle._campaign_underlay_path_is_reviewed(
                button.path, event=event
            ):
                raise SemanticGateClosed(
                    "campaign preparation underlay is not reviewed"
                )
            button_groups.setdefault(button.path, []).append(button)

        requested_stage = stage_code.strip().lower()
        requested_normal = re.fullmatch(
            r"([1-9][0-9]*)-([1-9][0-9]*)", requested_stage
        )
        validated = []
        stage_paths = set(text_groups).union(button_groups)
        for stage_path in stage_paths:
            fields = text_groups.get(stage_path, {})
            buttons = button_groups.get(stage_path, [])
            title_indexes = fields.get("title_index", [])
            titles = fields.get("title", [])
            if (
                len(buttons) != 1
                or buttons[0].bounds is None
                or len(title_indexes) != 1
                or len(titles) != 1
            ):
                raise SemanticGateClosed(
                    "campaign fleet-preparation underlay group is incomplete or ambiguous"
                )
            title_index = title_indexes[0]
            title = titles[0]
            observed_stage = title_index.text.strip().lower()
            observed_normal = re.fullmatch(
                r"([1-9][0-9]*)[\-–—]([1-9][0-9]*)", observed_stage
            )
            if observed_normal is not None:
                observed_stage = "{0}-{1}".format(*observed_normal.groups())
            if (
                title_index.truncated
                or title.truncated
                or not title.text.strip()
                or (
                (event or archive)
                and re.fullmatch(r"[a-z]+[0-9]*", observed_stage) is None
                )
            ):
                raise SemanticGateClosed(
                    "campaign fleet-preparation underlay identity is malformed"
                )
            if not event and not archive:
                if observed_normal is None:
                    raise SemanticGateClosed(
                        "campaign fleet-preparation underlay identity is malformed"
                    )
                chapter, index = (int(value) for value in observed_normal.groups())
                object_id = int(stage_path.rsplit("Chapter_", 1)[1].split("/", 1)[0])
                expected_id = chapter * 100 + index
                if object_id not in (expected_id, expected_id + 10000):
                    raise SemanticGateClosed(
                        "campaign fleet-preparation underlay identity is malformed"
                    )
            validated.append((observed_stage, buttons[0], title_index, title))

        selected = tuple(
            (button, title_index, title)
            for observed_stage, button, title_index, title in validated
            if observed_stage == requested_stage
        )

        if len(selected) > 1:
            raise SemanticGateClosed(
                "campaign fleet-preparation underlay identity is ambiguous"
            )
        if len(selected) != 1:
            if validated:
                raise SemanticGateClosed(
                    "campaign fleet-preparation stage identity changed"
                )
            raise SemanticGateClosed(
                "campaign fleet-preparation underlay identity is absent or ambiguous"
            )
        if not event and not archive and requested_normal is None:
            raise SemanticGateClosed("campaign stage code is not canonical")
        return selected[0]

    @staticmethod
    def _campaign_fleet_underlay_pair_is_reviewed(
        fleet_root: str,
        stage_button: ButtonState,
        *,
        event: bool,
    ) -> bool:
        """Bind one fleet overlay to its exact observer-variant underlay."""

        suffix_pattern = (
            r"Battle/Nodes/Chapter_[0-9]+/main"
            if event
            else r"float/levels/items/Chapter_[0-9]+/main"
        )
        matches = tuple(
            (candidate_fleet_root, candidate_underlay_root)
            for candidate_event, candidate_fleet_root, candidate_underlay_root in (
                _CAMPAIGN_FLEET_UNDERLAY_ROOT_PAIRS
            )
            if candidate_event is event
            and candidate_fleet_root == fleet_root
            and re.fullmatch(
                re.escape(candidate_underlay_root) + suffix_pattern,
                stage_button.path,
            )
            is not None
        )
        if len(matches) != 1:
            raise SemanticGateClosed(
                "campaign fleet-preparation observer roots are not a reviewed pair"
            )
        return True

    @staticmethod
    def _campaign_map_underlay_pair_is_reviewed(
        map_root: str,
        stage_button: ButtonState,
    ) -> bool:
        """Bind one EventSp detail overlay to its reviewed observer underlay."""

        matches = tuple(
            (candidate_map_root, candidate_underlay_root)
            for candidate_map_root, candidate_underlay_root in (
                _CAMPAIGN_MAP_UNDERLAY_ROOT_PAIRS
            )
            if candidate_map_root == map_root
            and re.fullmatch(
                re.escape(candidate_underlay_root)
                + r"Battle/Nodes/Chapter_[0-9]+/main",
                stage_button.path,
            )
            is not None
        )
        if len(matches) != 1:
            raise SemanticGateClosed(
                "campaign map-preparation observer roots are not a reviewed pair"
            )
        return True

    @staticmethod
    def _campaign_event_underlay_evidence(
        button_state: OracleState,
        ui_state: UiState,
    ) -> bool:
        return any(
            record.active_in_hierarchy and "levelselectspfullui" in record.path.lower()
            for record in (
                *button_state.buttons,
                *ui_state.toggles,
                *ui_state.texts,
                *ui_state.images,
            )
        )

    @staticmethod
    def _campaign_eventsp_remaining_attempts(text: str) -> int:
        exact = {
            "<color=#92FC63FF>1/1</color>": 1,
            "<color=#FF5C5CFF>0/1</color>": 0,
        }
        remaining = exact.get(text.strip())
        if remaining is None:
            raise SemanticGateClosed("event SP attempt counter is malformed")
        return remaining

    @staticmethod
    def _validate_campaign_live_map_underlay(
        button_state: OracleState,
        ui_state: UiState,
        stage_button: ButtonState,
        stage_code: str,
    ) -> Optional[int]:
        """Require the exact reviewed selector identity obscured by LevelInfoSPUI."""

        expected_stage_roots = {
            "sp": (_CAMPAIGN_LIVE_EVENTSP_STAGE_ROOT,),
            "a2": (_CAMPAIGN_LIVE_EVENTA2_STAGE_ROOT,),
            "a3": (_CAMPAIGN_LIVE_EVENTA3_STAGE_ROOT,),
            "c1": (_CAMPAIGN_LIVE_EVENTC1_STAGE_ROOT,),
            "c2": (
                _CAMPAIGN_LIVE_EVENTA2_STAGE_ROOT,
                _CAMPAIGN_LIVE_EVENTC2_STAGE_ROOT,
            ),
            "c3": (
                _CAMPAIGN_LIVE_EVENTA3_STAGE_ROOT,
                _CAMPAIGN_LIVE_EVENTC3_STAGE_ROOT,
            ),
            "d1": (_CAMPAIGN_LIVE_EVENTD1_STAGE_ROOT,),
            "d2": (
                _CAMPAIGN_LIVE_EVENTB2_STAGE_ROOT,
                _CAMPAIGN_LIVE_EVENTD2_STAGE_ROOT,
            ),
            "d3": (
                _CAMPAIGN_LIVE_EVENTB3_STAGE_ROOT,
                _CAMPAIGN_LIVE_EVENTD3_STAGE_ROOT,
            ),
            "b2": (_CAMPAIGN_LIVE_EVENTB2_STAGE_ROOT,),
            "b3": (_CAMPAIGN_LIVE_EVENTB3_STAGE_ROOT,),
        }.get(stage_code)
        if (
            expected_stage_roots is None
            or stage_button.path not in expected_stage_roots
            or stage_button.name != "main"
            or not stage_button.active_in_hierarchy
            or not stage_button.active_and_enabled
            or not stage_button.interactable
            or stage_button.raycast_top is not None
            or stage_button.point is None
            or stage_button.bounds is None
            or not stage_button.bounds.contains(stage_button.point)
        ):
            raise SemanticGateClosed(
                "campaign live map-preparation stage underlay is malformed"
            )

        story_path = _CAMPAIGN_LIVE_EVENTSP_UNDERLAY_ROOT + "Battle/Mask/Story/Switch"
        story = tuple(
            button
            for button in button_state.buttons
            if button.active_in_hierarchy
            and "levelselectspfullui" in button.path.lower()
            and (
                button.name == "Switch"
                or button.path.lower().endswith("/battle/mask/story/switch")
            )
        )
        if (
            len(story) != 1
            or story[0].path != story_path
            or story[0].name != "Switch"
            or not story[0].active_and_enabled
            or not story[0].interactable
            or story[0].raycast_top not in (None, False)
            or story[0].point is None
            or story[0].bounds is None
        ):
            raise SemanticGateClosed(
                "campaign live map-preparation story underlay is malformed"
            )

        # Ordinary event stages have no daily attempt counter.  Their exact
        # stage node, title, overlay profile, and actionable controls have
        # already been bound above; the remaining checks are SP-only evidence.
        if stage_code in (
            "a2",
            "a3",
            "c1",
            "c2",
            "c3",
            "d1",
            "d2",
            "d3",
            "b2",
            "b3",
        ):
            return None

        tries_path = _CAMPAIGN_LIVE_EVENTSP_STAGE_ROOT + "/triesLimit/Text"
        selected_text_path = _CAMPAIGN_LIVE_EVENTSP_SELECTED_ROOT + "Text"
        relevant_texts = tuple(
            item
            for item in ui_state.texts
            if item.active_in_hierarchy
            and "levelselectspfullui" in item.path.lower()
            and (
                item.path.lower().endswith("/trieslimit/text")
                or item.path.lower().endswith("/selected/text")
            )
        )
        tries = tuple(item for item in relevant_texts if item.path == tries_path)
        selected = tuple(
            item for item in relevant_texts if item.path == selected_text_path
        )
        if len(relevant_texts) != 2 or len(tries) != 1 or len(selected) != 1:
            raise SemanticGateClosed(
                "campaign live map-preparation selected-stage underlay is ambiguous"
            )
        if (
            not tries[0].active_and_enabled
            or tries[0].truncated
            or tries[0].bounds is None
            or not selected[0].active_and_enabled
            or selected[0].truncated
            or selected[0].bounds is None
            or selected[0].text.strip().lower() != "sp"
        ):
            raise SemanticGateClosed(
                "campaign live map-preparation selected-stage underlay changed"
            )
        remaining_attempts = CampaignPreparationOracle._campaign_eventsp_remaining_attempts(
            tries[0].text
        )

        selected_images = {
            _CAMPAIGN_LIVE_EVENTSP_SELECTED_ROOT + "Frame": "level_item_select",
            _CAMPAIGN_LIVE_EVENTSP_SELECTED_ROOT + "Light": "level_item_light",
        }
        relevant_images = tuple(
            item
            for item in ui_state.images
            if item.active_in_hierarchy
            and "levelselectspfullui" in item.path.lower()
            and (
                item.path.lower().endswith("/selected/frame")
                or item.path.lower().endswith("/selected/light")
            )
        )
        if len(relevant_images) != len(selected_images):
            raise SemanticGateClosed(
                "campaign live map-preparation selected images are ambiguous"
            )
        for path, sprite in selected_images.items():
            matches = tuple(item for item in relevant_images if item.path == path)
            if (
                len(matches) != 1
                or matches[0].sprite != sprite
                or not matches[0].active_and_enabled
                or matches[0].truncated
                or matches[0].bounds is None
            ):
                raise SemanticGateClosed(
                    "campaign live map-preparation selected image changed"
                )
        return remaining_attempts

    def campaign_map_preparation_state(
        self, stage_code: str
    ) -> CampaignPreparationState:
        """Read one exact ALAS MAP_PREPARATION surface for the selected stage."""

        return self._retry_transition_read(
            lambda: self._campaign_map_preparation_state_once(stage_code)
        )

    def campaign_map_preparation_mode_state(self, stage_code: str) -> str:
        """Return the exact normal/hard state on a shared event-stage detail."""

        preparation = self.campaign_map_preparation_state(stage_code)
        if "LevelStageInfoView(Clone)/panel/" in preparation.proceed_button.path:
            # The chapter-page button names its destination, not the active
            # difficulty. Main and archive stages share this native detail.
            destination = self.campaign_mode_switch_state()
            return "normal" if destination == "hard" else "hard"
        if "LevelInfoSPUI(Clone)/panel/" not in preparation.proceed_button.path:
            raise SemanticGateClosed(
                "campaign map-preparation mode switch is not on an event stage"
            )
        state = self.read_state()
        observed = []
        for mode in ("normal", "hard"):
            suffix = (
                "LevelInfoSPUI(Clone)/panel/Difficulty/"
                + mode.capitalize()
                + "/Switch"
            )
            matches = tuple(
                button
                for button in state.buttons
                if button.name == "Switch"
                and button.path.endswith(suffix)
                and button.active_in_hierarchy
                and button.active_and_enabled
                and button.interactable
                and button.point is not None
                and button.bounds is not None
            )
            if len(matches) > 1:
                raise SemanticGateClosed(
                    "campaign map-preparation mode switch is ambiguous"
                )
            if matches:
                observed.append(mode)
        if len(observed) != 1:
            raise SemanticGateClosed(
                "campaign map-preparation mode switch is absent or ambiguous"
            )
        return observed[0]

    def click_campaign_map_preparation_mode(
        self, stage_code: str, destination: str
    ) -> ActionReceipt:
        """Switch one shared event-stage detail to the requested difficulty."""

        if destination not in ("normal", "hard"):
            raise SemanticGateClosed(
                "campaign map-preparation mode destination is invalid"
            )
        current = self.campaign_map_preparation_mode_state(stage_code)
        if current == destination:
            raise SemanticGateClosed(
                "campaign map-preparation mode already matches destination"
            )
        state = self.read_state()
        suffix = (
            "LevelInfoSPUI(Clone)/panel/Difficulty/"
            + current.capitalize()
            + "/Switch"
        )
        matches = tuple(
            button
            for button in state.buttons
            if button.name == "Switch"
            and button.path.endswith(suffix)
            and button.active_in_hierarchy
            and button.active_and_enabled
            and button.interactable
            and button.point is not None
            and button.bounds is not None
        )
        if len(matches) != 1:
            raise SemanticGateClosed(
                "campaign map-preparation mode target is absent or ambiguous"
            )
        target = matches[0]
        semantic_id = "campaign/map-preparation/mode/" + destination
        if self._blocking_rules(state, semantic_id):
            raise SemanticGateClosed(
                "campaign map-preparation mode switch is blocked"
            )
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("foreground changed immediately before input")
        point = Point(
            (target.bounds.left + target.bounds.right) / 2.0,
            (target.bounds.top + target.bounds.bottom) / 2.0,
        )
        self._tap(int(round(point.x)), int(round(point.y)))
        return ActionReceipt(
            semantic_id=semantic_id,
            generation=state.generation,
            point=point,
            bounds=target.bounds,
            path=target.path,
        )

    def campaign_map_achievement_state(
        self, stage_code: str
    ) -> CampaignMapAchievementState:
        """Read stop-condition progress from one proven stage-detail layer.

        The legacy ALAS implementation samples framebuffer colors for the
        progress bar, stars, and threat-safe label. The observer exposes the
        exact Unity Text and Image records used by that surface, so semantic
        mode consumes those records directly and fails closed when the stage
        layer is incomplete.
        """

        return self._retry_transition_read(
            lambda: self._campaign_map_achievement_state_once(stage_code)
        )

    def campaign_map_clear_percentage(self, stage_code: str) -> float:
        """Read only the progress bar when a client omits star Image records."""

        def read_once() -> float:
            preparation = self.campaign_map_preparation_state(stage_code)
            ui_state = self.read_ui_state()
            if (
                ui_state.generation < preparation.generation
                or ui_state.generation > preparation.generation + 8
            ):
                raise SemanticGateClosed(
                    "campaign achievement snapshots are not coherent"
                )
            if "LevelStageInfoView(Clone)/panel/" in preparation.proceed_button.path:
                root = "LevelStageInfoView(Clone)/panel/"
            elif "LevelInfoSPUI(Clone)/panel/" in preparation.proceed_button.path:
                root = "LevelInfoSPUI(Clone)/panel/"
            else:
                raise SemanticGateClosed(
                    "campaign achievement layer identity is not reviewed"
                )
            values = tuple(
                item
                for item in ui_state.texts
                if item.path.endswith(root + "progress/Text/value")
                and item.active_in_hierarchy
                and item.active_and_enabled
                and not item.truncated
                and item.bounds is not None
            )
            if len(values) != 1:
                raise SemanticGateClosed(
                    "campaign achievement progress is absent or ambiguous"
                )
            match = re.fullmatch(r"([0-9]{1,3})%", values[0].text.strip())
            if match is None or not 0 <= int(match.group(1)) <= 100:
                raise SemanticGateClosed(
                    "campaign achievement progress is malformed"
                )
            return int(match.group(1)) / 100.0

        return self._retry_transition_read(read_once, attempts=12)

    def _campaign_map_achievement_state_once(
        self, stage_code: str
    ) -> CampaignMapAchievementState:
        preparation = self.campaign_map_preparation_state(stage_code)
        ui_state = self.read_ui_state()
        if (
            ui_state.generation < preparation.generation
            or ui_state.generation > preparation.generation + 2
        ):
            raise SemanticGateClosed("campaign achievement snapshots are not coherent")
        if "LevelStageInfoView(Clone)/panel/" in preparation.proceed_button.path:
            root = "LevelStageInfoView(Clone)/panel/"
        elif "LevelInfoSPUI(Clone)/panel/" in preparation.proceed_button.path:
            root = "LevelInfoSPUI(Clone)/panel/"
        else:
            raise SemanticGateClosed(
                "campaign achievement layer identity is not reviewed"
            )

        values = tuple(
            item
            for item in ui_state.texts
            if item.path.endswith(root + "progress/Text/value")
            and item.active_in_hierarchy
            and item.active_and_enabled
            and not item.truncated
            and item.bounds is not None
        )
        labels = tuple(
            item
            for item in ui_state.texts
            if item.path.endswith(root + "progress/Text")
            and item.active_in_hierarchy
            and item.active_and_enabled
            and not item.truncated
            and item.bounds is not None
        )
        if len(values) != 1 or len(labels) != 1:
            raise SemanticGateClosed(
                "campaign achievement progress is absent or ambiguous"
            )
        percentage = re.fullmatch(r"([0-9]{1,3})%", values[0].text.strip())
        if percentage is None:
            raise SemanticGateClosed("campaign achievement progress is malformed")
        percentage_value = int(percentage.group(1))
        if not 0 <= percentage_value <= 100:
            raise SemanticGateClosed("campaign achievement progress is outside 0..100")

        stars = tuple(
            item
            for item in ui_state.images
            if item.path.endswith(root + "achieves/achieve(Clone)/star")
            and item.name == "star"
            and item.sprite == "star"
            and item.active_in_hierarchy
            and item.active_and_enabled
            and not item.truncated
            and item.bounds is not None
        )
        if len(stars) != 3:
            raise SemanticGateClosed(
                "campaign achievement stars are absent or incomplete"
            )
        ordered_stars = tuple(sorted(stars, key=lambda item: item.bounds.left))
        left_values = tuple(item.bounds.left for item in ordered_stars)
        if any(
            not 250.0 <= later - earlier <= 320.0
            for earlier, later in zip(left_values, left_values[1:])
        ):
            raise SemanticGateClosed("campaign achievement star order is invalid")
        achieved = tuple(
            all(channel >= 0.95 for channel in item.color) for item in ordered_stars
        )
        label = "".join(labels[0].text.split())
        threat_safe = bool(percentage_value == 100 and label.startswith("威胁排除"))
        return CampaignMapAchievementState(
            generation=ui_state.generation,
            clear_percentage=percentage_value / 100.0,
            achieved_stars=achieved,
            threat_safe=threat_safe,
        )

    def _campaign_map_preparation_state_once(
        self,
        stage_code: str,
        *,
        button_state: Optional[OracleState] = None,
        ui_state: Optional[UiState] = None,
    ) -> CampaignPreparationState:
        if (
            re.fullmatch(r"(?:[1-9][0-9]*-[1-9][0-9]*|[a-z]+[0-9]*)", stage_code)
            is None
        ):
            raise SemanticGateClosed("campaign stage code is not canonical")
        if (button_state is None) != (ui_state is None):
            raise ValueError("map preparation snapshots must be supplied together")
        if button_state is None:
            button_state = self.read_state()
            ui_state = self.read_ui_state(check_foreground=False)
        assert ui_state is not None
        map_roots, fleet_roots = self._campaign_preparation_roots(
            button_state, ui_state
        )
        if fleet_roots or len(map_roots) != 1:
            raise SemanticGateClosed(
                "campaign map-preparation root is absent or ambiguous"
            )
        root = map_roots[0]
        proceed_matches = tuple(
            button
            for button in button_state.buttons
            if button.name == "start_button" and button.path == root + "start_button"
        )
        cancel_matches = tuple(
            button
            for button in button_state.buttons
            if button.name == "btnBack" and button.path == root + "btnBack"
        )
        if len(proceed_matches) != 1 or len(cancel_matches) != 1:
            raise SemanticGateClosed(
                "campaign map-preparation controls are absent or ambiguous"
            )
        proceed = proceed_matches[0]
        cancel = cancel_matches[0]
        for semantic_id, button in (
            ("campaign/map-preparation/proceed", proceed),
            ("campaign/map-preparation/cancel", cancel),
        ):
            sp_detail = "LevelInfoSPUI(Clone)/panel/" in button.path
            if (
                not button.active_in_hierarchy
                or not button.active_and_enabled
                or not button.interactable
                or button.point is None
                or button.bounds is None
                or (
                    button.raycast_top is not True
                    and not (sp_detail and button.raycast_top is None)
                )
                or self._blocking_rules(button_state, semantic_id)
            ):
                raise SemanticGateClosed(
                    "campaign map-preparation controls are not proven"
                )

        if (
            ui_state.generation < button_state.generation
            or ui_state.generation > button_state.generation + 2
        ):
            raise SemanticGateClosed(
                "campaign map-preparation snapshots are not coherent"
            )
        title_indexes = tuple(
            item
            for item in ui_state.texts
            if item.path == root + "title_form/title_index"
            and item.active_in_hierarchy
            and item.active_and_enabled
            and not item.truncated
        )
        titles = tuple(
            item
            for item in ui_state.texts
            if item.path == root + "title_form/title"
            and item.active_in_hierarchy
            and item.active_and_enabled
            and not item.truncated
            and item.text.strip()
        )
        if len(title_indexes) != 1 or len(titles) != 1:
            raise SemanticGateClosed(
                "campaign map-preparation stage identity is absent or ambiguous"
            )
        observed_stage = title_indexes[0].text.strip().lower()
        numeric = re.fullmatch(r"([1-9][0-9]*)[\-–—]([1-9][0-9]*)", observed_stage)
        if numeric is not None:
            observed_stage = "{0}-{1}".format(*numeric.groups())
        if observed_stage != stage_code:
            raise SemanticGateClosed("campaign map-preparation stage identity changed")
        oil_cost = None
        remaining_attempts = None
        if root.endswith("LevelInfoSPUI(Clone)/panel/"):
            stage_costs = tuple(
                item
                for item in ui_state.texts
                if item.path == root + "cost/text"
                and item.active_in_hierarchy
                and item.active_and_enabled
                and not item.truncated
                and re.fullmatch(r"[0-9]+", item.text.strip()) is not None
            )
            if len(stage_costs) != 1:
                raise SemanticGateClosed(
                    "campaign event stage oil cost is absent or ambiguous"
                )
            oil_cost = int(stage_costs[0].text.strip())
            if oil_cost <= 0:
                raise SemanticGateClosed(
                    "campaign event stage oil cost is outside the pinned range"
                )
            if (
                root
                in (
                    _CAMPAIGN_LIVE_MAP_PANEL_ROOT,
                    _CAMPAIGN_LIVE_MAP_UIORIGIN_PANEL_ROOT,
                )
                or self._campaign_event_underlay_evidence(button_state, ui_state)
            ):
                stage_button, _underlay_index, _underlay_title = (
                    self._campaign_underlay_identity_texts(
                        button_state,
                        ui_state,
                        stage_code,
                        event=True,
                    )
                )
                self._campaign_map_underlay_pair_is_reviewed(root, stage_button)
                if root in (
                    _CAMPAIGN_LIVE_MAP_PANEL_ROOT,
                    _CAMPAIGN_LIVE_MAP_UIORIGIN_PANEL_ROOT,
                ):
                    remaining_attempts = self._validate_campaign_live_map_underlay(
                        button_state,
                        ui_state,
                        stage_button,
                        stage_code,
                    )
                    if titles[0].text.strip() != _underlay_title.text.strip():
                        raise SemanticGateClosed(
                            "campaign live map-preparation title does not match underlay"
                        )
        return CampaignPreparationState(
            generation=button_state.generation,
            kind="map",
            stage_code=stage_code,
            title=titles[0].text.strip(),
            proceed_button=proceed,
            cancel_button=cancel,
            oil_cost=oil_cost,
            remaining_attempts=remaining_attempts,
        )

    def click_campaign_map_preparation(self, stage_code: str) -> ActionReceipt:
        """Advance from stage details to fleet preparation, never to sortie."""

        observed = self.campaign_map_preparation_state(stage_code)
        if observed.remaining_attempts == 0:
            raise SemanticGateClosed("campaign stage attempts are exhausted")
        target = observed.proceed_button
        actionable = target.actionable or (
            "LevelInfoSPUI(Clone)/panel/" in target.path
            and target.active_in_hierarchy
            and target.active_and_enabled
            and target.interactable
            and target.raycast_top is None
        )
        if not actionable or target.point is None or target.bounds is None:
            raise SemanticGateClosed(
                "campaign map-preparation proceed is not actionable"
            )
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("foreground changed immediately before input")
        point = target.point
        if "LevelInfoSPUI(Clone)/panel/" in target.path:
            point = Point(
                (target.bounds.left + target.bounds.right) / 2.0,
                (target.bounds.top + target.bounds.bottom) / 2.0,
            )
        self._tap(int(round(point.x)), int(round(point.y)))
        return ActionReceipt(
            semantic_id="campaign/map-preparation/proceed",
            generation=observed.generation,
            point=point,
            bounds=target.bounds,
            path=target.path,
        )

    def _campaign_dock_full_targets(
        self, state: OracleState, stage_code: str
    ) -> Mapping[str, ButtonState]:
        """Prove the shared dock-full modal without admitting gem expansion.

        Dock capacity is account-wide; a historical D3 title underneath the
        modal is not part of its identity, and is absent during map combat.
        """
        msgbox_root = "OverlayCamera/Overlay/UIMain/Msgbox(Clone)/"
        popup_root = msgbox_root + "window/"
        target_path = popup_root + "button_container/custom_button_1(Clone)"
        popup_paths = tuple(
            button.path
            for button in state.buttons
            if button.active_in_hierarchy and button.path.startswith(msgbox_root)
        )
        expected_paths = tuple(
            sorted(
                (
                    target_path,
                    target_path,
                    target_path,
                    popup_root + "msg_panel/content",
                    popup_root + "top/btnBack",
                    msgbox_root + "bg",
                )
            )
        )
        if tuple(sorted(popup_paths)) != expected_paths:
            raise SemanticGateClosed(
                "campaign dock-full control surface is not exact"
            )
        buttons = tuple(
            button
            for button in state.buttons
            if button.path == target_path
            and button.name == "custom_button_1(Clone)"
            and button.active_in_hierarchy
            and button.active_and_enabled
            and button.interactable
            and button.raycast_top is True
            and button.point is not None
            and button.bounds is not None
            and button.bounds.contains(button.point)
        )
        if len(buttons) != 3 or len({button.bounds for button in buttons}) != 3:
            raise SemanticGateClosed(
                "campaign dock-full buttons are absent or ambiguous"
            )
        for semantic_id in (
            "campaign/dock-full/organize",
            "campaign/dock-full/enhance",
        ):
            if self._blocking_rules(state, semantic_id):
                raise SemanticGateClosed("campaign dock-full action is blocked")

        ui_state = self._stable_msgbox_ui_state(state)
        content = tuple(
            text
            for text in ui_state.texts
            if text.path == popup_root + "msg_panel/content"
            and text.active_in_hierarchy
            and text.active_and_enabled
            and not text.truncated
            and text.bounds is not None
            and text.text.strip()
        )
        labels = tuple(
            text
            for text in ui_state.texts
            if text.path == target_path + "/pic"
            and text.active_in_hierarchy
            and text.active_and_enabled
            and not text.truncated
            and text.bounds is not None
            and text.text.strip()
        )
        if (
            len(content) != 1
            or len(labels) != 3
        ):
            raise SemanticGateClosed(
                "campaign dock-full identity is incomplete or ambiguous: "
                f"content={len(content)}, "
                f"labels={len(labels)}"
            )
        if not content[0].text.strip().startswith("船坞已满") or "整理" not in content[0].text:
            raise SemanticGateClosed("campaign dock-full message is not proven")

        normalized = {"".join(label.text.split()): label for label in labels}
        if set(normalized) != {"强化", "拓展", "整理"}:
            raise SemanticGateClosed("campaign dock-full labels are not exact")
        targets: dict[str, ButtonState] = {}
        for choice, text in (
            ("enhance", "强化"),
            ("expand", "拓展"),
            ("organize", "整理"),
        ):
            label = normalized[text]
            centre = Point(
                (label.bounds.left + label.bounds.right) / 2.0,
                (label.bounds.top + label.bounds.bottom) / 2.0,
            )
            labelled = tuple(
                button for button in buttons if button.bounds.contains(centre)
            )
            if len(labelled) != 1:
                raise SemanticGateClosed(
                    "campaign dock-full label is not bound to one action"
                )
            targets[choice] = labelled[0]
        if len({target.bounds for target in targets.values()}) != 3:
            raise SemanticGateClosed("campaign dock-full actions are not unique")
        return targets

    def campaign_dock_full_visible(self, stage_code: str) -> bool:
        state = self.read_state()
        if not any(
            button.path.startswith(
                "OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/"
            )
            for button in state.buttons
        ):
            return False
        ui = self._stable_msgbox_ui_state(state)
        labels = {"".join(t.text.split()) for t in ui.texts
                  if t.path.startswith("OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/button_container/")
                  and t.path.endswith("/pic") and t.active_in_hierarchy and not t.truncated}
        if not labels.intersection({"强化", "拓展", "整理"}):
            return False
        self._campaign_dock_full_targets(state, stage_code)
        return True

    def click_campaign_dock_full_choice(
        self, stage_code: str, choice: str
    ) -> ActionReceipt:
        if choice not in ("organize", "enhance"):
            raise SemanticGateClosed(
                "campaign dock expansion is not authorized by semantic recovery"
            )
        state = self.read_state()
        target = self._campaign_dock_full_targets(state, stage_code)[choice]
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("foreground changed immediately before input")
        assert target.bounds is not None
        point = Point(
            (target.bounds.left + target.bounds.right) / 2.0,
            (target.bounds.top + target.bounds.bottom) / 2.0,
        )
        self._tap(int(round(point.x)), int(round(point.y)))
        return ActionReceipt(
            semantic_id="campaign/dock-full/" + choice,
            generation=state.generation,
            point=point,
            bounds=target.bounds,
            path=target.path,
        )

    def cancel_campaign_map_preparation(self, stage_code: str) -> ActionReceipt:
        """Close the exact stage-detail preparation without advancing."""

        observed = self.campaign_map_preparation_state(stage_code)
        target = observed.cancel_button
        actionable = target.actionable or (
            "LevelInfoSPUI(Clone)/panel/" in target.path
            and target.active_in_hierarchy
            and target.active_and_enabled
            and target.interactable
            and target.raycast_top is None
        )
        if not actionable or target.point is None or target.bounds is None:
            raise SemanticGateClosed(
                "campaign map-preparation cancel is not actionable"
            )
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("foreground changed immediately before input")
        point = target.point
        if "LevelInfoSPUI(Clone)/panel/" in target.path:
            point = Point(
                (target.bounds.left + target.bounds.right) / 2.0,
                (target.bounds.top + target.bounds.bottom) / 2.0,
            )
        self._tap(int(round(point.x)), int(round(point.y)))
        return ActionReceipt(
            semantic_id="campaign/map-preparation/cancel",
            generation=observed.generation,
            point=point,
            bounds=target.bounds,
            path=target.path,
        )
