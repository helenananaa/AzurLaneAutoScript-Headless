# 在 Windows WSL2 本地运行 Redroid

这份教程记录一条已经在本项目实机跑通的低成本路径：在 Windows WSL2 中使用带
Binder/BinderFS 的自定义 Microsoft WSL 内核，启动 stock Redroid 或本项目自维护的
x86 Redroid 镜像，并从 Windows 通过 ADB 访问它。

它适合日常开发和调试：Redroid 启动、ADB、应用安装、ANGLE NULL、observer、ALAS
适配、容器重启和宿主目录 `/data` 持久化。原生 Linux 行为仍未资格化；外部构建
主机已退役，当前开发和镜像构建只使用本地 Windows/WSL。

2026-10-23 的已登录 `gameplay` 实例、公共适配修复、原调度组合、AVD 参考和本机
运行入口见[最新连续性记录](redroid-continuity-20261023.zh-CN.md)。下方登录前
结果保留其历史日期与范围，不代替该记录的当前验证与未完成项。

## 1. 已验证结果

2026-08-31 至 2026-09-07 的本机验证结果：

- Windows 11 + WSL2，Ubuntu 22.04；
- 自定义内核 `6.18.33.2-microsoft-standard-WSL2-alas-redroid+`；
- BinderFS 中存在 `binder`、`hwbinder`、`vndbinder`；
- Docker 使用 overlayfs 和 cgroup v2；
- 项目 Redroid 容器到达 `sys.boot_completed=1`；
- Windows ADB 可通过 `127.0.0.1:5556` 连接；
- `Accounts: 0`，没有输入任何游戏或系统账户；
- 容器 Stop→Start 后 `/data/local/tmp` 持久化标记仍存在；
- 项目镜像中的 `libEGL.so` 和 `vulkan.pastel.so` 哈希与留存构建证据一致；
- 稳定性采样期间容器 PID 不变、无 OOM、无 kernel panic。
- `Api31` profile 中游戏经强制 `-force-gfx-st` 冷启动后，observer 连续输出新鲜且
  coherent 的 typed `LoginUI2(Clone)`；
- 已停在空手机号登录页，`Accounts: 0`，没有输入或提交账户信息；
- `Api31` 容器 Stop→Start 后游戏、observer、公共资源和登录前状态均保留。
- 本地 WSL 构建域完成当前 source lock 的 x86_64 AOSP/Redroid 构建，生成的
  `system.img`、`vendor.img` 与远端最终优化构建逐字节一致；
- 本地构建 OCI `0b84bf53...459936` 已由独立 `Project` 容器启动到
  `sys.boot_completed=1`，API 34、x86_64、fingerprint、EGL/Pastel 哈希均匹配；
- 新的 `projectlocal-data` 经 Stop→Start 后保留无敏感内容的 `/data` 标记，且
  `Accounts: 0`；
- 9.7.10 x86_64 游戏已外部安装到这份独立 userdata。首次隐私页通过 DevTools/CDP
  验证标题、唯一可见且启用的“同意/拒绝”DOM，只调用一次 `.agree.click()`，同一
  游戏 PID 返回 MainActivity，60 秒内没有 fatal 或 destroyed-mutex；
- 协议后直接冷启动会短暂打开并销毁 `AnnouncementActivity`，并可能让 Unity 停在
  `OnApplicationPause`。G4 的显式 `-AllowSdkActivityReentry` 分支在确认精确 Activity
  历史、同一 PID、stale/unavailable observer 且无 fatal 后，执行一次 HOME→MainActivity
  生命周期 re-entry；恢复后 20 秒内 19/19 sample 新鲜，generation 从 `3` 前进到 `92`，
  typed 资源选择页出现唯一 raycast-top Confirm。没有点击资源选项。
- 基础资源页进一步确认 `Max=true`、`Min=false`。首次 Confirm 无后置的根因不是
  Unity mapping，而是 SystemUI `ImmersiveModeConfirmation` 持有 InputDispatcher focus；
  将 secure `immersive_mode_confirmations` 设为 `confirmed` 后，focused window 精确返回
  MainActivity，基础资源 Confirm、六项附加资源 Confirm 和下载 action 均取得递增
  generation 与预期后置状态；
- 本地保留的 `9.7.328` 资源基底以停止容器、独立 external-files 目录、Android
  `10067:1078` owner/mode 的方式导入。源为 90,503 文件 / 30,226,737,560 字节；导入后
  目标为 90,507 文件 / 30,226,761,687 字节，未复制 `/data/user/0` 或账号数据；
- 当前资源选择弹窗精确声明 `25.8GB`，下载报告 81,985 文件、失败 0，日志出现
  `BGDownload all task end:0`，最终版本为 `9.7.356`。资源目录变为 172,451 文件 /
  57,846,200,783 字节；
- Project 容器 Stop→Start 后 OCI digest、APK、资源和 `9.7.356` 版本均保留。随后带
  `-force-gfx-st` 冷启动和一次受控 re-entry，以新 PID 到达 PhoneLoginActivity；唯一
  手机号输入为空、“下一步”存在且 disabled，`Accounts: 0`，没有输入或提交账号。
- 在独立 Project guest 上还执行了可回滚的 Announcement component A/B：root 模式下
  精确禁用该 component 后，冷启动出现 `DownloadTool:OnResume` 且 observer 自然持续
  前进，但 90 秒内“正在检查更新...”仍未结束，因此该变更不足以解决资源流程，已恢复
  component `default` 状态并执行 `adb unroot`。

当前仓库提供三个相互隔离的 profile：

| Profile | 用途 | ADB | `/data` |
|---|---|---|---|
| `Project` | 本项目自维护 x86 镜像，默认选择 | `127.0.0.1:5556` | `projectlocal-data` |
| `Stock` | 官方 Android 14 x86_64-only 宿主冒烟 | `127.0.0.1:5555` | `localdev-data` |
| `Api31` | 官方 Android 12/API 31 游戏与登录前链路基线 | `127.0.0.1:5557` | `api31-game-data` |

三个 profile 都只把 ADB 发布到 loopback，不会监听局域网或公网。当前本地游戏链路
保留 `Api31` 作为已知良好对照；`Project` 已在项目 Android 14 镜像、独立 userdata 上
通过首次协议、G4、完整资源更新、Stop→Start 持久化和空手机号登录边界。它仍未通过账号
登录、ALAS workload、rollback 或 soak，因此不能把登录前结果推广为完整 ALAS 支持。
统一 backend 的登录前启动、游戏/容器重启和 cleanup 已在本日后续验证通过，见第 15 节。
禁用 SystemUI 的可回滚 A/B 无效且已恢复，不是启动条件。

## 2. 为什么不能只下载几个模块

Redroid 最关键的宿主能力是 Android Binder IPC。当前 Microsoft WSL 源码中的：

```text
CONFIG_ANDROID_BINDER_IPC
CONFIG_ANDROID_BINDERFS
```

都是 `bool` 选项。stock WSL 内核若显示：

```text
# CONFIG_ANDROID_BINDER_IPC is not set
```

就不存在一个可以事后插入的 `binder_linux.ko`；必须重新编译并启动整个 WSL 内核。
因此本教程只要求内核内建 Binder/BinderFS，并保留 Microsoft WSL 的完整 Docker、
网络、文件系统、Hyper-V 和 WSLg 配置。Redroid 的 `/data` 使用独立宿主目录持久化。

参考上游：

- [Microsoft WSL2 Linux Kernel](https://github.com/microsoft/WSL2-Linux-Kernel)
- [Redroid 官方文档](https://github.com/remote-android/redroid-doc)
- [WSL `.wslconfig` 文档](https://learn.microsoft.com/windows/wsl/wsl-config)

## 3. 前置条件

建议准备：

- Windows 11，WSL2 已安装；
- Ubuntu 22.04 WSL 发行版；
- WSL 内至少约 30 GiB 可用空间用于内核源码和构建输出；
- 16 GiB 以上可用内存；本机配置为 20 GiB WSL 内存、16 GiB swap；
- Ubuntu 内运行自己的 Docker daemon，且 `systemctl is-active docker` 返回 `active`；
- Windows 已安装 ADB；本机使用 `F:\platform-tools\adb.exe`；
- 本仓库已迁到当前工作目录。

先检查现状：

```powershell
wsl -l -v
wsl -d Ubuntu-22.04 -- uname -r
wsl -d Ubuntu-22.04 -- bash -lc "systemctl is-active docker; docker info"
```

进入 WSL 后检查 stock 内核是否已有 Binder：

```bash
zcat /proc/config.gz | grep -E 'CONFIG_ANDROID_BINDER|CONFIG_MODULES|CONFIG_MODVERSIONS'
grep binder /proc/filesystems || true
```

如果 Binder 已经是 `y` 且 BinderFS 可挂载，可跳到第 7 节。否则继续编译。

## 4. 编译 Microsoft WSL 自定义内核

### 4.1 安装依赖

在 Ubuntu WSL 中执行：

```bash
sudo apt-get update
sudo apt-get install -y \
  build-essential flex bison bc cpio dwarves libelf-dev libncurses-dev \
  libssl-dev qemu-utils zstd
```

### 4.2 使用与当前 WSL 匹配的源码

本次实测的 stock release 是 `6.18.33.2-microsoft-standard-WSL2`，对应源码 tag：

```bash
mkdir -p ~/src ~/build
git clone --depth 1 \
  --branch linux-msft-wsl-6.18.33.2 \
  https://github.com/microsoft/WSL2-Linux-Kernel.git \
  ~/src/wsl-redroid-kernel-6.18.33.2
```

WSL 更新后不要照抄旧 tag。应先运行 `uname -r`，再选择匹配的 Microsoft tag；
源码、内核和模块的 release 必须一致。

### 4.3 生成配置

```bash
src=~/src/wsl-redroid-kernel-6.18.33.2
out=~/build/wsl-redroid-6.18.33.2

mkdir -p "$out"
cp "$src/Microsoft/config-wsl" "$out/.config"

"$src/scripts/config" --file "$out/.config" \
  -e ANDROID_BINDER_IPC \
  -e ANDROID_BINDERFS \
  --set-str ANDROID_BINDER_DEVICES "binder,hwbinder,vndbinder" \
  --set-str LOCALVERSION "-microsoft-standard-WSL2-alas-redroid" \
  -d LOCALVERSION_AUTO

make -C "$src" O="$out" olddefconfig
```

必须确认：

```bash
grep -E '^(CONFIG_ANDROID_BINDER_IPC|CONFIG_ANDROID_BINDERFS|CONFIG_ANDROID_BINDER_DEVICES|CONFIG_MODULES|CONFIG_MODVERSIONS|CONFIG_OVERLAY_FS)=' "$out/.config"
```

预期至少包含：

```text
CONFIG_ANDROID_BINDER_IPC=y
CONFIG_ANDROID_BINDERFS=y
CONFIG_ANDROID_BINDER_DEVICES="binder,hwbinder,vndbinder"
CONFIG_MODULES=y
CONFIG_MODVERSIONS=y
CONFIG_OVERLAY_FS=y
```

### 4.4 编译

本机使用 16 个并发任务：

```bash
make -C "$src" O="$out" -j16
```

完成后验证：

```bash
make -s -C "$src" O="$out" kernelrelease
file "$out/arch/x86/boot/bzImage"
sha256sum "$out/arch/x86/boot/bzImage"
git -C "$src" status --short
```

源码树应保持干净。实际 `kernelrelease` 可能带尾部 `+`，后续安装模块时必须使用命令
实际返回的完整字符串，不要手工猜测。

## 5. 生成匹配的 modules.vhdx

不能只复制 `bzImage` 并继续使用旧模块盘，否则会出现 vermagic/modversion 不匹配。

安装剥离调试信息后的模块：

```bash
dist=~/build/wsl-redroid-artifacts
kernel_release=$(make -s -C "$src" O="$out" kernelrelease)

mkdir -p "$dist/modules-stripped"
make -C "$src" O="$out" \
  INSTALL_MOD_PATH="$dist/modules-stripped" \
  INSTALL_MOD_STRIP=1 \
  modules_install
```

使用 Microsoft 提供的脚本生成 VHDX：

```bash
sudo "$src/Microsoft/scripts/gen_modules_vhdx.sh" \
  "$dist/modules-stripped" \
  "$kernel_release" \
  "$dist/modules.vhdx"

qemu-img info "$dist/modules.vhdx"
sha256sum "$dist/modules.vhdx"
```

当前上游 helper 可能留下指向 `/tmp/.../modules.img` 的 loop 映射。生成完成后检查：

```bash
sudo losetup -a | grep '/tmp/.*/modules.img' || true
```

若存在，只对输出中明确列出的 `/dev/loopN` 执行 `sudo losetup -d /dev/loopN`；不要对
未知 loop 设备批量操作。

## 6. 安装到 Windows 并切换 WSL 内核

### 6.1 复制制品

在 Windows 创建一个版本化目录，例如：

```powershell
$kernelDir = "$env:USERPROFILE\wsl-kernels\6.18.33.2-alas-redroid"
New-Item -ItemType Directory -Path $kernelDir -Force
```

把以下文件复制进去：

```text
bzImage       <- ~/build/wsl-redroid-6.18.33.2/arch/x86/boot/bzImage
modules.vhdx  <- ~/build/wsl-redroid-artifacts/modules.vhdx
config        <- ~/build/wsl-redroid-6.18.33.2/.config
```

可通过 `\\wsl.localhost\Ubuntu-22.04\home\<WSL用户>\build\...` 从 Windows 复制。
复制后分别计算源和目标 SHA-256，必须完全一致。

### 6.2 备份并修改 `.wslconfig`

先备份：

```powershell
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
Copy-Item -LiteralPath "$env:USERPROFILE\.wslconfig" -Destination "$env:USERPROFILE\.wslconfig.pre-redroid-$stamp.bak"
```

保留原有内存和 swap 设置，增加 `kernel` 与 `kernelModules`：

```ini
[wsl2]
memory=20GB
swap=16GB
swapFile=E:\\CacheVault\\WSL\\wsl-swap.vhdx
kernel=C:\\Users\\<WindowsUser>\\wsl-kernels\\6.18.33.2-alas-redroid\\bzImage
kernelModules=C:\\Users\\<WindowsUser>\\wsl-kernels\\6.18.33.2-alas-redroid\\modules.vhdx
```

使配置生效：

```powershell
wsl --shutdown
wsl -d Ubuntu-22.04 -- uname -r
```

## 7. 验证宿主能力

在 WSL 中：

```bash
uname -r
grep binder /proc/filesystems

sudo install -d -m 0755 /dev/binderfs
mountpoint -q /dev/binderfs || sudo mount -t binder binder /dev/binderfs
ls -l /dev/binderfs/binder /dev/binderfs/hwbinder /dev/binderfs/vndbinder

sudo modprobe quota_tree
sudo modprobe quota_v2

stat -fc %T /sys/fs/cgroup
grep -w overlay /proc/filesystems
systemctl is-active docker
docker info --format 'driver={{.Driver}} cgroup={{.CgroupVersion}} kernel={{.KernelVersion}}'
```

预期：

- BinderFS 三个字符设备存在；
- 模块 vermagic 与 `uname -r` 一致；
- cgroup 返回 `cgroup2fs`；
- Docker driver 是 overlayfs；
- Docker daemon 为 active。

## 8. 启动项目 Redroid

在仓库根目录的 Windows PowerShell 中：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/windows/manage-redroid-wsl-local-dev.ps1 -Action Start -Profile Project
```

启动器会：

1. 启动隐藏的 WSL keepalive；
2. 通过 WSL root 入口挂载 BinderFS，不要求配置全局免密 sudo；
3. 从 OCI identity 校验候选 ABI、external-install 合同、大小、SHA-256 和 manifest digest；
4. 直接导入本地构建 OCI，并创建独立的 `projectlocal-data`；
5. 只把 ADB 发布到 `127.0.0.1:5556`；
6. 等待 `sys.boot_completed=1`，超时或容器退出时明确失败。

项目 profile 默认从所有 sibling worktree 之外的统一本地候选目录读取制品：

```text
H:\program\AzurLaneAutoScript-Headless-localdata\redroid-x86_64-candidates\current\
  redroid-x86_64.oci.tar
  redroid-x86_64.oci-build.json
```

候选目录也可以通过 `-ProjectArtifactDirectory <绝对路径>` 显式指定。启动器不扫描或
猜测“最新”文件；目录、identity 或 OCI 缺失时会 fail closed。此时可以先使用 Stock
profile 验证宿主，但不能把 stock 结果冒充项目镜像结果。

## 9. Windows ADB 验证

```powershell
adb connect 127.0.0.1:5556
adb -s 127.0.0.1:5556 wait-for-device
adb -s 127.0.0.1:5556 shell getprop sys.boot_completed
adb -s 127.0.0.1:5556 shell getprop ro.build.fingerprint
adb -s 127.0.0.1:5556 shell pidof system_server
adb -s 127.0.0.1:5556 shell ls -l /dev/binder /dev/hwbinder /dev/vndbinder
adb -s 127.0.0.1:5556 shell dumpsys account | Select-String 'Accounts:'
```

项目镜像的预期 fingerprint 包含：

```text
redroid_x86_64_only:VanillaIceCream/AP2A.240805.005.S4/alas-android-14-r75
```

ANGLE/Vulkan 制品身份可检查：

```powershell
adb -s 127.0.0.1:5556 shell sha256sum /system/lib64/libEGL.so /vendor/lib64/hw/vulkan.pastel.so
```

本次留存构建证据中的预期值：

```text
fa900be068b94760a7726996a14cafbc2cfcf01ce854f31d7689c65490c548a6  /system/lib64/libEGL.so
19c6959e163a9816b44d75525fbcaaa5b909ed34b4c6124b7f9af8282eb77c34  /vendor/lib64/hw/vulkan.pastel.so
```

这证明镜像组件身份，不等于游戏、Unity observer 或 ALAS 主链已经完成 live 验证。

## 10. 验证 `/data` 持久化

创建一个无敏感内容的标记：

```powershell
adb -s 127.0.0.1:5556 shell touch /data/local/tmp/alas-wsl-persistence-marker
```

停止并重新启动：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/windows/manage-redroid-wsl-local-dev.ps1 -Action Stop -Profile Project
powershell -ExecutionPolicy Bypass -File scripts/windows/manage-redroid-wsl-local-dev.ps1 -Action Start -Profile Project
adb -s 127.0.0.1:5556 shell ls -l /data/local/tmp/alas-wsl-persistence-marker
```

标记仍存在才说明宿主目录持久化通过。不要用容器仍在运行或历史日志代替重启验证。

## 10.1 全新游戏隐私页的 DOM 边界

Project 全新 userdata 第一次启动固定游戏时会进入 `AgreementWebActivity`。先按 G4
合同安装 observer ANGLE，并始终用 `-force-gfx-st` 冷启动游戏；黑 framebuffer 不用于
判断或输入。确认前台 Activity 后执行：

```powershell
powershell -ExecutionPolicy Bypass `
  -File scripts/windows/accept-game-webview-agreement.ps1 `
  -Serial 127.0.0.1:5556
```

脚本通过 WebView DevTools/CDP，要求标题、`.agree`、`.disagree`、中英文案、可见矩形、
enabled 状态、包、Activity、PID 和 socket 全部精确匹配。它只点击一次唯一 `.agree`，
随后要求同一 PID 返回 MainActivity，并观察 fatal/destroyed-mutex。缺少 Python
`websocket-client` 时明确失败；不会回退到 framebuffer 或坐标。

协议成功不代表 G4 自动成功。当前 Android 14 候选可显式启用一次性恢复：

```powershell
powershell -ExecutionPolicy Bypass `
  -File scripts/windows/run-g4-game-init.ps1 `
  -Serial 127.0.0.1:5556 `
  -AngleApk <verified-AngleLibraries.apk> `
  -RequireSemanticButtons `
  -AllowSdkActivityReentry
```

该开关默认关闭。只有 Announcement Activity 历史、当前 MainActivity、同一 PID、
stale/unavailable observer 和无 fatal 同时满足时才会切到精确 HOME Activity，再带
`-force-gfx-st` 返回 MainActivity；随后仍须取得两次递增 generation 和完整 G4 检查。
健康启动、其他 Activity 或其他 observer 错误不会触发这个恢复。

G4 在 `-RequireSemanticButtons` 或请求语义点击时还会在既有预算内等待 fresh、唯一、
actionable 的目标，避免 re-entry 后 observer 已恢复但 UGUI 尚未填充的合法空帧竞态。
这不会放宽点击条件，也不会在等待中输入。

本地导入旧资源基底时使用：

```powershell
powershell -ExecutionPolicy Bypass `
  -File scripts/windows/manage-redroid-wsl-local-dev.ps1 -Action Stop -Profile Project
wsl -d Ubuntu-22.04 -u root -- bash `
  /mnt/h/program/AzurLaneAutoScript-Headless-redroid-x86_64/scripts/wsl/copy-local-game-resource-base.sh `
  /mnt/h/program/AzurLaneAutoScript-Headless-localdata/game-cn-9.7.10-files/files `
  /home/helenanana/.local/share/alas-redroid/projectlocal-data/media/0/Android/data/com.bilibili.azurlane/files
```

脚本要求 Project 容器已停止，最多八路处理互不重叠的一级目录，不执行 `--delete`，并恢复
Android owner/mode。旧基底不是完成证据；启动后仍由游戏完成 server version、hash、split、
下载、失败计数和最终版本验证。

资源点击前还必须确认 InputDispatcher focused window 是游戏，而不只是 Activity 前台。
Project manager 会在 Android boot 后设置并读回 `immersive_mode_confirmations=confirmed`，
防止首次沉浸提示截获 typed-derived tap。这项状态只解决已观察到的系统 UI blocker，不放宽
包/PID、freshness、唯一 path、raycast-top 或 postcondition 条件。

## 11. 日常管理

查看项目实例：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/windows/manage-redroid-wsl-local-dev.ps1 -Action Status -Profile Project
```

停止项目实例：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/windows/manage-redroid-wsl-local-dev.ps1 -Action Stop -Profile Project
```

仅验证官方 stock Redroid：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/windows/manage-redroid-wsl-local-dev.ps1 -Action Start -Profile Stock
adb connect 127.0.0.1:5555
```

启动已验证的 API 31 游戏链路：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/windows/manage-redroid-wsl-local-dev.ps1 -Action Start -Profile Api31
adb connect 127.0.0.1:5557
```

Stop 不会删除容器或 `/data`。若三个 profile 中仍有一个运行，keepalive 会继续保留；
只有三个受管实例都停止后才结束 keepalive。

## 12. 常见故障

### `binder filesystem is unavailable`

当前 WSL 没有启动自定义内核。检查 `.wslconfig` 路径、运行 `wsl --shutdown`，再核对：

```bash
uname -r
grep binder /proc/filesystems
```

### `module not found` 或 vermagic 不匹配

`kernelModules` 仍指向旧 modules.vhdx，或 modules.vhdx 使用了不同 `kernelrelease`。
重新生成匹配模块盘，不要关闭 modversion 检查来绕过。

### Redroid 在命令结束后消失

Ubuntu WSL 可能在最后一个 Windows 侧 `wsl.exe` 客户端结束后自动关机，Docker 和
Redroid 会一起停止。使用 Windows manager 启动，不要只运行一次短命的
`wsl -d ... docker start ...`。manager 会保留隐藏 keepalive。

### `docker-credential-desktop.exe` 不存在

Ubuntu 自己的 Docker CLI 配置可能残留 Docker Desktop credential helper。manager 使用：

```text
$HOME/.config/alas-redroid/docker
```

作为隔离的 Docker client config，不修改用户原有 `~/.docker/config.json`。

### ADB 端口连接被拒绝

依次确认：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/windows/manage-redroid-wsl-local-dev.ps1 -Action Status -Profile Project
Test-NetConnection 127.0.0.1 -Port 5556
adb connect 127.0.0.1:5556
```

不要把端口改成 `0.0.0.0` 作为排错手段。

### Project 候选目录或 OCI 缺失

恢复经过哈希验证的本地候选包，或用 `-ProjectArtifactDirectory` 指向另一份完整候选；
也可临时使用 `-Profile Stock` 验证宿主。不要从 `artifacts/incomplete-transfers` 中的
未完成 OCI 冒充完整制品，也不要依赖另一个 Git worktree 的 ignored artifact 目录。

## 13. 回滚

先停止本地实例：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/windows/manage-redroid-wsl-local-dev.ps1 -Action Stop -Profile Project
powershell -ExecutionPolicy Bypass -File scripts/windows/manage-redroid-wsl-local-dev.ps1 -Action Stop -Profile Stock
powershell -ExecutionPolicy Bypass -File scripts/windows/manage-redroid-wsl-local-dev.ps1 -Action Stop -Profile Api31
```

把先前备份恢复为 `.wslconfig`，然后关闭 WSL：

```powershell
Copy-Item -LiteralPath "$env:USERPROFILE\.wslconfig.pre-redroid-<timestamp>.bak" -Destination "$env:USERPROFILE\.wslconfig" -Force
wsl --shutdown
```

不要删除 `projectlocal-data`、旧 `projectdev-data` 或 `localdev-data` 来回滚内核。内核回滚和 Android userdata
删除是两件不同的事。

## 14. 支持声明边界

本地 WSL 结果可以支持这些声明：

- Binder/BinderFS 自定义 WSL 内核可启动；
- Docker/cgroup/overlayfs 在换核后仍工作；
- stock、项目和 API 31 Redroid 可以到达 boot completed；
- Windows loopback ADB 可达；
- 项目镜像组件哈希匹配；
- host-directory `/data` 在容器重启后保留。
- API 31 上游戏可通过 typed observer 到达 `LoginUI2(Clone)` 和空登录边界。

本地 WSL 结果不能支持这些声明：

- 项目 AWS/原生 Linux qualification 已被 WSL 取代；
- 仅凭空 Redroid 启动就证明游戏、ANGLE NULL、Unity observer 或 ALAS 主链稳定。

游戏登录验证继续遵守项目边界：没有明确授权时停在空登录界面并保留
`Accounts: 0`，不得录入账户数据。

## 15. 从统一 runtime backend 使用本地 Project

本地宿主配置沿用 `backend: redroid`，增加 `container_engine: wsl-docker`。
`WslRedroidBackend` 复用现有 Redroid 的游戏冷启动、ADB、observer、重启顺序和
清理所有权，只把 containerd 宿主操作换成本地 WSL Docker 和 Project manager。
原 containerd 配置继续使用原路径，不需要修改 ALAS 补丁。

导出当前候选对应的配置：

```powershell
& scripts/windows/manage-redroid-wsl-local-dev.ps1 -Action Config -Profile Project |
    Set-Content -Encoding utf8 artifacts/redroid-wsl-runtime-config.json
```

配置中的 serial、容器、镜像和 userdata 来自当前 Project profile。执行前仍会核对
Docker 的实际绑定；不会把文档示例 serial 当成当前设备。Docker 显式连接该 WSL
发行版的 `/var/run/docker.sock`，避免环境变量或 context 把调用送到其他 daemon。

登录前生命周期验证使用：

```powershell
$env:PYTHONPATH = 'python'
python scripts/python/qualify_redroid_wsl_prelogin.py `
    --config evidence/redroid-wsl-runtime-20260907-r1/runtime-config.json `
    --lock evidence/redroid-wsl-runtime-20260907-r1/runtime-lock.json `
    --output evidence/redroid-wsl-runtime-new-run --execute
```

以上 lock 对应此次本地候选与保留的资源收据；更换候选时应重新捕获身份，不能继续
宣称旧 lock 的资格。脚本要求初始处于已确认的空手机号页，依次通过统一 backend
验证冷启动、游戏进程重启和容器重启。每轮检查新鲜、递增且 coherent 的语义帧，
随后只读检查原生 SDK 登录页的空输入、disabled 下一步与 `Accounts: 0`。
`account-input-required` 不会被转换为 `observer_ready=true`，也不会提交登录。

SDK 暂停恢复只针对 MainActivity、同一 PID、已观测的 Announcement 暂停历史和
stale/unavailable observer，且该游戏 PID 没有 fatal；每次冷启动最多一次
HOME→带 `-force-gfx-st` 的 MainActivity re-entry，再验证同 PID 和新鲜递增帧。
无关 Activity、仍健康的 observer、fatal 或身份变化不触发该恢复。

此次接入修复了两个宿主脚本问题：

- 重复 `install -d -m 0700` 会改窄运行中 `/data` 的权限，使新游戏进程无法读取 APK。
  现在仅首次创建目录时设为 0700，已有目录交给 Android init 管理。该镜像
  `/system/etc/init/hw/init.rc` 明确使用 `system:system`、`0771`。
- 保活子进程继承调用方输出句柄会让捕获输出的 Start 长时间不返回。现在通过
  `UseShellExecute=true`、`WindowStyle=Hidden` 独立启动保活进程。

结果见 `docs/redroid-wsl-runtime-20260907.zh-CN.md`。这些检查覆盖本地登录前生命周期，
不代表账号登录、ALAS 任务、镜像回滚、长期 soak 或原生 Linux 已通过资格验证。

## 16. 保留原数据的受控镜像回滚演练

2026-09-07 已新增并实机通过 current→受控候选→current 的 overlay 演练。
原 Project 停止后作为只读底层，临时写层只产生约 24 MiB 的采样占用；候选
userdata 写入和镜像诊断文件在回滚后均消失。原 Project 随后恢复，临时容器、
挂载、目录与连接均清理，资源 `9.7.356` 和空登录边界保留。

完整命令、失败样本与支持范围见
[本地镜像回滚演练](redroid-wsl-rollback-20260907.zh-CN.md)。缓存的旧 FBE 镜像
不能用于当前 host-directory 数据；受控候选 PASS 不代表真实版本回退已资格化。

## 17. 独立账号实例与原 ALAS 实跑

Project manager 支持命名实例。默认仍是 `projectlocal` / 5556；例如独立的
`gameplay` 使用 `alas-redroid-wsl-gameplay`、`gameplay-data` 和 5558。实例名只允许
小写字母开头的小写字母、数字和连字符，不能作为任意宿主路径。

```powershell
& scripts/windows/manage-redroid-wsl-local-dev.ps1 -Action Start -Profile Project `
    -ProjectInstance gameplay -ProjectAdbPort 5558
& scripts/windows/manage-redroid-wsl-local-dev.ps1 -Action Config -Profile Project `
    -ProjectInstance gameplay -ProjectAdbPort 5558 |
    Set-Content -Encoding utf8 artifacts/redroid-gameplay-runtime-config.json
```

统一 backend 会把实例和端口传回同一个 manager，并核对实际容器、userdata、镜像和
ADB 绑定后才执行 Start/Stop。容器带有 manager 标签；只要其他受管实例仍在运行，
停止一个实例就不会结束共享 WSL 保活。已有 userdata 根权限继续由 Android init 管理。

已有账号迁移应在源容器停止后保存独立副本，保留源目录。不要让两个实例共用可写
userdata，也不要同时登录同一个游戏账号。临时 overlay 验证成功后，可在源停止、
overlay 只读挂载时保留完整独立目录；卸载 overlay 后再启动命名实例。

账号实例继续使用原 ALAS 配置、任务与调度。为验证复制配置时关闭错误截图与外发
通知，并限定本次原生任务次数。APK 的 `driver_revision` 可能相同而 observer 内容
不同；部署需保留实际 APK 哈希和可回退副本，并以任务所需 typed 能力确认可用性。
不能用旧 APK 缺少的 raycast 信息作为放宽输入边界的理由。

2026-10-22 的首轮实跑见
[本地 Redroid 账号任务验证](redroid-gameplay-20261022.zh-CN.md)；Windows 提交内存、
AVD 2 GB 流量上限、原 ALAS 动画等待及后续补验见
[完整任务与 AVD 对照](redroid-completion-20261022.zh-CN.md)。
