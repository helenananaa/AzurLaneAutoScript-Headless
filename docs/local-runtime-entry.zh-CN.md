# 本机运行入口

更新于 2026-10-24。主仓库已经整合公共 ALAS 适配、Windows/WSL Redroid、
本地 KVM 与 Mac/HVF 的已有实现。各平台的实机资格仍分别记录；本页操作对象是
已验证的本机 Redroid `gameplay` 实例，不创建新 userdata，也不安装或重建镜像。

## 现有实例

在主仓库目录打开 PowerShell：

```powershell
$bundle = 'E:\Runtime\ALAS\redroid-x86_64-local-20261023'
& .\scripts\windows\manage-redroid-wsl-local-dev.ps1 -Action Status -Profile Project -ProjectInstance gameplay -ProjectAdbPort 5558
```

`5558` 是这个本地实例的配置，不是通用设备号。通过 `adb devices -l` 核对实际设备；
运行器继续验证包、前台/PID、新鲜语义帧和目标。AVD 与 Redroid 不得同时登录同一账号。
需要启动已停止的实例时，将同一 manager 命令的 `-Action Status` 改为 `-Action Start`。
manager 负责容器；游戏冷启动与登录交给公共运行时和原 LoginHandler，仍使用 `-force-gfx-st`。

运行包内的 manifest 指向现有 Python、ADB、ALAS 运行树、observer 及持久配置。
它依赖本机路径，游戏 APK、资源和账号数据不在运行包中。原始制品与资格身份保留，
源码入口已转到主仓库；无需重复复制 OCI 或 userdata。

## 原 ALAS 日常调度

先查看命令计划；此操作不启动 Python、游戏或调度器，也不修改配置：

```powershell
& .\scripts\windows\run-alas-local-scheduler.ps1 -BundleDirectory $bundle -Plan
```

有界执行最多三个原调度命令，并由原 Restart/LoginHandler 恢复游戏：

```powershell
& .\scripts\windows\run-alas-local-scheduler.ps1 -BundleDirectory $bundle -MaxTasks 3 -RestartBeforeLoop
```

按原计时持续运行，并指定一个本轮尚不存在的停止请求文件：

```powershell
$stop = Join-Path $bundle ('stop-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '.request')
& .\scripts\windows\run-alas-local-scheduler.ps1 -BundleDirectory $bundle -Continuous -RestartBeforeLoop -StopFile $stop
```

在另一个 PowerShell 窗口向该路径写入文件，即请求原 ALAS 在任务边界或原生等待循环
退出；当前任务可能需要先完成。此入口不强杀进程，不删除请求文件，也不重写 NextRun。
启动下一轮时使用新的停止路径。Ctrl+C 仍可中断前台进程，但中断不等于任务成功。

```powershell
Set-Content -LiteralPath '<本轮 $stop 的完整路径>' -Value 'stop'
```

`MaxTasks` 计数的是原调度命令，不保证恰好执行三种不同日常任务。默认是有界模式；
脚本只转发参数，任务选择、重试、计时、NextRun 和成功判断仍归原 ALAS。
持久配置 `semantic_daily_continuity_20261023` 继续原 NextRun，不重新复制 seed 覆盖它。
2026-10-23 晚间实机扩展还启用了 Tactical、Dorm、Daily、Exercise、Freebies、Guild、
PrivateQuarters、Meowfficer、Minigame、Gacha、Hard、Awaken，共十五项参与测试；Awaken
完成一次资源事务后已关闭重复调度。其余十四项在配置中仍启用，但本轮已因主机关机
中断并收尾，没有运行中的 runner，后台巡检已删除。启用不等于验证
通过，执行与局部失败见[真实调度记录](scheduler-live-20261023.zh-CN.md)。高油耗委托
关闭，科研不使用魔方或部件。Main 和商店采购仍关闭。
资源额度由运行包的 `scheduler_budgets` 转交已有运行器；持续模式按原任务轮次恢复额度。
普通任务资源按本轮明确预算使用；钻石消费、采购、改凭据和破坏性重置不在本轮范围。
启用任务时也需为相应 typed 输入配置已有预算，单改 Enable 不会自动扩权。
JSON 收据默认留在运行包目录，可用 `-Output` 指定新路径。
持续模式沿用原 ALAS 的任务失败与局部退让策略；有界模式可用 `-ContinueAfterFailure`
显式继续原生队列。该参数不会绕过传输错误、语义输入检查或原生致命退出。

2026-10-23 已有这些任务的有界执行、配置重入、正常停止与容器恢复证据。
委托已有自然下一轮及修复后连续两轮证据；奖励和科研的自然下一轮因主机关机未验证。
自然满仓后的不中断 Main 恢复、长期无人值守及已登录数据的真实版本升级/回退仍未
资格化。详见[连续性记录](redroid-continuity-20261023.zh-CN.md)及上述真实调度记录。

## 其他平台与开发验证

- Windows AVD：[启动器](../scripts/windows/start-alas-avd.ps1)保留 WHPX 时钟处理；
  [双端 Main 记录](campaign-camera-refresh-20261022.zh-CN.md)覆盖当前一次完整手动地图任务。
- 本地 KVM：[开发入口](local-wsl-kvm-dev.zh-CN.md)与[生命周期记录](kvm-local-lifecycle-20260907.zh-CN.md)。
- Mac/HVF：[登录前与恢复验证](mac-apple-silicon-hvf-login-validation-report.md)。

最终离线回归使用 `PYTHONPATH=python` 和 `python -m pytest -q tests`。
需要原 ALAS 的测试使用相邻只读 checkout `AzurLaneAutoScript-upstream-readonly`，
锁定提交见 `integration/alas/upstream-lock.json`。原生方法测试自动创建临时 checkout，
应用当前正式补丁，并在进程结束时清理该临时树。也可以设置 `ALAS_TEST_ROOT` 复用
已验证的 patched ALAS 运行树，本机为 `E:/Runtime/ALAS/redroid-live-20261022`。
不要用裸仓库根目录 `pytest -q` 收集 artifacts 中的保留树。
