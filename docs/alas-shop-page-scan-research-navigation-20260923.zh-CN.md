# 商店回主页时的页面扫描缺口（2026-09-23）

原 ALAS 从已打开的商店执行 `ui_ensure(page_main)`，`shop/home` 语义输入成功后，通用 `Page.iter_pages()` 探测尚未映射的 `SUPPLY_PACK_CHECK`，第一次现场运行因此失败。失败原始记录保留为 `artifacts/research-navigation-20260923-r3.json`（SHA-256 `59823e9aca8920ceb421bdd1a226a6fb95a78c3485f5cebbaa1b4014d6c5d4799`）。

适配器现在只在完整商店壳身份成立、`shop/home` 目标存在时，把同一轮通用页面枚举中的其他页面检查判为缺席，`SHOP_CHECK` 仍返回存在。未知输入仍拒绝，商店壳消失后未知页面检查恢复原有报错。未增加坐标、截图或 ALAS 导航状态机。

定向测试：商店、边界、Research 与任务隔离共 **109 passed**；`git diff --check` 通过。增加 `--start-from-shop` 只读导航探针选项，使用原 ALAS 导航先进入商店，再返回主页、进入 Research、读取五张卡与五个队列项、回主页。`artifacts/research-navigation-20260923-r5-shop.json` 为 `passed=true`、`shop_before_main=true`、`home=true`、重复入口未增加输入，SHA-256 `632e15eb2c1f9193147d3de62d79a0118928fa315de3730835cccb6a63d95569`。本轮队列五项自然完成且可领取；探针未领取、未开工、未购买，Research 支持等级不变。
