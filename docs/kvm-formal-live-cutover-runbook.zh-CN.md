# KVM 不可变 runtime 正式切换

> 历史旧机手册：以下路径、`weipa` 身份、共享 hot-output 发布入口和既有 service
> 名称只对应 2026-08-26/27 保留现场，不是当前新构建机的日常开发流程。当前构建必须使用
> `alas-kvm-build`、`alas-kvm-run x86_64 -- bash` 和 v3 独立 build-domain。本手册仅在明确
> 审核旧机正式切换时使用；仓库整理本身不会执行这些命令或修改旧机 AVD/userdata/service。

这条流程只切换 KVM。它不会启动 Redroid，也不会从 Redroid 工作树读取运行文件。
发布和 live cutover 是两个不同阶段：先把 hot output 发布成不可变 release，确认完整后，
才允许在停机状态保存整个 AVD 并切换 `image.sysdir.1`。

## 固定输入

以下变量必须替换为构建机上的真实绝对路径。domain、profile 和 runtime config 应当按
release 留存，不能在后续修改同一个文件后仍把旧 release 称为可回退。

```bash
REPO=/opt/alas-headless/kvm-image-control
KVM_DOMAIN=/etc/alas-headless/kvm/kvm-r75-x86_64-v2/android-build-domain.json
REDROID_DOMAIN=/etc/alas-headless/redroid/android-build-domain.json
KVM_PROFILE=/etc/alas-headless/kvm/kvm-r75-x86_64-v2/kvm-image-build-profile.json
RUNTIME_CONFIG=/etc/alas-headless/kvm/kvm-r75-x86_64-v2/runtime-config.json
RELEASE_ID=kvm-r75-x86_64-v2
UNIT=alas-headless-kvm.service
PREVIOUS_UNIT=alas-kvm-v7-split-bootstrap-r2-path.service
RUN_AS_USER=weipa
ALAS_PYTHON=/srv/android-runtime/kvm/alas-headless/toolchains/control-venv-3.12.11/bin/python
EVIDENCE=/srv/android-archive/kvm/evidence/kvm-r75-x86_64-v2
SNAPSHOT=/srv/android-archive/kvm/images/avd-snapshots/pre-kvm-r75-x86_64-v2
PHASE_MARKER=$EVIDENCE/live-cutover-phase.json
PREVIOUS_UNIT_ARCHIVE=$EVIDENCE/previous-unit.json
CUTOVER_LOCK=/run/alas-headless/kvm-live-cutover.lock
```

正式合同固定：console port `5588`、TCP transport `127.0.0.1:5589`、独立 ADB
server port `5043`。管理命令需要 root，以便安装 system unit、读取完整 `/proc` 和确认
listener PID；emulator 与 ADB server 则以显式非 root 用户运行。

## 1. 发布并复验

在轮换 KVM hot output 之前执行：

```bash
"$REPO/scripts/wsl/publish-kvm-runtime-bundle.sh" \
  "$KVM_DOMAIN" "$REDROID_DOMAIN" "$KVM_PROFILE" "$RELEASE_ID"

"$REPO/scripts/wsl/verify-kvm-runtime-bundle.sh" \
  "$KVM_DOMAIN" "$KVM_PROFILE" "$RELEASE_ID"
```

release 已存在时，publisher 会拒绝覆盖；只运行 verifier，不应删除或重建同名目录。

现场已确认 `ALAS_PYTHON` 的 logical venv 路径如上；canonical target 是
`/srv/android-runtime/kvm/alas-headless/toolchains/python/cpython-3.12.11-linux-x86_64-gnu/bin/python3.12`，
当前期望 SHA-256 为 `ccc93c55c24bb92866cc2f9eff61b124abf5d1ee6c8da0ef9b5eed4d78a21f07`。
正式操作前仍须只读复验，不能回退到 PATH 的 `python3`。unit 保留 logical venv 路径以维持
venv 语义；receipt 同时固定 logical symlink、canonical target、`pyvenv.cfg`、SHA-256、owner、
group 和 mode。候选 unit 与当前迁移 unit 必须使用不同名称。

## 2. 停止 ALAS，但保留旧 emulator unit 给 prepare 接管

先停止 ALAS 消费者，再让 guest 执行 `sync`。不要手工停止、disable 或 mask
`$PREVIOUS_UNIT`：正式 `prepare` 必须先读取并归档其 effective `FragmentPath`、全部 drop-ins、
有效属性及 enabled state，随后才会有界 stop、disable 并 runtime-mask 正确的旧消费者。
不要使用全局 `pkill`/`pgrep` 代替 unit、端口和文件依赖检查。

```bash
test "$(systemctl show --property=ActiveState --value -- "$PREVIOUS_UNIT")" = active
systemctl show --property=FragmentPath,DropInPaths,User,ExecStart,UnitFileState -- "$PREVIOUS_UNIT"
```

若上述 tracked validation report 对应的旧 unit 名称已被现场运维替换，必须把真实 active
consumer 作为 `--previous-unit`；不要照抄历史名称后继续。

## 3. 安装可复现 unit

安装动作只写 unit、执行 `daemon-reload` 并生成 receipt；它不会 enable 或 start。

```bash
sudo "$REPO/scripts/wsl/manage-kvm-live-cutover.sh" install-unit \
  --domain "$KVM_DOMAIN" \
  --profile "$KVM_PROFILE" \
  --release-id "$RELEASE_ID" \
  --runtime-config "$RUNTIME_CONFIG" \
  --unit "$UNIT" \
  --run-as-user "$RUN_AS_USER" \
  --run-script "$REPO/scripts/wsl/run-kvm-avd.sh" \
  --alas-python "$ALAS_PYTHON" \
  --unit-directory /etc/systemd/system \
  --timeout-stop-seconds 90 \
  --cutover-lock "$CUTOVER_LOCK" \
  --phase-marker "$PHASE_MARKER" \
  --receipt "$EVIDENCE/unit-install.json"
```

生成的 unit 固定 `User=<non-root>`、`KillMode=control-group`、`Restart=no`、
`TimeoutStopSec=90s`，固定 `ALAS_PYTHON`，并把 domain/profile/release/runtime config
作为四个明确参数传给 `run-kvm-avd.sh`。安装后会从 systemd 复读并验证 effective
`FragmentPath`、空 `DropInPaths`、`User`、`Environment`、`ExecStart`、`KillMode`、
`Restart`、`TimeoutStopUSec` 和 `UnitFileState=disabled`；不会 enable 或 start。

## 4. 离线 prepare

`prepare` 在任何 AVD 切换前完成以下操作：

1. 在共享 cutover lock 内归档旧 unit 的 fragment/drop-ins/effective/enabled state，再 stop、
   disable、runtime-mask 旧 unit；候选 unit 必须 loaded、disabled 且 inactive，两个递归子
   cgroup 均为空；5588/5589 没有 listener；全局
   `/proc` 中没有仍打开 AVD 文件的 orphan；
   prepare 还会在停止旧 unit 前读取 5043 listener 的 PID、四组 UID、start-time、loopback
   address 和 `/proc/<pid>/exe`。若它与旧 unit 的 effective user 一致且 exe 精确位于某个
   KVM immutable runtime release，停止旧 unit 后会复验同一 PID/start-time/exe，再用该
   **已证明的 adb executable** 执行 `-P 5043 kill-server` 并确认端口释放。现场旧 transient
   unit 的 `User` 为空（root）；因此 root-owned 5043 只有满足上述 provenance 才会被定向
   清理。未知、换 PID、非 loopback、非 KVM release 或 UID 不一致都会在 kill 前失败；
2. 相邻 `<name>.ini` 的唯一 `path=`（以及存在时的 `path.rel=`）必须精确解析到本次审计的
   `<name>.avd`；release 自带 `qemu-img` 必须返回非空、逐层相连的本地 ImageInfo chain，
   protocol/network backing filename、空/缺字段结果及 hot output、AOSP source、Redroid 引用
   都会 fail closed；
3. AVD 不能把额外 writable disk/sdcard 放在 snapshot 之外；
4. 使用 sparse-aware `rsync -aHAX --sparse --numeric-ids --fsync` 复制完整 `<name>.avd`、相邻
   `<name>.ini` 和 deployment contracts；launcher、resolver 与所依赖的 Python control-plane
   源文件也按逐文件 SHA-256 一并保存。AVD 会验证复制前、复制后、目标树内容及逐项
   uid/gid/mode 一致，并在 `renameat2(RENAME_NOREPLACE)` 发布 snapshot 前 fsync 全树；
5. snapshot 完整落盘后，只把 AVD 根目录下现存的 `.ini`、`.lock`、`.img`、`.qcow2`
   mutable 文件按记录 chown 给候选 non-root user；不递归、不 chmod。AVD 根目录必须已经
   由该用户持有且 owner `rwx`，否则停止。所有改动均记录在 prepare receipt，恢复边界是整
   AVD snapshot；随后复用 runtime release verifier 原子切换唯一的 `image.sysdir.1`，并保持
   `config.ini` 原 uid/gid/mode；
   旧 emulator 生成的 `hardware-qemu.ini` 与 `hardware-qemu.ini.lock` 是例外：prepare 先证明
   其中本地绝对路径只属于 live AVD 或当前 `image.sysdir.1` 对应的旧 KVM image root，并把
   原文件完整保存在 snapshot；随后只删除这两个 exact derived 文件并 fsync AVD 目录，让
   candidate emulator 按新 release 重建。删除记录写入 prepare receipt，不会递归清理；
6. 切换后再次逐文件 hash live AVD 和相邻 descriptor，把完整 manifest 写进 prepare receipt；
7. 写入 prepare receipt，明确 `first_boot_performed=false` 及离线整目录恢复策略。

```bash
sudo "$REPO/scripts/wsl/manage-kvm-live-cutover.sh" prepare \
  --domain "$KVM_DOMAIN" \
  --profile "$KVM_PROFILE" \
  --release-id "$RELEASE_ID" \
  --runtime-config "$RUNTIME_CONFIG" \
  --unit "$UNIT" \
  --previous-unit "$PREVIOUS_UNIT" \
  --unit-receipt "$EVIDENCE/unit-install.json" \
  --previous-unit-archive "$PREVIOUS_UNIT_ARCHIVE" \
  --snapshot-path "$SNAPSHOT" \
  --snapshot-timeout-seconds 7200 \
  --cutover-lock "$CUTOVER_LOCK" \
  --phase-marker "$PHASE_MARKER" \
  --receipt "$EVIDENCE/prepare.json"
```

已有 AVD 不应再运行 `provision-kvm-avd.sh`；该脚本会拒绝把一个指向其他 sysdir 的非空
AVD 当作新 AVD provision。

## 5. activate 与 live proof

`activate` 在任何 runtime mutation 前重新验证 snapshot 以及 prepare 记录的 post-switch live
AVD/descriptor manifest，并确认旧 unit 仍 masked、候选 unit effective contract 未漂移。随后先检查
现存 5043 listener 的 loopback address、PID、UID 和 `/proc/<pid>/exe`；只有 `weipa` 所有、来自
KVM pinned runtime 的 adb 才允许被 candidate adb 停止。candidate 启动或后验检查失败会事务式
kill 并确认 5043 已释放。随后显式启动 unit，有界 connect `127.0.0.1:5589`，要求专用 server
inventory 中只有该 transport 且状态为 `device`。

ADB ready 后，命令递归读取 unit 的所有子 cgroup PID，并检查每个进程的 `exe`、`cwd`、
`cmdline`、`maps` 和全部 fd；任一处引用 hot output、AOSP source 或 Redroid 都会失败。
active `config.ini`、descriptor 和生成的 `hardware-qemu.ini` 同样检查，且 image sysdir 必须
精确属于 candidate release；active config、cmdline、maps 或 fd 中任何 sibling/legacy KVM
release 路径都会失败。receipt 发布前再次确认 unit active、cgroup PID/start-time 稳定，且
真实 QEMU `/proc/<pid>/exe` 位于 candidate release 的 `emulator/` 下。

若 prepare 报告旧 5043 provenance 不可证明，不要运行 `adb kill-server`、`kill <pid>` 或全局
`pkill adb` 绕过。保持旧 service 现场，先只读保存 `ss -H -ltnp`、`/proc/<pid>/exe`、
`/proc/<pid>/status`、`/proc/<pid>/stat` 与旧 unit effective state，再决定宿主专用迁移方案。

```bash
sudo "$REPO/scripts/wsl/manage-kvm-live-cutover.sh" activate \
  --domain "$KVM_DOMAIN" \
  --profile "$KVM_PROFILE" \
  --release-id "$RELEASE_ID" \
  --runtime-config "$RUNTIME_CONFIG" \
  --unit "$UNIT" \
  --unit-receipt "$EVIDENCE/unit-install.json" \
  --prepare-receipt "$EVIDENCE/prepare.json" \
  --adb-timeout-seconds 180 \
  --cutover-lock "$CUTOVER_LOCK" \
  --phase-marker "$PHASE_MARKER" \
  --receipt "$EVIDENCE/activation.json"
```

`boot-attempted` phase 会在调用 `systemctl start` **之前**持久化。因此即便 `systemctl start`
返回非零，也会保守地写 recovery-required，而不会声称“从未启动”。失败时工具会尽力停止
candidate unit 和专用 ADB server，写
`failed-stopped-recovery-required` receipt。它不会自动覆盖 live AVD。

## 恢复边界

candidate 一旦收到 `systemctl start`，就保守地视为可能写过 userdata。通用工具不能判断
guest 是否已迁移 `/data`，所以禁止“只把 system image 切回去”的伪回滚，也不自动删除
或覆盖 AVD。

恢复时必须：

1. 停止 ALAS，停止 KVM unit，确认 `inactive`、5588/5589 空闲且没有进程打开 AVD；
2. 校验 snapshot manifest、自校验 hash、完整 AVD tree 和保存的 deployment contracts；
3. 使用经审查、适配该宿主文件系统的离线原子恢复操作，把 snapshot 中整个 `.avd` 和
   相邻 descriptor 恢复到原位置；不要 hardlink userdata；
4. 恢复旧 unit、旧 domain/profile/runtime config，并用旧 release verifier 检查；
5. 重新执行 qcow、5043/5589、active config 和 whole-cgroup 检查后才恢复 ALAS。

每份 prepare/activation receipt 都包含上述恢复说明和 snapshot 绝对路径。仓库不提供通用
`restore` 子命令，这是刻意的 fail-closed 边界，而不是缺省执行 destructive replacement。
可以生成一份不修改现场的恢复计划，先比较当前旧-unit 文件与归档内容，再由人工审查宿主专用
原子整目录恢复：

```bash
sudo "$REPO/scripts/wsl/manage-kvm-live-cutover.sh" recovery-plan \
  --domain "$KVM_DOMAIN" \
  --profile "$KVM_PROFILE" \
  --release-id "$RELEASE_ID" \
  --runtime-config "$RUNTIME_CONFIG" \
  --unit "$UNIT" \
  --previous-unit "$PREVIOUS_UNIT" \
  --prepare-receipt "$EVIDENCE/prepare.json" \
  --activation-receipt "$EVIDENCE/activation.json" \
  --phase-marker "$PHASE_MARKER" \
  --receipt "$EVIDENCE/recovery-plan.json"
```

该命令只读 live unit/AVD 相关证据并新建 plan receipt；不会 unmask、复制、删除或覆盖任何
live AVD、descriptor、unit fragment 或 drop-in。即使 activation receipt 尚未成功发布，它也
会从 durable phase history 保守恢复 `boot_attempted`，不会把已进入首次 boot 的现场写成 false。
