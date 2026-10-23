# 本地 WSL x86_64 KVM 开发与登录前验证

**后续更新：**正常停机已通过修复后的日常入口验证；使用方式和新证据见
[日常入口与停机修复](kvm-local-lifecycle-20260907.zh-CN.md)。下文关机失败
描述保留的是本页面最初那轮验证结果。

本页面面向 `ALAS-Android-Build` 中的独立 KVM 构建域。构建、发布和运行
使用 `alas-kvm-build`；只对挂载、systemd 管理和跨域只读检查提权。
不需要外部构建机，不读取或复用 Redroid 的源码、输出或 userdata。

## 当前候选

- 源码：Android 14 r75，锁定 manifest
  `e3b1a5113daede938922ed29c36806e0aac2ecb3`，1355 个项目。
- 构建：`kvm-local-full-j32-20260906-r1`，124778 个步骤完成，耗时 01:53:02。
  本轮复用该产物，没有重新构建或同步。
- 本地产物 release：`kvm-r75-x86_64-local-20260907-r1`。
- 本轮 AVD：`alas-kvm-local-r5`；原 `alas-kvm-local-r4` 保留。
- 本轮独立 ADB server：5043；实际发现的设备：`127.0.0.1:5589`。
  这些是本次身份，创建其他实例时需要重新发现和绑定。
- 游戏：9.7.10 / 9710 / x86_64。APK 与 libil2cpp 哈希匹配仓库锁定基线。
- 已验证可输出语义的 ANGLE：保留的 KVM adaptive r1，APK SHA-256
  `04281ef4afa52427192680e498dd1ba0ffdbb278a1b6029a21b7a1026fd8306b`。
  不能把另一个后端的 private-loader APK 当成这条 KVM 线的已验证驱动。

这是本地候选的运行验证，不是第二独立构建或字节级可复现声明，也不是
账号登录后的 ALAS 任务支持声明。

## 开始前

在 Windows 执行：

```powershell
& 'E:\Runtime\ALAS\Mount-ALASBuildDisks.ps1'
```

核对 `findmnt` 和 `blkid`：KVM 文件系统 UUID 必须为
`7febc493-864e-4e35-a01c-3090515de95e`，Redroid 必须为
`fd5ab68a-32b8-4fd7-987c-3b1c0575a12f`。不要在未挂载的底层目录写入。

2026-09-07 实际检查：WSL 约 58 GiB RAM，16 GiB swap，KVM 盘约 750 GiB
可用，Windows E 盘约 2.2 TiB 可用；KVM API 12 可用。再次构建前须重查
实际内存、磁盘、工具链和两个独立域的所有权。历史“20 GiB WSL / 等待内存升级”
描述已不能代表这台机器。

## 发布与新建 AVD

在拥有 KVM 树的 Linux 账号中设置本次路径：

```bash
REPO=/mnt/e/Disk0Merged/H/program/AzurLaneAutoScript-Headless-kvm-x86_64
DOMAIN=/mnt/e/Runtime/ALAS/android-build-domain.kvm.local.json
PEER=/mnt/e/Runtime/ALAS/android-build-domain.redroid.local.json
PROFILE=/srv/android-build/kvm/evidence/kvm-local-full-j32-20260906-r1/kvm-image-build-profile.json
export ALAS_PYTHON=/opt/alas-build-tools/bin/python
```

通过 `publish-kvm-runtime-bundle.sh` 发布到新的 release ID。已经存在的 release
只验证，不覆盖：

```bash
bash "$REPO/scripts/wsl/verify-kvm-runtime-bundle.sh" \
  "$DOMAIN" "$PROFILE" kvm-r75-x86_64-local-20260907-r1
```

新 AVD 使用 `provision-kvm-avd.sh DOMAIN PROFILE RELEASE_ID AVD_HOME AVD_NAME`。
它使用 release 自带的 `mkfs.ext4` 和 `e2fsck` 创建 48G ext4 userdata，
检查完成后再落盘。已有 AVD 的 userdata 不重建；配置模板缺失或不含
`image.sysdir.1` 时，在创建 userdata 前失败。

不要只设置 `disk.dataPartition.size=48G`，也不要复制其他 Android 版本的
userdata seed。配置容量不等于有效、可挂载的文件系统。

## 游戏冷启动和首次系统提示

使用仓库 `KvmBackend` 的正常启动或 `restart_game()` 路径，复用其显示、
ANGLE 路由、APK 预读和 Unity 参数处理。该路径现会在游戏启动前设置：

```text
settings put secure immersive_mode_confirmations confirmed
```

原因是全新 AVD 的 Android “Viewing full screen / GOT IT” 提示会覆盖游戏，
使 Unity 无法正常取得焦点。实际遇到时由 Android UI 树识别，未读取游戏像素。
设置只确认系统全屏教程，不表示接受游戏协议或登录账号。

每次游戏启动和恢复都必须带 Unity `-force-gfx-st`。通过 Python 构造 ADB argv
时复用 `encode_adb_shell_string_extra()`，不要丢失 ADB 二次解析所需的转义。
socket 存在或者 `ALAS_G3_BOOTSTRAP_READY` 都不能单独证明 observer 健康。
至少检查精确 package/PID、前台 Activity、主线程 flags、连续 generation、
状态新鲜度及所需按钮/UI surface。

本次首次协议由同包 `AgreementWebActivity` 的 DevTools DOM 唯一定位
`div.agree`，确认文字、可见性和顶层命中后点击，验证返回 MainActivity。
没有复制旧 consent、输入账号或使用截图坐标。

## 证据和后续范围

原始运行证据位于：

```text
/srv/android-build/kvm/evidence/local-runtime-20260907-r1
```

仓库留有[验证收据](../integration/runtime/local-kvm-20260907/receipt.json)和
[本次运行配置](../integration/runtime/local-kvm-20260907/runtime-config.json)。
收据分别记录每个已通过或未通过的能力，以及本地原始证据文件的摘要。

本次游戏重启改变 PID，Android 重启明确观察到 ADB 离线并改变 boot ID；
两者均保留安装和 userdata 标记。回退到保留镜像后 Android 可启动，切回
本地 release 后重新取得连续新鲜语义帧。回退前完整 AVD 备份位于：

```text
/srv/android-build/kvm/archive/images/avd-snapshots/local-r5-before-release-rollback-20260907
```

正常关机仍未通过：服务停止最终由 Emulator 自我强杀，guest poweroff 路径
出现 core-dump。两条路径都确认了最终进程退出后才切换镜像，并保留失败日志。
不要将“最终停下且数据仍可读取”写成“正常关机已通过”。

游戏报告的本次完整更新为 28.3GB。先下载约 1.2GB 后执行恢复与回退验证，
随后从剩余 27.1GB 续传，直到明确出现“更新完成，正在进入游戏...”。采样中
下载失败数均为 0。资源目录实际占用为 29867448 KiB。

最终前台是 `com.gsc.phone_login.PhoneLoginActivity`，手机号字段仍显示
“请输入手机号”，Android `Accounts: 0`，账号输入为零。完整下载后的再次
冷启动改变游戏 PID，并再次到达该空手机号登录页，资源及 userdata 标记保留。
这是原生 SDK 登录边界，不是 `LoginUI2(Clone)` 或登录后的 ALAS 资格。
SDK 登录页取得前台后 Unity generation 暂停；本次没有使用这些旧帧执行输入。

验证完成后已停止 r5，保留镜像、AVD 和资源。停机后再次执行真实 provision
入口，raw userdata 和 qcow2 的 inode、大小及修改时间均未变化。

构建证据仍保留在 `kvm-local-full-j32-20260906-r1`；两者分别描述构建和运行。
镜像、驱动、资源下载、进程恢复、Android 恢复和登录状态必须分别核对，
不能用其中一个结果代替另一个。

账号可用后，再在本候选上执行一个已支持的非战斗 ALAS 任务和一个已支持的
战斗任务。当前不修改 ALAS task/field 支持等级。
