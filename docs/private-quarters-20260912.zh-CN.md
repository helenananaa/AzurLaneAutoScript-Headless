# PrivateQuarters 初步实机接入

本轮把独立宿舍从纯离线配置验证推进到选房页、真实次数读取和一条新泽西房间访问路径。固定 ALAS 为 `81ccf63b4540f00241628c82a58c02c7a2bb11af`，设备为已发现的 `emulator-5580`，保持 ANGLE NULL 和 typed-only 输入。

## 已验证

- `SelectDorm3DUI` 选房页识别、当前地点及真实互动次数。现场是“汐语小筑”、3/3；未知或畸形次数不会变成 0。
- 补丁成员 0660 把原生 `status_get_daily_count()` 接到语义帧。传统模式的 OCR 路径保持不变。
- 原生 `PrivateQuarters.run()` 在 BuyRoses=false、BuyCake=false、TargetInteract=false 时完成进入及次日调度；随后原生次数方法读到 3，原生 UI 返回主页。证据 `noop-live-r6.json` 为 passed=true。此测试从已准备好的生活区菜单开始。
- 新泽西入口通过精确房间图标、解锁状态和原生命中验证；有锁标记、解锁信息不完整、未知命中或遮挡均不输入。
- 单次房间诊断完成选房、进入新泽西房间、推进无选项问候、调用**原生 `_pq_goto_room_exit()`**回选房页、再回主页。`room-probe-r2.json` 为 passed=true，互动次数前后均为 3。
- 房间内实际观察到“客厅”、好感等级 2、进度 140/200。继续对话端口仅覆盖当前新泽西单句问候，其他角色和选择题保持拒绝。

## 修复的阻塞

生活区菜单之前会被下层主界面抢先识别，导致重复点击已经被遮挡的入口。现在让准确菜单拥有页面识别，并在已观察到目的地时复用真实入口回执。独立宿舍入口和 `PQ_GOTO_MAIN` 的旧帧重复请求也按明确目的地处理，不多发输入。

房间返回按钮的原始 pivot 在边缘，不能通过命中验证。观察器改为计算可见按钮内部的整数点，并重新执行 Unity EventSystem 命中验证；最终原生退出方法使用该点完成退出。

日次数读取失败仅关闭次数消费路径，不阻止独立的安全返回。返回不依赖不相关的次数或当前地点文本。

## 仍未完成

真正的三段日常互动、三次循环消费、完整自动选角色/切换地点、其他角色、商店、送礼和礼物购买均未资格化。房间诊断的进入与问候采用新的语义端口，不能冒充原生 `TargetInteract=true` 全任务通过。四个配置字段的完整启用行为也没有提升为支持；面板仅记为部分支持。

本轮没有开战或购买，已验证的房间访问没有消耗 3/3 互动次数。最终回到主页。早期失败的导航、加载和登录尝试保留，没有改写为成功。

## 构建与证据

仅做本机 WSL x64 NULL 观察器的三次 J32 增量构建，分别 11.72、11.31、14.15 秒；没有 AOSP 镜像构建。最终 APK 为 `artifacts/private-quarters-20260912/observer-r3.apk`，SHA256 `5f265b9cecf4b1ac444b7ebcbaebb98842d96c3ae12c6332d646af52767b2b21`，设备安装包校验一致。上一轮 APK 与本轮早期 APK 均保留，本轮没有执行回退验收。

113 个补丁成员在干净固定上游应用并编译通过，含新增 `module/private_quarters/status.py`，总变更上游文件数由 150 变为 151。登录回放、帧时钟、像素清单及 PrivateQuarters 配置验证通过。最终测试及支持矩阵结果见证据目录。

最终聚焦回归 80 项通过；另有 57 项输入边界/任务隔离检查通过，覆盖通用 click 不能绕过房间解锁、说话者或对话选项检查。返回主页时钻石 5040、石油 6193、金币 32890，与本轮开始一致。

证据：[private-quarters-20260912](../integration/alas/private-quarters-20260912/)。入口/对话/房间原始状态分别见 `entry-r2.json`、`room-state.json`、`dialogue-r2.json`、`room-controls.json`；成功原生禁用分支见 `noop-live-r6.json`；最终房间闭环见 `room-probe-r2.json`。

可复用入口：`scripts/python/run_alas_private_quarters_overview_live_validation.py` 与 `scripts/python/run_alas_private_quarters_room_probe.py`。二者都保存失败，不放宽像素、前台、代次、目标和命中边界。

## 后续互动适配

后续已执行原生三次互动循环，并遇到好感升级弹窗阻断退出；完整任务仍未通过。详见 [物理点击与互动记录](private-quarters-physics-20260912.zh-CN.md)，此处早期 3/3 房间访问记录保留为历史证据。
