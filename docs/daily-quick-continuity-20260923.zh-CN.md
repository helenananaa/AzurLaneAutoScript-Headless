# Daily 批量快速连续性（2026-09-23）

原 AVD `alas_game_api32_x64`、`emulator-5554`、`com.bilibili.azurlane`。游戏前台、PID、新鲜语义帧和 ALAS 配置于输入前核对；游戏继续使用 ANGLE NULL。测试配置仅启用一个 Daily 类型的第一档批量快速，每次最多一次挑战操作，不允许转入普通战斗。

## 实机观察

原 ALAS 导航至 Daily 时，战术研修、强袭作战、护航、进阶分别为 3 次，兵装训练与破交作战为 0。战术研修第一次运行在批量快速后从 3 变 0，但原循环继续重复选第一档，因此停止输入；该运行的收据在中断前只写入意图，不能声称完整领奖。中断留下的当次临时配置已按精确文件名清理。

第二次原 ALAS 强袭作战产生 `daily/execute/fierce_assault/stage/1/quick/all` 操作收据，剩余次数从 3 变 0。旧退出判断在奖励弹层到达前认为快速挑战完成，随后最终返回被奖励弹层阻挡并触发 `GameStuckError`。任务结果为失败，未记作连续通过。之后按唯一审阅的 `reward/award-info/close` 输入关闭弹层，再由原 ALAS 导航返回主页。

第三次只启用护航任务；原任务正常返回，未发挑战操作。逐卡语义巡检证明护航和进阶虽然分别仍显示 3 次，但卡片 `active=false`，所以不继续尝试。战术研修与强袭作战均已为 0 次，当日没有剩余可用的同类挑战供修复后复验。

## 代码与资格

新增有序补丁 `0700-daily-quick-completion.patch`：原 `Daily.daily_enter()` 在语义模式下从既有循环读取完成结果。适配端只在**本会话该类型的 `quick/all` 收据、后续代际、次数 0、关联奖励弹层已关闭且当前无奖励遮挡**同时成立时报告完成；等待奖励时，被动 `DAILY_ENTER_CHECK` 不再重复选已耗尽的关卡。输入仍限定在审阅的 Daily 和奖励端口，没有增加坐标或截图回退。中断运行的验证入口也会保存异常收据并删除自己的临时配置。

第 117 个补丁成员、合并补丁及结构化支持台账中的哈希已同步。补丁树从固定上游成功应用并编译；定向测试覆盖未发操作、未耗尽、代际未前进、奖励未关闭和满足全部条件的情况。当前修复只有离线及补丁树验证，**没有修复后的单进程完整实机通过证据**，Daily 保持 `L`。下一次对应挑战开放且次数恢复时，重新运行原 Daily 一进程流程，核对快速操作、奖励关闭、返回及调度。

[精简收据](../integration/alas/daily-continuity-20260923/receipt.json)列出现场状态和完整本地产物 SHA-256。完整产物保留在 `artifacts/daily-condition-20260923.json`、`artifacts/daily-quick-20260923-tactical.json`、`artifacts/daily-quick-20260923-fierce-r1.json`、`artifacts/daily-quick-20260923-escort-r1.json` 与 `artifacts/daily-carousel-20260923.json`。
