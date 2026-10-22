# 导航准备阶段复用语义帧（2026-09-23）

## 变更

- ALAS Benchmark 的主页/设置切换与返回主页方法，在 `refresh_frame()` 后使用该帧进行页面判断和点击准备。点击完成后的 `wait_for()` 使用 live oracle，并要求代次大于动作回执。
- Session 的普通奖励弹窗关闭、演习页返回复用准备帧；`CLICK_SAFE_AREA` 前置的奖励/结果页面判断也使用该帧。专用战斗动作处理与结果过渡语义保留。
- 输入仍通过原有唯一目标、blocker、前台实时检查、帧有效期及输入后失效机制。没有跨动作复用帧，没有修改 0.5 秒轮询间隔。

新增 patch-series 成员 `0710-navigation-frame-reuse.patch`，共 118 个成员。combined SHA256 为 `3b155bcda598338f9065b41f41f323b690c47417878c1dac3bb038c4cc737352`；manifest SHA256 为 `27b81bec6348bcf44332903e6f813bd66419b7bf378672b394ec78a9a5a754f0`。支持账本只更新 patch 身份，无支持等级晋级，历史证据保持原样。

## 验证

定向测试 154 passed。新增奖励关闭/演习返回场景验证正常动作只采集一次 state/UI；前台变化、过期帧及重复目标都拒绝输入。已有帧和任务隔离测试继续通过。

最终相关回归 1273 passed（33.43 秒），JUnit 回执为 `artifacts/navigation-frame-reuse-tests-20260923.xml`。`git diff --check` 通过。

以下验证通过：

- patch-series 合成一致性、support-matrix 一致性；
- 在干净 pinned upstream 上应用完整补丁并编译，回执位于 `artifacts/navigation-frame-reuse-patch-verification-20260923/`；
- configuration attack matrix，使用本轮更新后的 `artifacts/campaign-preparation/upstream`。

## 真实导航结果

同一 `emulator-5554`、`com.bilibili.azurlane`、PID 18011、driver `506b76f698b5089aaa29c4e7908b48edb8532a44`。执行 patched ALAS 原有 Benchmark 的三组主页/设置往返；准备和恢复单列。六次样本均完成，最终恢复商店，共 8 次 typed tap，临时配置已删除。无购买或战斗。

| 指标 | 上轮前台查询合并后 | 本轮帧复用后 |
| --- | --- | --- |
| 每次导航 state 请求数 | 6–7 | 3–4 |
| 每次导航前台查询数 | 6–7 | 4–5 |
| 单次导航耗时中位数 | 1.284 秒 | 0.909 秒 |
| 六次导航累计时间 | 8.378 秒 | 6.057 秒 |

本轮回执 `artifacts/navigation-timing-frame-reuse-20260923.json` 为 `passed:true`、`restored:true`。对照为 `artifacts/navigation-timing-foreground-coalesced-20260923.json`。耗时是小样本前后观察，受 ADB、游戏调度和轮询影响；不作全任务统一提速承诺。奖励关闭与演习返回本轮只有离线验证，未另外执行真实任务。
