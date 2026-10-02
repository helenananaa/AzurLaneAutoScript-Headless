# Research 自然下一轮与等待项目入队（2026-09-27）

本轮在原本机 AVD `alas_game_api32_x64`、游戏 9.7.394、ANGLE NULL 上继续，绑定 `emulator-5554`。午后 ADB 曾把设备标为 offline，传输重连后旧游戏语义帧停止；两次游戏冷启动未及时恢复主线程导出。仅重启本任务的 AVD，保留 userdata 和原启动参数，再用 `-force-gfx-st` 冷启动。新 PID 1931 的语义代次由 1 推进到新鲜的 73 及以后。启动期公告由原 ALAS 登录处理器关闭；导航脚本现在也在“仅公告遮挡”时调用该处理器。没有使用游戏截图或坐标回退。

## 自然条件与第一次运行

[只读队列与主页往返](../artifacts/research-late-queue-observation-20260927-r5.json)通过：`G-412-MI` 自然完成且可领取，`C-185-MI` 正在运行，另三格等待。原 `RewardResearch.run()` 沿既有 `UseCoin=always_use`、`UseCube=do_not_use`、`UsePart=do_not_use`、`AllowDelay=false`、过滤 `S9-G > S9-D` 执行；没有重置或强制刷新。

[第一次原任务收据](../artifacts/research-natural-next-round-20260927-r1.json)保留 `passed=false`：它已经通过 `research.reward` 领取一个自然完成项目，随后原 ALAS 选择等待中的第六项目入队。详情页显示 `D-337-MI` 的 `is_running=true`、`can_queue=true`，但适配层旧门禁只接受卡片状态 `running`，对 `waiting` 拒绝 `RESEARCH_QUEUE_ADD`。因此本次没有科研开工输入；临时配置已删除。拒绝发生在入队输入前，不把这份收据记成任务完成。

## 最窄修复与续跑

等待中的第六项目已开工，原 ALAS 的 `receive_6th_research()` 明确会选择 `waiting` 或 `running` 卡片走入队。现在仅在这两个卡片状态之一、详情仍证明运行中且可入队、有 `research.start` 预算时，允许原入队确认。详情不运行、预算为零或目标不可入队仍拒绝；不重启项目，也不绕开入队确认。聚焦测试覆盖固定 `running` 与新 `waiting` 路径及缺失运行态/预算的拒绝。

[续跑收据](../artifacts/research-natural-next-round-20260927-r2.json)为 `passed=true`、`task_completed=true`，原任务先确认该等待项目入队，再按自身筛选启动一个价格 **1500 物资**的项目，返回并写出下一轮时间 **2026-09-27 19:49:04**。本次两条 `research.start` 授权分别对应已有项目的入队确认和新项目的物资确认；没有把前者说成再次开工。临时配置已删除。任务末尾附加的项目卡片读取报 `research project Buttons are incomplete`，并未改变原任务返回结果；[独立只读复核](../artifacts/research-natural-next-round-post-20260927-r3.json)确认五格队列为一项运行、四项等待、无可领奖项目，并返回主页。中途一次回主页探测失败的原始收据保留，[单独回主页恢复](../artifacts/research-natural-next-round-home-20260927-r2.json)通过。

首次领奖与后续成功入队/开工分属两次原任务运行；独立队列复核又是第三次运行。它们证明自然跨轮条件下能恢复并继续工作，尚不证明无人值守唤醒、双资源实际确认、重置或一次进程覆盖整个跨轮。Research 仍为 `L`。

## 验证

Research、语义 oracle、预算、配置回放及登录任务隔离相关 **94 项测试通过**；Research 配置回放、120 成员补丁系列哈希检查、固定上游补丁树计划及支持矩阵校验通过。未改 ALAS 补丁成员、观察器 APK 或结构化支持等级。
