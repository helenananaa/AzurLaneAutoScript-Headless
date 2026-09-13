# KVM 后续优化候选：启动预编译优先

本轮是测量与源码审计，未修改运行配置或镜像。沿用关闭开机动画的启动入口，
只启动 Android 到 launcher，未启动游戏或输入账号。挂载 UUID、锁定 manifest、
1355 项源码库存和既有 sync receipt 已核对。

## 新测量

- ready 总耗时 35.589 秒：ADB 15.177 秒、framework 16.399 秒、网络 3.805 秒。
- `MakeDisplayManagerServiceReady` 仍很短，为 4 ms；开机动画关闭保持生效。
- RenderEngine 生成 122 个 shader 耗时 15815 ms；guest monotonic 27.341 秒
  完成，28.056 秒出现 `wm_boot_animation_done`。
- 同配置上一轮 ready 为 29.546 秒。本轮再次说明单次总耗时不代表稳定提速，
  但 shader 编译持续占据重要启动成本。
- launcher 稳定后的 20.024 秒宿主线程 CPU 增量采样约 0.101 个逻辑核；
  只统计窗口前后均存在的线程，未计短命线程，不能外推游戏负载。
- Emulator RSS 2523288 KiB，约 2.41 GiB；无 swap。此数包含宿主开销和 guest
  内存，不能作为 Android 应用独占内存。
- guest `dumpsys meminfo`：正常内存状态，可回收/空闲合计约 1993714 KiB，
  cached PSS 148110 KiB。Bluetooth PSS 28225 KiB、Phone 20905 KiB、
  CameraServer 11205 KiB。不能把各进程共享页面的 RSS 相加作为裁剪收益。

## 按价值排序

### 1. SurfaceFlinger 预编译改为按需编译

本地 `frameworks/native/services/surfaceflinger/SurfaceFlinger.cpp` 914 行附近
由 `service.sf.prime_shader_cache` 控制预编译，默认 true；729 行附近启动完成
会等待其 future。`libs/renderengine/skia/SkiaRenderEngine.cpp` 252 行附近
的 SkSLCacheMonitor::load 明确不缓存内容，始终返回 nullptr。这不能证明所有
底层驱动均无缓存，但足以否定“这一层自动跨启动保存 shader”的假设。

这是下一次实验首选。须在独立候选中验证启动前配置实际生效，比较启动总耗时
及首次 system UI/游戏启动的按需编译代价；先沿用原镜像验证可行的配置路径，
确需镜像改动再做增量构建。15.8 秒是观察到的编译成本，不是可承诺节省量。
回退应恢复原预编译行为，无需重置 userdata。

### 2. 关闭系统背景模糊作为较窄候选

当前 `ro.surface_flinger.supports_background_blur=1`。
`libs/renderengine/skia/Cache.cpp` 705 行附近仅在支持 blur 时调用 drawBlurLayers；
SurfaceFlinger 在构造时读取该属性。关闭它可能缩减 shader 预编译和系统特效
成本，但尚未做 A/B，不能量化收益。它与第一项有重叠收益，不能简单相加。
优先作为保留预编译时的较窄替代方案，验证系统弹窗、输入和游戏观察不受影响。

### 3. 系统服务裁剪与内存压缩暂排后

少量不相关组件有可测 PSS，但当前 idle CPU 低、无内存压力，cached 页可回收。
没有证据支持一次性删除大量组件，或以 launcher 能运行为依据下调默认 guest RAM。
先保留网络、包安装/权限、输入与 SDK 依赖；裁剪应等具体组件依赖与实际收益明确。

网络等待仍有约 3.8 秒，但当前源码和日志未发现可直接删除的固定 sleep。
应继续保留真实连接/IP 就绪检查，不能用省略检查代替网络优化。

## 收尾

`Accounts: 0`；正常 Stop 返回 0，userdata 保留。本轮没有产品代码修改，未
重复运行无关回归，也未提升任何支持等级。
原始日志、属性、PSS、CPU 样本及启动/停止输出位于
`artifacts/local-kvm/optimization-audit-20260908/`。
