# 本地 Redroid 账号任务验证（2026-10-22）

这是首轮记录；Windows 1450 和 AVD 网络问题的后续处置及补验见
[完整任务与 AVD 对照补验](redroid-completion-20261022.zh-CN.md)。本页保留当时的失败范围。

这次验证使用独立 `gameplay` userdata 和原 ALAS；结果仅覆盖本机 Windows/WSL、
一个 CN 账号和本次明确执行的任务。不代表原生 Linux、完整任务矩阵或长期无人值守资格。

## 配置与保留数据

- 分支已合入 `codex/alas-fixed-upstream-capabilities`，合并提交 `a0aa101`。
- 原 ALAS 基线 `81ccf63b4540f00241628c82a58c02c7a2bb11af`，224 个补丁成员；
  独立运行目录 `E:/Runtime/ALAS/redroid-live-20261022`。
- 本次容器 `alas-redroid-wsl-gameplay`，实际 ADB `127.0.0.1:5558`。
- userdata 为 `/home/helenanana/.local/share/alas-redroid/gameplay-data`，
  从停止的 Project 与成功登录的 overlay 只读合并视图复制而来；约 60 GB。
  原 `projectlocal-data`、原 AVD 和旧 ALAS 运行目录保留。
- Android OCI digest
  `sha256:2e6e03e3ef33c08acf91a13b1cd9cc4a6a5d33d2d579511760c85ea7bb6c8e5a`。
- 游戏 APK 9.7.10 / 9710，资源 9.7.411；ANGLE NULL，1280×720。
- 最新保留的 observer APK SHA-256
  `7433f076161bb8c51eafa2fa5a2902ccd3aa9f187379bee3244431afab02b29e`。
  其 `driver_revision` 仍为 `506b76f698b5089aaa29c4e7908b48edb8532a44`，
  所以该 revision 本身不能区分这些实际内容不同的 APK。

账号复用成功；凭据归档仅在本机 Runtime 私有目录，不纳入 Git。任务副本关闭
SaveError 和 OnePush，原持续运行配置与定时任务没有启用。

## 实际发现与修复

1. 命名 Project 实例复用统一 `redroid` / `wsl-docker` backend，manager 传递实例名和
   ADB 端口，并核对实际 userdata、容器、镜像与端口。其他受管容器运行时保留 WSL 保活。
2. 资源更新后空 server-name 标签现在可被原 LoginHandler 的重启识别接受。
   仍要求同进程已观察更新、明确 opening 覆盖与版本信息；正常登录、非空、重复或
   截断标签不会触发此路径。
3. 较慢的 Android 前台检查曾被放在 Button/UI 两次读取之间，导致观察器发布超过
   两代状态而拒绝委托或战术学院。修复把前台检查移到配对读取外；保留前台、身份、
   新鲜度、原 generation 界限和输入前复查。共享弹窗的浅层识别也使用此读取顺序。
4. 原 Redroid observer 缺少委托行 raycast；第一份较新的 APK 又缺少
   `select_panel_adapt` 路径。使用已有较新 APK 后能力恢复，无需 Android 镜像构建，
   也未把未知 raycast 当作可点击。
5. ALAS 进程中断后，原 UI 恢复会先扫描紧急委托、领取奖励等提示，再处理已有总奖励页。
   为这个确切、无遮挡、退出目标唯一且可操作的结果页补齐其他提示的缺席识别；
   陌生弹窗、重复/缺失退出目标和错误 package 仍拒绝。退出与导航仍由原 ALAS 执行。
   退出后的关卡 postcondition 同样改用前台查询位于配对读取之外的顺序。

失败尝试均留档。原生调度器一次运行已完整完成 Commission（四项普通派遣，
`NextRun=2026-10-22 17:51:24`）；早先已领取完成的委托奖励。另一次原生调度完整完成
Tactical，消耗一册蓝 T4 与三册红 T3 教材，四项课程都有结束时间，原 ALAS 保存
`NextRun=2026-10-23 01:03:06`。两项任务均已停止，没有启动持续调度。

出击准备还修复了 Toggle 配对读取中的同类前台查询问题，以及关卡入口重复读取
导致已准备输入帧过期的问题。关卡入口现在复用原 Session.click 的新鲜输入帧读取
油量与目标；过期阈值、目标验证和最终输入边界保持不变。

## 真实出击与恢复边界

原 Main 使用既有配置：普通 12-4、道中一队/Boss 二队、不出潜艇、不用双倍书、单次出击。
正式进入官方自律寻敌，完成六场道中并进入 Boss 战；随后 Windows 创建 ADB 子进程时
报 `WinError 1450`（系统资源不足），原 ALAS 进程中断。没有将其记为 Main 成功或
`RunCount=0`。当时宿主机有其他工作负载；本次没有证明资源耗尽根因已解决。

游戏继续完成战斗，typed observer 确认 `LevelStageTotalRewardPanel(Clone)` 正式总奖励页。
随后原 ALAS UI 退出结果、返回主界面；首次退出后的配对读取验证失败也保留在失败收据中。
修复后单独恢复成功，没有为了取得绿色结果再开一局。

| 资源 | 出击前 | 出击后 | 本次变化 |
| --- | ---: | ---: | ---: |
| 石油 | 5982 | 5665 | -317 |
| 金币 | 67435 | 69499 | +2064 |
| 钻石 | 3505 | 3505 | 0 |

这证明了真实游戏出击与中断后分段恢复；**不证明原 Main 连续跑完**。

战斗中的 179.3 秒容器采样：CPU 平均 186.69%（100% 为一个逻辑核），其中游戏约
175.30%；容器 memory.current 4.43–4.48 GiB，包括约 2.42 GiB 文件缓存，anon
1.86–1.91 GiB。该口径不是 Windows 整体占用，也不是长期容量保证。

## 持久化重启

统一 `WslRedroidBackend` 实际执行 `restart_android → wait_android_offline → wait_adb →
wait_android_ready → wait_game_ready`，约 32.2 秒完成，容器 `StartedAt` 已变化。
游戏 PID 从 9380 变为 1611，冷启动保留 `-force-gfx-st`。之后原 LoginHandler
自动登录，原 UI 回到主界面，账号与 5665/69499/3505 的资源值保持不变。
新进程 generation 583 → 598，两次 Button/UI 同代，确认不是沿用旧 observer 状态。

运行配置另保存在 `E:/Runtime/ALAS/redroid-gameplay-runtime.json`。正常后续启动继续
使用 Project manager 的 `gameplay` 实例与 5558 端口；游戏恢复由统一 backend / 原
LoginHandler 执行。此次没有开启持续调度或定时任务。

## 短基准与 AVD 对照缺口

原 ALAS Benchmark 在 Redroid 主界面执行 15 次、取最快 12 次的均值：
语义观察约 0.327 秒，主界面/设置往返交互约 1.434 秒。单独 15 秒游戏进程空闲
采样 CPU 约 110.65%，PSS 1,525,110 KiB；不包含整个 WSL 或容器开销。

AVD 以 `-read-only`、`-no-snapshot` 启动，确认实际设备为 `emulator-5560`、
AVD 名 `alas_game_api32_x64`。第一次已安装相同 observer APK，但原 LoginHandler
停在 typed 更新页“最新版本获取失败”；设备无法解析域名。使用本机 WLAN DNS
重新只读启动后解析仍失败，因此没有执行可比较的 AVD Benchmark。
两次参考实例均已结束，原 AVD 数据保留；宿主机代理、DNS 配置没有修改。
结束参考试验后已再次启动 Redroid，并由原 LoginHandler 登录至主界面：PID 1610，
generation 458 → 472，账号和资源值与重启前一致。当前只有该独立实例待用，持续
调度保持停止。

这些数值只描述这次 Redroid 短采样。没有有效 AVD 成对结果，也没有隔离宿主机其他
工作负载，不能推导任务整体提速或多实例容量。资源更新后的空 server-name 重启
分支本轮有针对性测试，未取得新的 AVD 更新后端到端成功证据。

## 证据入口

原始本地证据位于 `artifacts/redroid-product-20261022/`，包含独立配置、完整日志、
失败快照、任务收据、APK 回退副本、测试与性能采样。原始证据包含账号信息，保持 Git
忽略。结构化交接摘要只记录本次验证需要的非凭据字段。

补丁组合、干净基线上的补丁树、support matrix 和原配置攻击矩阵检查均已通过。
本次 support ledger 仅纠正 `series.json` 的规范 LF 内容哈希，没有晋升任务或字段状态。
累计开发检查 344 项通过。后续结算恢复检查 115 项通过、8 项旧留档 fixture 缺失跳过；
关卡配对与恢复检查 59 项通过、8 项同类跳过。这些套件互有重叠，不相加作独立覆盖数。
具体任务、恢复和性能结果以 `evidence/redroid-gameplay-20261022/summary.json` 为准。
