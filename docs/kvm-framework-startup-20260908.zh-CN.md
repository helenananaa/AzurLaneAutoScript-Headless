# KVM framework 启动热点与开机动画优化

本轮沿用本地 r75 release 和 r5 AVD，采集一次基线启动和一次关闭开机动画的
启动。仅修改 `scripts/wsl/run-kvm-avd.sh`，加入 Emulator 支持的
`-no-boot-anim`；镜像、userdata、guest RAM、游戏 ANGLE NULL 路由保持原样。

## 定位结果

基线 logcat（monotonic 时间）显示：

- Zygote 预加载约 1008 ms；PackageManager 启动约 746 ms。
- `MakeDisplayManagerServiceReady` 从 16.263 秒到 23.799 秒，耗时 7536 ms。
- 23.747 秒，RenderEngine 报告生成 122 个 shader，耗时 12641.729 ms。
  随后出现 SurfaceControl `Excessive delay in setPowerMode()` 和显示服务锁竞争。
- 开机动画进程从约 11.45 秒运行至 26.88 秒；框架动画完成事件为 26.826 秒。

因此不将包扫描或 Zygote 作为首要优化目标。显示服务等待与 SwiftShader 下的
SurfaceFlinger/SkiaGL 预编译重合，动画路径也是此次可低成本控制的因素。

核对了本地源码的 manifest HEAD
`e3b1a5113daede938922ed29c36806e0aac2ecb3`、1355 项库存及保留的 sync receipt。
`frameworks/native/services/surfaceflinger/SurfaceFlinger.cpp` 中：

- 914 行附近通过 `service.sf.prime_shader_cache` 控制预编译，默认启用。
- 729 行附近的 `bootFinished()` 等待预编译 future 完成。

本轮没有修改该属性或重建镜像。Goldfish 的 qemu-props SELinux 配置只允许
指定属性类型，不能假设传入任意 Emulator `-prop` 就会成功关闭预编译。

## 单次对照结果

| 观测 | 基线 | 关闭开机动画 |
| --- | ---: | ---: |
| ready 总耗时 | 33.641 秒 | 29.546 秒 |
| ADB 等待 | 15.159 秒 | 13.099 秒 |
| framework 等待 | 15.090 秒 | 12.948 秒 |
| 网络等待 | 3.286 秒 | 3.436 秒 |
| MakeDisplayManagerServiceReady | 7536 ms | 10 ms |
| shader 预编译 | 12642 ms | 12260 ms |
| wm_boot_animation_done，guest monotonic | 26.826 秒 | 24.201 秒 |

关闭动画后，显示初始化不再长时间卡在原处，但预编译仍在后续启动完成路径
等待。约 4.1 秒的 ready 差值包含 ADB 阶段波动；每组仅一次，不能声称稳定
提速比例，更不能把 7.5 秒的局部差值全部视为整体收益。

保留该改动的依据是：此 headless 入口无需开机动画、参数真实生效
（`debug.sf.nobootanimation=1`）、就绪流程完整、功能回归通过。
它不禁用 SurfaceFlinger，也不改变游戏 ANGLE NULL。

## 验证和回退

- Windows 聚焦测试：56 passed、2 skipped。
- WSL 启动脚本测试：2 passed；`bash -n` 通过。
- 新参数下 Android-only 到达 launcher，framework 与网络检查均通过。
- 原 backend 游戏冷启动成功，PID 1766；状态先为 generation 1 / age 985 ms，
  后为 generation 7 / age 1304 ms，均通过现有语义完整性、新鲜度和 PID 检查。
- 此轮后续观察仍在 Unity MainActivity，不声称再次到达原生手机号登录页。
- `Accounts: 0`，无账号输入、游戏界面操作或游戏资源消费。
- 正常 Stop 返回 0，最终 Status 为 stopped，userdata 保留。
- 回退只需从启动脚本移除 `-no-boot-anim`，下次冷启动生效，无需重建 userdata。

原始输出在 `artifacts/local-kvm/framework-20260908/`。基线 logcat 导出时
内核缓冲读取提示权限不足，因此不声称完整 kernel trace；本报告依赖实际保留
的 framework/RenderEngine 事件和 ready 输出。未提升 ALAS 或多实例支持等级。

继续优化时，优先验证 SurfaceFlinger 预编译的启动期配置及按需编译的首次
使用代价，再决定是否值得增量构建候选镜像；不直接删除系统服务或关闭显示栈。
