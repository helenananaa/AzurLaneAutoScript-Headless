# AzurLaneAutoScript Headless

**简体中文** | [English](README.en.md)

干掉图像渲染，让 ALAS 以更低开销运行在更广泛的设备上。

AzurLaneAutoScript Headless 使用 ANGLE NULL 渲染器运行《碧蓝航线》Unity
客户端，跳过真实图像渲染及其 GPU、显存和帧数据开销；同时直接读取类型化的
Unity UI 状态，提供给锁定版本的 ALAS。这样不仅改变了自动化的观察方式，也让
没有硬件 GPU、没有 KVM 或资源受限的设备获得可行的运行路径。

项目中的每一种观察和输入都必须经过显式映射；未知、歧义、过期或未经审阅的
状态会直接拒绝，而不会偷偷回退到像素识别。

> **项目状态：**目前属于研究级运行时，已经可以执行通过资格验证的任务路径，
> 但还不是普通 ALAS 安装的一键替代品，也不代表全部任务都能长期无人值守运行。

[适配任务大表](docs/alas-adaptation-task-board.zh-CN.md) ·
[字段支持明细](docs/alas-config-support-matrix.md) ·
[运行环境支持](docs/runtime-support-matrix.md) ·
[系统架构](docs/architecture.md) ·
[最新验证状态](docs/status.md) ·
[ALAS 集成说明](integration/alas/README.md)

2026-10-23：主线已整合公共 ALAS 适配、Redroid、KVM 和 Mac/HVF 的已有成果。
同一公共适配层在 Windows AVD 与本机 WSL Redroid 上完成原 ALAS 普通 12-4
手动地图任务；Reward、Commission、Research 已有有界调度与配置重入证据。
本机使用入口见[本地运行指南](docs/local-runtime-entry.zh-CN.md)，
整合与回归结果见[主线整合记录](docs/main-integration-20261023.zh-CN.md)。

## 两条核心主线

这个仓库主要解决两个互相依赖的问题。

### 1. 不再渲染和识别画面

传统游戏自动化先把每一帧完整渲染出来，再截图、传输并使用 OCR、模板匹配和
预先记录的坐标执行操作。这条链路同时消耗 GPU、显存、内存带宽和 CPU，也可能
把外观相似、被遮挡或尚未加载完成的页面误判为目标状态。

本项目直接从 Unity 获取结构化界面状态：

- 使用锁定版本的 ANGLE NULL-only 驱动，跳过真实图像渲染；
- 直接从 Unity 读取 Button、Text、Image、Toggle 和布局信息；
- 保留上游 ALAS 原有的任务状态机，而不是另写一套自动化逻辑；
- 只允许上下文明确、经过审阅且带有新鲜后置条件的动作；
- 遇到未知状态时拒绝继续，不回退到截图、OCR 或旧坐标。

### 2. 把 ALAS 带到更多设备

不再要求设备持续生成可见画面后，运行时可以面向远比传统模拟器更广的硬件：

- 有 KVM 的 x86_64 Linux 服务器和 Android Emulator；
- 没有嵌套虚拟化的云主机与 Redroid 容器路径；
- 只能使用 QEMU TCG 的低配或受限环境；
- ARM64 Linux、已 root Android 设备，以及由普通 ARM 设备托管的 guest；
- Apple Silicon Mac 上通过 Hypervisor.Framework 加速的 ARM64 Emulator；
- 通过 external ADB 接入、由外部负责生命周期的明确设备。

这并不表示所有组合现在都已经达到同一级别的 ALAS 生产支持。跨设备运行本身是
项目的一条核心主线，因此每个平台都分别记录运行、observer、游戏、恢复和 ALAS
工作负载证据，而不是简单写成“支持”或“不支持”。

## 目前能做什么

当前锁定的 ALAS 配置面共有 60 个。项目按面板和配置分支分别记录支持程度，
不会因为某一次任务成功就把整类功能标记为完成。

| 等级 | 面板数量 | 含义 |
|---|---:|---|
| 完整支持（`F`） | 9 / 60 | 在已验证环境中，必要配置值和异常分支均已闭环。 |
| 实机主路径完成（`L`） | 31 / 60 | 至少一条真实设备主路径已闭环，但并非所有配置值都已验证。 |
| 仅离线完成（`O`） | 3 / 60 | 已有契约、回放或桩验证，但还没有实机任务闭环。 |
| 部分完成（`P`） | 10 / 60 | 已实现或可以到达部分流程，仍有重要分支未完成。 |
| 到达明确边界（`B`） | 7 / 60 | 已安全到达账号、资源、日期或观察能力边界。 |
| 尚未完成（`M`） | 0 / 60 | 没有整块面板归入此类；仍有未适配字段及分支。 |

具有代表性的已验证工作包括：

- 通过原始 ALAS 路由运行普通主线和活动关卡；
- 奖励、委托、重启、科研、后宅、战术学院和建造等有界实机任务路径；
- 多条大型作战导航、刷取、商店、档案和 Boss 路径；
- 类型化读取地图、舰队、敌人、资源、弹窗和战斗结果；
- 与原任务相称的动作预算、精确目标检查和后置条件证明；
- 确定性回放、锁定补丁序列验证和失败路径测试。

这些结果不代表所有任务、服务器、账号状态、地图布局或配置组合都已经支持。
完整口径和待完成项以
[配置项级支持矩阵](docs/alas-config-support-matrix.md)为准；最新实验证据、失败和
回归记录在[验证状态](docs/status.md)中。

## 工作原理

运行时把观察、决策所有权和输入分开：

```text
锁定版本的《碧蓝航线》Unity 客户端
        |
        v
ANGLE NULL 渲染器 + 进程内语义观察器
        |
        | 带 generation 的类型化 UI 快照
        v
Fail-closed ALAS 适配层
        |
        | 经过审阅的状态查询和有界动作
        v
原始 ALAS 任务状态机
```

语义观察器在 Unity 主线程读取对象并输出本地类型化快照。适配层只翻译已经审阅
的 ALAS 资源和动作。输入发出前，可以要求目标页面上下文、active/interactable
状态、精确几何范围、EventSystem 顶层射线命中、新鲜 generation、显式输入预算
以及可验证的后置条件全部成立。

任务选择、筛选、重试、调度、导航逻辑和恢复仍由 ALAS 负责。适配层提供的是
受约束的观察与输入边界，不是第二套自动化引擎。

组件边界见[系统架构](docs/architecture.md)，证据口径见
[验收门槛](docs/acceptance-gates.md)。

## 安全模型

Headless 模式有意采用 fail-closed 设计：

- 语义会话中不会自动回退到截图、OCR、模板匹配或旧素材坐标；
- 没有显式审阅映射时，不开放通用点击、滑动、拖拽或确认动作；
- 实机执行使用与所请求任务相称的资源预算；独立资格实验的默认关闭策略不作为所有任务的零输入要求；
- 过期、不完整、不一致、被遮挡或存在歧义的 UI 状态会被拒绝；
- 完整资格证明绑定精确的游戏、运行时、ALAS 和证据版本；日常运行按能力与语义契约尝试兼容更新；
- fail-closed 以受影响的能力或任务为边界逐步收敛；包名、前台/PID、状态新鲜度和输入目标检查仍然生效；
- 离线回放成功不会自动提升为实机支持。

实机运行前应查看支持矩阵并配置本次任务的资源预算。上游提交或游戏版本变化
本身不意味着适配器不可用；通过当前运行契约仍不等于获得完整实机资格证明。
兼容性检查与保留限制见 [ALAS 鲁棒性审计](docs/alas-robustness-audit-20261002.zh-CN.md)。

## 从这里开始

请选择与你要验证的目标对应的入口。

### 检查控制器和契约

离线测试不需要启动游戏。完整回归需要相邻的锁定 ALAS 只读 checkout；
原生方法测试会自动生成一次性补丁树，也可通过 `ALAS_TEST_ROOT` 复用已验证的运行树。
准备方法见[本地运行指南](docs/local-runtime-entry.zh-CN.md)。

```powershell
$env:PYTHONPATH = 'python'
python -m pytest -q tests
```

### 构建 ANGLE NULL 运行时

ANGLE 必须在 Linux 上构建。Windows 环境下，当前支持的开发路径使用 WSL2。
下面的脚本会拉取锁定的上游版本、应用已审阅补丁，并构建基础驱动和 observer
驱动 APK：

```bash
cd /mnt/h/program/AzurLaneAutoScript-Headless
./scripts/wsl/bootstrap-angle.sh
./scripts/wsl/apply-angle-patches.sh
./scripts/wsl/build-angle-null.sh
./scripts/wsl/build-gles-contract.sh
./scripts/wsl/apply-angle-g3-patches.sh
./scripts/wsl/build-angle-null-observer.sh
```

这些命令只构建运行时基础，不会安装或路由游戏包，也不会启动 ALAS 工作负载。

### 验证 Unity observer 契约

契约项目锁定 Unity `2022.3.62f3`，请使用该版本编辑器构建 Android player：

```powershell
Unity.exe -batchmode -quit `
  -projectPath H:\program\AzurLaneAutoScript-Headless\unity\HeadlessContract `
  -executeMethod Alas.Headless.Contract.Editor.BuildAndroidPlayer.Build `
  -logFile -
```

默认输出为 x86_64 IL2CPP APK：
`unity/HeadlessContract/Build/HeadlessContract.apk`。在准备好的 Android guest 上
运行 observer 契约：

```powershell
.\scripts\windows\run-g3-observer.ps1 `
  -Serial emulator-5570 `
  -AngleApk <observer-AngleLibraries.apk> `
  -UnityApk .\unity\HeadlessContract\Build\HeadlessContract.apk
```

设备序列号和制品路径只是环境相关示例。不要在未核对 runtime lock 的情况下
直接复制到其他模拟器环境。

### 集成锁定版本的 ALAS

当前集成目标是上游 ALAS 提交
`81ccf63b4540f00241628c82a58c02c7a2bb11af`。集成采用有序、哈希校验的补丁
序列，并且默认不启用；只有显式应用并开启集成后，ALAS 行为才会改变。

按照 [ALAS 集成说明](integration/alas/README.md)构建和验证补丁序列。各个任务的
实机 runner 是资格验证工具，不是通用启动器；每个 runner 都有自己的设备指纹、
配置、输入预算和恢复要求。

## 运行环境支持

移除硬件 GPU 依赖后，项目已经在服务器、容器、纯软件虚拟化和物理设备上验证
了多条运行路径。这里的每一格都按实际证据标注；“能启动 Android”“ANGLE NULL
通过”“游戏到达登录前”和“长期运行 ALAS”是四个不同结论。

| 宿主与 Android 路径 | 当前状态 | 已验证范围 | 主要边界 |
|---|---|---|---|
| Windows + AVD / WHPX | **当前本机任务路径已验证** | ANGLE NULL、typed observer、普通 12-4 完整手动地图、登录和返回主页 | 单账号、单关卡证据；长期无人值守仍未资格化 |
| Windows/WSL + Redroid x86_64 | **当前本机任务路径已验证** | 共享 backend、完整 Main、日常有界调度、配置重入、容器恢复及持久化 | 不代表原生 Linux；真实版本迁移/回退、自然满仓连续恢复和长期运行待验证 |
| x86_64 Linux + KVM / Android Emulator | **主线可执行** | 历史 API 32 的 ANGLE NULL、Unity、observer 与 recovery；本地 API 34 登录前、持久化与生命周期另有记录 | 本地当前账号任务、长期 soak、容量和多实例密度待验证 |
| External ADB | **主线可执行** | 附着到精确指定设备，执行身份、生命周期和恢复合同 | 不负责设备 provisioning、root、升级或持久化 |
| x86_64 Linux + Redroid | **真实探索；backend 待实机资格** | 无 `/dev/kvm` 云主机上的 Binder、容器、ANGLE NULL、observer、完整资源、重启持久化和登录界面 | backend 已实现但隔离实例 lifecycle、当前 OCI 回退和 ALAS 工作负载尚未闭环 |
| ARM64 Linux + Redroid | **全新容器的真实游戏登录前路径已通过** | VA39、Android 14、新 userdata 首次协议、私有 ANGLE NULL、typed observer、28.1 GB 资源下载和一次有界冷重启后到达手机号登录 Activity；未输入账号 | 两项运行时修复尚未封入 OCI，私有 NULL 从首次启动起的协议转场仍需复验；ALAS workload、backend recovery/cleanup 和 soak 仍缺失 |
| x86_64 QEMU TCG | **部分通过，fallback** | Q1/Q2/Q3、Unity 长运行、observer freshness，游戏到达隐私协议边界 | WebView 黑屏与 System UI ANR 阻塞更深游戏验证，性能低于 KVM |
| 已 root ARM64 Android 设备 | **真实工具链探索** | systemless ANGLE 安装、验证、移除和回滚；G1 NULL renderer 合同 | 未验证当前游戏、完整 observer、ALAS、温控和长期运行 |
| 无 root ARM64 手机/平板作为 QEMU 宿主 | **实验性部分通过** | 普通应用权限托管 ARM64 guest、ANGLE NULL、Unity，游戏到达无输入登录前 | 无硬件加速且很慢；没有 observer、ALAS 和恢复闭环 |
| 无 root 设备直接路由 release 游戏 | **当前不支持** | debug/queryable GLES probe 可以加载调试 ANGLE | locked user build 不能把 side-loaded debug ANGLE 直接路由给 release 游戏 |
| Apple Silicon Mac + Android Emulator/HVF | **工程基线：独立 backend、lifecycle 与双 recovery 已通过** | M1、API 32 ARM64、Hypervisor.Framework、exact runtime lock；owned AVD lifecycle、game recovery、Android reboot recovery 和 cleanup 实机通过 | 未完成账号登录、主页面、ALAS workload、soak、快照恢复和多实例资格 |
| Intel Mac + Android Emulator/HVF | **后续候选** | 同架构 x86/x86_64 guest 路径可行 | 本仓库尚无真实 Intel Mac 生命周期或游戏证据 |

这张表展示的是跨设备路线，而不是用一个模糊的“全平台支持”标签掩盖成熟度差异。
当前正式候选从 x86_64 KVM 起步，但 Redroid、TCG、ARM64 和物理设备不是旁支：
它们共同验证了移除真实渲染以后，ALAS 可以逐步进入传统图形自动化难以覆盖的
运行环境。

准确的 host、ABI、Android、backend、恢复能力和未解决问题见
[运行环境支持矩阵](docs/runtime-support-matrix.md)。可复现镜像构建和回滚流程见
[Android 镜像基础运行手册](docs/android-image-foundation-runbook.zh-CN.md)；ARM64
端到端操作、故障根因和重新进入条件见
[ARM64 Redroid 运行手册与故障账本](docs/arm64-redroid-end-to-end-runbook.zh-CN.md)。Mac
实机证据见 [Apple Silicon Mac / HVF 登录页验证报告](docs/mac-apple-silicon-hvf-login-validation-report.md)。

## 仓库结构

- `python/alas_headless` — fail-closed 控制器和语义适配库。
- `integration/alas` — 锁定上游提交的 ALAS 补丁序列、profile、manifest 和证据。
- `patches/angle` — ANGLE NULL 渲染器基础兼容补丁。
- `patches/angle-g3`、`overlays/angle-g3` — 语义观察器补丁和新增源码。
- `probes/gles-contract` — Android GLES 契约工作负载。
- `unity/HeadlessContract` — 锁定版本的 Unity IL2CPP observer 契约项目。
- `scripts/wsl` — ANGLE 初始化、补丁和构建脚本。
- `scripts/windows` — Android 执行、采集和比较脚本。
- `scripts/python` — 回放、验证、证据和有界实机 runner。
- `tests` — 控制器、适配层、补丁序列、契约和回归测试。
- `docs` — 架构、支持矩阵、运行手册和验证报告。

生成的 APK、Android 镜像、游戏文件、账号数据、原始采集结果以及 Unity/Gradle
构建状态保存在 `artifacts`、`evidence`、`Build`、`Library` 等已忽略的本地路径。
仓库内只保留紧凑的 receipt、manifest、哈希和报告，不提交大型二进制文件。

## 文档导航

- [配置项级支持矩阵](docs/alas-config-support-matrix.md) — 60 个面板的权威支持范围和待完成分支。
- [运行环境支持矩阵](docs/runtime-support-matrix.md) — host、ABI、Android 和 backend 的支持与实验状态。
- [Windows WSL2 本地 Redroid 教程](docs/local-wsl-redroid-dev.zh-CN.md) — 自定义 WSL 内核、BinderFS、项目镜像、ADB、持久化与回滚。
- [ARM64 Redroid 端到端运行手册](docs/arm64-redroid-end-to-end-runbook.zh-CN.md) — ARM 构建、内核、容器、ANGLE、observer、资源登录流程和故障账本。
- [AWS ARM64 Redroid 全新容器登录复现](docs/aws-arm64-redroid-fresh-login-validation-20260826.md) — 新 userdata 首次协议、OCI writable-layer 偏差、28.1 GB 下载、冷重启与无账号输入登录边界。
- [Apple Silicon Mac / HVF 登录页验证](docs/mac-apple-silicon-hvf-login-validation-report.md) — Mac ARM64 Emulator、ANGLE NULL、游戏登录页与 typed observer 的实机证据。
- [系统架构](docs/architecture.md) — observer、adapter、controller 和 fail-closed 边界。
- [验证状态](docs/status.md) — 按时间记录、限定证据范围的验证结果。
- [运行时基础](docs/runtime-foundation.md) — 生命周期、制品锁、trace、恢复和清理契约。
- [ALAS 自上而下路线](docs/alas-topdown-roadmap.md) — 任务顺序和单项完成标准。
- [ALAS 集成说明](integration/alas/README.md) — 锁定补丁序列的构建和集成细节。

## 许可证与第三方边界

除非文件或目录另有声明，本项目采用 GNU GPL v3.0 only（`GPL-3.0-only`），见
[LICENSE](LICENSE)。锁定的 ALAS 集成补丁受 GPL 约束；ANGLE 补丁和 overlay
源码保留 ANGLE 的 BSD-style 许可证。完整署名和分发边界见
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。

仓库有意排除构建后的 APK、Android 镜像、游戏包和资源、账号数据以及本地证据
采集结果。公开本源码仓库不代表获得重新分发这些内容的授权。发布二进制制品前，
需要单独完成来源、许可证声明、对应源码和隐私审查。

本项目为非官方研究项目，与《碧蓝航线》权利方、ALAS 维护者、Google/ANGLE
或 Unity 均无隶属、授权或背书关系。
