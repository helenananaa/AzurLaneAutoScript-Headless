# 资源下载 neterror：Android 联网验证失败

## 原因

2026-09-23，本地原 AVD `alas_game_api32_x64` 的 357.2 MB / 91 文件更新在启动下载约 100 ms 后返回 `allTaskEnd: ERROR neterror`。CDN DNS 解析、TCP 443 连通以及约 16 GB 剩余空间均不足以解释或排除此故障。

实机 Android 默认网络已连接，但缺少 `NET_CAPABILITY_VALIDATED`。`NetworkMonitor` 对默认 Google 联网检测地址的 HTTPS 探测失败，HTTP 也异常。不能由此推断是 TUN 软件本身导致；本轮未修改 Windows TUN、代理或系统 DNS。

游戏 `classes3.dex` 中 `com.ys4fun.downloader.util.NetWorkUtils.isNetworkAvailable()` 在 API >= 23 时读取活动网络，并检查 `NetworkCapabilities.hasCapability(16)`。Android SDK 常量确认 16 为 `NET_CAPABILITY_VALIDATED`。`DownloadDispatcher.enqueue()` 在检查失败时直接调用错误回调、退出，不会开始资源请求。因此“CDN 可访问但下载立即 neterror”与这一网络前置检查一致。

本地 APK 与设备当前已安装 APK 的 `classes3.dex` SHA-256 均为 `eea4e1a6db89cf549b7aa440509971fda852aa93fe8664c7c440f144f9f217a7`。仅只读核对字节码，没有修改 APK、下载器或游戏资源校验。

## 本机修复

发现设备为 `emulator-5554`，确认原 AVD、包名、前台和新鲜类型化状态。模拟器启动时使用当前验证可解析 CDN 的 LAN DNS `192.168.5.1`；该地址是本次网络环境的取值，不是通用默认值。仅更换 DNS 后仍能复现失败。

原 `captive_portal_https_url` 与 `captive_portal_http_url` 均未设置。本轮在该模拟器内设置：

```powershell
adb -s <发现并核实的设备> shell settings put global captive_portal_https_url https://connectivitycheck.platform.hicloud.com/generate_204
adb -s <发现并核实的设备> shell settings put global captive_portal_http_url http://connectivitycheck.platform.hicloud.com/generate_204
adb -s <发现并核实的设备> shell svc data disable
adb -s <发现并核实的设备> shell svc data enable
```

该 AVD 当前默认网络为模拟蜂窝网络，故重连 data；不要把这组重连命令盲用于其他网络类型。更换地址前先验证当前网络可达，地址会接收 Android 的联网检测请求。保留联网验证机制，不把验证关闭，也不伪造成功。

实机 HTTPS 探测返回真实 HTTP 204，网络转为 `EVER_VALIDATED&IS_VALIDATED`。HTTP 探测仍失败，但 HTTPS 成功足以使此 Android 版本验证通过。随后通过原 ALAS `LoginHandler` 与已审阅语义输入重试、确认更新，下载开始并持续推进。

设置保存在该 AVD 的 userdata 中。回滚本次检测地址覆盖（本次原值均为空）：

```powershell
adb -s <发现并核实的设备> shell settings delete global captive_portal_https_url
adb -s <发现并核实的设备> shell settings delete global captive_portal_http_url
```

之后按需要重连该设备的网络。DNS 启动参数仅作用于本次模拟器进程。游戏冷启动始终携带 Unity `-force-gfx-st`，保留 ANGLE NULL 和原 userdata。

## 验证

下载实测完成：374,513,855 字节，界面显示 `357.2MB/357.2MB`、91/91 文件、失败 0 个，下载器返回 `allTaskEnd: COMPLETED`。完成后保留数据冷启动，游戏 PID 从 2309 变为 18011，类型化登录页版本为 `ver 9.7.385`，磁盘 `version.txt` 同为 `9.7.385`，没有重新要求这批下载。

进入主页未通过验证：冷启动后的登录页仍有 `opening(Clone)` 覆盖层，服务器名称为空，覆盖层命中归属未知。原 ALAS 登录验证还曾因前台检查 `game activity is not top-resumed` 关闭；最终重查前台已回到正确 MainActivity，但不能据此宣称登录成功。未使用坐标跳过动画，也未扩大为登录适配修改。下载修复与这一后续登录边界分别记录。

原始诊断文件保留于 `artifacts/resource-download-repair-20260923/`；[精简收据](../integration/alas/resource-download-repair-20260923/receipt.json)及下载/联网日志存于 `integration/alas/resource-download-repair-20260923/`。本轮验证了联网状态前后变化、真实 HTTPS 204、下载完成回调及更新持久化，没有改代码或支持台账，也不把此本地 AVD 修复推广成其他运行环境资格。
