# 满仓恢复离线调用链验证（2026-09-13）

本轮没有连接设备、点击游戏或消耗游戏资源。正常满仓、装备取消选择延迟、
接手遗留退役页三个离线场景通过。实机单进程连续链仍未取得通过证据，
General/Main 支持等级保持原状。

## 验证到哪里

正常与延迟场景直接调用已应用当前补丁的原版 `Campaign.combat()`，
没有替换其业务方法。一次调用内实际经过 `combat_preparation()`、
`handle_retirement()`、`_retire_handler()`、`retire_ships_one_click()`、
`_retirement_quit()`、`ui_back()`、`combat_execute()` 和 `combat_status()`，
最终由原版结算循环报告返回稳定战役地图。

模拟输入逐次核对当前观察到的具体 Button；装备必须先取消全选，
再取消拆解并确认保留。延迟场景在三次状态读取后才发布取消选择结果。
两个场景均产生 15 次模拟输入、一次 79 艘退役收据和装备保留后置条件。
数字来自夹具，不是本轮游戏消耗或新的实机读数。

遗留退役页场景从原版 `Main._run` 提取两段未经重写的启动恢复 AST，
调用真实 `Campaign._semantic_campaign_retirement_recovery()` 与退役处理，
再由原启动恢复段退出战斗准备并识别原地图，产生 11 次模拟输入。
这项只验证启动恢复分支，没有把整个调度器或后续选敌宣布为已回放。

## 数据与边界

满仓提示、退役选择页、战斗准备和地图使用既有 typed observer 快照。
没有完整捕获的设置、确认、奖励、装备、战斗与结算页面使用明确标记的契约夹具。
这不是完整实机流量的逐帧重放，也不证明所有奖励顺序、掉船或弹窗组合。
回放重新绑定 PID、代次和时钟以形成新鲜一致的离线帧；未生成像素数组。
原版 ALAS 执行期间，Python 子进程创建与 socket 创建均被禁止。

ALAS 从固定基线 `81ccf63b4540f00241628c82a58c02c7a2bb11af` 重新物化，
应用全部 114 个权威补丁。开发运行树与新树的所有补丁涉及文件比对一致，
只有 `run.py` 的换行形式不同。最终三场景使用新树执行，
文件哈希与补丁哈希随证据保存，避免再误用旧的已打补丁目录。

## 本轮修复

- 战斗准备不存在时，不再要求无关船坞 Toggle 列表完整；准备页实际存在时仍要求完整。
- 登录更新只读取完整文字能力及其对应按钮，不受无关 Toggle/Image 截断影响。
- 已确认空选且未被遮挡的退役页，不再进入无关演习页探针来判断游戏提示不存在。
- 原 Main 启动恢复除满仓弹窗外，也接手已停在退役选择页的状态，仍调用原退役处理。

此前结果探针和登录失效确认探针的修复一起纳入验证。缺失必需文本、遮挡、
错误前台、装备选中状态未消失或库存改变仍拒绝继续。

## 验证与复跑

证据目录：`integration/alas/campaign-midmap-offline-20260913/`。
`normal.json`、`delayed.json`、`inherited.json` 保存原方法调用轨迹和模拟输入；
`runtime-sources.json` 保存源树比对；补丁系列、干净树应用、支持矩阵、
原版退役配置与 Main 共享配置均单独验证。

聚焦回归共 70 项。另行扩展到战斗准备套件时有一项既存事件模式断言失败；
将该方法替换为 Git HEAD 原文后仍复现，记录于 `baseline-mode-test.log`。
本轮没有改写该断言或修改未涉及的模式逻辑。

```powershell
$env:PYTHONPATH = 'python'
python scripts/python/replay_alas_midmap_retirement.py `
  --alas-root artifacts/midmap-offline-canonical-20260913 `
  --output artifacts/midmap-offline-normal.json
# 另外两种场景分别加 --delayed-equipment 或 --inherited-selection
```

下一次自然满仓时验证单进程实机链，继续保留本次离线与此前分段实机证据的区别。
不为制造条件刻意填仓。
