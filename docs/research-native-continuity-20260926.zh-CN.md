# Research 原任务连续闭环（2026-09-26）

本轮关闭了此前 Research 末尾队列重入与调度收尾的缺口。原 `RewardResearch.run()` 单次连续执行完成，不重写选择器、补队列循环或调度流程。支持等级保持 `L`，本次不是全配置或无人值守跨轮资格。

## 修复

1. 队列进入与返回的导航收据过去共用过渡时间；退出后旧入口收据仍在，后续操作更新过渡时间就会再次误用它。现在进入成功后清除上一段返回收据，返回成功后清除上一段入口收据；同一段的重复请求仍不重复输入。
2. `QUEUE_CHECK` 过去通过带 30 秒退出缓存的队列数据接口判断页面存在。实机连续第二次进入时，原 ALAS 因此误判已在队列页，跳过输入。现在页面检查只使用当前完整类型化队列状态；退出后读取容量的既有缓存单独保留。
3. 导航脚本识别登录更新页面，并支持连续两次队列往返。科研策略脚本新增 `--native-queue-fill`，保留原补队列方法，最多六次开工；默认单次策略取样行为保持不变，收据明确记录模式。

没有修改上游补丁成员、观察器或原 ALAS 状态机。当前有效系列仍为 119 成员。

## 实机范围与过程

- 发现并绑定原 `alas_game_api32_x64`，设备 `emulator-5554`；包和前台为 `com.bilibili.azurlane/com.manjuu.azurlane.MainActivity`，PID 1966，观察器修订 `506b76f698b5089aaa29c4e7908b48edb8532a44`。
- 原 userdata、ANGLE NULL 保持，冷启动携带 `-force-gfx-st`。本次有 861 MB 更新提示，原登录流程随后到达游戏版本 `9.7.394`。签到奖励和公告遮挡分别经原登录处理器恢复；早期失败收据保留，没有把这些恢复拼成一次无中断登录资格。
- 连续两次“进队列→退出”实机通过，重复入口请求零额外输入，最后返回主页。初次失败 `r4` 直接揭示上述 `QUEUE_CHECK` 缺口；修复后的 `r5` 通过。
- 固定上游 `81ccf63b4540f00241628c82a58c02c7a2bb11af` 的原科研任务采用 `UseCoin=always_use`、`UseCube=do_not_use`、`UsePart=do_not_use`、`AllowDelay=false`，自定义过滤 `S9-G > S9-D`。不强行刷新；原选择器在第六项目使用了自身的回退选择。

## 原任务结果

[完整任务收据](../integration/alas/research-native-continuity-live-validation-receipt-20260926.json) 为 `passed=true`、`task_completed=true`、`native_queue_fill=true`，耗时 145.031 秒，无网络重跑、无单次开工截断：

- 两次 `research.reward`：领取五格队列和第六个已完成项目。
- 六次 `research.start`：五个 `G-412-MI` 各 1500 物资，一个 `D-740-MI` 为 3000 物资，共 **10500 物资**。未消费魔方、部件或付费货币，未购买。
- 原循环填满五格队列，第六个项目在结束观察中为 `waiting`。
- 原任务重新进入队列、读取结束时间、退出并正常返回，下一次执行时间为 **2026-09-26 11:08:01**。
- 采用临时配置记录原调度结果，临时配置已删除；没有更改用户常驻配置或开启后台持续科研。

随后独立的无 Research 任务作用域导航返回主页通过。该回程与任务运行分别留证，见[导航汇总收据](../integration/alas/research-navigation-continuity-receipt-20260926.json)，不宣称它们是同一进程。

原始运行日志和完整页面数据保留在 `artifacts/research-native-continuity-20260926-r1.*`、`artifacts/research-continuity-navigation-20260926-r1..r5.*`、`artifacts/research-native-home-20260926.*`；汇总收据包含导航原始 JSON 的 SHA-256。

## 验证与剩余范围

两个回归分别在修复前复现：跨退出误用入口收据、退出缓存误判页面。修复后 Research、oracle、任务隔离、登录和配置回放共 **120 passed**；保留未知队列状态拒绝、一次输入后缺少后置条件时不重复输入的检查。Research 配置 verifier 通过。

双资源实际确认、自然半小时策略、重置、其他预设和无人值守跨轮仍未取得本轮资格。本次游戏更新后的证据仅覆盖这个本地 AVD 上的路径，不能推广为任意游戏版本或全部任务兼容。
