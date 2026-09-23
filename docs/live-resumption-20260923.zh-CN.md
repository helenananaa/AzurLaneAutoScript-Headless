# 联网恢复后的 ALAS 实机续推（2026-09-23）

范围：原 AVD `alas_game_api32_x64`，设备 `emulator-5554`，包 `com.bilibili.azurlane`，ANGLE NULL 与原 userdata 保留。联网修复和 357.2 MB 下载完成的因果与证据见[网络验证记录](resource-download-network-validation-20260923.zh-CN.md)。本轮确认目标 MainActivity 前台、PID 与新鲜一致的语义帧后，交由原 ALAS 状态机执行登录和任务导航。没有使用游戏截图、坐标回退或购买。

## 现场结果

- 原 ALAS `LoginHandler` 使用映射后的 `login/enter` 进入游戏；月签到和普通奖励弹层由原流程处理。随后出现公告遮挡，首次 Research 导航在公告下点击技术入口被阻止。再次运行原登录处理器清除公告，主页语义身份通过。
- Research 只读导航通过。原 ALAS 进入研究页、读取五张候选卡与队列、退出并返回主页。队列五项均为 `finished`，`reward_claimable=true`；本轮没有领取研究奖励、刷新或开启项目。第一次导航的公告阻挡失败收据保留，第二次运行才通过。
- PrivateQuarters 原任务进入新泽西房间，执行三次 `private-quarters/interact`，经 `ik`、`watch`、`base` 三层返回，原 ALAS 读到剩余次数 0 并调度到次日。第一次执行的最终通用 `ui_ensure(page_main)` 在回程过渡时访问未映射 `FLEET_CHECK` 而失败，尽管后续语义帧已显示主页。
- 修复仅作用于一次经过审阅的 `private-quarters/home` 输入之后：给原 ALAS 的**被动页面扫描**一个 30 秒过渡窗口，未知输入仍拒绝，超时后未知页面探针继续报未映射。次轮 0 次互动的独立回程验证通过，主页后置条件成立。它证明回程修复，但不能替代三次互动与回程在同一次无中断执行的证据。

## 资格与后续条件

PrivateQuarters 维持 `P`，Research 的本轮结果是导航与读取，均不提升完整任务支持。次日日精力恢复后，可用同一原生任务再跑三次互动与回程的连续资格；好感升级弹窗必须自然出现后再验证其关闭。Research 可领取奖励与当前卡片为下一次原生任务的真实条件，领取和开工前仍须核对资源策略及实际弹窗。Shipyard FATE、Daily 批量流程、META 奖励未在本轮验证。

[精简收据](../integration/alas/live-resumption-20260923/receipt.json)记录输入语义 ID、结果与三份完整本地 JSON 的 SHA-256。完整运行产物在 `artifacts/research-navigation-20260923-after-network.json`、`artifacts/research-navigation-20260923-r2.json`、`artifacts/private-quarters-20260923-after-network.json` 和 `artifacts/private-quarters-20260923-r2.json`，前两类首次失败产物保留以区分公告遮挡和回程缺口。
