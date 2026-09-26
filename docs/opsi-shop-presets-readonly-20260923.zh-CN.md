# OpsiShop 五预设只读实机核对（2026-09-23）

按[任务表](alas-adaptation-task-board.zh-CN.md)选择无需购买授权的五预设分支。运行时发现唯一设备 `emulator-5554`，确认游戏包 `com.bilibili.azurlane` 的 PID 为 `18011` 且处于前台。使用固定观察端修订 `506b76f698b5089aaa29c4e7908b48edb8532a44`，原 ALAS `OpsiShop` 从大世界地图进入利维浦港口商店，扫描同一批 19 张语义商品卡，再退出港口并正常结束任务。

新增的[只读脚本](../scripts/python/run_alas_opsi_shop_presets_readonly.py)为本次运行复制临时配置，设置购买预算 0，并在原 ALAS `Selector.items_filter_in_os_shop` 调用处对同一批原生 `Item` 依次运行 `max_benefit`、`max_benefit_meta`、`no_meta`、`all`、`custom`。脚本同时把实际购买入口设为抛错，完成后恢复方法并删除临时配置。未修改正式配置，也未提交任何交易。

[实机收据](../artifacts/opsi-shop-presets-readonly-20260923.json)记录语义代际 `549679`、特别兑换凭证余额 `719` 和 19 张卡的商品名、价格、币种、余量。四个内置预设各选中 4 张 `DevelopmentMaterialT3`；本次指定的 `custom = DevelopmentMaterialT2 > ActionPoint` 选中 0 张，符合 T2 与行动力商品均已售罄的观察。运行 `passed=true`，原任务返回 `True`。

这个结果证明五种过滤配置可在真实库存上完成只读决策；由于当前唯一在售商品种类为 `DevelopmentMaterialT3`，不能据此证明四个内置预设在差异商品上的排序或购买后效果。黄币商品当前余量为 0，黄币正向购买、余额不足、刷新与其他港口仍需后续自然库存和授权。`OpsiShop` 保持 `L`。
