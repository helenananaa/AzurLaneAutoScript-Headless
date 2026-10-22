# 固定上游：连续出击准备与普通关卡复用

补油后的续验和授权清仓见 [后续记录](campaign-oil-refill-closure-20260907.zh-CN.md)。下文缺油停止及对应 PID/资源数保留为当时的历史证据。

范围仍为 ALAS `81ccf63b4540f00241628c82a58c02c7a2bb11af`；不处理安装树基线或上游升级。

## 实现

- 普通出击不再要求剩余预算恰好为 1。每次授权记录当前预算，点击必须使用同一授权，手动地图确认验证恰好扣减一份；不会因重新准备补充任务预算。
- 原 `CampaignRun._run` 决定是否运行下一轮并扣减 `StopCondition_RunCount`。新 `0540` 边界只在该循环下一次调用 Campaign 前清理已完成出击的临时观察、舰队证明和书确认状态；必须已证明完成并回到关卡页。自动搜索复用结算证明，手动地图复用原 CampaignBase 已查询的 Boss 返回判定，完成的继承运行也清理旧观察。未完成的运行保留恢复边界。
- 普通官方自动搜索删除职责、出击与结算的 `12-4` 历史验证白名单。实际关卡身份、准备页、两支不同舰队、职责、油耗和可操作目标仍逐项验证。困难关卡的独立限制没有改动。
- 弹窗的被动存在探测复用 ALAS 截图边界的不可变语义帧，避免出击切场期间反复把新 UI 与旧状态拼接；输入仍使用原来的实时目标检查。
- 已消费的关卡入口不再解析被遮挡的底层列表；首次入口仍严格验身份。无大世界结算 UI 时只做负向存在判断，不把无关的双端点采样间隔当成兼容失败。档案秘钥确认先识别档案专用 HUD，不抢占普通出击的 Msgbox。
- `BOOK_CHECK_AUTO / BOOK_BOX_AUTO` 使用实际 `Window/Fixed/SpList/Item`、指令书图标、库存与 `Active/Checkbox/Mark`。准备页仍使用自己的 `Fixed/sp` 控件。原 FastForward 开关循环不变；状态未改变时拒绝再次发送同一个翻转输入。
- 勾选书本身不消耗书或石油，因此允许当前 Campaign 上下文配置继承的结算菜单，不额外要求拥有上一轮出击；继续出击仍保留独立授权。
- 策略栏开关、阵型循环和地图舰队切换补齐正向 raycast；策略输入同时检查前台、遮挡和观察一致性。新增 observer APK 为增量构建，不是 Android 镜像重建。
- 实机验证入口增加 `--run-count`；每轮完成证据在任务销毁前保存，另可只读采集结算菜单，不能仅靠 RunCount=0 宣称逐轮证明齐全。

这里的连续出击是“结算退出关卡页，再由原 ALAS 循环准备下一轮”。它不等同于 AUTO 菜单内直接继续出击。真实菜单的按钮名是 `ButtonGO`、标签为“再次前往”；没有把它冒充旧 `ButtonContinue`。

## 离线验证

- `7-2`/`12-4` 两轮准备，舰队 `(2,1,0)`、职责 Boss/道中，预算 `2 → 1 → 0`，用尽后拒绝第三次入口；未完成不能丢弃上一轮状态。
- 原 StrategyHandler 在同一实例依次设置两队不同阵型，再次访问两队不重复设置。组合为单纵/复纵、轮形/单纵；原函数回放 74 个检查通过。
- 普通手动出击也可在剩余预算 2 时扣减一份并确认地图，不再要求整项授权用尽。
- 直接执行物化固定上游的 `CampaignRun._run`：页面/战斗使用 fixture，循环、调用顺序和计数使用原函数；两轮共用同一 ledger，入口和出击预算均 `2 → 1 → 0`，原 RunCount 归零。这个回放也保护“先清理已完成准备，再检查入口”的顺序。
- 99-member 补丁已在固定上游应用、编译，登录回放、帧时序、像素边界和配置支持矩阵通过。
- 最终相关 Campaign/Session/Oracle/任务隔离与验证器用例 **328 passed**；补丁/支持元数据测试另 **19 passed**。没有宣称全仓测试全部通过。

证据：`integration/alas/campaign-repeat-final-patch-tree-20260907/result.json`、
`campaign-repeat-fleet-replay-20260907.json`、`campaign-repeat-final-login-replay-20260907.json`、
`campaign-repeat-final-frame-replay-20260907.json`、`campaign-repeat-final-pixel-20260907.json`。
最终组合补丁 SHA256：`cfbbf07cfa53cb26d418916869c2e418d2b42f5911828237dc0edbcc31009efc`。

组合测试中配置回放会预先导入 `module.map.map_operation`，与随后验证“尚未导入”的事件加载器测试发生进程状态干扰：103 passed、1 skipped、1 failed；该加载器用例独立运行通过。没有放宽生产加载器检查。

## 实机范围与剩余项

设备为 `emulator-5580`，APK versionName 实测 `9.7.10`；这不是对资源热更版本的全面支持声明。
新 observer 冷启动使用 `-force-gfx-st`，当前 PID `6454`，安装 APK SHA256 与本地文件一致：
`6e3a769f815d141883fb2f13dd31dfb3b1046a9d914d8a6040c32ade1a05a3fd`。
文件：`artifacts/campaign-preparation/observer-auto-book-strategy-20260907.apk`。

### 普通关卡与舰队职责

`7-2` 的原 Main 已做舰队交换及 Boss/道中职责调整并发出出击；其后旧弹窗探测异常导致 ALAS 退出，官方战斗自行完成。类型化结算菜单采样和退出读回证明石油 `2422 → 2009`，不能把它写成原任务全程通过。

`3-1` 的 r5/r6 则由原 Main 完成单轮出击和退出结算，证据保存了 `(2,1,0)`、Boss/道中、出击代次和完成代次。r5 还记录了初始 `(1,2,0) → (2,1,0)` 的完整准备变更。
两次任务总结果仍为 false：原调度器按到期任务切换，只把 RunCount 从 2 减到 1。这不是第二轮能力的正向证据。
固定 ALAS 会强制启用 Commission/Research/Reward，验证脚本改在**临时配置**中把无关任务的 NextRun 延后一小时；没有改动生产调度器。

相关证据：`campaign-repeat-main-live-20260907-r5.json`、`campaign-repeat-main-live-20260907-r6.json`、`campaign-auto-menu-observation-20260907.json`（均位于 `integration/alas`）。失败尝试日志保留于 `artifacts/campaign-preparation/repeat-main-r*.log`。

### AUTO 指令书开关

`integration/alas/campaign-auto-book-live-20260907.json` 为通过记录。
原 FastForward `_set_2x_book_status` 实测 `false → true → false`，代次 `18719 → 18815 → 18908`，两次均有正向 raycast。库存保持 `568 → 568`，没有发送出击输入。
两个独立测试用例之间调用原 ALAS `interval_clear`，避免前一次探测间隔让下一次被误判为“无书控件”。

### 两支舰队的不同阵型

`integration/alas/campaign-formations-live-20260907-r1.json` 记录原 ALAS 在 `12-4` 手动地图准备 `(1,2,1) → (2,1,0)`、进入地图，再由原 StrategyHandler 应用两队配置。
第一队已经是单纵阵，原处理器正确走无操作分支；第二队从复纵阵切至轮形阵。随后两队都读回并恢复为各自原来的单纵/复纵，四次地图舰队切换也记录了回执。

该脚本总结果仍保留 false：撤退确认在弹窗文字未挂载时采样过早。只读等待已修正；随后在同 PID 下补验，代次 `8581 → 8632`，关卡页为 true，石油 `1447 → 1437`。不重写原失败记录，也不为了相同阵型证据重复入图。
本段没有战斗；它证明配置、策略栏动作及恢复组合，不代表手动战斗导航所有分支完成。

### 连续任务的最终实机边界

`campaign-repeat-main-live-20260907-r8.json` 暴露入口检查早于状态重置的问题，已修正 `0540` 并补原循环回放。
最终 `campaign-repeat-main-live-20260907-r9.json` 保留 false：首轮由原 Main 完整结束，调度器明确选择继续 Main，但第二轮先触发原 ALAS 的油量保护。剩余油量为 `449`，低于原函数自身的最低 `500`（即使配置 OilLimit=0 也存在）。没有改动或绕过它。

因此，本轮**没有完整两轮连续出击的实机正向记录**；不是以单轮或 fixture 冒充两轮。代码和原循环离线闭环已经具备，完整实机补验需要先有足够普通石油。

最终已回主页：同 PID `6454`、代次 `50158`，石油 `449`，最近结算读到书 `568`。
本轮石油从 `2422` 净减少到 `449`（`1973`），包含失败任务退出后官方战斗自行完成的消耗；没有消耗指令书、购买或使用高级货币。此后不再追加战斗验证。未提交或推送 Git。

### 尚未提升的范围

- 两轮完整主任务仍需在原 ALAS 低油保护以上补实测，不用单轮记录代替。
- AUTO `ButtonGO` 的再次前往流程尚未接入；已有的是 AUTO 书开关及返回关卡页后的重复准备。
- 连续实际消耗双倍书尚未实测；9 月 6 日的单轮消耗与本次开关验证是分开的证据。
- 无可读出击油耗摘要的普通图仍有旧的 `conservative-uncapped-reserve` 预留（本次 `3-1` 为 1000），没有把这个剩余限制伪装成关卡白名单问题已经全部消失。
