# PrivateQuarters 连续流程与等级 4 阻挡（2026-09-26）

本轮修复选房导航缺口，并再次运行原 ALAS 新泽西互动任务。三次互动实际完成，但自然好感升级弹窗阻止房间退出，原任务超时。**连续闭环未通过，PrivateQuarters 保持 P。**

## 范围和修改

原 AVD `E:\Runtime\AndroidAVD\alas_game_api32_x64.avd`，发现并绑定 `emulator-5554`；游戏 9.7.394、原 PID 1966、观察器修订 `506b76f698b5089aaa29c4e7908b48edb8532a44`。目标为新泽西，`BuyRoses=False`、`BuyCake=False`，只允许原任务的三次普通互动。保留 ANGLE NULL、userdata，无截图或坐标回退。

- 当原 ALAS 一轮页面扫描已依次完成主页→生活区→选房，之后仍遇到旧主页别名时，凭两段真实入口收据和当前新鲜选房页确认到达，不再尝试点击已消失的主页入口。
- 选房页/生活区上的无关奖励和战斗准备探针，以及已证明无遮挡选房页上的旧弹窗探针，按被动缺席处理。真实奖励、委托提示、遮挡及未知输入不被这一处理放行。
- 已有回主页过渡窗口也覆盖 `ui_additional` 的 `MAP_PREPARATION` 被动探针；选房入口实际点击后同样给予该探针 30 秒过渡窗口。超时恢复拒绝，输入仍拒绝。
- 验证脚本即时保存动作收据，补充运行身份、任务入口日次数及连续互动结果，避免把全关闭恢复分支当成互动成功。

实机 ALAS 三份相关文件落后于仓库现有补丁：`module/private_quarters/interact.py` 缺少 0680 到达判断，`module/device/control.py` 缺少 0690 分层控件身份，`module/private_quarters/private_quarters.py` 缺少配置验证。本轮先备份至 `artifacts/private-quarters-live-before-sync-20260926/`，再同步为当前 119 成员补丁系列应用到固定上游 `81ccf63b4540f00241628c82a58c02c7a2bb11af` 的精确三文件结果。仓库补丁成员没有改动；不宣称整个实机 ALAS 工作树已全量同步。

## 实机结果与失败边界

前四轮均在入口阶段停止，未执行互动：分别为到达选房后的旧 `main/live` 输入、主页入口瞬时不可操作、`GET_MISSION` 未映射、`MONTHLY_PASS_NOTICE` 未映射。失败原始文件保留于 `artifacts/private-quarters-native-continuity-20260926-r1` 至 `r4` 的 JSON/日志。

[第五轮完整失败收据](../integration/alas/private-quarters-continuity-20260926/private-quarters-native-continuity-20260926-r5.json)从主页执行原任务：

| 阶段 | 结果 |
|---|---|
| 选房与日次数 | 新泽西，原任务读取 3/3 |
| 三次触摸 | 收据代次 47723、47747、47771 |
| 三次 IK 返回 | 47734、47758、47778 |
| watch 返回 | 47791 |
| base 返回 | 升级弹窗遮挡，未输入 |
| 原任务 | 10:19:45 原等待保护超时，未到调度与回主页 |

[弹窗独立只读观察](../integration/alas/private-quarters-continuity-20260926/private-quarters-levelup-observation-20260926.json)确认新泽西好感等级 **4**、进度 **20/800**，活动 `LevelUpWindow` 存在。背景 `LevelUpWindow/bg` 的 `raycast_top=false`，房间 base 返回同样为 false；没有观察到可用于关闭该弹窗的顶层可操作按钮。身体投影处的 UI 顶层命中是 `LevelUpWindow/panel/bg/item1/mark/word_get`，它是装饰文字图像，不是已验证的关闭控件。不能把它或身体输入当作弹窗关闭。

三次触摸后没有重复互动或穿透输入。未购买礼物、未消费付费货币来制造新的升级条件。不能用事后恢复拼接成一次无中断成功。

## 恢复与后续

同一游戏包按 `-force-gfx-st` 冷启动，PID 变为 25656。第一次读取尚处于启动期，语义状态过期而零输入退出；待状态恢复后由原 LoginHandler 登录并到主页，`private-quarters-cold-recovery-20260926-r2.json` 通过。保留原 userdata、渲染器和 AVD。

后续零互动恢复前两轮仍在页面过渡的 `MAP_PREPARATION` 探针停止；补入口过渡处理后，[第三轮全关闭恢复](../integration/alas/private-quarters-continuity-20260926/private-quarters-zero-recovery-20260926-r3.json)通过：原任务读取 **0/3**，排到 **2026-09-27 00:00:00**，随后调用原 `UI.ui_ensure(page_main)` 返回主页，实际互动输入为 0。三次日次数已消耗，临时配置删除，最终游戏在主页。这份恢复收据的 `continuous_interaction_passed=false`，不替代失败的互动闭环。

下一步应补观察器对升级弹窗**真实关闭接收器及其顶层命中**的可验证语义输出，再接入原 ALAS 弹窗处理/返回边界。不能仅凭可见背景增加关闭映射。完整互动复验还需要自然恢复日次数和下一次真实升级；当前等级 4 现场证据已保留，无需重复消耗资源来重现同一失败。

## 验证

PrivateQuarters 观察/物理/配置、Mission、Login、Exercise、Daily、Research、Session 共 **181 passed**。新增覆盖确认到达的旧别名复用、缺收据/旧代次/不可操作状态拒绝、被动探针窗口过期、真实提示和遮挡不被吞掉。输入和状态机的原边界保持。

最后新增入口过渡后的聚焦观察测试 **50 passed**；支持矩阵测试 **8 passed**，矩阵生成与固定上游配置来源、119 成员补丁哈希核验通过。未修改补丁系列或提升支持等级。

[运行索引](../integration/alas/private-quarters-continuity-20260926/runs.json)保留各轮原始文件路径、SHA-256、结果与动作代次。失败收据不改写为通过，支持矩阵等级不提升。
