# 每日快速挑战与 META 支援：边界补齐

日期：2026-09-11。固定 ALAS 基线 `81ccf63b4540f00241628c82a58c02c7a2bb11af`。
本轮完成观察和输入端口修复，未将任务整体提升为支持。

## 每日挑战

- 快速挑战输入检查真实顶层射线命中、前台和遮挡；新观察器导出对应按钮命中。
- 剩余次数按挑战标题的语义身份读取，避免轮播重排后读到另一个挑战。
- 原生 `GOTO_MAIN` 可经每日页面的已审查返回按钮退出。
- 新验证入口 `scripts/python/run_alas_daily_quick_live_validation.py` 保留原生 Daily 状态机，要求一次真实快速执行和实际次数归零；不篡改观察次数。

实机当天 Escort/FierceAssault 各有 3/3 但未开放；Advance/Tactical 为 0/3，Supply 为 0/4，Module 为 0/2。原生 Daily 正确跳过未开放的 FierceAssault，任务返回成功但验证器明确记录 `passed=false`、零事务。因此没有快速挑战真实消耗证据。重入条件是一个已开放、仍有次数并提供快速挑战的关卡。

证据：[原始页面](../integration/alas/daily-quick-20260911/preflight.json)、[未触发事务](../integration/alas/daily-quick-20260911/live-r1.json)。普通挑战保留已有观察器缺少可选 raycast 字段的兼容行为，快速执行要求明确命中。

## META 支援

- 补丁成员 0650 为原生 `AshBeaconAssist.run` 建立/释放任务上下文；恢复后重新绑定上下文，战前输入和战斗结果不会误归每日任务。
- 支援仍消耗 `meta.assist` 执行额度，不使用个人信标的旁路；结束时释放战斗上下文。
- `BEACON_MY` 页面标记及 `BEACON_REMAIN` 次数读取使用 typed 状态，次数为零、开始按钮禁用时仍能观察。
- 补齐旧档案详情→旧档案列表→当前支援列表的两个精确按钮端口。保留原生导航决策；没有新增任务状态机。
- 主界面侧栏已打开后，重复入口请求仅在观察到更新代次和侧栏返回控件时复用真实入口回执，避免再次切换侧栏。

实机从已击败的旧档案详情进入当前支援列表，看到 8 个候选、剩余 0/3。原生 `_begin_meta_assist()` 判断次数耗尽并正常返回，前后次数不变，上下文释放成功。
这只是原生 helper 的零次数路径，不是完整 `AshBeaconAssist.run`、战斗、战果或 `MetaReward` 领奖验收。完整领奖仍有未适配的像素路径。实战重入条件为支援次数恢复及可用候选。

证据：[旧档案列表操作](../integration/alas/meta-assist-20260911/archive-list-inspection.json)、[当前列表操作](../integration/alas/meta-assist-20260911/current-list-inspection.json)、[原生零次数路径](../integration/alas/meta-assist-20260911/zero-attempt-live-r2.json)。旧档案挑战不消耗当前支援次数，二者没有混算。

## 实际观察器与验收边界

复用本机 WSL ANGLE 源码，仅增量构建 x64 NULL 观察器，J32，两次各 12 步，约 9.51 秒和 8.54 秒。未做 AOSP 镜像构建。

已安装 `artifacts/daily-quick-20260911/observer-daily-meta-r2.apk`，SHA256 `f4cc1b0cc12cebd1ba611de321a1ed1a85197a2a6bb186b9f263a77102e7603e`；设备实际安装包校验一致。回退包 `artifacts/daily-quick-20260911/observer-before.apk`，SHA256 `b769137bd2d2c6b783f364a800cba243d0cd5392aff708af36a47fba53895d31`，回退本轮未执行。

设备为发现并核验的 `emulator-5580`；游戏按 `-force-gfx-st` 冷启动。最终 PID 24729，typed 代次 21444，已返回主界面。每日与 META 本轮未开始战斗、未消费挑战次数、未购买或消费高级货币。全程不用游戏截图。

92 项聚焦回归通过，覆盖每日、META、任务隔离、执行额度、补丁和支持矩阵；26 个警告来自保留上游的转义写法。112 个补丁成员可在干净固定上游应用并编译；最终登录回放、截图帧时钟、像素访问清单、配置攻击矩阵及支持矩阵校验通过，未分类像素访问为零。这里只约束被验证的回放入口，不代表 META 领奖等未执行入口已适配。失败尝试保留在两个证据目录中；最终校验日志使用 `final` 后缀，回归最终记录为 `final-tests-r2.log`。
