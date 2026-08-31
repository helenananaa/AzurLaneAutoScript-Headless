# AWS ARM64 Redroid 全新容器登录复现（2026-08-26）

## 结论

新建 Android 14 Redroid 容器、48 GiB userdata 和 1 GiB metadata 后，国服 9.7.10
完成首次协议同意、28.1 GB 全量资源下载和一次有界游戏冷重启，最终到达：

~~~text
com.bilibili.azurlane/com.gsc.phone_login.PhoneLoginActivity
~~~

手机号输入框为空且未聚焦，“下一步”禁用。没有输入、提交或保存账号信息。

这次通过的是“新容器与新 userdata 的登录前产品路径”。它不是纯 OCI 复现：现场镜像
缺少两个已验证运行时修复，本轮在新容器 writable layer 中补入精确二进制后才恢复
package-private ANGLE NULL。因此 digest-only fresh OCI 资格仍未通过。

## 隔离身份

~~~text
container: alas-redroid-a14-login-fresh-20260826
ADB:       127.0.0.1:15564
userdata:  /srv/alas-runtime/volumes/a14-login-fresh-20260826-userdata.img
metadata:  /srv/alas-runtime/volumes/a14-login-fresh-20260826-metadata.img
evidence:  /srv/alas-runtime/evidence/arm64-login-fresh-20260826/
~~~

旧登录基线容器保持停止，旧 userdata/资源未改。Android 报告
`ro.crypto.state=encrypted`、`ro.crypto.type=file`；这不替代 native FBE/Direct Boot
五项资格。

## 首次隐私协议

首次前台 Activity 是 `AgreementWebActivity`。UIAutomator 只能看到 WebView 容器，
因此使用 WebView DevTools/CDP 检查真实 DOM：标题 `sdk协议`，唯一 `.agree` 和
`.disagree` 分别为“同意”和“拒绝”，均可见且矩形有效。

只对唯一 `.agree` 执行 DOM `click()`。转场后前台为 MainActivity，游戏 PID 保持；
15 秒前置与 60 秒后置样本没有游戏 fatal 或 destroyed mutex。证据是：

~~~text
17-agreement-dom-action.json
17-agreement-transition-samples.txt
~~~

证据边界：这次协议转场发生在私有 loader 修复前；后续修复没有清除 userdata，因此不能
把它写成“私有 NULL 从首次启动起生效”的完整 Agreement 证明。

## OCI 与 writable-layer 偏差

fresh 启动最初持续增加 `angleLoadingFailureCount`，实际 maps 仍是 system
ANGLE/SwiftShader。检查发现现场 OCI 不含旧成功容器 writable layer 中的两个修复：

~~~text
C /system/lib64/libEGL.so
C /vendor/lib64/hw/vulkan.pastel.so
~~~

新容器补入的已验证哈希为：

~~~text
3ff77c7f09fcad34be75b71d36fc9ff1edefae06b88fea35d932124507d3cfd4  /system/lib64/libEGL.so
86d29a36fc10ad51df541f419ecf44ee7a0165f752db8b57d579bca0f2029dbc  /vendor/lib64/hw/vulkan.pastel.so
~~~

observer APK 以 `adb install -r -d --force-queryable` 安装，SHA-256 为：

~~~text
f37379fde001ee60f3916cbd56163fef55181d16e889383237968f7e7ea23401
~~~

修复后 maps 出现 `libEGL_alasx.so` 与 `libGLESv2_alasx.so`，observer 为
`flags=15`、`main_thread=true`。这只证明当前容器恢复；下一步必须重新封 OCI。

## 资源流程

所有输入都来自当前完整 typed frame，并检查前台 package/PID、正式 2500 ms freshness、
唯一 path、`raycast_top=true`、bounds 和后置 generation：

| 动作 | 前置状态 | generation | 后置状态 |
| --- | --- | --- | --- |
| 基础资源确认 | Max=true，Min=false | 59 -> 64 | OtherPrefsPanel |
| 六项附加资源确认 | MAP/DORM/MANGA/GALLERY_PIC/L2D/CV 均为 true | 90 -> 94 | 28.1 GB DialogPanel |
| 开始下载 | 弹窗文字精确匹配，`/data` 47,225,080 KiB 可用 | 106 -> 112 | 下载弹窗消失 |

下载从 03:24:59Z 到 03:36:22Z，约 683 秒。所有采样的失败文件数均为 0；日志最终为
`all task end:0`，资源校验无破损，内容版本为 `9.7.328`。

下载完成后 `LoginUI2` 已加载，但全屏 `opening(Clone)` 持续存在且
`raycast_top=null`，因此没有点击它。只在完整下载会话、零失败、校验成功、无 fatal、
LoginUI2 已加载的窄条件下，执行一次带 `-force-gfx-st` 的游戏冷重启。
PID `1763 -> 2593`，私有 ANGLE 和 observer 合同重新通过，约 10 秒后进入手机号 Activity。

## 最终登录边界

最终证据确认：

- 唯一手机号输入框 `com.bilibili.azurlane:id/et_gsc_phone_num`；
- “请输入手机号”为未填写占位文本，`focused=false`；
- 唯一下一步控件 `com.bilibili.azurlane:id/tv_gsc_phone_next`，`enabled=false`；
- 页面显示“已阅读并同意哔哩哔哩弹幕网用户使用协议和哔哩哔哩隐私政策”；
- `account_input_performed=false`；
- `account_submission_performed=false`；
- `/data` 最终可用 17,523,640 KiB；宿主最终可用 33,423,900 KiB；
- 最终 PID 没有 FATAL EXCEPTION 或 fatal signal。

权威边界 JSON：

~~~text
/srv/alas-runtime/evidence/arm64-login-fresh-20260826/46-final-login-boundary.json
~~~

## 未通过范围

- 两个运行时修复尚未封入并重新资格化 OCI；
- 私有 NULL 从首次游戏启动起生效的 Agreement 转场尚未重跑；
- RedroidBackend lifecycle/recovery/cleanup 尚未在该实例资格化；
- native FBE/Direct Boot、登录后主界面、ALAS workload、soak 和发布资格未通过。
