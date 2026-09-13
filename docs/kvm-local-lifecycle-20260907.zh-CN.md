# 本地 KVM 日常入口与正常停机修复

后续已增加启动分段计时，并减少控制命令加载开销，见
[启动优化与资源观测](kvm-startup-optimization-20260907.zh-CN.md)。
现也可使用 `-Action Reconnect` 恢复 ADB，见
[连接恢复与启动失败处理](kvm-connection-recovery-20260907.zh-CN.md)。

本轮在原 `kvm-r75-x86_64-local-20260907-r1` 镜像和 `alas-kvm-local-r5`
AVD 上完成，无需重编 Android、重装游戏或重新下载资源。新日常入口完成了
两次启动/停止，均正常退出为 0；再次启动后保留约 28.5 GiB 游戏资源、
userdata 标记和 `Accounts: 0`。未登录账号或执行 ALAS 任务。

## 日常使用

在本工作树的 PowerShell 中执行：

```powershell
.\scripts\windows\manage-kvm-wsl-local-dev.ps1 -Action Start
.\scripts\windows\manage-kvm-wsl-local-dev.ps1 -Action Status
.\scripts\windows\manage-kvm-wsl-local-dev.ps1 -Action Stop
```

`Start` 使用原来的 r5 和本地 release，不创建或覆盖 userdata。重复 Start
返回当前实例状态，不重启游戏。启动会检查挂载，在独立端口上启动 ADB，
启动 Emulator，并通过原 `KvmBackend` 完成 Android 就绪及游戏冷启动。

需要单独冷重启游戏时使用 `-Action RestartGame`。仅等待 Android、不主动
启动游戏时使用 `-Action Start -AndroidOnly`。所有游戏冷启动均保留 Unity
`-force-gfx-st`、规范逻辑显示、首次全屏教程确认和 ANGLE 配置检查。

可通过 `-Config`、`-Domain`、`-Profile` 覆盖配置文件路径。默认配置在
`integration/runtime/local-kvm-20260907/runtime-config.json`；原始镜像构建
profile 使用仓库的 `kvm-image-build-profile.example.json`。
使用实际物理工作树路径；当前 WSL 入口默认 `ALAS-Android-Build` /
`alas-kvm-build`。目标发行版内必须实际挂载指定 KVM VHDX，不能仅在另一个
发行版挂载后向空挂载点写入运行文件。

Windows 使用隐藏的前台 WSL 客户端等待 systemd 服务，维持该实例的运行
生命周期；停止后客户端退出。没有新增计划任务或永久 sleep 进程。
Emulator 与应用进程保持非 root，只有 systemd 管理操作提权。

状态输出中的 `semantic-ready` 表示当前有新鲜、同 generation 的主线程
语义状态，不表示当前页面的全部 ALAS 操作均已支持。`login-required` 表示
原生 `PhoneLoginActivity` 正在前台，此时不查询或使用 Unity 的旧帧。
其他页面、缺失/过期/截断帧会明确报告当前状态，不回退到像素。

日志位于 KVM 域的 `runtime/control/alas-kvm-local-r5/`：
`launcher.log` 记录服务运行，`last-exit.json` 保留最近退出码。Windows 启动器
自身的日志保留在工作树 `artifacts/local-kvm/launcher-*.log`。

## 发现与修复

1. **console 命令目标错误。** 普通 shell/observer 使用发现并绑定的 TCP
   transport，但 `adb emu` 命令需要 `emulator-<console_port>`。
   原 `stop()` 把 `emu kill` 发给 TCP serial，且未检查失败返回码。
   现在先查询 console 的 AVD 名称，确认匹配后同步 guest userdata，再发送
   console kill。错 AVD 或同步失败时不发送 kill。异常进程退出明确报错。
2. **内部 gRPC 未初始化。** 34.2.7 在显式指定 console 端口、没有显式 gRPC
   配置时，退出日志出现未配置内部 client，随后自我强杀或 core-dump。
   分别禁用 snapshot load/save 未修复该问题；加入 `-grpc 0 -grpc-use-jwt`
   后，同一镜像与 AVD 正常退出。当前二进制实际绑定 `127.0.0.1` 临时端口，
   认证由 Emulator 自身管理，不需要用户配置 token。
3. **ADB 留在 Emulator 服务 cgroup。** 主进程结束后，服务还会等待 ADB
   server。新入口在服务外先启动独立端口的 ADB，停机后断开本实例 transport。
   仅在没有其他设备使用该 ADB server 时关闭它。

上游的 [gRPC 初始化与 teardown 代码](https://android.googlesource.com/platform/external/qemu/+/emu-master-dev/android-qemu2-glue/qemu-setup.cpp)
说明了显式端口与初始化的关系；本轮结论主要来自保留二进制的 A/B 实测。
GDB 附加尝试超时，未获得可用栈，因此不声称已定位具体 SIGSEGV 指令。

这一修复验证的是新日常入口的停机路径。原先不带修复参数的失败日志保留，
不改写为成功，也不外推到所有 Emulator 版本或所有强制停止方式。

## 验证

- 带认证的临时 loopback gRPC 下，保留镜像正常 boot / typed observation。
- 两次日常 Start/Stop 成功，服务返回 0；一次 Windows Stop 实测约 9.8 秒，
  包含 WSL/Python 启动和同步开销，不是通用性能承诺。
- 重复 Start 未更换 Emulator / game PID；停止后的再次启动保留资源及标记。
- 最后一次仍到达原生手机号登录边界，`Accounts: 0`，账号输入为 0。
- 最终没有残留 Emulator 进程，也未残留该实例 console、ADB transport 或
  独立 ADB server 的 listener。
- 聚焦测试覆盖 console 身份错误、同步失败、强杀退出、SDK 登录暂停、
  过期/截断/错 PID 的状态、附加元数据兼容、幂等启动及共享 ADB 保留。

原始证据：`/srv/android-build/kvm/evidence/local-lifecycle-20260907-r1/`。
仓库摘要：[验证收据](../integration/runtime/local-kvm-lifecycle-20260907/receipt.json)。
登录后的 ALAS 工作负载、多实例密度及其他平台资格仍未提升。
