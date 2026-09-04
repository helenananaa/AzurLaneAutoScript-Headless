# KVM Android 镜像到登录页完整验证与缺陷修复报告

> 历史状态说明：第 1 至 12 节记录的是 2026-08-26 早期仍共享 AOSP source、`.repo`
> metadata 和 ccache 的迁移期验证现场。路径、服务名和“当前”措辞都只描述该次验证，
> 不是现行构建入口或正式运行资格。现行双 build-domain 状态见第 13 节。

本文档记录 2026-08-26 在共享付费 Android 构建服务器上完成的 KVM
Android Emulator 资格过程。目标是验证国服《碧蓝航线》能够在 x86_64 guest 中：

1. 通过独立 KVM 镜像启动；
2. 使用 ANGLE NULL observer 产生新鲜的类型化 Unity 状态；
3. 打开并同意隐私协议；
4. 选择并下载全部游戏资源；
5. 最终到达可操作的 `LoginUI2` 登录页。

结论按证据范围表述：**以上五项目标均已通过。** 最终游戏自行报告完成
`28.1GB`、`90472` 个文件的资源更新，observer 随后连续识别到登录页、当前服务器、
版本文本和活动按钮。验证没有输入账号、没有登录服务器，也没有执行 ALAS 任务；因此
结果是“游戏登录前链路和 typed observer 已通过”，不是生产 ALAS 支持声明。

## 1. 验证边界与原则

- KVM 与 Redroid 共用 AOSP 源码、下载缓存和 ccache，但使用独立输出、证据、运行时、
  userdata 和回退点。
- 服务器约 CNY 40/天。本轮复用保留源码和构建状态，没有重新全量下载 AOSP，也没有
  为了形式完整而执行 clean rebuild 或重复构建。
- 游戏通过 ANGLE NULL 运行时，游戏 framebuffer/ADB screenshot 为黑色是预期行为。
  游戏内导航、进度和验收仅使用 typed observer、WebView DOM、Android 包/进程状态和
  文件系统证据。
- 隐私协议是 Android WebView，不属于 Unity observer。本轮通过 WebView DevTools DOM
  唯一定位 `div.agree`，没有使用截图坐标点击。
- 没有清空旧 AVD、复制旧账号同意状态、覆盖旧 userdata 或删除共享源码。失败实例与
  关键中间证据被保留，只有已确认无价值的临时转换文件被移除。

## 2. 最终环境与身份

以下 SSH 入口是本次历史验证的运行身份。该 22022/43676 服务器现已到期，不得把这些命令
当作当前操作入口；对应源码/证据回退以本地已校验留存为准。

| 项目 | 最终值 |
|---|---|
| 主 SSH | `ssh -p 22022 weipa@47.110.157.178` |
| 备用 SSH | `ssh -p 43676 weipa@weipa.k9.luyouxia.net` |
| 共享 AOSP 源码 | `/srv/android-build/src/redroid-14-r75` |
| KVM 仓库副本 | `/srv/android-build/src/AzurLaneAutoScript-Headless-kvm-image-optimization` |
| KVM 独立输出 | `/srv/android-cache/out/kvm-14-r75-x86_64` |
| KVM 独立证据 | `/srv/android-archive/evidence/kvm` |
| 最终 AVD | `alas-headless-kvm-r75-x86_64-v3` |
| 最终 ADB transport | `127.0.0.1:5601` |
| guest | Android API 34，x86_64，SELinux Enforcing |
| 显示与 userdata | 1280×720，48G 配置，guest `/data` 约 47G 可用容量 |
| 游戏 | `com.bilibili.azurlane`，`versionCode=9710`，`versionName=9.7.10` |
| Activity | `com.manjuu.azurlane.MainActivity` |
| observer provider | `org.chromium.angle`，x86_64，debug ANGLE provider |
| observer driver revision | `506b76f698b5089aaa29c4e7908b48edb8532a44` |

`127.0.0.1:5601` 是本次实例的实际 transport，不是应写死的通用 serial。运行器必须
发现并绑定本次启动的精确设备。由于本次 console port 位于 Emulator 常用自动发现
区间之外，ADB 需要显式 `connect`。

## 3. 历史共享和隔离布局（已退役）

本轮采用以下边界：

```text
/srv/android-build/src/redroid-14-r75       shared: retained AOSP source
/srv/android-cache/ccache/alas-headless/aosp-14-r75
                                             shared: compiler cache
/srv/android-cache/out/redroid-*            isolated: Redroid output
/srv/android-cache/out/kvm-*                isolated: KVM output
/srv/android-archive/evidence/redroid       isolated: Redroid evidence
/srv/android-archive/evidence/kvm           isolated: KVM evidence
/srv/android-runtime/redroid                isolated: Redroid instances/userdata
/srv/android-runtime/kvm                    isolated: KVM AVDs/userdata
```

KVM 构建需要暂时撤销共享树里只适用于 Redroid 容器的源码修改。构建器在全局 build
lock 内完成以下动作：

1. 校验共享源码 lock 和每个项目的精确 HEAD；
2. 校验 overlay patch SHA-256；
3. 校验共享树中已保留的 dirty preimage；
4. 临时应用 KVM overlay；
5. 使用独立 `OUT_DIR` 增量构建；
6. 无论成功或失败都恢复共享源码；
7. 复核恢复后的 preimage 和工作树状态；
8. 生成 KVM 独立 manifest。

这样既复用昂贵的下载和编译缓存，又不会把 KVM 专用改动留给 Redroid 后续构建。

## 4. 完整验证过程

### 4.1 服务器预检和增量构建

连接后先验证实际宿主身份、RAM、磁盘、KVM、cgroup、活跃构建进程、共享源码状态和
现有制品，不能仅凭供应商规格继续。确认 retained source、ccache 和上一轮产物可用后，
使用仓库化构建入口：

```bash
cd /srv/android-build/src/AzurLaneAutoScript-Headless-kvm-image-optimization

./scripts/wsl/build-kvm-image.sh \
  integration/runtime/android-backend-layout.example.json \
  integration/runtime/android-image-source-lock.example.json \
  integration/runtime/kvm-image-build-profile.example.json
```

最终 loader 修复后的 KVM 增量构建约耗时 2 分 10 秒。没有重新 `repo sync` 全量代码，
也没有删除共享 `out` 或 ccache。最终构建 manifest：

```text
/srv/android-archive/evidence/kvm/kvm-angle-loader-fix-20260826T012900Z/manifest.json
```

前一轮 Goldfish Binder 修复也有独立证据：

```text
/srv/android-archive/evidence/kvm/kvm-goldfish-binder-fix-20260826T010038Z/manifest.json
```

### 4.2 新建 48G AVD

旧 AVD 虽已把 `config.ini` 改为 48G，但既有 ext4 文件系统仍只有约 10G，不能满足
完整资源下载。为了保留旧 userdata 和避免不可靠的在线扩容，本轮创建新 AVD：

```bash
./scripts/wsl/provision-kvm-avd.sh \
  /srv/android-cache/out/kvm-14-r75-x86_64/target/product/emu64x/emulator/x86_64 \
  /srv/android-runtime/kvm/alas-headless/avd \
  alas-headless-kvm-r75-x86_64-v3
```

新建实例首次格式化后，guest `/data` 显示约 47G 容量，满足完整资源链。旧 AVD 及其
扩容前备份继续保留：

```text
/srv/android-runtime/.../userdata-qemu.before-fs-resize-20260826T0959.qcow2
```

### 4.3 启动 Emulator

最终成功实例使用 SwiftShader guest 系统图形，但关闭 Emulator 的 Vulkan feature：

```bash
./scripts/wsl/run-kvm-avd.sh \
  /srv/android-build/src/redroid-14-r75/prebuilts/android-emulator/linux-x86_64/emulator \
  /srv/android-runtime/kvm/alas-headless/avd \
  /srv/android-runtime/kvm/alas-headless/sdk \
  alas-headless-kvm-r75-x86_64-v3 \
  5600
```

仓库脚本保持前台运行，便于外部 supervisor 准确管理 PID 和退出状态。验证现场使用
transient systemd unit `alas-kvm-v3.service` 托管等价命令。关键参数是：

```text
-no-window -no-audio -no-snapshot -no-snapshot-save
-gpu swiftshader_indirect
-feature -Vulkan
```

`-feature -Vulkan` 只关闭 Emulator guest Vulkan 路径；游戏 GLES 仍单独路由到
ANGLE NULL observer。

### 4.4 固定 ADB 客户端并安装 ANGLE observer

宿主同时存在 ADB 1.0.39 和 AOSP ADB 1.0.41。必须统一使用共享 AOSP 树中的新客户端：

```bash
ADB=/srv/android-build/src/redroid-14-r75/prebuilts/runtime/adb
$ADB connect 127.0.0.1:5601
$ADB -s 127.0.0.1:5601 wait-for-device
```

observer APK 使用保留 ANGLE 源码做一次 x86_64 focused build，耗时约 46 秒，不需要
重新下载 AOSP：

```text
/srv/android-archive/apks/alas-headless/AngleLibraries-observer-x86_64-login-bootstrap-fix-20260826.apk
SHA-256 d94d448c1a41544c6b991ff345b746a6b8efd0a932239c2a0dcb79bbc3cd81d6
```

安装和路由通过仓库脚本完成：

```bash
./scripts/wsl/install-kvm-angle-observer.sh \
  "$ADB" \
  127.0.0.1:5601 \
  /srv/android-archive/apks/alas-headless/AngleLibraries-observer-x86_64-login-bootstrap-fix-20260826.apk \
  com.bilibili.azurlane
```

脚本使用 `adb install -r -d --force-queryable`，并设置：

```text
angle_debug_package=org.chromium.angle
angle_gl_driver_selection_pkgs=com.bilibili.azurlane
angle_gl_driver_selection_values=angle
show_angle_in_use_dialog_box=0
```

### 4.5 安装并启动游戏

游戏 APK 保留在服务器归档区，不进入 Git：

```text
/srv/android-archive/apks/alas-headless/azurlane-cn-9.7.10-base.apk
size=1732663571 bytes
```

安装后确认精确包名、版本、ABI 和 Activity，再启动游戏。最终实例还预先确认 Android
一次性沉浸模式提示，避免系统 UI 覆盖游戏：

```bash
$ADB -s 127.0.0.1:5601 shell settings put secure immersive_mode_confirmations confirmed
$ADB -s 127.0.0.1:5601 shell am start -n \
  com.bilibili.azurlane/com.manjuu.azurlane.MainActivity
```

### 4.6 同意隐私协议

首次启动进入：

```text
com.base.gsc_agreement_library.AgreementWebActivity
```

该页面是 WebView，不应从黑 framebuffer 猜测坐标。验证过程将游戏进程的
`webview_devtools_remote_2423` 转发到临时本地端口，通过 Chrome DevTools Protocol
读取 DOM，并要求：

- 可见的 `div.agree` 恰好一个；
- 元素不是 disabled；
- 点击调用成功；
- 点击后 Activity 返回 `MainActivity`。

实际 DOM 操作返回：

```json
{"clicked":true,"count":1,"className":"agree"}
```

临时 DevTools forward 在完成后移除。没有复制旧 AVD 的 consent preference，也没有
清空游戏数据来反复试验。

### 4.7 选择并下载全部资源

进入 Unity 资源选择界面后，所有判断来自 `/v1/ui` 的类型化路径、文本和按钮状态。
本轮选择：

| 资源 | 游戏显示大小 |
|---|---:|
| 主完整资源 | 16.8GB |
| MAP | 2.1GB |
| DORM | 3GB |
| MANGA | 102.7MB |
| GALLERY_PIC | 34.2MB |
| L2D | 2.6GB |
| CV | 3.5GB |

游戏最终汇总为 `28.1GB`、`90472` 个文件。监控过程中持续检查：

- 游戏前台 package/activity/PID；
- observer `status=ok`；
- generation 持续推进且 frame 新鲜；
- download progress 文本递增；
- failed count 始终为 0；
- `/data` 和游戏外部数据目录可用空间。

完成时 typed 文本变为：

```text
更新完成，正在进入游戏...
```

资源目录最终约 29G：

```text
/storage/emulated/0/Android/data/com.bilibili.azurlane
```

guest `/data` 最终约 47G 总量、30G 已用、16G 可用，使用率约 65%。

### 4.8 登录页验收

资源处理完成后，observer 连续两个 generation 均识别到登录页。最终代表性快照：

| 字段 | 结果 |
|---|---|
| observer status | `ok` |
| package | `com.bilibili.azurlane` |
| PID | `2423` |
| ABI | `x86_64` |
| frame | 1280×720，`flags=15`，Unity main thread |
| generation | 1400，后续复核 1420 |
| frame age | 1287ms，后续复核 218ms |
| Button | 109 个，活动 11 个 |
| UI version text | `ver 9.7.328` |
| current server text | `点击更换` |

关键语义路径包括：

```text
UICamera/Canvas/UIMain/LoginUI2(Clone)
UICamera/Canvas/UIMain/LoginUI2(Clone)/adapt/current_server/Text
```

这证明登录页不是一张偶然出现的画面：精确包/PID、连续新鲜 generation、Unity 主线程
状态、登录页根节点和可操作控件同时成立。

## 5. 缺陷、根因与修复

### 5.1 KVM 继承了 Redroid 专用源码修改

**现象：** 直接复用 Redroid qualified 源码构建 Emulator 时，first-stage mount、
SELinux、Binder 和 EGL loader 行为不符合标准 Goldfish/KVM 环境。

**根因：** retained tree 中存在仅适用于 Redroid 容器的修改。共享源码不等于两种
runtime 可以共享同一套最终 patch 状态。

**修复：** KVM overlay 在 build lock 内分别恢复：

- `system/core` 标准 first-stage mount；
- `external/selinux` 标准 SELinux enforcement path；
- `frameworks/native` Goldfish Binder/security-context 行为；
- `frameworks/native/opengl/libs/EGL/Loader.cpp` 标准 ANGLE library name。

最终 guest `getenforce` 为 `Enforcing`。overlay 只存在于 KVM 构建窗口，结束后恢复
Redroid retained preimage。

### 5.2 EGL loader 仍查找 Redroid 私有库名

**现象：** ANGLE provider 已安装，但 KVM guest 的 loader 仍尝试 Redroid 使用的
`lib{kind}_alasx.so`，observer 不能按标准 Android ANGLE provider 方式加载。

**根因：** `frameworks/native/opengl/libs/EGL/Loader.cpp` 的 Redroid patch 被共享树保留。

**修复：** KVM overlay 恢复 `lib{kind}_angle.so`。更新后的 overlay patch SHA-256：

```text
dd774cd6dd5d200070ae55dac7d663d7480c1a06736bc8efe9f145245d2e198e
```

构建器同时钉住 retained dirty preimage：

```text
9b32188180beaa462de8ee022d053d776d60893d1de9fd4897ffdc7deb717790
```

### 5.3 两个 ADB 版本互相杀 server

**现象：** Emulator 已启动，但 transport 间歇消失；连接命令有时显示 device，下一条
命令又 offline 或无设备。

**根因：** 系统 ADB 1.0.39 与 AOSP ADB 1.0.41 交替启动/终止同一个 host server。

**修复：** 全流程固定为：

```text
/srv/android-build/src/redroid-14-r75/prebuilts/runtime/adb
```

并显式 `adb connect 127.0.0.1:5601`。在有其他 Android 工作负载的共享服务器上，
还应通过每条命令的 `adb -P <dedicated-port>` 或环境变量
`ANDROID_ADB_SERVER_PORT=<dedicated-port>` 使用独立 host server；`ADB_SERVER_PORT`
不是有效的隔离变量。不把文档示例 serial 当成实际设备身份。

### 5.4 修改 AVD 配置没有扩大既有 ext4

**现象：** `config.ini` 已写 48G，qcow2 virtual size 也显示 48G，但 guest `/data`
仍只有约 10G，游戏下载器报告空间不足/`neterror`。

**根因：** 既有 overlay 的 backing image 和 ext4 superblock 仍是 10G。配置和虚拟块设备
容量扩大不等于 guest 文件系统已经扩大。

**失败尝试：**

- 为游戏外部目录挂载 36GB 独立 raw disk；文件可写，但游戏的
  `OSUtils:CheckFreeDiskspaceEnough()` 仍按 `/data` 的约 7862MB 判断，不能绕过；
- 在线 `resize2fs` 返回
  `Invalid argument While trying to add group #81`；文件系统 block count 没有变化；
- recovery 模式没有可用 ADB，无法安全执行离线扩容。

**修复：** 不清空旧 AVD，创建新的 48G v3 AVD，让首次启动按目标容量格式化 ext4。
新 guest `/data` 约 47G。额外 resource disk 随后移除，因为它不是根因也不再需要。

### 5.5 Emulator 在游戏启动时 SIGSEGV

**现象：** 新 AVD 能完成 Android boot，但启动游戏时 qemu 进程崩溃。更换 nohup、
systemd-run 或父进程没有消除故障。

**排除：** 宿主约 187GiB RAM、约 178GiB 可用；没有 OOM 或 cgroup kill 证据。

**根因证据：** GDB 在正确放行 SIGUSR1/SIGUSR2/SIGPIPE 后得到栈：

```text
goldfish_vk::reservedunmarshal_VkPhysicalDeviceFeatures2(...)
libOpenglRender.so
```

**修复：** 保持 `-gpu swiftshader_indirect`，增加 `-feature -Vulkan`。尝试 `-gpu host`
因服务器无 DISPLAY/EGL display 失败，不作为方案。最终 v3 在关闭 guest Vulkan 后稳定
完成隐私协议、28.1GB 下载和登录页验收。

### 5.6 已安装 ANGLE provider 仍被报告为“未安装”

**现象：** `pm path org.chromium.angle` 可见 APK，包也为 DEBUGGABLE/x86_64，但游戏日志：

```text
ANGLE debug package 'org.chromium.angle' not installed
```

**根因：** Android package visibility。`GraphicsEnvironment` 从游戏进程调用
`PackageManager.getApplicationInfo(anglePkgName, 0)` 时得到 `NameNotFoundException`，
不是 APK 真正缺失。

**修复：** 使用：

```text
adb install -r -d --force-queryable
```

修复后日志不再出现“not installed”，`ALAS_G3` observer socket/ready 正常发布。该参数
已固化进 `install-kvm-angle-observer.sh`。

### 5.7 v2 首次初始化状态异常

**现象：** v2 在此前 EGL/qemu 崩溃阶段启动过游戏，SDK 的 `config_data` 为空，协议
页面没有完成正常 publish，只能看到路由订阅。

**风险：** 直接复制旧 AVD 的 `initial_agreement_tag=1` 会跳过真实隐私页面验证；清空
游戏数据则属于破坏性操作，而且不能证明一台干净机器可完成首次初始化。

**修复：** 保留 v2 做诊断，创建干净 v3。v3 正常打开 `AgreementWebActivity`，随后用
唯一 DOM 目标同意协议。旧 consent 没有被移植。

### 5.8 进程托管方式一度掩盖真实退出原因

**现象：** `nohup` 运行的 Emulator 退出后，远端 shell/父进程状态不够清晰，容易把
qemu 崩溃误判为 SSH 生命周期问题。

**修复：** 调试阶段使用 transient systemd unit 获取 PPID=1、MainPID 和准确退出码；
定位根因后，仓库脚本保持 `exec` 前台模型，由调用方/supervisor 管理，不自行 daemonize。

## 6. 失败尝试如何处理

本轮没有为了“重新来一次”而删除全部产物：

- 旧 10G AVD 保留，避免丢失原 userdata；
- 在线扩容前 qcow2 备份保留；
- v2 保留为首次初始化异常的诊断样本；
- KVM Binder 和 loader 两轮 manifest 分开保留；
- 已确认无继续价值的临时 raw 转换文件被移除；
- 共享 AOSP、ccache、Redroid 输出和 APK 归档均未清理。

这个处理既保留回退和诊断证据，也避免付费服务器进行无意义的全量下载/重编译。

## 7. 本轮固化到仓库的实现

与本报告直接相关的实现包括：

- `python/alas_headless/android_backend_layout.py`：共享/隔离目录合同；
- `python/alas_headless/android_kvm_image.py`：KVM 构建 profile 合同；
- `integration/runtime/android-backend-layout.example.json`：服务器布局；
- `integration/runtime/kvm-image-build-profile.example.json`：KVM product、输出和 overlay；
- `integration/runtime/kvm.shared-server.config.example.json`：共享服务器配置示例；
- `integration/runtime/patches/`：KVM-only source overlays；
- `scripts/wsl/provision-shared-android-layout.sh`：共享服务器目录准备；
- `scripts/wsl/build-kvm-image.sh`：带锁、preimage 校验和恢复的增量构建；
- `scripts/wsl/provision-kvm-avd.sh`：独立 48G、1280×720 KVM AVD；
- `scripts/wsl/run-kvm-avd.sh`：前台 Emulator 运行器及 Vulkan workaround；
- `scripts/wsl/install-kvm-angle-observer.sh`：queryable observer 安装和 ANGLE 路由；
- 对应 Python、shell 合同与 focused tests。

## 8. 仓库验证结果

最终 focused regression：

```powershell
$env:PYTHONPATH = 'python'
python -m pytest -q `
  tests/test_android_backend_layout.py `
  tests/test_android_kvm_image.py `
  tests/test_kvm_image_build_script.py `
  tests/test_kvm_avd_provision_script.py `
  tests/test_kvm_runtime_scripts.py `
  tests/test_runtime_backends.py
```

结果：

```text
26 passed in 0.55s
```

三个配置验证器均通过：

| 验证器 | 输出 SHA-256 |
|---|---|
| backend layout | `0ec1640a09e005d857f170f5d7c0b1f70c67a57cb547fa381c182383f9424c25` |
| Android image source lock | `4f35a668918d92b50a0d77d4dd4970fc491d4f26242ccf3bcc9df06868d1a940` |
| KVM build profile | `24f8ea27e734362046140e630300188126a9e7bed96a32658400c3e9a83aa2c4` |

此外，变更脚本通过 `bash -n`，工作树通过 `git diff --check`。

## 9. 成本、停止条件与该次验证的保留状态

本轮远端成本控制结果：

- 复用 retained AOSP tree，无全量代码下载；
- 复用 ccache 和独立 KVM OUT，最终镜像修复构建约 2 分 10 秒；
- observer focused build 约 46 秒；
- 不执行不控制当前决策的 clean rebuild、第二独立构建或双 ABI；
- 下载期间按 typed progress 监控，没有因短时不变化重复点击或重启；
- 达到登录页并取得连续新鲜 observer 证据后停止，不继续登录账号或扩展任务范围。

验证完成时 v3 仍由 `alas-kvm-v3.service` 运行，便于复核该次结果。该 transient unit
属于服务器现场状态，不是仓库声明的持久部署服务。后续释放服务器前应先归档仍需保留的
manifest、日志和 AVD 回退点，再停止 unit；不要顺手清理 Redroid 共用源码和缓存。

## 10. 回退点与重新进入条件

发生回归时按最窄边界处理：

- **镜像构建失败：** 保留独立 KVM OUT 和日志，先确认 overlay/preimage/共享 build
  lock；在该历史布局下不要删除共享源码或 ccache。
- **Emulator 启动失败：** 检查 qemu 退出码和 `libOpenglRender` 栈，确认仍带
  `-feature -Vulkan`；不要先重建 Android。
- **ANGLE provider 不可见：** 核对精确包、ABI、`--force-queryable` 和四项 global
  settings；不要回退到截图或坐标输入。
- **observer 不新鲜：** 核对精确 foreground package/activity/PID、socket、generation
  和 age；不满足时停止游戏输入。
- **隐私页面不出现：** 先区分 Unity Activity、Agreement WebView 和系统 UI；不得复制
  旧 consent 来伪造首次初始化通过。
- **资源空间不足：** 同时检查 AVD 配置、qcow2 chain、guest block size、ext4 size 和
  游戏实际检测的 filesystem。只有新建 AVD 不会丢失需要保留的状态时才采用该路径。
- **游戏下载失败：** 保留 failed count、typed progress、可用空间和网络错误；失败未被
  解释前不要反复点击或重新下载 28.1GB。

重新宣称本路径通过时，至少应重新取得：精确游戏/observer 身份、ANGLE NULL ready、
隐私 DOM 唯一操作、资源失败数为 0、下载完成文本，以及两个连续新鲜的 `LoginUI2`
generation。仅有黑屏、进程存活、APK 安装成功或一份旧快照都不够。

## 11. 尚未覆盖的工作

本报告没有证明：

- 账号登录、选服和主页面；
- ALAS 配置、任务 admission、战斗或日常任务；
- 重启后的资源/隐私/userdata 持久化复核；
- observer/action postcondition 的完整 ALAS 接线；
- 长期运行、恢复、soak、密度或性能结论；
- ARM64 KVM/Redroid 的等价结果；
- release-grade clean rebuild 或第二独立构建。

下一阶段应直接从保留的 v3 登录页状态进入账号登录前的配置复核，取得用户对账号/凭据
边界的明确授权后再继续；不应为了补齐次要形式材料重新下载或全量构建该次已通过的镜像。

## 12. 第二实例复现记录

2026-08-26 11:37 至 12:20 对“新开一个 KVM，再次到达登录页”进行了追加验证。
本节不覆盖前文结论：v3 的首次完整链路仍然通过；本节单独记录第二实例能否独立复现。

### 12.1 宿主复核

追加验证开始时：

- KVM device 可用；
- 宿主 187GiB RAM，约 172GiB 可用；
- runtime 盘剩余约 191G；
- cache 盘剩余约 149G；
- archive 盘剩余约 2.8T；
- 只有 v3 Emulator 在运行，load average 约 `0.96/1.03/1.67`。

因此没有停止 v3 来腾出计算资源，也没有触发镜像重建或代码下载。

### 12.2 干净 AVD 探索

先后创建了独立 v4、v5、v6 AVD，用于验证干净首次启动。过程中补充发现：

- 真正的 image sysdir 是
  `/srv/android-cache/out/kvm-14-r75-x86_64/target/product/emu64x/emulator/x86_64`；
  本报告原先写成 product 根目录，已在 4.2 节修正；
- 共享服务器上的多个 ADB 版本会争用默认 5037；隔离客户端必须使用每条命令的
  `adb -P <port>` 或 `ANDROID_ADB_SERVER_PORT`，不能使用无效的 `ADB_SERVER_PORT`；
- Unity observer 启动必须保留 Intent extra `--es unity -force-gfx-st`；缺少时 socket
  会发布，但持续 `BOOTSTRAP_RETRY`，typed UI 为 unavailable；
- 新 AVD 的 `/data` 均正确格式化为约 47G，不再复现旧 AVD 的 10G ext4 问题；
- 该次验证时段 B 站协议配置 SDK 多次只到
  `RouteProcessService /init/agreement subscribe`，没有生成 `config_agreement.0` 或
  `config_data.xml`，也没有发布 `AgreementWebActivity`。

没有向这些干净实例复制 v3 的 `initial_agreement_tag=1`。曾只复用 v3 的 510-byte
公共 `config_agreement.0`，以及从 v4 取得并确认**不含** agreement/privacy/consent
marker 的 2657-byte `config_data.xml`；SDK 仍未回调。因此干净第二次隐私协议流程在
外部配置边界失败，不能标记为通过。v4-v6 被停止并保留为诊断样本。

### 12.3 v7 一致性克隆复现

为区分“干净 SDK 初始化失败”和“KVM/userdata 不能复用”，随后执行第二条独立验证：

1. 一致性停止已通过的 v3；
2. 将 v3 AVD 复制为新目录 `alas-headless-kvm-r75-x86_64-v7.avd`；
3. 移除目标目录中的运行锁文件，创建独立 descriptor；
4. 用新 systemd unit、独立 console/ADB 端口 `5588/5589` 启动 v7；
5. 使用独立 ADB host server port 5043；
6. 以 `--es unity -force-gfx-st` 启动新游戏进程。

克隆耗时约 52 秒，目标 AVD 实际占用约 32G。v7 实测：

| 项目 | 结果 |
|---|---|
| systemd unit | `alas-kvm-v7.service`，active |
| guest boot | 约 18 秒完成 |
| ABI / SELinux | `x86_64` / `Enforcing` |
| `/data` | 47G 总量，30G 已用，16G 可用，65% |
| 游戏资源目录 | `30107096 KiB` |
| 游戏 | 9.7.10，versionCode 9710，x86_64 |
| 新游戏 PID | 1975 |
| ANGLE | `org.chromium.angle`，路由到 `com.bilibili.azurlane` |
| observer | `ALAS_G3_BOOTSTRAP_READY {"swap":1}` |

这证明同一 KVM 镜像能够启动独立 VM，完整资源/userdata 能够持久化并被新 VM 挂载，
ANGLE NULL 和 observer 也能在新进程重新进入 ready；它不是第二次干净安装证明。

### 12.4 该次验证结束时的外部阻塞

v7 随后以 typed UI 识别到：

```text
最新版本获取失败（请检查网络连接情况），是否重试？
正在获取最新版本...
```

唯一重试目标为：

```text
OverlayCamera/Overlay/UIMain/DialogPanel/dialog/action_button
sprite=text_confirm
bounds=(695.667,469.667)-(877.667,537.0)
```

一次初始重试和冷却后的最后一次重试均满足输入前置条件；点击后弹窗消失、generation
推进，说明输入和 postcondition 正常。但游戏日志显示：

```text
line1-login-bili-blhx.bilibiligame.net:80
Connection was closed by server.

line1-bak-login-bili-blhx.bilibiligame.net:8080
Connection was closed by server.
```

宿主 DNS 能解析两个域名，两个 TCP 端口均能建立连接；失败发生在游戏版本协议建立后，
不是 DNS、磁盘、KVM、ANGLE 或 observer 不可用。最后一次 typed generation 从 197
推进到 216，约 38 秒后错误弹窗重新出现。按 fail-closed 规则已停止重复输入。

本次追加验证的最终分类是：

- **新 KVM boot / userdata / resources / ANGLE / observer：通过；**
- **第二次干净隐私初始化：外部协议配置回调阻塞；**
- **v7 到 `LoginUI2`：外部版本服务主动断开，尚未通过。**

该次验证结束时 v7 保留在唯一重试弹窗，v3 已停止，v4-v6 已停止。重新进入条件是版本主站或备站
恢复游戏协议响应；恢复后只需在相同 typed precondition 下执行一次重试，并取得两个连续
新鲜的 `LoginUI2` generation。不需要重新构建镜像、重新安装 APK 或重新复制 userdata。

## 13. 旧构建机双 build-domain 历史状态（2026-08-26）

第 1 至 12 节证明的是那一轮 KVM 登录前链路，并暴露了共享源码会让一边的 patch 状态进入
另一边构建的问题。现行方案不再依靠“加锁后临时改共享树再恢复”，而是在同一物理机器、
同一批现有磁盘上把全部可变状态按 backend 分开：

```text
KVM source      /srv/android-build/src/kvm-14-r75
KVM .repo       /var/lib/alas-build-metadata/kvm/aosp-14-r75/.repo
KVM ccache      /srv/android-cache/ccache/kvm/aosp-14-r75-x86_64
KVM out         /srv/android-cache/out/kvm-14-r75-x86_64
KVM runtime     /srv/android-runtime/kvm/alas-headless
KVM archive     /srv/android-archive/kvm

Redroid source  /srv/android-build/src/redroid-14-r75
Redroid .repo   /var/lib/alas-build-metadata/redroid/aosp-14-r75/.repo
Redroid ccache  /srv/android-cache/ccache/redroid/aosp-14-r75
Redroid out     /srv/android-cache/out/redroid-14-r75
Redroid runtime /srv/android-runtime/redroid/alas-headless
Redroid archive /srv/android-archive/redroid
```

build home、临时目录、evidence 和 APK archive 也分别落在 `kvm`/`redroid` 私有路径。那一版
旧机实现仍共同使用 `/run/alas-headless/android-cache-hot-slot.lock`，用于协调同一块 cache SSD
上的一个热输出槽；它不是共享 source、metadata 或产物。这个机制仅作为历史证据保留，不是
现行构建合同。旧 KVM/Redroid 输出已分别冷归档到：

```text
/srv/android-archive/kvm/images/cold-output/kvm-legacy-r75-pre-split-20260826
/srv/android-archive/redroid/images/cold-output/redroid-legacy-r75-pre-split-20260826
```

`.repo` 拆分证据位于：

```text
/srv/android-archive/kvm/evidence/split-repo-metadata-20260826
/srv/android-archive/redroid/evidence/split-repo-metadata-20260826
```

两套 metadata 的普通文件 inode 交集为零。该结论证明可变构建状态已经逻辑隔离，但不证明
物理资源隔离：CPU、RAM、I/O、磁盘故障和整机故障仍然共用，构建前仍要检查容量和活动
负载。

新的 KVM 空热槽构建已经完成全部 `135744/135744` actions，耗时 52 分 42 秒；manifest 位于
`/srv/android-archive/kvm/evidence/kvm-split-fresh-r75-20260826-r4/manifest.json`。它使用 KVM
私有 source、metadata、output、ccache、HOME 和 tmp；启动编译前曾因源码属主修正做过小规模
重试，因此应称为“空槽 fresh build 加预编译重试”，不是第二次 clean rebuild。

该构建生成的 `kvm-r75-x86_64-v2` runtime bundle 已发布到 KVM 私有 runtime root，并通过
bundle verifier。在线 `alas-kvm-v7-split-bootstrap-r2-path.service` 仍使用迁移期镜像，只是
保持现有验证现场，状态仍为 **migration-only / unqualified**。必须先保留整套 AVD 回退点并
通过经复审的正式服务切换，才能更新运行资格结论。构建机当前内核也不能用来资格化 Redroid
container；Redroid boot、持久化、恢复、回滚和游戏路径仍必须在兼容的独立 AWS 运行机验证。

当前默认开发机已经改为 `alas-headless.android-build-domain/v3`：KVM 与 Redroid 使用专用构建
账户和完全独立的 source、`.repo`、output、ccache、HOME、tmp、runtime、archive、evidence 与
APK archive，不再设置 build lock、共享热输出槽或 peer 可写路径。两边可以并行构建；CPU、
RAM、I/O、物理磁盘和整机故障仍是共享的性能与故障域。旧服务器只作为源码/证据回退来源，
本报告中的旧机 active service、AVD 和 userdata 未因仓库整理而改变。

## 14. 首批精简镜像协议回调故障修正（2026-08-27）

首批 `alas_kvm_x86_64` 精简候选也曾停在
`RouteProcessService /init/agreement subscribe`。这一次保留原 userdata 做只读网络诊断后确认：

- `eth0`、`wlan0` 均为 down；
- guest 没有 IP、路由和可用 DNS；
- 协议订阅期间的正确接口抓包为 0 packet；
- 手工仅连接 `AndroidWifi` 后，同一 APK、同一进程链立即生成 510-byte
  `config_agreement.0` 并打开 `AgreementWebActivity`。

因此这次精简候选的根因不是外部协议服务，而是产品定义误保留通用 `Provision`、遗漏
Goldfish `SdkSetup`。后者是标准 emulator 产品用来创建并启用 `AndroidWifi` 的 provisioner。
第 12.2 节对旧 v4-v6 的“外部配置回调阻塞”仍是当时观察记录，但不能再将它概括成已排除
镜像网络；这些旧实例没有按本次方法重新测量网络状态。

修复后重新绑定 Goldfish 项目 patch，并增量构建
`kvm-slim-stage1-wifi-fix-20260827-r3`。最终产品 inventory 同时满足：

```text
SdkSetup present
Provision absent
required missing = []
forbidden present = []
```

构建 manifest：

```text
/srv/android-archive/kvm/evidence/kvm-slim-stage1-wifi-fix-20260827-r3/manifest.json
```

实测 `sys.boot_completed=1` 会比 `SdkSetup` 完成联网早数秒，因此 KVM runtime 的
Android-ready 边界也做了窄修复：保留原 framework/package-manager 条件，并在启动游戏前
等待 `device_provisioned=1` 和 Wi-Fi 已取得 IP。该等待只属于 KVM，不影响 external ADB
后端；未联网候选拒绝、正常联网候选放行均有聚焦测试。

随后创建全新 AVD `alas-headless-kvm-slim-stage1-wifi-fix-r1`，没有运行任何手工 Wi-Fi
命令，也没有复制旧 consent 或 userdata。首次启动由 `SdkSetup` 自动完成：

| 项目 | 结果 |
|---|---|
| Wi-Fi | `AndroidWifi` 自动连接 |
| IPv4 / DNS | `10.0.2.16/24` / `10.0.2.3` |
| 外部连通 | `api.biligame.net:443` TCP 通过 |
| setup | `device_provisioned=1`、`user_setup_complete=1` |
| account | `Accounts: 0` |
| game | 9.7.10、versionCode 9710、x86_64 |
| agreement | 新生成 510-byte 配置并进入精确 `AgreementWebActivity` |
| consent | `initial_agreement_tag` 不存在；未点击协议 |
| observer | `ALAS_G3_BOOTSTRAP_READY {"swap":1}` |

第二次 no-snapshot 冷启动自动重连网络，保留游戏、observer 和协议配置；再次以
`--es unity -force-gfx-st` 冷启动游戏后，协议页和 observer-ready 均复现。整个过程没有
截图导航、坐标输入、账号数据或凭据。证据目录：

```text
/srv/android-archive/kvm/evidence/kvm-slim-stage1-wifi-fix-live-20260827-r1
```

本次只验证修复直接控制的链路，没有点击协议，也没有重新下载约 28 GiB 资源，因而不能把
结果外推为新的干净 `LoginUI2(Clone)` 证明。测试 AVD 已停止并保留；在线
`alas-kvm-v7-split-bootstrap-r2-path.service` 始终 active、未被切换。Emulator 34.2.7 在
`emu kill` 完成后仍以 SIGSEGV 退出，这是独立的宿主 emulator 关闭缺陷；端口和 transient
unit 已清理，第二次启动已证明 userdata 持久化未受影响。

## 15. 最终镜像协议页未重入：宿主分流根因与修复（2026-08-27）

最终镜像唯一一次 90 秒窗口没有重入 `AgreementWebActivity`，后续 DEX 与网络联合诊断确认
这不是 WebView provider 故障，也不是 `ContactsProvider` 回归。协议 SDK 即使读到缓存的
`config_agreement.0`，仍会先异步请求 `/api/agreement/config`；只有该回调返回后才调用
`AgreementUtils.openAgreement()` 进入 `/gsc_agreement_library/AgreementWebActivity`。

宿主 `sing-box` 当时只有 SSH 地址直连规则，其余流量进入 `final: auto`。选中的代理节点对
Biligame 国内 HTTPS 返回 `remote error: rejected`，宿主 `curl` 也在 TLS 阶段失败。修复为在
80/443 端口先做 SNI sniff，并把 `biligame.net`、`biligame.com`、`bilibili.com`、
`bilibiligame.net` 后缀路由到 `direct`；原 SSH 直连规则继续保留。配置检查和服务重载通过，
日志确认相关目标由 `outbound/direct[direct]` 承载。

用同一最终镜像和保留 userdata 冷启动游戏，2 秒采样即得到精确前台组件：

```text
com.bilibili.azurlane/com.base.gsc_agreement_library.AgreementWebActivity
```

同一进程随后加载 `com.android.webview 119`，并从 x86_64-only WebView APK 成功加载
`lib/x86_64/libwebviewchromium.so`。为避免 SDK 十秒失败回退可能写入隐私状态，本次在识别
Activity 后立即 force-stop；root 检查的 `config_data.xml` 仍是空 `<map />`，没有
`initial_agreement_tag` 或 `key_agreement`，没有点击协议。证据目录：

```text
/srv/android-archive/kvm/evidence/kvm-webview-x86_64-agreement-fix-20260827-r1
```

另外，全新 userdata 上 Android 公网 captive-portal 探测会把可用的 `AndroidWifi` 永久禁用。
专用产品的 `SdkSetup` 现会在创建网络前设置 `captive_portal_mode=0`。增量构建用时 1 分 57 秒，
全新 AVD 首启和一次重启后均为 `NETWORK_SELECTION_ENABLED`、`VALIDATED`、
`10.0.2.16/24`，且 guest 到 `api.biligame.net:443` 成功。镜像与现场证据：

```text
/srv/android-archive/kvm/evidence/20260827T115541Z/manifest.json
/srv/android-archive/kvm/evidence/kvm-wifi-captive-portal-ignore-live-20260827-r1
```
