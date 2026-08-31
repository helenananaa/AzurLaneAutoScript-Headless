# x86 / ARM64 Pastel 生命周期差异只读诊断日志

日期：2026-08-25

本报告保留 Pastel 单项诊断的时间点结论；统一 ARM64 流程和其它故障见
[ARM64 Redroid 端到端运行手册](arm64-redroid-end-to-end-runbook.zh-CN.md)。

## 结论

当前分类为：**证据不足**。

更准确的表述是：**x86 当前没有在已证实与 ARM64 等价的 Pastel 使用路径下
复现问题**。现有证据不足以在“图形路由/进程隔离不同”“当前二进制补丁状态
不同”和“相同机制下暂时没有触发竞态”之间作最终选择。因此：

- 不能认定 x86 在机制上不存在该问题；
- 不能认定 x86 使用了完全不同的 SwiftShader 实现；
- 不能认定 x86 只走过隐私协议同意后的暖启动；
- 不能因为 x86 当前未崩溃而批准全 ABI 发布。

本次诊断严格只读。没有修改代码、镜像、容器或配置，没有清除 logcat，
没有点击游戏，也没有改动主 userdata。

## 补充解读：当前优先解释不是 ABI 免疫

当前最有区分度的证据不是 x86 与 ARM64 使用了相同 SwiftShader revision，
而是发生崩溃时两个运行路径中 Pastel 的实际归属不同：

- ARM64 崩溃时，游戏 PID 的栈明确进入
  `vulkan.pastel.so -> vk::Queue -> Reactor/LLVM -> marl`；
- 当前 x86 游戏 PID 同时映射私有 `libEGL_alasx.so` / `libGLESv2_alasx.so`
  和系统 ANGLE/WebView 库，但采样时没有映射 `vulkan.pastel.so`；
- x86 Unity 使用私有 ANGLE NULL，WebView renderer 位于独立 sandbox PID；
- x86 的 Pastel 实际映射目前只在 SurfaceFlinger、system_server、Settings、
  Launcher 等系统进程中得到确认。

因此，“x86 系统也使用 Pastel”不能直接推出“x86 游戏经历了与 ARM64 相同的
Pastel 生命周期”。当前 x86 更接近以下拓扑：

```text
游戏主进程
|-- Unity -> 私有 ANGLE NULL
`-- WebView browser/provider

WebView sandbox 进程
`-- WebView renderer

系统进程
`-- 系统 ANGLE -> Pastel
```

而 ARM64 已知失败路径至少包含：

```text
游戏进程
`-- Pastel Queue / LLVM / marl 仍在工作
    同时发生图形对象或进程级状态销毁
```

在补齐 Agreement 转场瞬间的 maps、PID、Vulkan device/queue 和线程时序前，
原因应按以下优先级处理：

1. **图形路由或进程隔离不等价。** x86 Unity 不消费 Pastel，且 WebView
   renderer 被隔离，可能天然避免 WebView teardown 与 Unity Pastel Queue
   交叉使用；这是当前最值得先验证的解释。
2. **运行制品不等价。** 当前 x86 Pastel 与保留基线的 SHA-256、Build ID
   不同，source-lock 标签却未同步，不能排除其已经带有增量生命周期修改。
3. **相同机制下未触发竞态。** CPU 数、worker 数和调度时序可能降低 x86
   复现概率，但在证明 x86 转场期间游戏 PID 也实际使用 Pastel之前，这只能
   作为后续解释，不能作为首要结论。

这也改变了修复顺序：当前不应先修改或重新发布 x86 SwiftShader。应先让
ARM64 与 x86 的图形拓扑尽量一致，确认 Unity 从进程启动起使用私有 ANGLE
NULL、WebView multiprocess 生效，并在真实协议同意转场期间连续采集游戏与
renderer PID/maps。若 ARM64 在该拓扑下稳定，修复边界优先是路由与进程隔离；
若仍在等价路径下进入 Pastel 并崩溃，才进入 ARM64 Pastel 源码生命周期修复。

provenance 缺口必须补齐，因为它阻止精确比较；但它本身不是崩溃原因的证据。

## 问题背景

ARM64 Redroid 中，碧蓝航线 9.7.10 在
`AgreementWebActivity -> MainActivity` 以及后续直接启动 `MainActivity`
时出现：

```text
FORTIFY: pthread_mutex_lock called on a destroyed mutex
```

已知 ARM64 崩溃栈曾进入 `vulkan.pastel.so`、LLVM ManagedStatic / PassRegistry、
Reactor JIT、`vk::Queue::taskLoop` 和 marl worker。屏蔽
`llvm::llvm_shutdown_obj` 后，LLVM PassRegistry 崩溃消失，但仍暴露其他
SwiftShader/Unity destroyed-mutex，因而不能把问题缩小为单一 LLVM 析构对象。

## 当前 x86 运行身份

采样服务器：`ubuntu@52.23.203.48`

采样时间：2026-08-25 12:52--12:59 UTC。

| 项目 | 实际值 |
| --- | --- |
| Redroid task | `alas-redroid-r75-x86-fbe`，container PID `716625` |
| Android | Android 14，SDK 34 |
| Build ID | `AP2A.240805.005.S4` |
| Incremental | `alas-android-14-r75` |
| Fingerprint | `redroid/redroid_x86_64_only/redroid_x86_64_only:VanillaIceCream/AP2A.240805.005.S4/alas-android-14-r75:userdebug/test-keys` |
| ABI | `x86_64` |
| OCI manifest | `sha256:bf55facb1e6458272b827615e3d4d3d47bffdad3705dfdea33ef1c5eb9ee99d0` |
| OCI tar SHA-256 | `1d7f37022e34c950724feeb4fcd3c3b88bd57028b62d325b22cdb0f82eb16f0` |
| 游戏 | `com.bilibili.azurlane` 9.7.10，primary ABI `x86_64` |
| WebView | `com.android.webview` 151.0.7922.71，multiprocess enabled |
| guest CPUs | 8 logical CPUs |

关键属性：

```text
[ro.boot.redroid_gpu_mode]: [guest]
[ro.hardware.egl]: [angle]
[ro.hardware.vulkan]: [pastel]
[ro.hardware.gralloc]: [redroid]
```

采集命令：

```sh
getprop | grep -E '\[(ro.build.version.release|ro.build.version.sdk|ro.build.id|ro.build.version.incremental|ro.build.fingerprint|ro.product.cpu.abi|ro.hardware.egl|ro.hardware.vulkan|ro.hardware.gralloc|ro.boot.redroid_gpu_mode)\]'
dumpsys webviewupdate
dumpsys package com.android.webview
dumpsys package com.bilibili.azurlane
```

## 进程和链接边界

采样时进程：

```text
37107  com.bilibili.azurlane
37158  com.android.webview:sandboxed_process0:org.chromium.content.app.SandboxedProcessService0:0
```

因此 WebView renderer 是独立 sandbox 进程。游戏、WebView renderer、
SurfaceFlinger 和 system_server 不在同一个进程，也不共享一个进程级链接
命名空间。

游戏主进程的 maps 同时包含：

```text
/data/app/.../libEGL_alasx.so
/data/app/.../libGLESv2_alasx.so
/system/lib64/libEGL_angle.so
/system/lib64/libGLESv2_angle.so
/system/lib64/libwebviewchromium_loader.so
/system/lib64/libwebviewchromium_plat_support.so
/vendor/lib64/hw/gralloc.redroid.so
```

这说明游戏的私有 ANGLE NULL 与 WebView/HWUI 使用的系统图形库可以同时
存在于游戏主进程。当前 Agreement 已结束后的游戏主进程和 WebView renderer
均未映射 `vulkan.pastel.so`。

全进程 maps 搜索仍证明 x86 系统实际使用 Pastel：

```text
/proc/151/maps    surfaceflinger
/proc/29212/maps  system_server
/proc/29542/maps  com.android.settings
/proc/36538/maps  com.android.launcher3
```

上述四个进程均映射：

```text
/vendor/lib64/hw/vulkan.pastel.so
```

所以不能把 x86 未崩溃解释为“x86 根本没有使用 Pastel”。尚未证明的是：
Agreement 显示及销毁期间，游戏主进程或 WebView renderer 是否曾加载 Pastel、
创建/销毁 Vulkan instance 或 device。

## x86 / ARM64 Pastel 二进制对照

保留的 Android 14 r75 双 ABI 构建来自同一 SwiftShader revision：

```text
07f12032dff80d37432e4655fd2dcb867d931ff0
```

| 项目 | x86_64 | ARM64 |
| --- | --- | --- |
| 保留基线 SHA-256 | `0eba3f729ad14a34a244fd227f7bac0b1e93132d7dff143b18ed7a3ecf41312a` | `d97a48030bc5dd6638067550a47035ae13c33835efe95655446fff4c8432491c` |
| 保留基线 Build ID | `1a73f84435da88027876356f6b37615b` | `ad5a31057602e576ec3ed905818d85df` |
| ELF | ELF64 x86-64 | ELF64 AArch64 |
| SONAME | `vulkan.pastel.so` | `vulkan.pastel.so` |
| DT_FLAGS | `SYMBOLIC BIND_NOW` | `SYMBOLIC BIND_NOW` |
| DT_FLAGS_1 | `NOW` | `NOW` |
| Reactor | LLVM backend | LLVM backend |
| LLVM | 静态链接 `third_party/llvm-16.0`，字符串 `LLVM version 16.0.0` | 相同 |

当前服务器 x86 Pastel：

```text
SHA-256  1ab5734ff24602f1432493955b5f9f2a207e154866655a31f6b4f29514482ff1
Build ID e3a153a8d084f014c8bb192c7d65836e
```

它与保留 x86 基线不同，但当前 OCI config 仍标记旧 source-lock：

```text
4f35a668918d92b50a0d77d4dd4970fc491d4f26242ccf3bcc9df06868d1a940
```

这是一个已经证实的 provenance 缺口：当前 x86 是不同于保留基线的增量或
定制二进制，但从已经 strip 的 ELF 不能确认它是否包含移除
`llvmShutdownObj` 的候选补丁。

当前发生崩溃、且已屏蔽 `llvmShutdownObj` 的 ARM64 Pastel 的 SHA-256 和
Build ID 未在可用证据中找到。因此当前 x86 与当前 ARM64 不能完成精确的
binary-to-binary 对照。

## 共同源码生命周期

Android 14 r75 SwiftShader 源码中：

- `src/Reactor/LLVMReactor.cpp` 定义全局
  `llvm::llvm_shutdown_obj llvmShutdownObj`；
- `src/Vulkan/libVulkan.cpp:getOrCreateScheduler()` 使用函数静态
  `Scheduler scheduler`，并带有 `Avoid exit-time destructor` TODO；
- `src/Vulkan/VkQueue.cpp` 中每个 Queue 启动一个 `std::thread`；
- Queue 析构时向 pending queue 投递 KILL、`join()` Queue 线程，然后回收资源；
- `Queue::taskLoop()` bind/unbind 同一个 marl scheduler。

对应官方源码：

- <https://android.googlesource.com/platform/external/swiftshader/+/refs/tags/android-14.0.0_r75/src/Reactor/LLVMReactor.cpp>
- <https://android.googlesource.com/platform/external/swiftshader/+/refs/tags/android-14.0.0_r75/src/Vulkan/libVulkan.cpp>
- <https://android.googlesource.com/platform/external/swiftshader/+/refs/tags/android-14.0.0_r75/src/Vulkan/VkQueue.cpp>

后续收口后的项目补丁
`integration/runtime/aosp-patches/0004-swiftshader-keep-llvm-state-process-lived.patch`
不再只是移除 `llvmShutdownObj`：它同时把 PassRegistry 与 LLVM error-handler mutex
保留为进程生命周期，并在 ARM/AArch64 LLVM 14+ 使用显式 `fptosi_sat`，避免把越界转换
交给不稳定的 target lowering。诊断时临时启用的
`ENABLE_RR_LLVM_IR_VERIFICATION` 没有进入发布补丁。

这仍没有改变 Scheduler static destructor、Queue 构造/析构、marl worker 或 Unity 自身
mutex 生命周期；因此通过当前登录前路径只能关闭已观察到的故障，不能证明所有更广泛的
销毁顺序问题均已修复。补丁身份、分区镜像内二进制身份和 OCI 内容必须分别验证。

## x86 实际 Agreement 生命周期

`dumpsys usagestats` 保存了下列事件：

```text
2026-08-25 11:46:28 MainActivity RESUMED
2026-08-25 11:46:30 MainActivity PAUSED
2026-08-25 11:46:30 AgreementWebActivity RESUMED

2026-08-25 11:47:23 AgreementWebActivity PAUSED
2026-08-25 11:47:23 MainActivity RESUMED
2026-08-25 11:47:23 AgreementWebActivity STOPPED
```

前后 `MainActivity instanceId=92859973` 相同。这证明 x86 确实进入并离开了
真实协议 Activity，不是只覆盖协议已经同意后的暖启动。

但现存证据不能证明：

- userdata 在启动前完全全新；
- 协议点击动作的精确控件身份；
- MainActivity 切换前后 PID 保持不变；
- WebView native teardown 与 Unity 绘制是否重叠；
- Vulkan instance/device 是否创建并销毁；
- Agreement 切换瞬间 Queue 和 marl worker 的数量及状态。

## 调度与时序

当前 x86 宿主与 guest 都暴露 8 个 logical CPUs。SurfaceFlinger 和
system_server 中都观察到 `Thread<00>` 至 `Thread<07>`，与 8 个 marl
worker 相符，但这只是基于线程名和数量的归因，未做符号级确认。

当前游戏主进程有 143 个线程，WebView renderer 有 11 个线程。游戏主进程
包括 `UnityMain`、Chrome、`VizWebView`、RenderThread、Unity Job.Worker 等
线程，说明存在足够的并发条件，不能因为架构是 x86 就排除销毁竞态。

ARM64 崩溃实例的 CPU 数、marl worker 数、Queue 线程数没有留存在当前可用
证据中，无法进行对等时序比较。

## 日志检查

在 2026-08-25 12:59:27 UTC 读取现有 logcat 缓冲并搜索：

```text
destroyed mutex
FORTIFY
Fatal signal
vulkan.pastel
llvm::ManagedStatic
llvm::PassRegistry
rr::Nucleus
vk::Queue
marl
```

没有匹配结果。该结果只说明当时仍保留在 logcat buffer 中的日志没有这些
签名，不能替代 Agreement 转场前清理日志并持续采集 60 秒的复现测试。

## 未执行的低成本复现及重新进入条件

本次没有执行“清 logcat -> 点击同意 -> 每 5 秒采样至少 60 秒”，原因是：

- `logcat -c` 会改变运行状态；
- 点击协议会写入 userdata；
- 当前没有确认可用于此目的的独立、可恢复、全新测试 userdata；
- 任务明确禁止修改稳定 x86 镜像、主 userdata、容器或配置。

重新进入条件是：明确授权使用一个克隆或可丢弃的独立 userdata。届时最低
成本的单次测试应同步记录：

1. 点击前至少 15 秒、点击后至少 60 秒；
2. 每 5 秒记录 foreground Activity、游戏 PID、WebView renderer PID 和进程存活；
3. 同步记录相关 PID 的 maps 和线程名；
4. 保存完整 logcat，不用截图判断图形健康；
5. 检查 Agreement teardown 与 Unity 绘制、Pastel 映射及 Queue/marl 线程是否重叠；
6. 记录实际 Vulkan instance/device 创建和销毁证据。

在该测试以及当前 ARM64/x86 精确二进制身份闭环之前，支持状态保持为：

```text
x86: 当前未复现，不能认定机制免疫
ARM64: 已复现 destroyed-mutex，候选补丁未闭环
全 ABI: 不允许据此提升为已修复或可发布
```
