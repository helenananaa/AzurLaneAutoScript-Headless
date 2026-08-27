# AWS x86 Redroid 新容器进游戏复现验证

日期：2026-08-26

## 结论

已在 AWS x86 验证机上用两个分别新建的 OCI container object 重复到达国服
`9.7.10` 的真实 Unity 登录页。两轮均满足：

- container task 保持 `RUNNING`；
- Android FBE 为 `encrypted` / `file`；
- 游戏 ABI 为 `x86_64`，通过 ANGLE NULL 启动；
- Unity 使用必需的 `-force-gfx-st`；
- typed observer 返回 `status=ok`、`main_thread=true` 和新鲜 generation；
- `/v1/ui` 精确包含 `LoginUI2(Clone)`，不是截图或日志推断；
- 独立 container network namespace 下，宿主 kernel journal 中 uevent/netlink
  `I/O error` 计数为 0；
- 验证结束后 task、DM、loop、veth、NAT 均已清理，宿主回到 stock
  `7.0.0-1011-aws`。

因此可以确认：**“用当前 x86 镜像/rootfs 和保留的已装游戏 userdata，新建
Redroid 容器可稳定进入游戏登录路径”已可复现。**

本验证没有声称全新空 userdata 的首次 FBE 初始化已经修复，也没有把登录页提升
为账号主页、ALAS workload、长时间 soak 或生产可用结论。

## 验证对象

宿主：

```text
AWS instance: i-043d5b0279af33c9c
validation kernel: 6.17.13-alas-dmdefault
recovery/default kernel: 7.0.0-1011-aws
containerd namespace: alas-headless-r75-x86
```

共同运行输入：

```text
rootfs:   /srv/alas-runtime/validation/x86-fresh-20260826a/rootfs
userdata: /srv/alas-runtime/volumes/userdata-x86-r75-run3.img
metadata: /srv/alas-runtime/volumes/metadata-x86-r75-run3.img
manifest: sha256:bf55facb1e6458272b827615e3d4d3d47bffdad3705dfdea33ef1c5eb9ee99d0
game:     com.bilibili.azurlane 9.7.10, x86_64
```

这里复用的是已安装游戏的 volume 内容，不是 OCI container object。每轮都删除
前一 task/container，并按现场设备身份创建新的 object；没有启动历史保留对象
`alas-redroid-r75-x86-fbe` 或 `alas-redroid-r75-x86-verify2`。

## 两轮结果

### Round 1

```text
container:  alas-redroid-r75-x86-game-b1
created_at: 2026-08-26T03:30:47.544089122Z
game_pid:   109794
```

登录页瞬时快照：

```text
status=ok
abi=x86_64
generation=73
age_ms=164
main_thread=true
width=1280
height=720
active_button_count=10
```

随后稳定性快照仍为 `status=ok`，generation 从 73 前进到 361，age 为
138 ms，游戏 PID 未变。`ui-login.json` 中有 24 个
`LoginUI2(Clone)` 路径匹配。

### Round 2

```text
container:  alas-redroid-r75-x86-game-b3
created_at: 2026-08-26T03:56:17.17206358Z
game_pid:   36887
```

登录页瞬时快照：

```text
status=ok
abi=x86_64
generation=68
age_ms=94
main_thread=true
width=1280
height=720
active_button_count=11
```

45 秒后的稳定性快照仍为 `status=ok`，generation 从 68 前进到 388，age 为
173 ms，游戏 PID 未变，container task 仍为 `RUNNING`。`ui-login.json` 中同样
有 24 个 `LoginUI2(Clone)` 路径匹配。

两轮 observer driver revision 均为：

```text
506b76f698b5089aaa29c4e7908b48edb8532a44
```

## 宿主稳定性的关键对照

原先失败路径使用 host network namespace；历史成功 run3 日志和失败日志都曾有
大量 uevent/netlink `I/O error`。本轮两个有效容器均使用独立 network
namespace，再通过 veth、DHCP 和窄范围 NAT 提供网络。

第二轮记录：

```text
host netns:  net:[4026531833]
guest netns: net:[4026532710]
Android default network: 100
transport: ETHERNET
capabilities: INTERNET, VALIDATED
kernel uevent/netlink I/O errors: 0
```

这证明事件风暴不是 native FBE 的必然结果，并把此前宿主不稳定的直接触发条件
缩小到共享 host network/netlink 边界。它还不是 Linux/Redroid 上游源码级最终
根因，后续 runtime 应把私有 network namespace 和网络附件固化为正式启动路径。

## 验证中排除的无效轮次

`alas-redroid-r75-x86-game-b2` 不计入复现结果。它错误地复用了 Round 1 导出的
OCI spec，其中冻结的设备清单不包含后来现场出现的 `/dev/loop9`，导致 APEX
bootstrap 失败并自行退出。清理后重新按现场设备图生成 b3 spec，Round 2 才通过。

这个对照再次确认：新 task 不等于新 container spec；不得把旧 spec 跨 loop/DM
设备图复用。

## 运行时修正

保留 userdata 中存在一条不完整的 Ethernet STATIC 配置，只有 DNS，没有
LinkAddress/Gateway。若直接出现 `eth0`，Android 15 `IpClient` 会因空
`LinkAddress` 抛出 NPE，并连带重启 system_server。验证中将该错误配置保留改名，
让 EthernetTracker 重新使用 DHCP；之后 default network 通过系统验证。

另一个必要条件是所有游戏冷启动都传入：

```text
--es unity -force-gfx-st
```

遗漏时游戏进程和 observer socket 虽存在，但 typed snapshot 保持
`status=unavailable`；补齐后立即恢复 `status=ok`。没有放宽 observer 主线程检查。

## 清理和恢复

结束时已验证：

```text
container tasks: empty
dmsetup: No devices found
run3 loop bindings: empty
validation veth: 0
validation NAT rules: 0
net.ipv4.ip_forward: 0
GRUB_DEFAULT: 0
GRUB next_entry: empty
```

宿主随后主动重启并重新连入：

```text
uname -r: 7.0.0-1011-aws
container tasks: empty
dmsetup: No devices found
net.ipv4.ip_forward: 0
```

## 证据

本地工作区（Git 忽略）：

```text
evidence/x86-game-new-container-20260826b/
```

远端保留：

```text
/srv/alas-runtime/evidence/x86-game-new-container-20260826b/
```

关键 SHA-256：

```text
round1/snapshot-login.json        9e8dcdecaf9f61ca0884e1ddf7a30ece1b4d10c67fd0420ec7e3284efb8e9f16
round1/ui-login.json              aab2871f5bfc9c5009b1a3e06c1957f5f85cc0f4e82f7bc79cecaa682ec77b37
round1/snapshot-stability-end.json 8315c6011789cb4d09c50f21e98589cff3029c1361f51b22923c85b80908011f
round2/snapshot-login.json        b5e1fac1a06a99e1d20625dd90ab1ececc9cab0cacfc6a39b0b21086f53b68e7
round2/ui-login.json              004b1eb3c1f20cac54ef9118fb63d69fb292cfa752185f644045f54981106403
round2/snapshot-stability-end.json 31a8d06d94b100f0dab74f01284e7cb9accc4c01f9e0ea391ac9a91aa7b32c41
summary.txt                       bf28df3bb64aa865622dad752071729395dfebfadc72a56bfecc97317d35a29d
```

## 当前支持声明

```text
x86 新 OCI container -> Android/FBE/ADB：两轮通过
x86 新 OCI container -> ANGLE NULL typed LoginUI2：两轮通过
x86 独立 network namespace 宿主稳定性：本轮零事件错误
x86 空 userdata 首次 FBE：仍未通过
x86 账号主页 / ALAS workload / persistence / rollback / soak：本轮未验证
ARM64：本轮未修改
```
