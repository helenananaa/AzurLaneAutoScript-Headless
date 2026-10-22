# Redroid 完整任务与 AVD 对照补验（2026-10-22）

这是[首轮实跑](redroid-gameplay-20261022.zh-CN.md)的后续；原失败证据保留。
范围仍为本机 Windows/WSL、一个 CN 账号、原 ALAS 任务和已安装的观察器。

最终 `main-9.json` 连续完成普通 12-4：六场普通战斗、Boss、总奖励退出和原任务
结束均由同一个 ALAS 进程完成。`passed=true`、原返回 `true`、`RunCount=0`，
耗时 **379.484 秒**；游戏 PID 始终为 3075。结构化摘要在
[完成证据](../evidence/redroid-completion-20261022/summary.json)。

## Windows 1450 的原因与处置

Windows System 日志在 17:14:15、17:15:41 记录 Event 2004：提交内存不足。
当时 `vmmemWSL` 提交约 55.8 GiB，同时有多个 Python 工作进程占用内存。
复查 WSL 为 60 GB 上限，Linux 仅使用约 3.3 GiB，却保留约 51 GiB 文件缓存。
这批缓存与前面的约 60 GB userdata 复制相符；没有证据表明 ALAS 自身泄漏。
D 盘分页文件已分配 50 GiB，该盘剩余约 5 GiB，扩展空间有限。

Windows 的提交额度与物理空闲内存不同；Event 2004 和 Commit size 才能解释这种
尚有空闲 RAM 却创建进程失败的情况。参见
[Microsoft 提交内存诊断](https://learn.microsoft.com/en-us/troubleshoot/windows-server/performance/troubleshoot-application-service-memory-leaks)。

确认没有 Android 构建/同步进程后，本次仅执行一次：

```powershell
wsl.exe -d Ubuntu-22.04 -- sudo -n sh -c 'sync; echo 1 > /proc/sys/vm/drop_caches'
```

该命令释放可丢弃的文件页缓存，不清理 userdata、不终止进程。Linux 文件缓存降至
约 1.7 GiB，随后 Windows 中 WSL 的提交占用降到约 5.5 GiB，可用提交空间恢复到
约 55 GiB。没有重启 WSL、改动分页文件或降低 Android 构建用的 WSL 内存上限。

缓存释放有后续磁盘重读成本，不能作为每次截图、启动或任务的固定步骤。
大量数据复制/构建之后如再次出现压力，先观察 Windows commit 和 Linux cache；
不要单凭物理空闲内存认定宿主机健康。WSL 的自动缓存回收行为及配置见
[Microsoft WSL 配置](https://learn.microsoft.com/en-us/windows/wsl/wsl-config)。

传输层现在保留结构化 `winerror`；遇到 1450 会明确指出宿主机资源问题，继续停止
输入，不把它伪装成 Android 断线，也不会自动重放点击。

修复后 17:41:23 至 18:30:58 的 575 个宿主机采样点中，可用提交空间最低为
37.30 GiB；Windows System 从 17:38 起没有新增 Event 2004。这个结果证明本轮
运行的资源压力已经解除，不代表其他工作负载永远不会再次耗尽宿主机资源。

## AVD“DNS 失败”的实际原因

本轮保留原 userdata 正常启动 AVD，指定本机 WLAN DNS `192.168.5.1` 后，解析与
Android `VALIDATED` 均正常。游戏更新推进到约 1.8 GiB 后，默认网络消失、`eth0`
变为 DOWN。radio 日志明确给出 `mPolicyDataEnabled=false`、`DATA_DISABLED`；
这不是单纯的 DNS 服务器不可达。

`dumpsys netpolicy` 显示模拟套餐 `EmulatorDataPlan` 的硬上限为 2,000,000,000 字节，
行为为达到上限后关闭数据。Android Settings 同时显示 “Data is paused”。
该套餐来自模拟器 RadioConfig，相关初始实现见
[AOSP EmulatorDataPlan](https://android.googlesource.com/device/generic/goldfish/+/b3f628d%5E%21/)。

保留原始 policy 二进制备份后，通过 Android 原生 Settings 的 accessibility 层级
进入 “Data warning & limit”，关闭 “Set data limit”。不是游戏像素输入，也没有修改
游戏 APK、资源校验或原 ALAS 工作流。实际策略变为 `limitBytes=-1, inferred=false`；
仍保留数据用量警告和 Android 联网验证，未改宿主机 DNS/代理或 captive portal 地址。

更新完成后资源版本为 9.7.411。重新启动 Android 后再次检查，策略仍为
`limitBytes=-1, inferred=false`，CDN 域名可以解析。重启后的第一次登录在原生 SDK
Activity 切换时按前台检查停止；待 typed 登录页和前台稳定后，用新进程运行原
LoginHandler 和 Benchmark 成功。保留这次失败收据，不把它计为通过。

本次 AVD 是原持久 userdata 的正常启动，网络策略修改和资源更新均被保留；
不同于首轮报告中的只读启动。复用已授权的有效 SDK 会话前备份了 AVD 对应目录，
凭据和原生 SDK 诊断只留在 Runtime 私有目录，没有清空游戏数据或重新绑定账号。
测试使用的启动命令如下；DNS 地址仅适用于本机当时的 WLAN 网络：

```powershell
& scripts/windows/start-alas-avd.ps1 -ConsolePort 5560 -Adb F:/platform-tools/adb.exe `
  -DnsServer 192.168.5.1 -LogDirectory artifacts/redroid-completion-20261022/avd-launch
```

每次游戏冷启动仍传入 Unity `-force-gfx-st`。没有用游戏截图、OCR 或旧坐标判断
页面，也没有为 SDK 切换放宽前台身份检查。

## 原 ALAS 基准对照

两端均为同一账号、游戏资源 9.7.411、同一个 observer APK、1280×720 和 ANGLE
NULL，先完成原 LoginHandler 和 UI 往返，再运行原 Benchmark。每项 15 次取最快
12 次平均；顺序运行，未让两端同时登录。修复宿主机压力后重新采样 Redroid。

| 指标 | Redroid / WSL | AVD / WHPX |
| --- | ---: | ---: |
| 语义观察 | 0.313852 秒 | 0.090150 秒 |
| 可逆 UI 往返 | 1.400190 秒 | 0.969530 秒 |
| 主页 15 秒游戏进程 CPU，100%=一个逻辑核 | 101.41% | 89.17% |
| 采样末游戏进程 PSS | 1,535,500 KiB | 1,517,509 KiB |

AVD 在本轮观察和交互基准中较快；Redroid 的容器形式并没有自动带来低延迟或更小的
游戏进程内存。CPU/PSS 仅统计游戏进程，不是容器、WSL 或整个模拟器的总开销。
两端分别为 Android 14 和 Android 12，顺序运行于共享宿主机；短样本不能说明长期
资源曲线，也不是同一 Main 任务的成对吞吐量对照。

## 连续 Main 复测中的开关修复

首次补跑 `main-5.json` 在出击前停止：原 ALAS 先将已开启的 Auto_Search 关闭，
启用 Fast_Forward 后按配置再次开启，旧适配层把第二次合法转换判为 single-use。
出击额度未消耗。修复只保留最近一次切换的前态和收据；再次切换必须读到更新的
generation 和相反的 typed 状态，仍要求已证明的关卡入口、当前准备页、原资源状态
及可操作目标。无状态推进、旧 generation、错误资源状态和提交准备后的输入均拒绝。
原 ALAS 的开关顺序、重试和任务流程保持不变。66 项相关准备页/舰队/额度测试通过。

第二次 `main-6.json` 已提交出击，但尚未战斗时遇到 map-entry 快照不一致。地图
入口与网格读取仍把慢 ADB 前台查询夹在两个端点之间，已改用同一配对读取方法。
相关测试覆盖真实 generation 差、前台切换和无输入副作用。失败运行及其收据均保留。

原 Main 在 `main-7.json` 中成功接管该遗留地图、按原地图逻辑完成一场战斗，随后
因本轮官方自律测试未授予地图拖动额度而按原任务延后。该收据是恢复中的局部证据，
不是完整 Main 成功。随后补齐原 UI 撤退前对不相关弹窗的缺席探测：只有完整、
无其他 blocker 且有唯一可操作撤退控件的地图可提供该结论；真实弹窗、缺失控件
仍拒绝。撤退输入和确认仍由原 UI handler 执行，未加入适配层任务流程。

`main-8.json` 再次从非自律分支进入地图，因地图相机观察改变逻辑状态而停止。
该手动地图分支仍不属于本轮完整资格。随后 `preparation-only.json` 不授予出击额度，
只记录原 ALAS 准备页读数，发现进度正在播放动画：真实 typed 文本为 **13%**，
而清图控件已经挂载。之前认为是清图控件可用性探测造成此分支的推测不成立，
相应试验改动已撤回。

最终追加 `1545-campaign-progress-native-animation.patch`：语义入口恢复调用原
`handle_map_preparation()`，复用 ALAS 已有的进度动画稳定性计时和截图循环；
`get_map_clear_percentage()` 读取已有 typed 进度端口，不强制依赖不相关的星标图片。
只有两行行为改动，不新增计时器、任务状态机，也不把非 100% 进度改成 100%。
测试实际执行已打补丁的原方法，覆盖 13%→58%→100%、稳定 40%、稳定 100%、
没有进度的可选关卡及一次性关卡；6 项全部通过。

最终 Main 使用 225 成员补丁树，合并 SHA-256 为
`70e3bd94fc71ce446b7985a559d67763656ecc213f7e048a7a44da41ff84f906`。
前面的双端 Benchmark 使用相同的 224 成员版本；新增成员只修改地图准备与进度读取，
未修改 Benchmark 的观察/往返测试路径。历史失败记录仍保留各自实际使用的版本。

## 离线验证与边界

- 最终相关回归集合：558 passed，8 skipped；跳过项是本地未保留的历史 fixture，
  不是本次网络或主任务失败。新加原 ALAS 动画测试实际运行，没有跳过。
  该测试读取 `ALAS_TEST_ROOT` 指向的已验证补丁树；本轮设为
  `E:/Runtime/ALAS/redroid-live-20261022`，同时设置 `PYTHONPATH=python`。
- 225 成员 patch-series、从锁定 upstream 应用并编译 patch-tree、support-matrix 和
  configuration attack matrix 均通过。仅更新补丁身份记录，没有提升字段支持等级。
- 准备阶段及恢复合计消耗 62 石油，获得 19 金币；钻石保持 3505。此数独立于下述
  完整 Main 的资源消耗。`preparation-only` 虽然原返回为 true，只代表准备页诊断
  完成，不能冒充战斗完成。
- AVD 的启动 DNS、流量限制和缓存处置是本机运行环境修复；镜像未重新构建。
  原生 Linux、全部 ALAS 任务、长期无人值守以及手动地图完整 Main 仍未资格化。

## 最终运行与资源收据

| 范围 | 石油变化 | 金币变化 | 钻石变化 |
| --- | ---: | ---: | ---: |
| 本轮诊断、单场恢复与撤退 | −62 | +19 | 0 |
| 连续完整 Main | −317 | +2068 | 0 |
| 本轮合计 | −379 | +2087 | 0 |

完整 Main 之前为 5603 石油、69518 金币、3505 钻石；结束后为 5286、71586、3505。
限定一次出击、不使用 2x 书、不出动潜艇；原 Main 将临时配置 RunCount 降到 0，
关闭该临时任务并正常返回。额外的原 UI 检查返回主页，两个新鲜 coherent generation
为 25989→25996，仍为同一游戏 PID 3075，没有通过重启拼接本次完整任务。

最终 `gameplay` 容器运行、游戏在主页；原 `projectlocal` 和 AVD 均停止，持续调度
未启动。两份持久 userdata 根权限均为 Android 管理的 `0771 / 1000:1000`。
观察用的宿主机采样器已停止，没有遗留本次 ALAS Python runner。

原始新证据位于 `artifacts/redroid-completion-20261022/`；部分复用资格化 harness 的
结果位于 `artifacts/redroid-product-20261022/avd-completion-*.json`。
