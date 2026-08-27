# AWS ARM64 Redroid 登录边界验证（2026-08-26）

本文保留首次使用持久化 userdata 的历史结果。新建容器与新建 userdata 的复现、首次协议、
OCI writable-layer 偏差和下载后冷重启见
[AWS ARM64 Redroid 全新容器登录复现](aws-arm64-redroid-fresh-login-validation-20260826.md)。

统一操作顺序、故障账本和后续重入条件见
[ARM64 Redroid 端到端运行手册](arm64-redroid-end-to-end-runbook.zh-CN.md)。

## 结论

真实 AWS ARM64 宿主上的 Android 14 Redroid 已在 ANGLE NULL 下完成游戏资源选择与
28.1 GB 下载，并自然进入：

```text
com.bilibili.azurlane/com.gsc.phone_login.PhoneLoginActivity
```

验证在登录边界停止。没有输入手机号，没有提交账号，也没有继续到游戏主界面。

本轮持久化 userdata 已持有隐私同意状态，没有再次出现协议页面，因此没有执行新的
同意动作。该结果证明的是既有同意状态可继续完成资源更新并到达登录页，不证明首次安装
协议 WebView 路径在这个候选上重新通过。

## 运行边界

- 宿主内核：`6.1.176-alas-dmdefault-ikconfig-va39+`
- Android：Redroid 14，持久化 loop userdata
- 游戏 APK：`versionName=9.7.10`、`versionCode=9710`
- Unity 内容版本：资源下载前观察到 `9.7.328`
- ANGLE 路由：包 `com.bilibili.azurlane`，驱动值 `angle`
- Unity 启动参数：`-force-gfx-st`
- observer ABI：`arm64-v8a`
- observer APK SHA-256：
  `f37379fde001ee60f3916cbd56163fef55181d16e889383237968f7e7ea23401`

`-force-gfx-st` 保证 NULL swap 与 Unity 主线程一致。没有放宽 observer 的主线程检查。

## 修复范围

资源引导只增加了三个精确、任务局部的 raycast path：

```text
PaintingPrefsPanel(Clone)/Panel/Confirm
OtherPrefsPanel(Clone)/Panel/Confirm
DialogPanel/dialog/action_button
```

首次 typed snapshot 在尚未就绪时会进行有界重试：swap 1，以及不超过 120 的每三个
swap。首个成功 snapshot 后恢复每 60 swap 的既有采样节奏。该变化没有加入通配坐标、
截图回退或 graphics-worker 线程豁免。

## 资源与存储

选择状态和下载确认均在输入前检查唯一目标、`raycast_top=true`、当前 generation 与前台
进程。下载确认文本为：

```text
本次更新需要下载28.1GB的文件，是否继续更新？
```

原 16 GiB `/data` 不能容纳下载，因此没有点击下载。容器停止后保留离线稀疏备份：

```text
/srv/alas-runtime/volumes/a14-pastel-process-lived-userdata.pre-expand-16g-20260826.img
```

原 userdata 非破坏扩展到 48 GiB，重启后保留原游戏状态，再执行下载。下载监控样本中
失败文件数始终为 0；约 643 秒后下载进度消失并进入登录 UI。登录边界证据采集时
`/data` 为 49,357,668 KiB，总可用 17,398,580 KiB。

## 登录边界后置条件

- 前台 Activity 是 `PhoneLoginActivity`；
- 唯一手机号输入框 resource id 为
  `com.bilibili.azurlane:id/et_gsc_phone_num`；
- 输入框显示 `请输入手机号` 占位文本，未聚焦；
- 唯一“下一步”控件 resource id 为
  `com.bilibili.azurlane:id/tv_gsc_phone_next`，且 `enabled=false`；
- `account_input_performed=false`；
- `account_submission_performed=false`。

远端证据目录：

```text
/srv/alas-runtime/evidence/arm64-login-20260826/
```

其中保存两次资源选择和下载确认的前后 typed state、UI、action receipt，userdata 扩容
前后状态，以及最终 Activity、UI hierarchy、包版本、ANGLE 设置和登录边界 JSON。

ARM64 observer 增量编译通过。本地与该变更直接相关的 build-script、observer contract、
ARM64 host probe 和 Redroid backend 定向回归为 `34 passed`。

## 未证明的范围

本次结果不能提升为完整支持。以下项目仍未验证：

- 首次安装时重新展示并同意隐私协议；
- 账号输入、账号提交和真实登录；
- 登录后的游戏主界面；
- pinned ALAS 或更新版 ALAS 的真实任务工作负载；
- game/Android recovery、容器 lifecycle/cleanup 和长期 soak；
- FBE 与自维护镜像发布资格。
