# AWS x86 Redroid 全新容器有界验证日志

日期：2026-08-26

> 后续进展：本文记录的“空 userdata 首次 FBE”失败仍然成立；之后使用保留的
> 已装游戏 run3 volume、现场新建 OCI object 和独立 network namespace，已连续
> 两轮到达 typed `LoginUI2(Clone)`，且宿主 uevent/netlink I/O error 为 0。
> 两项结论覆盖的边界不同，详见
> [AWS x86 Redroid 新容器进游戏复现验证](aws-x86-redroid-new-container-game-validation-20260826.md)。

## 结论

本轮按恢复日志的重新进入条件创建了全新 rootfs 副本、全新 userdata/metadata、
新的 loop 绑定和新的 OCI container object。结果仍然失败，因此可以排除“只要不
复用旧 OCI spec 就能恢复启动”；旧 spec 是真实风险，但不是唯一根因。

失败边界已经缩小到 Android native FBE 首次启用阶段：

```text
ext4_enable_quotas: Failed to enable quota tracking
vold: keystore2 Keystore generateKey returned service specific error: -67
enablefilecrypto exited with status 25
Rebooting into recovery, reason: enablefilecrypto_failed
```

同一窗口仍出现 234 条 `ueventd` I/O error 和 87 条 `NetlinkListener` I/O
error。Android init 随后自行退出，ADB 未就绪。x86 Redroid FBE 和新的
container lifecycle 资格继续保持 blocked。

## 宿主和恢复边界

- 实例：`i-043d5b0279af33c9c`；
- 验证内核：`6.17.13-alas-dmdefault`；
- 恢复内核：`7.0.0-1011-aws`；
- GRUB 默认第一项在验证前后均为 stock；
- custom kernel 只通过 `grub-reboot` 选择一次；
- custom 启动后创建 7 分钟强制恢复 timer；
- 验证结束后主动重启，实际回到 stock；
- 回到 stock 后 systemd 为 `running`、container task 为空、`dmsetup ls`
  为 `No devices found`、GRUB `next_entry` 为空；
- 临时自动恢复 unit 已禁用并删除。

这证明了 host boot、SSH、task/container cleanup、DM/loop cleanup 和 stock
回退路径。本轮没有再次造成宿主失联。

## custom kernel 预检

没有重编译现有 kernel。只读审计确认：

- source、build、modules 三处 kernel release 均为
  `6.17.13-alas-dmdefault`；
- `/boot/config-*` 与保留源码 `.config` SHA-256 均为
  `ab5f08c0d22e79b6d1820732660b552b9f396e8f47ddbc0989a416fbc466be26`；
- `binder_linux` vermagic 与 custom release 一致；
- `/lib/modules/6.17.13-alas-dmdefault` 有 5931 个模块文件；
- Binder、dm-crypt、dm-verity、netfilter、conntrack 和 quota 模块均可由
  `modinfo -k` 定位；
- custom 启动后 `dmsetup targets` 实际包含 `default-key`、`crypt` 和
  `verity`；
- capability preflight 通过，且识别 stock 为独立恢复默认内核。

因此没有证据支持“custom modules 文件不完整”，也没有理由在计费服务器上先做
一次无差别 clean rebuild。但本轮启动前只加载了 Binder、dm-crypt 和 dm-verity，
没有加载已安装的 `quota_tree` / `quota_v2`；容器不能替宿主可靠加载内核模块。
这与日志里的 `ext4_enable_quotas ... err=-3` 一致，是本轮已确认的 preflight
遗漏。

## 全新运行对象

本轮未启动保留的 `alas-redroid-r75-x86-fbe` 或
`alas-redroid-r75-x86-verify2`。

新对象为：

```text
container: alas-redroid-r75-x86-fresh-20260826a
rootfs:    /srv/alas-runtime/validation/x86-fresh-20260826a/rootfs
userdata:  /srv/alas-runtime/validation/x86-fresh-20260826a/volumes/userdata.img
metadata:  /srv/alas-runtime/validation/x86-fresh-20260826a/volumes/metadata.img
loops:     /dev/loop7, /dev/loop8
```

OCI object 在上述 loop identity 建立后才创建。container spec 中
`/dev/block/alas_userdata` 和 `/dev/block/alas_metadata` 对应本轮实际的
`7:7` 与 `7:8`，没有复用历史 alias。Android 退出后，新 task 和 container
object 均已删除；两个卷和 rootfs 副本作为失败样本保留，未再启动。

## 失败序列

1. userdata 以明文 ext4 首次挂载，Android 识别到 metadata encryption；
2. vold 建立 default-key DM 映射，证据中生成至 `dm-34` 的本轮 DM 图；
3. 加密映射后的 ext4 启用 quota tracking 失败；
4. keystore2 生成 key 返回 `-67`；
5. `vdc --wait cryptfs enablefilecrypto` 返回 25；
6. init 尝试进入 recovery，但容器没有 `/misc`，最终 init fatal reboot 并退出；
7. ADB 从未达到 ready，`sys.boot_completed`、`ro.crypto.state` 和
   `ro.crypto.type` 均未取得值。

验证后直接对 userdata 文件执行 host `e2fsck` 会看到无 ext4 magic；这与已经
写入 metadata-encrypted block view 一致，不能单独解释成普通文件系统损坏。
metadata 卷只读 `e2fsck -fn` 完整通过。

## 监控缺口

本轮 shell 监控最初只匹配字面量 `EIO`，没有实时匹配日志实际使用的
`I/O error` 拼写；task 在第一次 5 秒轮询前已经自行停止，因此没有发生继续输入
或重复启动。事后原始日志统计恢复了完整计数。

仓库预检现在同时识别 `EIO` 和 `I/O error` 两种形式；代表性三条错误会直接
分类为 `repeated-eio`。以后不得再用旧的窄 grep 作为 stop 条件。

## 原始证据

本地工作区副本：`evidence/x86-redroid-fresh-fbe-20260826a/`。`evidence/` 按仓库
约定被 Git 忽略，耐久结论以本文档为准。

远端保留副本：

```text
/srv/alas-runtime/evidence/x86-fresh-20260826a
```

关键 SHA-256：

```text
kernel.log          34743eda789dffb4a84e270cac3aae19713afc52269d5f667b86f8378600f3e9
container-info.json f7fb684f6ea8d9b2b3ebca145b46bbd4150f3f06184793b0cea118ae59573af4
dm-table.txt        ecf4461a5860fa5e917030caa4f1ae4faf261d68679e60d1c510b2a97a4d32a3
dm-tree.txt         cdf82e46da3e80187982b32aa6579fc6bdd49a68909c7e956f1125605135aa3f
run.txt             63494cedf2e291dc00b4c4894a394619b7081e75c8c033f996b1ea6f1bf29f42
```

## 后续开发决定

不等待 ARM，也不停止镜像主线；但应把工作拆开：

1. 继续不依赖 x86 native FBE 的镜像构建、外部安装/升级、ANGLE NULL、observer、
   typed adapter 和 ALAS workload 开发；
2. x86 FBE 单独进入最小化根因实验，先比较 quota inode 初始化与 keystore2
   `-67`，不要再跑游戏或完整登录流；
3. 先在一次性卷上证明 `/data` 经 default-key 映射后可稳定挂载且没有事件风暴，
   再重入 ADB、持久化、ANGLE、observer 和游戏；
4. 保留旧 x86 登录页证据，但它不覆盖本轮 custom-kernel/FBE/container
   lifecycle 失败。

当前准确声明：

```text
x86 镜像/登录页工程基线：可继续开发
x86 stock kernel native FBE：能力不足
x86 custom kernel fresh-container FBE：失败，已安全回退
x86 Redroid lifecycle 资格：blocked
ARM64：本轮未修改
```

补充约束：下一轮 custom-kernel preflight 必须确认所有模块化能力不仅可由
`modinfo` 定位，而且已在宿主 `/sys/module` 中加载。修复该遗漏只能消除 quota
handler 缺失，不能自动豁免或忽略本轮 321 条 uevent/netlink I/O error；在事件
错误有独立解释前不直接重跑完整容器。
