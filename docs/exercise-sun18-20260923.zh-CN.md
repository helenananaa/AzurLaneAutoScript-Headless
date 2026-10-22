# Exercise `sun18` 实机续推（2026-09-23）

## 范围与结果

在 `emulator-5554`、游戏包 `com.bilibili.azurlane`、PID 1927、observer driver `506b76f698b5089aaa29c4e7908b48edb8532a44` 上运行固定上游 ALAS 原 `Exercise` 任务。配置为 `ExerciseStrategy=sun18`、`OpponentChooseMode=easiest`、`OpponentTrial=2`、`LowHpThreshold=0.4`；单次运行最多准许一次出战、零次刷新。观察到本期剩余约 11 天，原 ALAS 日志计算 `Preserve 5 exercise`，因此剩余 8 次时允许出战。

完整 [实战收据](../integration/alas/exercise-sun18-trial2-live-validation-receipt-20260923.json) 记录原任务 `task_result=true`、演习次数 8→7、出战额度 1→0、刷新额度保持 0、结果页回到总览，校验 `passed=true`。随后两个单场运行从 7→6→5，均按一场额度完成。在剩余 5 次时，[保留阈值收据](../integration/alas/exercise-sun18-preserve-live-validation-receipt-20260923.json) 记录原任务 1.454 秒返回、次数仍为 5、出战额度仍为 1、刷新额度仍为 0，日志显示 `Preserve 5 exercise` 并将任务调度到次日零点。`OpponentTrial=2` 只证明该配置被接受，五场实战均首战成功，未触发第二次尝试。其他策略时段仍未验证。

## 遇到并修复的边界

从困难章节导航到演习时，ALAS 的页面枚举先探测 `EXERCISE_CHECK`。精确识别为普通或困难章节页后，这一无关页面探测现在被判为缺席；未知页面仍抛 `AlasSemanticUnmapped`。最初实战从稳定演习页起步，导航资格另见下节。

第一次实战 10→9 后，功勋商店覆盖层尚未关闭，旧校验脚本直接等总览而失败。使用精确的 `exercise/merit-shop/close` 语义按钮收尾，并让脚本在原任务返回后调用已有的演习结果栈处理器。

第二次出战在准备页切换期间，ALAS 再次看见 `BATTLE_PREPARATION` 并试图点击，适配器因演习意图已消费而安全拒绝；战斗本身完成，随后以语义结果页按钮收尾，次数 9→8。现在演习出战动作回执之后的 15 秒内将准备页重复探测判为“等待离开准备页”，不发第二次输入；若超过窗口仍在准备页，明确以 `SemanticGateClosed` 停止。聚焦测试覆盖短暂过渡和超时两侧。第三次 8→7 单场复验通过。

## 章节导航续验

原 ALAS 从演习页经战斗菜单进入普通章节，再返回菜单进入演习的四段导航已用 [往返收据](../integration/alas/exercise-chapter-navigation-live-validation-receipt-20260923.json) 实机通过。原日志记录四次精确语义点击与 `Page arrive: page_campaign`、`Page arrive: page_exercise`；演习剩余 5→5，出战额度保持 1，刷新额度保持 0，任务自行调度。

适配器只在精确返回/入口回执后的有限过渡期，把 ALAS 页面枚举和通用弹窗枚举的无关存在性探测判为缺席；菜单、章节或演习页的精确根节点出现后立即按各自页面识别。真实奖励、新舰和紧急委托目标保持独立检查，未知点击仍拒绝。全局更新重启的被动探测改用 ALAS 当前不可变语义帧，避免两个实时端点跨帧读取产生虚假的代数不一致；真正的重启输入仍需刷新帧并重新验证精确按钮。

## 剩余条件

- `OpponentTrial>1` 的实际二次尝试需要自然失败或低血退出后原 ALAS 再尝试的样本，不能用成功首战冒充。
- 其他非 aggressive 策略及切换时段仍需相应自然时间和次数。
- 该往返只覆盖演习、普通章节与战斗菜单；其他页面入口和活动章节未外推。
