# Android 双架构镜像基础实施手册

本文档用于在没有真实 ALAS 挂机负载的阶段，建立并逐步精简可运行游戏、支持游戏自行更新的 x86_64 与 ARM64 Android 镜像。

游戏不属于镜像。用户通过正常安装流程安装游戏；镜像必须支持：

- 单 APK 覆盖升级；
- split APK 覆盖升级；
- 游戏进程内下载资源、暂停后继续和重启后继续；
- 升级期间保留每个实例自己的 userdata；
- 游戏、Android 和宿主重启后的恢复；
- 失败后切回上一组镜像与 userdata 快照。

本文档不把“镜像能启动”“游戏能更新”和“ALAS 可长期挂机”混为一谈。当前最高允许状态是 `platform-and-update-qualified`，不得标记为 `production-ready`。

## 0. 当前实施边界

以下工作现在可以进行，不需要真实 ALAS 挂机数据：

- 固定 AOSP、ANGLE、构建工具和镜像制品身份；
- 构建 x86_64 与 ARM64 ANGLE/Unity 合同制品；
- 建立未精简的功能基线；
- 优化镜像体积、冷启动时间和无负载空闲占用；
- 删除不在产品配置中的示例、壁纸和非目标产品资产；
- 验证包升级、资源更新、userdata 持久化、重启和回滚；
- 在完整合同保护下逐项移除非必要组件。

以下工作必须等到可重复的真实 ALAS 任务切片存在后再进行：

- vCPU 数量、CPU affinity、cpuset 和 governor；
- NULL 刷新频率、Unity worker 数量；
- 基于 ALAS 工作负载的 PGO；
- 单机实例密度和超售比例。

机器可调度出多个 vCPU、空闲 CPU 较低或 Unity 合同更快，都不能替代真实 ALAS 工作负载证据。

## 1. 固定本次工作目录

以下命令在 PowerShell 中执行：

```powershell
$ImageRepo = 'H:\program\AzurLaneAutoScript-Headless-android-image-foundation'
Set-Location -LiteralPath $ImageRepo
git status --short --branch
$env:PYTHONPATH = Join-Path $ImageRepo 'python'
```

通过条件：

- 当前分支为 `codex/android-image-foundation`；
- 没有来源不明的工作区修改；
- 后续生成的大文件只进入已忽略的 `artifacts/`、`evidence/` 或仓库外构建目录。

## 2. 验证镜像策略边界

```powershell
python scripts/python/validate_android_image_policy.py `
  --policy integration/runtime/android-image-policy.example.json

python scripts/python/validate_runtime_lock.py `
  --lock integration/runtime/runtime-lock.example.json

python -m unittest tests.test_android_image_policy tests.test_runtime_artifacts `
  tests.test_runtime_backend tests.test_runtime_backends `
  tests.test_runtime_qualification_cli
```

通过条件：

- 策略验证输出 `"valid": true`；
- 游戏交付方式保持 `external-install`；
- 同时包含 `x86_64` 与 `arm64-v8a`；
- 包更新、资源更新、持久化、恢复和回滚门均存在；
- 工作负载相关调优仍在 deferred 集合中。

任何镜像变更开始前都必须先通过本步骤。策略 SHA-256 是本轮实验身份的一部分。

## 3. 建立未精简基线，不先删除服务

每个后端和 ABI 都建立独立基线，不允许把一种环境的结果转抄到另一种环境：

| 目标 | ABI | 用途 | 当前控制器状态 |
| --- | --- | --- | --- |
| KVM/Android Emulator | `x86_64` | x86 主资格线 | 可执行参考适配器 |
| Redroid | `x86_64` | x86 容器线 | plan-only |
| Redroid | `arm64-v8a` | 原生 ARM 主线 | plan-only |
| Cuttlefish/QEMU | `arm64-v8a` | ARM 兼容性线 | plan-only |

首个镜像必须是“足够完整、游戏更新链完整”的基线。不要为了得到一个漂亮的镜像体积数字，提前删除 WebView、PackageInstaller、DownloadProvider、keystore、SystemUI、AudioFlinger 或存储服务。

每个基线记录以下字段：

```text
AOSP manifest revision
product/release config/build variant
Android build fingerprint/API/ABI/security patch level
kernel or host Binder contract
system/vendor/product image SHA-256
provision profile SHA-256
NOTICE/SBOM SHA-256
冷启动时间（三次）
启动后十分钟的空闲 PSS/RSS/CPU
只读分区大小和 userdata 初始占用
```

这些记录属于镜像证据，不是 ALAS 性能结论。

### 3.1 固定源码并做构建宿主预检

源码锁是 `integration/runtime/android-image-source-lock.example.json`。它固定 AOSP tag/commit、Redroid local manifest commit、patch commit/patch set，以及两个 64 位 product；只有分支名或 tag 名而没有 40 位 commit 不算锁定。

```powershell
$env:PYTHONPATH = 'python'
python scripts/python/validate_android_image_source_lock.py `
  --source-lock integration/runtime/android-image-source-lock.example.json
python scripts/python/verify_android_image_source_remotes.py `
  --source-lock integration/runtime/android-image-source-lock.example.json `
  --output evidence/android-image-foundation/source-remotes.json
```

正式同步前在 Linux x86_64 构建机执行资源预检。400 GiB 可用空间、64 GiB RAM 和 `repo` 缺一项都返回非零，不允许绕过：

```bash
PYTHONPATH=python python3 scripts/python/preflight_redroid_build.py \
  --source-lock integration/runtime/android-image-source-lock.example.json \
  --root / \
  --output evidence/android-image-foundation/build-host-preflight.json
```

WSL 的 ext4.vhdx 是稀疏文件，Linux 内看到的空闲量不代表宿主盘还能增长多少。WSL 预检必须同时传入 VHD 所在 Windows 盘的真实 free bytes；省略该值会以 `backing_disk_verified` 失败：

```powershell
$backingFree = (Get-PSDrive -Name H).Free
wsl.exe -e sh -lc "cd /mnt/h/program/AzurLaneAutoScript-Headless-android-image-foundation && \
  PYTHONPATH=python python3 scripts/python/preflight_redroid_build.py \
  --source-lock integration/runtime/android-image-source-lock.example.json \
  --root / --backing-free-bytes $backingFree \
  --output evidence/android-image-foundation/build-host-preflight.json"
```

调用完整构建器时把同一值放入 `ALAS_BUILD_BACKING_FREE_BYTES`。这不是资源 override；低于锁定下限仍会失败。

### 3.2 同步、构建并生成供应链证据

构建入口只接受空目录，按 commit checkout local manifest/patch，输出 `repo manifest -r`，检查 patch driver 的隐性 `[ERROR]`，依次构建两个 ABI，并调用 AOSP 官方 `m sbom`：

```bash
./scripts/wsl/build-redroid-images.sh \
  integration/runtime/android-image-source-lock.example.json \
  /srv/android/redroid-14-r75 \
  /srv/android/evidence/redroid-14-r75-build-1
```

必须在干净、独立输出目录再执行第二次，随后比较两次 payload：

```bash
./scripts/wsl/build-redroid-images.sh \
  integration/runtime/android-image-source-lock.example.json \
  /srv/android/redroid-14-r75-rebuild \
  /srv/android/evidence/redroid-14-r75-build-2

PYTHONPATH=python python3 scripts/python/compare_android_image_builds.py \
  --first /srv/android/evidence/redroid-14-r75-build-1/provenance-x86_64.json \
  --second /srv/android/evidence/redroid-14-r75-build-2/provenance-x86_64.json \
  --output /srv/android/evidence/reproducibility-x86_64.json
PYTHONPATH=python python3 scripts/python/compare_android_image_builds.py \
  --first /srv/android/evidence/redroid-14-r75-build-1/provenance-arm64-v8a.json \
  --second /srv/android/evidence/redroid-14-r75-build-2/provenance-arm64-v8a.json \
  --output /srv/android/evidence/reproducibility-arm64-v8a.json
```

provenance 必须同时绑定源码锁、resolved manifest、fingerprint、安全补丁、`system.img`/`vendor.img`、AOSP SPDX 2.3 SBOM、NOTICE 与 installed-files；inventory 中发现游戏包名会直接失败。源码锁还逐个固定 local manifest 引入的五个 Redroid 子项目；构建器用 `extend-project` overlay 锁 commit，并在 sync 后逐项核对 `repo manifest -r`，不能让上游 `master` 漂移。当前仓库已有可执行构建入口，但尚未在满足资源下限的宿主完成上述两次全量构建，因此仍不得称为可复现发布制品。

### 3.3 确定性 OCI 打包

`build-redroid-images.sh` 在每个 product 完成后自动调用 `package-redroid-oci.sh`。打包器只读挂载 system/vendor，按路径排序、统一 `SOURCE_DATE_EPOCH`、owner/group 和 pax 时间字段，保留 xattr，生成单平台 OCI layout archive；OCI config 固定 Redroid entrypoint，并写入 ABI、fingerprint、源码锁和 `game-delivery=external-install` labels。archive 同样进入 provenance。

单独调试打包器时：

```bash
sudo ./scripts/wsl/package-redroid-oci.sh \
  out/target/product/redroid_arm64_only/system.img \
  out/target/product/redroid_arm64_only/vendor.img \
  arm64-v8a <source-lock-sha256> '<build-fingerprint>' <source-date-epoch> \
  evidence/redroid-arm64-v8a.oci.tar \
  evidence/redroid-arm64-v8a.oci-build.json

docker load --platform linux/arm64 -i evidence/redroid-arm64-v8a.oci.tar
```

同一 rootfs layer、源码锁、fingerprint 和 epoch 必须生成相同 archive SHA-256 与 manifest digest。合成 rootfs 已在 Docker 29 containerd image store 上分别完成 x86_64/ARM64 `load + inspect` 冒烟；这证明打包格式可消费，不代表真实 Android product 已构建或启动。

### 3.4 FBE 的 userdata 模型迁移

Redroid stock 的目录 bind 不能满足 Android native FBE。自维护线必须把每个实例的 userdata 改成独立块设备，禁止直接在宿主根分区上启用特性或就地试验：

1. 在实验宿主创建可丢弃的独立 userdata 块卷，不使用生产 `/var/lib/redroid/data`；
2. ext4 必须具备 `encrypt` feature，宿主内核必须有 `CONFIG_FS_ENCRYPTION=y`；当前 ARM 宿主内核满足，根 ext4 不满足；
3. 将该设备以固定容器内路径提供给 Redroid，不再 `-v host-dir:/data`；
4. 自维护 product 生成 userdata/fstab 合同，`/data` 使用 AOSP 推荐的 `fileencryption`，KeyMint 在 `early_hal`、vold 在 `post-fs-data` 前可用；
5. 首次格式化只允许在空实验卷上执行；现有 userdata 必须走备份、校验、恢复迁移，FBE on-disk format 不能作为普通 OTA 原地切换；
6. 通过五路 native FBE 门后，还要用测试凭据重启，验证 Direct Boot 时 DE 可用、CE 未解锁，解锁后 CE 与更新 userdata 恢复；
7. 镜像回退必须同时恢复与旧镜像匹配的块卷快照，不能把新 FBE 卷直接交给不兼容旧镜像。

在以上链路实测前，`device-encrypted-storage` 必须保持 fail；宿主 LUKS/fscrypt 只能作为额外的 at-rest 控制，不能冒充 Android FBE/Direct Boot。

可先在 Linux/Redroid 宿主制备一个完全隔离的空实验卷，验证块设备和 ext4
`encrypt` 前置能力。脚本只允许创建原本不存在的新镜像文件，拒绝生产 `/data`
路径、非空或已挂载目录，并在失败时删除本轮新建镜像：

```bash
sudo ./scripts/wsl/provision-redroid-userdata-image.sh \
  --image /var/lib/redroid-volumes/fbe-lab/userdata.img \
  --size-mib 1024 \
  --mount /mnt/redroid-userdata-fbe-lab \
  --output /var/lib/redroid-volumes/fbe-lab/probe.json
PYTHONPATH=python python3 scripts/python/qualify_redroid_userdata_volume.py \
  --probe /var/lib/redroid-volumes/fbe-lab/probe.json \
  --output evidence/android-image-foundation/userdata-volume-host-qualification.json
```

该资格结果的上限固定为 `host-volume-qualified`，并显式记录
`android_fbe_proven=false`、`direct_boot_proven=false`。只有把这个卷交给自建
Redroid 的 `/data` fstab、完成 Android 五路 FBE 门和 Direct Boot/CE 解锁恢复实验后，
才能提升为 Android FBE 证据。

## 4. 构建双架构 ANGLE 制品

以下命令在 WSL 中执行。ANGLE 源码和 depot_tools 放在仓库外，避免污染 Git：

```bash
cd /mnt/h/program/AzurLaneAutoScript-Headless-android-image-foundation
export ALAS_ANGLE_WORKSPACE="${HOME}/src/alas-headless-angle"
export ALAS_DEPOT_TOOLS_DIR="${HOME}/src/depot_tools"

./scripts/wsl/bootstrap-angle.sh
./scripts/wsl/apply-angle-patches.sh
./scripts/wsl/build-gles-contract.sh
./scripts/wsl/apply-angle-g3-patches.sh

ALAS_ANGLE_TARGET_CPU=x64 \
  ./scripts/wsl/build-angle-null-observer.sh

ALAS_ANGLE_TARGET_CPU=arm64 \
  ./scripts/wsl/build-angle-null-observer.sh
```

通过条件：

- 两个 APK 分别来自 `AndroidNullObserverX64` 和 `AndroidNullObserverArm64`；
- 两者都有 SHA-256，不能因文件名相同而覆盖；
- revision 等于仓库 `ANGLE_REVISION`；
- x86 和 ARM 的失败独立记录，不能用一个架构的通过替代另一个。

## 5. 构建双架构 Unity 合同 APK

使用 Unity `2022.3.62f3`。默认仍构建兼容的 x86_64 输出：

```powershell
$Unity = 'H:\Unity\Editor\Unity.exe'
Set-Location -LiteralPath $ImageRepo

Remove-Item Env:ALAS_UNITY_TARGET_CPU -ErrorAction SilentlyContinue
& $Unity -batchmode -quit `
  -projectPath (Join-Path $ImageRepo 'unity\HeadlessContract') `
  -executeMethod Alas.Headless.Contract.Editor.BuildAndroidPlayer.Build `
  -logFile -
```

输出：`unity/HeadlessContract/Build/HeadlessContract.apk`。

ARM64 构建：

```powershell
$env:ALAS_UNITY_TARGET_CPU = 'arm64'
& $Unity -batchmode -quit `
  -projectPath (Join-Path $ImageRepo 'unity\HeadlessContract') `
  -executeMethod Alas.Headless.Contract.Editor.BuildAndroidPlayer.Build `
  -logFile -
Remove-Item Env:ALAS_UNITY_TARGET_CPU
```

输出：`unity/HeadlessContract/Build/HeadlessContract-arm64.apk`。

通过条件：

- 构建日志中的 `targetCpu` 与目标一致；
- APK 的 `lib/` ABI 与目标一致；
- 两个 APK 的 SHA-256 被写入本轮制品清单。

## 6. 执行无 ALAS 负载的平台合同

对每个真实启动的镜像依次执行：

1. Q1：三次冷启动，ADB、PackageManager 和 framework ready；
2. G1：ANGLE NULL GLES 合同；
3. G2：Unity 生命周期、场景、readback 和前后台切换；
4. G3：observer schema、freshness、foreground 和拒绝非法请求；
5. 游戏恢复门：游戏进程重启后 PID 更新且完整指纹不变；
6. Android 恢复门：观察到 ADB offline，再要求 framework、游戏和 observer 恢复。

G1 示例：

```powershell
.\scripts\windows\run-g1-probe.ps1 `
  -Serial $Serial `
  -AngleApk $AngleApk `
  -ProbeApk $ProbeApk `
  -OutputRoot (Join-Path $ImageRepo 'evidence\android-image')
```

G2 示例：

```powershell
.\scripts\windows\run-g2-unity.ps1 `
  -Serial $Serial `
  -DriverMode null `
  -AngleApk $AngleApk `
  -UnityApk $UnityApk `
  -UnityCommandLine '-force-gfx-st' `
  -OutputRoot (Join-Path $ImageRepo 'evidence\android-image')
```

当前 `qualify_runtime.py` 只有 KVM 和 external-ADB 是可执行参考适配器。Redroid 与 ARM64-QEMU 必须等相应 adapter 实现后再使用 `--execute`，不得绕过 fail-closed 门。

## 7. 验证游戏安装和包升级能力

当前仓库提供 `probes/android-update-lab` 作为外置、测试专用应用。它不包含游戏，也不连接 ALAS 工作负载。先构建两版单 APK、AAB/APKS、同签名升级包和错签负例：

```powershell
.\scripts\windows\build-android-update-lab.ps1
```

启动完全独立的资格 AVD（不会复用游戏 AVD）：

```powershell
.\scripts\windows\start-android-image-foundation-avd.ps1 -CreateIfMissing
```

再执行更新资格门。合成 HTTP 载荷通过 ADB reverse 进入设备；Android 重启后脚本会重建该测试传输，它不代表生产游戏下载网络：

```powershell
$env:PYTHONPATH = Join-Path $ImageRepo 'python'
python scripts/python/qualify_android_update_lab.py `
  --serial emulator-5620 `
  --adb F:\platform-tools\adb.exe `
  --java D:\java\jdk-24\bin\java.exe `
  --bundletool artifacts\bundletool-all-1.18.3.jar `
  --artifacts artifacts\android-update-lab `
  --output evidence\android-image-foundation\update-lab-api32-x64
```

本步骤验证 Android 镜像能力，不要求安装真实游戏，也不要求登录。

准备两个使用同一测试证书签名的测试包版本：

- v1：versionCode 1，写入一份内部 userdata 和一份外部资源哨兵；
- v2：versionCode 2，包含一次可验证的数据迁移；
- v2 split：相同应用另做 base + ABI/config split 版本。

在一次性 userdata 克隆中依次验证：

```text
全新安装 v1
写入两个哨兵
adb install -r 升级到 v2
验证签名连续、versionCode=2、两个哨兵保留、迁移完成
恢复升级前快照
adb install-multiple -r 安装 v2 split 集合
验证 split 列表、ABI 选择、哨兵和迁移
用不同签名的 v2 做负例，必须被拒绝且 v1 数据仍可用
```

还要验证以下失败条件：

- 磁盘空间不足；
- 安装过程中 Android 重启；
- APK 或任一 split 哈希不符；
- versionCode 倒退；
- 包签名变化。

通过条件：升级成功路径保留 userdata；所有负例 fail closed；旧镜像和升级前 userdata 快照仍可启动。真实游戏 APK 不进入仓库或公开 Release。

### 当前实现

成对单 APK、ABI split、同签名迁移包、错签负例和自动化执行器已经位于
`probes/android-update-lab` 与 `scripts/python/qualify_android_update_lab.py`。x86_64
和 ARM64 的完整实验都已有通过证据。它们始终使用独立测试包名和测试证书，
不会复用或提交真实游戏包；发布门仍要求每个 ABI 分别提供自己的最新实验清单。

## 8. 验证游戏内资源更新能力

本步骤同样使用合成下载器，不需要 ALAS，也不把资源烘焙进镜像。

测试数据由本地 HTTP 服务生成，至少包含：

- 一个大文件；
- 数千个小文件；
- manifest 和逐文件 SHA-256；
- epoch 1 到 epoch 2 的增量集合。

按以下顺序执行：

1. 下载 epoch 1，校验全部哈希；
2. 下载到一半时杀死应用，重新启动后继续；
3. 下载到一半时重启 Android，恢复后继续；
4. 注入低磁盘条件，必须明确失败且不破坏 epoch 1；
5. 下载 epoch 2 到新 staging 路径，完整校验后原子提升；
6. 回滚渠道指针到 epoch 1；
7. 验证一个实例的下载上层不会写入另一个实例的 userdata。

公共资源若未来需要共享，只能是经过清单审查的内容寻址只读层；每个实例必须有自己的 writable upper。不得共享整个 `/data`、账号数据库、shared preferences、keystore 或用户目录。

### 当前缺口门

合成下载器、故障注入器和资源 promotion 工具尚未进入仓库。在它们完成前可以测网络和存储基线，但不能宣称镜像已通过资源更新门。

## 9. 开始逐项精简

任何删除候选之前，先执行受保护能力和无负载基线审计：

```powershell
python scripts/python/audit_android_foundation.py `
  --serial emulator-5620 `
  --adb F:\platform-tools\adb.exe `
  --policy integration/runtime/android-image-policy.example.json `
  --update-evidence evidence\android-image-foundation\update-lab-api32-x64\manifest.json `
  --output evidence\android-image-foundation\foundation-audit-api32-x64.json `
  --sample-seconds 600
```

`--sample-seconds 600` 是发布候选的十分钟无负载基线。短样本只用于开发调试，不能用于体积/密度或挂机性能结论。

只有未精简基线通过第 2、6、7、8 步后才允许精简。每次实验只改变一个产品包、一个服务或一组明确绑定的资源，并使用新的 provision-profile SHA-256。

以下能力默认受保护，删除申请必须先修改策略并给出独立证据：

```text
Android framework、ART、PackageManager、PackageInstaller
DownloadProvider、WebView、网络、DNS、TLS CA、时间同步
keystore、CE/DE storage、外部应用存储、低空间信号
SettingsProvider、SurfaceFlinger、HWUI/EGL、输入、音频框架
logcat、tombstone 和崩溃证据
```

优先从产品配置中根本不需要的示例应用、壁纸、演示内容和非目标设备产品资产开始；不要通过运行后 `pm disable` 制造“已经精简”的假象。

每次提交都记录：

```text
变更前后镜像字节数
三次冷启动中位数
十分钟空闲 PSS/RSS/CPU
包升级与资源更新耗时
Q1/G1/G2/G3/更新/恢复/回滚结果
x86_64 与 ARM64 是否分别通过
```

若任何功能门失败，隔离该候选，不把它与其他删除项合并后继续试。

每次只允许一个有明确假设和精确 removal allowlist 的精简变更。基线/候选 installed-files、provenance、受保护能力、G1/G2/G3、更新和真实镜像回退证据必须一起提交给门禁：

```powershell
python scripts/python/qualify_android_image_slimming.py `
  --change <one-change.json> `
  --baseline-provenance <baseline-provenance.json> `
  --candidate-provenance <candidate-provenance.json> `
  --baseline-inventory <baseline-installed-files.txt> `
  --candidate-inventory <candidate-installed-files.txt> `
  --audit <candidate-foundation-audit.json> `
  --gles <candidate-g1.json> --unity <candidate-g2.json> `
  --observer <candidate-g3.json> --update <candidate-update.json> `
  --rollback <candidate-image-rollback.json> `
  --output <one-change-qualification.json>
```

门禁拒绝未声明删除、allowlist 中未实际发生的删除、payload 未减小、跨源码锁比较，以及任何功能证据或 scope 不通过。它只证明该次变更在平台合同上可接受，不代表 ALAS 挂机性能变好。

## 10. 发布规则

生成双架构候选清单时，即使 ARM64 尚未具备运行宿主也要提供 ARM64 合同 APK；缺少镜像、设备审计或更新证据会自动阻止 promotion：

```powershell
python scripts/python/create_android_image_release.py `
  --policy integration/runtime/android-image-policy.example.json `
  --source-lock integration/runtime/android-image-source-lock.example.json `
  --x86-64-contract-apk unity\HeadlessContract\Build\HeadlessContract.apk `
  --x86-64-angle-apk <x86-observer-angle.apk> `
  --x86-64-image-identity <x86-oci-identity.json> `
  --x86-64-gles-evidence <x86-gles-evidence.json> `
  --x86-64-unity-evidence <x86-unity-evidence.json> `
  --x86-64-observer-evidence <x86-observer-evidence.json> `
  --x86-64-audit <x86-foundation-audit.json> `
  --x86-64-update-evidence <x86-update-manifest.json> `
  --x86-64-build-provenance <x86-provenance.json> `
  --x86-64-reproducibility-evidence <x86-reproducibility.json> `
  --x86-64-rollback-evidence <x86-image-rollback.json> `
  --arm64-contract-apk unity\HeadlessContract\Build\HeadlessContract-arm64.apk `
  --arm64-angle-apk <arm64-observer-angle.apk> `
  --arm64-image-identity <arm64-oci-identity.json> `
  --arm64-gles-evidence <arm64-gles-evidence.json> `
  --arm64-unity-evidence <arm64-unity-evidence.json> `
  --arm64-observer-evidence <arm64-observer-evidence.json> `
  --arm64-audit <arm64-foundation-audit.json> `
  --arm64-update-evidence <arm64-update-manifest.json> `
  --arm64-build-provenance <arm64-provenance.json> `
  --arm64-reproducibility-evidence <arm64-reproducibility.json> `
  --arm64-rollback-evidence <arm64-image-rollback.json> `
  --arm64-userdata-volume-evidence <arm64-host-volume-qualification.json> `
  --output evidence\android-image-foundation\release-candidate.json `
  --require-promotable
```

ARM64 Redroid 开始前先在目标 ARM64 Linux 宿主执行：

```bash
export ALAS_REDROID_IMAGE='registry.example/redroid@sha256:<digest>'
./scripts/wsl/probe-redroid-arm64-host.sh
```

当前 x86 Windows 主机或未运行 Docker/binderfs 的环境应返回 `blocked`；不得把预检失败改写成 plan PASS。

Redroid 使用 OCI 镜像时，先从运行容器只读采集 digest、架构、端口和 `/data` 挂载身份：

```powershell
python scripts/python/capture_redroid_image_identity.py `
  --ssh C:\Windows\System32\OpenSSH\ssh.exe `
  --target root@<arm-host> `
  --container redroid-arm64 `
  --output evidence\android-image-foundation\redroid-arm64-image-identity.json
```

更新实验中的 Android restart 对 Redroid 应使用容器 restart hook，并以 `ro.runtime.firstboot` 变化作为完成证明；三轮独立 restart 可执行：

```powershell
python scripts/python/qualify_redroid_restart.py `
  --serial 127.0.0.1:15555 `
  --adb F:\platform-tools\adb.exe `
  --ssh C:\Windows\System32\OpenSSH\ssh.exe `
  --target root@<arm-host> `
  --container redroid-arm64 `
  --rounds 3 `
  --output evidence\android-image-foundation\redroid-restart-arm64-3round.json
```

在真实 ALAS 工作负载出现前，只允许以下发布状态：

```text
built
  -> boot-qualified
  -> platform-qualified
  -> platform-and-update-qualified
```

发布目录或 OCI registry 只使用内容 digest。`latest` 可以作为人类可读别名，但运行时锁、证据和回滚都不得依赖它。

真实镜像回退必须使用与生产数据隔离的临时 `/data`，并显式传入两个不同 digest：

```bash
sudo ./scripts/wsl/qualify-redroid-image-rollback.sh \
  registry.example/redroid@sha256:<previous> \
  registry.example/redroid@sha256:<candidate> \
  arm64-v8a 15557 1280 720 240 \
  > evidence/android-image-foundation/redroid-image-rollback-arm64.json
```

脚本验证旧镜像写入、候选镜像继承、带 xattr/ACL/SELinux 的 `/data` 快照恢复，以及再次启动旧镜像；临时目录不在 `/var/lib/redroid/rollback-lab.*` 时拒绝删除。x86_64 必须在 x86_64 Redroid 宿主用同一脚本独立执行，不能复用 ARM 结果。

每个发布候选至少包含：

- 源 revision 和构建命令；
- system/provision/ANGLE/合同 APK SHA-256；
- SBOM、NOTICE 和许可证审查结果；
- x86_64 与 ARM64 独立门禁清单；
- 更新实验和回滚证据索引；
- 已知限制；
- 明确的 `alas_workload_qualified=false`。

发布清单对每份 G1/G2/G3、审计、更新、OCI identity、provenance、复现和回退 JSON 记录绝对路径、字节数与 SHA-256；缺少文件身份会 fail。清单字段摘要不能替代原始证据哈希。

游戏 APK、游戏资源、账号 userdata 和包含账号信息的证据不得进入公开制品。

## 11. 本阶段完成定义

满足以下全部条件，才算完成“不依赖真实 ALAS 数据的镜像优化阶段”：

- x86_64 与 ARM64 镜像从固定源码和工具链可重复构建；
- 两个架构分别通过 Q1/G1/G2/G3；
- 单 APK、split APK、签名负例和 userdata migration 通过；
- 资源中断、Android 重启、低磁盘、提升和回滚通过；
- 至少一次真实镜像回滚演练通过；
- 所有精简变更都有独立收益与功能门证据；
- 发布制品有 SHA-256、SBOM、NOTICE 和隐私检查；
- 没有进行或暗示任何依赖真实 ALAS 工作负载的调优；
- 状态最高为 `platform-and-update-qualified`。

## 12. 当前实现与实测状态（2026-08-12）

本 worktree 已完成以下不依赖真实 ALAS 挂机数据的基础工作：

- 策略 `compat-foundation-v1` 校验通过，SHA-256 为 `622d7fb202d020fda5ad87291c8fb36f546af0562a927ea6df9c461a83844233`；
- 当前仓库全量测试 `481 passed`；
- x86_64 与 ARM64 Unity 合同 APK 均已构建并确认只含目标 ABI；当前 SHA-256 分别为 `6030c2d4ba41b7b29150490b3d977991e01084a83e523b6a64d98fdfd5a3ceb0` 与 `dcd02e4aa10fb972ea9d7ba20c54b46ccab9f016308d8634d0207af4cbf51a61`；
- 最新 observer ANGLE x86_64/ARM64 APK 已从固定 ANGLE revision 交叉构建，SHA-256 分别为 `98941a4fb1fc99b201cde6b86498da6c132a74c0cf5d60b4b72fcb3dbff627fe` 与 `8670115d326ddc39ccc5ae2cd36352e7377c3c23f8360aa358649ec959e40ccb`；observer ABI 由编译目标生成，不再硬编码 x86_64；
- x86_64 更新实验完整通过：错签拒绝、单 APK、ABI split、userdata migration、进程中断续传、低空间、Android 重启续传、原子提升与回滚；
- 更新实验 APK 的四个资格哈希与重建后清单完全一致；
- API 32 x86_64 专用 AVD 的 21 项受保护能力全部通过；
- 三轮禁用 snapshot 的冷启动为 `20.234 / 23.000 / 24.047 s`，中位数 `23.000 s`，userdata 哨兵三轮保留；
- 卸载全部合成合同包后的 600 秒 idle 样本：设备 CPU busy `0.207%`、Used RAM `980245 KiB`、Free RAM `994255 KiB`。这些数值只是未精简基线；
- 当前 x86 G1 NULL GLES、G2 Unity 与 G3 observer 合同全部通过；G3 包含 32/32 IL2CPP allowlist、`flags=15`、typed UI stage 100、唯一可点击语义按钮、点击后的 semantic generation、场景 generation、Home 陈旧动作拒绝与恢复后 freshness。测试脚本会保存并恢复 Android secure `immersive_mode_confirmations`，避免系统首次沉浸提示遮挡 ADB 点击；
- ARM64 宿主 `47.77.183.3` 上的 digest-pinned Redroid Android 12/API 31 基线已通过 ARM G1/G2/G3；G1 普通 Activity 的逻辑 surface 为 `1280×648`，Unity 沉浸式 surface 为 `1280×720`；
- ARM64 更新实验完整通过，并实际安装 `split_config.arm64_v8a.apk`；Redroid 容器 restart 前后 `ro.runtime.firstboot` 改变，随后完成资源续传和指针回滚；
- ARM64 三轮 Redroid restart 为 `17.750 / 17.828 / 18.141 s`，每轮 OCI digest 不变且 `/data` sentinel 保留；
- ARM64 卸载合成包后的 600 秒 idle 样本为 CPU busy `0.195%`、Used RAM `1078446 KiB`、Free RAM `5982526 KiB`，只是未精简基线；
- ARM64 OCI identity 已固定到 `redroid/redroid@sha256:d3fb6daeaed9a7c98b05d649ed925ad9c6f45f578d1fd8c386951595d53778b2`，ADB 只绑定宿主 `127.0.0.1:5555`，`/data` 使用独立持久化挂载；
- ARM64 已完成一次独立临时 `/data` 的真实 OCI 回退：Android 12 digest `d3fb…78b2` → Android 13 digest `5a42…c13b` → 恢复快照 → Android 12 digest；候选与回退后的 sentinel 均保留且实验目录清理，证据为 `redroid-image-rollback-arm64-20260812.json`；
- 自维护源码锁已固定 AOSP `android-14.0.0_r75`、Redroid 14 local manifests、对应 patch set 与五个 transitive Redroid 项目 commit，八组远端 ref/commit 实时核验通过，源码锁 SHA-256 为 `3e8d154222c164d41ba045fac14335ece1d3546338e62e8de089bf57abbf65eb`；
- 双 ABI 构建入口、AOSP SPDX 2.3 SBOM/NOTICE provenance、installed-files 游戏制品负检、两次构建 payload 一致性门与 release 强制绑定均已实现；
- 确定性 Redroid OCI layout/archive 生成器已实现；同输入双次字节一致性单测通过，合成 x86_64 与 ARM64 archive 均已由 Docker 29 实际 load/inspect，且不包含游戏；
- digest-pinned stock Redroid 14/API 34 ARM64 基线已独立通过 G1/G2/G3 与完整更新实验，安全补丁为 `2024-05-05`；600 秒无游戏/无 ALAS 空闲基线为 CPU busy `0.222%`、Used RAM `1078133 KiB`，只用于该镜像基线记录；
- Android 14 ARM64 受保护能力仍为 20/21，唯一失败是 `device-encrypted-storage`。官方 Redroid 14 device 产品配置明确设置 `PRODUCT_BUILD_USERDATA_IMAGE := false`，宿主目录直接 bind 到 `/data`，所以 FBE 不能靠属性或普通 fstab overlay 修复；
- FBE 受保护能力门已改为五路复合验证：`ro.crypto.state=encrypted`、`ro.crypto.type=file`、PackageManager FBE feature=true、`sm get-fbe-mode=native` 和 mount/vold service 存在；缺任一项或仅为 `emulated` 都失败；
- Android 12 digest `d3fb…78b2` → Android 14 digest `0a61…69aa` → 恢复快照 → Android 12 的真实回退已通过；证据同时验证候选 fingerprint/API 34 与恢复后的旧 fingerprint/API 31，避免用可空的 `ro.runtime.firstboot` 冒充候选身份；
- OCI identity 现在分别记录 registry/index digest 与架构平台 manifest digest；运行配置仍必须用 index digest，tag 或缺失平台 descriptor 都无法通过发布门；
- ARM64 宿主已用全新 512 MiB 稀疏镜像实际完成独立 loop block、ext4 `encrypt`、
  `rw,nodev,nosuid` 临时挂载与自动释放验证；资格证据上限固定为
  `host-volume-qualified`，并明确 `android_fbe_proven=false`、
  `direct_boot_proven=false`。生产 `/var/lib/redroid/data` 未被挂载或修改；
- 与干净提交绑定的 fail-closed 候选清单中，双架构 G1/G2/G3 和更新证据均闭环；
  仍保留自建 provenance/reproducibility、x86 OCI 回退以及 ARM FBE blocker。

当前仍然 fail-closed 的项目：

- 当前 Redroid `/data` 是宿主 ext4 bind mount，镜像没有 `ro.crypto.type=file` 或 FBE fstab 合同；ARM 受保护能力为 20/21，`device-encrypted-storage` 必须保持 fail，不能通过启动参数豁免；
- 当前生产 Android 12 ARM 基线的安全补丁级别为 `2021-10-05`；已验证的 stock
  Android 14 候选也仅为 `2024-05-05`。二者都需要由自维护镜像线替代，不能作为长期发布基线；
- 当前 x86 镜像是内容哈希固定的 SDK API 32 基线，ARM 是 digest 固定的 stock Redroid 基线；二者都不是本项目从固定 AOSP/Redroid 产品配置构建出的精简镜像，尚未删除任何系统服务；
- 当前 WSL 已安装 `repo` launcher，系统、架构、Git、Repo 项通过；VHD 内部虽报告约 621 GiB 可用，但 VHD 所在 H 盘实际仅约 218.5 GiB 可用，低于 400 GiB 下限；RAM 仅 `20971327488` bytes，也低于 64 GiB 下限。因此没有启动完整 sync/build，也没有生成伪 SBOM/provenance；
- x86_64 的真实 Redroid OCI 镜像回退尚未执行；ARM 回退证据不能替代 x86 证据；
- worktree 未提交时，发布清单还会附加 `source:dirty-worktree` blocker；最新干净候选
  的实际 blocker 是双架构 build provenance/reproducibility、x86 OCI 回退和 ARM FBE；
- 在支持 FBE、更新安全补丁且可复现的自维护 AOSP/Redroid 构建入口补齐前，双架构 release promotion 必须保持 `blocked`。

冷启动复测命令：

```powershell
python scripts/python/qualify_android_cold_boot.py `
  --adb F:\platform-tools\adb.exe `
  --emulator H:\Unity\Editor\Data\PlaybackEngines\AndroidPlayer\SDK\emulator\emulator.exe `
  --avd-home H:\AndroidAVDImageFoundation `
  --avd-name alas_update_lab_api32_x64 `
  --console-port 5620 `
  --rounds 3 `
  --output evidence\android-image-foundation\cold-boot-api32-x64.json
```
