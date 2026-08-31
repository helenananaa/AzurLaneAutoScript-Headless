# 在 Windows WSL2 本地运行 Redroid

这份教程记录一条已经在本项目实机跑通的低成本路径：在 Windows WSL2 中使用带
Binder/BinderFS 的自定义 Microsoft WSL 内核，启动 stock Redroid 或本项目自维护的
x86 Redroid 镜像，并从 Windows 通过 ADB 访问它。

它适合日常开发和调试：Redroid 启动、ADB、应用安装、ANGLE NULL、observer、ALAS
适配、容器重启和宿主目录 `/data` 持久化。它不能替代最终的兼容 Linux/AWS
运行资格验证。

## 1. 已验证结果

2026-08-31 的本机验证结果：

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

当前仓库提供三个相互隔离的 profile：

| Profile | 用途 | ADB | `/data` |
|---|---|---|---|
| `Project` | 本项目自维护 x86 镜像，默认选择 | `127.0.0.1:5556` | `projectdev-data` |
| `Stock` | 官方 Android 14 x86_64-only 宿主冒烟 | `127.0.0.1:5555` | `localdev-data` |
| `Api31` | 官方 Android 12/API 31 游戏与登录前链路基线 | `127.0.0.1:5557` | `api31-game-data` |

三个 profile 都只把 ADB 发布到 loopback，不会监听局域网或公网。当前本地游戏链路
优先使用 `Api31`；`Project` 仍用于项目 Android 14 镜像的构建、启动和 observer 开发，
其全新 userdata 上的 SDK 首次启动 Activity 会暂停 Unity，尚不能替代 `Api31` 的登录前基线。

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
3. 校验项目 OCI 压缩包 SHA-256 和导入后的 image ID；
4. 创建独立的 `projectdev-data`；
5. 只把 ADB 发布到 `127.0.0.1:5556`；
6. 等待 `sys.boot_completed=1`，超时或容器退出时明确失败。

项目 profile 依赖仓库中的留存制品：

```text
artifacts/transfer-cache/20260830-redroid-no-storage-overlay-r1/redroid-x86_64.oci.tar.zst
```

若该制品没有随仓库/制品包保留，启动器会 fail closed。此时可以先使用 Stock profile
验证宿主，但不能把 stock 结果冒充项目镜像结果。

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

### Project OCI archive 缺失

恢复经过哈希验证的制品包，或临时使用 `-Profile Stock` 验证宿主。不要从
`artifacts/incomplete-transfers` 中的未完成 OCI 冒充完整制品。

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

不要删除 `projectdev-data` 或 `localdev-data` 来回滚内核。内核回滚和 Android userdata
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
