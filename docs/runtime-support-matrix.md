# 运行时支持矩阵与探索状态

本文记录 AzurLaneAutoScript Headless 在不同宿主架构、Android 运行方式和
物理设备上的当前证据边界。服务器/物理设备基线快照日期为 **2026-08-26**；
Apple Silicon Mac / HVF 登录页证据已补充至 **2026-08-23**，x86_64
Redroid 后端只读预检证据已补充至 **2026-08-25**。

这里的“通过”只对表格中写明的范围有效。Android 能启动、ANGLE NULL 合同
通过、游戏到达登录前，以及完整 ALAS 长期运行是四个不同结论。目前没有任一
平台通过完整、无人值守、长期 ALAS 工作负载资格测试。

## 2026-09-07 本地 WSL KVM 补充

**后续闭环：**修复后的日常启动/停止入口已完成两次正常退出（code 0），
数据及资源保留，账号输入为零。具体范围见
[生命周期修复报告](kvm-local-lifecycle-20260907.zh-CN.md)。下文关机异常
属于修复前那轮记录，不再代表新入口的当前结果。

当前开发和构建仅使用本地 Windows/WSL；下方服务器表保留历史证据范围，
不表示旧构建机仍可使用。已复用 9 月 6 日成功完成的本地 J32 构建，发布
`kvm-r75-x86_64-local-20260907-r1`，并以独立 `alas-kvm-local-r5` AVD
验证 API 34 启动、48G userdata、外部 APK 安装/驱动替换、typed observer、
游戏重启和 Android 重启后的数据保留。旧镜像回退验证了 Android 启动和
userdata 保留；切回本地镜像后重新取得了新鲜语义状态。

新 AVD 的 Android 全屏教程会阻止 Unity 正常取得焦点，KVM 冷启动入口现
确认该系统提示。Emulator 34.2.7 的正常退出仍未通过：服务停止发生自我强杀，
guest 关机路径出现 core-dump。账号登录后的 ALAS 工作负载仍未验证。
完整资源更新和更新后的冷启动均已到达空手机号 SDK 登录页，Android
`Accounts: 0`；这不代表已到达 Unity `LoginUI2` 或通过登录后的任务。
详见[本地 KVM 开发与登录前验证](local-wsl-kvm-dev.zh-CN.md)。

## 状态定义

2026-09-07 本地补充：Windows/WSL2 Docker Project 已接入共享 Redroid backend，
通过登录前冷启动、游戏/容器重启恢复，并通过独立 overlay 上的受控镜像回滚演练。
这不更新下面原生 Linux 服务器格的资格，也不表示历史 FBE 镜像可回退或 ALAS
任务已通过。见[本地生命周期](redroid-wsl-runtime-20260907.zh-CN.md)和
[受控回滚报告](redroid-wsl-rollback-20260907.zh-CN.md)。

| 标记 | 含义 |
| --- | --- |
| 主线可执行 | qualify_runtime.py 的 execute 模式有主线后端实现，并具有真实环境生命周期证据。 |
| 真实探索 | 真实宿主或设备通过了写明的平台、合同或游戏边界，但主线后端尚未产品化。 |
| 后续候选 | 外部工具链和架构路径可行，但本仓库尚无真实资格证据；不计入当前支持。 |
| 部分通过 | 只通过前置门，或者在进入下一门前遇到明确阻塞。 |
| 未验证 | 有设计、构件或相邻平台经验，但该矩阵格本身没有真实资格证据。 |
| 不支持 | 当前权限或系统合同明确阻止目标路径。 |

所有运行时选择必须由 runtime lock 明确固定。运行开始后禁止在 KVM、Redroid、
TCG 或外部设备之间静默切换。ANGLE NULL 消除的是游戏对硬件 GPU 的依赖，
并不消除 Android 图形栈、虚拟化、Binder、guest ABI 或持久化存储要求。

## 服务器矩阵

| Android 运行方式 | x86_64 Linux 服务器 | ARM64 Linux 服务器 |
| --- | --- | --- |
| KVM / Android Emulator | **主线可执行；当前最成熟。** API 32 x86_64、KVM 探测、ANGLE NULL、Unity、observer、游戏登录前、game/Android recovery 均有证据。仍缺当前 ALAS 全任务、长期 soak 与多实例资格。 | **未验证。** 已有 ARM64 ANGLE、Unity 和 runtime-lock 构件，但没有真实 ARM KVM 宿主、guest 生命周期、游戏或恢复证据。 |
| Redroid | **真实探索；后端实现待执行资格。** 原生 x86 云宿主在无 /dev/kvm 条件下完成 Binder/容器路径、完整游戏资源、重启持久化并到达登录界面；未输入账号。主线后端已实现，并在当前 containerd 宿主通过 manifest、容器、ABI 和持久目录只读预检；尚未对隔离实例执行完整 lifecycle/recovery/cleanup，也缺当前 x86 OCI 真实回退。 | **全新容器的真实游戏登录前路径已通过，尚未取得 ALAS 资格。** AWS ARM64 宿主在 VA39 内核、Android 14 Redroid、新 userdata 首次协议、ANGLE NULL 和 typed observer 下完成 28.1 GB 资源下载；下载后按窄条件冷重启一次进入手机号登录 Activity，未输入或提交账号。当前 OCI 未封入两个运行时修复，后端生命周期、登录后主界面、ALAS 工作负载、恢复与 soak 仍缺失。 |
| QEMU TCG | **部分通过，仅作为 fallback。** Q1/Q2/Q3、Unity 长运行和 observer freshness 通过，游戏到达隐私协议边界；WebView 黑屏/System UI ANR 阻止更深 Q4。单线程 portable PGO 候选保留，MTTCG 已因超时或退化被否决。 | **服务器格未验证。** 没有真实 ARM 服务器资格结果。相邻证据来自非 root ARM64 平板托管同架构 QEMU/Cuttlefish：Unity 通过且游戏到达无输入登录前，但极慢，不能替代服务器证据。ARM64 API 32 的另一实验还受 keystore2 崩溃阻塞。 |

### x86_64 KVM

这是第一条正式支持候选，也是目前唯一同时具备主线可执行后端和真实
Android、游戏、observer、recovery 证据的服务器路径。

当前已验证范围包括：

- Linux /dev/kvm 权限与 KVM API version 12；
- 固定 AVD、ADB serial 所有权和进程 cleanup；
- API 32 x86_64 guest 的 ANGLE NULL、Unity 和 typed observer；
- 固定游戏在无账号输入条件下到达登录前；
- 游戏恢复要求新 PID、同一完整指纹和新鲜 observer；
- Android 恢复要求观察到 ADB offline，再重新通过 framework、游戏和 observer 门；
- 镜像实验线上的 21/21 平台能力、更新/回滚实验和约 23 秒冷启动中位数。

尚未验证当前 ALAS top-down 分支的完整任务、24 小时以上 soak、容量和多实例密度。

### x86_64 Redroid

历史真实探索已经证明普通 Linux 云主机在没有嵌套虚拟化时可以使用 Redroid：
Binder/BinderFS、MemFD、privileged 容器、ANGLE NULL、observer、约 27.8 GB
资源下载、容器重启后的 /data 持久化和游戏登录界面均有证据。ADB 只允许绑定
loopback，测试没有输入账号。

这条路径当前缺的是后端执行资格和当前制品闭环，而不是最初可行性证明：

- RedroidBackend 已实现预配置 containerd 实例的严格配置、digest/标签/ABI/
  持久卷校验、所有权感知 start/stop，以及 game/Android recovery；
- 当前 x86_64 宿主已通过只读 probe、resolve 和 provision，未启停现有实例；
- 尚未用隔离实例执行完整 start、ADB、Android、游戏、observer、恢复和 cleanup；
- 缺少当前 OCI digest、runtime lock、恢复和 cleanup 的统一资格 manifest；
- x86_64 原生宿主上的真实 OCI 回退尚未完成；
- 尚未绑定当前 ALAS 工作负载。

### ARM64 Redroid

分支 codex/android-image-foundation 已在真实 ARM64 服务器上获得：

- digest-pinned Android 12/API 31 与 Android 14/API 34 Redroid 基线；
- ARM64 G1 GLES NULL、G2 Unity、G3 observer；
- 单 APK、ARM64 split APK、资源中断续传、restart 和指针回滚；
- 三轮 Redroid restart 约为 18 秒，OCI digest 不变且 /data sentinel 保留；
- Android 12 到候选镜像再恢复 Android 12 的真实 OCI 回退；
- ADB loopback、独立 /data 挂载和 registry/index digest 身份；
- 双 ABI 确定性 OCI 打包器、源码锁、SBOM/NOTICE 和 provenance 门的代码实现。

当前不能 promotion 的原因：

- Redroid `/data` 使用每实例独立的宿主目录，仍需在当前候选上补齐 lifecycle、
  restart/persistence 与 rollback 证据；
- stock 基线安全补丁不足以作为长期发布基线；
- 自维护 AOSP/Redroid 双 ABI 构建和 owner-preserving OCI 已完成，但尚未在 ARM
  运行宿主完成自建候选首启资格；
- 真实游戏与资源全集已在 fresh userdata 到登录边界，首次隐私转场单次通过；但该次
  转场发生在私有 loader 恢复前，且两项运行时修复尚未封入 OCI。主界面和 ALAS
  工作负载仍未验证；
- RedroidBackend 已实现并通过离线合同与只读预检，尚未在 ARM 隔离实例完成
  lifecycle/recovery/cleanup 资格。

### QEMU TCG

TCG 定位为无法使用 KVM 且没有可用 Binder 容器环境时的兼容或 CI fallback，
不作为首选生产运行时。

x86_64 的同架构 TCG 已通过平台合同，但游戏 Q4 被协议 WebView 与 System UI
稳定性阻塞。冷启动明显慢于 KVM。MTTCG 虽能看到多 vCPU 线程，但 2 vCPU 和
4 vCPU 对照均退化或超时，因此不得把并行线程等同于性能提升。

ARM64 平板上的同架构 QEMU/Cuttlefish 实验说明该方向功能上可行，但首次
framework 启动和大 APK 安装以十几至二十分钟计，且没有 observer、ALAS 或恢复
闭环。该结果不能写入 ARM 服务器格，也不能作为手机产品路径。

## 物理设备附加矩阵

| 设备类型 | 当前状态 | 已验证 | 未验证或阻塞 |
| --- | --- | --- | --- |
| 已 root ARM64 手机 | **真实探索：部署工具可用。** | 已 root、Android API 29+、Magisk-compatible 模块目录；systemless ANGLE provider 的 install/verify/remove/reboot/rollback；G1 NULL renderer、surface、零 readback 和 GLES error 门。 | 不负责解锁或获取 root；未验证当前游戏 G4、完整 observer、ALAS、长期运行、温控与性能；未覆盖任意 KernelSU 布局。 |
| 无 root、locked ARM64 手机/平板：直接运行 | **当前不支持 release 游戏路由。** | debug/queryable GLES probe 可加载调试 ANGLE。 | locked user build 上的 release 游戏不能直接加载 side-loaded debug ANGLE；除非 OEM/userdebug 提供系统级路由能力，否则不能产品化。 |
| 无 root、locked ARM64 手机/平板：作为 QEMU 宿主 | **实验性部分通过。** | 普通应用权限下托管 ARM64 QEMU/Cuttlefish、ANGLE NULL、ARM64 Unity，并让游戏到达无输入登录前。 | 无硬件加速、速度很慢；没有游戏 G4、observer、资源更新、ALAS、恢复或长期资格。 |

主线 external-adb 后端只负责附着到一个明确指定的设备并执行身份/生命周期合同，
不会声称拥有设备 provisioning、root、bootloader、持久化或系统升级。

## Apple 设备后续支持

Apple 设备当前全部属于后续支持或实验研究，不计入已支持平台。必须区分
“Mac 作为 ALAS/Android 宿主”和“iPhone/iPad 作为被控游戏设备”；Mac 能运行
控制程序不等于本项目已经支持 iOS 游戏。

### Mac 宿主矩阵

| Mac 路径 | 当前状态 | 可行性与边界 |
| --- | --- | --- |
| Intel x86_64 Mac + Android Emulator | **后续候选。** | Android Emulator 可在 macOS 上使用 Hypervisor.Framework，并运行同架构 x86/x86_64 guest。可复用现有 x86_64 Android 经验，但当前 `kvm` 后端是 Linux `/dev/kvm` 专用，本仓库没有 Intel Mac 生命周期或真实游戏证据。 |
| Apple Silicon Mac + Android Emulator | **真实探索：G4 登录页与 typed observer 已通过。** | 真实 M1 MacBook Air 上的 Android Emulator 37.1.11 以 `-no-window -accel on` 运行 API 32 ARM64 guest；`-accel-check` 确认 Hypervisor.Framework。国服 9.7.10 ARM64 游戏经 ANGLE NULL observer 到达 `LoginUI2`，快照 `status=ok`、`age_ms=52`，并读出精确登录页 Button/Text/Image 路径。仍缺账号登录、主页面、ALAS workload、recovery、cleanup、soak 和独立 `macos-hvf` backend；见 [Mac/HVF 登录页验证报告](mac-apple-silicon-hvf-login-validation-report.md)。 |
| Apple Silicon Mac + MuMu Pro | **上游真实探索，本仓库未验证。** | 上游 ALAS 已合并 macOS MuMu Pro 设备识别修复并报告真实截图方向验证；本仓库仍固定在较早的 ALAS revision，尚未吸收或复验该路径。 |
| Apple Silicon Mac + PlayCover | **实验性上游候选。** | 上游有开放中的 PlayCover 支持 PR，通过修改版 PlayCover/PlayTools 提供截图、触控和应用控制并绕过 ADB；仍有字体、抗锯齿、模板及 ADB 专属功能差异，不能视为正式支持。 |
| Intel Mac + PlayCover/iOS 应用 | **不作为候选。** | macOS 直接运行兼容 iPhone/iPad 应用是 Apple Silicon 路径，不能推广到 Intel Mac。 |
| Mac + Redroid | **暂不支持。** | Redroid 依赖 Linux Binder/BinderFS 等宿主内核能力；Docker Desktop 的 Linux VM 不能等同于原生可控的 Redroid 宿主。 |
| Mac + QEMU TCG | **低优先级 fallback。** | 理论上可运行，但 Mac 已有 Hypervisor.Framework；在 HVF 路径未验证前不投入 TCG 性能和产品化工作。 |

Mac Android 第一阶段已经通过真实 Apple Silicon Mac 上的 Android Emulator/HVF、
ARM64 guest、ANGLE NULL observer 和游戏 `LoginUI2` 边界。下一阶段仍应复用
`external-adb`，补齐账号登录/主页面、observer freshness、game/Android recovery
和一个有界 ALAS workload。通过后再实现独立 `macos-hvf` 后端，负责 AVD 启停、
ready、recovery、cleanup 和 runtime lock；不得把 Hypervisor.Framework 冒充
Linux KVM。

参考外部状态：

- [Android Emulator 硬件加速](https://developer.android.com/studio/run/emulator-acceleration)
  说明 macOS 使用 Hypervisor.Framework，并要求 host 与加速 guest 架构匹配；
- [上游 MuMu Pro macOS 修复](https://github.com/LmeSzinc/AzurLaneAutoScript/pull/5821)
  已合并，但只代表上游对应实现和报告环境；
- [上游 PlayCover 支持](https://github.com/LmeSzinc/AzurLaneAutoScript/pull/5866)
  截至本快照仍是开放 PR，不得作为发布依赖。

### iPhone 与 iPad

| iOS/iPadOS 路径 | 当前状态 | 主要阻塞或条件 |
| --- | --- | --- |
| 非越狱 iPhone/iPad 实机 | **研究项，不是当前产品方向。** | 没有 ADB。可研究 macOS + Xcode + Appium/XCUITest + WebDriverAgent，但需要设备信任、Developer Mode、UI Automation、代码签名和 provisioning profile，并承担 WDA 会话及系统升级兼容成本。 |
| 越狱 iPhone/iPad | **暂不支持。** | 系统版本、越狱工具、注入权限和安全边界高度碎片化；当前不建立正式 backend 或发布承诺。 |
| iOS Simulator | **对正式游戏阻塞。** | Simulator 需要面向 Simulator 构建的应用。本项目没有碧蓝航线源码或对应构建，不能把普通 App Store IPA 当作可资格验证的模拟器制品。 |
| Apple Silicon Mac 直接运行 iOS 游戏 | **只按 PlayCover 实验处理。** | 是否可从 Mac App Store 直接安装由发行方决定；侧载、修改运行时或 PlayCover 不能与官方可用性混为一谈。 |

iOS 实机若进入 spike，只允许先验证截图延迟、点击/滑动、应用启动停止、Unity
accessibility hierarchy、断线恢复和长会话稳定性。若 Unity 场景不能提供完整、
稳定且可身份绑定的语义结构，就只能形成独立的截图/OCR 兼容线；不得静默回退并
冒充当前 semantic observer。也不得把开发证书、provisioning profile、设备 UDID、
账号数据或解密 IPA 写入 Git、公开镜像或证据包。

参考外部约束：

- [Appium XCUITest 真实设备准备](https://appium.github.io/appium-xcuitest-driver/latest/getting-started/device-setup/)
  列出设备信任、Developer Mode、UI Automation 和 WDA provisioning 要求；
- [Apple 开发 provisioning profile](https://developer.apple.com/help/account/provisioning-profiles/create-a-development-provisioning-profile/)
  要求 App ID、开发证书和注册设备；
- [Apple Silicon Mac 运行 iPhone/iPad 应用](https://support.apple.com/en-gb/guide/app-store/fird2c7092da/mac)
  只说明发行方允许的兼容应用，不证明碧蓝航线当前可用；
- [上游 iOS 支持讨论](https://github.com/LmeSzinc/AzurLaneAutoScript/issues/5348)
  仍是开放性讨论，没有正式 backend。

## 镜像制造能力与运行支持的区别

Android 镜像线已经实现或验证双 ABI ANGLE/Unity 制品、更新实验、内容哈希、
source lock、确定性 OCI、SBOM/NOTICE、userdata、restart 和 rollback 门。它仍然
不能单独把一个矩阵格提升为“ALAS 支持”。提升至少需要：

1. 对应架构和运行方式的真实宿主；
2. 内容 digest 固定的 Android、ANGLE、游戏和资源身份；
3. 可执行 backend 的完整 probe、resolve、provision、start、ready、recover、stop；
4. G1/G2/G3，以及按目标声明的真实游戏边界；
5. cleanup、restart、rollback 和 userdata 隔离证据；
6. 当前 ALAS 工作负载、长时间 soak 和容量证据。

游戏 APK、游戏资源、账号 userdata 和含账号信息的原始证据不得进入公开镜像或 Git。

## 当前代码和开发分支

当前主分支代码状态（2026-08-24；开发基线以标签解引用的提交为准，文档提交
本身不需要形成自引用哈希）：

| 分支 | 快照提交 | 状态与范围 |
| --- | --- | --- |
| main | `dev-baseline-20260824` | `codex/android-image-foundation` 与 ALAS top-down 工作均已进入主线。可执行 lifecycle backend 仍只有 `kvm` 和 `external-adb`；`redroid`、`tcg`、`arm64-qemu` 继续由 `DeferredRuntimeBackend` fail-closed。当前 ALAS series 有 88 个成员并锁定上游 `81ccf63b4540f00241628c82a58c02c7a2bb11af`；本机全量套件通过 1693 项、跳过 3 项。四个非战斗 workload 与一个 12-4 官方自律 workload 均已有成功且通过统一完整性校验的 KVM 采集。这个标签是并行开发的工程基线，不是完整任务、长时间、多实例或生产发布资格。 |

旧的 platform-qualification、redroid-qualification、tcg-optimization、
arm64-qemu-qualification 和 arm64-venus-qualification 分支是证据与实现参考，
不是可以直接恢复为新开发基线的当前主线。

## 推荐推进顺序

1. 将当前 ALAS top-down 工作负载绑定到 x86_64 KVM，形成第一条端到端支持线。
2. 对已实现的独立 RedroidBackend 执行 ARM64 隔离实例 lifecycle/recovery/cleanup 资格，并把当前真实登录前证据绑定到 runtime lock。
3. 在原生 x86_64 Binder 宿主补齐当前 Redroid OCI、restart 和 rollback。
4. 将已 root 手机部署工具与 external-adb runtime lock 接通，并重新执行当前游戏 G4。
5. 获得真实 ARM64 KVM 服务器后，从 host Q0 开始建立独立 ARM KVM 证据。
6. TCG 保持 fallback；在有可重复 ALAS trace 前不继续 MTTCG、密度或主机特化调优。
7. 无 root 设备直接路由 release 游戏不作为当前主产品方向。
8. Apple Silicon Mac 的 Android Emulator/HVF、ARM64 guest、ANGLE NULL
   observer 和 G4 `LoginUI2` 已通过；下一步以 external-adb 补账号登录/主页面、
   freshness、game/Android recovery 和一个有界 ALAS workload。
9. 上述 Mac external-adb 生命周期与 workload 资格通过后再实现 `macos-hvf`
   后端；Intel Mac 仅在有真实设备和维护价值时补充 x86_64 对照。
10. PlayCover 只跟踪上游并保持实验隔离；iPhone/iPad 实机只做有停止条件的 WDA
    spike，越狱与 iOS Simulator 不进入当前路线图。

## 状态更新规则

更新本矩阵时必须同时写明宿主架构、backend、Android API/ABI、镜像或 OCI digest、
ANGLE revision/APK hash、游戏版本和 ABI、observer schema、runtime-lock hash、输入
边界以及最高通过门。不同 backend、ABI、镜像、游戏或未提交工作树的证据不得互相
覆盖，也不得以代码存在、容器存活或 sys.boot_completed=1 单独宣称支持。
