# Redroid 连续性推进与本机运行入口（2026-10-23）

按公共边界、Main 恢复、低消耗调度、本地运行交付的顺序推进。公共修复已提交到
适配分支并合入 Redroid；本轮没有增加平台专用 ALAS 任务引擎。
结构化结果见[本轮摘要](../evidence/redroid-continuity-20261023/summary.json)。

## 公共边界与清理

- `68f5e7c`：默认 UI 读取先采集数据，再完成已有前台检查，避免慢 ADB 查询拆开
  state/UI 配对，并拒绝请求中的 Activity 切换。没有加等待或放宽代次。
- `f877924`：删除科研队列读取失败后使用 30 秒旧快照的兜底、缓存字段和退出前
  预读。原 ALAS 在卡片页已经读取当前五格标记，不需要另一份跨页队列模型。
- 同时修正验收运行器：原调度器等待时收到停止事件后的 `exit(0)` 属于正常退出。
  非零退出和未请求的退出仍失败；没有修改原等待、选择和 NextRun。

详见[配对读取边界](semantic-ui-pair-boundary-20261023.zh-CN.md)和
[科研当前状态](research-current-state-20261023.zh-CN.md)。两端使用同一适配层，
不按 Redroid/AVD 分叉上层任务成果。

## Main 恢复与强化

进入时船坞为 **910/1010**，尚有 100 个空位。本轮没有填仓或重复跑图制造条件；
自然满仓→退役→保留装备→原图续战→完成的单进程连续链仍未资格化。
上轮两端完整手动 Main 的证据见[地图修复记录](campaign-camera-refresh-20261022.zh-CN.md)，
本轮没有重跑完整 12-4。

单独调用原 ALAS 强化流程成功一次：官方推荐实际消耗 **7 艘一级普通舰**，目标
雷击 **82→91**，装备全部保留，返回主页。原函数返回的 `10` 是上层估计计数，
不能当成实际消耗舰数。该组件验证没有消耗油、金币或钻石。
此前“强化无结果”的诊断本轮未复现；旧的恢复等待超时并不能单独证明提交了强化。
这次成功也不拼接成完整 Main 恢复资格。

## 原调度组合与持久化

使用同一个已有 ALAS 运行树，持久配置为 `semantic_daily_continuity_20261023`。
仅开启 Reward、Commission、Research；关闭高油耗大委托、科研魔方和部件，保留
科研 `UseCoin=only_no_project` 与原筛选逻辑。

| 原任务 | 本轮实际结果 | 原任务写回的 NextRun（本机时间） |
|---|---|---|
| Commission | 领取 4 项完成委托，派遣 4 项，原任务返回 true | 2026-10-23 12:53:15 |
| Research | 领取 5 格加第六项目，4 次开工；分两次原调度执行，均返回 true | 2026-10-23 13:25:33 |
| Reward | 领取生产油/金币/经验及任务奖励，原任务返回 true | 2026-10-23 14:47:08 |

首次有界运行选到 Commission、Research、Research，三项执行通过。随后进程从同一
持久配置继续，完成 Reward 并进入原空闲导航。第二份收据将原生正常停止误记为
失败，原文件保留；修正运行器后第三次进程重入通过，明确记录
`resumed_config=true`、`native_stop_exit=true`，三个 NextRun 未被改写。
第三次的 `goto_main` 是等待中的导航，不冒充再次执行 Commission。

第一次 Research 曾将时间排在当时并立即重入，第二次才写出未来时间。没有第一次
精确失败帧，不能断言旧缓存就是此次现场的根因。删除缓存后的独立实机只读检查
通过，两端均取得四项当前队列：一项运行、三项等待。此处不作两端时钟等价声明。

未来自然唤醒与下一轮完成仍待真实时间；没有改游戏时间、强制提前 NextRun，
也没有创建后台自动跟进任务。

## 本机运行与 AVD 参考

当前镜像仍为 `sha256:2e6e03e3ef33c08acf91a13b1cd9cc4a6a5d33d2d579511760c85ea7bb6c8e5a`。
当前安装 observer SHA-256 为
`67d7f10e51df39abe8caba4fa0733f28b1fcf8fe3558299c5e51cf3e09dd42eb`，游戏 9.7.10 / 9710。

既有 Windows manager 导出当前 Config；共用 WSL Redroid backend 完成容器停止、
离线观察、启动、ADB/Android 就绪与游戏冷启动。userdata 标记保留，`/data` 权限
前后均为 `0771 system:system`。原 LoginHandler 重新到达主页，账号和资源相同，
PID 13911→1637，取得两次连续新鲜 coherent generation。

AVD 路径重新确认存在，发现并绑定实际 `emulator-5560`，核对 AVD 名称。第一次
诊断在 ADB 仍 offline 时启动，未输入游戏且按传输错误停止，失败收据保留。
随后等 `sys.boot_completed=1`，使用当时重新验证可解析 CDN 的 WLAN resolver
`192.168.5.1`，原流量策略仍为 `limitBytes=-1`，实际网络为 VALIDATED。
以 `-force-gfx-st` 冷启动后，原 LoginHandler、科研队列/结束时间读取和回主页通过，
包、前台、PID、当前代次与账号均核对；无资源变化。没有变更系统 DNS/TUN。

参考完成后关闭本任务 AVD，再以 `-force-gfx-st` 恢复 Redroid。最终主页 PID 2655，
generation 312→322、state/UI 各自相同，资源为 1290 油、102545 金币、3505 钻石。
本次无遗留 ALAS runner；保留原调度配置和计时。

本机运行包位于：

`E:\Runtime\ALAS\redroid-x86_64-local-20261023`

目录内 README 提供现有 manager 与原调度器的运行命令，包含当前 observer APK、
Config 和制品索引。OCI 与原 ALAS 使用已有本地路径，不重复复制镜像或 userdata。
这是本机已有实例的运行入口，不是可移机的全新安装包。

没有重复安装相同 APK、重建 AOSP 或重跑未改变的历史回滚演练。
[历史受控回滚](redroid-wsl-rollback-20260907.zh-CN.md)只证明空登录页的 fixture
机制；真实发布版本升级/回退、当前登录 userdata 迁移、原生 Linux、ARM64 与
长期无人值守仍未资格化。旧 FBE 镜像继续不兼容当前 host-directory 模式。

## 验证与资源

最终相关 oracle、科研、调度、退役、强化和恢复集合 **1114 passed，0 skipped**。
此前 739/90/123 等聚焦集合有重叠，不相加。未修改 ALAS 233 成员 patch series、
支持矩阵或配置元数据，沿用上轮补丁应用与编译验证，不宣称本轮重跑全仓测试。

本轮资源净变化：**油 +774、金币 +6766、钻石 0**，另消耗 7 艘一级普通舰。
净值包含领奖与科研开工，不代表逐项目毛支出。没有购买、付费扩容或高级货币消费。
raw 收据、失败记录、私有账号观察和测试 XML 留在
`artifacts/continuity-20261023/`；公开摘要不含账号名称或凭据。
