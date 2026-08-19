# ALAS Headless 配置项级支持矩阵

更新日期：2026-08-18
Headless 适配证据提交：`266a77f6ce760b2aed3c05739e0e78d77a9f88dc`
固定 ALAS 上游基线：`81ccf63b4540f00241628c82a58c02c7a2bb11af`

## 1. 目的与口径

本文档把 ALAS 设置侧栏中的全部配置面板、配置组和字段纳入 Headless 适配范围。它既是当前支持情况的盘点，也是后续补齐与验收的检查表。

当前快照共有：

- 60 个配置面板；
- 278 个唯一的非 `Storage` 配置字段路径；
- 48 个 `WarArchives.Campaign.Event` 档案活动值；
- 26 个 `Research.PresetFilter` 预设；
- 22 个包名和 72 个服务器选项。

“某任务默认配置跑过”不能推出该任务的所有配置均受支持。一个配置项只有同时满足以下条件，才可以从“部分”提升为“完整”：

1. 配置值能被读取、校验并传入原 ALAS 状态机；
2. 该值对应的页面状态可以通过允许的观察端口可靠识别；
3. 该值需要的点击、滑动、返回和恢复动作均有语义输入闭环；
4. 成功、无资源、不可用、超限和异常分支都能区分，并且未知状态 fail-closed；
5. 布尔项至少覆盖 `true/false`，枚举项覆盖每个值或有等价性证明，数值项覆盖 `0/边界/正常/超限`，过滤器覆盖命中/无命中/非法规则；
6. 有离线契约测试，并按风险补充受控实机证据；概率掉落、账号资源和日期条件不能用无限实跑代替确定性测试。

状态标记：

| 标记 | 完成度标注 | 含义 |
|---|---|---|
| `F` | ✅ 完整支持 | 面板内全部配置值和必要异常分支均已按本文口径闭环；Benchmark、Commission、GameManager、Restart 已达到此状态 |
| `L` | 🟢 主路径已完成，完整支持未完成 | 至少一条实机主路径闭环，但不代表组内所有配置值已闭环 |
| `P` | 🟡 部分完成 | 有实现或可到达部分页面，配置分支仍不完整 |
| `B` | 🧱 已到边界，尚未完成 | 已安全到达账号、资源、日期或观察能力边界 |
| `O` | 🧪 仅离线完成 | 只有离线契约、回放或桩验证 |
| `M` | 🔴 尚未完成 | 缺少任务级适配或关键语义端口 |
| `R` | ⚙️ 运行时待验收 | ALAS 内部/运行时管理字段；仍需验证调度与恢复契约 |

### 1.1 完成度汇总（2026-08-16 标注）

这里的“完成”严格指整块面板的全部配置值和必要异常分支均已闭环，不能用“默认路径跑过”替代。

| 完成度 | 数量 | 面板 |
|---|---:|---|
| ✅ 完整支持（`F`） | **6 / 60** | Benchmark、Commission、GameManager、Minigame、Restart、Reward |
| 🟢 主路径已完成、全配置未完成（`L`） | **11 / 60** | Daily、Dorm、Event、EventA、Exercise、Gacha、Main、Main2、Main3、Research、Tactical |
| 🧪 仅离线完成（`O`） | **9 / 60** | Awaken、Coalition、CoalitionSp、EventB、Guild、Hospital、PrivateQuarters、Raid、RaidDaily |
| 🟡 部分完成（`P`） | **14 / 60** | Alas、AzurLaneUncensored、Daemon、Event2、EventC、EventD、EventGeneral、EventSp、EventStory、Freebies、General、OpsiDaemon、OpsiGeneral、ShopOnce |
| 🧱 已到边界、尚未完成（`B`） | **17 / 60** | Hard、OpsiAbyssal、OpsiArchive、OpsiAshAssist、OpsiAshBeacon、OpsiCrossMonth、OpsiDaily、OpsiExplore、OpsiHazard1Leveling、OpsiMeowfficerFarming、OpsiMonthBoss、OpsiObscure、OpsiShop、OpsiVoucher、Shipyard、ShopFrequent、WarArchives |
| 🔴 尚未完成（`M`） | **3 / 60** | GemsFarming、Meowfficer、OpsiStronghold |

当前账本的功能证据基线为 `3d0f60c`，矩阵首次提交为 `e2fc2fe`；authoritative patch series 的成员数与哈希由校验器现场验证。离线通过不会自动提升任何实机复核栏。

### 1.1B 配置交互攻击矩阵（2026-08-15）

单字段离线回放并不自动证明多个设置同时出现时仍会在正确的 ALAS 所有权
边界拒绝。本轮新增 `tests/test_alas_configuration_attack_matrix.py` 与
`scripts/python/verify_alas_configuration_attack_matrix.py`，使用干净固定上游
`81ccf63` 运行以下确定性组合：

- Campaign/Fleet/HpControl/Submarine/Emotion 的 pairwise 覆盖为 **21** 行；
- Scheduler/EventGeneral/TaskBalancer/Optimization 的 pairwise 覆盖为 **18** 行；
- 固定种子 `0xA1A5C0DE` 再运行 **32** 次 `合法 -> 非法 -> 合法` 序列，验证拒绝
  后无 scope、状态或 authority 泄漏；
- **8** 个最小非法案例覆盖 bool 冒充整数、`NaN`/`Infinity`、未知枚举、错误区间和
  未接管的 active submarine。每个随机/序列失败都带固定 seed 与行号，可独立重放。

矩阵只组合确实位于同一调用链的字段：campaign patch 的四个 gate 仍按
`Campaign -> Fleet -> HpControl -> EnemyPriority -> Submarine -> pre-sortie`
顺序，`Emotion` 仍在原对象取得 config 前校验，Scheduler/EventGeneral 则保留原
排队、任务切换、持久化和循环。合法路径同时重放固定上游的 Scheduler、Fleet、
HpControl、Emotion、Submarine、EventGeneral/TaskBalancer 和 Optimization 原方法；
所有输入均为内存 fixture/recorder，mutation budget 为 `0`，不连接设备、不读取
framebuffer、不走 OCR/模板/裸坐标 fallback，也不提升任何字段的 live/action/
observation 状态。

### 1.1A 当前低风险候选完成审计（2026-08-15）

本轮再次逐项审计了所有仍未达到 `offline=complete` 的支持字段，以及
`Daemon.EnterMap` 这条看似只差输入、实则共享 campaign 生命周期的路径。
下列项目不是遗漏一个默认值或单一夹具；在当前固定上游、观察后端和零资源
预算条件下均应保持 fail-closed。未列出的字段要么已有离线契约，要么已经
明确为上游无能力/不可用配置。

| 字段/路径 | 已完成层级 | 当前阻塞与为何不安全地继续 | 明确重新进入条件 |
|---|---|---|---|
| `Daemon.EnterMap` | 双值校验、禁用不探测地图、启用时 MAP/FLEET 原始分派回放 | 语义 `MAP_PREPARATION`/`FLEET_PREPARATION` 输入必须绑定已有 `begin_campaign_pre_sortie(stage)` 上下文、退出证明和 sortie 预算；Daemon 没有可信 stage identity，直接放开会绕过共享 campaign 门禁 | 有独立的、无 stage 歧义的 daemon 地图/编队观察，及进入、取消、恢复的可回放 postcondition；实机仅在隔离账户/明确输入预算下验证 |
| `Campaign.Event`、`Campaign.Mode`、`Campaign.Name` | 原 `handle_stage_name()`、配置覆写和已适配的当前主路径 | 三字段横跨 16 个任务面板；`Name` 是动态输入，别名、活动目录、硬图回退、循环和任务内部覆写共同决定实际路由。通用白名单会错误拒绝原内部路径，宽松校验又无法 fail-closed | 按 Scheduler command 建立锁定的路由/别名清单，并为每类目录、模式、内部覆写和未知组合提供无输入回放与 typed 页面证据 |
| `Emulator.Serial`、`ScreenshotMethod`、`ControlMethod` | 配置读取、严格值域与现有语义适配 | 三值在 `Device.__init__` 连接建立阶段即被消费，早于语义会话；继续需要改变连接、断线恢复与资源释放的所有权，不能以运行中的账户/设备试错 | 专用可丢弃设备上的连接、截图、控制、重连和清理生命周期契约；每种声明方式都有失败注入与无遗留证明 |
| `EventStory.SkipBattle` | 故事入口观察；字段已确认是上游锁定但无消费者 | 固定上游无条件在剧情战斗时重启应用，`false` 没有原业务分支。自行添加继续战斗会重写 ALAS 状态机且需要战斗/结算观察 | 上游提供消费者，或单独批准并审阅的继续战斗状态机，加上多活动布局的战斗、结算和恢复夹具 |
| `Shipyard.BuyAmount`、`ShipyardDr.BuyAmount` | `0..15` 数量、两种价格表、余额等于/不足边界和 DR→PR 分派回放 | 大于 15 的数量没有 typed 数量/总价面板收据；真实购买会消耗物资，不能用猜测的上限或账号尝试填补 | 只读数量/总价/余额关联观察和 `>15` 夹具；若要做真实购买，另行取得明确资源预算授权 |
| `StopCondition.GetNewShip` | 普通掉落页关闭与其他停止条件回放 | 现有观察不能可靠区分普通 `GET_SHIP` 与首次获得 `NEW_SHIP`；误报会错误停止刷图 | 自然出现的首次获得样本，包含稳定层级/身份差异和停机后状态夹具；不通过刷图制造样本 |
| `Benchmark.DeviceType`、`Benchmark.TestScene` | 5×3 方法选择与非法配置入口拒绝 | 实机路径可能卸载、导航和调用多种传输；当前没有专用空白设备，不能在用户运行中的账号/GUI 环境触发 | 隔离设备、逐传输 capability 证明、计时收据与恢复/失败夹具；确认不会影响用户应用状态 |

因此本轮不以单次当前页、默认配置或桩内成功来抬高上述 `action`、
`observation` 或 `live` 维度；未知页面、过期观察和非法配置继续拒绝，资源
预算维持为零。

### 1.2 本轮 StopCondition 优先适配标注

本轮优先处理影响 17 个地图面板的安全停止条件。容易确定性复现的状态使用离线夹具和既有真实观察证据；需要等待账号概率或成长条件的实机项目按要求标注后跳过，不用无限刷图制造证据。

| 字段 | 本轮结果 | 确定性证据 | 仍未完成/本轮跳过 |
|---|---|---|---|
| `OilLimit` | 🟡 保留既有实现 | 全局油量已经是 typed 读取，原 ALAS 保留 `< max(500, OilLimit)` 停止与延迟逻辑 | 500 下限、等于边界和多个停止条件同时满足尚未形成独立实机记录 |
| `RunCount` | 🧪 **新增三主线实例回放** | Main/Main2/Main3 分别执行固定上游 `_run()`；覆盖 1 次、2 次、恢复余量 1 次、异常零扣次及无限次数有界运行，原 ALAS 仍拥有初始化、成功后减一、归零禁用和退出 | 真实设备上的 Main2/Main3 独立任务启动、跨进程恢复和多轮资源后置条件仍待复核 |
| `MapAchievement` | 🧪 **本轮新增 typed port** | 真实 12-4 语义快照已给出 `100%`、三个星标和“威胁排除”；离线覆盖达成、未达成、畸形百分比和星标缺失，原五枚举判断保持不变 | 普通主线以外的活动/SP/档案布局、五种枚举的逐项实机停止仍待复核 |
| `StageIncrease` | 🟡 可接收新的 typed 达成信号 | 原 ALAS 仍拥有下一关计算、关卡存在性检查、写回 `Campaign.Name` 和末关停用 | 跨 A/B 分区、自定义链、末关和中断恢复尚未逐值实机验证 |
| `ReachLevel` | 🧪 **本轮新增 typed port** | 已审阅 G25 六舰等级节点（真实值 `118/109/117/110/118/107`）；离线覆盖排序、1..125 范围和非法 126 fail-closed；原 ALAS 保留升级跨阈值判断 | 为制造升级而等待/刷经验的实机触发按要求跳过；自动寻敌与双舰队切换后的等级复核仍待做 |
| `GetNewShip` | 🧱 **明确跳过首次获得实测** | 普通 `GET_SHIP` 页面可由确定性夹具关闭并继续 | 当前观察数据没有能把“首次获得 `NEW_SHIP`”与普通掉落可靠区分的节点；不伪造 selector、不把普通掉落误报成停止条件，待自然样本出现后补证据 |

实际固定 ALAS 方法的确定性回放现覆盖 **79 条断言**（含 40 条 `MapAchievement` 真值表组合）。Main、Main2、Main3 各自绑定独立 Scheduler 命令和 `campaign_main` 路由，并共同完成 15 个 `_run()` 循环场景；静态与动态证据共同证明 `RunCount` 只在 `campaign.run()` 成功返回后、下一次停止检查前扣减，异常不多扣且无限次数不会扣减。因此 `OilLimit`、`RunCount`、`MapAchievement`、`StageIncrease`、`ReachLevel` 的确定性边界已经闭环；StopCondition 整组仍为 `P`，因为 `GetNewShip=true` 继续按要求跳过自然首次获得实测并 fail-closed。

### 1.3 本轮官方一键退役适配标注

`General.Retirement.RetireMode=one_click_retire` 已从历史像素路径提升为受权限预算约束的官方事务端口。2026-08-14 在 API 32 专用设备、国服 9.7.10 上实际退役 68 艘：船坞 `882/910 -> 814/910`，官方奖励为物资 1026、荣誉勋章 22；18 类共 113 件随船装备全部取消拆解并进入仓库。

| 字段/安全项 | 当前 | 已验证 | 仍未完成 |
|---|:---:|---|---|
| `Retirement.RetireMode=one_click_retire` | 🟢 | 官方选择、稀有角色二次确认、奖励、装备入仓库、返回和容量差全部闭环；返回实际 68，不再硬编码 10；无候选官方提示也已实机闭环 | 未知弹窗和重连后页面不一致仍拒绝继续 |
| `Retirement.RetireMode=enhance` | 🟡 | 已接入 ALAS 正式任务入口；三项详细配置、语义筛选/选舰/强化页导航、官方推荐、单次确认、真实素材数和装备入仓均有闭环证据 | 未为补证据额外执行完整 `favourite` 破坏性任务；自然无素材实机分支仍待遇到 |
| `Retirement.RetireMode=old_retire` | 🔴 | 保留原 ALAS 分支及离线分派证据；Headless 在任何页面事件前明确拒绝，没有伪装成已支持 | 任务级语义观察、选择、确认和结果校验均未适配 |
| `OneClickRetire.KeepLimitBreak=keep_limit_break` | 🟢 | 官方设置读回 `keep_needed`，本次 68 艘实退使用该值 | 其他服务器和上游版本仍需重验 |
| `OneClickRetire.KeepLimitBreak=do_not_keep` | 🧪 | 官方 `keep_none` 选项和离线设置动作已识别 | 该值会扩大退役集合，本轮未做第二次破坏性实退 |
| 唯一舰船保护 | 🟢 强制 | 每次事务要求官方 `唯一舰船退役保护=on`，缺失或无法设置即拒绝 | ALAS 当前无独立用户配置；Headless 不允许关闭此保护 |
| 稀有度优先级 | 🟢 强制 | 精确要求 `R -> SR -> N`；本次触发并处理官方“精锐以上”二次确认 | SSR 不在官方快速退役优先选项中，未知布局拒绝 |
| 随船装备 | 🟢 强制保留 | 先取消全部拆解，再确认“所有装备会放入仓库” | 当前不提供 Headless 自动拆装选项 |
| 无可退役候选 | 🟢 | 实机精确读到 `没找到符合条件的舰船`，容量 `814/910`、选择数 0，未点破坏性确认；阻止旧像素重试并交给人工处理 | 其他文案或选择数/容量变化一律拒绝 |
| 网络弹窗中断 | 🧪 | 仅允许既有精确 `NetworkDown/HostNotFound` 重连框，并在设置、选择、确认、奖励、装备循环内恢复 | 本轮未人为制造实机断网；未知弹窗 fail-closed |

因此 `General` 面板保持 `P`，不能升为 `L/F`：强化主路径已接入，但 `old_retire`、`do_not_keep` 的实际退役、完整 `favourite` 破坏性任务和自然无素材分支仍未全部闭环。实机收据见 `artifacts/retirement-live-20260814.json` 与 `artifacts/enhancement-live-20260814.json`。

### 1.4 本轮 Research 全配置确定性适配

本轮直接从固定/已打补丁的 ALAS 源树抽取并执行原 `Filter`、`FILTER_REGEX`、`research_sort_filter`、`_research_check`、`research_select` 和 `research_delay_check`，Headless 不另写科研选择或调度状态机。共 **83 条确定性断言**，覆盖 `PresetFilter` 的 26 个公开值、`CustomFilter`、`AllowDelay=true/false`，以及 Coin/Cube/Part 各四种资源策略（36 个策略组合）；同时覆盖首项/中间项命中、无命中、默认回退、非法 token、同权卡片顺序、资源充足/不足、队列满、延迟、重置前后和跨轮幂等。

语义模式新增两道动作前门禁：五张 typed 科研卡必须具有完整且唯一的槽位/Unity 身份，并且每张卡都能由固定上游 `ResearchProject` 解析；自定义过滤器中任何空 token、非法 token 或仅被上游宽松 `re.search` 部分匹配的 token 都会 fail-closed。回放 mutation budget 为 **0**，没有启动科研、重置、资源消费或 Android 输入。因此六个 Research 配置字段的 `offline` 维度提升为 `complete`，既有 observation/action/live 维度不因离线证据而提升，Research 面板仍保持 `L` 而不是 `F`。

2026-08-18 的当前账号复验补齐了离开队列前的 typed 容量快照、五类部件名称到精确物品 ID 的确认映射，以及原 ALAS 已选位置与新鲜项目代码的双重校验；后者允许安全处理同一批次两张 `S9 C-153-MI`，但位置或代码任一变化仍会拒绝输入。受限运行启动两项金币科研（合计 8,000 金币）、一项魔方科研（3 魔方）、一项零件科研（鱼雷部件 T1×20）和一项无资源科研；Coin/Cube/Part 的三个 `do_not_use` 路径均没有消耗资源。最终源码绑定的 `AllowDelay=true` 回执覆盖无匹配、强制回退、重名卡选择、无资源启动及调度恢复，但当前资源充足，未触发“资源不足后等待”判定。五格队列已满，最早项目约在 2026-08-19 01:44 完成，因此 Research 保持 `L`，资源回执在最后一次位置接口变更后仍按阶段证据处理。

### 1.5 本轮 Scheduler 六字段跨任务契约

固定上游 `args.json` 中共有 **50 个面板**引用同一个六字段 Scheduler。校验器逐面板证明 `Enable/NextRun/Command/SuccessInterval/FailureInterval/ServerUpdate` 字段集合完整、`Command` 自识别，并按启用默认值、成功/失败间隔和服务器刷新表生成 **15 个等价类**；每个面板都明确列入一个类，不从单一任务样本直接外推。

离线回放直接抽取固定/已打补丁上游的 `Function`、`Filter`、`get_next_task`、`task_delay`、`ensure_time`、`get_server_next_update` 和 `nearest_future`，使用冻结时钟和临时内存配置完成 **19 条契约断言**：启用/禁用、合法/非法 datetime、固定/区间间隔、跨日及正负服务器偏移、成功/失败、跨任务写入、重复恢复、持久化 `NextRun`、override 重绑保留和无调度环。Headless 只在原 `get_next_task()` 排队前增加全量六字段 fail-closed 校验；调度优先级、延迟选择、持久化和循环仍由原 ALAS 拥有。本轮没有运行真实账号任务队列或注入 Android 输入，因此六字段仅把 `offline` 提升为 `complete`，既有 `live=partial` 保持不变。

### 1.6 本轮 Fleet 九字段确定性分类

固定/已打补丁 ALAS 的九个 `Fleet` 字段现由 **68 条确定性断言**完整分类。`Fleet1=1..6`、`Fleet2=0..6` 和两组 `Step=2..5` 均通过纯配置门禁，并直接回放原 ALAS 的 Boss 舰队、当前舰队与反转舰队分支。两组 `Formation` 经全量 Python AST 读取审计确认在固定上游原业务/状态机中没有运行时消费点；新加的有界导航前门禁是补丁中的唯一读取。除现有 `double_line` 基线外的两个值会在导航前明确拒绝，不再让用户误以为设置生效。

五种战斗模式均已分类，但只有 `combat_auto` 具有已审阅语义动作；其余模式依赖方向长按或武器释放，继续 fail-closed。四种 `FleetOrder` 的原 ALAS Boss 路由均完成离线回放，但当前语义出击只放行已有实机证据的 `fleet1_mob_fleet2_boss`。配置门禁在 `begin_campaign_pre_sortie()` 前执行，mutation budget 为 `0`，不连接设备、不注入 Android 输入。九字段只将 `offline` 提升为 `complete`；观察、动作和实机仍为部分支持，面板状态不提升为 `F`。

### 1.7 本轮 Mail 四字段全组合离线分类

固定/已打补丁 ALAS 的 `Mail.ClaimMerit`、`ClaimMaintenance`、`ClaimTradeLicense` 与 `DeleteCollected` 已覆盖全部 **16 个布尔组合**。回放直接执行原 `MailWhite.run()`；页面导航与最终 `mail_claim()` 被输入为空的记录桩替换，证明有领取类别时四个值原样传递，无领取类别时保留原提前返回，其中“仅删除”为真仍不会进入页面。四种代表性非布尔值在取得流程所有权和导航前 fail-closed。

本轮 mutation budget 为 `0`，没有连接设备、领取邮件、删除邮件、确认弹窗或注入 Android 输入。四字段只将 `offline` 提升为 `complete`；既有邮件动作仍需显式、有限预算，观察、动作和实机维度保持 `partial`，`Freebies` 面板仍为 `P`。

### 1.8 本轮 HpControl 八字段确定性分类

11 个普通/活动地图面板共享的八个 `HpControl` 字段现已完成离线逐类验证。四个阈值只接受有限的 `0..1` 比率，并覆盖 0、默认值、1、越界、非有限数、错误类型与布尔混入；`HpBalanceWeight` 精确要求三个正整数，同时直接执行原 `hp_get()` 证明中文逗号归一化和 `0.9/0.8/0.7 -> 0.9/0.4/0.175` 的权重结果。回放还直接执行原 `_expected_scout_order()`、`hp_retreat_triggered()` 与 `handle_emergency_repair_use()`，覆盖编队顺序、严格小于阈值及最终维修输入边界。

三个启用值均被分类但不会放行：`UseHpBalance=true` 最终仍是坐标拖拽，`UseEmergencyRepair=true` 仍依赖未审阅战斗模板/输入，`UseLowHpRetreat=true` 会进入尚未接管的撤退循环。门禁在 `begin_campaign_pre_sortie()` 前运行；默认三个开关均为 false 时继续使用原 ALAS 状态机。mutation budget 为 `0`，没有设备连接或 Android 输入。因此八字段只把 `offline` 提升为 `complete`，已有 observation/live 记录不扩张，action 仍缺失，相关面板不能升为 `F`。

### 1.9 本轮 TaskHoardingDuration 调度时间契约

`Optimization.TaskHoardingDuration` 现直接对照原 ALAS `hoarding` 属性与既有 Scheduler 回放，覆盖 `0/1/15/1440` 整分钟；负数、超过一天、小数、字符串、布尔、缺失及畸形结构在 `get_next_task()` 时间运算前 fail-closed。一天上限是 Headless 为避免误配置造成长期任务推迟而设置的明确安全边界。原 ALAS 继续拥有 pending/waiting 分类、优先级、`is_hoarding_task` 状态、`NextRun` 调整、持久化和循环；本轮没有运行真实账号队列或注入 Android 输入，因此只提升该字段的 `offline` 维度。

其余三个 Optimization 运行字段已在 1.35 节完成原方法离线回放；它们仍缺跨后端 frame-clock、长等待恢复和包进程租约实机证据，因此这里只声明离线完成，不扩张 live/action。`Emulator.ScreenshotDedithering` 对 Headless 语义截图仍无运行时效果，明确不做隐藏像素回退。

### 1.10 本轮 EnemyPriority 三值目标排序契约

`EnemyPriority.EnemyScaleBalanceWeight` 的三个公开值现已在 11 个共享地图面板进入导航前门禁。回放直接执行固定上游 `Map.clear_enemy()` 与 `Map.clear_filter_enemy()`：同一组原生 `GridInfo` 敌人格中，`default_mode/S1_enemy_first/S3_enemy_first` 分别选择 C1/B1/A1；两种显式优先级会按原实现覆盖活动过滤字符串。另覆盖同星级多目标按 weight/cost 排序、无敌人格返回 false，以及空值、大小写错误、未知值、非字符串和布尔值拒绝。

源码审计固定了 `clear_chosen_enemy`、普通选敌、道路阻挡、潜在道路阻挡及过滤选敌五个运行时消费点。七次目标选择仅在原 `clear_chosen_enemy()` 最终输入边界记录，不连接设备或点击地图。后续真实输入仍必须通过现有格子身份、raycast、快照新鲜度、动作预算及后状态证明，因此本轮只把该字段的 `offline` 维度提升为 `complete`，不能据此扩大 action/live 或把相关面板称为完整支持。

### 1.11 本轮 Emotion 十一字段时间账本契约

17 个普通地图、活动、Raid、Coalition 与 Hospital 面板共享的 11 个 `Emotion` 字段现由中心 `Emotion.__init__()` 门禁统一校验。三个公开模式完整保留原 `is_calculate/is_ignore` 真值；Hard 任务内部使用的 `nothing` 覆盖单独允许，但不伪装成第四个公开配置值。两舰队分别覆盖 `0..150` 心情值、2000..2100 的无时区记录时间、四种控制阈值、三种恢复位置及誓约 true/false。

离线回放直接执行原 `FleetEmotion`/`Emotion`：48 组速度/阈值/上限映射、已过与未来记录时间、四种 FleetOrder 的预计消耗向量、进入前双倍书、无需睡眠的已恢复等待，以及战后扣减记录。`keep_exp_bonus + not_in_dormitory` 会在原版稍后请求人工接管，现提前 fail-closed；另有九类非法值被拒绝。记录与任务延迟只写入内存桩，没有真实 sleep、调度持久化、宿舍操作、账号资源变化或 Android 输入，因此只提升 11 字段的 `offline`，不扩大 observation/action/live。

### 1.12 本轮 Submarine 四字段非活动面契约

12 个普通/活动地图面板共享的 `Fleet/Mode/AutoSearchMode/DistanceToBoss` 已进入出击导航前门禁。`Fleet=0` 时，五种模式、两种自动寻敌角色与四种 Boss 距离的 40 个组合保留原 ALAS 惰性语义；`Fleet=1/2` 会进入尚未接管的潜艇编队选择、策略栏、地图移动或战斗呼叫，因此两者均在导航前明确拒绝。GemsFarming 的 UI 只暴露 `do_not_use/hunt_only`，其余 11 面板暴露完整五模式，不能互相外推。

回放直接执行原战斗呼叫判断、Boss 专用模式映射、两种自动寻敌设置及四种距离规划。同一原生地图夹具上，贴 Boss、1 格、2 格分别选择 `(5,5)/(4,5)/(3,5)`，开放海域支援不移动；两个活动战斗呼叫只捕获最终输入边界，没有点击。另覆盖六类非法值与十个活动舰队/模式拒绝案例。因此四字段只提升 `offline`；没有潜艇编队、策略栏、移动、呼叫按钮或实机结果闭环，不能称为活动潜艇支持。

### 1.13 本轮 EventGeneral 与 TaskBalancer 五字段契约

`EventGeneral.PtLimit/TimeLimit` 与 `TaskBalancer.Enable/CoinLimit/TaskCall` 已在原 `CampaignEvent` 的 PT、时间、金币判断和任务切换方法入口统一校验。PT 支持非负整数及固定上游会归一化的中英文标点格式；时间只接受 2000..2100 的无时区 datetime；金币阈值有明确非负上限；目标任务严格为 Main/Main2/Main3。冻结时钟回放覆盖 PT 的 0/未达/等于、默认/未来/过期时间、非活动任务与 GemsFarming 主线豁免，以及金币 OCR 为 0、低于、等于、非 balancer 任务。

回放还执行原活动任务禁用、GemsFarming 重置、TimeLimit 重置，以及三个目标任务严格的 `task_delay(5) -> task_call -> task_stop` 顺序；所有写入只落到内存桩。静态审计固定 campaign、coalition、raid、hospital 和 auto-search combat 的消费文件。当前缺口是页面特定的 typed PT/金币观察、服务器时间与本机 naive datetime 的实机相关性、任务切换后的恢复收据和防调度环证据；在取得这些条件前 observation/action/live 保持 missing，EventGeneral 面板仍为 P。

### 1.14 本轮 Campaign Clear Mode 共用开关契约

`Campaign.UseClearMode` 在 16 个普通、活动、共斗、突袭、档案和每日地图面板共用同一声明。现在原 `FastForwardHandler.handle_fast_forward()` 在修改地图能力标志前先执行严格布尔校验；`0/1`、字符串和空值均不会被当作布尔值放行。

内存回放直接执行原方法的无 Clear Mode、显式关闭、开启、`MAP_CLEAR_ALL_THIS_TIME`、开关未变化和开关变化六类路径，并核对十个地图特性关闭、自动寻敌与 2x 书传播、`on/off` 请求和动画等待。没有调用真实 `FAST_FORWARD` 控件或 Android 输入；因此只把该字段的 offline 提升为 complete。缺少的仍是 Clear Mode 开关自身的 typed 状态/输入端口、切换后稳定 postcondition，以及不可用关卡上的实机拒绝证据。

### 1.15 本轮 Tactical 经验溢出与新学员八字段契约

`ControlExpOverflow.Enable/T1Allow/T2Allow/T3Allow/T4Allow` 与 `AddNewStudent.Enable/Favorite/MinLevel` 现在会在原 ALAS 的经验书过滤、领取循环和学员选择方法入口 fail-closed。离线契约覆盖 34 个合法配置和 12 个非法值：四档允许溢出量必须是 `0..5800` 的精确整数，学员等级接受 `1..125` 及可规范化的十进制文本；布尔值、非十进制文本及越界值均拒绝。

回放直接执行原 `_tactical_books_filter_exp()` 的等级 10 边界：关闭时只保留特殊 100 经验书，开启时逐档保留配置边界并排除越界书，技能未满时九本夹具全部保留。`Favorite` 会在读取候选前调用既有的精确共享 Dock 收藏切换。真机已完成 disabled 的不变性验证，以及两个 enabled 运行：收藏和非收藏范围各产生不同候选集，分别选择 204044 与 306064，并执行原 ALAS 的技能、书本和唯一课程确认。确认后的 Unity 卡片树会在同一根上保留旧身份；按物理槽位边界解析后，两个后置回执均证明选中舰船处于运行中的课程。故 `AddNewStudent.Enable/Favorite/MinLevel` 已五维完整。

2026-08-18，领取三门完成课程后，小声望的“小骑士的射击训练”处于 Lv.9、`5750/5800`。关闭溢出的原方法把 11 本真实库存过滤为两本基础 100 经验 T1，未消耗开课授权；开启并设置 `T1=100/T2=250/T3=750/T4=1450` 后，150/300/800/1500 经验的对应教材均按精确边界重新放行。最终原任务选中 `Blue_T4`，发出唯一 `tactical/course/confirm`，授权归零并留下约 12 小时运行卡；因此 `ControlExpOverflow` 五字段达到五维完整。证据为 `integration/alas/tactical-overflow-strict-live-validation-receipt.json`、`integration/alas/tactical-overflow-live-validation-receipt.json` 与 `integration/alas/tactical-overflow-postcondition-live-validation-receipt.json`。

### 1.16 本轮 Tactical 选书优先级与快速学习槽位契约

`Tactical.TacticalFilter` 现在只接受原 ALAS 的完整 token 语法：可选 `Same`、颜色、T1-T4，以及 `first` 回退；兼容原过滤器支持的 Unicode 分隔符和连字符。空 token、尾随垃圾、只被非锚定正则部分匹配的值、空过滤器和非文本值会在读取书本前 fail-closed。固定上游回放直接执行原 `_tactical_books_choose()`，覆盖同色、颜色+等级、仅颜色、仅等级、`first`、无匹配取消及 Unicode 规范化七类排序，保留 ALAS 的首本聚焦、最终开始/取消和状态机所有权。

`Tactical.RapidTrainingSlot` 严格限定 `do_not_use/slot_1/slot_2/slot_3/slot_4`。原 `handle_rapid_training()` 回放验证四个精确槽位偏移、按钮不可用返回 false，以及只有命中后才执行的 interval clear。十字段 Tactical 合并回放现有 45 个合法配置和 20 个非法配置。

2026-08-17，原始 Tactical 任务在实机加载 `BlueT1 > RedT1 > YellowT1 > BlueT2 > RedT2 > YellowT2 > first`，对 11 本真实库存排序并选择第 9 格 `Blue_T1`，随后以一条 typed `tactical/course/confirm` 输入开课。输入预算耗尽后，第 4 槽确认处于运行中（舰船 `102011`、技能“快速装填”）；完整收据见 `integration/alas/tactical-filter-r1-live-validation-receipt.json`。因此 `Tactical.TacticalFilter` 达到五维完整支持；当前只剩限时活动快速学习槽位未完成。

2026-08-19 的恢复矩阵还覆盖了已完成课程领取后的两种官方“继续学习”文案、`ConnectionReset` 精确重连、从三槽运行到第四槽开课，以及四槽全满时零预算、零 Dock/选船/教材输入且槽位身份不变；收据为 `integration/alas/tactical-empty-slot-fill-r4-live-validation-receipt.json` 与 `integration/alas/tactical-full-slot-r5-live-validation-receipt.json`。这不改变面板分类，唯一剩余项仍是当前非活动期无法出现的 `RapidTrainingSlot`。

### 1.17 本轮 EventA-D 每日关卡轮转契约

`EventDaily.StageFilter` 现在与当前 `Scheduler.Command` 严格绑定：A1-A3、B1-B3、C1-C3、D1-D3 各自所有非空有序子集均合法，并保留原过滤优先级；跨分区、重复、空 token、第四关、尾随垃圾和非文本值会在枚举活动脚本前 fail-closed。`LastStage` 只接受数值 `0` 或当前分区 1-3 关。门禁特意保留在原服务器日界判断之后：过期的异常游标仍由 ALAS 先重置为 `0`，未过期的跨分区游标则在运行关卡前拒绝。

固定上游回放直接执行原 `CampaignABCD.run()`，覆盖 76 个合法、48 个非法契约案例，以及四分区优先级、游标后续恢复、游标被过滤时从头开始、缺少脚本、无匹配时禁用并停止、`TaskEnd`、未解锁关卡请求人工接管和过期游标自愈。没有进入关卡、消耗油量或注入 Android 输入；两字段只从 `offline=partial` 提升为 `complete`，既有 observation/action/live 不变。

### 1.18 本轮 Daily 十四字段配置契约

Daily 组的 7 个关卡选择、6 个舰队选择和 `UseDailySkip` 现在会在原 `daily_run()` 前整组 fail-closed。五类普通日常严格接受 `skip/first/second/third`，普通与限时兵装开发只接受 `skip/first/second`，舰队只接受精确整数 1-6，快速跳过只接受布尔值。文本数字、布尔舰队、越界舰队、大小写或带空白的近似枚举都不会进入原状态机。

固定上游回放执行原 `get_daily_stage_and_fleet()`、`daily_enter()`、`daily_run_one()` 和 `run()`，覆盖普通及限时兵装两种 1-7 位排列、快速跳过与普通作战控件选择、破交作战 fleet=0 特例、关闭快速跳过时的安全略过、任务未激活和剩余次数为 0。64 个合法和 80 个非法单字段案例均通过，mutation budget 为 0，没有调用 `daily_execute()` 的真实实现、进入战斗、消耗次数或注入 Android 输入。十四字段只提升 `offline`，原 observation/action/live 证据不外推。

### 1.19 本轮 Hard 关卡与舰队契约

`Hard.HardStage` 现在绑定固定上游实际存在的 64 个主线地图模块，即 1-1 至 16-4，并兼容原转换器接受的 `campaign_11_4`、`11_4` 和空白写法后规范为 `11-4`。不存在的章节/小节、部分匹配、非文本值会在开启语义预出击 scope 或加载地图前 fail-closed。`Hard.HardFleet` 只接受精确整数 1/2，分别保留原 `fleet1_all_fleet2_standby` 与 `fleet1_standby_fleet2_all` 覆盖。

固定上游回放执行原 `CampaignHard.run()` 和 `_run_hard()` 的地图加载、模块导入、MAP 赋值、UI 关卡名、剩余次数循环、自动寻敌退出、次日调度与 Reward 调用顺序。68 个合法和 17 个非法案例通过，mutation budget 为 0；地图导入、设备、OCR 和 campaign run 都由夹具替代，没有进图、战斗、次数消耗或 Android 输入。两字段只提升 `offline`，11-4 当前账号路径仍不能外推到 64 关实机可用。

### 1.20 本轮免费补给包开关与星期契约

`SupplyPack.Collect` 现在只接受布尔值，并在原 Freebies 流程调用 BattlePass、DataKey 或 Mail 前 fail-closed；关闭时仍保留 Mail 和任务次日调度，开启时才进入原 SupplyPack 模块。`DayOfWeek` 只接受精确整数 0-6，继续使用 ALAS 原 Monday-zero `server_today >= target` 比较，文本数字、布尔值、浮点和越界值会在页面导航前拒绝。

固定上游回放执行原 `Freebies.run()` 和 `SupplyPack.run()`，覆盖开关两值、七个目标星期、星期三前后边界及油量恰好 21000 的保护分支，共 14 个合法和 10 个非法配置案例。真实 `supply_pack_buy()` 从未调用，只记录原状态机是否会产生免费包候选；mutation budget 为 0，没有领取物品、页面输入或 Android 注入。因此两字段只提升 `offline`，当前页面无免费项的实机记录不能称为成功领取闭环。

### 1.21 本轮 Reward 五开关契约

`Reward.CollectOil`、`CollectCoin`、`CollectExp`、`CollectMission` 和 `CollectWeeklyMission` 现在只接受精确布尔值。原 `Reward.run()` 在页面导航和领取前验证全部五字段；共享这些配置的 `RaidDaily.run()` 也在 EX 奖励路径前验证同一字段面，避免只守住普通 Reward 入口。

固定上游回放覆盖全部 32 种合法开关组合和 20 个非法单字段案例，执行原 Reward 参数转发与调度尾部、RaidDaily EX 下 `CollectMission` 的真假转发，以及非 EX 绕过。该回放本身的 mutation budget 为 0；随后五个字段分别取得原始 ALAS 的开启/关闭实机收据，正向领取均使用精确语义输入并回读后置状态。`Reward` 五开关现在完整支持。

### 1.22 本轮 Campaign 四个共享开关契约

`Campaign.UseFleetLock`、`UseAutoSearch`、`Use2xBook` 和 `AmbushEvade` 现在只接受精确布尔值，并在原 `CampaignRun.run()` 第一条语句统一校验。非法值会在关卡名转换、地图模块加载、页面导航和语义预出击 scope 之前 fail-closed；该入口覆盖 16 个普通、活动、共斗、突袭、档案和每日地图面板。

固定上游回放覆盖全部 16 种合法组合和 24 个非法单字段案例，执行原快速前进中的自动寻敌/2x 书选择、舰队锁定开关，以及伏击时规避/迎战分支。开关控件和伏击处理均由确定性夹具代替，没有调用真实地图方法、进入战斗、消耗 2x 书、页面输入或 Android 注入，mutation budget 为 0。因此四字段只提升 `offline`；真实控件后置条件、非周回地图、控件不可用、伏击观察及规避失败仍未闭环，`Name/Event/Mode` 的动态路由也不在本批范围。

### 1.23 本轮 Data Key 两开关契约

`DataKey.Collect` 和 `DataKey.ForceCollect` 现在只接受精确布尔值，并在原 `Freebies.run()` 开始处、BattlePass/DataKey/Mail/SupplyPack 任一子模块运行前 fail-closed。关闭 Collect 时仍保留 Mail 和次日调度；ForceCollect 只保留原容量已满时继续产生领取候选的语义。

固定上游回放覆盖四种开关组合和 12 个非法单字段案例，并执行原 `DataKey.data_key_collect()` 的已领取、容量恰好已满且不强制、已满且强制、尚余一格四个边界。真实 `_data_key_collect()` 循环从未调用，mutation budget 为 0，没有领取档案密钥、处理上限弹窗、页面输入或 Android 注入。两字段只提升 `offline`；现有 300/300 实机观察不能外推为强制领取、领取收据、上限弹窗或库存变化闭环。

### 1.24 本轮 GameManager 重启开关契约与 EventStory 跳过记录

`GameManager.AutoRestart` 只接受精确布尔值，并在原任务停止应用前 fail-closed。固定上游回放覆盖普通/语义两种后端与真假开关，并证明停止、重启和登录异常都执行 semantic session 清理。2026-08-16 在 API 32 x86_64 专用 AVD 上完成 false 运行中停止、false 已停止幂等、两轮连续 PID 冷启动、包禁用启动失败、ADB 传输停止失败、真实断网登录失败、故障恢复及未缩短的 600 秒 observer 启动超时。GameManager 新增 `finally` 清理后，所有成功/失败案例均以零 ADB observer forward 遗留结束；最终恢复到 PID 21799、前台 MainActivity、ANGLE 驱动和 `status=ok` 新鲜观察。该字段在已限定的 CN x86_64 语义运行时配置内达到五维完整支持，详见 [冷启动验证报告](game-manager-cold-start-validation-report.md)及机器可读收据。

`EventStory.SkipBattle` 本轮明确跳过而不提升：固定上游最终配置把它锁为 true，但运行时代码完全不读取该字段，并在剧情战斗处无条件重启应用。支持 false 需要上游提供或单独评审一套继续战斗状态机，以及覆盖代表性活动布局的确定性战斗/结算观察；当前只有故事节点语义适配，强行补分支会重写业务状态机。重新进入条件是获得该原始行为和可回放的战斗、结算夹具。

### 1.25 本轮 Benchmark 设备类型与测试场景实机矩阵

`Benchmark.DeviceType` 只接受固定上游声明的五种设备类型，`Benchmark.TestScene` 只接受 `screenshot_click/screenshot/click`，并在原任务卸载应用、导航或调用任一测速方法前 fail-closed。普通后端回放完整覆盖 5 x 3 组合并执行原 `get_test_methods()` 的 SDK 30 候选过滤，包括 Plone 去除 `ADB_nc` 与 VMOS 改用 aScreenCap/Hermit 的差异；语义后端保留观察、输入或二者组合的原场景选择，但不把旧设备类型伪装成语义测速差异。

12 个非法单字段输入都在入口事件前拒绝。实机回执 `integration/alas/benchmark-live-validation-receipt.json` 逐组运行五种 DeviceType 与三种 TestScene；每组保留原 15 次计时、返回所选的零或一条 observer/settings-round-trip 测量、确认回到主页并删除临时配置，15/15 通过、累计 218.342 秒。DeviceType 的实机结论是 Headless semantic 后端对全部声明值的绑定和验证，不宣称本设备具备旧 Plone、云端或 VMOS 传输；在该适配边界内两字段均为完整支持。

### 1.26 本轮 Dorm 收取、喂食与食物优先级契约

`Dorm.Collect` 与 `Dorm.Feed` 现在只接受精确布尔值，`Dorm.FeedFilter` 接受固定上游六种食物值的任意非空、无重复排列或子集，并保留 ALAS 对空白及 Unicode 大于号分隔符的规范化。空项、重复项、未知食物、前导零、尾随字符和除原 `ConfigUpdater` 数字 textarea 兼容值以外的非字符串会在 `RewardDorm.run()` 第一条可执行语句 fail-closed，早于语义 scope、页面导航、收取或喂食；该兼容路径也只接受六种精确食物数值。

回放覆盖 1,956 种食物优先级和四种收取/喂食开关组合，共 7,824 个合法配置；原状态机仍拥有“全关则禁用并停止”、其余组合的 `dorm_run` 分派和三舰 417 分钟调度。食物边界保持严格 `fill > food`、首选食物为空时回退以及无可用食物不操作。22 个非法单字段案例均在入口事件前拒绝，mutation budget 为 0，没有领取奖励、消耗食物、导航、截图/OCR 或 Android 输入。

2026-08-17 的原 ALAS 实机矩阵完成了 `Dorm.Feed` 的两条布尔路径：启用的默认优先级运行只发出动态计划的 typed 食物输入、耗尽授权并以精确库存差闭环（`integration/alas/dorm-feed-r10-live-validation-receipt.json`）；禁用运行成功且没有任何喂食输入（`integration/alas/dorm-feed-r11-disabled-live-validation-receipt.json`）。自定义单值 `Dorm.FeedFilter="1000"` 同样通过真实 ConfigUpdater→RewardDorm 路径，它在该路径中会规范为整数，实机仅点击 `dorm/feed/item/50001` 一次，库存 `17863→17862`、食物 `38760→39454` 并回到主页（`integration/alas/dorm-feed-r13-filter-1000-live-validation-receipt.json`）。2026-08-19 在食物槽 `0/40000` 的实机状态下，单值 `Dorm.FeedFilter="20000"` 由原任务进入喂食页后精确识别库存为零，零 typed 食物输入、六档库存不变并恢复主页（`integration/alas/dorm-feed-r14-filter-20000-no-stock-live-validation-receipt.json`）；实际消耗 20000 食物的正向后置条件仍需账号先取得至少一个该食物。2026-08-18 当前账号出现真实可领取奖励后，启用收取的原任务只消耗一次 `dorm.collect` 授权，后置快照证明精确收取控件由有变无、六个宿舍槽位不变且主页恢复（`integration/alas/dorm-collect-live-validation-receipt.json`）。连同全部 1,956 个原状态机过滤器回放、每张卡片读写边界的新鲜帧证明和非法值零输入契约，`Dorm.Collect`、`Dorm.Feed` 与 `Dorm.FeedFilter` 均达到五维完整支持。

### 1.27 本轮 Commission 预设、自定义规则与重大委托契约

`Commission.PresetFilter` 现在只接受六个声明值，`DoMajorCommission` 只接受精确布尔值，`CustomFilter` 接受原 ALAS 的类别、类型、时长与 `shortest` 语法，并保留空白、Unicode 大于号和 Unicode 连字符规范化。三字段在原 `run()` 文档字符串后的第一条可执行语句统一校验，空项、畸形项、未知项和错误类型会在语义 scope、奖励处理或委托派遣前 fail-closed；原代码对未知预设静默回退 cube 的行为只作为回放证据保留，无法通过受保护入口。

离线回放覆盖六预设的日/夜 12 种解析：cube/chip/oil 夜间切换对应 night 规则，两个 24h 预设不切换，custom 始终使用自定义规则。固定上游九个规则源全部通过原 `Filter`，覆盖 53 个唯一 token、代表性优先级和 Unicode 规范化；16 个有效性、状态、类别和重大委托开关组合保留原 `_commission_check` 决策。12 个预设/重大开关组合与 22 个非法单字段案例 mutation budget 为 0，没有领取奖励、启动委托、截图/OCR 或 Android 输入。

2026-08-16 实机补齐三字段的 live/action/observation：六个预设分别完成真实 ALAS 动态列表单轮，custom 使用 `major > daily-resource > shortest`，重大委托开关 `false/true` 各完成一轮。真实启动覆盖零油和非零油，`高阶自主训练` 精确确认 `1200` 油提示并进入运行态；运行委托完成精确取消，随后由完整 ALAS 单轮重新补位。列表重排后的目标按名称、等级、时长、状态和类型重新绑定，最终 4/4 运行且连续调度稳定指向最早完成时间。结合既有非法规则、日夜解析、空列表、奖励与无资源契约，Commission 三字段及面板提升为 `F`。

### 1.28 本轮 Exercise 已消费配置与无效等待字段审计

`Exercise.ExerciseStrategy` 只接受固定上游声明的八种策略，`OpponentChooseMode` 只接受四种选敌模式，`OpponentTrial` 只接受精确正整数，`LowHpThreshold` 限定为 `0..1`，`OpponentRefreshValue` 限定为整数 `0..6`，`OpponentRefreshRecord` 限定为 2000-01-01 至 2100-01-01 的 naive datetime。六字段在原 `Exercise.run()` 第一条可执行语句统一校验，早于进入演习页、读取对手或发起战斗。零值试探、布尔伪装数值、非有限阈值、越界刷新数、带时区/越界记录、未知枚举和畸形输入均 fail-closed；原代码把零次试探修正为一次的行为仅作为不可达兼容证据记录。

固定上游回放覆盖八策略在 0..60 小时的 488 个剩余次数决策，保留 hour 0 的原始 truthiness 边界和周五至周日各消费窗口；四种模式保留原对手排序、`leftmost` 跳过舰队详情读取和运行时分派；试探次数覆盖 1/2/3 次在各成功位置及全部失败时的边界。冻结服务器日期覆盖刷新值 0..6 的同日恢复、前一天/未来一天记录归零和五次任务内递增；低血回放覆盖严格 `0.01` 下界、配置阈值包含边界、等待未到/已到/超过 300 秒及对方血条消失复位。契约枚举 10,752 个代表性合法组合并拒绝 40 个非法单字段案例。对手状态、血量计算、计时器、OCR、调度和战斗均为夹具，mutation budget 为 0，没有消耗真实演习次数、进入战斗、截图/OCR、页面输入或 Android 注入。六个实际消费字段仅提升 `offline`；真实对手战力/等级与时段观察、刷新持久化、语义血量观察、实际重试/战斗/结算及失败恢复仍未闭环。

`LowHpConfirmWait` 本轮明确判为当前无效/未适配，而不是离线完成：固定上游虽然声明并描述该字段，但 Python 运行时零读取，`_combat_execute()` 无条件创建 `Timer(1.5, count=2)`。现在接线会改变上游现有时序且缺少字段到 Timer 参数的权威映射，因此不划算也不可信。重新进入条件是上游提供业务语义，或单独评审该映射，并补冻结时钟决策回放与可信语义血量实机证据。

### 1.29 本轮 Shipyard PR/DR 八字段与安全购买子域契约

`Shipyard.ResearchSeries` 只接受精确整数 `1..6`，`ShipyardDr.ResearchSeries` 只接受 `2..5`，两组 `ShipIndex` 只接受 `0..6`。两组 `LastRun` 必须是 2000-01-01 至 2100-01-01 的 naive datetime。两组 `BuyAmount` 当前只放行固定上游具有逐张价格表的精确整数 `0..15`；八字段在原 `RewardShipyard.run()` 文档字符串后的第一条可执行语句统一校验，早于调度状态写入、日期比较、页面导航、金币读取或蓝图使用。

固定上游回放覆盖 1,437 个合法案例并拒绝 58 个非法单字段案例。原 `shipyard_set_focus()` 保持 32 个可选、6 个 index 0 分支和 4 个三期以后 index 6 限制；DR 先于 PR、两组数量独立、双零停止、04:00 精确边界、DR 单独跳过和 PR 已运行的 delay/stop 均保持原分派。PR/DR 第 1..16 张价格也直接执行原算法：前 15 张合计分别为 8,250/22,200 金币，余额相等买满，少一金币只买 14；成功分支只在内存桩把对应 `LastRun` 写成冻结时间，最终 `BP_BUY` 确认不触发真实输入。

因此两组 `LastRun` 提升为 `offline=complete`，两组 `BuyAmount` 只提升为 `offline=partial`。固定上游对第 16 张以后定义了兜底单价，但当前语义观察尚不能证明购买面板显示数量、单价/总价和确认后余额，故 >15 明确 fail-closed，而不是假称完整或执行高额消费。页面不串页、蓝图不足、强化上限、真实确认、余额/蓝图 postcondition 和恢复收据仍未闭环，Shipyard 面板继续停留在账号边界。

### 1.30 本轮 Gacha 卡池、数量、票券与快速完成契约

`Gacha.Pool` 只接受 `light/heavy/special/event/wishing_well`，`Amount` 只接受精确整数 `1..10`，`UseTicket/UseDrill` 只接受精确布尔值。四字段在 `RewardGacha.run()` 第一条可执行语句统一校验，早于语义 build scope、资源读取、队列处理或提交；布尔伪装整数、浮点、字符串、越界和空值均 fail-closed。

200 个配置组合仍保持原卡池成本分类、仅活动池检查票券、票券优先与魔方余量拆分、提交后快速完成队列刷新；25 个非法单字段仍在 scope 前拒绝。实机 `event` 和 `special` 各完成一次两单建造：两次均从空队列开始，分别精确消耗 `4` 魔方和 `3000` 金币，并得到两条非空倒计时；回执为 `integration/alas/gacha-event-two-live-validation-receipt.json` 与 `integration/alas/gacha-special-two-live-validation-receipt.json`。其后以当前默认 `light`/`Amount=1` 重跑原任务：完整快照仅在池页、确认框和队列短暂陈旧时重读，最终精确消耗 `1` 魔方和 `600` 金币并产生一条队列倒计时，见 `integration/alas/gacha-light-daily-seed-validation-receipt.json`。`UseDrill=true` 现也由原 Gacha 任务完整闭环：从空队列开始，精确消耗 `1` 魔方、`600` 金币和 `1` 个快速完成道具，任务返回 true，依次关闭 NewShip 与 AwardInfo，并回到 typed 空队列；回执为 `integration/alas/gacha-light-drill-task-r7-live-validation-receipt.json`。随后对 `light`、`UseTicket=false`、`UseDrill=true` 的每个声明 `Amount=1..10` 逐值执行原任务：每次都从并回到 typed 空队列，返回 true，精确消耗 `N` 魔方、`600*N` 金币和 `N` 个快速完成道具；最终 Amount=10 还经过四槽完成态、十张 NewShip 和 AwardInfo 的真实恢复链。来源收据及摘要由 `integration/alas/gacha-light-amounts-1-10-live-validation-receipt.json` 绑定，故 `Gacha.Amount` 提升为完整。因此 `Gacha.UseDrill` 两个布尔值均提升为完整。活动票券栏当前不存在，祈愿池亦未开放，`UseTicket` 与 `wishing_well` 不能宣称完成。

### 1.31 本轮 Retirement 模式入口与旧退役拒绝契约

`Retirement.RetireMode` 只接受固定上游声明的 `one_click_retire/enhance/old_retire`。入口门禁位于原 `handle_retirement()` 文档字符串后的第一条业务语句，早于游戏提示、退役页/船坞识别、筛选、选择或确认。空值、布尔、整数、未知枚举和容器类型均 fail-closed；语义模式下的 `old_retire` 虽是合法 ALAS 配置，也会在任何页面事件前明确拒绝，因为该分支仍依赖未审阅的 framebuffer、卡片选择和坐标确认链。

固定上游回放逐值执行原 `_retire_amount` 映射，保持一键/强化的 3000 扫描上限、旧退役 `retire_all=3000` 与 `retire_10=10`；原 `_retire_handler()` 的一键和旧退役分派、宝石队旗舰衔接、退出及 `DOCK_FULL_TRIGGERED` 写入也由纯桩验证。入口回放保留一键、强化和非 Headless 旧退役的原状态机分派，同时证明 Headless 旧退役及非法配置均在零事件处拒绝。mutation budget 为 0，没有退役、强化、设备连接或 Android 输入，因此只把该字段的 `offline` 从 partial 提升为 complete；`old_retire` 的 observation/action/live 仍未适配，General 面板继续为 P，绝不能称为三模式完整支持。

### 1.32 本轮 BuyFurniture 开关、选项与六日记录契约

`BuyFurniture.Enable` 只接受精确布尔值，`BuyOption` 只接受固定上游 `set/all`，`LastRun` 只接受 2000-01-01 至 2100-01-01 的 naive datetime。三字段在原 Dorm 入口、语义 scope 和页面导航前统一校验；`BuyFurniture.run()` 也有独立的第一业务语句门禁，避免直接调用时先做日期运算。布尔伪装整数、未知枚举、字符串日期、带时区、越界和畸形值均 fail-closed。

冻结时钟回放保持原六日调度的精确边界：超过一秒与恰好六日都会运行，早一秒、未来记录会跳过；购买循环连续两次成功候选后停止，退出并把 `LastRun` 写为冻结当前时间。`set/all` 均保持原按钮映射，家具币大于价格及恰好等于价格判为可买，不足或价格为零判为失败。付款页、确认、退出、OCR 和 Dorm scope 的离线回放仍是零 mutation。

2026-08-18 当前客户端把新活动主题的原生套装页纳入 typed 观察与输入：主题详情、八张限时家具卡、`purchase_btn`（一套）、`purchase_all_btn`（全部）、家具币确认、价格、家具币/钻石余额和返回控件均有精确结构门禁。`Enable=true + BuyOption=set + 过期 LastRun` 的原 Dorm 任务只消耗一次 `shop.purchase` 授权，家具币 `4693→3363`（精确扣除 1330），钻石保持 5022，随后写入 `LastRun`、按六舰调度 278 分钟并恢复主页；收据为 `integration/alas/dorm-furniture-set-live-validation-receipt.json`。

按用户要求先买一套后，同一活动主题立即从该账号的主题候选列表消失。随后运行 `BuyOption=all` 时，适配器精确识别排在首位的是无任何限时标记的普通旧主题，保留全部购买授权、不改变家具币或钻石、写入 `LastRun` 并恢复主页；边界收据为 `integration/alas/dorm-furniture-all-post-set-boundary-receipt.json`。因此 set、真实扣款、空食物弹窗恢复和 post-set 无候选边界均已闭环；all 的原生按钮与最终提交路径已离线覆盖，但完整实买仍需要下一次未购买活动主题或另一个未购买账号，Dorm 面板保持 L、BuyFurniture 三字段保持 P。

### 1.33 本轮 Daemon 与 OpsiDaemon 三开关契约

`Daemon.EnterMap` 与 `OpsiDaemon.RepairShip/SelectEnemy` 只接受精确布尔值。两个门禁分别位于现有 `run_once()` 的第一条可执行语句，早于截图轮询；OpsiDaemon 还早于 `OSConfig` 合并和 override。21 个整数伪装、文本、空值和容器值均在零事件处 fail-closed。

单轮回放覆盖 EnterMap 的两个值和 OpsiDaemon 的四个组合。普通 Daemon 保持 MAP_PREPARATION 先于 FLEET_PREPARATION 的探测及各自早退，关闭时不触及这两个目标，但不篡改无关的伏击处理。OpsiDaemon 保持港口修复优先级、进入→修复→退出→interval reset 的顺序，以及无港口时才执行的最近目标探测。所有点击、修复和选敌都是记录桩，mutation budget 为 0，没有真实截图、导航、维修、移动、选敌或 Android 输入。

三字段仅提升 `offline=complete`。真实地图进入 postcondition、港口舰队 HP/资源变化、最近目标唯一身份、长期循环、断线/弹窗恢复和停止条件仍未闭环，因此 Daemon/OpsiDaemon 均保持 P，不能称为长期值守完整支持。

### 1.34 本轮 BattlePass 领取开关契约

`BattlePass.Collect` 只接受精确布尔值，并在 `Freebies.run()` 第一条可执行语句完成验证，早于 BattlePass、DataKey、Mail 和 SupplyPack 任一子模块构造。7 个整数伪装、文本、空值和容器值均在零事件处 fail-closed。

两值回放直接执行原 Freebies 分派：关闭时仅保留后续 Mail，开启时严格保持 BattlePass 在 Mail 之前；DataKey 与 SupplyPack 在夹具中关闭，最终 `task_delay(server_update=True)` 不变。所有子模块均为记录桩，mutation budget 为 0，没有真实战令导航、领奖或 Android 输入。

该字段只提升 `offline=complete`。真实战令入口、红点、免费/付费奖励区分、无奖励路径、领取后库存/货币收据和异常恢复仍缺，因此 Freebies 面板保持 P。

### 1.35 本轮 Optimization 三字段契约

`Optimization.ScreenshotInterval` 与 `CombatScreenshotInterval` 只接受有限数值且拒绝布尔混入；回放直接执行原 `Screenshot.screenshot_interval_set()`，保持普通 `0.1..0.3`、战斗 `0.3..1.0` 的夹取和写回、`nemu_ipc/ldopengl` 的 `0.2` 上限、`scrcpy` 的 `0.1` 覆盖，以及显式手工间隔不夹取。NaN、正负无穷、文本、空值和容器在 timer mutation 前 fail-closed。

`Optimization.WhenTaskQueueEmpty` 精确接受 `stay_there/goto_main/close_game`。冻结时钟回放直接执行原 `AzurLaneAutoScript.get_next_task()`：三种未来任务分支分别保留等待、回主界面、停包动作顺序；已到期任务不触发空队列动作。非法值现在在 `config.get_next()` 前拒绝，不再静默回退 `stay_there`。所有设备、等待和资源释放动作均为记录桩，mutation budget 为 0。

三字段只提升 `offline=complete`。真实跨后端帧时钟、长等待重载、停包后 Restart 租约、回主界面 postcondition 和进程恢复仍缺。另经 AST 证实，Headless 语义截图在读取 `Emulator.ScreenshotDedithering` 前已经返回 semantic frame；该字段当前对 Headless 无效，本批明确跳过，不把像素去抖算法外推为语义适配。Alas 面板保持 P。

### 1.36 本轮 Operation Siren 任务配置契约

`OpsiMonthBoss.Mode` 精确接受 `normal/normal_hard`，`CheckAdaptability` 精确接受布尔值。回放直接编译并执行固定上游 `clear_month_boss()` 与 `month_boss_delay()`，保留普通/困难入口选择、普通完成后继续困难、困难已完成跳过、`203/203/156` 适应性阈值及不足时延迟停止的原顺序。非法值在任务、地图或战斗状态前 fail-closed。

`OpsiObscure.ForceRun` 的真假分支直接执行原 `clear_obscure()` 与 `os_obscure()`：关闭时维持一次安全停止，开启时进入原任务切换检查。`OpsiDaily.UseTuningSample` 的真假分支直接执行原 `os_daily()`，只改变调律样本使用步骤，后续接任务、区域初始化、清任务与次日延迟顺序保持不变。`OpsiHazard1Leveling.TargetZone` 覆盖声明的 `0/22/44`：`0` 保持原逻辑映射到 22，另外两值进入对应安全区，回放在原 `run_strategic_search()` 边界停止。`OpsiMeowfficerFarming.HazardLevel` 覆盖 `3/4/5/6/10`，逐值保留原 `zone_select(hazard_level=...)` 参数和后续舰队、指令、自动搜索、后处理、任务切换顺序。`ActionPointPreserve` 接受非负整数，保持 0 时关闭潜艇及有效值上限裁剪到 2000 的原行为；负数和错误类型在日志、配置覆写、行动力检查或设备状态前拒绝。`TargetZone` 直接执行固定上游原 `ZoneManager.name_to_zone()`，数字 ID、数字文本及中/英/日/台名称均解析到同一原生海域；未知名称保持原人工接管结果，但已前移至行动力检查和设备动作之前。

`OpsiExplore.SpecialRadar` 直接回放原 `_os_explore()`，保留是否使用调律样本及 `recon_scan` 参数。它与 `OpsiExplore.ForceRun`、`OpsiObscure.ForceRun`、`OpsiAbyssal.ForceRun`、`OpsiStronghold.ForceRun` 还直接回放原 `AzurLaneConfig.opsi_task_delay()` 的侦察/潜艇任务延迟排除。五个布尔值的 32 种合法组合全部通过，30 个非法单字段值均在 `modified`、`update()` 或任务动作前 fail-closed。`OpsiExplore.LastZone` 通过固定上游原 `ZoneManager.name_to_zone()` 解析 `0`、排序内区域 ID、数字文本及多语言区域名，并保持从已保存区域的下一项续跑；错误类型、未知名称和不在当前顺序内的区域在地图导航前拒绝，不再静默归零重跑。

`OpsiGeneral.UseLogger` 的真假分支直接回放原 `StorageHandler.storage_get_next_item()`，保持进入仓库、可选使用全部坐标记录仪和坐标结算顺序。`BuyActionPointLimit=0..5` 与非负整数 `OilLimit` 直接回放原 `ActionPointHandler.action_point_buy()`：周购买次数达到上限时不购买，油量恰好等于费用加保留值时才进入最终购买边界，低一单位则拒绝。`RepairThreshold` 直接回放原 `OSMap.handle_fleet_repair()`，保留负数禁用、两位小数血量边界、回港修理和无需修理分支。`DoRandomMapEvent` 的真假分支保留不重扫和 `full` 重扫，显式 `current/full` 调用参数仍独立于配置。`AkashiShopFilter` 直接使用固定上游 `FILTER_REGEX` 与 `Filter`，保留空值默认回退、Unicode 分隔符、优先级、CL1 紫币排除和精确余额边界；未知或空 token 在商品预处理前拒绝。购买、血量、维修、仓库和地图重扫动作均为记录桩，未执行真实消费或 Android 输入。

`OpsiShop.PresetFilter` 的五个声明值直接绑定固定上游 `OS_SHOP`，`CustomFilter` 保留自定义顺序及空值回退默认预设。回放继续执行原 `Selector.items_filter_in_os_shop()`，覆盖 CL1 紫币排除和商品数量耗尽；未知预设、错误类型、未知及空 token 均在商品预处理前 fail-closed。没有刷新商店、读取或改变真实货币、购买商品或注入 Android 输入，因此只提升两个字段的 `offline` 维度。

`OpsiVoucher.Filter` 直接执行固定上游 `voucher_redirect()` 与通用商店 `FILTER_REGEX/Filter`，保留 Logger 双类型展开、T1..T6 展开、档案/解锁 Logger 删除、Unicode 分隔符和空过滤器安全跳过。未知 token、尾随空 token 和错误类型在代币商店页面动作前拒绝；没有滚动、兑换、读取或改变真实代币，也没有 Android 输入。

`OpsiAshAssist.Tier` 直接回放固定上游原 `_ensure_meta_level()`，精确整数保持等级显示等待、OCR 比较、最多五次向后轮换及找不到时使用当前信标的兜底行为。错误类型在首次页面观察或点击前 fail-closed。固定 ALAS 配置没有声明等级范围，因此不虚构 `1..15` 约束；负数、0 和高于当前等级的整数仍按原比较和兜底语义执行。

`OpsiAshBeacon.EnsureFullyCollected` 只回放两个既有刷图循环的行动力保留分支：在任务已启用且存在未完整领取的信标时，`false` 保留原 200/1,000 点限制，`true` 临时置零；其他条件仍保留正常限制。错误类型在配置 override、调度调用或地图输入前 fail-closed。该字段不生成、攻击、求助或领取信标，因此没有把高风险信标动作外推为已适配。

`OpsiAshBeacon.AttackMode` 精确接受 `current/current_dossier`，直接回放 `_begin_meta()` 的原选择逻辑：信标优先、`current` 跳过档案、`current_dossier` 进入档案，以及档案页的开始或退出分支。错误类型在首次页面观察前 fail-closed；输入均为记录桩，不启动战斗、求助、领奖或 Android 输入。

`OpsiAshBeacon.OneHitMode`、`RequestAssist` 和 `DossierAutoAttackMode` 均精确接受布尔值，并分别回放原 `_satisfy_attack_condition()` / `_pre_attack()` 的 inspect-and-delay、求助选择和档案自动攻击选择。错误类型在页面观察前 fail-closed；求助、自动攻击、战斗和领奖均由记录桩代替，仍没有实机动作或 Android 输入。

`OpsiFleetFilter.Filter` 直接使用固定上游 `FLEET_FILTER/Filter` 并回放原 `OSFleet.parse_fleet_filter()` 与 `AzurLaneConfig.opsi_task_delay()`。舰队顺序、`CallSubmarine`、Unicode 分隔符和连字符、重复去重、前三舰队待机位、不可用舰队形成空选择，以及潜艇任务延迟均保持原语义；未知或空 token、错误类型在过滤器状态、调度写入、舰队选择或任务输入前 fail-closed。调度器对没有该配置组的任务继续把缺省空值解释为“不调用潜艇”，不把缺省字段误判为非法用户配置。

共享 `OpsiFleet.Fleet` 的四个声明值直接回放原 `OSFleet.fleet_set()`，保留 selector 与相机稳定等待；非法值在 selector 或设备状态前拒绝。`OpsiFleet.Submarine` 的真假值直接回放原 `MapOrderHandler.os_order_execute()`，保留侦察/潜艇指令、潜艇完成等待与调度延迟参数；同时把非布尔 `recon_scan` 也挡在同一最终指令边界。连同此前字段，本契约共覆盖 31 个字段、136 个合法类并拒绝 234 个非法值，mutation budget 为 0；没有真实舰队切换、潜艇调用、行动力购买、维修、战斗、仓库消耗、兑换或 Android 输入，因此只提升 `offline=complete`。

此前只检查属性加载的 AST 审计漏掉了动态拼接的 `deep_get()` 字符串路径，因而错误地把 Explore/Abyssal/Stronghold 的 `ForceRun` 记为零读取；本轮已用源码绑定回放纠正。固定上游真正没有运行时消费者的仍只有 `OpsiMonthBoss.ForceRun` 与 `OpsiDaily.DoMission`，两者继续明确标为 `unsupported`。导航、坐标、舰队过滤、战斗和奖励 live 闭环仍未完成，相关面板不会因此提升为完整支持。

## 2. 60 个面板总表

“配置组”列是该面板实际暴露的组；同名配置组的详细字段在第 3 节只定义一次，所有引用它的面板必须共同满足该组的验收要求。

| # | 面板 | 配置组 | 当前 | 尚未闭环的配置范围与验收重点 |
|---:|---|---|:---:|---|
| 1 | Alas | Emulator, EmulatorInfo, Error, Optimization, DropRecord | P | 三项 Optimization 运行字段和 TaskHoardingDuration 已离线等价；语义截图仍不执行 Dedithering，传统方法/包名矩阵、错误截图、掉落上传与通知未完整验收 |
| 2 | General | Retirement, OneClickRetire, Enhance, OldRetire | P | 三种 `RetireMode` 已离线分类，旧退役在 Headless 页面事件前拒绝；官方一键退役和 `keep_limit_break` 已实机闭环；强化三项详细配置、ALAS 正式任务入口、语义筛选/选舰导航、官方推荐、真实强化、容量差及装备入仓已闭环；完整 `favourite` 破坏性任务和自然无素材分支未额外消耗舰船复测，`do_not_keep` 仅设置级验证，旧退役仍缺任务级语义事务 |
| 3 | Restart | Scheduler | F | 50 Scheduler 实例、15 等价类、首次启动跳过、禁包失败、冷恢复、运行中 PID 切换、登录、持久化与零 forward 遗留均已实机闭环；`AdbRestart` 属于 Alas 面板 |
| 4 | Main | Scheduler, Campaign, StopCondition, Fleet, Submarine, Emotion, HpControl, EnemyPriority | L | 12-4 已由原始 ALAS 完成入口、舰队、完整正交寻路、普通战、Boss 战、D 级败北结算、提示关闭和回图；Boss 胜利受当前账号战力限制，全部共用地图配置分支见 3.2 |
| 5 | Main2 | 同 Main | P | 已独立验证 Scheduler 命令、campaign_main 路由及 RunCount 五类循环；尚无 Main2 实机任务启动与地图闭环，不能沿用 Main 的运行记录提升为 L |
| 6 | Main3 | 同 Main | P | 已独立验证 Scheduler 命令、campaign_main 路由及 RunCount 五类循环；尚无 Main3 实机任务启动与地图闭环，不能沿用 Main 的运行记录提升为 L |
| 7 | GemsFarming | Scheduler, GemsFarming, EquipmentCode, Campaign, StopCondition, Fleet, Submarine, Emotion | M | 换旗舰/前排、常用舰选择、装备导入导出和换船后的强化衔接缺失；只有委托限制可复用 |
| 8 | EventGeneral | EventGeneral, TaskBalancer | P | 五字段离线决策已完整；仍缺 typed PT/金币实机观察、时间相关性、真实任务切换恢复和防调度环证据 |
| 9 | Coalition | Scheduler, Campaign, Coalition, StopCondition, Emotion | M | 共斗入口、难度、单/多舰队、战斗和结算缺适配 |
| 10 | Event | Scheduler, Campaign, StopCondition, Fleet, Submarine, Emotion, HpControl, EnemyPriority | L | 当前 A1 默认路径闭环；其他关卡和全部共用地图配置仍按字段验收 |
| 11 | Event2 | 同 Event | P | 与 Event 共用逻辑，但第二活动配置实例没有独立验收 |
| 12 | Raid | Scheduler, Raid, Campaign, StopCondition, Emotion | M | 难度、票券、活动入口、次数和结算缺适配 |
| 13 | Hospital | Scheduler, Hospital, StopCondition, Emotion | O | 推荐舰队开关已在医院入口与战斗准备入口离线回放并提前 fail-closed；医院页面、候选、推荐动作、战斗和结算观察/输入仍缺适配 |
| 14 | WarArchives | Scheduler, Campaign, StopCondition, Fleet, Submarine, Emotion, HpControl, EnemyPriority | B | 能观察入口/Data Key；48 个档案值的进入、消耗、地图和结算均未形成覆盖台账 |
| 15 | CoalitionSp | Scheduler, Campaign, Coalition, StopCondition, Emotion | M | SP 共斗专用状态机缺适配 |
| 16 | EventA | Scheduler, EventDaily, Campaign, StopCondition, Fleet, Submarine, Emotion, HpControl, EnemyPriority | L | A-D StageFilter/LastStage 离线轮转契约已完成；当前仅 A1-A3 默认路径有实机闭环，其余分区和共用地图配置仍未完整覆盖 |
| 17 | EventB | 同 EventA | O | B1 普通 `GET_SHIP` 已离线适配；因概率掉落停止实跑，B1 尚未完整闭环，B2/B3 未验证，首次获得 `NEW_SHIP` 未适配 |
| 18 | EventC | 同 EventA | P | C1-C3 地图脚本存在，无实机闭环 |
| 19 | EventD | 同 EventA | P | D1-D3 地图脚本存在，无实机闭环 |
| 20 | EventSp | Scheduler, Campaign, StopCondition, Fleet, Submarine, Emotion, HpControl, EnemyPriority | P | SP 地图脚本存在，无实机闭环 |
| 21 | RaidDaily | Scheduler, RaidDaily, Campaign, StopCondition, Emotion | M | 难度过滤、每日次数、战斗和领奖缺适配 |
| 22 | Commission | Scheduler, Commission | F | 六预设、custom、重大委托双值、动态多页、奖励、零油/非零油开始、1200 油确认、取消、补位和最早完成调度均已闭环 |
| 23 | Tactical | Scheduler, Tactical, ControlExpOverflow, AddNewStudent | L | AddNewStudent 三字段及 TacticalFilter 已完成真实库存观察、选书、确认和运行后置条件；经验溢出、四槽快速学习及其他 Tactical 分支仍未闭环 |
| 24 | Research | Scheduler, Research | L | 一个金币项目闭环；魔方/零件、延迟、重置、26 个预设和自定义规则未完整覆盖 |
| 25 | Dorm | Scheduler, Dorm, BuyFurniture | L | 收取、喂食、食物过滤与活动家具 set 实买均已闭环；all 因 set 后当前活动候选消失，尚缺另一未购买活动主题的最终实买回执 |
| 26 | Meowfficer | Scheduler, Meowfficer, MeowfficerTrain | M | 买箱、金币溢出、训练、增强和保留天赋规则均缺适配 |
| 27 | Guild | Scheduler, GuildLogistics, GuildOperation | M | 后勤兑换、新任务、作战、Boss 和推荐舰队均缺适配 |
| 28 | Reward | Scheduler, Reward | P | 五个领取开关及 RaidDaily 共享入口已离线完成；资源气泡可领取，任务领取部分可用，周常、红点、数字行、空页面和舰船奖励仍未完整闭环 |
| 29 | Awaken | Scheduler, Awaken | O | Favourite 与 120/125 上限已在原分派入口离线回放并提前 fail-closed；资源、候选、批量选择、确认和结果观察/输入仍缺适配 |
| 30 | Daily | Scheduler, Daily | L | 十四字段离线映射与 fail-closed 契约已完成；实机仍只闭环 Tactical Training 第二关默认舰队，其余日常和配置值未闭环 |
| 31 | Hard | Scheduler, Hard | B | 64 关目录与两舰队离线契约已完成；实机仍只到 11-4 进入边界，当前账号进度和自动寻敌锁定，尚无战斗/结算证据 |
| 32 | Exercise | Scheduler, Exercise | L | 六个实际消费字段已离线等价；`LowHpConfirmWait` 上游零读取，真实对手/时段/血量观察、刷新持久化、战斗结算和失败恢复未闭环 |
| 33 | ShopFrequent | Scheduler, GeneralShop | B | ConsumeCoins、BuySkinBox、UseGems、Filter 与 Refresh 已离线等价；购买、余额观察与确认仍未完成 |
| 34 | ShopOnce | Scheduler, GuildShop, MedalShop2, MeritShop, CoreShop | P | GuildShop 14 字段与 MedalShop2 7 字段入口已离线等价；其余商店与真实操作未闭环 |
| 35 | Shipyard | Scheduler, ShipyardDr, Shipyard | B | 八字段入口已门禁；LastRun 完整离线、BuyAmount 0..15 部分离线，>15 及真实页面/价格/确认/结果仍拒绝 |
| 36 | Gacha | Scheduler, Gacha | L | 四配置字段已离线等价；Event/Special 各两单已实机提交并核对资源与队列，UseDrill 两值均已完成原任务闭环；票券、祈愿池、其余卡池和数量仍未闭环 |
| 37 | Freebies | Scheduler, BattlePass, DataKey, Mail, SupplyPack | P | BattlePass 分派开关、Mail 四开关、DataKey 两开关和 SupplyPack 两字段已离线完成；真实战令奖励、Data Key 容量、免费补给和领取收据仍未闭环 |
| 38 | Minigame | Scheduler | F | 固定源代码仅声明抚顺挑战；无用户字段，单票实机任务已完整进入、结算、退出、预算耗尽停止并返回主界面 |
| 39 | PrivateQuarters | Scheduler, PrivateQuarters | M | 蛋糕、玫瑰、互动和 7 个舰船选项均缺适配 |
| 40 | OpsiGeneral | OpsiGeneral | P | 六字段均已离线等价；真实购买/维修结果、资源 postcondition 和异常恢复仍未闭环 |
| 41 | OpsiAshBeacon | Scheduler, OpsiAshBeacon | B | 五字段均已离线等价；自动攻击、一击、求助、完整领取和 Boss 结束的实机动作仍未闭环 |
| 42 | OpsiAshAssist | Scheduler, OpsiAshAssist | B | Tier 等级选择已离线等价；真实目标列表、出击、战斗和领奖仍受舰队条件限制 |
| 43 | OpsiExplore | Scheduler, OpsiExplore, OpsiFleet | B | ForceRun、LastZone、SpecialRadar、Fleet/Submarine 已离线等价；真实地图导航、舰队/潜艇动作和清区未闭环 |
| 44 | OpsiShop | Scheduler, OpsiShop | B | 5 个预设和自定义过滤已离线等价；真实购买、刷新、货币 postcondition 与异常恢复仍未闭环 |
| 45 | OpsiVoucher | Scheduler, OpsiVoucher | B | 过滤器及重定向已离线等价；真实库存、命中、兑换、代币 postcondition 与异常恢复仍未闭环 |
| 46 | OpsiDaily | Scheduler, OpsiDaily, OpsiFleet | B | UseTuningSample、Fleet/Submarine 已离线等价；DoMission 无消费者，真实舰队/潜艇动作和清图未闭环 |
| 47 | OpsiObscure | Scheduler, OpsiObscure, OpsiFleet | B | ForceRun、Fleet/Submarine 已离线等价；坐标消耗、真实动作、进入和清图未闭环 |
| 48 | OpsiAbyssal | Scheduler, OpsiAbyssal, OpsiFleetFilter | B | ForceRun 与舰队过滤已离线等价；坐标消耗、真实舰队、Boss 和结算未闭环 |
| 49 | OpsiArchive | Scheduler, OpsiFleet | B | Fleet/Submarine 已离线等价且档案商店可读；真实动作、购买、使用坐标、进入和清图未闭环 |
| 50 | OpsiStronghold | Scheduler, OpsiStronghold, OpsiFleetFilter | M | 舰队过滤已离线等价；3D 漩涡无可靠观察，进入、真实舰队、战斗和结算未闭环 |
| 51 | OpsiMonthBoss | Scheduler, OpsiMonthBoss, OpsiFleetFilter | B | 模式、适应性检查和舰队过滤已离线等价；ForceRun 无消费者，普通/困难 Boss 未闭环 |
| 52 | OpsiMeowfficerFarming | Scheduler, OpsiMeowfficerFarming, OpsiFleet | B | HazardLevel、Fleet/Submarine 已离线等价；行动力保留、选区、真实动作和循环未闭环 |
| 53 | OpsiHazard1Leveling | Scheduler, OpsiHazard1Leveling, OpsiFleet | B | TargetZone、Fleet/Submarine 已离线等价；真实动作、选区和循环未闭环 |
| 54 | OpsiCrossMonth | Scheduler | B | 非月末安全跳过；月末执行、重置和跨月恢复未验证 |
| 55 | Daemon | Daemon | P | EnterMap 双值与单轮地图/编队分派已离线等价；真实进入 postcondition、长期值守和稀有恢复仍未闭环 |
| 56 | OpsiDaemon | OpsiDaemon | P | 修船/选敌四组合与最终边界已离线等价；真实港口修复、最近目标 postcondition 和长期恢复仍未闭环 |
| 57 | EventStory | EventStory | P | `SkipBattle` 在固定上游锁为 true 且无运行时消费者；false 需要新的剧情战斗状态机和多活动观察，当前仅一条入口路径，战斗转场及其他故事结构未闭环 |
| 58 | Benchmark | Benchmark | F | 五种 DeviceType 与三种 TestScene 已逐组实机运行；每组保留原 15 次计时、确认回主页并清理临时配置。DeviceType 是已验证的 Headless semantic 配置来源，不宣称旧云/VMOS 传输 |
| 59 | AzurLaneUncensored | AzurLaneUncensored | P | 本地 localization 路径可用；`Repository` 对应的远端同步在上游被注释，配置与能力不一致 |
| 60 | GameManager | GameManager | F | 真假双值、已停止幂等、连续 PID 冷启动、登录、停止/启动/断网/600 秒 observer 超时、恢复及零 forward 遗留均已闭环 |

## 3. 配置组字段级矩阵

### 3.1 全局、调度、退役与强化

| 配置组 | 字段与取值 | 当前 | 完整支持必须满足 |
|---|---|:---:|---|
| Scheduler | `Enable`; `NextRun`; 隐藏字段 `Command`, `SuccessInterval`, `FailureInterval`, `ServerUpdate` | F | 50 个声明实例和 15 个等价类已走原始队列及持久化路径；正常 false 启用态不入队、Restart 锁定 true、success/failure/server-update 写入、首次服务跳过、禁包失败、冷恢复、PID 切换和零 forward 遗留均已验证 |
| Emulator | `Serial`; `PackageName`（22 值）; `ServerName`（72 值）; `ScreenshotMethod`=`auto/ADB/ADB_nc/uiautomator2/aScreenCap/aScreenCap_nc/DroidCast/DroidCast_raw/nemu_ipc/ldopengl`; `ControlMethod`=`ADB/uiautomator2/minitouch/Hermit/MaaTouch`; `ScreenshotDedithering`; `AdbRestart` | P | Headless 明确支持/拒绝每种方法；至少覆盖当前包/服务器、自动发现失败、设备断连、重连和方法不兼容；不能静默回退到未经授权的像素路径 |
| EmulatorInfo | `Emulator`=`auto/NoxPlayer/NoxPlayer64/BlueStacks4/BlueStacks5/BlueStacks4HyperV/BlueStacks5HyperV/LDPlayer3/LDPlayer4/LDPlayer9/LDPlayer14/MuMuPlayer/MuMuPlayerX/MuMuPlayer12/MEmuPlayer`; `name`; `path` | P | 自动与显式模拟器发现、找不到安装、多个实例和自定义路径均需 fail-closed |
| Error | `HandleError`; `SaveError`; `OnePushConfig`; `ScreenshotLength` | P | 两个布尔值组合、错误证据可用性、截图长度边界、通知成功/失败/未配置，以及不泄漏敏感信息 |
| Optimization | `ScreenshotInterval`; `CombatScreenshotInterval`; `TaskHoardingDuration`; `WhenTaskQueueEmpty`=`stay_there/goto_main/close_game` | P | 四字段均已离线等价并 fail-closed；跨后端帧时钟、长等待重载、`close_game` 包进程租约和空队列恢复仍未实机闭环 |
| DropRecord | `ResearchRecord`, `CommissionRecord`, `CombatRecord`, `OpsiRecord`, `MeowfficerBuy`, `MeowfficerTalent`; `API`; `AzurStatsID`; `SaveFolder` | M | `do_not/save/upload/save_and_upload` 各模式、默认/反代 API、无 ID、无权限目录、网络失败、脱敏和重试；没有有效画面时不得生成伪证据 |
| Retirement | `RetireMode`=`one_click_retire/enhance/old_retire` | P | 三枚举已离线逐值分类且非法值提前拒绝；`one_click_retire` 已走游戏官方事务并用容量差验证真实数量，`enhance` 已接 ALAS 正式任务并走官方推荐事务；`old_retire` 在 Headless 页面事件前 fail-closed，仍缺其任务级语义事务、完整收藏破坏性任务、自然无素材和非网络中断实机证据 |
| OneClickRetire | `KeepLimitBreak`=`keep_limit_break/do_not_keep` | P | `keep_limit_break` 已实退；`do_not_keep` 仅验证官方设置值，未做扩大集合后的破坏性实退；唯一舰船保护始终强制开启 |
| Enhance | `ShipToEnhance`=`all/favourite`; `CheckPerCategory`; `Filter` | P | 三字段已接 ALAS 正式任务并严格解析，非法/重复类型 fail-closed；`all/favourite` 控件、8 类筛选、候选卡、强化页、返回与恢复默认均为 typed 导航，默认 5 次及有序分类循环有确定性测试；官方推荐、7 艘 Lv.1/bg1 素材、真实强化 `196→197`、容量 `814→807` 及 14 件装备入仓已实机验证；完整收藏破坏性任务和自然无素材实机分支按避免额外消耗原则未跑 |
| OldRetire | `N`, `R`, `SR`, `SSR`; `RetireAmount`=`retire_all/retire_10` | M | 16 种稀有度开关组合与两种数量策略；锁定/收藏/满破保护和最终列表必须可核验 |

### 3.2 普通地图、活动地图与宝石委托共用配置

| 配置组 | 字段与取值 | 当前 | 完整支持必须满足 |
|---|---|:---:|---|
| Campaign | `Name`; `Event`; `Mode`=`normal/hard`; `UseClearMode`; `UseFleetLock`; `UseAutoSearch`; `Use2xBook`; `AmbushEvade` | P | 五个布尔开关的全组合、原快速前进/锁定/伏击分支及入口 fail-closed 已离线完成；仍缺真实控件后置条件、非周回地图与伏击失败闭环。`Name/Mode/Event` 仍需逐值路由验证，`Event` 的 48 个档案活动值必须逐项登记支持或显式拒绝 |
| StopCondition | `OilLimit`; `RunCount`; `MapAchievement`=`non_stop/100_percent_clear/map_3_stars/threat_safe/threat_safe_without_3_stars`; `StageIncrease`; `GetNewShip`; `ReachLevel` | P | 每个停止条件分别触发并停止在正确页面；0/边界/达到/未达到、条件同时满足、普通掉落与首次获得必须可区分 |
| Fleet | `Fleet1`=1..6; `Fleet1Formation`=`line_ahead/double_line/diamond`; `Fleet1Mode`=`combat_auto/combat_manual/stand_still_in_the_middle/hide_in_bottom_left/hide_in_upper_left`; `Fleet1Step`=2..5; `Fleet2`=0..6; `Fleet2Formation` 同三阵型；`Fleet2Mode` 同五模式；`Fleet2Step`=2..5; `FleetOrder` 四种主力/Boss/待机组合 | P | 九字段全部值已离线分类；索引和步数保留原 ALAS 路由。固定上游不消费 Formation，非默认值提前拒绝；手动战斗模式缺 typed 方向/武器输入，非默认 FleetOrder 缺实机语义出击证据，故观察、动作和实机仍不完整 |
| Submarine | `Fleet`=0/1/2; `Mode`=`do_not_use/hunt_only/boss_only/hunt_and_boss/every_combat`; `AutoSearchMode`=`sub_standby/sub_auto_call`; `DistanceToBoss`=`to_boss_position/1_grid_to_boss/2_grid_to_boss/use_open_ocean_support` | P | 四字段已完成原决策离线回放；`Fleet=0` 的 40 个惰性组合可用，`Fleet=1/2` 因编队、策略、移动和呼叫输入未接管而在导航前拒绝 |
| Emotion | `Mode`=`calculate/ignore/calculate_ignore`; `Fleet1Value`; `Fleet1Record`; `Fleet1Control`; `Fleet1Recover`; `Fleet1Oath`; `Fleet2Value`; `Fleet2Record`; `Fleet2Control`; `Fleet2Recover`; `Fleet2Oath`; 两个 `Control` 均为 `keep_exp_bonus/prevent_green_face/prevent_yellow_face/prevent_red_face`，两个 `Recover` 均为 `not_in_dormitory/dormitory_floor_1/dormitory_floor_2` | P | 11 字段已完成原时间账本离线回放与中心 fail-closed；真实低心情等待、持久化调度、誓约/宿舍事实观察和跨任务恢复仍未扩证 |
| HpControl | `UseHpBalance`; `UseEmergencyRepair`; `UseLowHpRetreat`; `HpBalanceThreshold`; `HpBalanceWeight`; `RepairUseSingleThreshold`; `RepairUseMultiThreshold`; `LowHpRetreatThreshold` | P | 八字段已离线分类并在出击前 fail-closed；三个启用态仍分别缺 typed 编队拖拽、紧急维修模板/输入和完整撤退循环，故动作与实机完整性不提升 |
| EnemyPriority | `EnemyScaleBalanceWeight`=`default_mode/S3_enemy_first/S1_enemy_first` | P | 三值已完成原方法离线回放与导航前 fail-closed；相同地图夹具覆盖过滤覆盖、无敌人和同星级多目标，实机/动作维度未扩大 |
| GemsFarming | `ChangeFlagship`=`ship/ship_equip`; `ChangeVanguard`=`disabled/ship/ship_equip`; `CommissionLimit`; `CommonCV`=`any/langley/bogue/ranger/hermes`; `CommonDD`=`any/favourite/aulick_or_foote/cassin_or_downes/z20_or_z21` | M | 每个候选舰/换装模式、收藏过滤、无候选舰、船坞满、委托占用和换船后继续刷图 |
| EquipmentCode | `Config`（DD 与四艘 CV 的装备代码）；`ExportToConfig` | M | 合法/缺失/错误装备代码、导出开关、装备不足、被占用装备和回滚；不得装备到错误舰船 |

### 3.3 活动专用配置

| 配置组 | 字段与取值 | 当前 | 完整支持必须满足 |
|---|---|:---:|---|
| EventGeneral | `PtLimit`; `TimeLimit` | P | PT 与冻结时间边界、非活动任务和 GemsFarming 主线豁免已离线完成；typed 实机观察、服务器时间相关性和真实禁用恢复仍缺 |
| TaskBalancer | `Enable`; `CoinLimit`; `TaskCall`=`Main/Main2/Main3` | P | 开关、金币边界和三个目标任务切换顺序已离线完成；真实任务调用、失败恢复及防调度环仍缺 |
| Coalition | `Mode`=`easy/normal/hard/sp`; `Fleet`=`single/multi` | M | 四难度、单/多舰队、次数/票券不足、战斗、结算和 SP 特殊入口 |
| Raid | `Mode`=`easy/normal/hard/ex`; `UseTicket` | M | 四难度、票券真假、无票券、次数耗尽、推荐舰队和结算 |
| Hospital | `UseRecommendFleet` | O | 开关两值已回放 in-use、推荐与手动接管原分支，错误值在医院 UI 前拒绝；仍需实际候选、推荐、活动结束和结算观察/输入 |
| EventDaily | `StageFilter`（A/B/C/D 各自 1-3 优先级字符串）；`LastStage` | P | 四分区过滤、缺脚本、无匹配、未解锁、游标恢复及跨日重置已离线覆盖；仍需 B-D 实机轮转和活动切换后的持久化收据 |
| RaidDaily | `StageFilter`=`hard > normal > easy`（自由优先级字符串） | M | 各难度可用组合、过滤命中/无命中/非法值、次数耗尽和每日重置 |

### 3.4 委托、战术、科研、宿舍、猫箱、公会与奖励

| 配置组 | 字段与取值 | 当前 | 完整支持必须满足 |
|---|---|:---:|---|
| Commission | `PresetFilter`=`cube/cube_24h/chip/chip_24h/oil/custom`; `CustomFilter`; `DoMajorCommission` | F | 六预设与重大委托双值均完成动态列表实机单轮；custom 语法、非零油确认、重大委托、奖励、取消、补位和连续调度均已闭环 |
| Tactical | `RapidTrainingSlot`=`do_not_use/slot_1/slot_2/slot_3/slot_4`; `TacticalFilter` | L | TacticalFilter 已通过原始任务的真实书库存排序、选书、开课确认和运行后置状态；仍需真实快速学习可用性/次数、无书/无空位及其他教学分支闭环 |
| ControlExpOverflow | `Enable`; `T1Allow`; `T2Allow`; `T3Allow`; `T4Allow` | F | `5750/5800` 真实临界技能下完成关闭过滤、四档精确放行、T4 选书、唯一课程确认与运行后置状态；全部边界继续由离线回放覆盖 |
| AddNewStudent | `Enable`; `Favorite`; `MinLevel` | F | Disabled 不变性、收藏/非收藏候选范围、120 级选舰、原始选书与唯一课程确认、运行中课程后置条件均已实机闭环 |
| Research | `PresetFilter`（26 值）; `CustomFilter`; `AllowDelay`; `UseCoin`, `UseCube`, `UsePart`=`always_use/only_05_hour/only_no_project/do_not_use` | L | 三资源 always/do_not、重名卡、队列容量与真值回退已实机；仍缺当前最终哈希下四策略全矩阵、26 预设、真实资源不足延迟、可用重置和跨轮闭环 |
| Dorm | `Collect`; `Feed`; `FeedFilter` | L | 三字段均已达到五维完整：真实收取控件由有变无、喂食库存差、关闭分支、单值过滤器与全部合法优先级均有证据；面板仍由 BuyFurniture all 的实买缺口限制 |
| BuyFurniture | `Enable`; `BuyOption`=`set/all`; `LastRun` | P | set 活动主题实买、家具币精确扣款、LastRun、六舰调度、主页恢复和 post-set all 无候选均已闭环；all 最终实买等待另一未购买活动主题 |
| Meowfficer | `BuyAmount`; `FortChoreMeowfficer`; `OverflowCoins` | M | 数量 0/边界、保留后勤猫、金币阈值、箱位满和购买确认 |
| MeowfficerTrain | `Enable`; `Mode`=`seamlessly/once_a_day`; `RetainTalentedGold`; `RetainTalentedPurple`; `MaxFeedLevel`; `EnhanceIndex` | M | 两训练模式、两保留开关组合、等级/索引边界、无材料、错误目标保护和每日去重 |
| GuildLogistics | `Enable`; `ExchangeFilter`; `SelectNewMission` | M | 开关、兑换规则、新任务选择、贡献不足、无奖励和重复领取 |
| GuildOperation | `Enable`; `JoinThreshold`; `SelectNewOperation`; `NewOperationMaxDate`; `AttackBoss`; `BossFleetRecommend` | M | 阈值/日期边界、加入/选择、Boss 与非 Boss、推荐舰队开关、次数不足和奖励 |
| Reward | `CollectOil`; `CollectCoin`; `CollectExp`; `CollectMission`; `CollectWeeklyMission` | F | 32 种开关组合、20 个非法单字段案例及 Reward/RaidDaily 双入口 fail-closed 已离线完成；五个开关均有原始 ALAS 的开启/关闭实机闭环 |
| Awaken | `Favourite`; `LevelCap`=`level120/level125` | O | 两个布尔/枚举设置已在原分派器回放，错误值在 `awaken_run` 前拒绝；仍需资源不足、无候选、批量选择、确认结果和所有实机观察/输入 |

### 3.5 每日、演习、商店、船坞、建造与免费领取

| 配置组 | 字段与取值 | 当前 | 完整支持必须满足 |
|---|---|:---:|---|
| Daily | `EscortMission`, `AdvanceMission`, `TacticalTraining`, `SupplyLineDisruption`, `FierceAssault`=`skip/first/second/third`; `ModuleDevelopment`, `EmergencyModuleDevelopment`=`skip/first/second`; `EscortMissionFleet`, `AdvanceMissionFleet`, `TacticalTrainingFleet`, `FierceAssaultFleet`, `ModuleDevelopmentFleet`, `EmergencyModuleDevelopmentFleet`=1..6；`UseDailySkip` | L | 全值域、两种排列、skip、次数耗尽及 SupplyLine fleet=0 已离线覆盖；仍缺非默认任务/难度/舰队、快速跳过不可用和战斗结算的实机收据 |
| Hard | `HardStage`; `HardFleet`=1/2 | B | 固定上游 64 关目录、两舰队、次数为 0/3 和非法值已离线覆盖；仍缺未解锁页、非默认关卡/舰队、真实战斗和结算收据 |
| Exercise | `ExerciseStrategy`=`aggressive/fri18/sat0/sat12/sat18/sun0/sun12/sun18`; `OpponentChooseMode`=`max_exp/easiest/leftmost/easiest_else_exp`; `OpponentRefreshValue`; `OpponentRefreshRecord`; `OpponentTrial`; `LowHpThreshold`; `LowHpConfirmWait` | L | 六个实际消费字段已离线等价；`LowHpConfirmWait` 零读取且明确不支持，真实对手/时段/血量观察、刷新持久化、失败重开和赛季边界仍需闭环 |
| GeneralShop | `Filter`; `Refresh`; `UseGems`; `ConsumeCoins`; `BuySkinBox` | B | ConsumeCoins 550,000 阈值、BuySkinBox、UseGems、Filter 与 Refresh 已离线等价；真实商品命中、刷新、余额观察和购买确认仍缺 |
| GuildShop | `Filter`; `Refresh`; `BOOK_T2`; `BOOK_T3`; `BOX_T3`; `BOX_T4`; `PLATE_T2`; `PLATE_T3`; `PLATE_T4`; `RETROFIT_T2`; `RETROFIT_T3`; `PR1`; `PR2`; `PR3` | P | 14 字段入口、语法与枚举已离线等价；真实商品/货币/库存、PR 系列判别、选择确认与购买仍缺 |
| MedalShop2 | `Filter`; `PLATE_T1`; `PLATE_T2`; `PLATE_T3`; `RETROFIT_T1`; `RETROFIT_T2`; `RETROFIT_T3` | L | 7 字段入口、语法与枚举已离线等价；真实商品/货币/库存、选择确认与购买仍缺 |
| MeritShop | `Filter`; `Refresh` | M | 规则命中、刷新真假、功勋不足和购买确认 |
| CoreShop | `Filter` | M | 规则命中/无命中、核心不足、月限购和确认 |
| ShipyardDr | `ResearchSeries`=2..5; `ShipIndex`=0..6; `BuyAmount`; `LastRun` | B | 系列/舰位已离线等价；数量边界、每日去重、蓝图不足、达到上限和实际购买仍需闭环 |
| Shipyard | `ResearchSeries`=1..6; `ShipIndex`=0..6; `BuyAmount`; `LastRun` | B | 系列/舰位已离线等价；其余同上，且 PR/DR 页面切换不能串页 |
| Gacha | `Amount`=1..10; `Pool`=`light/heavy/special/event/wishing_well`; `UseDrill`; `UseTicket` | L | 200 个配置组合已离线等价；`UseDrill` 两值已实机完整，仍缺其他卡池、多单、票券、队列满、资源不足和领取 |
| BattlePass | `Collect` | B | 两值与 Freebies 分派已离线；真实入口、免费/付费奖励区别、无奖励和领取结果仍待闭环 |
| DataKey | `Collect`; `ForceCollect` | L | 四组合、非法值和已领取/满容量/强制/有余量边界已离线完成；仍缺真实普通/强制领取、上限弹窗和库存后置条件 |
| Mail | `ClaimMerit`; `ClaimMaintenance`; `ClaimTradeLicense`; `DeleteCollected` | P | 16 组合、不同邮件类型、附件为空、容量上限、只删除已领取和误删保护 |
| SupplyPack | `Collect`; `DayOfWeek`=0..6 | B | 开关、七天、日期比较和高油保护已离线覆盖；仍缺免费包已领/可领、跨日、真实领取收据和购买项误触保护实机证据 |
| PrivateQuarters | `BuyCake`; `BuyRoses`; `TargetInteract`; `TargetShip`=`anchorage/noshiro/sirius/new_jersey/taihou/aegir/nakhimov` | M | 三开关组合、7 舰船、目标未解锁、货币不足、互动次数和购买确认 |
| Minigame | 无用户字段，仅 Scheduler | F | 上游固定任务仅声明 `new_year_challenge`；单票实机验证覆盖进入、开局、结算、退出、预算耗尽停止及主界面清理 |

### 3.6 大世界配置

| 配置组 | 字段与取值 | 当前 | 完整支持必须满足 |
|---|---|:---:|---|
| OpsiGeneral | `DoRandomMapEvent`; `AkashiShopFilter`; `BuyActionPointLimit`=0..5; `OilLimit`; `RepairThreshold`; `UseLogger` | P | 六字段均已离线等价；真实维修/购买确认、资源 postcondition 与异常恢复仍缺 |
| OpsiAshBeacon | `AttackMode`=`current/current_dossier`; `DossierAutoAttackMode`; `EnsureFullyCollected`; `OneHitMode`; `RequestAssist` | B | 五字段均已离线等价；点数不足/满、生成、攻击、求助、领取和 Boss 结束的实机闭环仍缺 |
| OpsiAshAssist | `Tier` | B | 整数阈值、五次轮换和兜底已离线等价；真实无目标、舰队不可用、出击、战斗和奖励仍缺 |
| OpsiExplore | `ForceRun`; `LastZone`; `SpecialRadar` | B | 三字段已离线等价；真实地图重置、导航、舰队动作和清区仍缺 |
| OpsiFleet | `Fleet`=1..4; `Submarine` | B | 四舰队和潜艇真假已在原最终边界离线等价；舰队不可用、真实选中结果、潜艇调用结果及隐藏字段 override 仍需实机闭环 |
| OpsiShop | `PresetFilter`=`max_benefit/max_benefit_meta/no_meta/all/custom`; `CustomFilter` | B | 两字段已离线等价；不同港口真实库存、货币不足、刷新、购买确认和无匹配实机恢复仍缺 |
| OpsiVoucher | `Filter` | B | 过滤与 Logger/Tier/Archive 重定向已离线等价；真实代币余额、兑换结果、空列表和异常恢复仍缺 |
| OpsiDaily | `DoMission`; `UseTuningSample` | B | 四组合、无任务、接取/进入/清图、样本有无和跨日恢复 |
| OpsiObscure | `ForceRun` | B | 开关、坐标不存在/存在、消耗、进入、清图与奖励 |
| OpsiAbyssal | `ForceRun` | B | 开关、坐标、Boss、多舰队、撤退/失败和奖励 |
| OpsiFleetFilter | `Filter`（默认含 Fleet-4、CallSubmarine、Fleet-2/3/1） | B | 语法、顺序、潜艇、重复、不可用与非法规则已离线等价；真实舰队可用性、切换结果和战斗仍缺 |
| OpsiStronghold | `ForceRun` | M | 先补足 3D 漩涡存在性观察；再验证开关、进入、舰队选择、战斗、撤退和结算 |
| OpsiMonthBoss | `Mode`=`normal/normal_hard`; `CheckAdaptability`; `ForceRun` | B | 两模式、两个开关组合、适应性不足/足够、普通/困难切换、战斗和奖励 |
| OpsiMeowfficerFarming | `HazardLevel`=3/4/5/6/10; `TargetZone`; `ActionPointPreserve` | B | 五危险等级、自动/显式区域、行动力边界、舰队/潜艇、循环与停止 |
| OpsiHazard1Leveling | `TargetZone`=0/44/22 | B | 三目标值、不可用区域、舰队/潜艇、自动寻敌和循环停止 |
| OpsiArchive | 无独立组，复用 Scheduler 与 OpsiFleet | B | 档案商店购买、坐标使用、舰队/潜艇、进入/清图与奖励 |
| OpsiCrossMonth | 无独立组，仅 Scheduler | B | 月末前后、服务器时区、重置完成/失败、重启续跑和幂等性 |

### 3.7 工具任务

| 配置组 | 字段与取值 | 当前 | 完整支持必须满足 |
|---|---|:---:|---|
| Daemon | `EnterMap` | P | 两值及单轮分派已离线；主界面/地图内真实进入、恢复循环和未知弹窗仍待闭环 |
| OpsiDaemon | `RepairShip`; `SelectEnemy` | P | 四组合及最终边界已离线；真实维修/选敌 postcondition、长期循环和异常恢复仍待闭环 |
| EventStory | `SkipBattle`（当前只允许 true） | P | 固定上游锁 true 且无字段消费者，实际始终重启跳过战斗；false 需上游/评审后的继续战斗状态机及多活动战斗、结算夹具，当前不外推完成 |
| Benchmark | `DeviceType`=`emulator/plone_cloud_with_adb/phone_cloud_without_adb/android_phone/android_phone_vmos`; `TestScene`=`screenshot_click/screenshot/click` | F | 5 x 3 全矩阵已实机执行；逐组返回预期 observer/settings-round-trip 测量、回主页并清理临时配置。设备类型完成范围是 Headless semantic 配置绑定与验证，不宣称旧云/VMOS 传输 |
| AzurLaneUncensored | `Repository` | P | 先决定恢复远端同步还是删除/禁用该配置；网络失败、仓库不可达、本地文件和回滚必须有明确契约 |
| GameManager | `AutoRestart` | F | true/false、运行中/已停止、连续 PID 冷启动、登录、停止/启动/断网/完整 observer 超时、恢复和 session/forward 清理均已实机与回放闭环 |

## 4. 关键中断面与观察缺口

以下分支会横向影响多个配置项，不能只在单个任务里打补丁：

| 中断面 | 当前状态 | 受影响配置 | 收口要求 |
|---|---|---|---|
| `GET_SHIP` 普通掉落 | 已有离线语义适配 | EventB、所有 `GetNewShip=false` 地图 | 普通掉落可关闭并继续；使用确定性夹具，不继续刷概率掉落 |
| `NEW_SHIP` 首次获得 | 未适配 | `StopCondition.GetNewShip=true`、所有首次掉落场景 | 独立识别首次获得标志，触发停止条件；不得与普通掉落混淆 |
| 退役分支 | 官方一键与强化主路径已闭环 | General、船坞满后的所有任务 | 已覆盖动态数量、安全设置、稀有确认、奖励、装备保留、返回、无候选、强化正式任务和精确网络重连；仍需旧退役、完整收藏破坏性任务、自然无素材及未知中断恢复 |
| 伏击分支 | 信息条依赖像素裁剪 | `Campaign.AmbushEvade`、潜艇/地图移动 | 需要决定补语义节点还是允许受控局部视觉，并覆盖迎战/规避失败 |
| 剧情选择 | 动态选项未完整观察 | EventStory、普通/活动地图 | 识别选项数量和选择结果；未知剧情 fail-closed |
| 公会/任务上下文弹窗 | 语义动作不完整 | Reward、Guild、Campaign | 区分确认/取消/前往，不得用通用坐标误点 |
| 白色确认框 | 变体未完整观察 | 购买、维修、活动、退役 | 确认内容与动作绑定，不能只看“有白框” |
| 大世界要塞 3D 漩涡 | UI 树不可见 | OpsiStronghold | 明确采用新增语义来源或受控局部视觉；无可靠存在性信号时保持 fail-closed |

## 5. 验收与维护规则

### 5.1 每个字段的最小验收记录

后续补齐时，每个字段或经证明等价的字段组合必须记录：

| 项目 | 必填内容 |
|---|---|
| 配置路径 | 例如 `Main.Submarine.Mode` |
| 测试值 | 明确枚举值、开关值或数值边界 |
| 前置状态 | 页面、账号资源、解锁条件、服务器和活动日期 |
| 观察证据 | 使用的语义节点/受控视觉信号及置信条件 |
| 输入动作 | 语义动作名称、目标和防误触条件 |
| 预期结果 | 状态机下一状态、持久化变化和停止原因 |
| 异常结果 | 无资源、未解锁、页面变化、网络错误时的 fail-closed 行为 |
| 证据级别 | 离线契约、回放、受控实机或条件边界 |
| 证据位置 | 测试名、trace/evidence 文件和对应提交 |

### 5.2 配置组合压缩规则

- 可以用等价类减少组合数量，但必须写清楚哪些配置共享同一观察和动作路径。
- 只要配置导致不同页面、不同资源消耗、不同舰队选择或不同停止条件，就不能仅凭代码共用而跳过验收。
- 商店、科研、委托等自由过滤器至少验证：首项命中、中间项命中、无命中、fallback、非法 token 和同名商品歧义。
- 资源消费类必须同时验证成功、余额不足、限购/已购、确认取消和重启后幂等性。
- 概率事件使用录制语义树或构造夹具；实机只证明入口与真实页面兼容，不以刷到目标作为自动化测试前提。
- 账号暂不具备条件时保留 `B`，不能把安全停止写成完整支持。

### 5.3 上游变更门禁

本矩阵绑定上述固定上游。以后升级上游时，至少执行以下只读差异检查：

1. 比较 `task.yaml`，发现新增/删除面板或配置组；
2. 比较 `args.json` 与 `template.json`，发现新增字段、枚举值、默认值和显示 override；
3. 新字段默认状态为未验收，不允许继承同组旧状态；
4. 更新本矩阵的总数、面板表和字段级表；
5. 适配代码、离线测试和实机证据全部齐全后再提升状态。

## 6. 配置源快照

| 文件 | SHA-256 | 用途 |
|---|---|---|
| `module/config/argument/task.yaml` | `19E6464AAA1E92913BA9F31DE590096A09B101638969C41E14C70DD1A4EB6C5A` | 60 个侧栏面板及其配置组 |
| `module/config/argument/args.json` | `94A4E553E857E7E3BADA215E08B8963F46D287AC530F32A02B7DAF6B7533AD90` | 当前实际字段、类型、默认值、枚举和显示 override |
| `config/template.json` | `2DE0A47643D9AD73417473F66BE75DADCC1A82E11D405E1F2421ADE3E31EACED` | 用户配置模板和运行时默认值 |

注意：以上哈希来自固定上游 `81ccf63b` 加 authoritative Headless patch series 的确定性重建，不读取或信任可能已经升级、带本地修改的实机 ALAS 工作副本。

### 6.1 单一事实源与校验命令

机器可读账本是 `integration/alas/support-matrix-ledger.json`，本节以下的字段汇总与逐字段表由它确定性生成。`scripts/python/verify_alas_support_matrix.py` 同时校验：面板、字段、面板字段实例、配置源哈希、固定上游、patch series 成员与哈希、状态汇总，以及本轮状态提升所引用的测试/文档证据。

常规校验不修改文件：

```powershell
$env:PYTHONPATH='python'
python scripts/python/verify_alas_support_matrix.py
```

若本机有任意包含固定提交对象的 ALAS Git 仓库，可从固定提交只读提取三份配置源、仅应用 authoritative patch 中的 `args.json` 变更，再复核真实 `60 / 278 / 1,217` 配置面：

```powershell
python scripts/python/verify_alas_support_matrix.py `
  --upstream-repository 'F:\工具箱\AzurLaneAutoScript'
```

账本发生经过证据审阅的修改后，使用 `--write` 重建文档；authoritative series 成员变化后，先使用 `--refresh-patch-series` 只刷新账本里的 series 计数与哈希并重建文档。校验器遇到配置源新增字段会直接失败，并要求先显式加入未支持账本项；不会从同组旧字段继承状态。

## 7. 逐字段生成闭环清单

本表由当前 `args.json` 反查生成，覆盖 278 个唯一配置字段，并通过“使用面板”展开到 1,217 个实际面板字段实例。完整实例路径为 `{面板}.{配置组}.{字段}`；例如 `Main` 面板对应的 `Fleet.Fleet1Formation`，完整路径是 `Main.Fleet.Fleet1Formation`。

`Storage.Storage` 是禁用显示的内部持久化载荷，不是用户功能开关，因此不列入；所有隐藏的 Scheduler 字段和其他隐藏/禁用字段仍然列入。长过滤器默认文本不在表格中重复复制，以配置源快照为准。

复核规则：`组级现状` 只表示第 3 节的总体结论，不表示该字段的所有值已通过。五个复核栏按以下四档标注：

- `☑`：该字段在这一维度的全部公开值和必要异常分支均有证据；
- `◐`：只有当前值、默认值、一个面板实例或一条分支有证据，仍属于部分支持；
- `☐`：尚未找到该字段在这一维度的直接证据；
- `⊘`：当前任务级适配缺失，或已确认该字段在当前上游/Headless 路径中无效；
- `—`：这一维度不适用，例如纯调度字段没有独立 UI 观察或输入动作。

账本初始化审计检查了固定上游配置读取点、Headless patch、当时的 `790/790` 离线测试、配置快照和 2026-08-13 至 2026-08-14 的实机交付记录。`◐` 只证明当时使用的具体值或安全停止分支，不得外推到同字段其他枚举值，也不得外推到“使用面板”列中的其他配置实例。后续提升必须同时增加账本 promotion、存在的证据路径和等价性说明。

### 7.1 字段级审计结论

| 结论 | 字段数 | 含义 |
|---|---:|---|
| ✅ 五维完整支持 | **28 / 278** | 配置、观察、输入、离线和实机五个维度均已完成 |
| ◐ 有实机当前值/分支证据 | **131 / 278** | 至少一个当前值或安全停止分支在实机出现；仍不是完整支持 |
| 🧪 只有离线路径证据 | **97 / 278** | 有设置相关离线覆盖，但没有该设置的实机值证据 |
| ⊘ 当前未适配或无效 | **22 / 278** | 任务级语义端口缺失，或配置当前不产生对应能力 |
| ☐ 只有配置声明/读取 | **0 / 278** | 配置可以存在，但未找到设置相关的 Headless 闭环证据 |

| 配置组.字段 | 使用面板 | 类型/显示元数据 | 默认值与可选值 | 组级现状 | 配置读取 | 语义观察 | 输入闭环 | 离线证据 | 实机证据 |
|---|---|---|---|:---:|:---:|:---:|:---:|:---:|:---:|
| `AddNewStudent.Enable` | Tactical | type=checkbox; display=default | input/default: false | `F`/☑ 完整 | ☑ | ☑ | ☑ | ☑ | ☑ |
| `AddNewStudent.Favorite` | Tactical | type=checkbox; display=default | input/default: false | `F`/☑ 完整 | ☑ | ☑ | ☑ | ☑ | ☑ |
| `AddNewStudent.MinLevel` | Tactical | type=input; display=default | input/default: 50 | `F`/☑ 完整 | ☑ | ☑ | ☑ | ☑ | ☑ |
| `Awaken.Favourite` | Awaken | type=checkbox; display=default | input/default: false | `O`/🧪 离线回放 | ☑ | ☐ | ☐ | ☑ | ☐ |
| `Awaken.LevelCap` | Awaken | type=select; display=default | options: "level120", "level125"; default: "level120" | `O`/🧪 离线回放 | ☑ | ☐ | ☐ | ☑ | ☐ |
| `AzurLaneUncensored.Repository` | AzurLaneUncensored | type=input; display=disabled | input/default: "https://gitee.com/LmeSzinc/AzurLaneUncensored" | `P`/⊘ 当前无效 | ⊘ | ⊘ | ⊘ | ⊘ | ⊘ |
| `BattlePass.Collect` | Freebies | type=checkbox; display=default | input/default: true | `B`/◐ 实机当前值 | ☑ | ◐ | ☐ | ☑ | ◐ |
| `Benchmark.DeviceType` | Benchmark | type=select; display=default | options: "android_phone_vmos", "android_phone", "emulator", "phone_cloud_without_adb", "plone_cloud_with_adb"; default: "emulator" | `F`/☑ 完整 | ☑ | ☑ | ☑ | ☑ | ☑ |
| `Benchmark.TestScene` | Benchmark | type=select; display=default | options: "click", "screenshot_click", "screenshot"; default: "screenshot_click" | `F`/☑ 完整 | ☑ | ☑ | ☑ | ☑ | ☑ |
| `BuyFurniture.BuyOption` | Dorm | type=select; display=default | options: "all", "set"; default: "all" | `P`/◐ set 已购买/all 后置边界 | ☑ | ☑ | ☑ | ☑ | ◐ |
| `BuyFurniture.Enable` | Dorm | type=checkbox; display=default | input/default: false | `P`/◐ 启用购买已闭环 | ☑ | ☑ | ☑ | ☑ | ◐ |
| `BuyFurniture.LastRun` | Dorm | type=datetime; display=default; validate=datetime | input/default: "2020-01-01 00:00:00" | `P`/◐ 实机已写入 | ☑ | ☑ | ☑ | ☑ | ◐ |
| `Campaign.AmbushEvade` | Main, Main2, Main3, GemsFarming, Coalition, Event, Event2, Raid, WarArchives, CoalitionSp, EventA, EventB, EventC, EventD, EventSp, RaidDaily | type=checkbox; display=default/hide | input/default: true | `P`/◐ 实机当前值 | ☑ | ◐ | ☐ | ☑ | ◐ |
| `Campaign.Event` | Main, Main2, Main3, GemsFarming, Coalition, Event, Event2, Raid, WarArchives, CoalitionSp, EventA, EventB, EventC, EventD, EventSp, RaidDaily | type=select; display=default/hide | options: "campaign_main", "coalition_20260723", "event_20260625_cn", "event_20260813_cn", "raid_20260212", "war_archives_20180607_cn", "war_archives_20180726_cn", "war_archives_20181020_en", "war_archives_20181026_en", "war_archives_20181227_cn", "war_archives_20190221_en", "war_archives_20190314_en", "war_archives_20190321_en", "war_archives_20190620_en", "war_archives_20190911_cn", "war_archives_20191010_en", "war_archives_20191031_en", "war_archives_20200312_cn", "war_archives_20200507_cn", "war_archives_20200603_cn", "war_archives_20200806_cn", "war_archives_20200820_cn", "war_archives_20200903_cn", "war_archives_20200917_cn", "war_archives_20201012_cn", "war_archives_20201029_cn", "war_archives_20201229_cn", "war_archives_20210225_cn", "war_archives_20210325_cn", "war_archives_20210422_cn", "war_archives_20210527_cn", "war_archives_20210624_cn", "war_archives_20210819_cn", "war_archives_20210916_cn", "war_archives_20211014_cn", "war_archives_20211028_cn", "war_archives_20211111_cn", "war_archives_20211229_cn", "war_archives_20220210_cn", "war_archives_20220224_cn", "war_archives_20220324_cn", "war_archives_20220414_cn", "war_archives_20220428_cn", "war_archives_20220526_cn", "war_archives_20220728_cn", "war_archives_20220818_cn", "war_archives_20220915_cn", "war_archives_20221222_cn", "war_archives_20230223_cn", "war_archives_20230525_cn", "war_archives_20230803_cn", "war_archives_20231026_cn", "war_archives_20240725_cn"; default: "campaign_main" | `P`/🧪 三主线常规路由 | ☑ | ◐ | ◐ | ◐ | ◐ |
| `Campaign.Mode` | Main, Main2, Main3, GemsFarming, Coalition, Event, Event2, Raid, WarArchives, CoalitionSp, EventA, EventB, EventC, EventD, EventSp, RaidDaily | type=select; display=default/hide | options: "hard", "normal"; default: "normal" | `P`/🧪 三主线常规路由 | ☑ | ◐ | ◐ | ◐ | ◐ |
| `Campaign.Name` | Main, Main2, Main3, GemsFarming, Coalition, Event, Event2, Raid, WarArchives, CoalitionSp, EventA, EventB, EventC, EventD, EventSp, RaidDaily | type=input; display=default/hide | input/default: "12-4", "dynamic", "sp" | `P`/🧪 三主线 64 图路由 | ☑ | ◐ | ◐ | ◐ | ◐ |
| `Campaign.Use2xBook` | Main, Main2, Main3, GemsFarming, Coalition, Event, Event2, Raid, WarArchives, CoalitionSp, EventA, EventB, EventC, EventD, EventSp, RaidDaily | type=checkbox; display=default/hide | input/default: false | `P`/◐ 实机当前值 | ☑ | ◐ | ☐ | ☑ | ◐ |
| `Campaign.UseAutoSearch` | Main, Main2, Main3, GemsFarming, Coalition, Event, Event2, Raid, WarArchives, CoalitionSp, EventA, EventB, EventC, EventD, EventSp, RaidDaily | type=checkbox; display=default/hide | input/default: false, true | `P`/◐ 实机当前值 | ☑ | ◐ | ◐ | ☑ | ◐ |
| `Campaign.UseClearMode` | Main, Main2, Main3, GemsFarming, Coalition, Event, Event2, Raid, WarArchives, CoalitionSp, EventA, EventB, EventC, EventD, EventSp, RaidDaily | type=checkbox; display=default/hide | input/default: true | `P`/◐ 实机当前值 | ☑ | ◐ | ☐ | ☑ | ◐ |
| `Campaign.UseFleetLock` | Main, Main2, Main3, GemsFarming, Coalition, Event, Event2, Raid, WarArchives, CoalitionSp, EventA, EventB, EventC, EventD, EventSp, RaidDaily | type=checkbox; display=default/hide | input/default: true | `P`/◐ 实机当前值 | ☑ | ◐ | ◐ | ☑ | ◐ |
| `Coalition.Fleet` | Coalition, CoalitionSp | type=select; display=default | options: "multi", "single"; default: "single" | `O`/🧪 离线回放 | ☑ | ☐ | ☐ | ☑ | ☐ |
| `Coalition.Mode` | Coalition, CoalitionSp | type=select; display=default/hide | options: "easy", "hard", "normal", "sp"; default: "hard", "sp" | `O`/🧪 离线回放 | ☑ | ☐ | ☐ | ☑ | ☐ |
| `Commission.CustomFilter` | Commission | type=textarea; display=default | input/default: <long default in args.json> | `F`/☑ 完整 | ☑ | ☑ | ☑ | ☑ | ☑ |
| `Commission.DoMajorCommission` | Commission | type=checkbox; display=default | input/default: false | `F`/☑ 完整 | ☑ | ☑ | ☑ | ☑ | ☑ |
| `Commission.PresetFilter` | Commission | type=select; display=default | options: "chip_24h", "chip", "cube_24h", "cube", "custom", "oil"; default: "cube" | `F`/☑ 完整 | ☑ | ☑ | ☑ | ☑ | ☑ |
| `ControlExpOverflow.Enable` | Tactical | type=checkbox; display=default | input/default: true | `P`/☑ 完整 | ☑ | ☑ | ☑ | ☑ | ☑ |
| `ControlExpOverflow.T1Allow` | Tactical | type=input; display=default | input/default: 200 | `P`/☑ 完整 | ☑ | ☑ | ☑ | ☑ | ☑ |
| `ControlExpOverflow.T2Allow` | Tactical | type=input; display=default | input/default: 200 | `P`/☑ 完整 | ☑ | ☑ | ☑ | ☑ | ☑ |
| `ControlExpOverflow.T3Allow` | Tactical | type=input; display=default | input/default: 100 | `P`/☑ 完整 | ☑ | ☑ | ☑ | ☑ | ☑ |
| `ControlExpOverflow.T4Allow` | Tactical | type=input; display=default | input/default: 100 | `P`/☑ 完整 | ☑ | ☑ | ☑ | ☑ | ☑ |
| `CoreShop.Filter` | ShopOnce | type=textarea; display=default | input/default: "Array" | `M`/⊘ 未适配 | ☑ | ⊘ | ⊘ | ⊘ | ⊘ |
| `Daemon.EnterMap` | Daemon | type=checkbox; display=default | input/default: true | `P`/◐ 实机当前值 | ☑ | ◐ | ☐ | ☑ | ◐ |
| `Daily.AdvanceMission` | Daily | type=select; display=default | options: "first", "second", "skip", "third"; default: "first" | `L`/☐ 未逐值 | ☑ | ☐ | ☐ | ☑ | ☐ |
| `Daily.AdvanceMissionFleet` | Daily | type=select; display=default | options: 1, 2, 3, 4, 5, 6; default: 1 | `L`/☐ 未逐值 | ☑ | ☐ | ☐ | ☑ | ☐ |
| `Daily.EmergencyModuleDevelopment` | Daily | type=select; display=default | options: "first", "second", "skip"; default: "first" | `L`/☐ 未逐值 | ☑ | ☐ | ☐ | ☑ | ☐ |
| `Daily.EmergencyModuleDevelopmentFleet` | Daily | type=select; display=default | options: 1, 2, 3, 4, 5, 6; default: 1 | `L`/☐ 未逐值 | ☑ | ☐ | ☐ | ☑ | ☐ |
| `Daily.EscortMission` | Daily | type=select; display=default | options: "first", "second", "skip", "third"; default: "first" | `L`/☐ 未逐值 | ☑ | ☐ | ☐ | ☑ | ☐ |
| `Daily.EscortMissionFleet` | Daily | type=select; display=default | options: 1, 2, 3, 4, 5, 6; default: 1 | `L`/☐ 未逐值 | ☑ | ☐ | ☐ | ☑ | ☐ |
| `Daily.FierceAssault` | Daily | type=select; display=default | options: "first", "second", "skip", "third"; default: "first" | `L`/☐ 未逐值 | ☑ | ☐ | ☐ | ☑ | ☐ |
| `Daily.FierceAssaultFleet` | Daily | type=select; display=default | options: 1, 2, 3, 4, 5, 6; default: 1 | `L`/☐ 未逐值 | ☑ | ☐ | ☐ | ☑ | ☐ |
| `Daily.ModuleDevelopment` | Daily | type=select; display=default | options: "first", "second", "skip"; default: "first" | `L`/☐ 未逐值 | ☑ | ☐ | ☐ | ☑ | ☐ |
| `Daily.ModuleDevelopmentFleet` | Daily | type=select; display=default | options: 1, 2, 3, 4, 5, 6; default: 1 | `L`/☐ 未逐值 | ☑ | ☐ | ☐ | ☑ | ☐ |
| `Daily.SupplyLineDisruption` | Daily | type=select; display=default | options: "first", "second", "skip", "third"; default: "second" | `L`/☐ 未逐值 | ☑ | ☐ | ☐ | ☑ | ☐ |
| `Daily.TacticalTraining` | Daily | type=select; display=default | options: "first", "second", "skip", "third"; default: "second" | `L`/◐ 实机当前值 | ☑ | ◐ | ◐ | ☑ | ◐ |
| `Daily.TacticalTrainingFleet` | Daily | type=select; display=default | options: 1, 2, 3, 4, 5, 6; default: 1 | `L`/◐ 实机当前值 | ☑ | ◐ | ◐ | ☑ | ◐ |
| `Daily.UseDailySkip` | Daily | type=checkbox; display=default | input/default: true | `L`/◐ 实机当前值 | ☑ | ◐ | ☐ | ☑ | ◐ |
| `DataKey.Collect` | Freebies | type=checkbox; display=default | input/default: true | `L`/◐ 实机当前值 | ☑ | ◐ | ☐ | ☑ | ◐ |
| `DataKey.ForceCollect` | Freebies | type=checkbox; display=default | input/default: false | `L`/◐ 实机当前值 | ☑ | ◐ | ☐ | ☑ | ◐ |
| `Dorm.Collect` | Dorm | type=checkbox; display=default | input/default: true | `L`/☑ 完整 | ☑ | ☑ | ☑ | ☑ | ☑ |
| `Dorm.Feed` | Dorm | type=checkbox; display=default | input/default: true | `L`/☑ 完整 | ☑ | ☑ | ☑ | ☑ | ☑ |
| `Dorm.FeedFilter` | Dorm | type=textarea; display=default | input/default: "20000 > 10000 > 5000 > 3000 > 2000 > 1000" | `L`/☑ 完整 | ☑ | ☑ | ☑ | ☑ | ☑ |
| `DropRecord.API` | Alas | type=select; display=default | options: "cn_gz_reverse_proxy", "default"; default: "default" | `M`/⊘ 未适配 | ☑ | ⊘ | ⊘ | ⊘ | ⊘ |
| `DropRecord.AzurStatsID` | Alas | type=input; display=default | input/default: null | `M`/⊘ 未适配 | ☑ | ⊘ | ⊘ | ⊘ | ⊘ |
| `DropRecord.CombatRecord` | Alas | type=select; display=default | options: "do_not", "save"; default: "do_not" | `M`/⊘ 未适配 | ☑ | ⊘ | ⊘ | ⊘ | ⊘ |
| `DropRecord.CommissionRecord` | Alas | type=select; display=default | options: "do_not", "save_and_upload", "save", "upload"; default: "do_not" | `M`/⊘ 未适配 | ☑ | ⊘ | ⊘ | ⊘ | ⊘ |
| `DropRecord.MeowfficerBuy` | Alas | type=select; display=default | options: "do_not", "save"; default: "do_not" | `M`/⊘ 未适配 | ☑ | ⊘ | ⊘ | ⊘ | ⊘ |
| `DropRecord.MeowfficerTalent` | Alas | type=select; display=default | options: "do_not", "save_and_upload", "save", "upload"; default: "do_not" | `M`/⊘ 未适配 | ☑ | ⊘ | ⊘ | ⊘ | ⊘ |
| `DropRecord.OpsiRecord` | Alas | type=select; display=default | options: "do_not", "save_and_upload", "save", "upload"; default: "do_not" | `M`/⊘ 未适配 | ☑ | ⊘ | ⊘ | ⊘ | ⊘ |
| `DropRecord.ResearchRecord` | Alas | type=select; display=default | options: "do_not", "save_and_upload", "save", "upload"; default: "do_not" | `M`/⊘ 未适配 | ☑ | ⊘ | ⊘ | ⊘ | ⊘ |
| `DropRecord.SaveFolder` | Alas | type=input; display=default | input/default: "./screenshots" | `M`/⊘ 未适配 | ☑ | ⊘ | ⊘ | ⊘ | ⊘ |
| `Emotion.Fleet1Control` | Main, Main2, Main3, GemsFarming, Coalition, Event, Event2, Raid, Hospital, WarArchives, CoalitionSp, EventA, EventB, EventC, EventD, EventSp, RaidDaily | type=select; display=default/hide | options: "keep_exp_bonus", "prevent_green_face", "prevent_red_face", "prevent_yellow_face"; default: "prevent_green_face", "prevent_red_face", "prevent_yellow_face" | `P`/◐ 实机当前值 | ☑ | ◐ | ☐ | ☑ | ◐ |
| `Emotion.Fleet1Oath` | Main, Main2, Main3, GemsFarming, Coalition, Event, Event2, Raid, Hospital, WarArchives, CoalitionSp, EventA, EventB, EventC, EventD, EventSp, RaidDaily | type=checkbox; display=default/hide | input/default: false | `P`/◐ 实机当前值 | ☑ | ◐ | ☐ | ☑ | ◐ |
| `Emotion.Fleet1Record` | Main, Main2, Main3, GemsFarming, Coalition, Event, Event2, Raid, Hospital, WarArchives, CoalitionSp, EventA, EventB, EventC, EventD, EventSp, RaidDaily | type=datetime; display=disabled; validate=datetime | input/default: "2020-01-01 00:00:00" | `P`/◐ 实机当前值 | ☑ | ◐ | ☐ | ☑ | ◐ |
| `Emotion.Fleet1Recover` | Main, Main2, Main3, GemsFarming, Coalition, Event, Event2, Raid, Hospital, WarArchives, CoalitionSp, EventA, EventB, EventC, EventD, EventSp, RaidDaily | type=select; display=default/hide | options: "dormitory_floor_1", "dormitory_floor_2", "not_in_dormitory"; default: "not_in_dormitory" | `P`/◐ 实机当前值 | ☑ | ◐ | ☐ | ☑ | ◐ |
| `Emotion.Fleet1Value` | Main, Main2, Main3, GemsFarming, Coalition, Event, Event2, Raid, Hospital, WarArchives, CoalitionSp, EventA, EventB, EventC, EventD, EventSp, RaidDaily | type=input; display=default | input/default: 119 | `P`/◐ 实机当前值 | ☑ | ◐ | ☐ | ☑ | ◐ |
| `Emotion.Fleet2Control` | Main, Main2, Main3, GemsFarming, Coalition, Event, Event2, Raid, Hospital, WarArchives, CoalitionSp, EventA, EventB, EventC, EventD, EventSp, RaidDaily | type=select; display=default/hide | options: "keep_exp_bonus", "prevent_green_face", "prevent_red_face", "prevent_yellow_face"; default: "prevent_green_face", "prevent_red_face", "prevent_yellow_face" | `P`/◐ 实机当前值 | ☑ | ◐ | ☐ | ☑ | ◐ |
| `Emotion.Fleet2Oath` | Main, Main2, Main3, GemsFarming, Coalition, Event, Event2, Raid, Hospital, WarArchives, CoalitionSp, EventA, EventB, EventC, EventD, EventSp, RaidDaily | type=checkbox; display=default/hide | input/default: false | `P`/◐ 实机当前值 | ☑ | ◐ | ☐ | ☑ | ◐ |
| `Emotion.Fleet2Record` | Main, Main2, Main3, GemsFarming, Coalition, Event, Event2, Raid, Hospital, WarArchives, CoalitionSp, EventA, EventB, EventC, EventD, EventSp, RaidDaily | type=datetime; display=disabled/hide; validate=datetime | input/default: "2020-01-01 00:00:00" | `P`/◐ 实机当前值 | ☑ | ◐ | ☐ | ☑ | ◐ |
| `Emotion.Fleet2Recover` | Main, Main2, Main3, GemsFarming, Coalition, Event, Event2, Raid, Hospital, WarArchives, CoalitionSp, EventA, EventB, EventC, EventD, EventSp, RaidDaily | type=select; display=default/hide | options: "dormitory_floor_1", "dormitory_floor_2", "not_in_dormitory"; default: "not_in_dormitory" | `P`/◐ 实机当前值 | ☑ | ◐ | ☐ | ☑ | ◐ |
| `Emotion.Fleet2Value` | Main, Main2, Main3, GemsFarming, Coalition, Event, Event2, Raid, Hospital, WarArchives, CoalitionSp, EventA, EventB, EventC, EventD, EventSp, RaidDaily | type=input; display=default/hide | input/default: 119 | `P`/◐ 实机当前值 | ☑ | ◐ | ☐ | ☑ | ◐ |
| `Emotion.Mode` | Main, Main2, Main3, GemsFarming, Coalition, Event, Event2, Raid, Hospital, WarArchives, CoalitionSp, EventA, EventB, EventC, EventD, EventSp, RaidDaily | type=select; display=default/hide | options: "calculate_ignore", "calculate", "ignore"; default: "calculate_ignore", "calculate" | `P`/◐ 实机当前值 | ☑ | ◐ | ☐ | ☑ | ◐ |
| `Emulator.AdbRestart` | Alas | type=checkbox; display=default | input/default: false | `P`/☐ 未逐值 | ☑ | ☐ | ☐ | ☑ | ☐ |
| `Emulator.ControlMethod` | Alas | type=select; display=default | options: "ADB", "Hermit", "MaaTouch", "minitouch", "uiautomator2"; default: "MaaTouch" | `P`/◐ 实机当前值 | ☑ | ◐ | ☐ | ◐ | ◐ |
| `Emulator.PackageName` | Alas | type=select; display=default | options: "auto", "com.bilibili.azurlane", "com.bilibili.blhx.baidu", "com.bilibili.blhx.bilibiliMove", "com.bilibili.blhx.dl", "com.bilibili.blhx.honor", "com.bilibili.blhx.huawei", "com.bilibili.blhx.lenovo", "com.bilibili.blhx.m4399", "com.bilibili.blhx.mi", "com.bilibili.blhx.mz", "com.bilibili.blhx.mzw", "com.bilibili.blhx.nearme.gamecenter", "com.bilibili.blhx.qihoo", "com.bilibili.blhx.uc", "com.bilibili.blhx.vivo", "com.hkmanjuu.azurlane.gp.mc", "com.hkmanjuu.azurlane.gp", "com.tencent.tmgp.bilibili.blhx", "com.yiwu.blhx.yx15", "com.YoStarEN.AzurLane", "com.YoStarJP.AzurLane"; default: "auto" | `P`/◐ 实机当前值 | ☑ | ◐ | ☐ | ☑ | ◐ |
| `Emulator.ScreenshotDedithering` | Alas | type=checkbox; display=default | input/default: false | `P`/◐ 实机当前值 | ☑ | ◐ | ☐ | ☑ | ◐ |
| `Emulator.ScreenshotMethod` | Alas | type=select; display=default | options: "ADB_nc", "ADB", "aScreenCap_nc", "aScreenCap", "auto", "DroidCast_raw", "DroidCast", "ldopengl", "nemu_ipc", "uiautomator2"; default: "auto" | `P`/◐ 实机当前值 | ☑ | ◐ | ☐ | ◐ | ◐ |
| `Emulator.Serial` | Alas | type=input; display=default | input/default: "auto" | `P`/◐ 实机当前值 | ☑ | ◐ | ☐ | ◐ | ◐ |
| `Emulator.ServerName` | Alas | type=select; display=default | options: "cn_android-0", "cn_android-1", "cn_android-10", "cn_android-11", "cn_android-12", "cn_android-13", "cn_android-14", "cn_android-15", "cn_android-16", "cn_android-17", "cn_android-18", "cn_android-19", "cn_android-2", "cn_android-20", "cn_android-21", "cn_android-22", "cn_android-23", "cn_android-24", "cn_android-25", "cn_android-26", "cn_android-27", "cn_android-28", "cn_android-29", "cn_android-3", "cn_android-4", "cn_android-5", "cn_android-6", "cn_android-7", "cn_android-8", "cn_android-9", "cn_channel-0", "cn_channel-1", "cn_channel-2", "cn_channel-3", "cn_channel-4", "cn_channel-5", "cn_ios-0", "cn_ios-1", "cn_ios-10", "cn_ios-2", "cn_ios-3", "cn_ios-4", "cn_ios-5", "cn_ios-6", "cn_ios-7", "cn_ios-8", "cn_ios-9", "disabled", "en-0", "en-1", "en-2", "en-3", "en-4", "en-5", "jp-0", "jp-1", "jp-10", "jp-11", "jp-12", "jp-13", "jp-14", "jp-15", "jp-16", "jp-17", "jp-2", "jp-3", "jp-4", "jp-5", "jp-6", "jp-7", "jp-8", "jp-9"; default: "disabled" | `P`/☐ 未逐值 | ☑ | ☐ | ☐ | ☑ | ☐ |
| `EmulatorInfo.Emulator` | Alas | type=select; display=default | options: "auto", "BlueStacks4", "BlueStacks4HyperV", "BlueStacks5", "BlueStacks5HyperV", "LDPlayer14", "LDPlayer3", "LDPlayer4", "LDPlayer9", "MEmuPlayer", "MuMuPlayer", "MuMuPlayer12", "MuMuPlayerX", "NoxPlayer", "NoxPlayer64"; default: "auto" | `P`/☐ 未逐值 | ☑ | ☐ | ☐ | ☑ | ☐ |
| `EmulatorInfo.name` | Alas | type=textarea; display=default | input/default: null | `P`/☐ 未逐值 | ☑ | ☐ | ☐ | ☑ | ☐ |
| `EmulatorInfo.path` | Alas | type=textarea; display=default | input/default: null | `P`/☐ 未逐值 | ☑ | ☐ | ☐ | ☑ | ☐ |
| `EnemyPriority.EnemyScaleBalanceWeight` | Main, Main2, Main3, Event, Event2, WarArchives, EventA, EventB, EventC, EventD, EventSp | type=select; display=default | options: "default_mode", "S1_enemy_first", "S3_enemy_first"; default: "default_mode" | `P`/◐ 实机当前值 | ☑ | ◐ | ◐ | ☑ | ◐ |
| `Enhance.CheckPerCategory` | General | type=input; display=default | input/default: 5 | `P`/◐ 正式任务循环已接入 | ☑ | ☑ | ☑ | ☑ | ◐ |
| `Enhance.Filter` | General | type=textarea; display=default | input/default: null | `P`/☑ 完整 | ☑ | ☑ | ☑ | ☑ | ☑ |
| `Enhance.ShipToEnhance` | General | type=select; display=default | options: "all", "favourite"; default: "all" | `P`/☑ 完整 | ☑ | ☑ | ☑ | ☑ | ☑ |
| `EquipmentCode.Config` | GemsFarming | type=textarea; display=default | input/default:…4672 tokens truncated…t" | `B`/☐ 未逐值 | ☑ | ☐ | ☐ | ☑ | ☐ |
| `EquipmentCode.ExportToConfig` | GemsFarming | type=checkbox; display=default | input/default: true | `M`/⊘ 未适配 | ☑ | ⊘ | ⊘ | ⊘ | ⊘ |
| `Error.HandleError` | Alas | type=checkbox; display=default | input/default: true | `P`/☐ 未逐值 | ☑ | ☐ | ☐ | ☑ | ☐ |
| `Error.OnePushConfig` | Alas | type=textarea; display=default | input/default: "provider: null" | `P`/☐ 未逐值 | ☑ | ☐ | ☐ | ☑ | ☐ |
| `Error.SaveError` | Alas | type=checkbox; display=default | input/default: true | `P`/☐ 未逐值 | ☑ | ☐ | ☐ | ☑ | ☐ |
| `Error.ScreenshotLength` | Alas | type=input; display=default | input/default: 1 | `P`/☐ 未逐值 | ☑ | ☐ | ☐ | ☑ | ☐ |
| `EventDaily.LastStage` | EventA, EventB, EventC, EventD | type=input; display=default | input/default: 0 | `P`/◐ 实机当前值 | ☑ | ◐ | ☐ | ☑ | ◐ |
| `EventDaily.StageFilter` | EventA, EventB, EventC, EventD | type=textarea; display=default | input/default: "A1 > A2 > A3", "B1 > B2 > B3", "C1 > C2 > C3", "D1 > D2 > D3" | `P`/◐ 实机当前值 | ☑ | ◐ | ◐ | ☑ | ◐ |
| `EventGeneral.PtLimit` | EventGeneral | type=input; display=default | input/default: 0 | `P`/☐ 未逐值 | ☑ | ☐ | ☐ | ☑ | ☐ |
| `EventGeneral.TimeLimit` | EventGeneral | type=datetime; display=default; validate=datetime | input/default: "2020-01-01 00:00:00" | `P`/☐ 未逐值 | ☑ | ☐ | ☐ | ☑ | ☐ |
| `EventStory.SkipBattle` | EventStory | type=lock; display=default | options: true; default: true | `P`/◐ 实机当前值 | ◐ | ◐ | ◐ | ◐ | ◐ |
| `Exercise.ExerciseStrategy` | Exercise | type=select; display=default | options: "aggressive", "fri18", "sat0", "sat12", "sat18", "sun0", "sun12", "sun18"; default: "aggressive" | `L`/◐ 实机当前值 | ☑ | ◐ | ◐ | ☑ | ◐ |
| `Exercise.LowHpConfirmWait` | Exercise | type=input; display=default | input/default: 0.1 | `L`/⊘ 未适配 | ☑ | ⊘ | ⊘ | ⊘ | ⊘ |
| `Exercise.LowHpThreshold` | Exercise | type=input; display=default | input/default: 0.4 | `L`/☐ 未逐值 | ☑ | ☐ | ☐ | ☑ | ☐ |
| `Exercise.OpponentChooseMode` | Exercise | type=select; display=default | options: "easiest_else_exp", "easiest", "leftmost", "max_exp"; default: "max_exp" | `L`/◐ 实机当前值 | ☑ | ◐ | ◐ | ☑ | ◐ |
| `Exercise.OpponentRefreshRecord` | Exercise | type=datetime; display=default; validate=datetime | input/default: "2020-01-01 00:00:00" | `L`/◐ 实机当前值 | ☑ | ◐ | ☐ | ☑ | ◐ |
| `Exercise.OpponentRefreshValue` | Exercise | type=input; display=default | input/default: 0 | `L`/◐ 实机当前值 | ☑ | ◐ | ☐ | ☑ | ◐ |
| `Exercise.OpponentTrial` | Exercise | type=input; display=default | input/default: 1 | `L`/◐ 实机当前值 | ☑ | ◐ | ◐ | ☑ | ◐ |
| `Fleet.Fleet1` | Main, Main2, Main3, GemsFarming, Event, Event2, WarArchives, EventA, EventB, EventC, EventD, EventSp | type=select; display=default | options: 1, 2, 3, 4, 5, 6; default: 1 | `P`/◐ 实机当前值 | ☑ | ◐ | ◐ | ☑ | ◐ |
| `Fleet.Fleet1Formation` | Main, Main2, Main3, GemsFarming, Event, Event2, WarArchives, EventA, EventB, EventC, EventD, EventSp | type=select; display=default | options: "diamond", "double_line", "line_ahead"; default: "double_line" | `P`/◐ 实机当前值 | ☑ | ◐ | ◐ | ☑ | ◐ |
| `Fleet.Fleet1Mode` | Main, Main2, Main3, GemsFarming, Event, Event2, WarArchives, EventA, EventB, EventC, EventD, EventSp | type=select; display=default | options: "combat_auto", "combat_manual", "hide_in_bottom_left", "hide_in_upper_left", "stand_still_in_the_middle"; default: "combat_auto" | `P`/◐ 实机当前值 | ☑ | ◐ | ◐ | ☑ | ◐ |
| `Fleet.Fleet1Step` | Main, Main2, Main3, GemsFarming, Event, Event2, WarArchives, EventA, EventB, EventC, EventD, EventSp | type=select; display=default | options: 2, 3, 4, 5; default: 3 | `P`/◐ 实机当前值 | ☑ | ◐ | ◐ | ☑ | ◐ |
| `Fleet.Fleet2` | Main, Main2, Main3, GemsFarming, Event, Event2, WarArchives, EventA, EventB, EventC, EventD, EventSp | type=select; display=default | options: 0, 1, 2, 3, 4, 5, 6; default: 2 | `P`/◐ 实机当前值 | ☑ | ◐ | ◐ | ☑ | ◐ |
| `Fleet.Fleet2Formation` | Main, Main2, Main3, GemsFarming, Event, Event2, WarArchives, EventA, EventB, EventC, EventD, EventSp | type=select; display=default | options: "diamond", "double_line", "line_ahead"; default: "double_line" | `P`/◐ 实机当前值 | ☑ | ◐ | ◐ | ☑ | ◐ |
| `Fleet.Fleet2Mode` | Main, Main2, Main3, GemsFarming, Event, Event2, WarArchives, EventA, EventB, EventC, EventD, EventSp | type=select; display=default | options: "combat_auto", "combat_manual", "hide_in_bottom_left", "hide_in_upper_left", "stand_still_in_the_middle"; default: "combat_auto" | `P`/◐ 实机当前值 | ☑ | ◐ | ◐ | ☑ | ◐ |
| `Fleet.Fleet2Step` | Main, Main2, Main3, GemsFarming, Event, Event2, WarArchives, EventA, EventB, EventC, EventD, EventSp | type=select; display=default | options: 2, 3, 4, 5; default: 2 | `P`/◐ 实机当前值 | ☑ | ◐ | ◐ | ☑ | ◐ |
| `Fleet.FleetOrder` | Main, Main2, Main3, GemsFarming, Event, Event2, WarArchives, EventA, EventB, EventC, EventD, EventSp | type=select; display=default/display | options: "fleet1_all_fleet2_standby", "fleet1_boss_fleet2_mob", "fleet1_mob_fleet2_boss", "fleet1_standby_fleet2_all"; default: "fleet1_all_fleet2_standby", "fleet1_mob_fleet2_boss" | `P`/◐ 实机当前值 | ☑ | ◐ | ◐ | ☑ | ◐ |
| `Gacha.Amount` | Gacha | type=select; display=default | options: 1, 10, 2, 3, 4, 5, 6, 7, 8, 9; default: 1 | `F`/☑ 完整 | ☑ | ☑ | ☑ | ☑ | ☑ |
| `Gacha.Pool` | Gacha | type=select; display=default | options: "event", "heavy", "light", "special", "wishing_well"; default: "light" | `F`/☑ 完整 | ☑ | ☑ | ☑ | ☑ | ☑ |
| `Gacha.UseDrill` | Gacha | type=checkbox; display=default | input/default: false | `F`/☑ 完整 | ☑ | ☑ | ☑ | ☑ | ☑ |
| `Gacha.UseTicket` | Gacha | type=checkbox; display=default | input/default: true | `L`/◐ 实机当前值 | ☑ | ◐ | ☐ | ☑ | ◐ |
| `GameManager.AutoRestart` | GameManager | type=checkbox; display=default | input/default: true | `F`/☑ 完整 | ☑ | ☑ | ☑ | ☑ | ☑ |
| `GemsFarming.ChangeFlagship` | GemsFarming | type=select; display=default | options: "ship_equip", "ship"; default: "ship" | `M`/🧪 仅离线完成 | ☑ | ☐ | ☐ | ☑ | ☐ |
| `GemsFarming.ChangeVanguard` | GemsFarming | type=select; display=default | options: "disabled", "ship_equip", "ship"; default: "ship" | `M`/🧪 仅离线完成 | ☑ | ☐ | ☐ | ☑ | ☐ |
| `GemsFarming.CommissionLimit` | GemsFarming | type=checkbox; display=default | input/default: true | `M`/🧪 仅离线完成 | ☑ | ☐ | ☐ | ☑ | ☐ |
| `GemsFarming.CommonCV` | GemsFarming | type=select; display=default | options: "any", "bogue", "hermes", "langley", "ranger"; default: "any" | `M`/🧪 仅离线完成 | ☑ | ☐ | ☐ | ☑ | ☐ |
| `GemsFarming.CommonDD` | GemsFarming | type=select; display=default | options: "any", "aulick_or_foote", "cassin_or_downes", "favourite", "z20_or_z21"; default: "any" | `M`/🧪 仅离线完成 | ☑ | ☐ | ☐ | ☑ | ☐ |
| `GeneralShop.BuySkinBox` | ShopFrequent | type=checkbox; display=default | input/default: false | `B`/◐ 实机当前值 | ☑ | ◐ | ☐ | ☑ | ◐ |
| `GeneralShop.ConsumeCoins` | ShopFrequent | type=checkbox; display=default | input/default: false | `B`/◐ 实机当前值 | ☑ | ◐ | ☐ | ☑ | ◐ |
| `GeneralShop.Filter` | ShopFrequent | type=textarea; display=default | input/default: "BookRedT3 > BookYellowT3 > BookBlueT3 > BookRedT2\n> Cube\n> FoodT6 > FoodT5" | `B`/◐ 实机当前值 | ☑ | ◐ | ☐ | ☑ | ◐ |
| `GeneralShop.Refresh` | ShopFrequent | type=checkbox; display=default | input/default: false | `B`/◐ 实机当前值 | ☑ | ◐ | ☐ | ☑ | ◐ |
| `GeneralShop.UseGems` | ShopFrequent | type=checkbox; display=default | input/default: false | `B`/◐ 实机当前值 | ☑ | ◐ | ☐ | ☑ | ◐ |
| `GuildLogistics.Enable` | Guild | type=checkbox; display=default | input/default: true | `O`/🧪 仅离线完成 | ☑ | ☐ | ☐ | ☑ | ☐ |
| `GuildLogistics.ExchangeFilter` | Guild | type=textarea; display=default | input/default: <long default in args.json> | `O`/🧪 仅离线完成 | ☑ | ☐ | ☐ | ☑ | ☐ |
| `GuildLogistics.SelectNewMission` | Guild | type=checkbox; display=default | input/default: false | `O`/🧪 仅离线完成 | ☑ | ☐ | ☐ | ☑ | ☐ |
| `GuildOperation.AttackBoss` | Guild | type=checkbox; display=default | input/default: true | `O`/🧪 仅离线完成 | ☑ | ☐ | ☐ | ☑ | ☐ |
| `GuildOperation.BossFleetRecommend` | Guild | type=checkbox; display=default | input/default: false | `O`/🧪 仅离线完成 | ☑ | ☐ | ☐ | ☑ | ☐ |
| `GuildOperation.Enable` | Guild | type=checkbox; display=default | input/default: true | `O`/🧪 仅离线完成 | ☑ | ☐ | ☐ | ☑ | ☐ |
| `GuildOperation.JoinThreshold` | Guild | type=input; display=default | input/default: 1 | `O`/🧪 仅离线完成 | ☑ | ☐ | ☐ | ☑ | ☐ |
| `GuildOperation.NewOperationMaxDate` | Guild | type=input; display=default | input/default: 15 | `O`/🧪 仅离线完成 | ☑ | ☐ | ☐ | ☑ | ☐ |
| `GuildOperation.SelectNewOperation` | Guild | type=checkbox; display=default | input/default: false | `O`/🧪 仅离线完成 | ☑ | ☐ | ☐ | ☑ | ☐ |
| `GuildShop.BOOK_T2` | ShopOnce | type=select; display=default | options: "blue", "red", "yellow"; default: "red" | `P`/☐ 未逐值 | ☑ | ☐ | ☐ | ☑ | ☐ |
| `GuildShop.BOOK_T3` | ShopOnce | type=select; display=default | options: "blue", "red", "yellow"; default: "red" | `P`/☐ 未逐值 | ☑ | ☐ | ☐ | ☑ | ☐ |
| `GuildShop.BOX_T3` | ShopOnce | type=select; display=default | options: "eagle", "ironblood", "royal", "sakura"; default: "ironblood" | `P`/☐ 未逐值 | ☑ | ☐ | ☐ | ☑ | ☐ |
| `GuildShop.BOX_T4` | ShopOnce | type=select; display=default | options: "eagle", "ironblood", "royal", "sakura"; default: "ironblood" | `P`/☐ 未逐值 | ☑ | ☐ | ☐ | ☑ | ☐ |
| `GuildShop.Filter` | ShopOnce | type=textarea; display=default | input/default: <long default in args.json> | `P`/◐ 实机当前值 | ☑ | ◐ | ☐ | ☑ | ◐ |
| `GuildShop.PLATE_T2` | ShopOnce | type=select; display=default | options: "antiair", "general", "gun", "plane", "torpedo"; default: "general" | `P`/☐ 未逐值 | ☑ | ☐ | ☐ | ☑ | ☐ |
| `GuildShop.PLATE_T3` | ShopOnce | type=select; display=default | options: "antiair", "general", "gun", "plane", "torpedo"; default: "general" | `P`/☐ 未逐值 | ☑ | ☐ | ☐ | ☑ | ☐ |
| `GuildShop.PLATE_T4` | ShopOnce | type=select; display=default | options: "antiair", "general", "gun", "plane", "torpedo"; default: "gun" | `P`/☐ 未逐值 | ☑ | ☐ | ☐ | ☑ | ☐ |
| `GuildShop.PR1` | ShopOnce | type=select; display=default | options: "ibuki", "izumo", "monarch", "neptune", "roon", "saintlouis"; default: "neptune" | `P`/☐ 未逐值 | ☑ | ☐ | ☐ | ☑ | ☐ |
| `GuildShop.PR2` | ShopOnce | type=select; display=default | options: "gascogne", "georgia", "kitakaze", "seattle"; default: "seattle" | `P`/☐ 未逐值 | ☑ | ☐ | ☐ | ☑ | ☐ |
| `GuildShop.PR3` | ShopOnce | type=select; display=default | options: "champagne", "cheshire", "mainz", "odin"; default: "cheshire" | `P`/☐ 未逐值 | ☑ | ☐ | ☐ | ☑ | ☐ |
| `GuildShop.RETROFIT_T2` | ShopOnce | type=select; display=default | options: "bb", "cl", "cv", "dd"; default: "cl" | `P`/☐ 未逐值 | ☑ | ☐ | ☐ | ☑ | ☐ |
| `GuildShop.RETROFIT_T3` | ShopOnce | type=select; display=default | options: "bb", "cl", "cv", "dd"; default: "cl" | `P`/☐ 未逐值 | ☑ | ☐ | ☐ | ☑ | ☐ |
| `GuildShop.Refresh` | ShopOnce | type=checkbox; display=default | input/default: true | `P`/◐ 实机当前值 | ☑ | ◐ | ☐ | ☑ | ◐ |
| `Hard.HardFleet` | Hard | type=select; display=default | options: 1, 2; default: 1 | `B`/◐ 实机当前值 | ☑ | ◐ | ◐ | ☑ | ◐ |
| `Hard.HardStage` | Hard | type=input; display=default | input/default: "11-4" | `B`/◐ 实机当前值 | ☑ | ◐ | ◐ | ☑ | ◐ |
| `Hospital.UseRecommendFleet` | Hospital | type=checkbox; display=default | input/default: true | `O`/🧪 离线回放 | ☑ | ☐ | ☐ | ☑ | ☐ |
| `HpControl.HpBalanceThreshold` | Main, Main2, Main3, Event, Event2, WarArchives, EventA, EventB, EventC, EventD, EventSp | type=input; display=default | input/default: 0.2 | `P`/☐ 未逐值 | ☑ | ☐ | ☐ | ☑ | ☐ |
| `HpControl.HpBalanceWeight` | Main, Main2, Main3, Event, Event2, WarArchives, EventA, EventB, EventC, EventD, EventSp | type=input; display=default | input/default: "1000, 1000, 1000" | `P`/☐ 未逐值 | ☑ | ☐ | ☐ | ☑ | ☐ |
| `HpControl.LowHpRetreatThreshold` | Main, Main2, Main3, Event, Event2, WarArchives, EventA, EventB, EventC, EventD, EventSp | type=input; display=default | input/default: 0.3 | `P`/🧪 离线路径 | ☑ | ◐ | ☐ | ☑ | ☐ |
| `HpControl.RepairUseMultiThreshold` | Main, Main2, Main3, Event, Event2, WarArchives, EventA, EventB, EventC, EventD, EventSp | type=input; display=default | input/default: 0.6 | `P`/☐ 未逐值 | ☑ | ☐ | ☐ | ☑ | ☐ |
| `HpControl.RepairUseSingleThreshold` | Main, Main2, Main3, Event, Event2, WarArchives, EventA, EventB, EventC, EventD, EventSp | type=input; display=default | input/default: 0.3 | `P`/☐ 未逐值 | ☑ | ☐ | ☐ | ☑ | ☐ |
| `HpControl.UseEmergencyRepair` | Main, Main2, Main3, Event, Event2, WarArchives, EventA, EventB, EventC, EventD, EventSp | type=checkbox; display=default | input/default: false | `P`/◐ 实机当前值 | ☑ | ◐ | ☐ | ☑ | ◐ |
| `HpControl.UseHpBalance` | Main, Main2, Main3, Event, Event2, WarArchives, EventA, EventB, EventC, EventD, EventSp | type=checkbox; display=default | input/default: false | `P`/◐ 实机当前值 | ☑ | ◐ | ☐ | ☑ | ◐ |
| `HpControl.UseLowHpRetreat` | Main, Main2, Main3, Event, Event2, WarArchives, EventA, EventB, EventC, EventD, EventSp | type=checkbox; display=default | input/default: false | `P`/◐ 实机当前值 | ☑ | ◐ | ☐ | ☑ | ◐ |
| `Mail.ClaimMaintenance` | Freebies | type=checkbox; display=default | input/default: false | `P`/◐ 实机当前值 | ☑ | ◐ | ☐ | ☑ | ◐ |
| `Mail.ClaimMerit` | Freebies | type=checkbox; display=default | input/default: true | `P`/◐ 实机当前值 | ☑ | ◐ | ◐ | ☑ | ◐ |
| `Mail.ClaimTradeLicense` | Freebies | type=checkbox; display=default | input/default: false | `P`/◐ 实机当前值 | ☑ | ◐ | ☐ | ☑ | ◐ |
| `Mail.DeleteCollected` | Freebies | type=checkbox; display=default | input/default: true | `P`/◐ 实机当前值 | ☑ | ◐ | ◐ | ☑ | ◐ |
| `MedalShop2.Filter` | ShopOnce | type=textarea; display=default | input/default: <long default in args.json> | `L`/◐ 实机当前值 | ☑ | ◐ | ◐ | ☑ | ◐ |
| `MedalShop2.PLATE_T1` | ShopOnce | type=select; display=default | options: "antiair", "general", "gun", "plane", "torpedo"; default: "general" | `L`/☐ 未逐值 | ☑ | ☐ | ☐ | ☑ | ☐ |
| `MedalShop2.PLATE_T2` | ShopOnce | type=select; display=default | options: "antiair", "general", "gun", "plane", "torpedo"; default: "general" | `L`/☐ 未逐值 | ☑ | ☐ | ☐ | ☑ | ☐ |
| `MedalShop2.PLATE_T3` | ShopOnce | type=select; display=default | options: "antiair", "general", "gun", "plane", "torpedo"; default: "general" | `L`/☐ 未逐值 | ☑ | ☐ | ☐ | ☑ | ☐ |
| `MedalShop2.RETROFIT_T1` | ShopOnce | type=select; display=default | options: "bb", "cl", "cv", "dd"; default: "cl" | `L`/☐ 未逐值 | ☑ | ☐ | ☐ | ☑ | ☐ |
| `MedalShop2.RETROFIT_T2` | ShopOnce | type=select; display=default | options: "bb", "cl", "cv", "dd"; default: "cl" | `L`/☐ 未逐值 | ☑ | ☐ | ☐ | ☑ | ☐ |
| `MedalShop2.RETROFIT_T3` | ShopOnce | type=select; display=default | options: "bb", "cl", "cv", "dd"; default: "cl" | `L`/☐ 未逐值 | ☑ | ☐ | ☐ | ☑ | ☐ |
| `Meowfficer.BuyAmount` | Meowfficer | type=input; display=default | input/default: 1 | `M`/🧪 仅离线完成 | ☑ | ☐ | ☐ | ☑ | ☐ |
| `Meowfficer.FortChoreMeowfficer` | Meowfficer | type=checkbox; display=default | input/default: true | `M`/🧪 仅离线完成 | ☑ | ☐ | ☐ | ☑ | ☐ |
| `Meowfficer.OverflowCoins` | Meowfficer | type=input; display=default | input/default: -1 | `M`/🧪 仅离线完成 | ☑ | ☐ | ☐ | ☑ | ☐ |
| `MeowfficerTrain.Enable` | Meowfficer | type=checkbox; display=default | input/default: false | `M`/🧪 仅离线完成 | ☑ | ☐ | ☐ | ☑ | ☐ |
| `MeowfficerTrain.EnhanceIndex` | Meowfficer | type=input; display=default | input/default: 1 | `M`/🧪 仅离线完成 | ☑ | ☐ | ☐ | ☑ | ☐ |
| `MeowfficerTrain.MaxFeedLevel` | Meowfficer | type=input; display=default | input/default: 5 | `M`/🧪 仅离线完成 | ☑ | ☐ | ☐ | ☑ | ☐ |
| `MeowfficerTrain.Mode` | Meowfficer | type=select; display=default | options: "once_a_day", "seamlessly"; default: "seamlessly" | `M`/🧪 仅离线完成 | ☑ | ☐ | ☐ | ☑ | ☐ |
| `MeowfficerTrain.RetainTalentedGold` | Meowfficer | type=checkbox; display=default | input/default: true | `M`/🧪 仅离线完成 | ☑ | ☐ | ☐ | ☑ | ☐ |
| `MeowfficerTrain.RetainTalentedPurple` | Meowfficer | type=checkbox; display=default | input/default: true | `M`/🧪 仅离线完成 | ☑ | ☐ | ☐ | ☑ | ☐ |
| `MeritShop.Filter` | ShopOnce | type=textarea; display=default | input/default: "Cube" | `M`/⊘ 未适配 | ☑ | ⊘ | ⊘ | ⊘ | ⊘ |
| `MeritShop.Refresh` | ShopOnce | type=checkbox; display=default | input/default: false | `M`/⊘ 未适配 | ☑ | ⊘ | ⊘ | ⊘ | ⊘ |
| `OldRetire.N` | General | type=checkbox; display=default | input/default: true | `M`/⊘ 未适配 | ☑ | ⊘ | ⊘ | ⊘ | ⊘ |
| `OldRetire.R` | General | type=checkbox; display=default | input/default: true | `M`/⊘ 未适配 | ☑ | ⊘ | ⊘ | ⊘ | ⊘ |
| `OldRetire.RetireAmount` | General | type=select; display=default | options: "retire_10", "retire_all"; default: "retire_all" | `M`/⊘ 未适配 | ☑ | ⊘ | ⊘ | ⊘ | ⊘ |
| `OldRetire.SR` | General | type=checkbox; display=default | input/default: false | `M`/⊘ 未适配 | ☑ | ⊘ | ⊘ | ⊘ | ⊘ |
| `OldRetire.SSR` | General | type=checkbox; display=default | input/default: false | `M`/⊘ 未适配 | ☑ | ⊘ | ⊘ | ⊘ | ⊘ |
| `OneClickRetire.KeepLimitBreak` | General | type=select; display=default | options: "do_not_keep", "keep_limit_break"; default: "keep_limit_break" | `P`/◐ 两设置 typed；keep_limit_break 已实机 | ☑ | ☑ | ☑ | ☑ | ◐ |
| `OpsiAbyssal.ForceRun` | OpsiAbyssal | type=checkbox; display=default | input/default: false | `B`/◐ 实机当前值 | ☑ | ◐ | ☐ | ☑ | ◐ |
| `OpsiAshAssist.Tier` | OpsiAshAssist | type=input; display=default | input/default: 15 | `B`/◐ 实机当前值 | ☑ | ◐ | ◐ | ☑ | ◐ |
| `OpsiAshBeacon.AttackMode` | OpsiAshBeacon | type=select; display=default | options: "current_dossier", "current"; default: "current" | `B`/◐ 实机当前值 | ☑ | ◐ | ☐ | ☑ | ◐ |
| `OpsiAshBeacon.DossierAutoAttackMode` | OpsiAshBeacon | type=checkbox; display=default | input/default: false | `B`/☐ 未逐值 | ☑ | ☐ | ☐ | ☑ | ☐ |
| `OpsiAshBeacon.EnsureFullyCollected` | OpsiAshBeacon | type=checkbox; display=default | input/default: true | `B`/☐ 未逐值 | ☑ | ☐ | ☐ | ☑ | ☐ |
| `OpsiAshBeacon.OneHitMode` | OpsiAshBeacon | type=checkbox; display=default | input/default: true | `B`/☐ 未逐值 | ☑ | ☐ | ☐ | ☑ | ☐ |
| `OpsiAshBeacon.RequestAssist` | OpsiAshBeacon | type=checkbox; display=default | input/default: true | `B`/☐ 未逐值 | ☑ | ☐ | ☐ | ☑ | ☐ |
| `OpsiDaemon.RepairShip` | OpsiDaemon | type=checkbox; display=default | input/default: true | `P`/◐ 实机当前值 | ☑ | ◐ | ☐ | ☑ | ◐ |
| `OpsiDaemon.SelectEnemy` | OpsiDaemon | type=checkbox; display=default | input/default: true | `P`/◐ 实机当前值 | ☑ | ◐ | ☐ | ☑ | ◐ |
| `OpsiDaily.DoMission` | OpsiDaily | type=checkbox; display=default | input/default: true | `M`/⊘ 未适配 | ☑ | ⊘ | ⊘ | ⊘ | ⊘ |
| `OpsiDaily.UseTuningSample` | OpsiDaily | type=checkbox; display=default | input/default: true | `B`/◐ 实机当前值 | ☑ | ◐ | ☐ | ☑ | ◐ |
| `OpsiExplore.ForceRun` | OpsiExplore | type=checkbox; display=default | input/default: false | `B`/◐ 实机当前值 | ☑ | ◐ | ☐ | ☑ | ◐ |
| `OpsiExplore.LastZone` | OpsiExplore | type=input; display=default | input/default: 0 | `B`/◐ 实机当前值 | ☑ | ◐ | ☐ | ☑ | ◐ |
| `OpsiExplore.SpecialRadar` | OpsiExplore | type=checkbox; display=default | input/default: false | `B`/◐ 实机当前值 | ☑ | ◐ | ☐ | ☑ | ◐ |
| `OpsiFleet.Fleet` | OpsiExplore, OpsiDaily, OpsiObscure, OpsiArchive, OpsiMeowfficerFarming, OpsiHazard1Leveling | type=select; display=default | options: 1, 2, 3, 4; default: 1 | `B`/◐ 实机当前值 | ☑ | ◐ | ☐ | ☑ | ◐ |
| `OpsiFleet.Submarine` | OpsiExplore, OpsiDaily, OpsiObscure, OpsiArchive, OpsiMeowfficerFarming, OpsiHazard1Leveling | type=checkbox; display=default/hide | input/default: false | `B`/◐ 实机当前值 | ☑ | ◐ | ☐ | ☑ | ◐ |
| `OpsiFleetFilter.Filter` | OpsiAbyssal, OpsiStronghold, OpsiMonthBoss | type=textarea; display=default | input/default: "Fleet-4 > CallSubmarine > Fleet-2 > Fleet-3 > Fleet-1" | `B`/☐ 未逐值 | ☑ | ☐ | ☐ | ☑ | ☐ |
| `OpsiGeneral.AkashiShopFilter` | OpsiGeneral | type=textarea; display=default | input/default: "ActionPoint > PurpleCoins" | `P`/◐ 实机当前值 | ☑ | ◐ | ☐ | ☑ | ◐ |
| `OpsiGeneral.BuyActionPointLimit` | OpsiGeneral | type=select; display=default | options: 0, 1, 2, 3, 4, 5; default: 0 | `P`/◐ 实机当前值 | ☑ | ◐ | ☐ | ☑ | ◐ |
| `OpsiGeneral.DoRandomMapEvent` | OpsiGeneral | type=checkbox; display=default | input/default: true | `P`/◐ 实机当前值 | ☑ | ◐ | ☐ | ☑ | ◐ |
| `OpsiGeneral.OilLimit` | OpsiGeneral | type=input; display=default | input/default: 1000 | `P`/◐ 实机当前值 | ☑ | ◐ | ☐ | ☑ | ◐ |
| `OpsiGeneral.RepairThreshold` | OpsiGeneral | type=input; display=default | input/default: 0.4 | `P`/◐ 实机当前值 | ☑ | ◐ | ☐ | ☑ | ◐ |
| `OpsiGeneral.UseLogger` | OpsiGeneral | type=checkbox; display=default | input/default: true | `P`/◐ 实机当前值 | ☑ | ◐ | ☐ | ☑ | ◐ |
| `OpsiHazard1Leveling.TargetZone` | OpsiHazard1Leveling | type=select; display=default | options: 0, 22, 44; default: 0 | `B`/◐ 实机当前值 | ☑ | ◐ | ☐ | ☑ | ◐ |
| `OpsiMeowfficerFarming.ActionPointPreserve` | OpsiMeowfficerFarming | type=input; display=default | input/default: 1000 | `B`/◐ 实机当前值 | ☑ | ◐ | ☐ | ☑ | ◐ |
| `OpsiMeowfficerFarming.HazardLevel` | OpsiMeowfficerFarming | type=select; display=default | options: 10, 3, 4, 5, 6; default: 5 | `B`/◐ 实机当前值 | ☑ | ◐ | ☐ | ☑ | ◐ |
| `OpsiMeowfficerFarming.TargetZone` | OpsiMeowfficerFarming | type=input; display=default | input/default: 0 | `B`/◐ 实机当前值 | ☑ | ◐ | ☐ | ☑ | ◐ |
| `OpsiMonthBoss.CheckAdaptability` | OpsiMonthBoss | type=checkbox; display=default | input/default: true | `B`/◐ 实机当前值 | ☑ | ◐ | ☐ | ☑ | ◐ |
| `OpsiMonthBoss.ForceRun` | OpsiMonthBoss | type=checkbox; display=default | input/default: false | `M`/⊘ 未适配 | ☑ | ⊘ | ⊘ | ⊘ | ⊘ |
| `OpsiMonthBoss.Mode` | OpsiMonthBoss | type=select; display=default | options: "normal_hard", "normal"; default: "normal" | `B`/◐ 实机当前值 | ☑ | ◐ | ☐ | ☑ | ◐ |
| `OpsiObscure.ForceRun` | OpsiObscure | type=checkbox; display=default | input/default: false | `B`/◐ 实机当前值 | ☑ | ◐ | ☐ | ☑ | ◐ |
| `OpsiShop.CustomFilter` | OpsiShop | type=textarea; display=default | input/default: <long default in args.json> | `B`/◐ 实机当前值 | ☑ | ◐ | ☐ | ☑ | ◐ |
| `OpsiShop.PresetFilter` | OpsiShop | type=select; display=default | options: "all", "custom", "max_benefit_meta", "max_benefit", "no_meta"; default: "max_benefit_meta" | `B`/◐ 实机当前值 | ☑ | ◐ | ☐ | ☑ | ◐ |
| `OpsiStronghold.ForceRun` | OpsiStronghold | type=checkbox; display=default | input/default: false | `M`/⛔ Headless 跳过 | ☑ | ☐ | ☐ | ☑ | ☐ |
| `OpsiVoucher.Filter` | OpsiVoucher | type=textarea; display=default | input/default: "LoggerAbyssal > LoggerObscure > Book > Coin > Fragment" | `B`/◐ 实机当前值 | ☑ | ◐ | ☐ | ☑ | ◐ |
| `Optimization.CombatScreenshotInterval` | Alas | type=input; display=default | input/default: 1.0 | `P`/◐ 实机当前值 | ☑ | ◐ | ☐ | ☑ | ◐ |
| `Optimization.ScreenshotInterval` | Alas | type=input; display=default | input/default: 0.3 | `P`/◐ 实机当前值 | ☑ | ◐ | ☐ | ☑ | ◐ |
| `Optimization.TaskHoardingDuration` | Alas | type=input; display=default | input/default: 0 | `P`/◐ 实机当前值 | ☑ | ◐ | ☐ | ☑ | ◐ |
| `Optimization.WhenTaskQueueEmpty` | Alas | type=select; display=default | options: "close_game", "goto_main", "stay_there"; default: "goto_main" | `P`/◐ 实机当前值 | ☑ | ◐ | ☐ | ☑ | ◐ |
| `PrivateQuarters.BuyCake` | PrivateQuarters | type=checkbox; display=default | input/default: false | `O`/🧪 仅离线完成 | ☑ | ☐ | ☐ | ☑ | ☐ |
| `PrivateQuarters.BuyRoses` | PrivateQuarters | type=checkbox; display=default | input/default: true | `O`/🧪 仅离线完成 | ☑ | ☐ | ☐ | ☑ | ☐ |
| `PrivateQuarters.TargetInteract` | PrivateQuarters | type=checkbox; display=default | input/default: true | `O`/🧪 仅离线完成 | ☑ | ☐ | ☐ | ☑ | ☐ |
| `PrivateQuarters.TargetShip` | PrivateQuarters | type=select; display=default | options: "aegir", "anchorage", "nakhimov", "new_jersey", "noshiro", "sirius", "taihou"; default: "anchorage" | `O`/🧪 仅离线完成 | ☑ | ☐ | ☐ | ☑ | ☐ |
| `Raid.Mode` | Raid | type=select; display=default | options: "easy", "ex", "hard", "normal"; default: "hard" | `O`/🧪 离线回放 | ☑ | ☐ | ☐ | ☑ | ☐ |
| `Raid.UseTicket` | Raid | type=checkbox; display=default | input/default: false | `O`/🧪 离线回放 | ☑ | ☐ | ☐ | ☑ | ☐ |
| `RaidDaily.StageFilter` | RaidDaily | type=textarea; display=default | input/default: "hard > normal > easy" | `O`/🧪 离线回放 | ☑ | ☐ | ☐ | ☑ | ☐ |
| `Research.AllowDelay` | Research | type=checkbox; display=default | input/default: true | `L`/◐ 双值读取/真值回退 | ☑ | ☑ | ◐ | ☑ | ◐ |
| `Research.CustomFilter` | Research | type=textarea; display=default | input/default: <long default in args.json> | `L`/◐ 当前规则/重名闭环 | ☑ | ◐ | ◐ | ☑ | ◐ |
| `Research.PresetFilter` | Research | type=select; display=default | options: "custom", "series_2_457_only", "series_2_blueprint_457", "series_2_blueprint_only", "series_2_than_3_457_234", "series_3_234_only", "series_3_blueprint_234", "series_3_blueprint_only", "series_4_blueprint_only", "series_4_blueprint_tenrai", "series_4_tenrai_only", "series_5_152_only", "series_5_blueprint_152", "series_5_blueprint_only", "series_6_203_only", "series_6_blueprint_203", "series_6_blueprint_only", "series_7_blueprint_la9", "series_7_blueprint_only", "series_7_la9_only", "series_8_305_only", "series_8_blueprint_305", "series_8_blueprint_only", "series_9_blueprint_only", "series_9_blueprint_ta152", "series_9_ta152_only"; default: "series_9_blueprint_ta152" | `L`/◐ 实机当前值 | ☑ | ◐ | ◐ | ☑ | ◐ |
| `Research.UseCoin` | Research | type=select; display=default | options: "always_use", "do_not_use", "only_05_hour", "only_no_project"; default: "always_use" | `L`/◐ 实机当前值 | ☑ | ◐ | ◐ | ☑ | ◐ |
| `Research.UseCube` | Research | type=select; display=default | options: "always_use", "do_not_use", "only_05_hour", "only_no_project"; default: "only_05_hour" | `L`/◐ 实机当前值 | ☑ | ◐ | ◐ | ☑ | ◐ |
| `Research.UsePart` | Research | type=select; display=default | options: "always_use", "do_not_use", "only_05_hour", "only_no_project"; default: "always_use" | `L`/◐ 实机当前值 | ☑ | ◐ | ◐ | ☑ | ◐ |
| `Retirement.RetireMode` | General | type=select; display=default | options: "enhance", "old_retire", "one_click_retire"; default: "one_click_retire" | `P`/◐ 一键与强化已接入；旧退役未适配 | ☑ | ◐ | ◐ | ☑ | ◐ |
| `Reward.CollectCoin` | Reward | type=checkbox; display=default | input/default: true | `F`/☑ 完整 | ☑ | ☑ | ☑ | ☑ | ☑ |
| `Reward.CollectExp` | Reward | type=checkbox; display=default | input/default: true | `F`/☑ 完整 | ☑ | ☑ | ☑ | ☑ | ☑ |
| `Reward.CollectMission` | Reward | type=checkbox; display=default | input/default: true | `F`/☑ 完整 | ☑ | ☑ | ☑ | ☑ | ☑ |
| `Reward.CollectOil` | Reward | type=checkbox; display=default | input/default: true | `F`/☑ 完整 | ☑ | ☑ | ☑ | ☑ | ☑ |
| `Reward.CollectWeeklyMission` | Reward | type=checkbox; display=default | input/default: true | `F`/☑ 完整 | ☑ | ☑ | ☑ | ☑ | ☑ |
| `Scheduler.Command` | Restart, Main, Main2, Main3, GemsFarming, Coalition, Event, Event2, Raid, Hospital, WarArchives, CoalitionSp, EventA, EventB, EventC, EventD, EventSp, RaidDaily, Commission, Tactical, Research, Dorm, Meowfficer, Guild, Reward, Awaken, Daily, Hard, Exercise, ShopFrequent, ShopOnce, Shipyard, Gacha, Freebies, Minigame, PrivateQuarters, OpsiAshBeacon, OpsiAshAssist, OpsiExplore, OpsiShop, OpsiVoucher, OpsiDaily, OpsiObscure, OpsiAbyssal, OpsiArchive, OpsiStronghold, OpsiMonthBoss, OpsiMeowfficerFarming, OpsiHazard1Leveling, OpsiCrossMonth | type=input; display=hide | input/default: "Awaken", "Coalition", "CoalitionSp", "Commission", "Daily", "Dorm", "Event", "Event2", "EventA", "EventB", "EventC", "EventD", "EventSp", "Exercise", "Freebies", "Gacha", "GemsFarming", "Guild", "Hard", "Hospital", "Main", "Main2", "Main3", "Meowfficer", "Minigame", "OpsiAbyssal", "OpsiArchive", "OpsiAshAssist", "OpsiAshBeacon", "OpsiCrossMonth", "OpsiDaily", "OpsiExplore", "OpsiHazard1Leveling", "OpsiMeowfficerFarming", "OpsiMonthBoss", "OpsiObscure", "OpsiShop", "OpsiStronghold", "OpsiVoucher", "PrivateQuarters", "Raid", "RaidDaily", "Research", "Restart", "Reward", "Shipyard", "ShopFrequent", "ShopOnce", "Tactical", "WarArchives" | `F`/☑ 完整 | ☑ | — | — | ☑ | ☑ |
| `Scheduler.Enable` | Restart, Main, Main2, Main3, GemsFarming, Coalition, Event, Event2, Raid, Hospital, WarArchives, CoalitionSp, EventA, EventB, EventC, EventD, EventSp, RaidDaily, Commission, Tactical, Research, Dorm, Meowfficer, Guild, Reward, Awaken, Daily, Hard, Exercise, ShopFrequent, ShopOnce, Shipyard, Gacha, Freebies, Minigame, PrivateQuarters, OpsiAshBeacon, OpsiAshAssist, OpsiExplore, OpsiShop, OpsiVoucher, OpsiDaily, OpsiObscure, OpsiAbyssal, OpsiArchive, OpsiStronghold, OpsiMonthBoss, OpsiMeowfficerFarming, OpsiHazard1Leveling, OpsiCrossMonth | type=checkbox/lock/state; display=default | options: false, true; default: false, true | `F`/☑ 完整 | ☑ | — | — | ☑ | ☑ |
| `Scheduler.FailureInterval` | Restart, Main, Main2, Main3, GemsFarming, Coalition, Event, Event2, Raid, Hospital, WarArchives, CoalitionSp, EventA, EventB, EventC, EventD, EventSp, RaidDaily, Commission, Tactical, Research, Dorm, Meowfficer, Guild, Reward, Awaken, Daily, Hard, Exercise, ShopFrequent, ShopOnce, Shipyard, Gacha, Freebies, Minigame, PrivateQuarters, OpsiAshBeacon, OpsiAshAssist, OpsiExplore, OpsiShop, OpsiVoucher, OpsiDaily, OpsiObscure, OpsiAbyssal, OpsiArchive, OpsiStronghold, OpsiMonthBoss, OpsiMeowfficerFarming, OpsiHazard1Leveling, OpsiCrossMonth | type=input; display=hide | input/default: "120-240", "30-60", 0, 120, 278, 30, 60 | `F`/☑ 完整 | ☑ | — | — | ☑ | ☑ |
| `Scheduler.NextRun` | Restart, Main, Main2, Main3, GemsFarming, Coalition, Event, Event2, Raid, Hospital, WarArchives, CoalitionSp, EventA, EventB, EventC, EventD, EventSp, RaidDaily, Commission, Tactical, Research, Dorm, Meowfficer, Guild, Reward, Awaken, Daily, Hard, Exercise, ShopFrequent, ShopOnce, Shipyard, Gacha, Freebies, Minigame, PrivateQuarters, OpsiAshBeacon, OpsiAshAssist, OpsiExplore, OpsiShop, OpsiVoucher, OpsiDaily, OpsiObscure, OpsiAbyssal, OpsiArchive, OpsiStronghold, OpsiMonthBoss, OpsiMeowfficerFarming, OpsiHazard1Leveling, OpsiCrossMonth | type=datetime; display=default; validate=datetime | input/default: "2020-01-01 00:00:00" | `F`/☑ 完整 | ☑ | — | — | ☑ | ☑ |
| `Scheduler.ServerUpdate` | Restart, Main, Main2, Main3, GemsFarming, Coalition, Event, Event2, Raid, Hospital, WarArchives, CoalitionSp, EventA, EventB, EventC, EventD, EventSp, RaidDaily, Commission, Tactical, Research, Dorm, Meowfficer, Guild, Reward, Awaken, Daily, Hard, Exercise, ShopFrequent, ShopOnce, Shipyard, Gacha, Freebies, Minigame, PrivateQuarters, OpsiAshBeacon, OpsiAshAssist, OpsiExplore, OpsiShop, OpsiVoucher, OpsiDaily, OpsiObscure, OpsiAbyssal, OpsiArchive, OpsiStronghold, OpsiMonthBoss, OpsiMeowfficerFarming, OpsiHazard1Leveling, OpsiCrossMonth | type=input; display=hide | input/default: "00:00, 06:00, 12:00, 18:00, 21:00", "00:00, 12:00, 18:00", "00:00, 12:00", "00:00", "04:00" | `F`/☑ 完整 | ☑ | — | — | ☑ | ☑ |
| `Scheduler.SuccessInterval` | Restart, Main, Main2, Main3, GemsFarming, Coalition, Event, Event2, Raid, Hospital, WarArchives, CoalitionSp, EventA, EventB, EventC, EventD, EventSp, RaidDaily, Commission, Tactical, Research, Dorm, Meowfficer, Guild, Reward, Awaken, Daily, Hard, Exercise, ShopFrequent, ShopOnce, Shipyard, Gacha, Freebies, Minigame, PrivateQuarters, OpsiAshBeacon, OpsiAshAssist, OpsiExplore, OpsiShop, OpsiVoucher, OpsiDaily, OpsiObscure, OpsiAbyssal, OpsiArchive, OpsiStronghold, OpsiMonthBoss, OpsiMeowfficerFarming, OpsiHazard1Leveling, OpsiCrossMonth | type=input; display=hide | input/default: "120-240", "30-60", 0, 278, 30, 60 | `F`/☑ 完整 | ☑ | — | — | ☑ | ☑ |
| `Shipyard.BuyAmount` | Shipyard | type=input; display=default | input/default: 2 | `B`/☐ 未逐值 | ☑ | ☐ | ☐ | ◐ | ☐ |
| `Shipyard.LastRun` | Shipyard | type=datetime; display=default; validate=datetime | input/default: "2020-01-01 00:00:00" | `B`/☐ 未逐值 | ☑ | ☐ | ☐ | ☑ | ☐ |
| `Shipyard.ResearchSeries` | Shipyard | type=select; display=default | options: 1, 2, 3, 4, 5, 6; default: 1 | `B`/◐ 实机当前值 | ☑ | ◐ | ◐ | ☑ | ◐ |
| `Shipyard.ShipIndex` | Shipyard | type=select; display=default | options: 0, 1, 2, 3, 4, 5, 6; default: 0 | `B`/◐ 实机当前值 | ☑ | ◐ | ◐ | ☑ | ◐ |
| `ShipyardDr.BuyAmount` | Shipyard | type=input; display=default | input/default: 2 | `B`/☐ 未逐值 | ☑ | ☐ | ☐ | ◐ | ☐ |
| `ShipyardDr.LastRun` | Shipyard | type=datetime; display=default; validate=datetime | input/default: "2020-01-01 00:00:00" | `B`/☐ 未逐值 | ☑ | ☐ | ☐ | ☑ | ☐ |
| `ShipyardDr.ResearchSeries` | Shipyard | type=select; display=default | options: 2, 3, 4, 5; default: 2 | `B`/◐ 实机当前值 | ☑ | ◐ | ◐ | ☑ | ◐ |
| `ShipyardDr.ShipIndex` | Shipyard | type=select; display=default | options: 0, 1, 2, 3, 4, 5, 6; default: 0 | `B`/◐ 实机当前值 | ☑ | ◐ | ◐ | ☑ | ◐ |
| `StopCondition.GetNewShip` | Main, Main2, Main3, GemsFarming, Coalition, Event, Event2, Raid, Hospital, WarArchives, CoalitionSp, EventA, EventB, EventC, EventD, EventSp, RaidDaily | type=checkbox; display=default/hide | input/default: false | `P`/🧱 首次获得跳过 | ☑ | ◐ | ☐ | ◐ | ◐ |
| `StopCondition.MapAchievement` | Main, Main2, Main3, GemsFarming, Coalition, Event, Event2, Raid, Hospital, WarArchives, CoalitionSp, EventA, EventB, EventC, EventD, EventSp, RaidDaily | type=select; display=default/hide | options: "100_percent_clear", "map_3_stars", "non_stop", "threat_safe_without_3_stars", "threat_safe"; default: "non_stop" | `P`/◐ typed 主线夹具 | ☑ | ◐ | ☐ | ☑ | ◐ |
| `StopCondition.OilLimit` | Main, Main2, Main3, GemsFarming, Coalition, Event, Event2, Raid, Hospital, WarArchives, CoalitionSp, EventA, EventB, EventC, EventD, EventSp, RaidDaily | type=input; display=default | input/default: 1000 | `P`/◐ 实机当前值 | ☑ | ◐ | ☐ | ☑ | ◐ |
| `StopCondition.ReachLevel` | Main, Main2, Main3, GemsFarming, Coalition, Event, Event2, Raid, Hospital, WarArchives, CoalitionSp, EventA, EventB, EventC, EventD, EventSp, RaidDaily | type=input; display=default/hide | input/default: 0 | `P`/◐ typed 六舰等级 | ☑ | ◐ | ☐ | ☑ | ◐ |
| `StopCondition.RunCount` | Main, Main2, Main3, GemsFarming, Coalition, Event, Event2, Raid, Hospital, WarArchives, CoalitionSp, EventA, EventB, EventC, EventD, EventSp, RaidDaily | type=input; display=default/hide | input/default: 0 | `P`/🧪 三主线实例回放 | ☑ | ◐ | ☐ | ☑ | ◐ |
| `StopCondition.StageIncrease` | Main, Main2, Main3, GemsFarming, Coalition, Event, Event2, Raid, Hospital, WarArchives, CoalitionSp, EventA, EventB, EventC, EventD, EventSp, RaidDaily | type=checkbox; display=default/hide | input/default: false | `P`/◐ 实机当前值 | ☑ | ◐ | ☐ | ☑ | ◐ |
| `Submarine.AutoSearchMode` | Main, Main2, Main3, GemsFarming, Event, Event2, WarArchives, EventA, EventB, EventC, EventD, EventSp | type=select; display=default/hide | options: "sub_auto_call", "sub_standby"; default: "sub_standby" | `P`/☐ 未逐值 | ☑ | ☐ | ☐ | ☑ | ☐ |
| `Submarine.DistanceToBoss` | Main, Main2, Main3, GemsFarming, Event, Event2, WarArchives, EventA, EventB, EventC, EventD, EventSp | type=select; display=default/hide | options: "1_grid_to_boss", "2_grid_to_boss", "to_boss_position", "use_open_ocean_support"; default: "2_grid_to_boss", "use_open_ocean_support" | `P`/☐ 未逐值 | ☑ | ☐ | ☐ | ☑ | ☐ |
| `Submarine.Fleet` | Main, Main2, Main3, GemsFarming, Event, Event2, WarArchives, EventA, EventB, EventC, EventD, EventSp | type=select; display=default | options: 0, 1, 2; default: 0 | `P`/◐ 实机当前值 | ☑ | ◐ | ☐ | ☑ | ◐ |
| `Submarine.Mode` | Main, Main2, Main3, GemsFarming, Event, Event2, WarArchives, EventA, EventB, EventC, EventD, EventSp | type=select; display=default/display | options: "boss_only", "do_not_use", "every_combat", "hunt_and_boss", "hunt_only"; default: "do_not_use" | `P`/◐ 实机当前值 | ☑ | ◐ | ☐ | ☑ | ◐ |
| `SupplyPack.Collect` | Freebies | type=checkbox; display=default | input/default: true | `B`/◐ 实机当前值 | ☑ | ◐ | ◐ | ☑ | ◐ |
| `SupplyPack.DayOfWeek` | Freebies | type=select; display=default | options: 0, 1, 2, 3, 4, 5, 6; default: 0 | `B`/◐ 实机当前值 | ☑ | ◐ | ☐ | ☑ | ◐ |
| `Tactical.RapidTrainingSlot` | Tactical | type=select; display=default | options: "do_not_use", "slot_1", "slot_2", "slot_3", "slot_4"; default: "do_not_use" | `L`/◐ 实机当前值 | ☑ | ◐ | ☐ | ☑ | ◐ |
| `Tactical.TacticalFilter` | Tactical | type=textarea; display=default | input/default: <long default in args.json> | `F`/☑ 完整 | ☑ | ☑ | ☑ | ☑ | ☑ |
| `TaskBalancer.CoinLimit` | EventGeneral | type=input; display=default | input/default: 10000 | `P`/☐ 未逐值 | ☑ | ☐ | ☐ | ☑ | ☐ |
| `TaskBalancer.Enable` | EventGeneral | type=checkbox; display=default | input/default: false | `P`/☐ 未逐值 | ☑ | ☐ | ☐ | ☑ | ☐ |
| `TaskBalancer.TaskCall` | EventGeneral | type=select; display=default | options: "Main", "Main2", "Main3"; default: "Main" | `P`/☐ 未逐值 | ☑ | ☐ | ☐ | ☑ | ☐ |
