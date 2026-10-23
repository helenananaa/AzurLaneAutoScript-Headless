# 本地 KVM 启动失败与 ADB 重连

本轮补齐了日常入口的连接恢复和失败状态，沿用同一镜像、AVD 和游戏资源。
没有账号输入，没有新建 ALAS 任务流程，也没有新增版本准入条件。

## 使用

```powershell
.\scripts\windows\manage-kvm-wsl-local-dev.ps1 -Action Status
.\scripts\windows\manage-kvm-wsl-local-dev.ps1 -Action Reconnect
```

`Reconnect` 只重新连接配置中的 ADB transport，检查当前服务所有权及 Emulator
PID，然后重新读取状态。它不会启动或重启游戏，也不会点击游戏界面。
已有实例断连时，重复 `Start` 会走同一重连路径；健康实例保持原状。
需要主动冷重启游戏时仍使用 `RestartGame`。

Status 现在区分：

| 状态 | 含义 |
| --- | --- |
| `stopped` | 当前没有运行实例，未观察到该服务的失败状态 |
| `failed` | 服务失败退出，返回退出状态、日志路径和 journal unit |
| `stopping` | systemd 正在停止服务 |
| `adb-disconnected` | Emulator 仍在，但配置的 ADB transport 不可用 |
| `adb-unavailable` | ADB 查询超时或无法执行，可尝试 Reconnect |
| `starting` | 连接可用，但 Android 尚未就绪 |
| `semantic-ready` | 当前有通过既有新鲜度、PID、完整性检查的语义状态 |
| `login-required` | 原生 SDK 手机号登录页在前台，Unity 旧帧不用于操作 |

原有 backend 就绪循环继续使用，但在等待间隔检查所属服务是否仍存活。
服务已经失败时及时退出，不再盲等完 ADB 的 180 秒等待窗口。启动器和就绪
调用方分别收尾，避免后者的探测在前者结束后又留下一个空闲 ADB server。
其他设备仍使用该 server 时，不关闭它。

## 本轮验证

- 复制构建 profile 并仅修改副本的 source-lock hash，模拟配置错误。
  原镜像校验拒绝该输入，未启动 guest；状态正确为 `failed`。最终受控失败
  约 10.03 秒返回，未残留本实例相关 listener。
- 恢复默认 profile 后，同一 AVD 正常启动。故障 profile 没有写入默认配置。
- 依次验证 TCP disconnect 后显式 Reconnect、TCP disconnect 后重复 Start、
  关闭本实例独立 ADB server 后 Reconnect。最后一项先核对该 server 没有
  其他设备使用。
- 三条路径的 Emulator PID `695`、游戏 PID `1807`、Android boot ID 和
  userdata 标记保持不变；`Accounts: 0`、账号输入为 0。
- 三次 Linux 内部重连步骤约 0.08–0.09 秒，不包含 Windows/WSL 启动开销，
  也不是通用延迟承诺。
- 正常 Stop 仍以退出码 0 完成。最后的受控失败标记在留存证据后清除，
  测试实例保持停止，AVD 和完整资源保留。
- 聚焦验证：Windows 55 passed、2 skipped；WSL 57 passed。

原始证据位于 `/srv/android-build/kvm/evidence/connection-recovery-20260907-r1/`，
仓库保留[验证收据](../integration/runtime/kvm-connection-recovery-20260907/receipt.json)。
这不提升登录后的 ALAS 任务、多实例或其他平台支持等级。
