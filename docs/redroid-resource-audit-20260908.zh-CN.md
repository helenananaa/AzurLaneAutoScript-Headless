# 本地 Redroid 无账号资源审计与蓝牙待机优化

2026-09-08，本轮仅操作本地 Project。开始时 Project 停止，另有独立模拟器
`emulator-5580` 在线；没有操作该模拟器。未输入账号、提交登录、运行 ALAS 任务、
修改镜像或访问 Android 构建源树。

## 已落实的优化

Project 的 Android 蓝牙原本为 ON，没有 BLE 应用注册。通过标准
`svc bluetooth disable` 关闭；启用对照后再次关闭，最终保留 OFF。
没有停止 HAL 服务、禁用 Android 软件包或增加启动门槛。

蓝牙 ON 时，`bluetooth@1.1-s` 进程在两个不同阶段分别使用约单核
1.50% 和 1.23% CPU；OFF 时该进程的采样增量为零。它是一个小而明确的
后台节省，不能表述成整机 CPU 降低同样百分比。

关闭状态下，游戏按 `-force-gfx-st` 启动，PID 3964 的 typed observer
generation 从 1 推进至 4，age 538 ms，然后到达唯一空手机号输入框、
disabled 下一步、`Accounts: 0` 的 SDK 页面。原生登录页不被视为 observer ready。

随后 Project Stop→Start 验证 `boot_completed=1`、`bluetooth_on=0`、
Bluetooth OFF、`Accounts: 0`。最终恢复 Project 停止状态并断开本次 ADB。
证据：`evidence/redroid-resources-20260908/launch.json`、
`restart-postcheck.json`、`final-status.txt`。

恢复蓝牙：用 Project manager 启动实例，从当前 manager/容器端口发现其准确 ADB
serial 后，执行 `adb -s <serial> shell svc bluetooth enable`，并读回
`dumpsys bluetooth_manager`。该设置只保存在当前 Project userdata；没有更改
Stock、Api31、其他模拟器、宿主蓝牙或新镜像默认值。

## 实测范围

CPU 的 100% 表示一个逻辑核。下表是约 58 秒的实际窗口，并非每项精确 60 秒。
容器数据来自其 cgroup v2，包含本次采样和诊断的成本；进程 CPU 来自 `/proc`。
不是无干扰微基准，不据此推算多实例容量。

| 阶段/证据子目录 | 容器 CPU | 游戏 CPU | 计费内存 MiB | anon MiB | file MiB |
|---|---:|---:|---:|---:|---:|
| Android 空载，蓝牙 ON / android-idle-final | 9.29% | 未启动 | 3312 | 482 | 2688 |
| Android 空载，蓝牙 OFF / android-bluetooth-off | 6.29% | 未启动 | 3289 | 460 | 2688 |
| Unity 启动混合窗口 / unity-startup | 52.90% | 不作全窗归因 | 4941 | 1536 | 3115 |
| SDK 空登录页 OFF / login-bluetooth-off | 40.46% | 27.70% | 4946 | 1543 | 3115 |
| 同页面 ON / login-bluetooth-on | 28.33% | 20.56% | 4964 | 1557 | 3115 |
| 同页面再次 OFF / login-bluetooth-off-repeat | 24.88% | 13.92% | 4918 | 1522 | 3115 |

内存取各窗口末次采样。`file` 包含文件缓存及 shmem，`anon` 也不等同于游戏 PSS；
不能把整个 memory.current 都说成不可回收常驻内存。Android `dumpsys meminfo`
顶部的总 RAM 是 WSL 可见主机值，不是容器独占内存。

第一轮空载 ON 窗口包含一次额外 meminfo 诊断；最后 OFF 窗口包含两次线程计数读取。
游戏本身也随时间明显降载，因此不能将表中容器均值差异直接归因于蓝牙。
可确认的是蓝牙 HAL 自身 ON/OFF 活动变化，尚不能给出可靠的整容器节省比例。

启动窗口同时含 Android 空载、Unity 加载、SDK 转场和边界检查。
其中一个约 10 秒区间游戏 CPU 为 87.61%，后续下降；不能把这个混合窗口当成
稳定 Unity 待机。未尝试阻止正常 SDK 转场来制造长时间 Unity 场景。

## 下一处热点已定位，但未修改

`game-threads.txt` 和 `thread-groups.json` 记录空登录页游戏进程共 246 个线程，
其中 **64 个 TaskDistributor 线程在约 16.43 秒窗口合计使用单核 14.67% CPU**。
这说明登录前持续开销值得从线程池唤醒开始定位；线程名不能证明其属于哪个
库，也不能证明它是 Unity Job System，或必然随 CPU 数量变化。

下一轮应先确认这些线程的所属库、等待/唤醒来源，以及线程数与可见 CPU 数量
是否有关，再选择局部修复或可恢复的 CPU 可见性实验。不能直接设置未知游戏
线程参数，也不能以 SDK 暂停页结果证明战斗时可以降低帧率或线程数。

## 采样器与验证

新增 `scripts/python/sample_redroid_wsl_resources.py`，复用既有 WSL backend 的
容器/镜像/userdata 身份核对，记录原始 `/proc`、cgroup CPU、内存、I/O 计数，
按 PID 和启动时间排除 PID 重用，结束时确认容器未更换或重启。
该工具不启动/停止实例、不请求截图或 observer、不修改设置。

```powershell
$env:PYTHONPATH = 'python'
python scripts/python/sample_redroid_wsl_resources.py `
  --config evidence/redroid-wsl-runtime-20260907-r1/runtime-config.json `
  --output evidence/redroid-resources-new/android-idle `
  --phase android-idle --seconds 60
```

需先启动选中的 Project，输出目录必须是新目录。进程榜仅比较两个采样点都存在、
启动时间一致的进程；启动窗口新进程的完整成本仍计入容器 CPU，但可能不出现在
全窗进程榜中，应查看分段榜。I/O 保留原始计数，没有包装成未经验证的吞吐结论。

前几次工具调试遇到 Windows stdin CRLF、空 io.stat 解析问题，保留的
`android-idle`、`android-idle-r2`、`android-idle-r3` 不属于通过数据；
`android-idle-r4` 是早期逐进程 cat 版本，最终表未采用。
性能样本使用内建 read 版本；最后仅改进只读执行策略、记录时间/脚本哈希，及从
首个采样点开始计时，`final-sampler-smoke` 实测验证最终版本。该短窗口只验证工具，
不作为性能数据。早期性能收据没有脚本哈希，不声称为冻结版本资格化证据。

聚焦测试 `tests/test_redroid_resource_sample.py`：2 passed，覆盖特殊进程名称、
空 I/O、单核 CPU 归一化、PID 重用和非递增时间。`git diff --check` 通过。
没有修改 ALAS patch series 或提升任务支持台账；未进行账号后、长期 soak、
多实例或原生 Linux 资格化。
