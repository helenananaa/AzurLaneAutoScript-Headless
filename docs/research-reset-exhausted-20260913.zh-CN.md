# Research 已用完刷新次数的观察（2026-09-13）

新增 RESET_AVAILABLE 的窄观察端口：在真实研究页、唯一 refresh 图标及“每日0点后可刷新”文字一致时返回 False，交给原 research_reset 分支处理。未知、歧义或可刷新状态仍局部拒绝；本轮没有实现或执行刷新输入。

原 research_reset 返回False、零输入，随后原 start→双资源确认→queue 合同回放通过，见 integration/alas/research-reset-exhausted-20260913/original-chain-handoff.json。它是离线原方法证据，不是新项目实耗、真实刷新或完整Research.run资格。重点回归同时覆盖旧基线、额外元数据和未知状态拒绝。
