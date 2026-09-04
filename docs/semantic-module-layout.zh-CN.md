# 语义适配代码导航

`semantic_oracle.py` 和 `alas_adapter.py` 保留原有导入入口。具体实现按能力放到
`oracle/` 和 `adapter/semantic/`，测试按同样的能力命名。修改一种任务时，先从
对应模块和测试开始，避免继续向公共入口追加任务分支。

## 从哪里开始修改

| 修改内容 | 实现位置（相对 `python/alas_headless/`） | 测试位置 |
| --- | --- | --- |
| Observer 通信、ADB 桥接 | `oracle/transport.py` | `tests/test_semantic_oracle_transport.py` |
| 类型、异常、目标映射 | `oracle/contracts.py`、`errors.py`、`button_targets.py`、`ui_targets.py`、`campaign_mappings.py`、`blockers.py` | 对应能力测试及 `test_semantic_oracle_boundary.py` |
| 身份、generation、观察帧读取 | `oracle/core.py` | `test_semantic_oracle_boundary.py` |
| 公共观察的页面/遮挡归属 | `oracle/surfaces.py` | `test_semantic_task_isolation.py` |
| 通用目标定位和最终输入 | `oracle/targets.py`、`oracle/actions.py` | `test_semantic_oracle_boundary.py` |
| 科研、委托、后宅等语义读写 | `oracle/research.py`、`commission.py`、`dorm.py` 等 | `test_semantic_oracle_<能力>.py` |
| 战役地图、准备、舰队 | `oracle/campaign_map.py`、`campaign_navigation.py`、`campaign_preparation.py`、`campaign_fleet.py` | `test_semantic_oracle_campaign_*.py` |
| 大世界 | `oracle/opsi_state.py`、`opsi_navigation.py`、`opsi_globe.py`、`opsi_storage.py`、`opsi_mission.py`、`opsi_resources.py`、`opsi_shop.py` | `test_semantic_oracle_opsi*.py` |
| ALAS 资源名称和任务端口 | `adapter/semantic/resources.py` 及对应能力模块 | `test_alas_adapter_<能力>.py` |
| 页面判断和点击的优先顺序 | `adapter/semantic/dispatch.py` | 对应页面、弹窗、任务隔离测试 |
| 通用页面和点击处理 | `adapter/semantic/dispatch_observation.py`、`dispatch_actions.py` | `test_alas_adapter_boundary.py` |
| 会话、runtime handle、帧刷新 | `adapter/semantic/session.py` | `test_adapter_session_runtime_handle.py`、`test_opsi_monthstart.py` |
| 单次 ALAS 任务结束、兼容性异常分类 | `adapter/task_lifecycle.py`、`adapter/semantic/core.py` | `test_adapter_task_lifecycle.py` |
| 会话的战斗和任务委派 | `adapter/semantic/session_combat.py`、`session_opsi.py`、`session_tasks.py`、`session_dispatch.py` | 对应会话和任务测试 |

## 共享状态和分派顺序

能力模块以显式 mixin 组合到原来的 `SemanticOracle`、`AlasSemanticAdapter`、
`AlasSemanticSession` 对象上。各模块共享该对象原有的帧、任务上下文和输入台账，
没有独立任务状态机，也不单独创建会话。ALAS 继续拥有选择任务、导航、重试、
战斗和结束判定。

`dispatch.py` 显式保留原判断顺序，包括顶层弹窗、任务上下文、包身份检查和最后
的通用分派。任务处理函数返回实际结果；仅在不负责当前资源时返回内部
`UNHANDLED`。`False` 表示已处理的阴性观察，不能当作“未匹配”继续尝试其他任务。

输入仍经过原有 package/PID、freshness、唯一目标、遮挡和后置条件检查。拆分不改变
截图边界刷新 immutable frame 的语义，不增加像素或通用坐标回退。

## 公共观察的故障隔离

`oracle/surfaces.py` 从已验证的语义帧中读取浅层 Unity 归属，供公共入口决定是否调用
某个能力的详细读取器。它不产生输入权限，也不维护任务状态机。

- 通用页面扫描看到消息框、月度重置舰队界面或剧情遮挡时，只隐藏下层页面；不会
  为判断一个无关页面而解析重置条件、兑换商店按钮或剧情选项。
- 舰队通知也在主界面快速判断之前遮住下层页面，交给 ALAS 原有关闭通知的分支。
- 奖励侧栏优先于仍挂载的主界面节点；关闭后重复的返回请求只在新鲜状态证明目标主界面
  已可操作时返回 `main/already`，不再点击已经卸载的侧栏。
- 月度兑换商店只在对应消息身份出现时接管 `POPUP_CONFIRM`，普通确认继续由原有
  任务处理。实际重置入口仍校验文本、generation、目标唯一性与可操作性。
- 当前 Raid 和会话中的战斗观察先检查对应归属，缺席时不调用详细能力读取器。
  页面扫描与战斗识别优先使用当前 ALAS 截图边界借出的不可变帧。
- 遮挡规则也匹配只发布根节点的界面，避免子节点尚未出现时点击下层页面。
- `GOTO_MAIN`、通用返回以及商店/通行证/档案被动观察先读取对应的原子入口，
  缺席时不进入详细解析。多条返回路径同时成立仍拒绝输入。
- 通用确认按消息所属功能选择解析器；确定归属后仍执行原有完整结构及输入校验。

这次改动覆盖上述公共入口，尚不代表所有任务具有完整的故障隔离。各任务仍共享
Adapter/Session 和同一个游戏进程，无法识别、无法安全返回的界面仍可能阻止后续任务。

`test_semantic_task_isolation.py` 使用离线故障注入验证无关读取器不被调用、同一会话
仍可扫描主界面、恢复后无需重建 Adapter，以及错误确认和真实遮挡不能取得输入权限。
这些结果属于离线契约验证，不增加实机任务支持等级。

## 任务结束与调度

补丁 `0510-semantic-task-isolation.patch` 在原版 `ALAS.run()` 外围调用
`semantic_task_scope()`；任务选择、失败间隔、导航、重启、成功判定仍由 ALAS 负责。

- 仅将 `AlasSemanticUnmapped`、`UnknownObservationError`、`UnsupportedPixelRead`
  转成该任务的“能力不可用”。ALAS 使用原有 `task_delay(success=False)` 延后任务，
  返回独立的 deferred 结果，不计成功，也不累加客户端崩溃次数。
- 成功、`TaskEnd`、兼容性失败及其他异常都会释放任务上下文、待执行意图、结果归属
  和借出的观察帧。动作台账、已消费额度、运行身份、输入 generation 失效记录与已完成
  回执保留；清理不会重新授予额度或让旧帧恢复有效。
- 身份、新鲜度、目标歧义、输入结果不确定及未分类实现异常保持原有失败路径。
  `GameNotRunningError` 等已有恢复异常仍由 ALAS 安排 Restart。

`scripts/python/verify_alas_task_isolation.py` 直接执行已应用补丁的 `run/loop` 函数体，
验证三次可选能力失败后独立任务仍执行，以及原有终止/恢复规则不变。详细验证范围见
[任务隔离报告](task-isolation-20260902.zh-CN.md)。

## 测试与验证记录

原来的两个大测试文件只保留共享 fixture 的兼容导入。测试用例位于同名前缀的能力
文件中；公共 fixture 位于 `tests/semantic_support/`，FakeOracle 的战役、大世界、
养成、奖励端口分文件维护。

例如，修改科研语义时先运行：

```powershell
$env:PYTHONPATH = 'python'
python -m pytest -q tests/test_semantic_oracle_research.py tests/test_alas_adapter_research.py
```

涉及公共输入分派、会话或累积改动时，再运行相关台账测试及 `python -m pytest -q tests`。
不需要为了纯 Python 代码搬移重建 Android 镜像或重新执行付费远程资格测试。

`semantic_sources.py` 统一枚举公共入口和拆出的实现文件。源码基线统计、台账静态检查
以及后续 live runner 的源码哈希使用该枚举，避免只检查已经变小的入口文件。
新记录继续保留原有入口哈希，并增加按仓库相对路径记录的模块哈希。历史 receipt、
patch series 和支持状态不因代码搬移而重写或晋级。
