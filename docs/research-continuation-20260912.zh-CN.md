# 科研资源策略续接（2026-09-12）

范围为固定上游 `81ccf63b`、本地 ANGLE NULL x64 AVD，复用原 ALAS
`RewardResearch.run()`、选择器、队列和调度。使用现有单次启动验证入口；
它会在一个项目启动后停止继续填队列，因此不是六项目满队列或长期无人值守证明。

## 科研入口修复

最初从主页进入科研时，目的页面已出现，原 ALAS 仍按旧帧重复请求
`RESHMENU_GOTO_RESEARCH`，最终报 `research-menu/research` 不存在。
现场失败保留在 `research-continuation-20260912/probe-r1.log`。

现有 12 秒转场回执在较慢的页面扫描后可能已过期。新增目的页完成确认：
必须有本次 Research 上下文内实际入口回执、可操作的科研返回按钮、完整五卡
类型化状态和更新代次，才复用回执。源入口在输入前消失时再检查一次；已经发出
输入的异常仍向上传递。结束 Research 上下文后回执失效，不新增替代导航循环。

## 魔方 only_05_hour

`cube-half-r1.json` 为 passed=true，原任务同进程完成：

1. 领取队列中已完成的 G-236-MI、G-412-MI、Q-389-MI；一次领取事务，三个奖励页关闭。
2. `S9-H` 自定义过滤、其他资源禁用时，原选择器在 enforce=false 下返回空。
3. 原 `research_enforce()` 切换 enforce=true，选中 S9 H-387-MI（一小时）。
4. 详情库存 3226，确认消耗 3 个心智魔方；启动、入队确认及原任务返回成功。
5. 原任务给出下次运行时间 `2026-09-12 21:51:49`。配置为临时验证配置，结束后删除。

这证明 **only_05_hour 的原生强制选择分支**，并不证明半小时魔方项目正向路径。
固定上游在 enforce=true 时允许非半小时项目；适配器没有重写这项策略。
真实半小时项目、半小时 Q 双资源确认、重置和长期跨轮仍需各自证据。

## 部件 only_no_project

`part-no-project-r1.json` 为 passed=true。上一轮结束后自然出现 Q-368-MI，
使用 `S9-Q` 过滤、禁用物资和魔方。原选择器先返回空，再由 enforce=true
选择一小时 Q-368-MI；详情库存 17983 个防空炮部件 T1，确认精确消耗 20 个，
随后入队，原任务返回并调度至 `2026-09-12 21:51:49`。
这一轮没有新增奖励领取。两轮合计启动 2 个项目，消耗 3 魔方和 20 个 T1 部件，
没有刷新、购买或付费货币消耗。

两个收据均为各自同进程成功，但不把它们合并成长期跨轮验收。
新候选中也没有半小时 Q 项目；双资源确认保持原来的明确拒绝。

## 证据位置

本轮收据和日志位于 `integration/alas/research-continuation-20260912/`。
初次队列探针误在卡片页读取队列而失败；改为原生 queue_enter/queue_quit 后
`inspect-r3.json` 成功读到三项完成状态。该探针错误不归为运行时回归。
代码与设备失败均保留，不将独立恢复拼成同进程成功。

聚焦回归 `tests-focused.log` 为 63 passed；Research 配置校验和固定上游支持矩阵
校验通过。未修改 ALAS 补丁系列或观察器，不需要 Android 构建。
实机导航日志中的部分页面扫描间隔约 40 秒，性能原因尚未定位；本次修复转场
正确性，没有宣称导航性能已改善。

首个完整导航诊断把 Research 上下文保留到了外层回主页。最初把停顿归因于
这一诊断生命周期差异，但进一步完整状态审查发现：主页底层上方有
“当前研究中的高梁有新的进展，请去开发船坞确认”双按钮通知，才是实际阻塞。
**main_page_visible 不等于没有遮挡的可用主页**。`navigation-r1-interrupted.json`
中的原诊断理由由本段更正；收据仍为 passed=false，保留两个栈采样及原日志。
`navigation-r2.json` 也保留 Unknown UI 的失败。后续脚本按原
`RewardResearch.run()` 的 finally 生命周期，在外层回主页前结束 Research，
并逐阶段保存中间结果。该调整不改变产品任务状态机。

新增 `research/progress/confirm` 只接受上述进展通知结构及确定/取消按钮文案，
支持舰名变化；资源消耗、购买和不完整通知均不能借用该输入。沿用原
`ui_additional -> handle_popup_confirm -> 船坞 -> 原导航返回`，不执行购买或强化。
默认消息框仍遮挡底层页面。新增正反测试后，科研聚焦回归为 65 passed。

`notice-recovery-r3.json` 在原未知页面探测 `GOTO_MAIN_WHITE` 时被错误路由到
邮件任务上下文，尚未到达 popup handler 就失败。现在只在精确进展通知存在时
将 GOTO_MAIN/GOTO_MAIN_WHITE/RPG_HOME 判为遮挡，原 handler 随后继续。
加入任务隔离、船坞和每日导航回归后，`tests-final.log` 为 122 passed。

`notice-recovery-r4.json` 尚未通过：原 `handle_popup_confirm()` 要求取消与确认
两个控件同时可见，首版仅提供确认观察，因而未执行该分支。补齐相同严格文案
下的取消观察/输入后，`tests-final-r2.log` 为 122 passed；不借用资源确认端口。

最终 `notice-recovery-r5.json` 为 passed=true：原 UI 确认进展通知
（generation 158360），识别船坞并返回（generation 159411），原导航确认到达
主页；通知已消失。仅两个实际 oracle 输入，无购买、强化或开发任务领取。
这是一份独立恢复收据，不覆盖前面被中断的完整导航诊断。
恢复前后资源相同：钻石 5040、石油 6193、物资 32958。最终恢复收据的
semantic source hashes 与交接代码逐文件一致，支持矩阵最终校验见
`support-handoff.log`。Research 保持 L，未提升成全配置完整支持。
