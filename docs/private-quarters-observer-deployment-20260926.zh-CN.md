# PrivateQuarters 观察器候选构建与部署（2026-09-26）

升级关闭候选已完成本机 **x86_64 增量构建、安装、冷启动和语义健康检查**。真实升级弹窗尚未再次出现，不能把启动/导航通过当成关闭能力通过；PrivateQuarters 保持 `P`。

## 构建与回滚材料

先运行本机挂载脚本，`findmnt` / `blkid` 核对 KVM UUID `7febc493-864e-4e35-a01c-3090515de95e`、Redroid UUID `fd5ab68a-32b8-4fd7-987c-3b1c0575a12f`。本轮未进入或修改两套 AOSP checkout，也未做 AOSP 同步/镜像构建或完整主机资格声明。

复用 Ubuntu-22.04 下 `helenanana` 所有的 `/home/helenanana/src/alas-headless-angle/angle`；固定 ANGLE 基线 `be80ce591a481c12d60c50d6040d40c035b40a2b`，输出 `out/AndroidNullObserverX64`。已核对源码与候选仅差本次升级命中改动，先备份旧 CPP/APK，再同步 CPP 与新头文件；未改其他构建树。可用内存约 53 GiB、可用磁盘约 222 GiB。

使用普通用户运行 `autoninja -C out/AndroidNullObserverX64 -j8 angle_chromium_apk`，**10.64 秒、12 个步骤**成功，包含 `Il2CppNamespaceProbe.cpp` 实际编译和链接。随后执行现有私有加载器打包/签名校验；构建源和输出仍由该用户拥有。未做 clean build、第二次独立构建、ARM64、长时测试或全镜像重建。

| 材料 | SHA-256 |
|---|---|
| 候选 APK / 设备已安装 APK | `f5d3d11f9f5ac529b8c9f7ca931440d924f869355b8beea197b914439660c1dd` |
| 从设备拉取的原 APK | `dc4a85c5be094add97f24dec2fe78632a835cd9f42f5d742870b54ea747ca1f6` |

两份 APK 保留于 `artifacts/private-quarters-observer-20260926/` 的 `candidate.apk` 和 `rollback-installed.apk`。这是保留了可重装的旧产物，**本轮没有执行回滚复测**。构建前本机文件备份另保留在 WSL `~/build/private-quarters-observer-20260926/`。

## 设备证据

发现并绑定原 AVD `emulator-5554`，仅替换 `org.chromium.angle`。游戏 userdata、原 AVD 和 ANGLE NULL 配置保留；精确包 force-stop 后用 `--es unity '-force-gfx-st'` 冷启动 `com.bilibili.azurlane/com.manjuu.azurlane.MainActivity`。

新 PID **27842**，驱动导出修订仍为 `506b76f698b5089aaa29c4e7908b48edb8532a44`。该字符串不区分本次候选，必须同时记录 APK 和源码哈希；不能仅凭修订字符串认定加载了新构建。设备 APK 哈希与候选一致，进程 maps 也确认加载了该次安装路径中的 `libGLESv2_angle.so`。

启动初期五次读取因前台尚未就绪被拒绝，未输入。随后五组状态代次 **250、263、269、292、315** 持续递增，与对应 UI 代次一致或相差不超过 2；采样年龄 17–1795 ms。原 ALAS LoginHandler 登录并回主页通过。

部署日志、健康采样、源码/二进制哈希和导航收据索引见[部署收据](../integration/alas/private-quarters-observer-deployment-20260926.json)。安装成功与健康采样不承担弹窗关闭结论。

## 导航回归与后续

首次零互动导航在登录后页面过渡的 `MAP_PREPARATION` 处停止；确认新鲜主页后第二轮到选房入口，又在 `FLEET_PREPARATION` 停止。两份失败保留。将同一组已知战斗被动探针统一放入已有 PQ 入口/回程窗口，且只在没有 campaign owner 时生效；过期后恢复原行为，未增加任何输入放行。

PrivateQuarters、Exercise、Daily 聚焦回归 **76 passed**。本轮没有重新消费互动次数、购买礼物或触发付费操作。下一步是自然升级时验证实际关闭点、后置条件和完整原任务；不通过改写等级或追加消费伪造条件。

修复后第三轮零互动导航通过：原任务读取 **0/3**，写入 **2026-09-27 00:00:00**，再由原 UI 导航返回主页，互动输入 **0**，临时配置已删除。最终游戏停在主页。此结果证明安装后的基础导航可用，不证明升级关闭或三次互动连续链。
