# 同帧解析与页面扫描重复查询清理（2026-09-23）

本次在现有未提交工作区上继续优化，没有修改 ALAS 任务状态机、补丁成员或支持等级。

## 改动

- `_FrameBoundSemanticOracle` 按帧缓存通过校验的 Button 状态、UI 状态、文本状态，以及浅层页面/目标存在性结果。原始记录递归冻结，消费者不能修改缓存污染后续判断。
- 每次命中缓存仍借用原帧；刷新、输入失效、关闭、PID 或运行时身份变化后，旧 reader 拒绝使用。实时 Oracle 不缓存。
- 文本读取、完整 UI 读取和允许保留部分 Toggle 标志的读取分别缓存；宽松读取不能替代严格读取。失败不缓存为成功。
- Session 的通用网络重连和奖励弹窗观察使用当前 screenshot 对应的帧。没有帧的直接只读探针沿用现有实时读取路径。输入前的刷新、前台确认、时效、唯一目标、遮挡与后置条件不变。
- 地图世界坐标和 Private Quarters 物理记录的消费者接受冻结后的 Mapping/tuple，保持原有数值、完整性和歧义检查。
- 只读页面探针新增 `--profile`，只统计页面扫描，不包含取帧、导入和运行时初始化。

缓存只覆盖帧内数据和浅层存在性判断，不缓存带任务状态的整个 `appear()`，也不复用动作授权或把旧帧视为新观察。

## 实机只读结果

重新发现的设备为 `emulator-5554`，包为 `com.bilibili.azurlane`，运行时 revision 为 `506b76f698b5089aaa29c4e7908b48edb8532a44`。探针通过正常会话获取并校验语义帧，未注入输入、重启游戏或消耗游戏资源。

| 商店页候选扫描 | 候选数 | 最终结果 | 时间 |
| --- | ---: | --- | ---: |
| 先前前台查询优化后的保留记录 | 33 | `page_shop` | 8.047 秒 |
| 本次无 profiler | 33 | `page_shop` | 0.110 秒 |
| 本次扫描阶段 profiler | 33 | `page_shop` | 0.078 秒 |

相对先前单次记录，本次无 profiler 扫描耗时减少约 98.6%。这是同设备同页面的单次记录比较，不是严格配对的总体性能基准，不能推导完整任务或相对原版 ALAS 的加速比。profiler 与无 profiler 是不同次运行，不据此判断 profiler 的影响。

新剖析的扫描阶段：

- 实时前台查询和 observer 网络请求均为 0；取帧阶段仍执行必要查询。
- 底层 `CoreOracle.read_state()` 解析 1 次，解析 Button 19 条。
- 帧 reader 的 `read_state()` 被调用 1,048 次，命中缓存与轻量租约检查；没有将这些调用数误报成解析次数。
- 本地冻结投影读取 2 次（状态与 UI）；它们不是网络请求。

原始结果：

- `artifacts/page-sweep-parsed-frame-cache-20260923.json`
- `artifacts/page-sweep-parsed-frame-profile-20260923.json`
- `artifacts/page-sweep-parsed-frame-profile-20260923.pstats`

## 验证与边界

针对性测试 **161 passed**，覆盖缓存复用、嵌套不可变性、刷新与运行时失效、部分 UI 隔离、地图和物理读取、只读扫描无实时查询，以及既有前台切换/过期帧输入拒绝、任务隔离测试。

扩大到 adapter、semantic oracle、任务隔离和 Private Quarters 回归后：**1,252 passed / 15 failed**。独立复制当前 Python 源码并仅撤去本次生产代码改动的对照为 **1,247 passed / 同样 15 failed / 5 deselected**；排除的是本次新增测试。没有修改工作区来跑对照。

15 项既有失败涉及登录 facade 调用序列、补丁文件数旧断言、宿舍/战役/大世界/演习测试替身、META session 替身，以及强化/战役模式/预战斗返回断言。不能将扩大回归报告为全绿。对照源码、完整输出和 JUnit 保留在 `artifacts/parsed-frame-cache-baseline-20260923/`。

以下验证通过：

- `build_alas_patch_series.py --check integration/alas/0001-semantic-oracle-hooks.patch`：117 个成员，组合哈希一致。
- `verify_alas_patch_tree.py`：在本地干净 pinned upstream 上应用并编译通过；结果位于 `artifacts/parsed-frame-cache-patch-verification-20260923/result.json`。最初向已有补丁的运行树执行验证被“工作树不干净”检查拒绝，随后使用独立干净上游完成，没有清理运行树。
- `verify_alas_support_matrix.py`：结构、生成矩阵与补丁引用一致。
- `verify_alas_configuration_attack_matrix.py --alas-root artifacts/campaign-preparation/upstream`：通过。
- `git diff --check`：通过。

本次未重新执行完整游戏任务、未测量完整任务加速、未晋级支持状态，未提交或推送。
