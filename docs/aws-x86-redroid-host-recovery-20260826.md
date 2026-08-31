# AWS x86 Redroid 宿主机失联恢复与容器启动故障日志

日期：2026-08-26

## 状态摘要

本轮已经修复的是 **AWS x86 验证宿主机的启动和远程维护路径**，不是
Redroid 容器启动故障本身。

当前状态：

- x86 实例 `i-043d5b0279af33c9c` 已恢复启动；
- 当前公网地址为 `54.237.212.139`，该地址会随 EC2 停止/启动变化；
- 实际运行 AWS stock 内核 `7.0.0-1011-aws`；
- `systemctl is-system-running` 返回 `running`；
- 连续三次独立 SSH 探测均成功；
- `alas-headless-r75-x86` namespace 中没有运行中的 container task；
- `dmsetup ls` 返回 `No devices found`；
- Redroid 重新启动故障仍为 **未修复、禁止直接重试**。

临时资源按用户要求保留：

- 救援实例 `i-09c96f0d548a9e3d7` 已停止，未终止；
- IAM 角色和 instance profile `EC2-SSM-Recovery` 仍保留；
- IAM instance profile 已从 x86 实例解绑，当前实例 metadata 不再暴露 IAM
  身份。

## 故障现象

x86 宿主机切换到定制内核
`6.17.13-alas-dmdefault` 后启动保留的
`alas-redroid-r75-x86-fbe` task。Android 串口随后持续出现：

```text
ueventd: Error reading from Uevent Fd: I/O error
NetlinkListener: recvmsg failed (I/O error)
```

此后 SSH 端口仍可建立 TCP 连接，但连接在服务器 SSH banner 前关闭或超时。
因此本次不是普通的 Android 应用退出或 container task 单独退出，而是 Redroid
启动后触发了影响宿主机可维护性的内核/设备事件异常。

EC2 没有留下可用于精确定位内核源码位置的 panic、Oops 或 Call Trace。当前只能
确认故障边界，不能把某个尚未证明的内核函数写成最终根因。

## 已确认的运行事实

### 内核差异

定制内核基于 AWS 6.17 内核构建，主要新增了 FBE 所需的：

```text
CONFIG_DM_DEFAULT_KEY=y
```

当前可恢复的 stock 内核没有该选项：

```text
CONFIG_DM_CRYPT=m
CONFIG_DM_VERITY=m
CONFIG_ANDROID_BINDER_IPC=m
CONFIG_ANDROID_BINDERFS=m
CONFIG_FS_ENCRYPTION=y
CONFIG_FS_VERITY=y
```

因此 stock 内核可以作为宿主机维护基线，但不能据此声称已经具备当前 Redroid
FBE 路径的启动资格。

### “新容器”实际复用了旧容器对象

现存 container object：

```text
ID:        alas-redroid-r75-x86-fbe
CreatedAt: 2026-08-26T01:31:22.154921924Z
Rootfs:    /srv/alas-runtime/rootfs/x86-r75-ownerfix
Runtime:   io.containerd.runc.v2
```

操作历史显示，后续主要是在同一个 container object 上反复删除、创建和启动
task，并在多组 loop-backed userdata/metadata 之间切换，包括 `run3` 和 `run4`。
期间还多次执行：

```text
dmsetup remove_all
losetup -d /dev/loop6 /dev/loop7
重新绑定 /dev/block/alas_userdata 和 /dev/block/alas_metadata
```

保留的 OCI spec 冻结了创建时的宿主设备集合，其中包括大量：

```text
/dev/dm-0 ... /dev/dm-34
/dev/loop0 ... /dev/loop90
```

在 dm/loop 设备图被清理、重建和跨宿主机重启后继续复用该 spec，不能保证 spec
中的设备身份仍与实际 FBE volume graph 一致。

### 宿主根文件系统

离线只读 `e2fsck` 首次发现 free block count 和 free inode count 不一致。执行
`e2fsck -fy` 后修正计数；后续检查完成全部 inode、directory、connectivity、
reference count 和 group summary pass，没有发现支持“根盘结构损坏导致容器崩溃”
的证据。

## 根因分类

### 已确认

1. 故障只在定制内核下启动 Redroid task 后进入；切回 stock 内核且不启动
   Redroid 后，宿主机恢复稳定。
2. Android `ueventd` / `NetlinkListener` 在失败窗口持续收到 `EIO`。
3. 被称为“新容器”的运行路径复用了已有 OCI container object 和冻结的设备
   spec，不是基于当前设备图全新生成的容器定义。
4. FBE volume 的 loop/dm 设备图曾被多次删除、重绑和跨重启复用。

### 最可能、但尚未最终证明

当前最可能的原因是：

> 定制内核的 FBE/device-mapper 路径，与跨多轮重绑后复用的 loop/dm 设备图及
> 旧 OCI device spec 组合，触发了 Redroid uevent/netlink 路径异常；持续事件
> 错误进一步使宿主机失去稳定的 SSH 维护能力。

现有证据还不能区分以下子原因：

- `DM_DEFAULT_KEY` 定制内核或其模块集合自身存在兼容性问题；
- OCI spec 中冻结的 dm/loop 设备节点与本轮实际设备身份不一致；
- Redroid 在共享宿主 netlink/uevent 路径下遇到异常消息或事件风暴；
- 上述因素组合后才触发故障。

没有证据支持把问题归因于游戏 APK、ANGLE NULL、首次画面程序或 Android
userdata 中的普通应用数据。

## 已执行的恢复

1. 停止失联的 x86 实例；正常停止最终完成，没有强制分离在线根盘。
2. 在同一 AZ `us-east-1c` 启动临时 `t3.micro` 救援实例。
3. 将 150 GiB 根卷 `vol-09c6f5cb65590bb36` 从停止的 x86 实例分离，并以
   `/dev/sdf` 挂载到救援实例；Nitro 内实际设备为 `/dev/nvme1n1`。
4. 完成根文件系统检查和计数修复。
5. 同时挂载 root、独立 `/boot` 和 `/boot/efi`，在 chroot 中运行
   `update-grub`。
6. 将 `GRUB_DEFAULT` 恢复为 `0`，移除
   `/etc/default/grub.d/99-alas-dmdefault.cfg`。
7. 验证新生成的 `grub.cfg` 第一项为：

   ```text
   /boot/vmlinuz-7.0.0-1011-aws
   ```

8. 干净卸载所有 bind/root/boot/EFI mount，确认救援实例不再持有该卷。
9. 将根卷以 `/dev/sda1` 接回原实例，并恢复
   `DeleteOnTermination=true`。
10. 清除一次性 recovery User Data，避免后续启动重复执行恢复脚本。
11. 因账户 16 vCPU 配额阻止 x86 启动，先停止临时救援实例释放 2 vCPU；未
    停止或修改 ARM 实例。
12. 启动 x86 实例，完成 SSH、内核、systemd、container task、dm 和启动日志
    检查。
13. 从 x86 实例解绑临时 IAM instance profile。

`/var/lib/alas-recovery-boothook.done` 当前不存在，因此不能用该 stamp 声称
boothook 完整执行。最终可验证的持久修复来自离线挂载独立 `/boot` 后重新生成的
`grub.cfg`。

## 恢复后的验证结果

```text
uname -r
7.0.0-1011-aws

systemctl is-system-running
running

ctr -n alas-headless-r75-x86 tasks ls
TASK    PID    STATUS

dmsetup ls
No devices found
```

三次独立 SSH 探测均返回同一内核和 `running`。本次启动没有失败的 systemd
unit；`journalctl -b -p err..alert` 只有 EC2 虚拟硬件常见的
`piix4_smbus ... SMBus base address uninitialized`，没有再次出现 Android
uevent/netlink 错误。

## 下一轮修复约束与重新进入条件

当前禁止直接执行：

```text
ctr -n alas-headless-r75-x86 tasks start alas-redroid-r75-x86-fbe
```

重新进入 Redroid 启动验证前至少需要：

1. 保留 stock 内核为已验证的恢复启动项，不再把实验内核设成无保护的默认项。
2. 生成一套完整、一致的 custom kernel 和 modules，避免继续在现有制品上逐个
   手工补装 netfilter、quota 等模块后直接提升为基线。
3. 清理 task 后，先建立并记录稳定的 loop/dm 设备图，再按当前设备图重新创建
   OCI container object；不得复用现有冻结设备 spec。
4. 使用独立、可丢弃的新 userdata/metadata 做一次有界首次启动，不修改已验证
   的主 volume set。
5. 启动前持续采集 EC2 serial console、host kernel journal 和 Android 日志；
   发现首个连续 uevent/netlink `EIO` 后立即停止 task 或实例。
6. 先证明 host boot、SSH、container task stop/delete 和 dm cleanup 可恢复，再
   继续 ADB、ANGLE NULL、observer、持久化和游戏路径验证。
7. 在得到 kernel Oops/Call Trace、可重复的最小触发条件或对照实验前，根因状态
   保持“最可能但未最终证明”，不得写成 Redroid 或 Linux 上游 bug 已修复。

## 当前支持声明

```text
AWS x86 宿主维护路径：已恢复
AWS stock 内核 Redroid FBE：不具备当前配置资格
定制内核 Redroid 启动：已复现宿主失联，未修复
x86 登录页面旧证据：保留，但不能覆盖本次失败后的容器生命周期资格
ARM64 状态：本轮未修改、未重新验证
```
