# PrivateQuarters 升级关闭候选实现（2026-09-26）

后续进展：同日已完成增量构建、安装和零互动导航验证，见[部署记录](private-quarters-observer-deployment-20260926.zh-CN.md)。下文保留实现阶段的验证范围；实际升级关闭仍未验证。

本轮补上观察器的升级背景 Button 命中搜索与 Python typed 关闭端口，接入原 ALAS 的 `PRIVATE_QUARTERS_ROOM_BACK` 边界。**这是离线通过的候选代码；未更换设备观察器，未实机关闭升级弹窗，PrivateQuarters 仍为 P。**

## 原因与实现

等级 4 的[真实失败帧](../integration/alas/private-quarters-continuity-20260926/private-quarters-levelup-observation-20260926.json)中，观察器已通过 Unity Button 枚举导出 `OverlayCamera/Overlay/UIMain/LevelUpWindow/bg`，但原先只在其中心检查顶层命中。中心被兄弟节点上的解锁装饰覆盖，背景与房间返回均 `raycast_top=false`，因此不能输入。

新增 `PrivateQuartersRaycast.h`：只在这个精确 Button 的实时矩形与屏幕交集内检查最多九个整数点，拒绝空/非有限矩形、越界点和取整后落在边界上的点。每个候选必须通过真实 `EventSystem.RaycastAll` 首命中检查，确认该 Button 或其子节点拥有命中才发布。坐标来自当前控件几何，不使用历史坐标；没有命中则继续导出不可用。其他控件的采样行为不变。

Python 增加 `private-quarters/level-up/close`。它仅在真实私密船舱 base 页面存在时接管原 `ROOM_BACK`：先核验唯一升级 Button、可操作性、顶层命中、整数点、控件边界、遮挡、精确包/前台/PID和新鲜状态。原循环保护使用弹窗控件路径，避免与后续 base 返回混为同一控件。

关闭只发送一次输入，随后最多等待五秒，要求新代次中弹窗所有已导出活动控件消失，房间返回重新可操作且顶层命中。未确认则报“输入已发送、后置条件未证明”并停止；不会连续点击或穿透房间。正常房间返回路径不变，ALAS 继续控制互动次数、返回循环、计时、错误和调度。

## 验证与限制

- 新增八项聚焦测试：C++ 边界/整数点搜索编译执行、真实命中与全遮挡、关闭后新代次房间返回、旧观察器 false/unknown 拒绝、重复目标/非房间拒绝、浮点点位拒绝、发送一次后的超时、等级 4 原始失败帧零输入回放。
- PrivateQuarters 观察、物理、配置回归通过；已有 C++ raycast 选择器测试发现测试程序遗漏 `<string>` 头文件，已只修正该测试程序依赖，三个选择器测试通过。
- 未运行完整 Android/ANGLE 构建或安装。当前弹窗已由上轮冷启动恢复消失，今日互动次数已耗尽，本轮不消耗额外资源制造等级条件。测试编译的是新增原生搜索函数和既有选择器，不能据此声称完整 Android 库编译或实机能力成立。

后续在可验证实机关闭的开发窗口做本地单 ABI 增量观察器构建、保留回滚 APK，并按冷启动合同部署。自然升级出现时，记录关闭前后代次、精确命中点与收据；只有完整原任务互动→关闭升级→退出→调度/回主页通过，才补对应资格证据。仅更换观察器或离线通过不提升支持等级。
