# 登录恢复船坞返回映射（2026-09-13）

上轮冷启动恢复处理科研进度提示后进入船坞。原 LoginHandler 的 ui_additional 检测到 SHIPYARD_CHECK，却持续得不到 GOTO_MAIN；普通导航可返回，登录恢复不行。

原因在 adapter/flows/login.py 的独立 goto_main_target 候选缺少已有的 shipyard/page/root → shipyard/page/back。补上该映射，使原登录观察和输入共享同一目标解析。原 ALAS 登录循环、导航选择、定时器及成功判断保持不变；未新增任务状态机或输入后备路径。

船坞根节点与可操作的返回控件必须同时存在；多个主页目标仍拒绝，实际输入继续经过现有包名/PID/前台、帧新鲜度、遮挡、唯一目标边界。导航不读取蓝图库存、研究阶段或可选船卡字段，避免局部不支持阻止退出。

## 验证

- tests-focused-r2.log：51项登录适配及船坞测试通过，含无根节点、不可操作、歧义拒绝，以及新增/缺失可选数据仍能导航。
- tests-isolation.log：48项登录底层与任务隔离测试通过；合计99项定向通过。
- 扩展 tests-r1.log：61通过、5失败；撤去本轮唯一映射再执行同一登录Flow测试得到同样5项失败（parity-baseline.log，13通过）。失败是既有facade与独立flow的额外观察调用序列不一致，未修改断言。不能宣称扩展套件全通过。
- 本轮未改ALAS补丁，保持116成员；不因单一恢复分支推进Shipyard或其他面板等级。
- 实机入口 scripts/python/run_alas_login_shipyard_recovery.py：原导航到真实船坞，再调用原 LoginHandler.handle_app_login，保存前后typed状态、源文件哈希及回执。范围是已登录船坞的恢复，不是重新执行冷启动或科研进度提示触发链。

证据目录：integration/alas/login-shipyard-recovery-20260913/。

实机r1保存passed=false：原登录处理器返回，但回执采集仅包住live oracle，漏掉冻结帧路径的click；同时返回科研菜单后立即判断主页。后续r2改在session.click采集，分别记录login_handler_returned与原ui_ensure(page_main)到达确认。没有为此改变ALAS原生返回条件。

最终 live-r2.json/log 为passed=true：原LoginHandler在PID17906、固定观察器修订506b76f698b5089aaa29c4e7908b48edb8532a44上发出shipyard/page/back（generation16006），正常返回；原ui_ensure随后发出research-menu/page/back并确认主页。全程仅导航，不购买、不强化、不消耗蓝图或每日次数。记录中的两条research-menu/shipyard为同generation同回执的原导航重试确认，不应计为两次实际输入。

本轮闭合的是船坞登录恢复分支加原导航到主页。尚未重跑冷启动→科研进度提示→船坞的完整触发链；上轮失败保留。未来若要提升冷恢复支持声明，应在真实提示再次出现时验证该链，不需要人为制造消费。
