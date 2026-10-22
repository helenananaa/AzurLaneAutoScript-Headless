# FleetLock 与伏击适配进展（2026-09-07）

固定上游仍为 `81ccf63b4540f00241628c82a58c02c7a2bb11af`。
FleetLock 已取得原 ALAS 的双向实机结果；伏击输入及原规避/战斗分派已经补齐，
自然伏击的正向实机验证仍未完成。

## FleetLock

在 12-4、周回开启、自律寻敌关闭的手动地图中，确认了
`LevelStageView(Clone)/right_stage/event/collapse/lock_fleet`，其图标为
`auto_battle_on/off`。控件由当前 observer 证明顶层可操作。

适配通过原 ALAS 的 `FLEET_LOCK` Switch 消费 typed 状态和输入。
原 `handle_map_fleet_lock()` 连续完成开启、关闭、再开启，三次均读回目标状态。
控件缺席继续由原 ALAS 判断无该选项；未知图标、重复目标、遮挡和过期状态禁止输入。
同一状态在输入后未推进时停止重复切换，避免第二次点击反转延迟生效的第一次点击。

证据：`integration/alas/campaign-fleet-lock-live-20260907.json`，
PID `1929`、设备 `emulator-5580`；原 ALAS 日志在
`artifacts/campaign-preparation/fleet-lock-live-20260907.log`。
该结果限定于本次地图/客户端条件，不提升整个 Campaign 面板为完整支持。

## 伏击

新增 `0530-campaign-ambush-flow.patch`：

- 将语义分支接回原 `_handle_ambush()`、`_handle_ambush_evade()` 和
  `_handle_ambush_attack()`，由原 ALAS 继续拥有等待、规避结果和战斗流程。
- 规避结果读取已有 TipPanel 的 typed 通知；成功、失败与未知分别走原有分支。
  原 info-bar 等待能够清理旧规避通知，结果不能在本次点击前被消费。
- 输入必须属于唯一的 `LevelAmbushView(Clone)`，精确定位躲避/迎击控件，
  要求 `raycast_top=true`。不再接受 null，也不把另一根节点的按钮绑定过来。
  根 Canvas 不必额外挂载 Button；唯一、完整的子控件路径也可证明界面归属。
- 伏击选择收据允许复用现有战斗输入接口，但独立于计划中的地图目标收据。
  它不会被当成击败 Boss、移除地图敌人或完成原计划战斗；旧防御资源映射不能截走新端口。
- 相同伏击未完成时不重复输入；原处理函数返回后仍需新 generation 和弹窗消失证明。

observer 为躲避/迎击按钮增加精确命中检测与可见区域中心采样。
本地 x64 ANGLE 增量构建完成 12 步、约 4.76 秒，新 APK 已安装并通过
`-force-gfx-st` 冷启动和原 ALAS 登录。
APK SHA-256：`f090e63c7d834a699bd23707eb4b515f093465bfa32916fa8742c3a209776dda`。

## 自然样本条件与收尾

通过原 Main 分别用现有舰队 1、6 进入周回关闭的 7-2，战斗/镜头预算均为 0。
两次 typed 观察分别显示侦查值 **175**、**147**，受到伏击概率均为 **无**。
因此没有重复移动碰概率，没有自然伏击，也不宣称躲避成功、失败或迎击已实机闭环。

原始观察保存在：

- `integration/alas/campaign-ambush-probability-fleet1-20260907.json`
- `integration/alas/campaign-ambush-probability-fleet6-20260907.json`

本轮三次地图进入均未战斗，按入口计消耗 30 石油；后两次已分别读到
`2442 → 2432 → 2422`。没有使用指令书、购买或退役。
已撤退、恢复验证参考舰队 `(1,2,0)`、开启周回并回到主页。
下一次正向验证需要一个**实测伏击概率非“无”**的地图/舰队状态；这次没有证明
所有已有舰队或所有地图都无法触发。

## 验证

相关 Campaign、Session、战斗接口、任务隔离和 native 选择器测试共 **207 passed**。
规避成功/失败/未知的原函数回放、输入归属、无进展拒绝、同根绑定和 null 命中拒绝均有覆盖。
98-member 补丁在固定上游应用及编译通过；登录、帧时序、像素边界和支持矩阵另行核对。
最终补丁树记录为 `integration/alas/campaign-remaining-patch-tree-final-20260907/result.json`。
未重写以前的实机结果，未提交 Git；本轮没有把自然伏击提升为已实机支持。
