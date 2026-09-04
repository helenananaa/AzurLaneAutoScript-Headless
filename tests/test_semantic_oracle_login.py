"""Login regression cases for the oracle."""

import unittest
from alas_headless.semantic_oracle import SemanticGateClosed
from tests.semantic_support.observer_fixtures import (
    FakeBackend,
    make_button,
    make_buttons,
    make_oracle,
    make_text,
    make_ui,
)
from tests.semantic_support.oracle_cases import SemanticOracleTestsSupport


class SemanticOracleTests(SemanticOracleTestsSupport, unittest.TestCase):
    def test_login_data_expired_confirm_requires_exact_single_button_prompt(self):
        popup = "root/Overlay/UIMain/Msgbox(Clone)/window/"
        backend = FakeBackend(
            [
                make_button(
                    "custom_button_1(Clone)",
                    popup + "button_container/custom_button_1(Clone)",
                )
            ]
        )
        backend.ui = make_ui(
            [
                make_text("登录数据失效", popup + "msg_panel/content"),
                make_text(
                    "确 定",
                    popup + "button_container/custom_button_1(Clone)/pic",
                ),
            ]
        )
        oracle = make_oracle(backend)

        self.assertTrue(oracle.enabled("overlay/login-data-expired/confirm"))
        receipt = oracle.click("overlay/login-data-expired/confirm")
        self.assertEqual(receipt.semantic_id, "overlay/login-data-expired/confirm")

        backend.ui["texts"][0]["text"] = "您在别处登录"
        self.assertTrue(oracle.enabled("overlay/login-data-expired/confirm"))

        backend.ui["texts"][0]["text"] = "是否购买资源？"
        self.assertFalse(oracle.enabled("overlay/login-data-expired/confirm"))

    def test_server_maintenance_requires_exact_single_button_prompt(self):
        popup = "root/Overlay/UIMain/Msgbox(Clone)/window/"
        backend = FakeBackend(
            [
                make_button(
                    "custom_button_1(Clone)",
                    popup + "button_container/custom_button_1(Clone)",
                )
            ]
        )
        backend.ui = make_ui(
            [
                make_text("服务器维护", popup + "msg_panel/content"),
                make_text(
                    "确 定",
                    popup + "button_container/custom_button_1(Clone)/pic",
                ),
            ]
        )
        oracle = make_oracle(backend)

        self.assertTrue(oracle.server_maintenance_visible())
        self.assertEqual(backend.taps, [])

        backend.ui["texts"][0]["text"] = "是否购买资源？"
        self.assertFalse(oracle.server_maintenance_visible())

    def test_login_update_download_requires_exact_dialog(self):
        dialog = "root/Overlay/UIMain/DialogPanel/dialog/"
        backend = FakeBackend(
            [
                make_button("exit_button", dialog + "exit_button", raycast_top=None),
                make_button(
                    "action_button", dialog + "action_button", raycast_top=None
                ),
            ]
        )
        backend.ui = make_ui(
            [
                make_text(
                    "本次更新需要下载796.8MB的文件，是否继续更新？",
                    dialog + "content/Text",
                )
            ]
        )
        oracle = make_oracle(backend)

        self.assertTrue(oracle.enabled("login/update/download"))
        receipt = oracle.click("login/update/download")
        self.assertEqual(receipt.semantic_id, "login/update/download")
        self.assertEqual(backend.taps, [(640, 360)])
        self.assertTrue(oracle._login_update_seen)

        backend.ui["texts"][0]["text"] = "是否购买资源？"
        self.assertFalse(oracle.enabled("login/update/download"))

    def test_login_update_download_accepts_reviewed_maintenance_variants(self):
        dialog = "root/Overlay/UIMain/DialogPanel/dialog/"
        backend = FakeBackend(
            [
                make_button("exit_button", dialog + "exit_button", raycast_top=None),
                make_button(
                    "action_button", dialog + "action_button", raycast_top=None
                ),
            ]
        )
        backend.ui = make_ui([make_text("placeholder", dialog + "content/Text")])
        oracle = make_oracle(backend)

        accepted = (
            "本次更新共需要下载982个文件，是否继续更新？",
            "本次更新共需要下载982的文件，是否继续更新？",
            "本次更新需要下载982文件（其中已选文件12，"
            "本地文件更新970），是否继续更新？",
            "本次更新需要下载796.8MB的文件，是否继续更新？\n（本次更新可以后台下载）",
            "本次更新需要下载的资源大小约为796.8MB（建议在WIFI环境下下载）",
        )
        for content in accepted:
            with self.subTest(content=content):
                backend.ui["texts"][0]["text"] = content
                self.assertTrue(oracle.login_update_download_available())

        rejected = (
            "检测到版本更新，需要手动下载更新包，是否前往下载？",
            "是否下载Live2D资源，资源大小约为796.8MB",
            "下载完整资源 (796.8MB)",
        )
        for content in rejected:
            with self.subTest(content=content):
                backend.ui["texts"][0]["text"] = content
                self.assertFalse(oracle.login_update_download_available())

    def test_login_update_progress_uses_exact_typed_status(self):
        backend = FakeBackend([])
        backend.ui = make_ui(
            [
                make_text(
                    "正在下载更新:进度103.2MB/796.8MB  总共982个  "
                    "已完成426个  失败0个  速度3.63MB/S",
                    "root/Overlay/UIMain/UpdatePanel/progressInfo",
                )
            ]
        )
        oracle = make_oracle(backend)

        self.assertTrue(oracle.login_update_in_progress())
        backend.ui["texts"][0]["text"] = "正在下载未知文件"
        self.assertFalse(oracle.login_update_in_progress())

    def test_stale_login_update_panel_is_passive_and_path_exact(self):
        backend = FakeBackend([])
        backend.ui = make_ui(
            [
                make_text(
                    "正在检查更新...",
                    "root/Overlay/UIMain/UpdatePanel/progressInfo",
                )
            ],
            age_ms=3_000,
        )
        oracle = make_oracle(backend)

        self.assertTrue(oracle.stale_login_update_in_progress())
        self.assertEqual(backend.taps, [])
        self.assertFalse(oracle._login_update_seen)

        backend.ui["texts"][0]["text"] = "decode-lost-status"
        self.assertTrue(oracle.stale_login_update_in_progress())
        backend.ui["texts"][0]["text"] = ""
        self.assertFalse(oracle.stale_login_update_in_progress())
        backend.ui["texts"][0]["text"] = "正在检查更新..."
        backend.ui["age_ms"] = 20
        self.assertFalse(oracle.stale_login_update_in_progress())

    def test_login_update_download_prompt_wins_over_background_check_status(self):
        dialog = "root/Overlay/UIMain/DialogPanel/dialog/"
        backend = FakeBackend(
            [
                make_button("exit_button", dialog + "exit_button", raycast_top=None),
                make_button(
                    "action_button", dialog + "action_button", raycast_top=None
                ),
            ]
        )
        backend.ui = make_ui(
            [
                make_text(
                    "本次更新需要下载115.5MB的文件，是否继续更新？",
                    dialog + "content/Text",
                ),
                make_text(
                    "正在检查更新...",
                    "root/Overlay/UIMain/UpdatePanel/progressInfo",
                ),
            ]
        )
        oracle = make_oracle(backend)

        self.assertTrue(oracle.login_update_download_available())
        self.assertFalse(oracle.login_update_restart_prompt_available())
        self.assertFalse(oracle.login_update_in_progress())

    def test_login_update_lifecycle_accepts_exact_check_and_completion_states(self):
        backend = FakeBackend([])
        backend.ui = make_ui(
            [
                make_text(
                    "正在检查更新...", "root/Overlay/UIMain/UpdatePanel/progressInfo"
                )
            ]
        )
        oracle = make_oracle(backend)

        accepted = (
            "正在检查更新...",
            "正在获取最新版本...",
            "正在检查资源配置文件",
            "正在下载资源配置文件:hashes.csv",
            "校验中：100%",
            "正在下载hashes.csv(12/982)",
        )
        for content in accepted:
            with self.subTest(content=content):
                backend.ui["texts"][0]["text"] = content
                self.assertTrue(oracle.login_update_in_progress())

        backend.ui["texts"][0]["text"] = "正在进入游戏..."
        self.assertFalse(oracle.login_update_in_progress())

    def test_update_completion_waits_for_client_transition_without_cold_restart(self):
        backend = FakeBackend([])
        backend.ui = make_ui(
            [
                make_text(
                    "更新完成，正在进入游戏...",
                    "root/Overlay/UIMain/UpdatePanel/progressInfo",
                )
            ]
        )
        oracle = make_oracle(backend)

        self.assertTrue(oracle.login_update_in_progress())
        self.assertFalse(oracle.login_update_restart_required())
        self.assertEqual(backend.taps, [])

    def test_explicit_update_restart_msgbox_clicks_only_exact_prompt(self):
        popup = "root/Overlay/UIMain/Msgbox(Clone)/window/"
        backend = FakeBackend(
            [
                make_button(
                    "custom_button_1(Clone)",
                    popup + "button_container/custom_button_1(Clone)",
                    raycast_top=None,
                )
            ]
        )
        backend.ui = make_ui(
            [
                make_text("更新完成，请重启游戏", popup + "msg_panel/content"),
                make_text(
                    "重启游戏",
                    popup + "button_container/custom_button_1(Clone)/pic",
                ),
            ]
        )
        oracle = make_oracle(backend)

        self.assertTrue(oracle.login_update_restart_prompt_available())
        receipt = oracle.click_login_update_restart_prompt()
        self.assertEqual(receipt.semantic_id, "login/update/restart-msgbox")
        self.assertEqual(backend.taps, [(640, 360)])

        backend.ui["texts"][0]["text"] = "是否购买资源？"
        with self.assertRaisesRegex(SemanticGateClosed, "incomplete"):
            oracle.login_update_restart_prompt_available()

    def test_explicit_update_restart_dialog_rejects_cancelable_surface(self):
        dialog = "root/Overlay/UIMain/DialogPanel/dialog/"
        backend = FakeBackend(
            [
                make_button(
                    "action_button", dialog + "action_button", raycast_top=None
                ),
                make_button("exit_button", dialog + "exit_button", raycast_top=None),
            ]
        )
        backend.ui = make_ui(
            [
                make_text("热更新完成，需要重启游戏", dialog + "content/Text"),
                make_text("确定", dialog + "action_button/Text"),
            ]
        )
        oracle = make_oracle(backend)

        with self.assertRaisesRegex(SemanticGateClosed, "incomplete"):
            oracle.login_update_restart_prompt_available()

    def test_completed_login_update_requires_one_exact_cold_restart(self):
        backend = FakeBackend([])
        backend.ui = make_ui(
            [
                make_text(
                    "正在下载更新:进度796.8MB/796.8MB  总共982个  "
                    "已完成982个  失败0个  速度3.63MB/S",
                    "root/Overlay/UIMain/UpdatePanel/progressInfo",
                )
            ]
        )
        oracle = make_oracle(backend)
        self.assertTrue(oracle.login_update_in_progress())

        backend.buttons = make_buttons(
            [
                make_button(
                    "opening(Clone)",
                    "root/OverlayCamera/Overlay/UIMain/opening(Clone)",
                    bounds={"left": 0, "top": 0, "right": 1280, "bottom": 720},
                    raycast_top=None,
                ),
                make_button(
                    "LoginUI2(Clone)",
                    "root/UICamera/Canvas/UIMain/LoginUI2(Clone)",
                    bounds={"left": 0, "top": 0, "right": 1280, "bottom": 720},
                    raycast_top=False,
                ),
            ]
        )
        backend.ui = make_ui(
            [
                make_text(
                    "点击更换",
                    "root/UICamera/Canvas/UIMain/LoginUI2(Clone)/adapt/"
                    "current_server/Text",
                ),
                make_text(
                    "ver 9.7.324",
                    "root/UICamera/Canvas/UIMain/LoginUI2(Clone)/adapt/version",
                ),
            ]
        )

        self.assertTrue(oracle.login_update_restart_required())
        self.assertFalse(oracle.login_update_restart_required())
