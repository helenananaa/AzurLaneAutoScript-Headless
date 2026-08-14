# ALAS Headless 配置项级支持矩阵

更新日期：2026-08-15
Headless 适配证据提交：`3d0f60ce1c89c54fd8a2519c260f6e19018ef93d`
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
| `F` | ✅ 完整支持 | 面板内全部配置值和必要异常分支均已按本文口径闭环；当前没有面板达到此状态 |
| `L` | 🟢 主路径已完成，完整支持未完成 | 至少一条实机主路径闭环，但不代表组内所有配置值已闭环 |
| `P` | 🟡 部分完成 | 有实现或可到达部分页面，配置分支仍不完整 |
| `B` | 🧱 已到边界，尚未完成 | 已安全到达账号、资源、日期或观察能力边界 |
| `O` | 🧪 仅离线完成 | 只有离线契约、回放或桩验证 |
| `M` | 🔴 尚未完成 | 缺少任务级适配或关键语义端口 |
| `R` | ⚙️ 运行时待验收 | ALAS 内部/运行时管理字段；仍需验证调度与恢复契约 |

### 1.1 完成度汇总（2026-08-14 标注）

这里的“完成”严格指整块面板的全部配置值和必要异常分支均已闭环，不能用“默认路径跑过”替代。

| 完成度 | 数量 | 面板 |
|---|---:|---|
| ✅ 完整支持（`F`） | **0 / 60** | 暂无 |
| 🟢 主路径已完成、全配置未完成（`L`） | **13 / 60** | Benchmark、Commission、Daily、Dorm、Event、EventA、Exercise、Gacha、GameManager、Minigame、Research、Restart、Tactical |
| 🧪 仅离线完成（`O`） | **1 / 60** | EventB |
| 🟡 部分完成（`P`） | **17 / 60** | Alas、AzurLaneUncensored、Daemon、Event2、EventC、EventD、EventGeneral、EventSp、EventStory、Freebies、General、Main2、Main3、OpsiDaemon、OpsiGeneral、Reward、ShopOnce |
| 🧱 已到边界、尚未完成（`B`） | **18 / 60** | Hard、Main、OpsiAbyssal、OpsiArchive、OpsiAshAssist、OpsiAshBeacon、OpsiCrossMonth、OpsiDaily、OpsiExplore、OpsiHazard1Leveling、OpsiMeowfficerFarming、OpsiMonthBoss、OpsiObscure、OpsiShop、OpsiVoucher、Shipyard、ShopFrequent、WarArchives |
| 🔴 尚未完成（`M`） | **11 / 60** | Awaken、Coalition、CoalitionSp、GemsFarming、Guild、Hospital、Meowfficer、OpsiStronghold、PrivateQuarters、Raid、RaidDaily |

当前账本的功能证据基线为 `3d0f60c`，矩阵首次提交为 `e2fc2fe`；authoritative patch series 的成员数与哈希由校验器现场验证。离线通过不会自动提升任何实机复核栏。

### 1.2 本轮 StopCondition 优先适配标注

本轮优先处理影响 17 个地图面板的安全停止条件。容易确定性复现的状态使用离线夹具和既有真实观察证据；需要等待账号概率或成长条件的实机项目按要求标注后跳过，不用无限刷图制造证据。

| 字段 | 本轮结果 | 确定性证据 | 仍未完成/本轮跳过 |
|---|---|---|---|
| `OilLimit` | 🟡 保留既有实现 | 全局油量已经是 typed 读取，原 ALAS 保留 `< max(500, OilLimit)` 停止与延迟逻辑 | 500 下限、等于边界和多个停止条件同时满足尚未形成独立实机记录 |
| `RunCount` | 🟡 保留既有实现 | 原 ALAS 仍拥有初始化、每轮减一、归零禁用任务和循环前后复查 | 0/1/多次、异常中断不多扣和恢复后的计数持久化尚未受控实机复核 |
| `MapAchievement` | 🧪 **本轮新增 typed port** | 真实 12-4 语义快照已给出 `100%`、三个星标和“威胁排除”；离线覆盖达成、未达成、畸形百分比和星标缺失，原五枚举判断保持不变 | 普通主线以外的活动/SP/档案布局、五种枚举的逐项实机停止仍待复核 |
| `StageIncrease` | 🟡 可接收新的 typed 达成信号 | 原 ALAS 仍拥有下一关计算、关卡存在性检查、写回 `Campaign.Name` 和末关停用 | 跨 A/B 分区、自定义链、末关和中断恢复尚未逐值实机验证 |
| `ReachLevel` | 🧪 **本轮新增 typed port** | 已审阅 G25 六舰等级节点（真实值 `118/109/117/110/118/107`）；离线覆盖排序、1..125 范围和非法 126 fail-closed；原 ALAS 保留升级跨阈值判断 | 为制造升级而等待/刷经验的实机触发按要求跳过；自动寻敌与双舰队切换后的等级复核仍待做 |
| `GetNewShip` | 🧱 **明确跳过首次获得实测** | 普通 `GET_SHIP` 页面可由确定性夹具关闭并继续 | 当前观察数据没有能把“首次获得 `NEW_SHIP`”与普通掉落可靠区分的节点；不伪造 selector、不把普通掉落误报成停止条件，待自然样本出现后补证据 |

实际固定 ALAS 方法的确定性回放现覆盖 **77 条断言**（含 40 条 `MapAchievement` 真值表组合），并静态证明 `RunCount` 只在 `campaign.run()` 返回后、下一次停止检查前扣减，且无限次数不会扣减。因此 `OilLimit`、`RunCount`、`MapAchievement`、`StageIncrease`、`ReachLevel` 的确定性边界已经闭环；StopCondition 整组仍为 `P`，因为 `GetNewShip=true` 继续按要求跳过自然首次获得实测并 fail-closed。

### 1.3 本轮官方一键退役适配标注

`General.Retirement.RetireMode=one_click_retire` 已从历史像素路径提升为受权限预算约束的官方事务端口。2026-08-14 在 API 32 专用设备、国服 9.7.10 上实际退役 68 艘：船坞 `882/910 -> 814/910`，官方奖励为物资 1026、荣誉勋章 22；18 类共 113 件随船装备全部取消拆解并进入仓库。

| 字段/安全项 | 当前 | 已验证 | 仍未完成 |
|---|:---:|---|---|
| `Retirement.RetireMode=one_click_retire` | 🟢 | 官方选择、稀有角色二次确认、奖励、装备入仓库、返回和容量差全部闭环；返回实际 68，不再硬编码 10；无候选官方提示也已实机闭环 | 未知弹窗和重连后页面不一致仍拒绝继续 |
| `Retirement.RetireMode=enhance` | 🟡 | 已接入 ALAS 正式任务入口；三项详细配置、语义筛选/选舰/强化页导航、官方推荐、单次确认、真实素材数和装备入仓均有闭环证据 | 未为补证据额外执行完整 `favourite` 破坏性任务；自然无素材实机分支仍待遇到 |
| `Retirement.RetireMode=old_retire` | 🔴 | 保留原 ALAS 分支，没有伪装成已支持 | 任务级语义观察、选择、确认和结果校验均未适配 |
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

其余三个 Optimization 字段明确跳过：两个截图间隔在 `Device` 初始化时即被钳位和消费，当前门禁位置太晚，且尚无跨截图后端的语义帧新鲜度证据；`WhenTaskQueueEmpty=close_game` 仍会进入没有包进程租约证明的旧 `app_stop()`，而 `goto_main/stay_there` 也缺空队列恢复回放。重新进入需要初始化期纯配置门禁、各后端 frame-clock 证据，以及 `close_game` 的租约化语义进程停止端口。

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

回放直接执行原 `_tactical_books_filter_exp()` 的等级 10 边界：关闭时只保留特殊 100 经验书，开启时逐档保留配置边界并排除越界书，技能未满时九本夹具全部保留。`Favorite` 原先未传入语义候选选择，本轮会在读取候选前调用既有的精确共享 Dock 收藏切换。整个回放的 mutation budget 为 0，且没有 Android 输入、真实选舰或书本消耗；仍缺 Tactical 场景下收藏状态与候选的实机 typed 观察、真实书库存/技能经验、教学结果 postcondition 和安全回滚。因此八字段只提升 `offline`，不提升 observation/action/live。

### 1.16 本轮 Tactical 选书优先级与快速学习槽位契约

`Tactical.TacticalFilter` 现在只接受原 ALAS 的完整 token 语法：可选 `Same`、颜色、T1-T4，以及 `first` 回退；兼容原过滤器支持的 Unicode 分隔符和连字符。空 token、尾随垃圾、只被非锚定正则部分匹配的值、空过滤器和非文本值会在读取书本前 fail-closed。固定上游回放直接执行原 `_tactical_books_choose()`，覆盖同色、颜色+等级、仅颜色、仅等级、`first`、无匹配取消及 Unicode 规范化七类排序，保留 ALAS 的首本聚焦、最终开始/取消和状态机所有权。

`Tactical.RapidTrainingSlot` 严格限定 `do_not_use/slot_1/slot_2/slot_3/slot_4`。原 `handle_rapid_training()` 回放验证四个精确槽位偏移、按钮不可用返回 false，以及只有命中后才执行的 interval clear。十字段 Tactical 合并回放现有 45 个合法配置和 20 个非法配置，mutation budget 为 0，没有 Android 输入、真实快速学习次数消耗或选书。因此两字段仅从 `offline=partial` 提升为 `complete`，既有 observation/action/live 仍保持 partial。

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

固定上游回放覆盖全部 32 种合法开关组合和 20 个非法单字段案例，执行原 Reward 参数转发与调度尾部、RaidDaily EX 下 `CollectMission` 的真假转发，以及非 EX 绕过。真实资源、任务和周常领取方法均未调用，mutation budget 为 0，没有页面输入或 Android 注入。因此五字段只提升 `offline`；资源上限、日常/周常领取后置条件、红点、数字行、空页和特殊舰船奖励仍需实机闭环。

### 1.22 本轮 Campaign 四个共享开关契约

`Campaign.UseFleetLock`、`UseAutoSearch`、`Use2xBook` 和 `AmbushEvade` 现在只接受精确布尔值，并在原 `CampaignRun.run()` 第一条语句统一校验。非法值会在关卡名转换、地图模块加载、页面导航和语义预出击 scope 之前 fail-closed；该入口覆盖 16 个普通、活动、共斗、突袭、档案和每日地图面板。

固定上游回放覆盖全部 16 种合法组合和 24 个非法单字段案例，执行原快速前进中的自动寻敌/2x 书选择、舰队锁定开关，以及伏击时规避/迎战分支。开关控件和伏击处理均由确定性夹具代替，没有调用真实地图方法、进入战斗、消耗 2x 书、页面输入或 Android 注入，mutation budget 为 0。因此四字段只提升 `offline`；真实控件后置条件、非周回地图、控件不可用、伏击观察及规避失败仍未闭环，`Name/Event/Mode` 的动态路由也不在本批范围。

## 2. 60 个面板总表

“配置组”列是该面板实际暴露的组；同名配置组的详细字段在第 3 节只定义一次，所有引用它的面板必须共同满足该组的验收要求。

| # | 面板 | 配置组 | 当前 | 尚未闭环的配置范围与验收重点 |
|---:|---|---|:---:|---|
| 1 | Alas | Emulator, EmulatorInfo, Error, Optimization, DropRecord | P | 当前语义观察/输入路径可运行；传统截图/控制方法矩阵、包名/服务器矩阵、错误截图、掉落记录与上传、通知均未完整验收 |
| 2 | General | Retirement, OneClickRetire, Enhance, OldRetire | P | 官方一键退役和 `keep_limit_break` 已实机闭环；强化三项详细配置、ALAS 正式任务入口、语义筛选/选舰导航、官方推荐、真实强化、容量差及装备入仓已闭环；完整 `favourite` 破坏性任务和自然无素材分支未额外消耗舰船复测，`do_not_keep` 仅设置级验证，旧退役仍缺任务级适配 |
| 3 | Restart | Scheduler | L | 当前冷重启闭环；`AdbRestart`、其他模拟器生命周期、失败重试与只恢复不重启仍需覆盖 |
| 4 | Main | Scheduler, Campaign, StopCondition, Fleet, Submarine, Emotion, HpControl, EnemyPriority | B | 12-4 能到账号战斗边界；全部共用地图配置分支见 3.2 |
| 5 | Main2 | 同 Main | P | 共用实现，没有独立配置实例验收；不能沿用 Main 的运行记录直接判定完整 |
| 6 | Main3 | 同 Main | P | 共用实现，没有独立配置实例验收；不能沿用 Main 的运行记录直接判定完整 |
| 7 | GemsFarming | Scheduler, GemsFarming, EquipmentCode, Campaign, StopCondition, Fleet, Submarine, Emotion | M | 换旗舰/前排、常用舰选择、装备导入导出和换船后的强化衔接缺失；只有委托限制可复用 |
| 8 | EventGeneral | EventGeneral, TaskBalancer | P | 五字段离线决策已完整；仍缺 typed PT/金币实机观察、时间相关性、真实任务切换恢复和防调度环证据 |
| 9 | Coalition | Scheduler, Campaign, Coalition, StopCondition, Emotion | M | 共斗入口、难度、单/多舰队、战斗和结算缺适配 |
| 10 | Event | Scheduler, Campaign, StopCondition, Fleet, Submarine, Emotion, HpControl, EnemyPriority | L | 当前 A1 默认路径闭环；其他关卡和全部共用地图配置仍按字段验收 |
| 11 | Event2 | 同 Event | P | 与 Event 共用逻辑，但第二活动配置实例没有独立验收 |
| 12 | Raid | Scheduler, Raid, Campaign, StopCondition, Emotion | M | 难度、票券、活动入口、次数和结算缺适配 |
| 13 | Hospital | Scheduler, Hospital, StopCondition, Emotion | M | 医院专用入口、推荐舰队开关和完整状态机缺适配 |
| 14 | WarArchives | Scheduler, Campaign, StopCondition, Fleet, Submarine, Emotion, HpControl, EnemyPriority | B | 能观察入口/Data Key；48 个档案值的进入、消耗、地图和结算均未形成覆盖台账 |
| 15 | CoalitionSp | Scheduler, Campaign, Coalition, StopCondition, Emotion | M | SP 共斗专用状态机缺适配 |
| 16 | EventA | Scheduler, EventDaily, Campaign, StopCondition, Fleet, Submarine, Emotion, HpControl, EnemyPriority | L | A-D StageFilter/LastStage 离线轮转契约已完成；当前仅 A1-A3 默认路径有实机闭环，其余分区和共用地图配置仍未完整覆盖 |
| 17 | EventB | 同 EventA | O | B1 普通 `GET_SHIP` 已离线适配；因概率掉落停止实跑，B1 尚未完整闭环，B2/B3 未验证，首次获得 `NEW_SHIP` 未适配 |
| 18 | EventC | 同 EventA | P | C1-C3 地图脚本存在，无实机闭环 |
| 19 | EventD | 同 EventA | P | D1-D3 地图脚本存在，无实机闭环 |
| 20 | EventSp | Scheduler, Campaign, StopCondition, Fleet, Submarine, Emotion, HpControl, EnemyPriority | P | SP 地图脚本存在，无实机闭环 |
| 21 | RaidDaily | Scheduler, RaidDaily, Campaign, StopCondition, Emotion | M | 难度过滤、每日次数、战斗和领奖缺适配 |
| 22 | Commission | Scheduler, Commission | L | 领取和零油开始有证据；非零油、重大委托、全部过滤器、取消和连续循环未闭环 |
| 23 | Tactical | Scheduler, Tactical, ControlExpOverflow, AddNewStudent | L | 十个专属配置字段离线契约已完成；真实收藏/等级候选、完整书库存、四槽快速学习实机结果及安全回滚仍未闭环 |
| 24 | Research | Scheduler, Research | L | 一个金币项目闭环；魔方/零件、延迟、重置、26 个预设和自定义规则未完整覆盖 |
| 25 | Dorm | Scheduler, Dorm, BuyFurniture | L | 默认收取和喂食闭环；食物过滤、买家具、套装/全部和日期状态未闭环 |
| 26 | Meowfficer | Scheduler, Meowfficer, MeowfficerTrain | M | 买箱、金币溢出、训练、增强和保留天赋规则均缺适配 |
| 27 | Guild | Scheduler, GuildLogistics, GuildOperation | M | 后勤兑换、新任务、作战、Boss 和推荐舰队均缺适配 |
| 28 | Reward | Scheduler, Reward | P | 五个领取开关及 RaidDaily 共享入口已离线完成；资源气泡可领取，任务领取部分可用，周常、红点、数字行、空页面和舰船奖励仍未完整闭环 |
| 29 | Awaken | Scheduler, Awaken | M | 收藏过滤、120/125 上限及批量觉醒缺适配 |
| 30 | Daily | Scheduler, Daily | L | 十四字段离线映射与 fail-closed 契约已完成；实机仍只闭环 Tactical Training 第二关默认舰队，其余日常和配置值未闭环 |
| 31 | Hard | Scheduler, Hard | B | 64 关目录与两舰队离线契约已完成；实机仍只到 11-4 进入边界，当前账号进度和自动寻敌锁定，尚无战斗/结算证据 |
| 32 | Exercise | Scheduler, Exercise | L | 一种策略闭环；不同选敌/时段策略、刷新、试探次数、低血重试和失败恢复未闭环 |
| 33 | ShopFrequent | Scheduler, GeneralShop | B | 可读页面并安全跳过；购买、过滤、刷新、金币/钻石和皮肤箱均未完成 |
| 34 | ShopOnce | Scheduler, GuildShop, MedalShop2, MeritShop, CoreShop | P | 只有勋章商店一次 DR 图纸购买；其他商店、过滤/子选项和刷新未闭环 |
| 35 | Shipyard | Scheduler, ShipyardDr, Shipyard | B | 可识别 30/30 并停止；系列、舰船、数量和实际蓝图消耗未验证 |
| 36 | Gacha | Scheduler, Gacha | L | 一次轻型建造闭环；其他卡池、1-10 次、快速完成、票券及队列领取未闭环 |
| 37 | Freebies | Scheduler, BattlePass, DataKey, Mail, SupplyPack | P | Mail 四开关和 SupplyPack 两字段已离线完成；Data Key 有证据，BattlePass 不可用，补给包当前实机无免费项且未执行领取 |
| 38 | Minigame | Scheduler | L | 当前抚顺小游戏路径可用；没有字段配置，但其他轮换小游戏仍属于该任务支持范围 |
| 39 | PrivateQuarters | Scheduler, PrivateQuarters | M | 蛋糕、玫瑰、互动和 7 个舰船选项均缺适配 |
| 40 | OpsiGeneral | OpsiGeneral | P | 共享页面可读；随机事件、明石过滤、行动力购买、维修阈值、油量和 Logger 未完整覆盖 |
| 41 | OpsiAshBeacon | Scheduler, OpsiAshBeacon | B | 入口/状态可读；受点数限制，当前/档案、自动攻击、一击、求助和完整领取未闭环 |
| 42 | OpsiAshAssist | Scheduler, OpsiAshAssist | B | 可到列表/开始提示；受舰队条件限制，Tier、出击、战斗和领奖未闭环 |
| 43 | OpsiExplore | Scheduler, OpsiExplore, OpsiFleet | B | 到自动寻敌锁定边界；强制运行、续跑区、特殊雷达、舰队/潜艇和清区未闭环 |
| 44 | OpsiShop | Scheduler, OpsiShop | B | 可读取并零购买停止；5 个预设、自定义过滤、购买/刷新/货币链路未闭环 |
| 45 | OpsiVoucher | Scheduler, OpsiVoucher | B | 可读取并零购买停止；过滤器命中和实际兑换未闭环 |
| 46 | OpsiDaily | Scheduler, OpsiDaily, OpsiFleet | B | 可接任务并进入目标海域；任务开关、调律样本、舰队/潜艇和清图未闭环 |
| 47 | OpsiObscure | Scheduler, OpsiObscure, OpsiFleet | B | 可读仓库/详情；强制运行、坐标消耗、进入和清图未闭环 |
| 48 | OpsiAbyssal | Scheduler, OpsiAbyssal, OpsiFleetFilter | B | 可读仓库/详情；强制运行、过滤器、坐标消耗、Boss 和结算未闭环 |
| 49 | OpsiArchive | Scheduler, OpsiFleet | B | 可读档案商店；舰队/潜艇、购买、使用坐标、进入和清图未闭环 |
| 50 | OpsiStronghold | Scheduler, OpsiStronghold, OpsiFleetFilter | M | 3D 漩涡当前无法由 UI 树可靠观察；存在检测、过滤、进入、战斗和结算均未闭环 |
| 51 | OpsiMonthBoss | Scheduler, OpsiMonthBoss, OpsiFleetFilter | B | 能在适应性不足时安全停止；模式、强制运行、过滤器和普通/困难 Boss 未闭环 |
| 52 | OpsiMeowfficerFarming | Scheduler, OpsiMeowfficerFarming, OpsiFleet | B | 到自动寻敌锁定边界；危险等级、行动力保留、选区、舰队/潜艇和循环未闭环 |
| 53 | OpsiHazard1Leveling | Scheduler, OpsiHazard1Leveling, OpsiFleet | B | 到自动寻敌锁定边界；目标区、舰队/潜艇和循环未闭环 |
| 54 | OpsiCrossMonth | Scheduler | B | 非月末安全跳过；月末执行、重置和跨月恢复未验证 |
| 55 | Daemon | Daemon | P | 单轮条件路径可用；进入地图开关、长期值守和稀有恢复分支未闭环 |
| 56 | OpsiDaemon | OpsiDaemon | P | 单轮条件路径可用；修船/选敌各开关组合及长期恢复未闭环 |
| 57 | EventStory | EventStory | P | 46 个故事中只跑过一条入口路径；战斗转场、跳过战斗及其他故事结构未闭环 |
| 58 | Benchmark | Benchmark | L | 当前设备默认 `screenshot_click` 跑过；设备类型和测试场景矩阵未覆盖 |
| 59 | AzurLaneUncensored | AzurLaneUncensored | P | 本地 localization 路径可用；`Repository` 对应的远端同步在上游被注释，配置与能力不一致 |
| 60 | GameManager | GameManager | L | `AutoRestart=true` 跑过；`false`、只停不启和异常生命周期未覆盖 |

## 3. 配置组字段级矩阵

### 3.1 全局、调度、退役与强化

| 配置组 | 字段与取值 | 当前 | 完整支持必须满足 |
|---|---|:---:|---|
| Scheduler | `Enable`; `NextRun`; 隐藏字段 `Command`, `SuccessInterval`, `FailureInterval`, `ServerUpdate` | R | 启用/禁用、成功/失败间隔、跨服务器刷新时刻、重启恢复、重复调度和非法时间必须可预测；不同任务对隐藏字段的 override 必须保留 |
| Emulator | `Serial`; `PackageName`（22 值）; `ServerName`（72 值）; `ScreenshotMethod`=`auto/ADB/ADB_nc/uiautomator2/aScreenCap/aScreenCap_nc/DroidCast/DroidCast_raw/nemu_ipc/ldopengl`; `ControlMethod`=`ADB/uiautomator2/minitouch/Hermit/MaaTouch`; `ScreenshotDedithering`; `AdbRestart` | P | Headless 明确支持/拒绝每种方法；至少覆盖当前包/服务器、自动发现失败、设备断连、重连和方法不兼容；不能静默回退到未经授权的像素路径 |
| EmulatorInfo | `Emulator`=`auto/NoxPlayer/NoxPlayer64/BlueStacks4/BlueStacks5/BlueStacks4HyperV/BlueStacks5HyperV/LDPlayer3/LDPlayer4/LDPlayer9/LDPlayer14/MuMuPlayer/MuMuPlayerX/MuMuPlayer12/MEmuPlayer`; `name`; `path` | P | 自动与显式模拟器发现、找不到安装、多个实例和自定义路径均需 fail-closed |
| Error | `HandleError`; `SaveError`; `OnePushConfig`; `ScreenshotLength` | P | 两个布尔值组合、错误证据可用性、截图长度边界、通知成功/失败/未配置，以及不泄漏敏感信息 |
| Optimization | `ScreenshotInterval`; `CombatScreenshotInterval`; `TaskHoardingDuration`; `WhenTaskQueueEmpty`=`stay_there/goto_main/close_game` | P | `TaskHoardingDuration` 已完成 0..1440 分钟离线契约并保留原调度器；截图间隔缺初始化期门禁/跨后端帧时钟证据，`close_game` 缺包进程租约，空队列恢复仍未闭环 |
| DropRecord | `ResearchRecord`, `CommissionRecord`, `CombatRecord`, `OpsiRecord`, `MeowfficerBuy`, `MeowfficerTalent`; `API`; `AzurStatsID`; `SaveFolder` | M | `do_not/save/upload/save_and_upload` 各模式、默认/反代 API、无 ID、无权限目录、网络失败、脱敏和重试；没有有效画面时不得生成伪证据 |
| Retirement | `RetireMode`=`one_click_retire/enhance/old_retire` | P | `one_click_retire` 已走游戏官方事务并用容量差验证真实数量；`enhance` 已接 ALAS 正式任务并走官方推荐事务；仍需补 `old_retire`、完整收藏破坏性任务、自然无素材和非网络中断实机证据 |
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
| Hospital | `UseRecommendFleet` | M | 开关两值、推荐不可用、手动舰队、活动结束和结算 |
| EventDaily | `StageFilter`（A/B/C/D 各自 1-3 优先级字符串）；`LastStage` | P | 四分区过滤、缺脚本、无匹配、未解锁、游标恢复及跨日重置已离线覆盖；仍需 B-D 实机轮转和活动切换后的持久化收据 |
| RaidDaily | `StageFilter`=`hard > normal > easy`（自由优先级字符串） | M | 各难度可用组合、过滤命中/无命中/非法值、次数耗尽和每日重置 |

### 3.4 委托、战术、科研、宿舍、猫箱、公会与奖励

| 配置组 | 字段与取值 | 当前 | 完整支持必须满足 |
|---|---|:---:|---|
| Commission | `PresetFilter`=`cube/cube_24h/chip/chip_24h/oil/custom`; `CustomFilter`; `DoMajorCommission` | L | 6 预设、规则命中/无命中/非法值、日常委托/紧急委托、0/非 0 油、重大委托、取消和连续派遣 |
| Tactical | `RapidTrainingSlot`=`do_not_use/slot_1/slot_2/slot_3/slot_4`; `TacticalFilter` | L | 五值槽位与完整过滤语法已离线覆盖；仍需真实快速学习可用性/次数、完整书库存、无书/无空位及教学结果闭环 |
| ControlExpOverflow | `Enable`; `T1Allow`; `T2Allow`; `T3Allow`; `T4Allow` | P | 离线关闭/启用及各等级 0/配置/最大/越界已覆盖；仍需真实库存、当前技能经验及选书结果闭环 |
| AddNewStudent | `Enable`; `Favorite`; `MinLevel` | P | 离线开关、收藏传播和等级边界已覆盖；仍需真实收藏候选状态、无/多候选及教学结果验证 |
| Research | `PresetFilter`（26 值）; `CustomFilter`; `AllowDelay`; `UseCoin`, `UseCube`, `UsePart`=`always_use/only_05_hour/only_no_project/do_not_use` | L | 26 预设、自由规则、重置、延迟、三种资源各四策略、资源不足、队列满和跨轮选择 |
| Dorm | `Collect`; `Feed`; `FeedFilter` | L | 两开关四组合、食物规则命中/回退/无食物、宿舍满、收取为空和喂食结果 |
| BuyFurniture | `Enable`; `BuyOption`=`set/all`; `LastRun` | P | 开关、套装/全部、货币不足、已购买、日期去重和购买确认 |
| Meowfficer | `BuyAmount`; `FortChoreMeowfficer`; `OverflowCoins` | M | 数量 0/边界、保留后勤猫、金币阈值、箱位满和购买确认 |
| MeowfficerTrain | `Enable`; `Mode`=`seamlessly/once_a_day`; `RetainTalentedGold`; `RetainTalentedPurple`; `MaxFeedLevel`; `EnhanceIndex` | M | 两训练模式、两保留开关组合、等级/索引边界、无材料、错误目标保护和每日去重 |
| GuildLogistics | `Enable`; `ExchangeFilter`; `SelectNewMission` | M | 开关、兑换规则、新任务选择、贡献不足、无奖励和重复领取 |
| GuildOperation | `Enable`; `JoinThreshold`; `SelectNewOperation`; `NewOperationMaxDate`; `AttackBoss`; `BossFleetRecommend` | M | 阈值/日期边界、加入/选择、Boss 与非 Boss、推荐舰队开关、次数不足和奖励 |
| Reward | `CollectOil`; `CollectCoin`; `CollectExp`; `CollectMission`; `CollectWeeklyMission` | P | 32 种开关组合、20 个非法单字段案例及 Reward/RaidDaily 双入口 fail-closed 已离线完成；仍缺资源上限、日常/周常领取后置条件、数字行、空页、红点和特殊奖励实机闭环 |
| Awaken | `Favourite`; `LevelCap`=`level120/level125` | M | 收藏真假、两个上限、资源不足、无候选、批量选择和确认结果 |

### 3.5 每日、演习、商店、船坞、建造与免费领取

| 配置组 | 字段与取值 | 当前 | 完整支持必须满足 |
|---|---|:---:|---|
| Daily | `EscortMission`, `AdvanceMission`, `TacticalTraining`, `SupplyLineDisruption`, `FierceAssault`=`skip/first/second/third`; `ModuleDevelopment`, `EmergencyModuleDevelopment`=`skip/first/second`; `EscortMissionFleet`, `AdvanceMissionFleet`, `TacticalTrainingFleet`, `FierceAssaultFleet`, `ModuleDevelopmentFleet`, `EmergencyModuleDevelopmentFleet`=1..6；`UseDailySkip` | L | 全值域、两种排列、skip、次数耗尽及 SupplyLine fleet=0 已离线覆盖；仍缺非默认任务/难度/舰队、快速跳过不可用和战斗结算的实机收据 |
| Hard | `HardStage`; `HardFleet`=1/2 | B | 固定上游 64 关目录、两舰队、次数为 0/3 和非法值已离线覆盖；仍缺未解锁页、非默认关卡/舰队、真实战斗和结算收据 |
| Exercise | `ExerciseStrategy`=`aggressive/fri18/sat0/sat12/sat18/sun0/sun12/sun18`; `OpponentChooseMode`=`max_exp/easiest/leftmost/easiest_else_exp`; `OpponentRefreshValue`; `OpponentRefreshRecord`; `OpponentTrial`; `LowHpThreshold`; `LowHpConfirmWait` | L | 8 时段策略、4 选敌策略、刷新次数/记录、试探次数、低血阈值与等待、失败重开和赛季边界 |
| GeneralShop | `Filter`; `Refresh`; `UseGems`; `ConsumeCoins`; `BuySkinBox` | B | 过滤命中/无命中/非法值，刷新真假，钻石/金币消费保护，皮肤箱和购买确认 |
| GuildShop | `Filter`; `Refresh`; `BOOK_T2`; `BOOK_T3`; `BOX_T3`; `BOX_T4`; `PLATE_T2`; `PLATE_T3`; `PLATE_T4`; `RETROFIT_T2`; `RETROFIT_T3`; `PR1`; `PR2`; `PR3` | P | 14 个字段的每个枚举、刷新前后、货币不足、库存为空、商品同名歧义和确认；舰船/阵营/部件选择必须核验 |
| MedalShop2 | `Filter`; `PLATE_T1`; `PLATE_T2`; `PLATE_T3`; `RETROFIT_T1`; `RETROFIT_T2`; `RETROFIT_T3` | L | 当前只有一次 DR 图纸；7 字段的所有选择、商品轮换、库存/勋章不足和确认未闭环 |
| MeritShop | `Filter`; `Refresh` | M | 规则命中、刷新真假、功勋不足和购买确认 |
| CoreShop | `Filter` | M | 规则命中/无命中、核心不足、月限购和确认 |
| ShipyardDr | `ResearchSeries`=2..5; `ShipIndex`=0..6; `BuyAmount`; `LastRun` | B | 每系列/舰船、自动索引 0、数量边界、每日去重、蓝图不足、达到上限和实际购买 |
| Shipyard | `ResearchSeries`=1..6; `ShipIndex`=0..6; `BuyAmount`; `LastRun` | B | 同上，且 PR/DR 页面切换不能串页 |
| Gacha | `Amount`=1..10; `Pool`=`light/heavy/special/event/wishing_well`; `UseDrill`; `UseTicket` | L | 50 个数量/卡池组合可按等价类压缩；票券、快速完成、队列满、活动池不存在、资源不足和领取 |
| BattlePass | `Collect` | B | 开关两值、入口不可用、免费/付费奖励区别、无奖励和领取结果 |
| DataKey | `Collect`; `ForceCollect` | L | 四组合、上限、普通/强制领取、无可领和结果校验 |
| Mail | `ClaimMerit`; `ClaimMaintenance`; `ClaimTradeLicense`; `DeleteCollected` | P | 16 组合、不同邮件类型、附件为空、容量上限、只删除已领取和误删保护 |
| SupplyPack | `Collect`; `DayOfWeek`=0..6 | B | 开关、七天、日期比较和高油保护已离线覆盖；仍缺免费包已领/可领、跨日、真实领取收据和购买项误触保护实机证据 |
| PrivateQuarters | `BuyCake`; `BuyRoses`; `TargetInteract`; `TargetShip`=`anchorage/noshiro/sirius/new_jersey/taihou/aegir/nakhimov` | M | 三开关组合、7 舰船、目标未解锁、货币不足、互动次数和购买确认 |
| Minigame | 无用户字段，仅 Scheduler | L | 仍需按实际轮换小游戏建立子类型清单；未知小游戏必须安全退出，不能因无字段而宣称全部支持 |

### 3.6 大世界配置

| 配置组 | 字段与取值 | 当前 | 完整支持必须满足 |
|---|---|:---:|---|
| OpsiGeneral | `DoRandomMapEvent`; `AkashiShopFilter`; `BuyActionPointLimit`=0..5; `OilLimit`; `RepairThreshold`; `UseLogger` | P | 随机事件开关、过滤器、购买次数、油量/血量边界、Logger 有无及维修/购买确认 |
| OpsiAshBeacon | `AttackMode`=`current/current_dossier`; `DossierAutoAttackMode`; `EnsureFullyCollected`; `OneHitMode`; `RequestAssist` | B | 当前/档案、三个布尔开关组合、点数不足/满、生成、攻击、求助、领取和 Boss 结束 |
| OpsiAshAssist | `Tier` | B | Tier 边界、无目标、舰队不可用、出击、战斗和奖励 |
| OpsiExplore | `ForceRun`; `LastZone`; `SpecialRadar` | B | 强制真假、续跑区有效/失效、雷达真假、地图重置和清区 |
| OpsiFleet | `Fleet`=1..4; `Submarine` | B | 四舰队、潜艇真假、舰队不可用、选中结果和调用结果；某些面板隐藏 Submarine 也要保持 override |
| OpsiShop | `PresetFilter`=`max_benefit/max_benefit_meta/no_meta/all/custom`; `CustomFilter` | B | 5 预设、自由规则、不同港口库存、货币不足、刷新、购买确认和无匹配 |
| OpsiVoucher | `Filter` | B | 规则命中/无命中/非法值、兑换券不足、限购和确认 |
| OpsiDaily | `DoMission`; `UseTuningSample` | B | 四组合、无任务、接取/进入/清图、样本有无和跨日恢复 |
| OpsiObscure | `ForceRun` | B | 开关、坐标不存在/存在、消耗、进入、清图与奖励 |
| OpsiAbyssal | `ForceRun` | B | 开关、坐标、Boss、多舰队、撤退/失败和奖励 |
| OpsiFleetFilter | `Filter`（默认含 Fleet-4、CallSubmarine、Fleet-2/3/1） | B | 过滤器顺序、潜艇条目、舰队不可用、无匹配、非法规则和最终选中结果 |
| OpsiStronghold | `ForceRun` | M | 先补足 3D 漩涡存在性观察；再验证开关、进入、舰队选择、战斗、撤退和结算 |
| OpsiMonthBoss | `Mode`=`normal/normal_hard`; `CheckAdaptability`; `ForceRun` | B | 两模式、两个开关组合、适应性不足/足够、普通/困难切换、战斗和奖励 |
| OpsiMeowfficerFarming | `HazardLevel`=3/4/5/6/10; `TargetZone`; `ActionPointPreserve` | B | 五危险等级、自动/显式区域、行动力边界、舰队/潜艇、循环与停止 |
| OpsiHazard1Leveling | `TargetZone`=0/44/22 | B | 三目标值、不可用区域、舰队/潜艇、自动寻敌和循环停止 |
| OpsiArchive | 无独立组，复用 Scheduler 与 OpsiFleet | B | 档案商店购买、坐标使用、舰队/潜艇、进入/清图与奖励 |
| OpsiCrossMonth | 无独立组，仅 Scheduler | B | 月末前后、服务器时区、重置完成/失败、重启续跑和幂等性 |

### 3.7 工具任务

| 配置组 | 字段与取值 | 当前 | 完整支持必须满足 |
|---|---|:---:|---|
| Daemon | `EnterMap` | P | 开关两值、主界面/地图内启动、恢复循环和未知弹窗 |
| OpsiDaemon | `RepairShip`; `SelectEnemy` | P | 四组合、无需维修/需要维修、无敌人/有敌人、长期循环和异常恢复 |
| EventStory | `SkipBattle`（当前只允许 true） | P | 所有可发现故事入口、剧情选项、战斗转场、活动结束和幂等领取；固定 true 也不能跳过分支验收 |
| Benchmark | `DeviceType`=`emulator/plone_cloud_with_adb/phone_cloud_without_adb/android_phone/android_phone_vmos`; `TestScene`=`screenshot_click/screenshot/click` | L | 5×3 矩阵或等价性证明；无截图设备、无 ADB 设备和纯点击场景必须报告真实能力 |
| AzurLaneUncensored | `Repository` | P | 先决定恢复远端同步还是删除/禁用该配置；网络失败、仓库不可达、本地文件和回滚必须有明确契约 |
| GameManager | `AutoRestart` | L | true/false、游戏已开/已关/卡死、启动失败、停止失败和重试上限 |

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
| ✅ 五维完整支持 | **0 / 278** | 当前没有任何详细设置同时完成全部值的配置、观察、输入、离线和实机闭环 |
| ◐ 有实机当前值/分支证据 | **151 / 278** | 至少一个当前值或安全停止分支在实机出现；仍不是完整支持 |
| 🧪 只有离线路径证据 | **30 / 278** | 有设置相关离线覆盖，但没有该设置的实机值证据 |
| ⊘ 当前未适配或无效 | **55 / 278** | 任务级语义端口缺失，或配置当前不产生对应能力 |
| ☐ 只有配置声明/读取 | **42 / 278** | 配置可以存在，但未找到设置相关的 Headless 闭环证据 |

| 配置组.字段 | 使用面板 | 类型/显示元数据 | 默认值与可选值 | 组级现状 | 配置读取 | 语义观察 | 输入闭环 | 离线证据 | 实机证据 |
|---|---|---|---|:---:|:---:|:---:|:---:|:---:|:---:|
| `AddNewStudent.Enable` | Tactical | type=checkbox; display=default | input/default: false | `P`/☐ 未逐值 | ☑ | ☐ | ☐ | ☑ | ☐ |
| `AddNewStudent.Favorite` | Tactical | type=checkbox; display=default | input/default: false | `P`/☐ 未逐值 | ☑ | ☐ | ☐ | ☑ | ☐ |
| `AddNewStudent.MinLevel` | Tactical | type=input; display=default | input/default: 50 | `P`/☐ 未逐值 | ☑ | ☐ | ☐ | ☑ | ☐ |
| `Awaken.Favourite` | Awaken | type=checkbox; display=default | input/default: false | `M`/⊘ 未适配 | ☑ | ⊘ | ⊘ | ⊘ | ⊘ |
| `Awaken.LevelCap` | Awaken | type=select; display=default | options: "level120", "level125"; default: "level120" | `M`/⊘ 未适配 | ☑ | ⊘ | ⊘ | ⊘ | ⊘ |
| `AzurLaneUncensored.Repository` | AzurLaneUncensored | type=input; display=disabled | input/default: "https://gitee.com/LmeSzinc/AzurLaneUncensored" | `P`/⊘ 当前无效 | ⊘ | ⊘ | ⊘ | ⊘ | ⊘ |
| `BattlePass.Collect` | Freebies | type=checkbox; display=default | input/default: true | `B`/◐ 实机当前值 | ☑ | ◐ | ☐ | ☐ | ◐ |
| `Benchmark.DeviceType` | Benchmark | type=select; display=default | options: "android_phone_vmos", "android_phone", "emulator", "phone_cloud_without_adb", "plone_cloud_with_adb"; default: "emulator" | `L`/◐ 实机当前值 | ☑ | ◐ | ☐ | ◐ | ◐ |
| `Benchmark.TestScene` | Benchmark | type=select; display=default | options: "click", "screenshot_click", "screenshot"; default: "screenshot_click" | `L`/◐ 实机当前值 | ☑ | ◐ | ◐ | ◐ | ◐ |
| `BuyFurniture.BuyOption` | Dorm | type=select; display=default | options: "all", "set"; default: "all" | `P`/☐ 未逐值 | ☑ | ☐ | ☐ | ☐ | ☐ |
| `BuyFurniture.Enable` | Dorm | type=checkbox; display=default | input/default: false | `P`/◐ 实机当前值 | ☑ | ◐ | ☐ | ☐ | ◐ |
| `BuyFurniture.LastRun` | Dorm | type=datetime; display=default; validate=datetime | input/default: "2020-01-01 00:00:00" | `P`/☐ 未逐值 | ☑ | ☐ | ☐ | ☐ | ☐ |
| `Campaign.AmbushEvade` | Main, Main2, Main3, GemsFarming, Coalition, Event, Event2, Raid, WarArchives, CoalitionSp, EventA, EventB, EventC, EventD, EventSp, RaidDaily | type=checkbox; display=default/hide | input/default: true | `P`/◐ 实机当前值 | ☑ | ◐ | ☐ | ☑ | ◐ |
| `Campaign.Event` | Main, Main2, Main3, GemsFarming, Coalition, Event, Event2, Raid, WarArchives, CoalitionSp, EventA, EventB, EventC, EventD, EventSp, RaidDaily | type=select; display=default/hide | options: "campaign_main", "coalition_20260723", "event_20260625_cn", "event_20260813_cn", "raid_20260212", "war_archives_20180607_cn", "war_archives_20180726_cn", "war_archives_20181020_en", "war_archives_20181026_en", "war_archives_20181227_cn", "war_archives_20190221_en", "war_archives_20190314_en", "war_archives_20190321_en", "war_archives_20190620_en", "war_archives_20190911_cn", "war_archives_20191010_en", "war_archives_20191031_en", "war_archives_20200312_cn", "war_archives_20200507_cn", "war_archives_20200603_cn", "war_archives_20200806_cn", "war_archives_20200820_cn", "war_archives_20200903_cn", "war_archives_20200917_cn", "war_archives_20201012_cn", "war_archives_20201029_cn", "war_archives_20201229_cn", "war_archives_20210225_cn", "war_archives_20210325_cn", "war_archives_20210422_cn", "war_archives_20210527_cn", "war_archives_20210624_cn", "war_archives_20210819_cn", "war_archives_20210916_cn", "war_archives_20211014_cn", "war_archives_20211028_cn", "war_archives_20211111_cn", "war_archives_20211229_cn", "war_archives_20220210_cn", "war_archives_20220224_cn", "war_archives_20220324_cn", "war_archives_20220414_cn", "war_archives_20220428_cn", "war_archives_20220526_cn", "war_archives_20220728_cn", "war_archives_20220818_cn", "war_archives_20220915_cn", "war_archives_20221222_cn", "war_archives_20230223_cn", "war_archives_20230525_cn", "war_archives_20230803_cn", "war_archives_20231026_cn", "war_archives_20240725_cn"; default: "campaign_main" | `P`/◐ 实机当前值 | ☑ | ◐ | ◐ | ◐ | ◐ |
| `Campaign.Mode` | Main, Main2, Main3, GemsFarming, Coalition, Event, Event2, Raid, WarArchives, CoalitionSp, EventA, EventB, EventC, EventD, EventSp, RaidDaily | type=select; display=default/hide | options: "hard", "normal"; default: "normal" | `P`/◐ 实机当前值 | ☑ | ◐ | ◐ | ◐ | ◐ |
| `Campaign.Name` | Main, Main2, Main3, GemsFarming, Coalition, Event, Event2, Raid, WarArchives, CoalitionSp, EventA, EventB, EventC, EventD, EventSp, RaidDaily | type=input; display=default/hide | input/default: "12-4", "dynamic", "sp" | `P`/◐ 实机当前值 | ☑ | ◐ | ◐ | ◐ | ◐ |
| `Campaign.Use2xBook` | Main, Main2, Main3, GemsFarming, Coalition, Event, Event2, Raid, WarArchives, CoalitionSp, EventA, EventB, EventC, EventD, EventSp, RaidDaily | type=checkbox; display=default/hide | input/default: false | `P`/◐ 实机当前值 | ☑ | ◐ | ☐ | ☑ | ◐ |
| `Campaign.UseAutoSearch` | Main, Main2, Main3, GemsFarming, Coalition, Event, Event2, Raid, WarArchives, CoalitionSp, EventA, EventB, EventC, EventD, EventSp, RaidDaily | type=checkbox; display=default/hide | input/default: false, true | `P`/◐ 实机当前值 | ☑ | ◐ | ◐ | ☑ | ◐ |
| `Campaign.UseClearMode` | Main, Main2, Main3, GemsFarming, Coalition, Event, Event2, Raid, WarArchives, CoalitionSp, EventA, EventB, EventC, EventD, EventSp, RaidDaily | type=checkbox; display=default/hide | input/default: true | `P`/◐ 实机当前值 | ☑ | ◐ | ☐ | ☑ | ◐ |
| `Campaign.UseFleetLock` | Main, Main2, Main3, GemsFarming, Coalition, Event, Event2, Raid, WarArchives, CoalitionSp, EventA, EventB, EventC, EventD, EventSp, RaidDaily | type=checkbox; display=default/hide | input/default: true | `P`/◐ 实机当前值 | ☑ | ◐ | ◐ | ☑ | ◐ |
| `Coalition.Fleet` | Coalition, CoalitionSp | type=select; display=default | options: "multi", "single"; default: "single" | `M`/⊘ 未适配 | ☑ | ⊘ | ⊘ | ⊘ | ⊘ |
| `Coalition.Mode` | Coalition, CoalitionSp | type=select; display=default/hide | options: "easy", "hard", "normal", "sp"; default: "hard", "sp" | `M`/⊘ 未适配 | ☑ | ⊘ | ⊘ | ⊘ | ⊘ |
| `Commission.CustomFilter` | Commission | type=textarea; display=default | input/default: <long default in args.json> | `L`/☐ 未逐值 | ☑ | ☐ | ☐ | ☐ | ☐ |
| `Commission.DoMajorCommission` | Commission | type=checkbox; display=default | input/default: false | `L`/◐ 实机当前值 | ☑ | ◐ | ☐ | ◐ | ◐ |
| `Commission.PresetFilter` | Commission | type=select; display=default | options: "chip_24h", "chip", "cube_24h", "cube", "custom", "oil"; default: "cube" | `L`/◐ 实机当前值 | ☑ | ◐ | ◐ | ◐ | ◐ |
| `ControlExpOverflow.Enable` | Tactical | type=checkbox; display=default | input/default: true | `P`/◐ 实机当前值 | ☑ | ◐ | ☐ | ☑ | ◐ |
| `ControlExpOverflow.T1Allow` | Tactical | type=input; display=default | input/default: 200 | `P`/☐ 未逐值 | ☑ | ☐ | ☐ | ☑ | ☐ |
| `ControlExpOverflow.T2Allow` | Tactical | type=input; display=default | input/default: 200 | `P`/☐ 未逐值 | ☑ | ☐ | ☐ | ☑ | ☐ |
| `ControlExpOverflow.T3Allow` | Tactical | type=input; display=default | input/default: 100 | `P`/☐ 未逐值 | ☑ | ☐ | ☐ | ☑ | ☐ |
| `ControlExpOverflow.T4Allow` | Tactical | type=input; display=default | input/default: 100 | `P`/◐ 实机当前值 | ☑ | ◐ | ☐ | ☑ | ◐ |
| `CoreShop.Filter` | ShopOnce | type=textarea; display=default | input/default: "Array" | `M`/⊘ 未适配 | ☑ | ⊘ | ⊘ | ⊘ | ⊘ |
| `Daemon.EnterMap` | Daemon | type=checkbox; display=default | input/default: true | `P`/◐ 实机当前值 | ☑ | ◐ | ☐ | ☐ | ◐ |
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
| `DataKey.Collect` | Freebies | type=checkbox; display=default | input/default: true | `L`/◐ 实机当前值 | ☑ | ◐ | ☐ | ◐ | ◐ |
| `DataKey.ForceCollect` | Freebies | type=checkbox; display=default | input/default: false | `L`/◐ 实机当前值 | ☑ | ◐ | ☐ | ◐ | ◐ |
| `Dorm.Collect` | Dorm | type=checkbox; display=default | input/default: true | `L`/◐ 实机当前值 | ☑ | ◐ | ◐ | ◐ | ◐ |
| `Dorm.Feed` | Dorm | type=checkbox; display=default | input/default: true | `L`/◐ 实机当前值 | ☑ | ◐ | ◐ | ◐ | ◐ |
| `Dorm.FeedFilter` | Dorm | type=textarea; display=default | input/default: "20000 > 10000 > 5000 > 3000 > 2000 > 1000" | `L`/◐ 实机当前值 | ☑ | ◐ | ◐ | ◐ | ◐ |
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
| `Emulator.AdbRestart` | Alas | type=checkbox; display=default | input/default: false | `P`/☐ 未逐值 | ☑ | ☐ | ☐ | ☐ | ☐ |
| `Emulator.ControlMethod` | Alas | type=select; display=default | options: "ADB", "Hermit", "MaaTouch", "minitouch", "uiautomator2"; default: "MaaTouch" | `P`/◐ 实机当前值 | ☑ | ◐ | ☐ | ◐ | ◐ |
| `Emulator.PackageName` | Alas | type=select; display=default | options: "auto", "com.bilibili.azurlane", "com.bilibili.blhx.baidu", "com.bilibili.blhx.bilibiliMove", "com.bilibili.blhx.dl", "com.bilibili.blhx.honor", "com.bilibili.blhx.huawei", "com.bilibili.blhx.lenovo", "com.bilibili.blhx.m4399", "com.bilibili.blhx.mi", "com.bilibili.blhx.mz", "com.bilibili.blhx.mzw", "com.bilibili.blhx.nearme.gamecenter", "com.bilibili.blhx.qihoo", "com.bilibili.blhx.uc", "com.bilibili.blhx.vivo", "com.hkmanjuu.azurlane.gp.mc", "com.hkmanjuu.azurlane.gp", "com.tencent.tmgp.bilibili.blhx", "com.yiwu.blhx.yx15", "com.YoStarEN.AzurLane", "com.YoStarJP.AzurLane"; default: "auto" | `P`/◐ 实机当前值 | ☑ | ◐ | ☐ | ☐ | ◐ |
| `Emulator.ScreenshotDedithering` | Alas | type=checkbox; display=default | input/default: false | `P`/◐ 实机当前值 | ☑ | ◐ | ☐ | ☐ | ◐ |
| `Emulator.ScreenshotMethod` | Alas | type=select; display=default | options: "ADB_nc", "ADB", "aScreenCap_nc", "aScreenCap", "auto", "DroidCast_raw", "DroidCast", "ldopengl", "nemu_ipc", "uiautomator2"; default: "auto" | `P`/◐ 实机当前值 | ☑ | ◐ | ☐ | ◐ | ◐ |
| `Emulator.Serial` | Alas | type=input; display=default | input/default: "auto" | `P`/◐ 实机当前值 | ☑ | ◐ | ☐ | ◐ | ◐ |
| `Emulator.ServerName` | Alas | type=select; display=default | options: "cn_android-0", "cn_android-1", "cn_android-10", "cn_android-11", "cn_android-12", "cn_android-13", "cn_android-14", "cn_android-15", "cn_android-16", "cn_android-17", "cn_android-18", "cn_android-19", "cn_android-2", "cn_android-20", "cn_android-21", "cn_android-22", "cn_android-23", "cn_android-24", "cn_android-25", "cn_android-26", "cn_android-27", "cn_android-28", "cn_android-29", "cn_android-3", "cn_android-4", "cn_android-5", "cn_android-6", "cn_android-7", "cn_android-8", "cn_android-9", "cn_channel-0", "cn_channel-1", "cn_channel-2", "cn_channel-3", "cn_channel-4", "cn_channel-5", "cn_ios-0", "cn_ios-1", "cn_ios-10", "cn_ios-2", "cn_ios-3", "cn_ios-4", "cn_ios-5", "cn_ios-6", "cn_ios-7", "cn_ios-8", "cn_ios-9", "disabled", "en-0", "en-1", "en-2", "en-3", "en-4", "en-5", "jp-0", "jp-1", "jp-10", "jp-11", "jp-12", "jp-13", "jp-14", "jp-15", "jp-16", "jp-17", "jp-2", "jp-3", "jp-4", "jp-5", "jp-6", "jp-7", "jp-8", "jp-9"; default: "disabled" | `P`/☐ 未逐值 | ☑ | ☐ | ☐ | ☐ | ☐ |
| `EmulatorInfo.Emulator` | Alas | type=select; display=default | options: "auto", "BlueStacks4", "BlueStacks4HyperV", "BlueStacks5", "BlueStacks5HyperV", "LDPlayer14", "LDPlayer3", "LDPlayer4", "LDPlayer9", "MEmuPlayer", "MuMuPlayer", "MuMuPlayer12", "MuMuPlayerX", "NoxPlayer", "NoxPlayer64"; default: "auto" | `P`/☐ 未逐值 | ☑ | ☐ | ☐ | ☐ | ☐ |
| `EmulatorInfo.name` | Alas | type=textarea; display=default | input/default: null | `P`/☐ 未逐值 | ☑ | ☐ | ☐ | ☐ | ☐ |
| `EmulatorInfo.path` | Alas | type=textarea; display=default | input/default: null | `P`/☐ 未逐值 | ☑ | ☐ | ☐ | ☐ | ☐ |
| `EnemyPriority.EnemyScaleBalanceWeight` | Main, Main2, Main3, Event, Event2, WarArchives, EventA, EventB, EventC, EventD, EventSp | type=select; display=default | options: "default_mode", "S1_enemy_first", "S3_enemy_first"; default: "default_mode" | `P`/◐ 实机当前值 | ☑ | ◐ | ◐ | ☑ | ◐ |
| `Enhance.CheckPerCategory` | General | type=input; display=default | input/default: 5 | `P`/◐ 正式任务循环已接入 | ☑ | ☑ | ☑ | ☑ | ◐ |
| `Enhance.Filter` | General | type=textarea; display=default | input/default: null | `P`/◐ 8 类型任务筛选已接入 | ☑ | ☑ | ☑ | ☑ | ◐ |
| `Enhance.ShipToEnhance` | General | type=select; display=default | options: "all", "favourite"; default: "all" | `P`/◐ all/favourite typed 控件已实机 | ☑ | ☑ | ☑ | ☑ | ◐ |
| `EquipmentCode.Config` | GemsFarming | type=textarea; display=default | input/default:…4672 tokens truncated…t" | `B`/☐ 未逐值 | ☑ | ☐ | ☐ | ☐ | ☐ |
| `EquipmentCode.ExportToConfig` | GemsFarming | type=checkbox; display=default | input/default: true | `M`/⊘ 未适配 | ☑ | ⊘ | ⊘ | ⊘ | ⊘ |
| `Error.HandleError` | Alas | type=checkbox; display=default | input/default: true | `P`/☐ 未逐值 | ☑ | ☐ | ☐ | ☐ | ☐ |
| `Error.OnePushConfig` | Alas | type=textarea; display=default | input/default: "provider: null" | `P`/☐ 未逐值 | ☑ | ☐ | ☐ | ☐ | ☐ |
| `Error.SaveError` | Alas | type=checkbox; display=default | input/default: true | `P`/☐ 未逐值 | ☑ | ☐ | ☐ | ☐ | ☐ |
| `Error.ScreenshotLength` | Alas | type=input; display=default | input/default: 1 | `P`/☐ 未逐值 | ☑ | ☐ | ☐ | ☐ | ☐ |
| `EventDaily.LastStage` | EventA, EventB, EventC, EventD | type=input; display=default | input/default: 0 | `P`/◐ 实机当前值 | ☑ | ◐ | ☐ | ☑ | ◐ |
| `EventDaily.StageFilter` | EventA, EventB, EventC, EventD | type=textarea; display=default | input/default: "A1 > A2 > A3", "B1 > B2 > B3", "C1 > C2 > C3", "D1 > D2 > D3" | `P`/◐ 实机当前值 | ☑ | ◐ | ◐ | ☑ | ◐ |
| `EventGeneral.PtLimit` | EventGeneral | type=input; display=default | input/default: 0 | `P`/☐ 未逐值 | ☑ | ☐ | ☐ | ☑ | ☐ |
| `EventGeneral.TimeLimit` | EventGeneral | type=datetime; display=default; validate=datetime | input/default: "2020-01-01 00:00:00" | `P`/☐ 未逐值 | ☑ | ☐ | ☐ | ☑ | ☐ |
| `EventStory.SkipBattle` | EventStory | type=lock; display=default | options: true; default: true | `P`/◐ 实机当前值 | ◐ | ◐ | ◐ | ◐ | ◐ |
| `Exercise.ExerciseStrategy` | Exercise | type=select; display=default | options: "aggressive", "fri18", "sat0", "sat12", "sat18", "sun0", "sun12", "sun18"; default: "aggressive" | `L`/◐ 实机当前值 | ☑ | ◐ | ◐ | ◐ | ◐ |
| `Exercise.LowHpConfirmWait` | Exercise | type=input; display=default | input/default: 0.1 | `L`/☐ 未逐值 | ☑ | ☐ | ☐ | ☐ | ☐ |
| `Exercise.LowHpThreshold` | Exercise | type=input; display=default | input/default: 0.4 | `L`/☐ 未逐值 | ☑ | ☐ | ☐ | ☐ | ☐ |
| `Exercise.OpponentChooseMode` | Exercise | type=select; display=default | options: "easiest_else_exp", "easiest", "leftmost", "max_exp"; default: "max_exp" | `L`/◐ 实机当前值 | ☑ | ◐ | ◐ | ◐ | ◐ |
| `Exercise.OpponentRefreshRecord` | Exercise | type=datetime; display=default; validate=datetime | input/default: "2020-01-01 00:00:00" | `L`/◐ 实机当前值 | ☑ | ◐ | ☐ | ☐ | ◐ |
| `Exercise.OpponentRefreshValue` | Exercise | type=input; display=default | input/default: 0 | `L`/◐ 实机当前值 | ☑ | ◐ | ☐ | ☐ | ◐ |
| `Exercise.OpponentTrial` | Exercise | type=input; display=default | input/default: 1 | `L`/◐ 实机当前值 | ☑ | ◐ | ◐ | ◐ | ◐ |
| `Fleet.Fleet1` | Main, Main2, Main3, GemsFarming, Event, Event2, WarArchives, EventA, EventB, EventC, EventD, EventSp | type=select; display=default | options: 1, 2, 3, 4, 5, 6; default: 1 | `P`/◐ 实机当前值 | ☑ | ◐ | ◐ | ☑ | ◐ |
| `Fleet.Fleet1Formation` | Main, Main2, Main3, GemsFarming, Event, Event2, WarArchives, EventA, EventB, EventC, EventD, EventSp | type=select; display=default | options: "diamond", "double_line", "line_ahead"; default: "double_line" | `P`/◐ 实机当前值 | ☑ | ◐ | ◐ | ☑ | ◐ |
| `Fleet.Fleet1Mode` | Main, Main2, Main3, GemsFarming, Event, Event2, WarArchives, EventA, EventB, EventC, EventD, EventSp | type=select; display=default | options: "combat_auto", "combat_manual", "hide_in_bottom_left", "hide_in_upper_left", "stand_still_in_the_middle"; default: "combat_auto" | `P`/◐ 实机当前值 | ☑ | ◐ | ◐ | ☑ | ◐ |
| `Fleet.Fleet1Step` | Main, Main2, Main3, GemsFarming, Event, Event2, WarArchives, EventA, EventB, EventC, EventD, EventSp | type=select; display=default | options: 2, 3, 4, 5; default: 3 | `P`/◐ 实机当前值 | ☑ | ◐ | ◐ | ☑ | ◐ |
| `Fleet.Fleet2` | Main, Main2, Main3, GemsFarming, Event, Event2, WarArchives, EventA, EventB, EventC, EventD, EventSp | type=select; display=default | options: 0, 1, 2, 3, 4, 5, 6; default: 2 | `P`/◐ 实机当前值 | ☑ | ◐ | ◐ | ☑ | ◐ |
| `Fleet.Fleet2Formation` | Main, Main2, Main3, GemsFarming, Event, Event2, WarArchives, EventA, EventB, EventC, EventD, EventSp | type=select; display=default | options: "diamond", "double_line", "line_ahead"; default: "double_line" | `P`/◐ 实机当前值 | ☑ | ◐ | ◐ | ☑ | ◐ |
| `Fleet.Fleet2Mode` | Main, Main2, Main3, GemsFarming, Event, Event2, WarArchives, EventA, EventB, EventC, EventD, EventSp | type=select; display=default | options: "combat_auto", "combat_manual", "hide_in_bottom_left", "hide_in_upper_left", "stand_still_in_the_middle"; default: "combat_auto" | `P`/◐ 实机当前值 | ☑ | ◐ | ◐ | ☑ | ◐ |
| `Fleet.Fleet2Step` | Main, Main2, Main3, GemsFarming, Event, Event2, WarArchives, EventA, EventB, EventC, EventD, EventSp | type=select; display=default | options: 2, 3, 4, 5; default: 2 | `P`/◐ 实机当前值 | ☑ | ◐ | ◐ | ☑ | ◐ |
| `Fleet.FleetOrder` | Main, Main2, Main3, GemsFarming, Event, Event2, WarArchives, EventA, EventB, EventC, EventD, EventSp | type=select; display=default/display | options: "fleet1_all_fleet2_standby", "fleet1_boss_fleet2_mob", "fleet1_mob_fleet2_boss", "fleet1_standby_fleet2_all"; default: "fleet1_all_fleet2_standby", "fleet1_mob_fleet2_boss" | `P`/◐ 实机当前值 | ☑ | ◐ | ◐ | ☑ | ◐ |
| `Gacha.Amount` | Gacha | type=select; display=default | options: 1, 10, 2, 3, 4, 5, 6, 7, 8, 9; default: 1 | `L`/◐ 实机当前值 | ☑ | ◐ | ◐ | ◐ | ◐ |
| `Gacha.Pool` | Gacha | type=select; display=default | options: "event", "heavy", "light", "special", "wishing_well"; default: "light" | `L`/◐ 实机当前值 | ☑ | ◐ | ◐ | ◐ | ◐ |
| `Gacha.UseDrill` | Gacha | type=checkbox; display=default | input/default: false | `L`/◐ 实机当前值 | ☑ | ◐ | ☐ | ◐ | ◐ |
| `Gacha.UseTicket` | Gacha | type=checkbox; display=default | input/default: true | `L`/◐ 实机当前值 | ☑ | ◐ | ☐ | ◐ | ◐ |
| `GameManager.AutoRestart` | GameManager | type=checkbox; display=default | input/default: true | `L`/◐ 实机当前值 | ☑ | ◐ | ◐ | ◐ | ◐ |
| `GemsFarming.ChangeFlagship` | GemsFarming | type=select; display=default | options: "ship_equip", "ship"; default: "ship" | `M`/⊘ 未适配 | ☑ | ⊘ | ⊘ | ⊘ | ⊘ |
| `GemsFarming.ChangeVanguard` | GemsFarming | type=select; display=default | options: "disabled", "ship_equip", "ship"; default: "ship" | `M`/⊘ 未适配 | ☑ | ⊘ | ⊘ | ⊘ | ⊘ |
| `GemsFarming.CommissionLimit` | GemsFarming | type=checkbox; display=default | input/default: true | `M`/⊘ 未适配 | ☑ | ⊘ | ⊘ | ⊘ | ⊘ |
| `GemsFarming.CommonCV` | GemsFarming | type=select; display=default | options: "any", "bogue", "hermes", "langley", "ranger"; default: "any" | `M`/⊘ 未适配 | ☑ | ⊘ | ⊘ | ⊘ | ⊘ |
| `GemsFarming.CommonDD` | GemsFarming | type=select; display=default | options: "any", "aulick_or_foote", "cassin_or_downes", "favourite", "z20_or_z21"; default: "any" | `M`/⊘ 未适配 | ☑ | ⊘ | ⊘ | ⊘ | ⊘ |
| `GeneralShop.BuySkinBox` | ShopFrequent | type=checkbox; display=default | input/default: false | `B`/◐ 实机当前值 | ☑ | ◐ | ☐ | ☐ | ◐ |
| `GeneralShop.ConsumeCoins` | ShopFrequent | type=checkbox; display=default | input/default: false | `B`/◐ 实机当前值 | ☑ | ◐ | ☐ | ☐ | ◐ |
| `GeneralShop.Filter` | ShopFrequent | type=textarea; display=default | input/default: "BookRedT3 > BookYellowT3 > BookBlueT3 > BookRedT2\n> Cube\n> FoodT6 > FoodT5" | `B`/◐ 实机当前值 | ☑ | ◐ | ☐ | ☐ | ◐ |
| `GeneralShop.Refresh` | ShopFrequent | type=checkbox; display=default | input/default: false | `B`/◐ 实机当前值 | ☑ | ◐ | ☐ | ☐ | ◐ |
| `GeneralShop.UseGems` | ShopFrequent | type=checkbox; display=default | input/default: false | `B`/◐ 实机当前值 | ☑ | ◐ | ☐ | ☐ | ◐ |
| `GuildLogistics.Enable` | Guild | type=checkbox; display=default | input/default: true | `M`/⊘ 未适配 | ☑ | ⊘ | ⊘ | ⊘ | ⊘ |
| `GuildLogistics.ExchangeFilter` | Guild | type=textarea; display=default | input/default: <long default in args.json> | `M`/⊘ 未适配 | ☑ | ⊘ | ⊘ | ⊘ | ⊘ |
| `GuildLogistics.SelectNewMission` | Guild | type=checkbox; display=default | input/default: false | `M`/⊘ 未适配 | ☑ | ⊘ | ⊘ | ⊘ | ⊘ |
| `GuildOperation.AttackBoss` | Guild | type=checkbox; display=default | input/default: true | `M`/⊘ 未适配 | ☑ | ⊘ | ⊘ | ⊘ | ⊘ |
| `GuildOperation.BossFleetRecommend` | Guild | type=checkbox; display=default | input/default: false | `M`/⊘ 未适配 | ☑ | ⊘ | ⊘ | ⊘ | ⊘ |
| `GuildOperation.Enable` | Guild | type=checkbox; display=default | input/default: true | `M`/⊘ 未适配 | ☑ | ⊘ | ⊘ | ⊘ | ⊘ |
| `GuildOperation.JoinThreshold` | Guild | type=input; display=default | input/default: 1 | `M`/⊘ 未适配 | ☑ | ⊘ | ⊘ | ⊘ | ⊘ |
| `GuildOperation.NewOperationMaxDate` | Guild | type=input; display=default | input/default: 15 | `M`/⊘ 未适配 | ☑ | ⊘ | ⊘ | ⊘ | ⊘ |
| `GuildOperation.SelectNewOperation` | Guild | type=checkbox; display=default | input/default: false | `M`/⊘ 未适配 | ☑ | ⊘ | ⊘ | ⊘ | ⊘ |
| `GuildShop.BOOK_T2` | ShopOnce | type=select; display=default | options: "blue", "red", "yellow"; default: "red" | `P`/☐ 未逐值 | ☑ | ☐ | ☐ | ☐ | ☐ |
| `GuildShop.BOOK_T3` | ShopOnce | type=select; display=default | options: "blue", "red", "yellow"; default: "red" | `P`/☐ 未逐值 | ☑ | ☐ | ☐ | ☐ | ☐ |
| `GuildShop.BOX_T3` | ShopOnce | type=select; display=default | options: "eagle", "ironblood", "royal", "sakura"; default: "ironblood" | `P`/☐ 未逐值 | ☑ | ☐ | ☐ | ☐ | ☐ |
| `GuildShop.BOX_T4` | ShopOnce | type=select; display=default | options: "eagle", "ironblood", "royal", "sakura"; default: "ironblood" | `P`/☐ 未逐值 | ☑ | ☐ | ☐ | ☐ | ☐ |
| `GuildShop.Filter` | ShopOnce | type=textarea; display=default | input/default: <long default in args.json> | `P`/◐ 实机当前值 | ☑ | ◐ | ☐ | ☐ | ◐ |
| `GuildShop.PLATE_T2` | ShopOnce | type=select; display=default | options: "antiair", "general", "gun", "plane", "torpedo"; default: "general" | `P`/☐ 未逐值 | ☑ | ☐ | ☐ | ☐ | ☐ |
| `GuildShop.PLATE_T3` | ShopOnce | type=select; display=default | options: "antiair", "general", "gun", "plane", "torpedo"; default: "general" | `P`/☐ 未逐值 | ☑ | ☐ | ☐ | ☐ | ☐ |
| `GuildShop.PLATE_T4` | ShopOnce | type=select; display=default | options: "antiair", "general", "gun", "plane", "torpedo"; default: "gun" | `P`/☐ 未逐值 | ☑ | ☐ | ☐ | ☐ | ☐ |
| `GuildShop.PR1` | ShopOnce | type=select; display=default | options: "ibuki", "izumo", "monarch", "neptune", "roon", "saintlouis"; default: "neptune" | `P`/☐ 未逐值 | ☑ | ☐ | ☐ | ☐ | ☐ |
| `GuildShop.PR2` | ShopOnce | type=select; display=default | options: "gascogne", "georgia", "kitakaze", "seattle"; default: "seattle" | `P`/☐ 未逐值 | ☑ | ☐ | ☐ | ☐ | ☐ |
| `GuildShop.PR3` | ShopOnce | type=select; display=default | options: "champagne", "cheshire", "mainz", "odin"; default: "cheshire" | `P`/☐ 未逐值 | ☑ | ☐ | ☐ | ☐ | ☐ |
| `GuildShop.RETROFIT_T2` | ShopOnce | type=select; display=default | options: "bb", "cl", "cv", "dd"; default: "cl" | `P`/☐ 未逐值 | ☑ | ☐ | ☐ | ☐ | ☐ |
| `GuildShop.RETROFIT_T3` | ShopOnce | type=select; display=default | options: "bb", "cl", "cv", "dd"; default: "cl" | `P`/☐ 未逐值 | ☑ | ☐ | ☐ | ☐ | ☐ |
| `GuildShop.Refresh` | ShopOnce | type=checkbox; display=default | input/default: true | `P`/◐ 实机当前值 | ☑ | ◐ | ☐ | ☐ | ◐ |
| `Hard.HardFleet` | Hard | type=select; display=default | options: 1, 2; default: 1 | `B`/◐ 实机当前值 | ☑ | ◐ | ◐ | ☑ | ◐ |
| `Hard.HardStage` | Hard | type=input; display=default | input/default: "11-4" | `B`/◐ 实机当前值 | ☑ | ◐ | ◐ | ☑ | ◐ |
| `Hospital.UseRecommendFleet` | Hospital | type=checkbox; display=default | input/default: true | `M`/⊘ 未适配 | ☑ | ⊘ | ⊘ | ⊘ | ⊘ |
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
| `MedalShop2.Filter` | ShopOnce | type=textarea; display=default | input/default: <long default in args.json> | `L`/◐ 实机当前值 | ☑ | ◐ | ◐ | ☐ | ◐ |
| `MedalShop2.PLATE_T1` | ShopOnce | type=select; display=default | options: "antiair", "general", "gun", "plane", "torpedo"; default: "general" | `L`/☐ 未逐值 | ☑ | ☐ | ☐ | ☐ | ☐ |
| `MedalShop2.PLATE_T2` | ShopOnce | type=select; display=default | options: "antiair", "general", "gun", "plane", "torpedo"; default: "general" | `L`/☐ 未逐值 | ☑ | ☐ | ☐ | ☐ | ☐ |
| `MedalShop2.PLATE_T3` | ShopOnce | type=select; display=default | options: "antiair", "general", "gun", "plane", "torpedo"; default: "general" | `L`/☐ 未逐值 | ☑ | ☐ | ☐ | ☐ | ☐ |
| `MedalShop2.RETROFIT_T1` | ShopOnce | type=select; display=default | options: "bb", "cl", "cv", "dd"; default: "cl" | `L`/☐ 未逐值 | ☑ | ☐ | ☐ | ☐ | ☐ |
| `MedalShop2.RETROFIT_T2` | ShopOnce | type=select; display=default | options: "bb", "cl", "cv", "dd"; default: "cl" | `L`/☐ 未逐值 | ☑ | ☐ | ☐ | ☐ | ☐ |
| `MedalShop2.RETROFIT_T3` | ShopOnce | type=select; display=default | options: "bb", "cl", "cv", "dd"; default: "cl" | `L`/☐ 未逐值 | ☑ | ☐ | ☐ | ☐ | ☐ |
| `Meowfficer.BuyAmount` | Meowfficer | type=input; display=default | input/default: 1 | `M`/⊘ 未适配 | ☑ | ⊘ | ⊘ | ⊘ | ⊘ |
| `Meowfficer.FortChoreMeowfficer` | Meowfficer | type=checkbox; display=default | input/default: true | `M`/⊘ 未适配 | ☑ | ⊘ | ⊘ | ⊘ | ⊘ |
| `Meowfficer.OverflowCoins` | Meowfficer | type=input; display=default | input/default: -1 | `M`/⊘ 未适配 | ☑ | ⊘ | ⊘ | ⊘ | ⊘ |
| `MeowfficerTrain.Enable` | Meowfficer | type=checkbox; display=default | input/default: false | `M`/⊘ 未适配 | ☑ | ⊘ | ⊘ | ⊘ | ⊘ |
| `MeowfficerTrain.EnhanceIndex` | Meowfficer | type=input; display=default | input/default: 1 | `M`/⊘ 未适配 | ☑ | ⊘ | ⊘ | ⊘ | ⊘ |
| `MeowfficerTrain.MaxFeedLevel` | Meowfficer | type=input; display=default | input/default: 5 | `M`/⊘ 未适配 | ☑ | ⊘ | ⊘ | ⊘ | ⊘ |
| `MeowfficerTrain.Mode` | Meowfficer | type=select; display=default | options: "once_a_day", "seamlessly"; default: "seamlessly" | `M`/⊘ 未适配 | ☑ | ⊘ | ⊘ | ⊘ | ⊘ |
| `MeowfficerTrain.RetainTalentedGold` | Meowfficer | type=checkbox; display=default | input/default: true | `M`/⊘ 未适配 | ☑ | ⊘ | ⊘ | ⊘ | ⊘ |
| `MeowfficerTrain.RetainTalentedPurple` | Meowfficer | type=checkbox; display=default | input/default: true | `M`/⊘ 未适配 | ☑ | ⊘ | ⊘ | ⊘ | ⊘ |
| `MeritShop.Filter` | ShopOnce | type=textarea; display=default | input/default: "Cube" | `M`/⊘ 未适配 | ☑ | ⊘ | ⊘ | ⊘ | ⊘ |
| `MeritShop.Refresh` | ShopOnce | type=checkbox; display=default | input/default: false | `M`/⊘ 未适配 | ☑ | ⊘ | ⊘ | ⊘ | ⊘ |
| `OldRetire.N` | General | type=checkbox; display=default | input/default: true | `M`/⊘ 未适配 | ☑ | ⊘ | ⊘ | ⊘ | ⊘ |
| `OldRetire.R` | General | type=checkbox; display=default | input/default: true | `M`/⊘ 未适配 | ☑ | ⊘ | ⊘ | ⊘ | ⊘ |
| `OldRetire.RetireAmount` | General | type=select; display=default | options: "retire_10", "retire_all"; default: "retire_all" | `M`/⊘ 未适配 | ☑ | ⊘ | ⊘ | ⊘ | ⊘ |
| `OldRetire.SR` | General | type=checkbox; display=default | input/default: false | `M`/⊘ 未适配 | ☑ | ⊘ | ⊘ | ⊘ | ⊘ |
| `OldRetire.SSR` | General | type=checkbox; display=default | input/default: false | `M`/⊘ 未适配 | ☑ | ⊘ | ⊘ | ⊘ | ⊘ |
| `OneClickRetire.KeepLimitBreak` | General | type=select; display=default | options: "do_not_keep", "keep_limit_break"; default: "keep_limit_break" | `P`/◐ 两设置 typed；keep_limit_break 已实机 | ☑ | ☑ | ☑ | ☑ | ◐ |
| `OpsiAbyssal.ForceRun` | OpsiAbyssal | type=checkbox; display=default | input/default: false | `B`/◐ 实机当前值 | ☑ | ◐ | ☐ | ☐ | ◐ |
| `OpsiAshAssist.Tier` | OpsiAshAssist | type=input; display=default | input/default: 15 | `B`/◐ 实机当前值 | ☑ | ◐ | ◐ | ☐ | ◐ |
| `OpsiAshBeacon.AttackMode` | OpsiAshBeacon | type=select; display=default | options: "current_dossier", "current"; default: "current" | `B`/◐ 实机当前值 | ☑ | ◐ | ☐ | ☐ | ◐ |
| `OpsiAshBeacon.DossierAutoAttackMode` | OpsiAshBeacon | type=checkbox; display=default | input/default: false | `B`/☐ 未逐值 | ☑ | ☐ | ☐ | ☐ | ☐ |
| `OpsiAshBeacon.EnsureFullyCollected` | OpsiAshBeacon | type=checkbox; display=default | input/default: true | `B`/☐ 未逐值 | ☑ | ☐ | ☐ | ☐ | ☐ |
| `OpsiAshBeacon.OneHitMode` | OpsiAshBeacon | type=checkbox; display=default | input/default: true | `B`/☐ 未逐值 | ☑ | ☐ | ☐ | ☐ | ☐ |
| `OpsiAshBeacon.RequestAssist` | OpsiAshBeacon | type=checkbox; display=default | input/default: true | `B`/☐ 未逐值 | ☑ | ☐ | ☐ | ☐ | ☐ |
| `OpsiDaemon.RepairShip` | OpsiDaemon | type=checkbox; display=default | input/default: true | `P`/◐ 实机当前值 | ☑ | ◐ | ☐ | ☐ | ◐ |
| `OpsiDaemon.SelectEnemy` | OpsiDaemon | type=checkbox; display=default | input/default: true | `P`/◐ 实机当前值 | ☑ | ◐ | ☐ | ☐ | ◐ |
| `OpsiDaily.DoMission` | OpsiDaily | type=checkbox; display=default | input/default: true | `B`/◐ 实机当前值 | ☑ | ◐ | ◐ | ☐ | ◐ |
| `OpsiDaily.UseTuningSample` | OpsiDaily | type=checkbox; display=default | input/default: true | `B`/◐ 实机当前值 | ☑ | ◐ | ☐ | ☐ | ◐ |
| `OpsiExplore.ForceRun` | OpsiExplore | type=checkbox; display=default | input/default: false | `B`/◐ 实机当前值 | ☑ | ◐ | ☐ | ☐ | ◐ |
| `OpsiExplore.LastZone` | OpsiExplore | type=input; display=default | input/default: 0 | `B`/◐ 实机当前值 | ☑ | ◐ | ☐ | ☐ | ◐ |
| `OpsiExplore.SpecialRadar` | OpsiExplore | type=checkbox; display=default | input/default: false | `B`/◐ 实机当前值 | ☑ | ◐ | ☐ | ☐ | ◐ |
| `OpsiFleet.Fleet` | OpsiExplore, OpsiDaily, OpsiObscure, OpsiArchive, OpsiMeowfficerFarming, OpsiHazard1Leveling | type=select; display=default | options: 1, 2, 3, 4; default: 1 | `B`/◐ 实机当前值 | ☑ | ◐ | ☐ | ☐ | ◐ |
| `OpsiFleet.Submarine` | OpsiExplore, OpsiDaily, OpsiObscure, OpsiArchive, OpsiMeowfficerFarming, OpsiHazard1Leveling | type=checkbox; display=default/hide | input/default: false | `B`/◐ 实机当前值 | ☑ | ◐ | ☐ | ☐ | ◐ |
| `OpsiFleetFilter.Filter` | OpsiAbyssal, OpsiStronghold, OpsiMonthBoss | type=textarea; display=default | input/default: "Fleet-4 > CallSubmarine > Fleet-2 > Fleet-3 > Fleet-1" | `B`/☐ 未逐值 | ☑ | ☐ | ☐ | ☐ | ☐ |
| `OpsiGeneral.AkashiShopFilter` | OpsiGeneral | type=textarea; display=default | input/default: "ActionPoint > PurpleCoins" | `P`/◐ 实机当前值 | ☑ | ◐ | ☐ | ☐ | ◐ |
| `OpsiGeneral.BuyActionPointLimit` | OpsiGeneral | type=select; display=default | options: 0, 1, 2, 3, 4, 5; default: 0 | `P`/◐ 实机当前值 | ☑ | ◐ | ☐ | ☐ | ◐ |
| `OpsiGeneral.DoRandomMapEvent` | OpsiGeneral | type=checkbox; display=default | input/default: true | `P`/◐ 实机当前值 | ☑ | ◐ | ☐ | ☐ | ◐ |
| `OpsiGeneral.OilLimit` | OpsiGeneral | type=input; display=default | input/default: 1000 | `P`/◐ 实机当前值 | ☑ | ◐ | ☐ | ☐ | ◐ |
| `OpsiGeneral.RepairThreshold` | OpsiGeneral | type=input; display=default | input/default: 0.4 | `P`/◐ 实机当前值 | ☑ | ◐ | ☐ | ☐ | ◐ |
| `OpsiGeneral.UseLogger` | OpsiGeneral | type=checkbox; display=default | input/default: true | `P`/◐ 实机当前值 | ☑ | ◐ | ☐ | ☐ | ◐ |
| `OpsiHazard1Leveling.TargetZone` | OpsiHazard1Leveling | type=select; display=default | options: 0, 22, 44; default: 0 | `B`/◐ 实机当前值 | ☑ | ◐ | ☐ | ☐ | ◐ |
| `OpsiMeowfficerFarming.ActionPointPreserve` | OpsiMeowfficerFarming | type=input; display=default | input/default: 1000 | `B`/◐ 实机当前值 | ☑ | ◐ | ☐ | ☐ | ◐ |
| `OpsiMeowfficerFarming.HazardLevel` | OpsiMeowfficerFarming | type=select; display=default | options: 10, 3, 4, 5, 6; default: 5 | `B`/◐ 实机当前值 | ☑ | ◐ | ☐ | ☐ | ◐ |
| `OpsiMeowfficerFarming.TargetZone` | OpsiMeowfficerFarming | type=input; display=default | input/default: 0 | `B`/◐ 实机当前值 | ☑ | ◐ | ☐ | ☐ | ◐ |
| `OpsiMonthBoss.CheckAdaptability` | OpsiMonthBoss | type=checkbox; display=default | input/default: true | `B`/◐ 实机当前值 | ☑ | ◐ | ☐ | ☐ | ◐ |
| `OpsiMonthBoss.ForceRun` | OpsiMonthBoss | type=checkbox; display=default | input/default: false | `B`/◐ 实机当前值 | ☑ | ◐ | ☐ | ☐ | ◐ |
| `OpsiMonthBoss.Mode` | OpsiMonthBoss | type=select; display=default | options: "normal_hard", "normal"; default: "normal" | `B`/◐ 实机当前值 | ☑ | ◐ | ☐ | ☐ | ◐ |
| `OpsiObscure.ForceRun` | OpsiObscure | type=checkbox; display=default | input/default: false | `B`/◐ 实机当前值 | ☑ | ◐ | ☐ | ☐ | ◐ |
| `OpsiShop.CustomFilter` | OpsiShop | type=textarea; display=default | input/default: <long default in args.json> | `B`/◐ 实机当前值 | ☑ | ◐ | ☐ | ☐ | ◐ |
| `OpsiShop.PresetFilter` | OpsiShop | type=select; display=default | options: "all", "custom", "max_benefit_meta", "max_benefit", "no_meta"; default: "max_benefit_meta" | `B`/◐ 实机当前值 | ☑ | ◐ | ☐ | ☐ | ◐ |
| `OpsiStronghold.ForceRun` | OpsiStronghold | type=checkbox; display=default | input/default: false | `M`/⊘ 未适配 | ☑ | ⊘ | ⊘ | ⊘ | ⊘ |
| `OpsiVoucher.Filter` | OpsiVoucher | type=textarea; display=default | input/default: "LoggerAbyssal > LoggerObscure > Book > Coin > Fragment" | `B`/◐ 实机当前值 | ☑ | ◐ | ☐ | ☐ | ◐ |
| `Optimization.CombatScreenshotInterval` | Alas | type=input; display=default | input/default: 1.0 | `P`/◐ 实机当前值 | ☑ | ◐ | ☐ | ☐ | ◐ |
| `Optimization.ScreenshotInterval` | Alas | type=input; display=default | input/default: 0.3 | `P`/◐ 实机当前值 | ☑ | ◐ | ☐ | ☐ | ◐ |
| `Optimization.TaskHoardingDuration` | Alas | type=input; display=default | input/default: 0 | `P`/◐ 实机当前值 | ☑ | ◐ | ☐ | ☑ | ◐ |
| `Optimization.WhenTaskQueueEmpty` | Alas | type=select; display=default | options: "close_game", "goto_main", "stay_there"; default: "goto_main" | `P`/◐ 实机当前值 | ☑ | ◐ | ☐ | ☐ | ◐ |
| `PrivateQuarters.BuyCake` | PrivateQuarters | type=checkbox; display=default | input/default: false | `M`/⊘ 未适配 | ☑ | ⊘ | ⊘ | ⊘ | ⊘ |
| `PrivateQuarters.BuyRoses` | PrivateQuarters | type=checkbox; display=default | input/default: true | `M`/⊘ 未适配 | ☑ | ⊘ | ⊘ | ⊘ | ⊘ |
| `PrivateQuarters.TargetInteract` | PrivateQuarters | type=checkbox; display=default | input/default: true | `M`/⊘ 未适配 | ☑ | ⊘ | ⊘ | ⊘ | ⊘ |
| `PrivateQuarters.TargetShip` | PrivateQuarters | type=select; display=default | options: "aegir", "anchorage", "nakhimov", "new_jersey", "noshiro", "sirius", "taihou"; default: "anchorage" | `M`/⊘ 未适配 | ☑ | ⊘ | ⊘ | ⊘ | ⊘ |
| `Raid.Mode` | Raid | type=select; display=default | options: "easy", "ex", "hard", "normal"; default: "hard" | `M`/⊘ 未适配 | ☑ | ⊘ | ⊘ | ⊘ | ⊘ |
| `Raid.UseTicket` | Raid | type=checkbox; display=default | input/default: false | `M`/⊘ 未适配 | ☑ | ⊘ | ⊘ | ⊘ | ⊘ |
| `RaidDaily.StageFilter` | RaidDaily | type=textarea; display=default | input/default: "hard > normal > easy" | `M`/⊘ 未适配 | ☑ | ⊘ | ⊘ | ⊘ | ⊘ |
| `Research.AllowDelay` | Research | type=checkbox; display=default | input/default: true | `L`/◐ 实机当前值 | ☑ | ◐ | ☐ | ☑ | ◐ |
| `Research.CustomFilter` | Research | type=textarea; display=default | input/default: <long default in args.json> | `L`/☐ 未逐值 | ☑ | ☐ | ☐ | ☑ | ☐ |
| `Research.PresetFilter` | Research | type=select; display=default | options: "custom", "series_2_457_only", "series_2_blueprint_457", "series_2_blueprint_only", "series_2_than_3_457_234", "series_3_234_only", "series_3_blueprint_234", "series_3_blueprint_only", "series_4_blueprint_only", "series_4_blueprint_tenrai", "series_4_tenrai_only", "series_5_152_only", "series_5_blueprint_152", "series_5_blueprint_only", "series_6_203_only", "series_6_blueprint_203", "series_6_blueprint_only", "series_7_blueprint_la9", "series_7_blueprint_only", "series_7_la9_only", "series_8_305_only", "series_8_blueprint_305", "series_8_blueprint_only", "series_9_blueprint_only", "series_9_blueprint_ta152", "series_9_ta152_only"; default: "series_9_blueprint_ta152" | `L`/◐ 实机当前值 | ☑ | ◐ | ◐ | ☑ | ◐ |
| `Research.UseCoin` | Research | type=select; display=default | options: "always_use", "do_not_use", "only_05_hour", "only_no_project"; default: "always_use" | `L`/◐ 实机当前值 | ☑ | ◐ | ◐ | ☑ | ◐ |
| `Research.UseCube` | Research | type=select; display=default | options: "always_use", "do_not_use", "only_05_hour", "only_no_project"; default: "only_05_hour" | `L`/◐ 实机当前值 | ☑ | ◐ | ◐ | ☑ | ◐ |
| `Research.UsePart` | Research | type=select; display=default | options: "always_use", "do_not_use", "only_05_hour", "only_no_project"; default: "always_use" | `L`/◐ 实机当前值 | ☑ | ◐ | ◐ | ☑ | ◐ |
| `Retirement.RetireMode` | General | type=select; display=default | options: "enhance", "old_retire", "one_click_retire"; default: "one_click_retire" | `P`/◐ 一键与强化已接入；旧退役未适配 | ☑ | ◐ | ◐ | ◐ | ◐ |
| `Reward.CollectCoin` | Reward | type=checkbox; display=default | input/default: true | `P`/◐ 实机当前值 | ☑ | ◐ | ◐ | ☑ | ◐ |
| `Reward.CollectExp` | Reward | type=checkbox; display=default | input/default: true | `P`/◐ 实机当前值 | ☑ | ◐ | ◐ | ☑ | ◐ |
| `Reward.CollectMission` | Reward | type=checkbox; display=default | input/default: true | `P`/◐ 实机当前值 | ☑ | ◐ | ☐ | ☑ | ◐ |
| `Reward.CollectOil` | Reward | type=checkbox; display=default | input/default: true | `P`/◐ 实机当前值 | ☑ | ◐ | ◐ | ☑ | ◐ |
| `Reward.CollectWeeklyMission` | Reward | type=checkbox; display=default | input/default: true | `P`/◐ 实机当前值 | ☑ | ◐ | ☐ | ☑ | ◐ |
| `Scheduler.Command` | Restart, Main, Main2, Main3, GemsFarming, Coalition, Event, Event2, Raid, Hospital, WarArchives, CoalitionSp, EventA, EventB, EventC, EventD, EventSp, RaidDaily, Commission, Tactical, Research, Dorm, Meowfficer, Guild, Reward, Awaken, Daily, Hard, Exercise, ShopFrequent, ShopOnce, Shipyard, Gacha, Freebies, Minigame, PrivateQuarters, OpsiAshBeacon, OpsiAshAssist, OpsiExplore, OpsiShop, OpsiVoucher, OpsiDaily, OpsiObscure, OpsiAbyssal, OpsiArchive, OpsiStronghold, OpsiMonthBoss, OpsiMeowfficerFarming, OpsiHazard1Leveling, OpsiCrossMonth | type=input; display=hide | input/default: "Awaken", "Coalition", "CoalitionSp", "Commission", "Daily", "Dorm", "Event", "Event2", "EventA", "EventB", "EventC", "EventD", "EventSp", "Exercise", "Freebies", "Gacha", "GemsFarming", "Guild", "Hard", "Hospital", "Main", "Main2", "Main3", "Meowfficer", "Minigame", "OpsiAbyssal", "OpsiArchive", "OpsiAshAssist", "OpsiAshBeacon", "OpsiCrossMonth", "OpsiDaily", "OpsiExplore", "OpsiHazard1Leveling", "OpsiMeowfficerFarming", "OpsiMonthBoss", "OpsiObscure", "OpsiShop", "OpsiStronghold", "OpsiVoucher", "PrivateQuarters", "Raid", "RaidDaily", "Research", "Restart", "Reward", "Shipyard", "ShopFrequent", "ShopOnce", "Tactical", "WarArchives" | `R`/◐ 调度路径 | ☑ | — | — | ☑ | ◐ |
| `Scheduler.Enable` | Restart, Main, Main2, Main3, GemsFarming, Coalition, Event, Event2, Raid, Hospital, WarArchives, CoalitionSp, EventA, EventB, EventC, EventD, EventSp, RaidDaily, Commission, Tactical, Research, Dorm, Meowfficer, Guild, Reward, Awaken, Daily, Hard, Exercise, ShopFrequent, ShopOnce, Shipyard, Gacha, Freebies, Minigame, PrivateQuarters, OpsiAshBeacon, OpsiAshAssist, OpsiExplore, OpsiShop, OpsiVoucher, OpsiDaily, OpsiObscure, OpsiAbyssal, OpsiArchive, OpsiStronghold, OpsiMonthBoss, OpsiMeowfficerFarming, OpsiHazard1Leveling, OpsiCrossMonth | type=checkbox/lock/state; display=default | options: false, true; default: false, true | `R`/◐ 调度路径 | ☑ | — | — | ☑ | ◐ |
| `Scheduler.FailureInterval` | Restart, Main, Main2, Main3, GemsFarming, Coalition, Event, Event2, Raid, Hospital, WarArchives, CoalitionSp, EventA, EventB, EventC, EventD, EventSp, RaidDaily, Commission, Tactical, Research, Dorm, Meowfficer, Guild, Reward, Awaken, Daily, Hard, Exercise, ShopFrequent, ShopOnce, Shipyard, Gacha, Freebies, Minigame, PrivateQuarters, OpsiAshBeacon, OpsiAshAssist, OpsiExplore, OpsiShop, OpsiVoucher, OpsiDaily, OpsiObscure, OpsiAbyssal, OpsiArchive, OpsiStronghold, OpsiMonthBoss, OpsiMeowfficerFarming, OpsiHazard1Leveling, OpsiCrossMonth | type=input; display=hide | input/default: "120-240", "30-60", 0, 120, 278, 30, 60 | `R`/◐ 调度路径 | ☑ | — | — | ☑ | ◐ |
| `Scheduler.NextRun` | Restart, Main, Main2, Main3, GemsFarming, Coalition, Event, Event2, Raid, Hospital, WarArchives, CoalitionSp, EventA, EventB, EventC, EventD, EventSp, RaidDaily, Commission, Tactical, Research, Dorm, Meowfficer, Guild, Reward, Awaken, Daily, Hard, Exercise, ShopFrequent, ShopOnce, Shipyard, Gacha, Freebies, Minigame, PrivateQuarters, OpsiAshBeacon, OpsiAshAssist, OpsiExplore, OpsiShop, OpsiVoucher, OpsiDaily, OpsiObscure, OpsiAbyssal, OpsiArchive, OpsiStronghold, OpsiMonthBoss, OpsiMeowfficerFarming, OpsiHazard1Leveling, OpsiCrossMonth | type=datetime; display=default; validate=datetime | input/default: "2020-01-01 00:00:00" | `R`/◐ 调度路径 | ☑ | — | — | ☑ | ◐ |
| `Scheduler.ServerUpdate` | Restart, Main, Main2, Main3, GemsFarming, Coalition, Event, Event2, Raid, Hospital, WarArchives, CoalitionSp, EventA, EventB, EventC, EventD, EventSp, RaidDaily, Commission, Tactical, Research, Dorm, Meowfficer, Guild, Reward, Awaken, Daily, Hard, Exercise, ShopFrequent, ShopOnce, Shipyard, Gacha, Freebies, Minigame, PrivateQuarters, OpsiAshBeacon, OpsiAshAssist, OpsiExplore, OpsiShop, OpsiVoucher, OpsiDaily, OpsiObscure, OpsiAbyssal, OpsiArchive, OpsiStronghold, OpsiMonthBoss, OpsiMeowfficerFarming, OpsiHazard1Leveling, OpsiCrossMonth | type=input; display=hide | input/default: "00:00, 06:00, 12:00, 18:00, 21:00", "00:00, 12:00, 18:00", "00:00, 12:00", "00:00", "04:00" | `R`/◐ 调度路径 | ☑ | — | — | ☑ | ◐ |
| `Scheduler.SuccessInterval` | Restart, Main, Main2, Main3, GemsFarming, Coalition, Event, Event2, Raid, Hospital, WarArchives, CoalitionSp, EventA, EventB, EventC, EventD, EventSp, RaidDaily, Commission, Tactical, Research, Dorm, Meowfficer, Guild, Reward, Awaken, Daily, Hard, Exercise, ShopFrequent, ShopOnce, Shipyard, Gacha, Freebies, Minigame, PrivateQuarters, OpsiAshBeacon, OpsiAshAssist, OpsiExplore, OpsiShop, OpsiVoucher, OpsiDaily, OpsiObscure, OpsiAbyssal, OpsiArchive, OpsiStronghold, OpsiMonthBoss, OpsiMeowfficerFarming, OpsiHazard1Leveling, OpsiCrossMonth | type=input; display=hide | input/default: "120-240", "30-60", 0, 278, 30, 60 | `R`/◐ 调度路径 | ☑ | — | — | ☑ | ◐ |
| `Shipyard.BuyAmount` | Shipyard | type=input; display=default | input/default: 2 | `B`/☐ 未逐值 | ☑ | ☐ | ☐ | ☐ | ☐ |
| `Shipyard.LastRun` | Shipyard | type=datetime; display=default; validate=datetime | input/default: "2020-01-01 00:00:00" | `B`/☐ 未逐值 | ☑ | ☐ | ☐ | ☐ | ☐ |
| `Shipyard.ResearchSeries` | Shipyard | type=select; display=default | options: 1, 2, 3, 4, 5, 6; default: 1 | `B`/◐ 实机当前值 | ☑ | ◐ | ◐ | ◐ | ◐ |
| `Shipyard.ShipIndex` | Shipyard | type=select; display=default | options: 0, 1, 2, 3, 4, 5, 6; default: 0 | `B`/◐ 实机当前值 | ☑ | ◐ | ◐ | ◐ | ◐ |
| `ShipyardDr.BuyAmount` | Shipyard | type=input; display=default | input/default: 2 | `B`/☐ 未逐值 | ☑ | ☐ | ☐ | ☐ | ☐ |
| `ShipyardDr.LastRun` | Shipyard | type=datetime; display=default; validate=datetime | input/default: "2020-01-01 00:00:00" | `B`/☐ 未逐值 | ☑ | ☐ | ☐ | ☐ | ☐ |
| `ShipyardDr.ResearchSeries` | Shipyard | type=select; display=default | options: 2, 3, 4, 5; default: 2 | `B`/◐ 实机当前值 | ☑ | ◐ | ◐ | ◐ | ◐ |
| `ShipyardDr.ShipIndex` | Shipyard | type=select; display=default | options: 0, 1, 2, 3, 4, 5, 6; default: 0 | `B`/◐ 实机当前值 | ☑ | ◐ | ◐ | ◐ | ◐ |
| `StopCondition.GetNewShip` | Main, Main2, Main3, GemsFarming, Coalition, Event, Event2, Raid, Hospital, WarArchives, CoalitionSp, EventA, EventB, EventC, EventD, EventSp, RaidDaily | type=checkbox; display=default/hide | input/default: false | `P`/🧱 首次获得跳过 | ☑ | ◐ | ☐ | ◐ | ◐ |
| `StopCondition.MapAchievement` | Main, Main2, Main3, GemsFarming, Coalition, Event, Event2, Raid, Hospital, WarArchives, CoalitionSp, EventA, EventB, EventC, EventD, EventSp, RaidDaily | type=select; display=default/hide | options: "100_percent_clear", "map_3_stars", "non_stop", "threat_safe_without_3_stars", "threat_safe"; default: "non_stop" | `P`/◐ typed 主线夹具 | ☑ | ◐ | ☐ | ☑ | ◐ |
| `StopCondition.OilLimit` | Main, Main2, Main3, GemsFarming, Coalition, Event, Event2, Raid, Hospital, WarArchives, CoalitionSp, EventA, EventB, EventC, EventD, EventSp, RaidDaily | type=input; display=default | input/default: 1000 | `P`/◐ 实机当前值 | ☑ | ◐ | ☐ | ☑ | ◐ |
| `StopCondition.ReachLevel` | Main, Main2, Main3, GemsFarming, Coalition, Event, Event2, Raid, Hospital, WarArchives, CoalitionSp, EventA, EventB, EventC, EventD, EventSp, RaidDaily | type=input; display=default/hide | input/default: 0 | `P`/◐ typed 六舰等级 | ☑ | ◐ | ☐ | ☑ | ◐ |
| `StopCondition.RunCount` | Main, Main2, Main3, GemsFarming, Coalition, Event, Event2, Raid, Hospital, WarArchives, CoalitionSp, EventA, EventB, EventC, EventD, EventSp, RaidDaily | type=input; display=default/hide | input/default: 0 | `P`/◐ 实机当前值 | ☑ | ◐ | ☐ | ☑ | ◐ |
| `StopCondition.StageIncrease` | Main, Main2, Main3, GemsFarming, Coalition, Event, Event2, Raid, Hospital, WarArchives, CoalitionSp, EventA, EventB, EventC, EventD, EventSp, RaidDaily | type=checkbox; display=default/hide | input/default: false | `P`/◐ 实机当前值 | ☑ | ◐ | ☐ | ☑ | ◐ |
| `Submarine.AutoSearchMode` | Main, Main2, Main3, GemsFarming, Event, Event2, WarArchives, EventA, EventB, EventC, EventD, EventSp | type=select; display=default/hide | options: "sub_auto_call", "sub_standby"; default: "sub_standby" | `P`/☐ 未逐值 | ☑ | ☐ | ☐ | ☑ | ☐ |
| `Submarine.DistanceToBoss` | Main, Main2, Main3, GemsFarming, Event, Event2, WarArchives, EventA, EventB, EventC, EventD, EventSp | type=select; display=default/hide | options: "1_grid_to_boss", "2_grid_to_boss", "to_boss_position", "use_open_ocean_support"; default: "2_grid_to_boss", "use_open_ocean_support" | `P`/☐ 未逐值 | ☑ | ☐ | ☐ | ☑ | ☐ |
| `Submarine.Fleet` | Main, Main2, Main3, GemsFarming, Event, Event2, WarArchives, EventA, EventB, EventC, EventD, EventSp | type=select; display=default | options: 0, 1, 2; default: 0 | `P`/◐ 实机当前值 | ☑ | ◐ | ☐ | ☑ | ◐ |
| `Submarine.Mode` | Main, Main2, Main3, GemsFarming, Event, Event2, WarArchives, EventA, EventB, EventC, EventD, EventSp | type=select; display=default/display | options: "boss_only", "do_not_use", "every_combat", "hunt_and_boss", "hunt_only"; default: "do_not_use" | `P`/◐ 实机当前值 | ☑ | ◐ | ☐ | ☑ | ◐ |
| `SupplyPack.Collect` | Freebies | type=checkbox; display=default | input/default: true | `B`/◐ 实机当前值 | ☑ | ◐ | ◐ | ☑ | ◐ |
| `SupplyPack.DayOfWeek` | Freebies | type=select; display=default | options: 0, 1, 2, 3, 4, 5, 6; default: 0 | `B`/◐ 实机当前值 | ☑ | ◐ | ☐ | ☑ | ◐ |
| `Tactical.RapidTrainingSlot` | Tactical | type=select; display=default | options: "do_not_use", "slot_1", "slot_2", "slot_3", "slot_4"; default: "do_not_use" | `L`/◐ 实机当前值 | ☑ | ◐ | ☐ | ☑ | ◐ |
| `Tactical.TacticalFilter` | Tactical | type=textarea; display=default | input/default: <long default in args.json> | `L`/◐ 实机当前值 | ☑ | ◐ | ◐ | ☑ | ◐ |
| `TaskBalancer.CoinLimit` | EventGeneral | type=input; display=default | input/default: 10000 | `P`/☐ 未逐值 | ☑ | ☐ | ☐ | ☑ | ☐ |
| `TaskBalancer.Enable` | EventGeneral | type=checkbox; display=default | input/default: false | `P`/☐ 未逐值 | ☑ | ☐ | ☐ | ☑ | ☐ |
| `TaskBalancer.TaskCall` | EventGeneral | type=select; display=default | options: "Main", "Main2", "Main3"; default: "Main" | `P`/☐ 未逐值 | ☑ | ☐ | ☐ | ☑ | ☐ |
