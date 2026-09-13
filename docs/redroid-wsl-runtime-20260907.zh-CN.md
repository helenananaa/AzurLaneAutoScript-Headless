# 本地 WSL Project runtime 生命周期验证

2026-09-07：本地 WSL Docker Project 已接入统一 `redroid` runtime backend，
完成登录前冷启动、游戏重启和 Android 容器重启闭环。ALAS 原状态机与补丁未改动。

## 实现

- `runtime_backend_redroid_wsl.py` 继承已有 Redroid 生命周期，仅适配本地 WSL Docker
  宿主探测、容器身份、Project manager 启停与登录前 SDK 状态。
- Windows manager 的 `Config` 动作导出 `container_engine: wsl-docker` 配置。
  操作前检查实际容器的镜像、可写 `/data` 绑定和 loopback ADB，并确认 manager
  将要操作的目标与所选配置相同。Docker 固定连接该发行版的本地 socket。
- SDK 恢复只在已知 Announcement 暂停且 observer stale/unavailable 时尝试一次
  HOME→MainActivity；要求同 PID、无当前游戏 fatal、正确 Unity extra 和恢复后的
  新鲜递增帧。该分支本次有聚焦单元测试，最终实机三轮没有触发它，不能称为本轮
  新取得的 SDK 异常恢复实机覆盖。
- 原生手机号页只返回 `account-input-required`；不当作 Unity observer 就绪。
  检查唯一空输入、唯一 disabled 下一步、前后台 PID/component 未变化与 `Accounts: 0`。

## 实机结果

权威运行收据：`evidence/redroid-wsl-runtime-20260907-r1/run-4/manifest.json`。
该轮执行期间实现文件未改变，`passed=true`、`cleanup_passed=true`。

| 路径 | 游戏 PID | 第一组 generation | 到空登录页用时 | 结果 |
|---|---:|---|---:|---|
| 冷启动 | 3074 | 1 → 5 | 29.141 秒 | PASS |
| 游戏进程重启 | 3679 | 1 → 5 | 41.719 秒 | PASS |
| 容器重启、ADB 重连和游戏冷启动 | 1634 | 1 → 5 | 62.156 秒 | PASS |

三轮均继续观测到后续 generation 推进，然后到达空 `PhoneLoginActivity`。
容器重启明确观测到 ADB offline；清理释放 observer 转发，保留原本运行中的容器。
最终游戏停在空登录页，没有账号输入、游戏任务输入或高级货币消耗。

`postcheck.json` 独立核对了 Android fingerprint/API、游戏 APK、libil2cpp 和
ANGLE APK 的真实设备身份，均与本轮 lock 相符；资源版本仍为 `9.7.356`，
`/data` 为 `0771`、owner/group 为 `1000:1000`。没有重新扫描或复制约 57.8 GB 资源。

本轮 lock 为本地开发身份，core commit 为 `73215f2`，工作树含未提交改动；
实现文件 SHA-256 随运行收据保留。ANGLE 输入清单取自当前补丁和 overlay 文件；
资源 manifest 使用此前的资源更新收据。它不代表独立重建或完整资源逐文件复验。

## 发现并修复的问题

1. **重复 Start 改坏 `/data` 权限。** 旧脚本无条件执行
   `install -d -m 0700`。运行中的 Android 还能保留已打开的页面，但下一次冷启动
   因无法打开 APK、resource-cache 而出现 Java fatal。现在仅首次创建目录时设置
   0700，保留 Android 已建立的权限。当前根目录按镜像中 init.rc 的配置恢复为
   `0771 system:system`，没有递归 chmod/chown、重装游戏或清空 userdata。
2. **WSL 保活进程持有调用方的输出管道。** Python 捕获输出调用 manager 时，
   PowerShell 已退出而调用仍等待。保活进程现在使用 ShellExecute 和 Hidden 独立
   启动；修复后 captured Start 为 4.78 秒，并在最终容器重启链路中自然返回。

`run-2` 保留首次启动失败，`run-3` 保留两条路径成功及 manager 输出管道问题，
两者都不作为通过凭据。第一次 lock 生成因资源身份使用了资源版本而非 APK 版本
被现有校验拒绝，修正身份计算后才执行；没有降低 lock 校验。

## 离线验证与边界

- 相关 runtime、observer、CLI、Project/G4/协议脚本回归：**104 passed，2 skipped**。
- PowerShell AST、Bash `-n`、Python 编译和 `git diff --check` 通过。
- 聚焦覆盖错容器/镜像/数据目录/端口、manager 目标漂移、重启顺序、空登录边界、
  observer PID/schema/freshness、SDK fatal/无关页面/重复恢复，以及重复 Start 权限保持。

仍未资格化：账号登录、Redroid 上的 ALAS 工作负载、镜像候选回滚、长期 soak、
多实例和原生 Linux 行为。未修改 ALAS 任务支持台账或把登录前结果升级为任务支持。

下一步可在账号授权后复用原 ALAS 做主页导航和一个固定任务；没有账号时仍可独立
推进保留 userdata 的镜像回滚设计与验证，但不得据本轮结果声称回滚已经完成。
