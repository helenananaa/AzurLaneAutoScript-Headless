# Restart 与 Scheduler 实机验证报告

验证时间：2026-08-16 14:17:07 +08:00
设备：`emulator-5580`（x86_64）
客户端：`com.bilibili.azurlane` 9.7.10
观测驱动：`be80ce591a481c12d60c50d6040d40c035b40a2b`

本报告限定 ALAS `Restart` 任务和它唯一继承的 `Scheduler` 配置组；
不把 `Alas.Emulator.AdbRestart`、模拟器发现或其他任务的业务流程归入本次结论。
所有运行使用临时配置 `codex_restart_live_<uuid>`，完成后已删除。

## 修复的实际路径

原调度循环会在调用 `Restart` 前先取得首帧。当游戏已停止时，这使重启任务无法取得
启动游戏的机会。补丁仅让 `Restart` 传入 `skip_first_screenshot=True`；其它任务保持原始
首帧行为。

`LoginHandler.app_restart()` 在语义设备存在时改为调用其
`restart_game_for_manager()`，由该会话以 `-force-gfx-st` 启动客户端；普通设备仍使用
上游的 `app_stop()` 和 `app_start()`。随后仍复用上游登录和
`task_delay(server_update=True)` 路径。

## Scheduler 配置覆盖

验证器将固定上游的原始 `AzurLaneConfig` 用在 50 个实际声明的 Scheduler 实例上，覆盖
15 个 `(Enable, SuccessInterval, FailureInterval, ServerUpdate)` 等价类。每个实例均验证
原始队列使用 `Command` 标识目标任务，并通过原始持久化路径写入 success、failure 与
server-update 的 `NextRun`。`Main.Enable=false` 被实证不会进入队列；`Restart.Enable`
是上游 `state` 字段，只允许 true，因此没有捏造不存在的 false 分支。

首次服务启动也直接执行原调度循环：当 `Restart` 预置为 due 时，它精确调用
`task_delay(server_update=True)`，不执行一次不必要的应用重启。

## 设备执行收据

| 用例 | 实际结果 |
|---|---|
| 预置 Restart 首次启动 | 精确 server-update 延迟；没有执行 app restart；`NextRun=2026-08-17 00:00:00` |
| 禁用包后的调度 Restart | `restart` 命令被调度，进程以退出码 1 结束，前后均无游戏 PID，零 observer forward 遗留 |
| 重新启用后的冷恢复 | 无 PID -> PID `25778`，约 35.0 秒，登录到主界面，延迟到 `2026-08-17 00:00:00` |
| 运行中 Restart | PID `25778` -> `27548`，约 32.781 秒，登录到主界面，延迟到 `2026-08-17 00:00:00` |

最终状态为包已启用、顶层 Activity 为
`com.bilibili.azurlane/com.manjuu.azurlane.MainActivity`、PID `27548`、`Restart.NextRun`
为次日服务器刷新时刻，且没有残留的 observer forward。

完整机器可读收据见
[`integration/alas/restart-live-validation-receipt.json`](../integration/alas/restart-live-validation-receipt.json)，
可重复执行的驱动为
[`scripts/python/run_alas_restart_live_validation.py`](../scripts/python/run_alas_restart_live_validation.py)。
规范合并补丁还在固定 `81ccf63` 上以一次性临时 worktree 应用并编译，结果见
[`integration/alas/restart-patch-tree-verification/result.json`](../integration/alas/restart-patch-tree-verification/result.json)。

## 失败信号说明

禁用包时，ALAS 日志已经记录根因 `ObserverTransportError`（ADB 命令因包被禁用失败），
任务没有被当作成功或静默跳过。当前工作树缺少可选 `onepush` 包，上游错误通知在此后又抛出
`ModuleNotFoundError: No module named 'onepush'`，因此收据的进程级 failure 字段记录的是
后者。这个通知掩蔽问题属于 `Alas.Error/OnePushConfig` 的未完成范围，不能倒推为
Restart 成功；Restart 的失败退出、无残留和后续冷恢复均已经实际验证。
