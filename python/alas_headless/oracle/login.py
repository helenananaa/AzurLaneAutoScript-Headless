"""Login for the typed ALAS boundary."""

from __future__ import annotations

import re
from typing import Optional, Tuple
from .contracts import ActionReceipt, OracleState, TextState, UI_SCHEMA
from .errors import ObserverTransportError, SemanticGateClosed


class LoginOracle:
    """Login operations sharing the oracle frame and input boundary."""

    def _login_data_expired_prompt_matches(self, state: OracleState) -> bool:
        ui_state = self._stable_msgbox_ui_state(state)

        def matches(suffix: str) -> Tuple[TextState, ...]:
            return tuple(
                text
                for text in ui_state.texts
                if text.path.endswith(suffix)
                and text.active_in_hierarchy
                and text.active_and_enabled
                and not text.truncated
                and text.bounds is not None
            )

        content = matches("Msgbox(Clone)/window/msg_panel/content")
        confirm = matches(
            "Msgbox(Clone)/window/button_container/custom_button_1(Clone)/pic"
        )
        cancel = matches(
            "Msgbox(Clone)/window/button_container/custom_button_2(Clone)/pic"
        )
        buttons = self._matches(state, "overlay/login-data-expired/confirm")
        return bool(
            len(content) == 1
            and content[0].text.strip() in {"登录数据失效", "您在别处登录"}
            and len(confirm) == 1
            and "".join(confirm[0].text.split()) == "确定"
            and not cancel
            and len(buttons) == 1
        )

    def server_maintenance_visible(self) -> bool:
        """Recognize CN maintenance; a cancel button does not make it actionable login."""

        state = self.read_state()
        ui_state = self._stable_msgbox_ui_state(state)

        def matches(suffix: str) -> Tuple[TextState, ...]:
            return tuple(
                text
                for text in ui_state.texts
                if text.path.endswith(suffix)
                and text.active_in_hierarchy
                and text.active_and_enabled
                and not text.truncated
                and text.bounds is not None
            )

        content = matches("Msgbox(Clone)/window/msg_panel/content")
        confirm = matches(
            "Msgbox(Clone)/window/button_container/custom_button_1(Clone)/pic"
        )
        cancel = matches(
            "Msgbox(Clone)/window/button_container/custom_button_2(Clone)/pic"
        )
        buttons = self._matches(state, "overlay/server-maintenance/confirm")
        return bool(
            len(content) == 1
            and content[0].text.strip() == "服务器维护"
            and len(confirm) == 1
            and "".join(confirm[0].text.split()) == "确定"
            and (not cancel or (len(cancel) == 1 and ''.join(cancel[0].text.split()) == '取消'))
            and len(buttons) == 1
            and buttons[0].actionable
        )

    def _login_update_download_prompt_matches(self, state: OracleState) -> bool:
        ui_state = self.read_text_state()
        if (
            ui_state.generation < state.generation
            or ui_state.generation > state.generation + 2
        ):
            raise SemanticGateClosed("login update snapshots are not coherent")
        content = tuple(
            text
            for text in ui_state.texts
            if text.path.endswith("DialogPanel/dialog/content/Text")
            and text.active_in_hierarchy
            and text.active_and_enabled
            and not text.truncated
            and text.bounds is not None
        )
        download = self._matches(state, "login/update/download")
        cancel = self._matches(state, "login/update/cancel")
        if len(content) != 1 or not self._login_update_download_text_matches(
            content[0].text
        ):
            return False
        return bool(
            len(download) == 1
            and len(cancel) == 1
            and all(
                button.active_in_hierarchy
                and button.active_and_enabled
                and button.interactable
                # Older observer builds could not classify DialogPanel
                # raycast ownership and reported ``None``.  Current builds
                # positively prove the affirmative button is topmost with
                # ``True``.  Preserve the historical unknown-but-reviewed
                # shape while rejecting an explicitly obscured button.
                and button.raycast_top is not False
                and button.point is not None
                and button.bounds is not None
                and button.bounds.contains(button.point)
                for button in (download[0], cancel[0])
            )
        )

    def login_update_download_available(self) -> bool:
        return self._retry_transition_read(
            lambda: self._login_update_download_prompt_matches(self.read_state())
        )

    @staticmethod
    def _login_update_restart_text_matches(value: str) -> bool:
        plain = "".join(value.split())
        if (
            plain
            == "指挥官，当前客户端的游戏版本不是最新的，推荐您重新打开游戏进行更新"
        ):
            return True
        return (
            re.fullmatch(
                r"(?:热更新|资源更新|更新)(?:已)?完成[，,]?(?:需要|请|请点击确定)"
                r"(?:重启游戏|重新启动游戏)[。.]?",
                plain,
            )
            is not None
        )

    def _login_update_restart_prompt_target(self, state: OracleState) -> Optional[str]:
        """Return the sole reviewed explicit post-update restart control.

        Current CN 9.7.324 has no such button.  These two structures are the
        client's existing dialog families, so a future hot update is accepted
        only when its exact update/restart wording and sole affirmative label
        agree.  Any mixed or ambiguous surface remains closed.
        """

        ui_state = self.read_text_state()
        if (
            ui_state.generation < state.generation
            or ui_state.generation > state.generation + 2
        ):
            raise SemanticGateClosed("login update restart snapshots are not coherent")

        def active_text(suffix: str) -> Tuple[TextState, ...]:
            return tuple(
                text
                for text in ui_state.texts
                if text.path.endswith(suffix)
                and text.active_in_hierarchy
                and text.active_and_enabled
                and not text.truncated
                and text.bounds is not None
            )

        candidates = []
        variants = (
            (
                "login/update/restart-dialog",
                "DialogPanel/dialog/content/Text",
                "DialogPanel/dialog/action_button/Text",
                "login/update/cancel",
            ),
            (
                "login/update/restart-msgbox",
                "Msgbox(Clone)/window/msg_panel/content",
                "Msgbox(Clone)/window/button_container/custom_button_1(Clone)/pic",
                None,
            ),
        )
        for semantic_id, content_suffix, label_suffix, cancel_id in variants:
            content = active_text(content_suffix)
            label = active_text(label_suffix)
            button = self._matches(state, semantic_id)
            cancel = self._matches(state, cancel_id) if cancel_id is not None else ()
            if not content and not label and not button:
                continue
            # DialogPanel is shared by download confirmation and many other
            # login notices.  It is a restart candidate only when its exact
            # content says so; unrelated complete dialogs belong to their own
            # semantic branches and are not a malformed restart prompt.
            if content and not any(
                self._login_update_restart_text_matches(item.text) for item in content
            ):
                if any(
                    "".join(item.text.split()) in ("重启", "重启游戏", "重新启动")
                    for item in label
                ):
                    raise SemanticGateClosed(
                        "explicit login update restart prompt is incomplete"
                    )
                continue
            if (
                len(content) == 1
                and self._login_update_restart_text_matches(content[0].text)
                and len(label) == 1
                and "".join(label[0].text.split())
                in ("确定", "重启", "重启游戏", "重新启动")
                and len(button) == 1
                and not cancel
                and button[0].active_in_hierarchy
                and button[0].active_and_enabled
                and button[0].interactable
                and button[0].point is not None
                and button[0].bounds is not None
                and button[0].bounds.contains(button[0].point)
            ):
                candidates.append(semantic_id)
            else:
                raise SemanticGateClosed(
                    "explicit login update restart prompt is incomplete"
                )
        if len(candidates) > 1:
            raise SemanticGateClosed("login update restart prompt is ambiguous")
        return candidates[0] if candidates else None

    def login_update_restart_prompt_available(self) -> bool:
        return self._retry_transition_read(
            lambda: (
                self._login_update_restart_prompt_target(self.read_state()) is not None
            )
        )

    def click_login_update_restart_prompt(self) -> ActionReceipt:
        state = self.read_state()
        semantic_id = self._login_update_restart_prompt_target(state)
        if semantic_id is None:
            raise SemanticGateClosed("login update restart prompt is absent")
        receipt = self.click(semantic_id)
        self._login_update_seen = True
        return receipt

    @staticmethod
    def _login_update_download_text_matches(value: str) -> bool:
        """Match the reviewed CN maintenance-update download prompts.

        The client uses the same dialog for a byte-size update, a file-count
        update, the newer split-file summary, and the initial resource-size
        advisory.  Optional background-download copy is part of that exact
        prompt; unrelated manual APK and optional Live2D/full-client downloads
        remain excluded.
        """

        plain = "".join(value.split())
        background = r"(?:（本次更新可以后台下载）|\(本次更新可以后台下载\))?"
        size = r"[1-9][0-9]*(?:\.[0-9]+)?(?:B|KB|MB|GB)"
        count = r"[1-9][0-9]*"
        payload = (
            r"(?:"
            + size
            + r"的文件|"
            + count
            + r"(?:个)?文件(?:（其中已选文件"
            + count
            + r"，本地文件更新"
            + count
            + r"）)?|"
            + count
            + r"的文件)"
        )
        update_prompt = (
            background
            + r"本次更新(?:共)?需要下载"
            + payload
            + r"，是否继续更新？"
            + background
        )
        resource_advisory = (
            r"本次更新需要下载的资源大小约为" + size + r"（建议在WIFI环境下下载）"
        )
        return (
            re.fullmatch(
                r"(?:" + update_prompt + r"|" + resource_advisory + r")",
                plain,
            )
            is not None
        )

    @staticmethod
    def _login_update_status_text_matches(value: str) -> bool:
        """Recognize only client-owned update/check/download status text."""

        plain = "".join(value.split())
        patterns = (
            r"正在检查更新\.\.\.",
            r"正在获取最新版本\.\.\.",
            r"正在检查资源配置文件",
            r"正在下载资源配置文件:[^\r\n]{1,200}",
            r"校验中：[0-9]{1,3}%",
            r"正在下载[^\r\n]{1,200}\([0-9]+/[0-9]+\)",
            r"正在下载更新:进度[0-9]+(?:\.[0-9]+)?(?:B|KB|MB|GB)/"
            r"[0-9]+(?:\.[0-9]+)?(?:B|KB|MB|GB)总共[0-9]+个"
            r"已完成[0-9]+个失败[0-9]+个速度"
            r"[0-9]+(?:\.[0-9]+)?(?:B|KB|MB|GB)/S",
            # This is an automatic client transition, not a request for an
            # external restart.  Interrupting it with force-stop leaves the CN
            # client in its package-switch state and repeats this panel.
            r"更新完成，正在进入游戏\.\.\.",
        )
        return any(re.fullmatch(pattern, plain) is not None for pattern in patterns)

    def login_update_in_progress(self) -> bool:
        # UpdatePanel keeps its background "checking" status visible while
        # DialogPanel is waiting for the user's download confirmation.  The
        # prompt is the actionable state and must win; otherwise ALAS keeps
        # treating the screen as passive progress and never reaches its
        # LOGIN_GAME_UPDATE click branch.
        if self.login_update_download_available():
            return False
        state = self.read_text_state()
        progress = tuple(
            text
            for text in state.texts
            if text.path.endswith("UpdatePanel/progressInfo")
            and text.active_in_hierarchy
            and text.active_and_enabled
            and not text.truncated
            and text.bounds is not None
            and self._login_update_status_text_matches(text.text)
        )
        if len(progress) > 1:
            raise SemanticGateClosed("login update progress is ambiguous")
        visible = bool(progress)
        if visible:
            self._login_update_seen = True
        return visible

    def stale_login_update_in_progress(self) -> bool:
        """Recognize one passive UpdatePanel status after frame freshness expires.

        This is deliberately narrower than :meth:`login_update_in_progress`:
        it admits no frame, records no update transition, and exposes no
        actionable control. It exists only so the GameManager-owned cold-start
        wait can remain fail-closed while Unity has left a same-process,
        identity-valid UpdatePanel snapshot stale during update checking. The
        stale wait does not interpret status text: some pre-login Unity text is
        emitted lossily, and this method never converts the observation into an
        action or an update-completion latch.
        """

        if self._foreground_component() != self.fingerprint.component:
            return False
        ui_snapshot = self._request("GET /v1/ui\n")
        if not isinstance(ui_snapshot, dict):
            return False
        try:
            self._validate_identity(
                ui_snapshot,
                UI_SCHEMA,
                allow_stale=True,
            )
            if self._integer(ui_snapshot.get("age_ms"), "UI age_ms") <= (
                self.fingerprint.max_age_ms
            ):
                return False
            if (
                ui_snapshot.get("schema") != 1
                or ui_snapshot.get("text_truncated") is not False
                or self._integer(ui_snapshot.get("error_count"), "UI error_count")
                != 0
            ):
                return False
            raw_texts = ui_snapshot.get("texts")
            if (
                not isinstance(raw_texts, list)
                or self._integer(ui_snapshot.get("text_count"), "text_count")
                != len(raw_texts)
            ):
                return False
            if self._integer(ui_snapshot.get("method_mask"), "UI method_mask") & 0x6 == 0:
                return False
            progress = tuple(
                text
                for text in (self._parse_text(raw) for raw in raw_texts)
                if text.path.endswith("UpdatePanel/progressInfo")
                and text.active_in_hierarchy
                and text.active_and_enabled
                and not text.truncated
                and text.bounds is not None
                and bool(text.text.strip())
            )
        except (ObserverTransportError, SemanticGateClosed):
            return False
        return len(progress) == 1

    def login_update_restart_required(self) -> bool:
        """Recognize the inert black transition left by a completed CN update.

        The surface is actionable only after this oracle observed the typed
        download progress in the same process.  This prevents a normal startup
        animation from being mistaken for an update restart boundary.
        """

        if self._login_update_restart_consumed:
            return False
        state, ui_state = self._retirement_records()
        if (
            ui_state.generation < state.generation
            or ui_state.generation > state.generation + 2
        ):
            raise SemanticGateClosed("login update restart snapshots are not coherent")

        opening = tuple(
            button
            for button in state.buttons
            if button.name == "opening(Clone)"
            and button.path.endswith("OverlayCamera/Overlay/UIMain/opening(Clone)")
            and button.active_in_hierarchy
            and button.active_and_enabled
            and button.interactable
            and button.raycast_top is None
            and button.point is not None
            and button.bounds is not None
            and button.bounds.contains(button.point)
        )
        login_root = tuple(
            button
            for button in state.buttons
            if button.name == "LoginUI2(Clone)"
            and button.path.endswith("UICamera/Canvas/UIMain/LoginUI2(Clone)")
            and button.active_in_hierarchy
            and button.active_and_enabled
            and button.interactable
            and button.raycast_top is False
        )

        def active_text(suffix: str) -> Tuple[TextState, ...]:
            return tuple(
                text
                for text in ui_state.texts
                if text.path.endswith(suffix)
                and text.active_in_hierarchy
                and text.active_and_enabled
                and not text.truncated
                and text.bounds is not None
            )

        # Current client metadata contains no normal hot-update restart
        # button.  The only explicit restart surface is repair completion;
        # restart it through the owned ADB runtime rather than inventing a tap.
        repair_completion = tuple(
            text
            for text in ui_state.texts
            if (
                text.path.endswith("UpdatePanel/progressInfo")
                or text.path.endswith("DialogPanel/dialog/content/Text")
            )
            and text.active_in_hierarchy
            and text.active_and_enabled
            and not text.truncated
            and text.bounds is not None
            and "".join(text.text.split()) == "修复完毕，即将重启游戏"
        )
        if len(repair_completion) > 1:
            raise SemanticGateClosed("login repair restart state is ambiguous")
        if repair_completion:
            self._login_update_restart_consumed = True
            return True

        if not self._login_update_seen:
            return False

        change_server = active_text("LoginUI2(Clone)/adapt/current_server/Text")
        server_name = active_text("LoginUI2(Clone)/adapt/current_server/server_name")
        versions = active_text("LoginUI2(Clone)/adapt/version")
        progress = active_text("UpdatePanel/progressInfo")
        matched = bool(
            len(opening) == 1
            and len(login_root) == 1
            and len(change_server) == 1
            and change_server[0].text.strip() == "点击更换"
            and not server_name
            and len(versions) == 1
            and re.fullmatch(r"ver [0-9]+\.[0-9]+\.[0-9]+", versions[0].text.strip())
            and not progress
        )
        if matched:
            self._login_update_restart_consumed = True
        return matched
