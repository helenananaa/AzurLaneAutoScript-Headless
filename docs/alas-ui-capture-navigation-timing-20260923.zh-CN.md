# UI 单次采集与原生导航分段计时（2026-09-23）

## 本次修改

`SemanticFrameClock.acquire(include_ui=True)` 首次 UI 读取就保留 `toggle_truncated` 的真实值，不再先严格读取、遇到截断错误后再请求同类数据。只允许保留布尔 `True` 标志；缺失、类型错误、文本截断、提取错误、身份或代次不一致仍按原规则拒绝。

完整 UI 的消费者继续拒绝 Toggle 截断，退役等能力仍自行验证所需片段。本次没有放宽 UI 完整性约束，也没有缩短 ALAS 等待。变化只减少截断场景的一次 UI 请求；普通完整帧没有这一额外请求，不能宣称每次取帧都获得同样收益。

验证：`test_adapter_frame.py`、`test_adapter_session_runtime_handle.py`、`test_semantic_task_isolation.py` 共 **105 passed**。新增断言证明截断帧只发送一次 `/v1/ui`，严格读取仍拒绝；Malformed flag 和 extraction error 也拒绝。此前完整相关回归不因这一局部变化重复执行。新探针编译检查及 `git diff --check` 通过。

## 测量方法

新增 `scripts/python/probe_alas_navigation_timing.py`。临时配置绑定 Benchmark，调用当前 patched ALAS 自带的 `semantic_reversible_input()`；不另写导航状态机。主页/设置页之间切换，准备与恢复阶段单列，使用专用语义输入和页面身份校验。

测量 `SemanticFrameClock.acquire`、ADB 命令、observer 请求、动作后条件等待和 sleep。耗时为包围调用的墙钟时间：frame 和 wait 包含其内部 ADB/observer 操作，不能把它们直接相加。observer 项包含 socket、传输及解码，不把它全归因于网络。ADB 项也包含主机进程和设备执行，不单独声称是游戏加载时间。

当前设备重新发现为 `emulator-5554`，包 `com.bilibili.azurlane`，PID `18011`，driver revision `506b76f698b5089aaa29c4e7908b48edb8532a44`。起始为商店。运行中只进行可逆页面切换，无购买、任务奖励或战斗资源消费。

## 首轮三组往返：六次单向切换

| 指标 | 结果 |
| --- | --- |
| 单次切换时间 | 1.410–2.231 秒，中位数 1.854 秒 |
| 六次累计时间 | 11.195 秒 |
| 前台检查 | 每次 8–9 次；累计 5.188 秒，占累计时间约 46.3% |
| observer 请求 | 每次 6–7 次 state、1 次 UI；累计 0.785 秒 |
| ADB 点击命令 | 每次 1 次；中位数 0.103 秒 |
| 取帧 | 每次 1 次 acquire；中位数 0.374 秒，包含其内部查询 |
| 后置条件等待 | 约 0.707–1.360 秒，包含轮询查询及等待 |

六次切换均完成。首版探针最后使用通用 `wait_for('shop/home')` 恢复确认，错误要求商店的图像控制满足普通 Button 的 `actionable`，因此最终报告 `passed:false`。实际商店已恢复，随后独立只读页面扫描确认了 `page_shop`。保留失败回执，没有将它改写为通过。

首轮 `time.sleep` 包装未覆盖 CoreOracle 在导入时保存的默认 sleep callable，因此不能从该轮直接给出精确 sleep 累计值。后置条件整体等待时间仍有效。

## 修正探针的一组验证

恢复确认改为完整商店页面身份；同时直接测量 live oracle 的 `_sleep`。只补跑一组往返验证修正，不重跑原三组。

- 两次切换耗时分别 1.881 秒、1.356 秒。
- 每次明确观察到一次约 0.500 秒的 oracle sleep。
- 前台检查分别 9 次/0.684 秒、8 次/0.611 秒。
- 点击命令分别 0.548 秒、0.088 秒，表明单次 ADB 命令也存在波动。
- 最终 `passed:true`、`restored:true`，恢复商店。

两轮分别 8 次、4 次 typed tap，累计 **12 次**，临时配置均删除。两轮只用于定位耗时，没有原版 ALAS 同设备对照，也不把不同轮次当成严格配对性能基准。

原始记录：

- `artifacts/navigation-timing-20260923.json`：六次切换及首版恢复确认超时。
- `artifacts/navigation-restoration-check-20260923.json`：随后独立只读恢复确认；不使用其取整后的 0.000 秒作为性能结论。
- `artifacts/navigation-timing-confirmed-20260923.json`：修正后的完整成功验证及 sleep 细分。

## 后续优先级

### 已完成：同一次帧采集只查询一次前台

`SemanticFrameClock.acquire` 内部读取 state、UI 和跨代闭合 state 时不再分别运行 ADB 前台查询；完整采集结束、发布帧之前执行一次实时前台检查。独立 live `read_state()` 保持默认前台检查，输入前检查与动作后实时轮询保持原样。没有增加跨帧或按时间缓存前台状态。

定向验证 **107 passed**，覆盖采集期间 state/UI 请求后前台切换时拒绝发布帧、直接 live 读取仍拒绝错误前台、输入前重新检查，以及稳定跨代采集只查询一次前台。PID、代次、截断和任务隔离的已有测试继续通过。

最终 adapter、ALAS adapter、semantic oracle、task isolation 和 private quarters 相关回归 **1272 passed，38.17 秒**；`git diff --check` 通过。

复测回执 `artifacts/navigation-timing-foreground-coalesced-20260923.json`：同设备、PID、driver，调用未修改的 ALAS Benchmark 原方法，三组往返均成功，`passed:true`、`restored:true`。本轮 8 次 typed tap，临时配置已删除，无购买或战斗。

| 指标 | 修改前首轮六次 | 修改后六次 |
| --- | --- | --- |
| 每次完整导航前台查询 | 8–9 次 | 6–7 次 |
| 取帧耗时中位数 | 0.374 秒 | 0.137 秒 |
| 单向导航耗时中位数 | 1.854 秒 | 1.284 秒 |
| 六次导航累计耗时 | 11.195 秒 | 8.378 秒 |

调用次数减少有代码和分段记录支持；耗时是前后小样本观察，受 ADB、游戏调度和 0.5 秒轮询影响，不是严格交错配对实验或普遍提速承诺。此前一组修正探针的中位数为 1.619 秒，也说明基线存在波动。此次未修改 ALAS patch、支持等级或历史回执。

本次证据最支持先检查原生 Benchmark/实际动作观察链路中的多次 live 前台查询，区分同一准备步骤可复用的观察与真正输入前必须进行的实时确认。其次评估 0.5 秒轮询间隔造成的发现延迟；不能从这个小样本直接缩短所有任务的等待。

页面扫描已经很快，继续微调其 CPU 调用不是当前最高收益项。暂不依据本次测量引入常驻连接、改写 observer 协议或改变所有任务的等待策略。本次未提交、推送或晋级支持状态。
