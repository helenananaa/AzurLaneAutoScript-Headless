# KVM 登录前启动等待优化

本轮复用 `kvm-r75-x86_64-local-20260907-r1` 和 `alas-kvm-local-r5`，
未重编镜像、改动 guest RAM、输入账号或执行游戏任务。

## 改动与原因

Windows 启动器在等待 systemd 服务出现时，原先调用完整 Status，可能进入
尚未就绪的 ADB 查询，甚至游戏观察。现在这一段使用 `status --service-only`，
只读取服务状态；后续原有 ready 流程仍负责 ADB、Android framework、网络及
游戏状态验证。正常 Status 和已有实例的重复 Start 仍执行完整状态读取。
未缩短轮询间隔、超时或删减就绪条件。失败服务仍报告 failed。

ready 的 `timings_seconds` 增加 `android_framework_seconds` 和
`android_network_seconds`，两者是 `android_seconds` 内的分段，不能重复相加。
这些字段仅提供观测，不增加准入要求。

## 实测

同一 WSL 会话、镜像和 AVD，修改前后各一次 Android-only 启动：

| 阶段 | 修改前（秒） | 修改后（秒） |
| --- | ---: | ---: |
| Windows 总入口，包含挂载检查 | 42.263 | 39.443 |
| ready 等待 ADB | 14.124 | 12.084 |
| ready 等待 Android/网络 | 18.263 | 17.206 |
| 其中 framework | 未单独记录 | 12.786 |
| 其中网络/provisioning | 未单独记录 | 4.420 |

这不是充分的性能 A/B 结论：每组仅一次，存在启动波动和缓存影响；修改后
启动期间还执行了约 5 秒的 WSL 聚焦测试。不能将约 2.8 秒差值全归因于修改。
明确消除的是服务轮询中的 guest 探测；实际 Android 启动仍是主要等待。

另一次对 Status 内部耗时的可选探测因使用不同路径别名，被既有服务配置
所有权检查拒绝，没有取得可用样本，不作为性能证据。

## 功能验证与边界

- Windows 聚焦测试：56 passed、2 skipped；WSL 对应测试：58 passed。
  覆盖服务查询跳过 guest、完整 Status 仍检测断连、服务失败保留、
  Android-only 仍等待网络并传播失败，以及原有语义与停机边界。
- 新入口 Android-only 到达 launcher；随后通过原 backend 冷启动游戏，
  约 12.517 秒的 ready 流程取得 `semantic-ready`，游戏 PID 1793，
  generation 1，age 140 ms。随后完整 Status 到达原生手机号登录页，
  正确报告 `login-required`，不消费暂停的 Unity 帧。
- `Accounts: 0`；无账号、游戏界面输入、购买或资源消费。
- 两次正常 Stop 均返回 0；最后 Status 为 stopped，userdata 保留。
- 启动前核实 KVM/Redroid 挂载 UUID；本轮仅操作 KVM runtime。
- 不提升登录后的 ALAS、战斗性能或多实例支持等级。

本轮原始输出保留在工作树 `artifacts/local-kvm/startup-20260908/`，
包括前后启动/停止、Windows 总耗时、游戏冷启动、登录页及最终停止状态。

下一步若继续做平台性能优化，应先定位 framework 启动阶段的具体热点；
当前证据不支持降低 guest 内存、删除系统组件或声称镜像启动已明显加速。
