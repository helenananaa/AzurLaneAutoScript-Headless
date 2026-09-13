# Redroid x86_64 蓝牙硬件镜像裁剪

本轮将蓝牙模拟硬件从 x86_64 镜像构建中移除，不再依赖每份 userdata 的蓝牙 OFF
设置。范围是无账号、本地 WSL 的一批可回退镜像变更；不是全部系统服务裁剪。

## 依赖核查与变更

- `device/redroid/redroid.mk` 原来无条件加入模拟蓝牙 HAL 和对应 VINTF manifest。
  新补丁 `0010` 仅在 `redroid_x86_64_only` 排除二者，并安装一个声明
  Bluetooth/BLE unavailable 的权限 XML，覆盖通用 handheld 硬件声明。
- `frameworks/base/services/java/com/android/server/SystemServer.java` 已有缺少
  `FEATURE_BLUETOOTH` 时跳过 BluetoothService 的分支。本轮复用该分支，
  不修改 SystemServer，不额外停止服务或加入启动脚本。
- 新补丁 `0009` 在同一产品中移除 BluetoothMidiService。
- 保留 `com.android.btservices.apex`：其中 framework-bluetooth 位于 APEX
  boot classpath。直接删除整个 APEX 涉及 framework API/类路径兼容性，
  本轮没有做这种扩展。因此这里的“裁剪”指 HAL、硬件能力、MIDI 应用和服务启动
  路径，不代表磁盘上所有带 bluetooth 名称的代码都被删除。
- ARM64 的 make 分支保持原行为；本轮没有构建或资格化 ARM64。

其他残留组件也已核查到：cameraserver、virtual_camera、TeleService/Telecom、
NFC、AdServices、HealthFitness 等仍在构建产品中。它们与 framework、APEX 或
其他系统功能的依赖不同，尚未逐项完成依赖和启动验证；不能据名称认定它们都可
直接删除。本轮不把这些未处理项列为“已裁剪”。

## 构建

先运行 Windows 构建盘挂载脚本，核对 KVM/Redroid UUID，确认源树属于独立
`ALAS-Android-Build` 发行版的 `alas-redroid-build` 账户。核查保留 manifest、
1363 个项目清单、已有同步收据和干净的 `repo status` 后，复用现有源树及输出。

新 source lock 为：
`c0d5db9ae0471a5da66ca818e21345aa755ea864a31f0de882555d374001691e`。
新增补丁由已有 rebind 工具核对、应用并记录，旧构建收据未覆盖。
首次 rebind 在补丁提交后因新运行目录缺少 apply log 退出；复制已有原始 apply log
到新证据目录后重试，工具验证已应用补丁的精确提交，没有重复应用或放宽检查。

实际 WSL 预检通过：约 58.9 GiB RAM、16 GiB swap、约 800 GiB VHD 空闲，
宿主 E 盘约 2.1 TiB 空闲。以 J32 增量构建，主构建 4:23、SBOM 2:32，
完整 wrapper 退出码 0。编译保持普通构建账户，只有 OCI 挂载/打包使用 root；
system/vendor 镜像和归档最终均归构建账户所有。

构建证据位于：
`/srv/android-build/redroid/evidence/x86_64/bluetooth-trim-20260908`。
包清单、WebView ABI、locale/font、ext4 时间戳、运行库、SBOM、provenance 检查通过。
libEGL 和 Pastel 的 SHA-256 与旧镜像一致。

可部署候选保留在：
`H:\program\AzurLaneAutoScript-Headless-localdata\redroid-x86_64-candidates\bluetooth-trim-20260908`。

- OCI identity：`sha256:86476dea211e3b010d6ebbc50394360af363f9d17e01eb49782fccfe2c78763f`
- OCI tar SHA-256：`b1679247dc6a78e899351c6cd07ddd3ad829cf1dc4658a7ce8f1a3b85ec18d5f`
- OCI tar：1,349,580,800 bytes，旧版 1,358,192,640 bytes，减少约 8.21 MiB。
- 导出归档已重新计算 SHA-256，与构建收据一致。

这是一轮本地增量构建，不是独立 clean rebuild 或可复现构建证明。

## 运行验证方法

`scripts/python/qualify_redroid_bluetooth_trim.py` 复用既有 image trial，使用停止的
Project userdata 作为只读 lower，临时完成 baseline→candidate→rollback。
原 Project 的控制文件哈希、数据标记恢复和临时挂载清理仍由原框架检查。

为排除旧数据中的 OFF 设置掩盖缺陷，在**临时 baseline overlay** 中开启蓝牙。
候选必须继承 `bluetooth_on=1`，同时满足：无 Bluetooth/BLE feature、无
bluetooth_manager、无蓝牙进程/模拟 HAL、无对应 init 服务。回滚后必须恢复旧
镜像的蓝牙能力与 manager。该检查仅用于这项镜像资格化，不影响日常 runtime
启动或其他 ALAS 任务。

候选还会在临时数据层中重装同一份固定 SHA-256 的 ANGLE APK，再经
`-force-gfx-st` 启动游戏，检查新鲜递增语义帧与唯一空登录边界。没有登录输入。

离线聚焦验证：包策略、补丁 rebind、构建脚本 31 passed；蓝牙验证与既有镜像
trial 23 passed，共 54 项。覆盖残留 HAL/MIDI 被拒、API APEX 可保留、无关服务
可继续存在、ON 设置不能被 OFF 掩盖等。本轮未修改 ALAS patch series 或支持台账。

## 运行结果

实机执行结果在 `evidence/redroid-bluetooth-trim-20260908/live-run-1/manifest.json`。

| 阶段 | 到空登录页及阶段检查耗时 | 语义帧检查组数 | 蓝牙结果 |
|---|---:|---:|---|
| 旧镜像 baseline | 53.360 秒 | 4 | feature/manager 存在，在临时数据层开启蓝牙 |
| 新镜像 candidate | 60.344 秒 | 5 | 保留 ON 设置，但 feature/manager/蓝牙进程/HAL init 均不存在 |
| 旧镜像 rollback | 58.313 秒 | 4 | feature/manager 恢复 |

候选 ANGLE APK 重装返回 `Success`；三个阶段都有新鲜递增语义帧，最终为
唯一空手机号输入框、禁用的下一步、`Accounts: 0`。没有账号输入、游戏任务输入
或高级货币消耗。安装清单确认 MIDI 和模拟 HAL 移除，约 22.17 MiB 的
btservices APEX 仍保留，不能将其宣称为完整蓝牙栈磁盘移除。

最终 manifest 和独立 `verification.json` 均 PASS。回滚保留基准标记、移除候选
新增标记；原 Project 抽查控制文件哈希不变。临时容器、overlay 挂载及其写层
清理完成，原 Project 恢复后再次通过语义帧与空登录边界，最后恢复为停止状态。
这些是抽查文件与标记恢复证据，不代表全盘逐字节复验或任意版本迁移兼容性。
Project 默认仍指向旧 `current` 候选，新镜像保存在独立候选目录；本轮没有替换
Project 默认镜像、覆盖原 userdata、验证战斗性能、测试长期 soak 或扩大 ALAS 支持。
