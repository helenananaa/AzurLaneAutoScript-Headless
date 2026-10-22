# 登录资源更新重试边界（2026-09-23）

本轮启动本地 `alas_game_api32_x64`，发现 `emulator-5554`，冷启动游戏时传入 Unity `-force-gfx-st`。观察器修订为 `506b76f698b5089aaa29c4e7908b48edb8532a44`；游戏包和前台均为 `com.bilibili.azurlane/com.manjuu.azurlane.MainActivity`。原 ALAS 登录流程遇到 357.2 MB 更新，随后出现类型化文案“部分文件下载失败，是否重试？”，原有下载确认映射不接受该文案。

适配层现仅在该精确文案、唯一肯定和取消按钮、肯定按钮顶层命中、同一新鲜帧的条件下，把原 `LOGIN_GAME_UPDATE` 映射到一次重试。重试标记在同一游戏会话的连续 ALAS 截图帧间保留；其他弹窗、遮挡和重复重试仍关闭。原 ALAS 登录状态机及输入端口不变。没有添加截图、旧坐标或通用确认后备。

定向测试 `tests/test_semantic_oracle_login.py`、`tests/test_alas_adapter_login.py`、`tests/test_adapter_session_runtime_handle.py` 共 79 项通过，覆盖正确文案、错误文案、遮挡以及跨帧重试标记。未改 ALAS 补丁系列和支持台账。
补丁系列原件校验通过，仍为 116 成员及原组合哈希；支持矩阵与固定上游配置源校验通过。原登录回放验证器要求临时补丁树只有组合补丁涉及的文件，本地留存运行树另含活动目录和集成文件，因此在文件表面检查处拒绝该树；本轮未用其冒充干净补丁树的回放结果。

现场调用原 `LoginHandler.appear_then_click(LOGIN_GAME_UPDATE)` 返回 `True`，提交一次重试。游戏随即从 line3 切到 line1 CDN，但两次均报告 `allTaskEnd: ERROR neterror`；[后置 typed 状态](../integration/alas/login-update-retry-20260923/post-retry-state.json)仍是同一失败弹窗，[游戏日志节选](../integration/alas/login-update-retry-20260923/game-update-tail.log)保留 CDN 和错误。当前 WLAN DNS 对 CDN 域名可解析，主机 HTTPS 和模拟器 TCP 443 可连接，模拟器约有 16 GB 可用；这些检查不能证明游戏下载的具体失败原因。未再次点击、修改系统 DNS、清空 userdata 或重装游戏。

登录更新未完成，所以本轮未进入 Research、Daily、META 或 PrivateQuarters 实机验证。此前 PrivateQuarters 的旧 `ROOM_BACK` 循环误报已有 0690 补丁和离线回放，仍缺更新完成后的一次连续原任务互动、退出和调度收据。面板支持等级不变。重进时先确认更新实际完成、主页及账号身份，再按任务板选择当时具备自然条件的任务。
另核对了旧好感升级弹窗收据：`LevelUpWindow/bg` 虽出现在 Button 列表，保存的帧没有顶层射线命中结论；不能据此增加关闭输入映射，也不能用旧坐标尝试。
结束时游戏安装版本仍为 `9.7.10`；已正常关闭本轮启动的模拟器，保留原 AVD 与 userdata。
