# 科研入口转场：重复点击修复

原生 ALAS 从主界面进入科研菜单时，旧帧仍可能识别 `page_main_white`，再次提交 `MAIN_GOTO_RESHMENU`。此时 `main/tech` 已消失，之前会报 `semantic target is absent: main/tech`。现场失败保留于 `integration/alas/meta-reward-20260912/character-navigation-r2.log`。

现在仅在已有真实入口回执、更新代次中的科研菜单返回控件存在且可操作时，复用原回执，不再次点击主界面下层。若源控件恰在输入前消失，再检查一次同一目标页面；已经发生输入的异常仍向上传递，不吞掉不确定结果。任务重置清除缓存。ALAS 原来的 UI 导航循环保持不变。

实机连续执行两轮原生 `ui_ensure(page_reshmenu)` → `ui_ensure(page_main)`：

| 轮次 | 科研入口实际输入 | 重复请求 | 结果 |
| --- | --- | --- | --- |
| 1 | 1 | 无 | 进入科研菜单并返回主页 |
| 2 | 1 | 1 次，实际输入为 0 | 进入科研菜单并返回主页 |

第二轮自然复现了旧帧重复入口，完整流程没有中断。两轮共 4 次实际导航输入；没有开战、领取、购买或修改编队。

45 项聚焦测试通过，覆盖目标缺失、不可操作、代次未推进、输入前竞态、已发出输入后不吞异常、缓存重置及无关任务隔离；Research 配置验证通过。支持矩阵校验记录于同一证据目录。

证据：[live.json](../integration/alas/research-navigation-20260912/live.json)、[live.log](../integration/alas/research-navigation-20260912/live.log)、[tests.log](../integration/alas/research-navigation-20260912/tests.log)、[research-config.json](../integration/alas/research-navigation-20260912/research-config.json)。本轮仅验证公共科研菜单导航，不提升 Research、Shipyard 或 META 子任务的其他未验证分支。
