# 工作区整理与本地提交（2026-09-13）

本次将 `75a094a` 之后积累的 41 个已修改文件和 132 个未跟踪文件保存为一个完整检查点；本页为额外的整理索引。代码、补丁清单、支持矩阵和被引用的证据一起提交，避免拆分后产生缺少证据或清单不一致的中间版本。未改变任务支持等级。

## 成果入口

| 工作内容 | 说明与证据入口 |
| --- | --- |
| 科研续跑、资源与重置观察 | [续跑](research-continuation-20260912.zh-CN.md)、[双资源](research-dual-resource-20260913.zh-CN.md)、[重置耗尽](research-reset-exhausted-20260913.zh-CN.md) |
| 船坞选择、系列与阶段解析 | [后续适配](research-shipyard-next-20260912.zh-CN.md)、[系列选择](shipyard-series-20260912.zh-CN.md)、[阶段调查](shipyard-fate-survey-20260913.zh-CN.md) |
| 登录恢复 | [船坞返回映射](login-shipyard-recovery-20260913.zh-CN.md) |
| 主线中途满船坞恢复 | [分段实机](campaign-midmap-recovery-20260913.zh-CN.md)、[原生流程离线回放](campaign-midmap-offline-20260913.zh-CN.md) |
| 原生宿舍交互 | [交互与退出边界](private-quarters-native-20260913.zh-CN.md) |
| 日常观察 | [当前观察](daily-current-observation-20260913.zh-CN.md) |

总体状态仍以 [任务板](alas-adaptation-task-board.zh-CN.md)、[状态记录](status.md) 和 `integration/alas/support-matrix-ledger.json` 为准。

## 本次验证

- 11 个相关测试文件：254 passed，31.12 秒。覆盖运行句柄、登录、科研、支持矩阵、继承退役恢复、宿舍、日常、船坞和中途回放隔离。
- 补丁系列检查通过：116 成员，合并补丁 SHA-256 为 `9259c71a73ef93c116a432d1c690f55774056d9aa52a5595895d8f25ec1c893c`。
- 支持矩阵验证通过：60 面板、278 字段、1217 个面板字段实例。
- Research、Shipyard、PrivateQuarters 配置验证器均在本地固定上游的临时补丁工作树上执行通过。
- 复用 `integration/alas/private-native-20260913/patch-tree-final/result.json`：其上游与补丁哈希同本次检查一致，记录了补丁应用与 Python 编译；本次未重复执行该补丁树验证。
- `git diff --check` 通过。部分原有文件出现 CRLF 转 LF 提示，未做批量换行重写。

本次没有重建 Android/observer、运行实机任务或全仓测试。原文档记录的 5 项登录 facade 调用序列 parity 失败仍保留，本次未重跑这些失败用例；254 项通过不代表全仓通过。连续主线恢复、宿舍完整退出、真实 FATE 面板与科研实际双资源消费等未完成范围见各主题文档。

## 文件与工作树处理

- 保留所有开发文件、测试夹具、历史成功及失败回执；未移动 `artifacts/` 或 `integration/alas/` 的证据路径。
- 当前工作树属于 `codex/alas-fixed-upstream-capabilities`；其他平台及上游更新工作树保留。
- Python/pytest 缓存删除被自动审批策略拒绝（`blocked by policy`），因此缓存保留。
- 本次仅作本地提交，不推送远端。
