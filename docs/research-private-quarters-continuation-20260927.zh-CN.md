# Research 跨轮与 PrivateQuarters 现场续推（2026-09-27）

本轮使用原 `alas_game_api32_x64`、游戏 9.7.394、ANGLE NULL 和携带 `-force-gfx-st` 的冷启动。发现并绑定 `emulator-5554`；Research 阶段 PID 1969，PrivateQuarters 观察器更新后 PID 13581，语义代次持续更新。没有截图、坐标回退、购买或高级货币消费。Research 保持 `L`，PrivateQuarters 保持 `P`。

## Research：有条件且已完成一次跨轮

只读检查时五格队列的 `D-732-MI`、`D-381-MI`、`Q-368-MI`、两项 `G-412-MI` 均为已完成、可领取；原科研页有五张可识别卡片。首次只读返回揭示：原 ALAS 在 `research/page/back` 后、新菜单挂载前扫描无关的 `GET_MISSION`、`GET_ITEMS_1`、`MONTHLY_PASS_NOTICE` 和 `MAP_PREPARATION`。适配层原先将该短暂空档误作无任务归属。现在只在实际 `research/page/back` 输入回执后的八秒内，把无关的**被动观察**判为不存在；新遮挡物仍拒绝，未知输入没有放行。完整原导航→队列读数→退出→主页的 [修复后收据](../artifacts/feasibility-research-navigation-20260927-r9.json) 为通过。

随后沿原 `RewardResearch.run()` 使用临时配置执行自然补队列，没有强制刷新或重写选择器。原始[任务收据](../artifacts/research-native-cross-round-20260927-r1.json)记录 `task_completed=true`，一次 `research.reward`、六次 `research.start`，其中前两项为零资源启动，后四项的物资确认价格合计 **17000**；启动授权 `6→0`、领奖授权 `2→1`，原任务返回并写出下一轮时间 **2026-09-27 11:49:01**。临时配置已删除；该时间是原任务调度写入，不证明后台无人值守唤醒。

原始收据仍保留 `passed=false`：旧验收脚本错误要求**第一项**启动就消耗资源，实际原选择器先启动了两项零资源项目。脚本现改为在整次原生补队列运行中要求**至少一项**实际消耗资源，全部免费时仍拒绝。未重新消耗队列；[独立修正评估](../artifacts/research-native-cross-round-20260927-assessment.json)以原始收据及后续导航的 SHA-256 绑定结果。任务后只读[队列与回主页收据](../artifacts/research-post-task-navigation-20260927.json)通过：`G-412-MI` 运行，其余四格等待，不可领奖，最终主页。原任务与独立回主页是两次运行，不合并为同进程证据。

## PrivateQuarters：原任务三次互动与回程通过

原任务先在零互动配置下读到 **3/3** 并正常回主页。[互动尝试](../artifacts/private-quarters-native-interaction-20260927-r1.json)也读到 3/3，但在进入新泽西房间前被 `Private Quarters New Jersey room is absent or ambiguous` 拒绝，互动次数未消耗。当前[纯语义结构收据](../artifacts/pq-special-diagnosis-20260927.json)显示原 `Map/floor_2/Xinzexi` 目标缺失；导出两个路径相同的 `Xinzexi_special` Button，均无顶层命中证明，也没有旧版 `front/complete/favor/Text` 解锁读数。页面回主页通过。不能凭相同房间图标或历史位置选一个点击。

观察器只为 `Xinzexi_special` 增加真实顶层 Raycast 和整数输入点搜索。本机 x86_64 增量构建、签名、安装与 `-force-gfx-st` 冷启动通过；[候选 APK](../artifacts/private-quarters-special-observer-20260927/candidate.apk) SHA-256 为 `98e2da400ad196d58b00c69ac6254c3784aebcfa75be4870741d5767e8b30390`，[设备原 APK](../artifacts/private-quarters-special-observer-20260927/rollback-installed.apk)已保存用于回滚。新[实机帧](../artifacts/private-quarters-special-observer-20260927/pre-mapping-live-r3.json)中两个同路径实例只有一个 `raycast_top=true`，另一个明确为 `false`；同帧两个房间图标均为 `room_icon_xinzexi`，两个状态均为 `state_main`，没有活动锁图标。适配层仅对这组结构选唯一真实命中的入口，其他组合拒绝。

原任务首次点击新入口后进入 `Dorm3dMainUI` 过渡，出现零按钮背景和 `TimelineTouch/content/clickTpl`；两者分别增加窄范围只读加载识别和经顶层命中、`timeline_touch_btn` 图标验证的继续输入。[首次运行](../artifacts/private-quarters-special-observer-20260927/native-interaction-r1.json)在尚未识别零按钮过渡时停止；[回程尝试](../artifacts/private-quarters-special-observer-20260927/native-interaction-r3.json)经原 ALAS 点击时间线后回到旧版 `Xinzexi` 入口，但回程子流程因已到总览而再次要求对话，故不作为通过证据。没有互动次数消耗。

随后[完整原任务收据](../artifacts/private-quarters-special-observer-20260927/native-interaction-r4.json)在同一进程读到 **3/3**，由原 ALAS 选房、入房、进行 **3 次** `private-quarters/interact`、退出房间，最终读到 **0/3** 且返回主页；`passed=true`、`continuous_interaction_passed=true`，临时配置已删除。本次实际完整链使用过渡后出现的旧版 `Xinzexi` 入口；新入口的点击和时间线回程分别有实机收据，但尚未在同一条成功链中重现。升级弹窗自然出现前，不宣称关闭能力实机通过；不通过改等级或消耗额外礼物制造触发条件。

## 验证范围

Research、适配边界、Exercise、Daily 导航、Shipyard 和验收脚本此前聚焦回归 **151 passed**；本次观察器与 PrivateQuarters 改动后，PrivateQuarters、Research 和原生命中测试 **120 passed**。观察器 C++ 经本机实际增量编译和实机命中验证；设备回拉 APK 哈希与候选一致。PrivateQuarters 配置回放、固定上游支持矩阵校验通过。本轮未改 ALAS 补丁成员或结构化支持等级；当前结果仅限定本地 AVD、这次游戏和账号状态。先前失败收据按原样保留。
