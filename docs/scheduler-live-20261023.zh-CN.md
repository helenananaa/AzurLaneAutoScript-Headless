# 原 ALAS 扩展实机调度

本轮沿用本机 Redroid `gameplay` 的已有账号与 userdata，保持 ANGLE NULL。
只从 typed observer、动作回执和原任务结果收集证据，不使用游戏截图。
运行入口见[本机运行入口](local-runtime-entry.zh-CN.md)。本记录仍在随实机结果补充；
启用配置、一次任务完成和自然下一轮完成分别记录。

## 运行身份与范围

- 持久配置：`semantic_daily_continuity_20261023`，原 NextRun 保留，未重新用 seed 覆盖。
- 本轮发现并核对的设备为 `127.0.0.1:5558`；不是通用 serial。
- 镜像、observer 和 ALAS 基线沿用[连续性记录](redroid-continuity-20261023.zh-CN.md)。
- 开始资源为油 1290、金币 102545、钻石 3505。账号名称仅留在本地私有收据。
- 新增 Tactical、Dorm、Daily、Exercise、Freebies、Guild、PrivateQuarters、
  Meowfficer、Minigame、Gacha、Hard、Awaken，与原三项日常一起由 ALAS 原队列选取。
- Main 暂未启用：当前油量低于既有 3000 油保留设置。商店、宿舍家具、私室鲜花/蛋糕、
  指挥喵采购和公会物资交换关闭；不改凭据，不重置 userdata，不消费钻石。
- 普通任务按本轮预算执行：四项战术指派、一次轻型建造（不开快速完成）、一次觉醒、
  最多三次困难出击等。持续模式在原任务轮次开始时更新已有额度；它不是全天总消耗上限。

## 已完成的原任务与恢复

`native-r1.json` 使用同一持久配置，四条原命令均返回 true，总计 233.375 秒：

| 原命令 | 结果 | 原任务写回的 NextRun（本机时间） |
|---|---|---|
| Restart | 原 Restart/LoginHandler 冷启动，包含 `-force-gfx-st` | 2026-10-24 00:00:00 |
| Commission | 领取并派遣；动作账本 reward 1、start 4，批量领取不冒充单项数量 | 2026-10-23 20:27:42 |
| Research | 领取并开工；动作账本 reward 1、start 1 | 2026-10-24 01:24:55 |
| Reward | 生产资源与任务奖励，原任务完成 | 2026-10-23 22:26:21 |

扩展运行 `native-r2.json` 在 Tactical 首次输入前因 ADB 传输失败停止。宿主 ADB
37.0.0 日志记录 `fdevent.cpp:96` 的内部断言失败，随后服务重启但 TCP 设备列表为空。
容器仍运行。保留失败收据与 `adb-crash-r2.log` 后，仅重连核对过的该设备；未重启容器、
清空数据或杀掉其他 ADB 客户端。只读检查确认前台包/组件、PID 6757、state/UI 同代次
9532、帧龄 295 ms。此处证明连接恢复，不声称已经修复 ADB 本身。

`native-r3.json` 随后从相同持久配置继续，保留原计时，由 ALAS 自行选择 Tactical。
其中 Tactical 已返回 true（81.594 秒），账本记录四次指派和一次领取授权消耗，原
NextRun 为 2026-10-24 03:36:16。Exercise 返回 true（549.719 秒），原剩余次数
从 10 降到 0；十二次进入战斗包含两次原策略撤退重试，没有刷新对手。原 NextRun
为 2026-10-24 00:00:00。运行器随后在原任务边界响应停止文件，记录
`terminal=true / passed=true / stop_file_requested=true`，进程已退出。

停机后的只读复核通过：同一 PID 6757，state/UI generation 22438，帧龄 260 ms。
`native-r4.json` 于 19:46 从同一持久配置继续，未请求重复冷启动。运行包 manifest
的 27 项预算参数已与扩展实机参数一致，入口 `-Plan` 验证未启动游戏或改配置。
其余扩展任务和自然下一轮结果待运行完成后追加；不提前改写 NextRun 制造唤醒。

本聊天已建立每 15 分钟的后台巡检，正常等待不通知。完成十五项首轮执行/明确局部
边界以及三项核心日常的自然下一轮后正常停止；本轮截止时间为本机
2026-10-24 02:00，届时仍未完成的项目保留为未验证。此前 AVD 巡检继续暂停。

## 停止入口与验证

运行器新增 `--stop-file`，Windows 入口提供 `-StopFile`。文件出现时只设置原 ALAS
的 `stop_event`；任务边界/原等待循环负责退出，不增加第二个调度器。
原任务尚未结束时允许其走到原退出边界。请求文件保留，收据记录请求路径与是否存在。
有界入口新增 `-ContinueAfterFailure`，仅转发已有运行器选项。

停止事件、原正常退出、参数透传、收据、额度和原调度策略的最终相关集合 **85 passed**。
真实停止与同配置重入已按上节完成。未更改 233 成员 ALAS 补丁系列、
support ledger 或支持等级；本轮成功不能直接推广成所有账号/配置支持。

原始运行收据、stdout/stderr、配置前后快照和私有 typed 状态保留在
`artifacts/scheduler-live-20261023/`。此前有界连续性记录保持原样。
