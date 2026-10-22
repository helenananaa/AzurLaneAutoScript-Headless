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
| 当前游戏与 ALAS 活动身份绑定 | `oracle/activity_identity.py`、`archives.py`、`raid.py` | `test_dynamic_activity_identity.py`、`test_semantic_oracle_raid.py` |
| 战役地图、准备、舰队 | `oracle/campaign_map.py`、`campaign_navigation.py`、`campaign_preparation.py`、`campaign_fleet.py` | `test_semantic_oracle_campaign_*.py` |
| 大世界 | `oracle/opsi_state.py`、`opsi_navigation.py`、`opsi_globe.py`、`opsi_storage.py`、`opsi_mission.py`、`opsi_resources.py`、`opsi_shop.py` | `test_semantic_oracle_opsi*.py` |
| ALAS 资源名称和任务端口 | `adapter/semantic/resources.py` 及对应能力模块 | `test_alas_adapter_<能力>.py` |
| 页面判断和点击的优先顺序 | `adapter/semantic/dispatch.py` | 对应页面、弹窗、任务隔离测试 |
| 通用页面和点击处理 | `adapter/semantic/dispatch_observation.py`、`dispatch_actions.py` | `test_alas_adapter_boundary.py` |
| 会话、runtime handle、帧刷新 | `adapter/semantic/session.py` | `test_adapter_session_runtime_handle.py`、`test_opsi_monthstart.py` |
| 单次 ALAS 任务结束、兼容性异常分类 | `adapter/task_lifecycle.py`、`adapter/semantic/core.py` | `test_adapter_task_lifecycle.py` |
| 会话的战斗和任务委派 | `adapter/semantic/session_combat.py`、`session_opsi.py`、`session_tasks.py`、`session_dispatch.py` | 对应会话和任务测试 |

## 共享状态和分派顺序

截图边界仍采集并冻结一帧。UI 的文字、开关、图片及图片源元数据在实际消费时
分别解析，成功结果只缓存在该 `UiState` 内；不能把解析失败替换成空列表。
这允许坏图片不阻断只读文字的功能，同时保留输入所需字段的完整性检查。
共享包/PID、schema、代次、时效及无法归属的错误仍在采集边界拒绝。

`alas-headless.ui/v1` 可附带 `error_counts`，键为 `toggle`、`text`、`image`、
`shared`，保留原有总计 `error_count`；计数必须与总计一致。`shared` 或未知族的
非零错误仍影响整帧，已知族的错误仅在消费该族时拒绝。旧 observer 没有该字段且
总错误为零时继续兼容；旧版非零总错误不能凭空归属给某个字段族。对应验证在
`test_ui_family_isolation.py` 和 `test_observer_ui_error_attribution.py`。

### 可选 Lua 模型观察

`/v1/ui` 的 `shipyard_strengthen` 和 `activity_identity` 来自
`NativeLuaShipyardProbe.h`、`NativeLuaActivityIdentity.h`。它们只读取当前 Unity
主线程 Lua 状态中已经存在的原始表，不调用 Lua 函数、元方法或延迟加载器，不写游戏
状态。每个 reader 检查自己实际需要的 native 符号；Globe 使用的 upvalue、对象指针
等接口缺失，不会连带关闭不依赖这些接口的 Shipyard/Activity reader。

`shipyard_strengthen` 关联当前 `ShipBluePrintMediator` 选中蓝图、筛选结果及原有
模型中的进度、稀有度、免费追赶和购买数据。它只提供实际字段；Python 仍负责验证
所选舰船、当前窗口、资源授权和输入后置条件，不能把完整观察等同于购买许可。
可选 `gems_known`、`paid_gems`、`free_gems` 从同一 PlayerProxy 原始字段读取；
缺失不关闭此 reader 或独立导航。存量蓝图消费用它们证明钻石未变化，同时要求
库存精确减少、强化进度推进及金币/购买计数不变；最终完成读取不依赖动画中隐藏的
DEV 等级文字或数量面板。ALAS 的数量选择、确认循环和后续任务策略保持原样。

`activity_identity` 的 `archives`、`raids` 各有独立 `status`、数量和截断标记。
外层栈平衡成功不意味着两个族都可用；读取失败不会计入无关 UI 族的错误数。

- Archives 核对 `pg.re_map_template.all` 与已加载的 `pg.base.re_map_template`。
  未完整加载时只能报告该族不可用，不能从部分目录推断唯一活动。Python 用实际安装
  ALAS 的游戏语言标题与游戏活动名精确关联，仅处理已知的档案前后缀，然后读取游戏
  当前类别和 banner；不按文件夹日期、列表位置或相似图标猜测。旧条目保留已审阅
  的资源身份关联，完整动态目录可兼容同一活动的 banner 更新。
  列表移动中的卡片位置/几何观察不要求 Button 与 Image 已完全对齐；点卡仍要求
  唯一控件及精确相同边界。仅“尚未对齐”的输入前拒绝可有界重读，真正重复控件、
  遮挡和输入异常立即失败。半露卡片继续沿已证明列表滚动，不作为可点击目标。
  原生射线命中已确认时使用其证明的输入点；旧 publisher 没有射线字段时，使用
  已审阅 `bg/icon` 按钮当前矩形的内部中心，避免边缘 pivot 取整后落到按钮外。
  整数输入点仍须严格位于按钮内，明确未命中的射线结果不能走兼容分支。
  档案关卡列表同时识别旧 `float/levels/items` 和已支持的
  `LevelSelectSPFullUI/Battle/Nodes` 布局；后者复用 Event 的父节点、标题与次数解析。
  两种布局必须属于同一已识别页面，混合或未知容器不能授权关卡输入。
- Raid 用 `pg.m02.model.proxyMap.ActivityProxy.data` 中服务器创建的活动 ID，关联
  游戏配置的同一 ID、活动类型、`mark` 和 `page_core`。`raid_<mark>` 是动态连接键，
  无需为每个发布日期添加允许名单；存在于静态配置而未出现在 proxy 的旧活动不会
  被当成当前活动。完整读取后的空列表是正常的“当前没有该类活动”，不是读取失败。
- 未选中条目的类别/banner/layout 缺失只令该条目未知，不关闭整个目录。影响唯一
  身份的 ID、档案名或 Raid mark 缺失仍需局部拒绝。已识别的 Raid 目前仅复用已支持
  的界面结构；新布局需要新的 typed 端口，不能因为活动身份匹配就授权任意按钮。

活动过期、剩余次数、任务选择和战斗仍由游戏与原 ALAS 决定。身份观察和元数据匹配
不替代包/PID、freshness、不可变帧、目标唯一性、遮挡和输入后置条件，也不自动提高
任务支持等级。对应离线测试另见 `tests/cpp/native_lua_activity_identity_test.cpp`
与 `native_lua_shipyard_probe_test.cpp`；实机收据的覆盖范围单独记录。

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
