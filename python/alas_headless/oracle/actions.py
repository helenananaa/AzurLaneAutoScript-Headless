"""Actions for the typed ALAS boundary."""

from __future__ import annotations

from typing import Union
from .private_quarters import PrivateQuartersPhysicsReceipt

import math
import re
from typing import Optional, Tuple
from .contracts import ActionReceipt, ButtonState, Point
from .errors import SemanticGateClosed, SemanticOracleError


class ActionsOracle:
    """Actions operations sharing the oracle frame and input boundary."""

    def click(self, semantic_id: str) -> Union[ActionReceipt, PrivateQuartersPhysicsReceipt]:
        if semantic_id.startswith('private-quarters/'):
            private_quarters_actions = {
                'private-quarters/interact': self.click_private_quarters_interact,
                'private-quarters/character/new-jersey': self.click_private_quarters_new_jersey_body,
                'private-quarters/home': self.click_private_quarters_home,
                'private-quarters/room/back': self.click_private_quarters_room_back,
                'private-quarters/room/new-jersey': self.click_private_quarters_new_jersey,
                'private-quarters/dialogue/continue': self.click_private_quarters_new_jersey_dialogue,
            }
            if semantic_id in private_quarters_actions:
                return private_quarters_actions[semantic_id]()
        delegated_new_ship_reward = semantic_id == "reward/new-ship/continue"
        state = (
            self._new_ship_reward_action_state()
            if delegated_new_ship_reward
            else self.read_state()
        )
        if (semantic_id == "campaign/urgent-notice/confirm"
                and not self._campaign_urgent_notice_matches(state)):
            raise SemanticGateClosed("campaign urgent notice identity is not proven")
        delegated_login_update = (
            semantic_id == "login/update/download"
            and self._login_update_download_prompt_matches(state)
        )
        delegated_login_restart = (
            semantic_id
            in ("login/update/restart-dialog", "login/update/restart-msgbox")
            and self._login_update_restart_prompt_target(state) == semantic_id
        )
        delegated_activity_main_back = bool(
            semantic_id == "event-list/page/back"
            and len(self._matches(state, "event-list/page/back")) == 1
            and not self._matches(state, "reward/award-info/close")
            and not self._matches(state, "reward/award-info1/close")
        )
        delegated_mail_confirmation = bool(
            semantic_id in ("mail/confirm/claim", "mail/confirm/cancel")
            and self.mail_confirmation_kind() is not None
        )
        delegated_exercise_opponent = bool(
            semantic_id.startswith("exercise/opponent/")
            and self.exercise_page_visible()
        )
        delegated_exercise_start = bool(
            semantic_id == "exercise/opponent/start"
            and self.exercise_opponent_detail_visible()
        )
        delegated_exercise_detail_back = bool(
            semantic_id == "exercise/opponent/back"
            and self.exercise_opponent_detail_visible()
        )
        delegated_exercise_back = bool(
            semantic_id == "exercise/page/back" and self.exercise_page_visible()
        )
        delegated_academy_munitions = bool(
            semantic_id == "academy/munitions" and self.academy_munitions_available()
        )
        delegated_academy_game_room = bool(
            semantic_id == "academy/game-room" and self.academy_page_visible()
        )
        delegated_shipyard_series = bool(
            semantic_id.startswith("shipyard/series/")
            and (semantic_id != "shipyard/series/open" or self.shipyard_page_visible())
        )
        if semantic_id in (
            "overlay/network-reconnect/cancel",
            "overlay/network-reconnect/confirm",
        ):
            if self._dock_full_prompt_matches(state):
                raise SemanticGateClosed(
                    "dock-full prompt cannot use network reconnect input"
                )
            if not self._network_reconnect_prompt_matches(state):
                raise SemanticGateClosed(
                    "network reconnect prompt identity is not proven"
                )
        if (
            semantic_id == "overlay/login-data-expired/confirm"
            and not self._login_data_expired_prompt_matches(state)
        ):
            raise SemanticGateClosed("login-data-expired prompt identity is not proven")
        if semantic_id in (
            "minigame/tickets/cancel",
            "minigame/tickets/confirm",
        ) and not self._minigame_ticket_prompt_matches(state):
            raise SemanticGateClosed("minigame ticket prompt identity is not proven")
        target = self._unique(state, semantic_id)
        if delegated_activity_main_back:
            delegated_activity_main_back = bool(
                target.active_in_hierarchy
                and target.active_and_enabled
                and target.interactable
                and target.raycast_top is not False
                and target.point is not None
                and target.bounds is not None
                and target.bounds.contains(target.point)
            )
        delegated_guild_control = False
        if semantic_id in (
            "guild/lobby/report",
            "guild/logistics/supply",
            "guild/logistics/mission",
            "guild/operations/formation",
            "guild/operations/report",
            "guild/operations/dispatch/open",
        ):
            ui_state = self.read_ui_state()
            if (
                ui_state.generation < state.generation
                or ui_state.generation > state.generation + 2
            ):
                raise SemanticGateClosed("guild control snapshots are not coherent")
            delegated_guild_control = self._guild_delegated_button_proven(
                state, ui_state, semantic_id, target
            )
        delegated_guild_dispatch_detail = False
        if semantic_id in (
            "guild/dispatch-detail/close",
            "guild/dispatch-detail/formation",
        ):
            ui_state = self.read_ui_state()
            if (
                ui_state.generation < state.generation
                or ui_state.generation > state.generation + 2
            ):
                raise SemanticGateClosed("guild dispatch snapshots are not coherent")
            delegated_guild_dispatch_detail = (
                self._guild_dispatch_detail_control_proven(
                    state, ui_state, semantic_id, target
                )
            )
        delegated_guild_report = False
        if semantic_id in (
            "guild/report/close",
            "guild/report/claim-all",
        ):
            ui_state = self.read_ui_state()
            if (
                ui_state.generation < state.generation
                or ui_state.generation > state.generation + 2
            ):
                raise SemanticGateClosed("guild report snapshots are not coherent")
            delegated_guild_report = self._guild_report_control_proven(
                state, ui_state, semantic_id, target
            )
        delegated_guild_formation = False
        if semantic_id in (
            "guild/formation/close",
            "guild/formation/recommend",
            "guild/formation/go",
        ):
            ui_state = self.read_ui_state()
            if (
                ui_state.generation < state.generation
                or ui_state.generation > state.generation + 2
            ):
                raise SemanticGateClosed("guild formation snapshots are not coherent")
            delegated_guild_formation = self._guild_formation_control_proven(
                state, ui_state, semantic_id, target
            )
        delegated_main_guild = bool(
            semantic_id == "main/guild"
            and target.active_in_hierarchy
            and target.active_and_enabled
            and target.interactable
            and target.raycast_top is None
            and target.point is not None
            and target.bounds is not None
            and target.bounds.contains(target.point)
            and self.main_page_visible()
        )
        delegated_main_raid = bool(
            semantic_id == "main/raid" and self._main_raid_entry_proven(state)
        )
        delegated_meowfficer_get_continue = bool(
            semantic_id == "meowfficer/get/continue"
            and self._meowfficer_get_continue_proven(state)
        )
        delegated_meowfficer_purchase_control = False
        if semantic_id in (
            "meowfficer/buy/min",
            "meowfficer/buy/add",
            "meowfficer/buy/max",
            "meowfficer/buy/submit",
        ):
            try:
                self.meowfficer_purchase_state()
            except SemanticGateClosed:
                pass
            else:
                delegated_meowfficer_purchase_control = bool(
                    target.active_in_hierarchy
                    and target.active_and_enabled
                    and target.interactable
                    and target.raycast_top is None
                    and target.point is not None
                    and target.bounds is not None
                    and target.bounds.contains(target.point)
                )
        delegated_meowfficer_purchase_skip = bool(
            semantic_id == "meowfficer/buy/skip"
            and self._meowfficer_purchase_skip_proven(state)
        )
        delegated_meowfficer_purchase_prompt = bool(
            semantic_id
            in ("meowfficer/buy/cancel", "meowfficer/buy/confirm")
            and self._meowfficer_purchase_prompt_proven(state)
        )
        delegated_meowfficer_enhance_control = False
        if semantic_id == "meowfficer/enhance/open":
            try:
                self.meowfficer_dock_state()
            except SemanticGateClosed:
                pass
            else:
                delegated_meowfficer_enhance_control = (
                    self._meowfficer_reviewed_control_proven(state, semantic_id)
                )
        elif semantic_id in (
            "meowfficer/enhance/back",
            "meowfficer/feed/open",
            "meowfficer/enhance/submit",
        ):
            try:
                self.meowfficer_enhance_state()
            except SemanticGateClosed:
                pass
            else:
                delegated_meowfficer_enhance_control = (
                    self._meowfficer_reviewed_control_proven(state, semantic_id)
                )
        elif semantic_id in (
            "meowfficer/feed/cancel",
            "meowfficer/feed/confirm",
        ):
            try:
                self.meowfficer_feed_state()
            except SemanticGateClosed:
                pass
            else:
                delegated_meowfficer_enhance_control = (
                    self._meowfficer_reviewed_control_proven(state, semantic_id)
                )
        delegated_meowfficer_enhance_prompt = bool(
            semantic_id
            in ("meowfficer/enhance/cancel", "meowfficer/enhance/confirm")
            and self._meowfficer_enhance_prompt_proven(state)
        )
        delegated_meowfficer_lock_toggle = bool(
            semantic_id in ("meowfficer/get/lock", "meowfficer/get/unlock")
            and self._meowfficer_lock_toggle_proven(state, semantic_id)
        )
        delegated_meowfficer_lock_prompt = bool(
            semantic_id
            in (
                "meowfficer/get/lock-cancel",
                "meowfficer/get/lock-confirm",
            )
            and self._meowfficer_lock_prompt_proven(state)
        )
        delegated_meowfficer_get_result = bool(
            semantic_id == "meowfficer/get/result/close"
            and self._meowfficer_get_result_proven(state)
        )
        delegated_meowfficer_fort_close = bool(
            semantic_id == "meowfficer/fort/close"
            and self._meowfficer_fort_close_proven(state)
        )
        delegated_meowfficer_queue_control = False
        if semantic_id in (
            "meowfficer/queue/auto",
            "meowfficer/queue/start",
            "meowfficer/queue/close",
        ):
            try:
                self.meowfficer_queue_state()
            except SemanticGateClosed:
                pass
            else:
                delegated_meowfficer_queue_control = bool(
                    target.active_in_hierarchy
                    and target.active_and_enabled
                    and target.interactable
                    and target.raycast_top is None
                    and target.point is not None
                    and target.bounds is not None
                    and target.bounds.contains(target.point)
                )
        delegated_meowfficer_queue_prompt = bool(
            semantic_id
            in (
                "meowfficer/queue/cancel",
                "meowfficer/queue/confirm",
            )
            and self._meowfficer_queue_prompt_proven(state)
        )
        delegated_meowfficer_dock_control = False
        if semantic_id in (
            "meowfficer/page/back",
            "meowfficer/fort/enter",
            "meowfficer/buy/enter",
            "meowfficer/train/enter",
        ):
            try:
                self.meowfficer_dock_state()
            except SemanticGateClosed:
                pass
            else:
                delegated_meowfficer_dock_control = bool(
                    target.active_in_hierarchy
                    and target.active_and_enabled
                    and target.interactable
                    and target.raycast_top is None
                    and target.point is not None
                    and target.bounds is not None
                    and target.bounds.contains(target.point)
                )
        delegated_meowfficer_training_control = False
        if semantic_id in (
            "meowfficer/train/close",
            "meowfficer/train/complete/first",
            "meowfficer/train/finish-all",
            "meowfficer/train/start",
        ):
            try:
                training = self.meowfficer_training_state()
            except SemanticGateClosed:
                pass
            else:
                delegated_meowfficer_training_control = bool(
                    (
                        semantic_id != "meowfficer/train/complete/first"
                        or training.completed > 0
                    )
                    and target.active_in_hierarchy
                    and target.active_and_enabled
                    and target.interactable
                    and target.raycast_top is None
                    and target.point is not None
                    and target.bounds is not None
                    and target.bounds.contains(target.point)
                )
        delegated_operation_siren_control = bool(
            semantic_id
            in (
                "os/map/auto-search/off",
                "os/map/auto-search/on",
                "os/map/strategic-search/off",
                "os/map/strategic-search/on",
                "os/strategic-search/confirm",
                "os/strategic-search/cancel",
                "os/map/mission-list",
                "os/map/storage",
                "os/map/order",
                "os/order/back",
                "os/order/scan",
                "os/order/submarine",
                "os/port/enter",
                "os/port/supply",
                "os/port/dock",
                "os/port/dock/back",
                "os/port/dock/repair-all",
                "os/port/back",
                "os/shop/back",
                "os/globe/voucher",
                "os/globe/mission-overview",
                "os/mission-overview/back",
                "os/mission-list/close",
                "os/voucher/back",
                "os/storage/back",
            )
            and target.active_in_hierarchy
            and target.active_and_enabled
            and target.interactable
            and target.raycast_top is None
            and target.point is not None
            and target.bounds is not None
            and target.bounds.contains(target.point)
            and (
                self.operation_siren_state()
                if semantic_id
                in (
                    "os/map/auto-search/off",
                    "os/map/auto-search/on",
                    "os/map/strategic-search/off",
                    "os/map/strategic-search/on",
                    "os/map/mission-list",
                    "os/map/storage",
                    "os/port/enter",
                )
                else True
            )
        )
        delegated_operation_siren_boss_start = bool(
            semantic_id == "os/boss/start"
            and self.operation_siren_boss_preparation_visible()
        )
        delegated_operation_siren_help = bool(
            semantic_id == "os/help/close"
            and target.active_in_hierarchy
            and target.active_and_enabled
            and target.interactable
            and target.raycast_top is None
            and target.point is not None
            and target.bounds is not None
            and target.bounds.contains(target.point)
        )
        delegated_meta_back = bool(
            semantic_id == "meta/page/back"
            and target.active_in_hierarchy
            and target.active_and_enabled
            and target.interactable
            and target.raycast_top is None
            and target.point is not None
            and target.bounds is not None
            and target.bounds.contains(target.point)
            and not self._blocking_rules(state, semantic_id)
        )
        delegated_game_room_list = bool(
            semantic_id == "game-room/list"
            and target.active_in_hierarchy
            and target.active_and_enabled
            and target.interactable
            and target.raycast_top is None
            and target.point is not None
            and target.bounds is not None
        )
        delegated_game_room_home = bool(
            semantic_id == "game-room/home"
            and target.active_in_hierarchy
            and target.active_and_enabled
            and target.interactable
            and target.raycast_top is None
            and target.point is not None
            and target.bounds is not None
            and self.game_room_page_visible()
        )
        delegated_game_room_back = bool(
            semantic_id == "game-room/back"
            and target.active_in_hierarchy
            and target.active_and_enabled
            and target.interactable
            and target.raycast_top is None
            and target.point is not None
            and target.bounds is not None
            and self.game_room_page_visible()
        )
        delegated_shop_home = bool(
            semantic_id == "shop/home"
            and target.active_in_hierarchy
            and target.active_and_enabled
            and target.interactable
            and target.raycast_top is None
            and target.point is not None
            and target.bounds is not None
            and (self.recommendation_shop_visible() or self.game_room_page_visible())
        )
        dorm_back_delegated = (
            semantic_id == "dorm/page/back"
            and self._dorm_back_delegated_raycast_proven(state)
        )
        dorm_empty_food_cancel = (
            semantic_id == "dorm/empty-food/cancel"
            and self._dorm_empty_food_cancel_proven(state)
        )
        dorm_page_control = semantic_id in (
            "dorm/feed",
            "dorm/collect",
        ) and self._dorm_page_control_proven(state, semantic_id)
        mail_manager_back_delegated = (
            semantic_id == "mail/manage/back"
            and self._mail_manager_back_delegated_raycast_proven(state)
        )
        if (
            semantic_id == "tactical/continue/cancel"
            and not self._tactical_continue_prompt_matches(state)
        ):
            raise SemanticGateClosed("tactical continue prompt identity is not proven")
        if semantic_id in (
            "build/warning/cancel",
            "build/warning/confirm",
        ) and not self._build_warning_prompt_matches(state):
            raise SemanticGateClosed("build warning prompt identity is not proven")
        if semantic_id in (
            "build/queue/finish-cancel",
            "build/queue/finish-confirm",
        ) and self._build_queue_finish_prompt_cost(state) is None:
            raise SemanticGateClosed(
                "construction quick-finish prompt identity is not proven"
            )
        if semantic_id in (
            "tactical/course/cancel",
            "tactical/course/confirm",
        ) and not self._tactical_course_prompt_matches(state):
            raise SemanticGateClosed("tactical course prompt identity is not proven")
        if semantic_id in (
            "commission/start/cancel",
            "commission/start/confirm",
        ):
            parts = self._msgbox_prompt_parts(state)
            if parts is None or re.fullmatch(
                r"本次委托需要花费([1-9][0-9]*)石油", parts[0]
            ) is None or parts[1:] != ("取消", "确定"):
                raise SemanticGateClosed(
                    "commission start prompt identity is not proven"
                )
        if semantic_id in (
            "commission/cancel/cancel",
            "commission/cancel/confirm",
        ):
            parts = self._msgbox_prompt_parts(state)
            if parts != ("确定放弃任务？", "取消", "确定"):
                raise SemanticGateClosed(
                    "commission cancel prompt identity is not proven"
                )
        if (
            semantic_id in ("research/start/cancel", "research/start/confirm")
            and self._research_start_prompt_cost(state) is None
        ):
            raise SemanticGateClosed("research start prompt identity is not proven")
        if semantic_id in (
            "research/queue/cancel",
            "research/queue/confirm",
        ) and not self._research_queue_prompt_matches(state):
            raise SemanticGateClosed("research queue prompt identity is not proven")
        if semantic_id in (
            "guild/dispatch/cancel",
            "guild/dispatch/confirm",
        ) and not self._guild_dispatch_prompt_matches(state):
            raise SemanticGateClosed("guild dispatch prompt identity is not proven")
        if semantic_id in (
            "guild/exchange/cancel",
            "guild/exchange/confirm",
        ) and not self._guild_exchange_prompt_matches(state):
            raise SemanticGateClosed("guild exchange prompt identity is not proven")
        if semantic_id == "research/detail/root" and any(
            candidate.actionable
            for candidate in self._matches(state, "research/detail/finish")
        ):
            raise SemanticGateClosed(
                "research detail cannot close through the root while finish is actionable"
            )
        if (
            (
                not target.actionable
                and not delegated_login_update
                and not delegated_login_restart
                and not delegated_activity_main_back
                and not delegated_shop_home
                and not delegated_mail_confirmation
                and not delegated_exercise_opponent
                and not delegated_exercise_start
                and not delegated_exercise_detail_back
                and not delegated_exercise_back
                and not delegated_academy_munitions
                and not delegated_academy_game_room
                and not delegated_game_room_list
                and not delegated_game_room_home
                and not delegated_game_room_back
                and not delegated_shipyard_series
                and not delegated_operation_siren_control
                and not delegated_operation_siren_boss_start
                and not delegated_operation_siren_help
                and not delegated_meta_back
                and not dorm_back_delegated
                and not dorm_empty_food_cancel
                and not dorm_page_control
                and not mail_manager_back_delegated
                and not delegated_new_ship_reward
                and not delegated_meowfficer_dock_control
                and not delegated_meowfficer_training_control
                and not delegated_meowfficer_purchase_control
                and not delegated_meowfficer_purchase_skip
                and not delegated_meowfficer_purchase_prompt
                and not delegated_meowfficer_enhance_control
                and not delegated_meowfficer_enhance_prompt
                and not delegated_meowfficer_get_continue
                and not delegated_meowfficer_lock_toggle
                and not delegated_meowfficer_lock_prompt
                and not delegated_meowfficer_get_result
                and not delegated_meowfficer_fort_close
                and not delegated_meowfficer_queue_control
                and not delegated_meowfficer_queue_prompt
                and not delegated_main_guild
                and not delegated_main_raid
                and not delegated_guild_control
                and not delegated_guild_dispatch_detail
                and not delegated_guild_report
                and not delegated_guild_formation
            )
            or target.point is None
            or target.bounds is None
        ):
            raise SemanticGateClosed("semantic target is not actionable")
        point = target.point
        if (
            delegated_guild_control
            or delegated_guild_dispatch_detail
            or delegated_guild_report
            or delegated_guild_formation
        ):
            # Guild controls commonly expose an edge pivot while their exact
            # typed Button and matching Image cover a much larger visible
            # rectangle.  Use the centre of that proven rectangle.
            point = Point(
                (target.bounds.left + target.bounds.right) / 2.0,
                (target.bounds.top + target.bounds.bottom) / 2.0,
            )
        if semantic_id == "os/order/back":
            # SVOrderPanel anchors this wide back hit area at its left edge.
            # Use the centre of the exact visible bounds so the tap is not
            # delivered on the boundary shared with the panel background.
            assert target.bounds is not None
            point = Point(
                (target.bounds.left + target.bounds.right) / 2.0,
                (target.bounds.top + target.bounds.bottom) / 2.0,
            )
        if semantic_id == "os/help/close":
            # WorldHelpUI anchors its back Button pivot on x=0.  Use the
            # centre of its fully visible proven bounds so Android receives an
            # in-screen coordinate rather than a boundary tap ignored by Unity.
            assert target.bounds is not None
            point = Point(
                (target.bounds.left + target.bounds.right) / 2.0,
                (target.bounds.top + target.bounds.bottom) / 2.0,
            )
        if semantic_id == "meowfficer/page/back":
            # CommanderCatUI docks this button partly outside the left/top
            # viewport and reports that clipped pivot as its input point.
            # The full dock identity was proven above; tap the centre of the
            # visible part of the exact button bounds.
            assert target.bounds is not None
            point = Point(
                (
                    max(target.bounds.left, 0.0)
                    + min(target.bounds.right, self.fingerprint.width - 1.0)
                )
                / 2.0,
                (
                    max(target.bounds.top, 0.0)
                    + min(target.bounds.bottom, self.fingerprint.height - 1.0)
                )
                / 2.0,
            )
        if semantic_id == "meowfficer/train/complete/first":
            # CommanderBoxesUI anchors each completed-slot Button on the top
            # edge of its exact RectTransform.  That pivot is inside the
            # reported bounds but Unity ignores it as a boundary tap.  The
            # training identity and completed-slot text were proven above, so
            # use the centre of this uniquely mapped Button rectangle.
            assert target.bounds is not None
            point = Point(
                (target.bounds.left + target.bounds.right) / 2.0,
                (target.bounds.top + target.bounds.bottom) / 2.0,
            )
        if dorm_page_control:
            ui_state = self.read_ui_state()
            if not self._dorm_page_control_proven(
                state, semantic_id, ui_state=ui_state
            ):
                raise SemanticGateClosed("dorm page control changed before input")
            image_path = (
                target.path + "/icon" if semantic_id == "dorm/feed" else target.path
            )
            image_sprite = "btn_feed" if semantic_id == "dorm/feed" else "onekey"
            click_images = tuple(
                image
                for image in ui_state.images
                if image.path == image_path
                and image.sprite == image_sprite
                and image.bounds is not None
            )
            if len(click_images) != 1:
                raise SemanticGateClosed("dorm page-control click image is ambiguous")
            click_bounds = click_images[0].bounds
            assert click_bounds is not None
            point = Point(
                (click_bounds.left + click_bounds.right) / 2.0,
                (click_bounds.top + click_bounds.bottom) / 2.0,
            )
            if not target.bounds.contains(point):
                raise SemanticGateClosed("dorm page-control click point is invalid")
        if (
            semantic_id == "research/queue/claim"
            and math.isclose(point.x, float(self.fingerprint.width), abs_tol=0.01)
            and math.isclose(
                target.bounds.right, float(self.fingerprint.width), abs_tol=0.01
            )
            and 0 <= target.bounds.left < target.bounds.right
            and 0 <= target.bounds.top < target.bounds.bottom <= self.fingerprint.height
        ):
            # This reviewed edge-docked Button reports its right-edge pivot as
            # the screen point.  Its complete visible bounds and top raycast
            # are proven, so use the centre of the visible in-screen rectangle.
            point = Point(
                (
                    target.bounds.left
                    + min(target.bounds.right, self.fingerprint.width - 1.0)
                )
                / 2.0,
                (target.bounds.top + target.bounds.bottom) / 2.0,
            )
        if not (
            0 <= point.x < self.fingerprint.width
            and 0 <= point.y < self.fingerprint.height
        ):
            raise SemanticGateClosed("semantic target point is outside the screen")

        disallowed = tuple(
            rule.blocker_id for rule in self._blocking_rules(state, semantic_id)
        )
        if disallowed:
            raise SemanticGateClosed(
                "semantic input is blocked by: {0}".format(", ".join(disallowed))
            )
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("foreground changed immediately before input")

        x = int(round(point.x))
        y = int(round(point.y))
        self._tap(x, y)
        if delegated_login_update or delegated_login_restart:
            # A small maintenance patch can finish between observer frames.
            # The exact reviewed confirmation is sufficient to establish the
            # update session for the later completion/restart gate.
            self._login_update_seen = True
        return ActionReceipt(
            semantic_id=semantic_id,
            generation=state.generation,
            point=point,
            bounds=target.bounds,
            path=target.path,
        )

    def wait_for(
        self,
        semantic_id: str,
        timeout_seconds: float,
        minimum_generation: Optional[int] = None,
        interval_seconds: float = 0.5,
    ) -> ButtonState:
        deadline = self._monotonic() + timeout_seconds
        last_error: Optional[SemanticOracleError] = None
        while self._monotonic() < deadline:
            try:
                state = self.read_state()
                matches = self._matches(state, semantic_id)
                if len(matches) > 1:
                    raise SemanticGateClosed("semantic target mapping is ambiguous")
                if (
                    matches
                    and matches[0].actionable
                    and not self._blocking_rules(state, semantic_id)
                    and (
                        minimum_generation is None
                        or state.generation > minimum_generation
                    )
                ):
                    return matches[0]
            except SemanticOracleError as exc:
                last_error = exc
            self._sleep(interval_seconds)
        if last_error is not None:
            raise SemanticGateClosed("semantic wait timed out") from last_error
        raise SemanticGateClosed("semantic wait timed out")

    def wait_for_any(
        self,
        semantic_ids: Tuple[str, ...],
        timeout_seconds: float,
        minimum_generation: Optional[int] = None,
        interval_seconds: float = 0.5,
    ) -> Tuple[str, ButtonState]:
        if not semantic_ids or len(set(semantic_ids)) != len(semantic_ids):
            raise ValueError("semantic wait set must contain unique targets")
        deadline = self._monotonic() + timeout_seconds
        last_error: Optional[SemanticOracleError] = None
        while self._monotonic() < deadline:
            try:
                state = self.read_state()
                actionable = []
                for semantic_id in semantic_ids:
                    matches = self._matches(state, semantic_id)
                    if len(matches) > 1:
                        raise SemanticGateClosed("semantic target mapping is ambiguous")
                    if semantic_id == "reward/new-ship/continue":
                        if matches and self._new_ship_reward_visible_in_state(state):
                            actionable.append((semantic_id, matches[0]))
                        continue
                    if (
                        matches
                        and matches[0].actionable
                        and not self._blocking_rules(state, semantic_id)
                    ):
                        actionable.append((semantic_id, matches[0]))
                if len(actionable) > 1:
                    raise SemanticGateClosed("semantic wait set is ambiguous")
                if len(actionable) == 1 and (
                    minimum_generation is None or state.generation > minimum_generation
                ):
                    return actionable[0]
            except SemanticOracleError as exc:
                last_error = exc
            self._sleep(interval_seconds)
        if last_error is not None:
            raise SemanticGateClosed("semantic wait timed out") from last_error
        raise SemanticGateClosed("semantic wait timed out")

    def click_and_wait(
        self,
        semantic_id: str,
        expected_semantic_id: str,
        timeout_seconds: float,
    ) -> ButtonState:
        receipt = self.click(semantic_id)
        return self.wait_for(
            expected_semantic_id,
            timeout_seconds,
            minimum_generation=receipt.generation,
        )
