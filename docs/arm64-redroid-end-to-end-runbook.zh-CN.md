# ARM64 Redroid 端到端运行手册与故障账本

状态日期：2026-08-26

## 1. 当前结论

ARM64 主线已经真正打通到账号登录边界：

~~~text
ARM64 Linux
  -> VA39 kernel
  -> Android 14 Redroid
  -> package-private ANGLE NULL
  -> Unity main-thread typed observer
  -> 28.1 GB real resource update
  -> com.gsc.phone_login.PhoneLoginActivity
~~~

最终页面的手机号输入框为空且未聚焦，“下一步”禁用，没有输入或提交账号。

这是一条可继续开发的工程通道，不是完整支持声明。当前仍未证明：

- 私有 ANGLE loader 从首次游戏启动起就已封入 OCI 的整段 fresh-userdata 复现；
- 账号登录、游戏主界面和服务器选择；
- pinned ALAS 或更新版 ALAS 的真实任务工作负载；
- game/Android recovery、Redroid lifecycle/cleanup 和长期 soak；
- Android native FBE、Direct Boot 和自维护镜像发布资格。

登录边界的逐项证据见原持久化 userdata 的
[AWS ARM64 Redroid 登录边界验证](aws-arm64-redroid-login-boundary-validation-20260826.md)，
以及新建 userdata/container 的
[AWS ARM64 Redroid 全新容器登录复现](aws-arm64-redroid-fresh-login-validation-20260826.md)。

### 已验证范围总览

| 流程 | 当前状态 | 证据边界 |
| --- | --- | --- |
| 固定源码与双 ABI 构建 | 通过 | AOSP/Redroid 14 r75 的 x86_64、ARM64 system/vendor、OCI、SBOM 和 provenance 已产出；不等于运行资格 |
| OCI Android UID/GID | 通过 | 双 ABI 修正版均验证 logd=0550 1036:1036 |
| ARM64 host/kernel | 当前运行路径通过 | Binder、cgroup v2、VA39、dm-default-key/loop 路径可启动当前 Android 14 实例 |
| G1/G2/G3 平台合同 | 通过历史与当前样本 | ANGLE NULL、Unity、typed observer；不能替代真实 ALAS workload |
| 外部 APK/资源更新 | 通过 | 合成更新矩阵已通过；真实游戏 28.1 GB 资源也完成 |
| restart/persistence/OCI rollback | 平台证据通过 | 历史隔离实验已通过；最新登录实例尚未由新 backend 重跑完整 recovery/cleanup |
| 真实游戏登录前 | 通过 | 国服 9.7.10、内容版本 9.7.328，到 PhoneLoginActivity，未输入账号 |
| fresh userdata 首次隐私页 | 单次通过、拓扑仍需复验 | 新 userdata 上唯一 `.agree` 经 CDP DOM 点击后同 PID 转入 MainActivity；该次转场发生在私有 loader 修复前，不能冒充“私有 NULL 自首次启动即生效”的完整证明 |
| 当前 OCI 独立复现 | blocked | tag/digest 不含已验证的 libEGL loader 与 process-lived Pastel 二进制；当前 fresh 容器在 writable layer 补入两文件后通过 |
| RedroidBackend | 实现与离线合同通过 | ARM 隔离实例完整 lifecycle 资格待执行 |
| Android native FBE/Direct Boot | blocked | loop/dm 存在，但五项 Android 证据未闭环 |
| ALAS workload/soak | 未验证 | 不得提升为生产或发布资格 |

## 2. 两条流水线、一个汇合点

ARM 环境不是一条“镜像能启动就算成功”的流水线。它由两条独立路径组成：

~~~text
镜像/宿主流水线
source lock
  -> AOSP/Redroid 双 ABI 构建
  -> 保留 Android UID/GID 的 OCI
  -> Binder/cgroup/kernel/loop volumes
  -> Android boot/ADB/persistence
                         \
                          -> 汇合：精确 package + foreground PID
                         /           + fresh coherent generation
游戏/语义流水线                    + unique actionable target
外部安装游戏                      + blocker/postcondition checks
  -> package-private ANGLE NULL
  -> -force-gfx-st
  -> typed observer
  -> reviewed semantic input
~~~

汇合点之后才允许输入。镜像能启动、Unity 不崩溃、observer 有响应和某个按钮可点击，
是四个不同条件，不能互相替代。

## 3. 主机职责与制品边界

### Android 镜像/ANGLE 构建机

仓库 AGENTS.md 中的两个 SSH 端点是 Android 镜像优化和构建机。连接后仍要重新确认
主机身份、RAM、磁盘、源码树、缓存和活动工作负载。

日常 Redroid 工作直接登录 `alas-redroid-build`，KVM 工作直接登录 `alas-kvm-build`。
两者都有完整免密 sudo，使用 `sudo -n true` 预检；这使账户成为 root-equivalent，因此 sudo
只能提升确实需要 root 的单条宿主、loop/mount、systemd 或打包命令。不得以 root 运行整次
`repo`/Git/Soong/Ninja 构建，不得跨写、清理或改权另一 backend。root 步骤结束后要核对当前
backend 的源码、out、cache、archive 和 evidence 属主，并记录重要提权变更及回滚。

该机器当前内核不满足 Redroid 容器资格条件。它可以用于：

- 固定源码的 AOSP/Redroid 构建；
- x86_64/ARM64 OCI 打包；
- ARM64 ANGLE NULL observer 增量构建；
- 保存源码树、out、缓存、日志和制品。

它不能用于宣称真实 Redroid boot、游戏、持久化、恢复或回滚通过。

### ARM64 Redroid 运行机

真实 Redroid 和游戏验证使用单独的 ARM64 Linux/AWS 主机。该主机地址会在停机后变化，
不得把历史公网 IP 写入脚本或运行锁。每次开始前向用户取得当前连接信息。

### 游戏与账号数据

游戏始终外部安装。游戏 APK、资源、账号 userdata 和原始现场证据不得进入系统镜像、
公开 OCI 或仓库。每个运行实例使用独立 writable userdata；不得共享整个 /data。

## 4. 阶段 0：定义目标、权限和停止条件

付费主机开工前记录：

- 本轮要关闭的具体 blocker；
- 预计时长和所需制品；
- 哪个结果会改变工程决策；
- 最大动作与资源预算；
- 成功和失败停止条件；
- 要保留的日志、镜像、哈希和回滚点。

“验证到登录页”的动作边界是：

- 可按用户授权同意隐私协议；
- 可选择并下载普通游戏资源；
- 不输入账号，不点击“下一步”，不选择服务器；
- 不执行购买、付费、账号绑定、清除 userdata 或卸载游戏。

## 5. 阶段 1：ARM64 宿主预检

先验证当前运行内核和 digest-pinned 镜像：

~~~bash
export ALAS_REDROID_IMAGE='registry.example/redroid@sha256:<digest>'
./scripts/wsl/probe-redroid-arm64-host.sh
~~~

探针至少检查：

- uname -m 是 aarch64/arm64；
- Docker CLI 存在；
- cgroup v2 controllers 存在；
- Binder/BinderFS 设备存在；
- Redroid 镜像使用内容 digest；
- 当前运行内核配置可读取；
- CONFIG_ARM64_VA_BITS 不超过 47。

预期关键输出：

~~~json
{
  "outcome": "pass",
  "kernel_va_bits": 39,
  "game_lightuserdata_va_outcome": "pass",
  "failures": []
}
~~~

如果内核配置不可读，必须返回 arm64-kernel-config-unavailable；不能猜测另一内核版本的
/boot/config 文件。如果 VA bits 为 48，只阻止真实游戏能力，不应把无关的 Redroid
合成 APK 能力也全局否定。

随后只读确认：

~~~bash
uname -a
docker ps --no-trunc
findmnt -T /srv/alas-runtime
df -h /srv/alas-runtime
free -h
cat /sys/fs/cgroup/cgroup.controllers
ls -l /dev/binderfs /dev/binder /dev/hwbinder /dev/vndbinder 2>/dev/null
~~~

还要检查 dm-default-key、ext4 quota 和所需模块。native FBE 需要真实
CONFIG_DM_DEFAULT_KEY 能力；普通 ext4 encrypt feature 不能替代它。

## 6. 阶段 2：固定源码并构建双 ABI 镜像

构建必须从
[android-image-source-lock.example.json](../integration/runtime/android-image-source-lock.example.json)
固定的 AOSP、Redroid、WebView 和项目补丁开始。

先验证 source lock：

~~~bash
export PYTHONPATH=python
python3 scripts/python/validate_android_image_source_lock.py \
  --source-lock integration/runtime/android-image-source-lock.example.json
~~~

正式入口：

~~~bash
./scripts/wsl/build-redroid-images.sh \
  integration/runtime/android-build-domain.redroid.example.json \
  integration/runtime/android-build-domain.kvm.example.json \
  integration/runtime/android-image-source-lock.example.json \
  redroid-14-r75-build-1
~~~

构建机曾遇到系统 Python 3.8 无法执行 dataclass(slots=True)。修复方式是给该构建任务
显式使用现有 Python 3.10+ 环境；不要替换系统 Python，也不要因此重做已经成功的 repo
sync。预同步源码树必须有与 source lock 校验结果一致的恢复 marker，不能绕过脚本的
resume 身份检查。

Redroid 和 KVM 不再共享 AOSP source、`.repo` metadata、ccache、build home、临时目录、
out、runtime、archive、evidence 或 APK archive。build domain v3 没有锁字段、共享热输出
或共享构建组；两侧输出可以同时存在并并行构建。容量不足应通过各自目录的空间检查和明确
失败处理，不能靠互斥等待掩盖。完整 sudo 可以绕过普通 Unix 权限，但不得用它破坏这些
路径边界。

一次成功构建必须保留：

- x86_64 与 ARM64 的 system.img、vendor.img；
- OCI archive 与 identity；
- resolved manifest、source-lock hash、project patch receipt；
- build log、installed-files、SBOM、NOTICE 和 provenance；
- 失败时的源码树、out 和缓存。

构建失败后先诊断，不删除 out 或启动 clean rebuild。双 ABI 构建成功只证明“构建完成”，
不证明镜像能启动、FBE 可用或游戏可运行。

以下记录属于拆分前的共享源码迁移阶段，已被现行双 build-domain 布局取代，只保留作历史
诊断证据。2026-08-26 当时完成了一次不编译的共享源码迁移，并保留
`/srv/android-build/evidence/redroid-14-r75-source-rebind-20260826/`：

- 新 source-lock canonical SHA-256：
  `a92490c4f92112baa0e7ff5a296caf36b3c670e98f27cfc7527c7eb802d77bf9`；
- `frameworks/native` 0003 提交：
  `adccef2d34c375750152b80cf301679063378b62`；
- `external/swiftshader` 0004 提交：
  `b211373246bc9824dd9c48170b194d18d756f8ae`；
- 诊断用 `ENABLE_RR_LLVM_IR_VERIFICATION` 已从共享源码恢复为 HEAD，未进入 0004；
- 全部 1364 个 repo project 返回 `nothing to commit`；
- KVM profile 已绑定同一个 source lock 和新的 `frameworks/native` HEAD，三个临时
  overlay 均通过 apply preimage 检查；layout/profile SHA-256 分别为
  `8afbdb8fba808eb52f1a4cd57735ebae8cb1d5ca7cf3f8fb66e2357bf9c1ee64`、
  `f405f8f13f2f171de07a2b954e0c8accecca7870d1e31bcba8f2d91ceb0a9fe2`。

这一步当时只把 Redroid/KVM 共用源码和下一次构建入口收成可审计状态，没有启动新的
Android 编译，也没有生成修正版 OCI；不得再把它当成当前构建入口。

现行布局已经进一步拆开：

~~~text
Redroid source  /srv/android-build/redroid/source/aosp-14-r75
Redroid .repo   /srv/android-build/redroid/repo/aosp-14-r75
Redroid ccache  /srv/android-build/redroid/ccache/dual-abi
Redroid out     /srv/android-build/redroid/out/dual-abi

KVM source      /srv/android-build/kvm/source/aosp-14-r75
KVM .repo       /srv/android-build/kvm/repo/aosp-14-r75
KVM ccache      /srv/android-build/kvm/ccache/x86_64
KVM out         /srv/android-build/kvm/out/x86_64
~~~

拆分收据分别位于
`/srv/android-archive/redroid/evidence/split-repo-metadata-20260826/` 和
`/srv/android-archive/kvm/evidence/split-repo-metadata-20260826/`；两套 metadata 的普通文件
inode 交集为零。旧输出分别冷归档到 backend 私有的
`images/cold-output/redroid-legacy-r75-pre-split-20260826` 和
`images/cold-output/kvm-legacy-r75-pre-split-20260826`，不再作为另一侧的热构建输入。

新的 KVM 私有空输出目录构建已经完成全部 `135744/135744` actions，耗时 52 分 42 秒；它使用 KVM
私有 source、metadata、output、ccache、HOME 和 tmp。启动编译前曾因源码属主修正做过小规模
重试，所以这不是第二次 clean rebuild。产出的 `kvm-r75-x86_64-v2` runtime bundle 已发布到
KVM 私有 runtime root 并通过 verifier；旧在线 KVM 服务仍是 migration-only，整套 AVD 回退点
和正式 live cutover 尚未通过。这不重新打开 Redroid 的可变构建路径。该机器仍只承担 Redroid
**构建**；容器 boot、持久化、恢复、回滚和游戏路径资格必须在兼容的独立 AWS 运行机完成。

## 7. 阶段 3：OCI 打包与 Android 文件属主

OCI 打包入口是
[package-redroid-oci.sh](../scripts/wsl/package-redroid-oci.sh)。打包 rootfs 时必须使用：

~~~text
--numeric-owner --xattrs
~~~

不得再使用 --owner=0 --group=0。旧打包器把全部 Android UID/GID 归零后，
/system/bin/logd 虽然仍是 0550，却变成 0:0；以 1036:1036 启动的 logd 无执行权限，
导致 service status 127 和 Android 首启失败。

修正版 OCI 至少检查：

~~~text
/system/bin/logd                    0550 1036:1036
/system/bin/vold                    0755 0:2000
/system/lib64/libandroid_runtime.so 0644 0:0
~~~

这项修复同时适用于 x86_64 和 ARM64。检查 OCI 时使用临时 containerd namespace，
结束后删除 view lease、snapshot、tag 和 namespace；不要影响保留的运行实例。

### 不得把容器 writable layer 当成 OCI 内容

2026-08-26 的全新容器复现发现，现场 tag/digest 本身没有包含两个运行时修复；旧成功
容器只在自己的 writable layer 中持有它们。`docker diff` 的关键项是：

~~~text
C /system/lib64/libEGL.so
C /vendor/lib64/hw/vulkan.pastel.so
~~~

把旧容器成功等同于 OCI 成功会让新容器重新出现 `angleLoadingFailureCount`，游戏回到
system ANGLE/SwiftShader。当前恢复是在新容器自己的 writable layer 中补入已验证二进制：

~~~text
3ff77c7f09fcad34be75b71d36fc9ff1edefae06b88fea35d932124507d3cfd4  /system/lib64/libEGL.so
86d29a36fc10ad51df541f419ecf44ee7a0165f752db8b57d579bca0f2029dbc  /vendor/lib64/hw/vulkan.pastel.so
~~~

根因已经确认：两项修复在完整 `system.img/vendor.img` 生成后做了目标级增量编译；product
output 已是新二进制，但后续 OCI 重打仍读取旧分区镜像。构建机实测为：

~~~text
product output libEGL.so          3ff77c7f09fcad34be75b71d36fc9ff1edefae06b88fea35d932124507d3cfd4
system.img     libEGL.so          39d2a8f2b57a90d5ff9bae9fd1a9f9ad222c397fa0fcbaa7c14b98991ea72232
product output vulkan.pastel.so   86d29a36fc10ad51df541f419ecf44ee7a0165f752db8b57d579bca0f2029dbc
vendor.img     vulkan.pastel.so   46cb75f461b5772ae20a2a122e9e163d3ebdc3775da8bb1877d1464be030c5bc
~~~

打包入口现在必须生成 `runtime-components-<abi>.json`，并要求分区镜像中的两个库与当前
product output 内容、ABI 完全一致；否则在创建 OCI 前 fail-closed，并提示先重建
`systemimage/vendorimage`。这只关闭“旧分区被封装”的通路；下一次发布仍必须从新 OCI
启动 fresh userdata，重跑登录前路径，不能把本次容器级补丁写成 digest-only 复现。

## 8. 阶段 4：内核选择与安全回退

### 48-bit VA 与旧 LuaJIT

真实症状：

~~~text
bad light userdata pointer
Lua unprotected panic
Unity process exit status 1
~~~

同一事件中的高地址位于 libtolua.so 的有效可写映射，调用方来自 libil2cpp.so。
这不是悬空指针、ANGLE NULL 或 RSA 失败。游戏内嵌旧 LuaJIT 的 lightuserdata 编码
不能表示 47 位以上的用户地址；48-bit VA 内核可能把合法映射放到其窗口之外。

已验证修复：

- 保留原 48-bit 内核和启动项；
- 构建并另装 CONFIG_ARM64_VA_BITS_39=y 的 4 KiB page 内核；
- 先单次启动新内核；
- 验证 Android 12/14 boot、真实游戏 PID 和崩溃日志；
- 只有验证通过后才把新内核设为 GRUB saved entry。

已验证内核版本为：

~~~text
6.1.176-alas-dmdefault-ikconfig-va39+
~~~

不要尝试通过增大 RLIMIT_STACK、截断地址或修改 Lua 指针表示绕过问题。这些做法没有
稳定的语义边界。

### quota 与 dm-default-key

切换内核后，启动带 quota 的 userdata 前检查 quota_tree、quota_v2；模块化配置可先
加载模块。native FBE 还要求 dm-default-key target。缺失时应明确阻止 FBE 路径，
而不是删掉 fstab 中的 fileencryption 来制造启动成功。

构建/安装候选内核时至少审查以下配置，并保留完整 config 作为制品：

~~~text
CONFIG_ARM64_4K_PAGES=y
CONFIG_ARM64_VA_BITS_39=y
CONFIG_DM_DEFAULT_KEY=y 或可在启动前加载的模块
CONFIG_IKCONFIG=y
CONFIG_IKCONFIG_PROC=y
CONFIG_QUOTA_TREE=y/m
CONFIG_QFMT_V2=y/m
CONFIG_ANDROID_BINDER_IPC=y
CONFIG_ANDROID_BINDERFS=y
~~~

配置存在不等于功能已通过；仍要在重启后的当前内核上检查 dmsetup targets、Binder、
quota、Android boot、userdata 和真实游戏。

## 9. 阶段 5：userdata、metadata 与 Redroid 启动

正式实例应提供独立的 userdata 和 metadata block device。仓库提供：

- [provision-redroid-userdata-image.sh](../scripts/wsl/provision-redroid-userdata-image.sh)
- [redroid-native-fbe](../integration/runtime/redroid-native-fbe/)

空实验卷可用于验证 host ext4 encrypt、独立 loop、rw/nodev/nosuid 和清理，但这只能
叫 host-volume-qualified。只有 Android 同时满足以下条件才能声明 native FBE：

~~~text
ro.crypto.state=encrypted
ro.crypto.type=file
PackageManager advertises FBE
sm get-fbe-mode=native
mount/vold service and Direct Boot behavior are coherent
~~~

启动后至少确认：

~~~bash
docker inspect <container>
adb -s <private-serial> shell getprop sys.boot_completed
adb -s <private-serial> shell getprop ro.product.cpu.abi
adb -s <private-serial> shell getprop ro.build.fingerprint
adb -s <private-serial> shell df -k /data
~~~

ADB 只能绑定 loopback 或 RFC1918 地址，不能暴露到公网。

## 10. 阶段 6：构建和安装 ARM64 ANGLE observer

在保留的固定 ANGLE 源码树上执行：

~~~bash
./scripts/wsl/bootstrap-angle.sh
./scripts/wsl/apply-angle-patches.sh
./scripts/wsl/apply-angle-g3-patches.sh
export ALAS_ANGLE_TARGET_CPU=arm64
./scripts/wsl/build-angle-null-observer.sh
~~~

构建脚本会：

- 验证固定 ANGLE revision；
- 应用基础 NULL 和 G3 observer 补丁；
- 检查资源流程的精确 raycast allowlist；
- 构建 arm64-v8a APK；
- 生成私有 libEGL_alasx.so、libGLESv1_CM_alasx.so、libGLESv2_alasx.so；
- zipalign、签名并输出 SHA-256。

2026-08-26 登录路径使用的最终 APK SHA-256：

~~~text
f37379fde001ee60f3916cbd56163fef55181d16e889383237968f7e7ea23401
~~~

### Android 14 ANGLE SONAME 冲突

Redroid 系统显示栈会预装 system ANGLE。若 packaged ANGLE 仍使用
libEGL_angle.so/libGLESv2_angle.so，应用 linker namespace 可能复用已加载的系统
SONAME，导致游戏没有真正进入 observer APK。

修复由三部分组成：

1. frameworks/native 的 load_angle 只为 APK ANGLE 请求 alasx 后缀；
2. ANGLE APK 提取 native libraries 到 nativeLibraryDir；
3. 包内同时保留 upstream alias，并生成等长私有 SONAME/依赖副本。

系统进程继续使用原 system ANGLE，不受 package-local 修复影响。

### APK 签名不兼容

若 adb install -r 返回：

~~~text
INSTALL_FAILED_UPDATE_INCOMPATIBLE
~~~

这是正确的 fail-closed 行为。先用 apksigner 比较新旧证书。当前现场中，构建 APK 使用
Chromium debug certificate，而已安装 ANGLE 包使用 AOSP testkey。最终用同一 AOSP
testkey 重新签名后才允许覆盖安装。

不得为保留游戏状态而关闭签名检查；也不得未经授权卸载包。签名失败时原包和 userdata
应保持不变。

## 11. 阶段 7：ANGLE 路由和 Unity 启动

精确路由：

~~~bash
adb -s <serial> shell settings put global angle_debug_package org.chromium.angle
adb -s <serial> shell settings put global angle_gl_driver_selection_pkgs com.bilibili.azurlane
adb -s <serial> shell settings put global angle_gl_driver_selection_values angle
adb -s <serial> shell settings put global show_angle_in_use_dialog_box 0
~~~

Unity 必须带主线程图形参数启动：

~~~bash
adb -s <serial> shell am force-stop com.bilibili.azurlane
adb -s <serial> shell am start -W \
  -a android.intent.action.MAIN \
  -c android.intent.category.LAUNCHER \
  -n com.bilibili.azurlane/com.manjuu.azurlane.MainActivity \
  --es unity -force-gfx-st
~~~

遗漏 -force-gfx-st 时，NULL swap 可能在 graphics worker，observer 注册的 Unity
主线程与 swap TID 不一致。修复不是放宽线程门，而是使用游戏已支持的官方参数，
让 snapshot rendezvous 回到 Unity main thread。

启动后验证：

- 唯一游戏 PID；
- 精确 foreground package/activity；
- maps 中存在 libEGL_alasx.so 与 libGLESv2_alasx.so，或同 PID observer 日志证明；
- observer 报告 abi=arm64-v8a、flags=15、main_thread=true；
- logcat 没有 bad light userdata、Lua panic、fatal signal 或 exit_group。

ANGLE NULL 下游戏截图为黑色是预期结果，不能用截图判断游戏健康。

## 12. 阶段 8：observer 首帧与 semantic input

旧逻辑只在 swap 1 和每 60 swap 采样。若 swap 1 时 IL2CPP/场景尚未 ready，后续资源
页面可能一直没有 typed frame。

[0012-android-null-bootstrap-snapshot-retry.patch](../patches/angle-g3/0012-android-null-bootstrap-snapshot-retry.patch)
增加有界 bootstrap：

- 未 ready 时采样 swap 1；
- 之后在不超过 120 的每三个 swap 采样；
- 首次 status=0 后设置 observer ready；
- ready 后恢复每 60 swap 的正常节奏；
- 只记录少量 READY/RETRY 日志。

它没有接受 graphics worker，没有创建第二套状态机，也没有截图回退。

任何输入前仍必须同时满足：

- exact package、foreground activity 和 PID；
- fresh coherent generation；
- 唯一 reviewed mapping；
- enabled、actionable、raycast_top=true；
- 无 blocker/遮挡；
- 动作后出现明确 postcondition。

状态不推进时停止重复点击，检查 generation、path、target、blocker 和场景。

## 13. 阶段 9：隐私协议与首次安装路径

全新 userdata 首次进入：

~~~text
com.bilibili.azurlane/com.base.gsc_agreement_library.AgreementWebActivity
~~~

UIAutomator 只暴露 WebView 容器，因此本轮通过 WebView DevTools/CDP 读取真实 DOM，要求：

- 标题精确为 `sdk协议`；
- `.agree` 与 `.disagree` 各且仅各一个；
- 文字分别为“同意”与“拒绝”，可见且矩形为正；
- 只调用唯一 `.agree` 的 DOM `click()`；
- 点击后前台转为 MainActivity，同一游戏 PID 保持；
- 15 秒前置与 60 秒后置窗口内没有游戏 fatal 或 destroyed mutex。

该单次 fresh Agreement 转场已通过，但有一个重要证据边界：当时 OCI 缺少私有 loader
修复，游戏尚未进入 package-private NULL；补入 loader/Pastel 后协议状态已经持久化，不能
在同一 userdata 中再次制造首次协议页。因此原 destroyed-mutex 问题被进一步缩小，但
“私有 NULL 从首次启动起生效的 Agreement 转场”仍需在封好修复的新 OCI 上再跑一次。

若任务明确要求单独的 rendered-mode 诊断，可使用
[run-redroid-rendered-login.ps1](../scripts/windows/run-redroid-rendered-login.ps1)：

~~~powershell
.\scripts\windows\run-redroid-rendered-login.ps1 -Serial 127.0.0.1:<tunnel-port>
~~~

该脚本只在开始时确认当前确实是 ANGLE NULL，临时切到 native renderer，关闭 scrcpy
后在 finally 中恢复原设置、以 -force-gfx-st 重启，并再次验证私有 NULL library。
它不是常规 headless 验收路径；除非任务明确要求 separate rendered investigation，
不得为视觉检查随意关闭 NULL。

## 14. 阶段 10：资源选择、容量门与下载

登录前资源流程新增的 raycast allowlist 只有：

~~~text
PaintingPrefsPanel(Clone)/Panel/Confirm
OtherPrefsPanel(Clone)/Panel/Confirm
DialogPanel/dialog/action_button
~~~

验证过的动作序列：

1. 基础资源页确认 Max 已选、Min 未选；
2. 点击唯一 PaintingPrefsPanel Confirm；
3. 附加资源页确认六项默认勾选；
4. 点击唯一 OtherPrefsPanel Confirm；
5. 验证弹窗文本精确为“本次更新需要下载28.1GB的文件，是否继续更新？”；
6. 下载前检查 /data；
7. 只有容量充足后点击唯一 action_button；
8. 监控进度、完成文件、失败文件、前台 PID 和剩余空间；
9. 进度消失后以 typed state/activity 判断下一页面，不盲点第二次。

全新容器本轮从 2026-08-26 03:24:59Z 开始下载，03:36:22Z 记录
`all task end:0`，约 683 秒。最后一个可见进度是 27.9 GB，所有采样的失败文件数均为 0；
资源校验报告没有破损，随后加载 `LoginUI2` 和内容版本 `9.7.328`。

### 下载完成后的 opening 覆盖层

本轮下载完成后没有自然切换到手机号 Activity，而是留下全屏
`OverlayCamera/Overlay/UIMain/opening(Clone)`。它的 Button `raycast_top=null`，不能
作为可执行语义目标。只有同时满足以下窄条件时，才执行一次游戏冷重启：

1. 同一登录会话已观察到合法下载进度且失败数为 0；
2. 日志精确出现 `all task end:0`，资源校验无破损；
3. UpdatePanel 已消失，`LoginUI2 ver 9.7.328` 已加载；
4. opening 全屏覆盖持续存在，且没有唯一 `raycast_top=true` 的安全动作；
5. 前台 package/PID 无误且没有游戏 fatal。

冷重启必须保留 `-force-gfx-st`。重启后重新发现 PID、重绑 observer socket、验证私有
`libEGL_alasx.so`/`libGLESv2_alasx.so`、`flags=15` 和主线程一致。本轮只重启一次，
PID `1763 -> 2593`，约 10 秒后自然进入 PhoneLoginActivity。普通启动黑屏、未知弹窗或
没有完整下载会话时不得套用这个恢复。

### 16 GiB userdata 不足

首次检查时 /data 只有约 13.4 GiB 可用，因此没有点击 28.1 GB 下载。已验证的无损扩容
流程是：

1. clean stop 容器；
2. 用 docker inspect、losetup -j 和 realpath 精确绑定 container、loop 和 backing file；
3. 保留离线稀疏备份；
4. 将原 backing file 从 16 GiB 扩到 48 GiB；
5. losetup --set-capacity；
6. 重启容器并验证新的 dm table sector count；
7. 在容器 root 中对实际 /data block device 执行 resize2fs；
8. 再次验证游戏状态和下载确认弹窗仍在。

现场备份：

~~~text
/srv/alas-runtime/volumes/a14-pastel-process-lived-userdata.pre-expand-16g-20260826.img
~~~

不得对未验证路径、多个 loop match 或正在写入的容器执行扩容。设备名如 dm-34 会漂移，
每次必须重新发现，不能复制历史编号。

原持久化 userdata 运行约 643 秒后到登录边界；新建 userdata/container 运行约 683 秒
完成下载，随后按上述窄条件冷重启一次到登录边界。新容器最终 `/data` 剩余
17,523,640 KiB，宿主剩余 33,423,900 KiB。

## 15. 阶段 11：登录边界验收

目标 Activity：

~~~text
com.bilibili.azurlane/com.gsc.phone_login.PhoneLoginActivity
~~~

通过条件：

- phone field count=1；
- resource id=com.bilibili.azurlane:id/et_gsc_phone_num；
- 文本是“请输入手机号”占位符；
- 输入框未聚焦；
- next control count=1；
- resource id=com.bilibili.azurlane:id/tv_gsc_phone_next；
- enabled=false；
- account_input_performed=false；
- account_submission_performed=false。

Android 14 的 activity 输出应优先读取 topResumedActivity，同时兼容旧字段
mResumedActivity；无论字段名如何，都要精确匹配游戏 package/activity。

达到该边界后停止，不输入账号。

## 16. 阶段 12：Redroid backend、恢复和回滚

[redroid.config.example.json](../integration/runtime/redroid.config.example.json) 和
[runtime_backend_redroid.py](../python/alas_headless/runtime_backend_redroid.py)
实现预配置 containerd 实例的生命周期合同：

- config 只接受 loopback/RFC1918 ADB；
- image manifest digest 必须精确匹配；
- container ID、image reference、ABI、fingerprint、external-install 和 storage label
  必须一致；
- userdata/metadata 必须各自唯一映射到已验证 loop backing file；
- 只启动已预配置的 container，不在 backend 中临时造镜像；
- cleanup 只停止本次 backend 自己启动的 task；
- Android restart 先观察 ADB offline，再重新启动原实例；
- game restart 始终保留 -force-gfx-st。

先生成计划：

~~~powershell
$env:PYTHONPATH = 'python'
python scripts/python/qualify_runtime.py --backend redroid --config integration/runtime/redroid.config.example.json --lock <arm-runtime-lock.json> --plan-output <plan.json>
~~~

只有配置、当前主机和 runtime lock 都是目标实例时，才在明确 mutation 授权下执行。
当前实现和离线测试已通过，但 ARM64 真实实例尚未完成 backend 的完整
start/ready/recover/stop/cleanup 资格。

容器 restart 证据可使用 qualify_redroid_restart.py；真实 OCI rollback 必须使用与
生产 userdata 隔离的临时目录和两个不同 digest。不要把同一镜像 restart 写成 rollback。

## 17. 故障账本

| 状态 | 症状 | 根因/结论 | 修复或重新进入条件 |
| --- | --- | --- | --- |
| 已关闭 | 构建预检在 Python 3.8 报 dataclass slots 错误 | 任务解释器过旧，不是源码或硬件故障 | 构建任务显式使用 Python 3.10+；不替换系统 Python，不重做 sync |
| 已关闭 | 自建 OCI 首启时 logd Permission denied/status 127 | 打包器用 owner=0/group=0 抹掉 Android UID/GID | 使用 numeric-owner 保留属主；验证 logd=0550 1036:1036 |
| 未关闭/当前容器已恢复 | 新容器选择 ANGLE 后仍增加 angleLoadingFailureCount | 现场 OCI 未包含 private loader 与 process-lived Pastel 修复；旧成功仅来自 writable layer | 当前容器补入两份精确哈希二进制；重新封 OCI 并用 fresh userdata 独立验证后才能关闭 |
| 外部宿主 blocker | 自建 native-FBE 候选无法创建 default-key dm target | 构建机内核缺 CONFIG_DM_DEFAULT_KEY | 换合格运行宿主/内核后用全新隔离卷首启；构建机不承担运行资格 |
| 未关闭 | Android native FBE 20/21，device-encrypted-storage 失败 | host ext4 encrypt 不是 Android FBE/Direct Boot | 五项 FBE 与 Direct Boot 实机全部通过后才重入 |
| 未关闭/局部缓解 | AgreementWebActivity 转 MainActivity 出现 destroyed mutex | ARM64 失败栈进入 Pastel Queue/Reactor/LLVM/marl；完整对象生命周期尚未闭环 | fresh userdata、等价私有 NULL/WebView 拓扑下连续采集并重复通过转场 |
| 已关闭一个子因 | LLVM PassRegistry/ManagedStatic teardown 崩溃 | driver unload 时销毁进程仍在使用的 LLVM 状态 | LLVM state/PassRegistry 改为 process-lived；仍不能代表全部 Pastel mutex 已关闭 |
| 已排除 | 怀疑 RSA/BIO 导致 Unity 退出 | 小米 11 与 Redroid 的 BIO/RSA 四步均成功，RSA_public_decrypt 都返回 182 字节 | 不再沿 OpenSSL 改代码；bio fail 视为并发退出期次生症状 |
| 已关闭 | bad light userdata pointer、Lua panic、Unity exit 1 | 48-bit VA 合法高地址超出旧 LuaJIT lightuserdata 窗口 | VA39 内核；真实 maps/PID/logcat 复验，保留 VA48 回退 |
| 已关闭 | 已选择 debug ANGLE，但游戏复用了 system ANGLE | Android 14 已加载相同 angle SONAME，namespace 复用错误对象 | AOSP private alasx loader + extracted private ANGLE libraries |
| 已关闭 | adb install -r observer APK 被拒绝 | 新 APK Chromium debug cert 与已安装 AOSP testkey 不同 | 比较证书后用同一已批准 testkey 重签；不禁用签名检查 |
| 已关闭 | observer APK 已安装但游戏仍不把它当可查询驱动 | 安装时遗漏 package visibility 标志 | 使用 `adb install -r -d --force-queryable`，再验证包、设置与实际 maps |
| 已关闭 | observer 主线程与 NULL swap TID 不同 | 手工启动遗漏 -force-gfx-st，Unity 创建 graphics worker | 所有 launch/restart 统一传 -force-gfx-st；不放宽线程门 |
| 已关闭 | 资源页面长期没有初始 typed frame | swap 1 时 IL2CPP 尚未 ready，下一次正常采样太晚 | 最多 120 swap 的有界 bootstrap retry，成功后恢复原 cadence |
| 已关闭 | 资源确认控件存在但没有 raycast_top | 三个资源动作未进入 reviewed raycast allowlist | 只增加三个精确 path，并用唯一性、generation、postcondition 验证 |
| 已关闭 | 28.1 GB 下载前空间不足 | 初始 userdata 16 GiB，仅约 13.4 GiB 可用 | 停容器、离线备份、精确 loop 校验、无损扩到 48 GiB |
| 操作缺口 | 下载监控终端有输出但预期 tee 文件未创建 | 外层 tee 使用无写权限用户 | 未来先验证 evidence 目录属主/权限，或让写入与采集在同一授权上下文执行 |
| 已关闭 | 完成下载后长期停在全屏 opening(Clone) | 资源和 LoginUI2 已完成，但覆盖层没有可确认的 raycast 动作 | 仅在完整下载会话/无失败/校验成功/无 fatal 的窄状态链下冷重启一次并验证新 PID |
| 预期行为 | ANGLE NULL 下 ADB/emulator 游戏截图全黑 | NULL renderer 不产生可视觉验收的 framebuffer | 使用 typed state、trace、generation、receipt 和 postcondition |
| 已关闭 | 把构建服务器当成 Redroid 运行资格机 | 构建机内核缺关键容器/FBE能力 | 构建与运行职责分离；AWS/合格 ARM Linux 做真实 boot/game 验证 |

Pastel 的详细证据和 x86 对照见
[x86 / ARM64 Pastel 生命周期诊断](x86-arm64-pastel-lifecycle-diagnostic-20260825.md)。

## 18. 不再重复的错误路径

- 不因一次失败立即删 out、cache、源码树或 userdata；
- 不重跑输入、代码、镜像和宿主状态都未改变的昂贵构建；
- 不用历史 AWS IP；
- 不用截图、OCR、模板、旧矩形或近似坐标替代 typed state；
- 不因黑帧关闭 ANGLE NULL；
- 不放宽 package/PID/freshness/main-thread/raycast/postcondition 边界；
- 不通过卸载游戏、清空 userdata 或关闭签名检查解决升级问题；
- 不把 host ext4 encrypt、dm-default-key 单项或属性字符串写成 FBE PASS；
- 不把 process-lived LLVM patch 写成完整 Pastel 修复；
- 不把旧容器 writable layer 中的二进制写成 OCI 已包含；
- 不点击 `raycast_top=null` 的 opening 覆盖层；
- 不通过禁用 WebView、加入 `--disable-gpu` 或改变前后台时序修复 ANGLE loader；这些路径已失败并回滚；
- 不把 RSA/BIO 次生日志继续当第一根因；
- 不把 build、boot、login boundary、ALAS workload 和 release promotion 混为一谈。

## 19. 证据与交接

当前 ARM64 登录现场证据：

~~~text
/srv/alas-runtime/evidence/arm64-login-20260826/
/srv/alas-runtime/evidence/arm64-login-fresh-20260826/
~~~

当前登录修复 observer 制品与构建归档：

~~~text
/srv/alas-runtime/tools/AngleLibraries-observer-arm64-login-bootstrap-fix-20260826-testkey.apk
/srv/android-archive/apks/alas-headless/AngleLibraries-observer-arm64-login-bootstrap-fix-20260826-testkey.apk
~~~

目录包含：

- 两个资源选择页的 before/after typed state 和 UI；
- 三个 exact action receipt；
- 扩容前后 df、loop/container/dm/resize2fs 记录；
- 最终 Activity、UI hierarchy、游戏包版本、ANGLE 设置；
- final login-boundary JSON。

本地相关实现：

- host probe：python/alas_headless/redroid_arm64_host.py
- Redroid backend：python/alas_headless/runtime_backend_redroid.py
- AOSP loader patch：integration/runtime/aosp-patches/0003-angle-apk-private-loader-suffix.patch
- SwiftShader patch：integration/runtime/aosp-patches/0004-swiftshader-keep-llvm-state-process-lived.patch
- ANGLE private package：scripts/wsl/package-angle-private-loader.sh
- observer bootstrap：patches/angle-g3/0012-android-null-bootstrap-snapshot-retry.patch
- resource allowlist：overlays/angle-g3/src/libANGLE/renderer/null/Il2CppNamespaceProbe.cpp

2026-08-26 本地相关回归：

~~~text
34 passed
~~~

完整测试曾得到 1704 passed、3 skipped、1 failed。唯一失败来自仓库外的脏 ALAS
live tree：DataKey_ForceCollect 消费面已漂移；它与本次 ARM/Redroid 变更无关，
不能靠放宽 ARM 校验来消除。

## 20. 下一轮重入顺序

1. 把 private loader 与 process-lived Pastel 修复封入 OCI，并从镜像导出验证精确哈希；
2. 用另一套 fresh isolated userdata 从首次启动起复验私有 NULL 下的 Agreement 转场；
3. 对当前 ARM 实例执行 Redroid backend 完整 lifecycle/recovery/cleanup；
4. 在合格自维护镜像上完成 native FBE 与 Direct Boot；
5. 到账号登录边界后等待新的账号操作授权；
6. 登录后先冻结一个代表性 workload；
7. 分开验证 W1 战斗因果、W2 日常 idle acceptance、W3 release soak；
8. 最后才讨论 ARM 支持 promotion、多实例和长期运行。

在上述项目完成前，准确状态是：

~~~text
ARM64 Redroid real-game pre-login path: passed
ARM64 Redroid engineering baseline: usable for continued qualification
ARM64 digest-only fresh OCI reproduction: blocked on sealing two runtime fixes
ARM64 ALAS workload qualification: not yet passed
ARM64 production/release readiness: blocked
~~~
