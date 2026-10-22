# 共享 Campaign 准备能力（2026-09-06）

固定上游为 `81ccf63b4540f00241628c82a58c02c7a2bb11af`，开发分支为
`codex/alas-fixed-upstream-capabilities`。本批补齐周回开关、双倍书准备和确认，
扩展普通官方自律的双舰队编号与职责组合，修正非默认阵型的错误拒绝。
FleetLock 和自然伏击的实机闭环仍未完成，整个批次不能标为全部完成。

## 已实现的行为

- 新增补丁成员 `0520-campaign-preparation-decisions.patch`。语义准备分支用 typed
  进度和周回控件证明可用性，再执行原 `handle_fast_forward()`；不再按
  `UseAutoSearch` 强制开启周回并把 `Use2xBook` 写死为 false。
- 周回控件按当前 `Loop/Toggle` 的 `on/live2d_on`、`off/live2d_off` 读取。
  原 Switch 继续决定是否切换、何时刷新和何时结束。
- 双倍书按 `Fixed/sp`、`tebiezuozhan` 图标、库存及 `checkbox/mark=gou` 读取。
  原 `_set_2x_book_status()` 的重试和后置判断保留，替换像素读取与按钮输入。
  指令书设置放在舰队及职责准备之后，避免游戏取消先前设置。
- 指令书确认只接受精确道具名、数量 1、正库存、明确的双倍油耗条款和唯一可操作按钮。
  确认依附已经授权的本次出击，不重新授予额度。游戏取消指令书时返回明确错误。
  普通 Msgbox 不再一律进入仅供历史 D3 使用的船坞恢复解析器。
- 两个普通水面编队的职责绑定编队位置，允许不同的实际舰队编号，如 `(3,6)`、`(2,1)`；
  保留实际选舰证明、两队不同、无潜艇、船只占用、油量和输入目标检查。
  普通自律四种职责组合均有针对性覆盖；困难任务的特定限制保持局部有效。
- 原 `handle_strategy()` 通过格式化的 `__getattribute__` 读取两队阵型。
  旧静态扫描漏掉了这个消费者，错误地拒绝 `line_ahead/diamond`。现执行原函数验证
  两队三种阵型，并移除该错误拒绝。手动操舰模式仍未因此获得输入能力。
- 普通关卡难度从已识别的章节界面读取，不再错误地要求存在活动详情页的难度按钮。
  准备状态/UI 连续读取时省去中间重复的 ADB 前台查询，输入前仍复核前台。

## 实机结果

目标为本地 `alas_game_api32_x64` / `emulator-5580`，国服巴巴罗萨，游戏 PID
`13240`。ANGLE NULL 保持启用，通过带 `-force-gfx-st` 的原 ALAS 重启流程进入游戏。

- 周回开关完成 `on → off → on` 的 typed 输入及复查。
- 双倍书设置完成 `off → on → off`；设置阶段库存保持 569。
- 原 Main 12-4 在 `UseAutoSearch=true / Use2xBook=true`、舰队 `(1,2,0)`、
  职责 `mob/boss` 下完成一次任务，`RunCount 1 → 0`、Scheduler 关闭。
  原日志记录官方自律等待 `348.25s` 后返回；战斗/地图点击和镜头预算均为 0。
- 独立 typed 后置复查证明指令书 `569 → 568`，油量 `3096 → 2462`：
  实际消耗 1 本书、634 石油。任务收据中的 `auto_search_completion` 为 null，
  因而不能把该字段当成完整战斗轨迹；任务持久化、日志和独立资源复查分别保留。
- 另一次原 Main 手动准备验证关闭周回，并由原阵型 Switch 从 `double_line`
  经 `diamond` 到达 `line_ahead`。战斗预算为 0，未清图，随后 typed 撤退。
  此探针的任务收据为 `passed=false`，只用于准备/阵型证据，不作为关卡成功证据。
  它额外消耗 10 石油；本轮合计 644 石油、1 本书，没有退役舰船或消费钻石。
- 收尾已退出地图、恢复周回开关为 on、双倍书选择为 off，并返回主页。

主要记录：

- `integration/alas/campaign-preparation-main-2x-live-20260906-r8.json`
- `integration/alas/campaign-preparation-main-2x-resources-20260906.json`
- `integration/alas/campaign-preparation-book-on-observation-20260906.json`
- `integration/alas/campaign-preparation-book-after-main-20260906.json`
- `integration/alas/campaign-preparation-manual-map-observation-20260906.json`
- 迭代和手动探针日志位于 `artifacts/campaign-preparation/`。

## Observer 与验证

仅为上述周回和指令书按钮补充精确的 EventSystem 顶层命中检测，并在它们实际可见的
RectTransform 内取中心进行命中查询；未计算命中或被遮挡仍禁止输入。
复用了本地 x64 ANGLE 缓存，12 个增量构建步骤约 10 秒完成；APK 已安装到目标 AVD。
APK SHA-256 为 `c7fb25a6ed41d0184cc0d3d137773440a46c341f9cb5ea62ac2f96404cc51c27`。
旧 APK 保存在 `artifacts/campaign-preparation/observer-before.apk`，没有重建 Android 镜像。

97 个补丁成员已在固定上游干净应用并编译通过，最终记录在
`integration/alas/campaign-preparation-patch-tree-20260906-r5/result.json`。
登录、截图帧时序和像素边界回放通过，未分类像素访问为 0。
初次全套回归的 29 个失败涉及补丁身份、事件运行器的已审查调用集合及旧成员数，
均已同步并定向复测。最后相关套件为 **177 passed、1 skipped**；另外新增确认框
及准备/舰队回归组为 **85 passed**，两组覆盖有重叠，不能相加。
未把历史实机收据重签为本次证据，未提升整面板支持等级。

## 仍待补全

- **FleetLock**：本次周回关闭的手动地图中，原 ALAS 判断开关缺席，typed 树也没有该控件。
  下一步需要周回开启、手动地图控制的真实样本，确认该客户端的独立锁定状态及输入。
- **AmbushEvade**：原分派和既有 typed 躲避/迎击接口继续保留；12-4 未触发自然伏击，
  不新增这两个分支的实机支持声明。
- 双倍书自动连续出击菜单、其他关卡/舰队组合、两队阵型的全部实机路径仍需按实际需求验证。
