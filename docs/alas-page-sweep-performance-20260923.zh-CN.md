# ALAS 页面枚举的冻结帧读取优化（2026-09-23）

## 问题和定位

在现有 ANGLE NULL、语义模式和 `emulator-5554` 上，ALAS 从商店页扫描 `Page.iter_pages()` 的 33 个页面候选需要 134.547 秒。探针只调用 `ui_page_appear`，没有发送输入。单个不存在的页面候选的性能剖析显示，同一冻结帧内的 `SemanticOracle.read_state()` 会反复调用 ADB 查询前台组件；这不是新的观察帧或页面跳转。

## 修改

`SemanticFrameClock.acquire()` 仍在取得帧时通过实时 Oracle 验证准确的前台组件、包、PID、观察端点和代次。该帧的只读 Oracle 在随后匹配页面时复用这份已验证的前台身份，并继续借用同一个不可变帧。帧失效、PID 或运行时身份变化仍会拒绝读取。

部分动作也使用帧 Oracle 作最后一次语义目标确认，因此其点击和滑动入口现在额外查询实时前台组件；不匹配即拒绝输入。原有的输入前帧时效检查、帧失效处理和运行时输入路径继续执行。此修改没有扩大任务或资源支持范围。

完整 Freebies 回归首次在档案页返回商店时停住：第一次 `main/shop` 已输入，ALAS 仍在过渡帧中识别到主页并重复请求同一导航，但实时目标已从主页消失。随后只读探针确认实际商店页已挂载。适配器现在只在首次输入回执存在、时间窗内、新代次确认准确商店页时，复用该回执；其他状态仍保留原来的目标缺失错误。

## 结果与边界

| 相同商店页面只读探针 | 修改前 | 修改后 |
| --- | ---: | ---: |
| 候选数 | 33 | 33 |
| 最终识别页 | `page_shop` | `page_shop` |
| 用时 | 134.547 秒 | 8.047 秒 |

本次单次对照约快 16.72 倍；它只证明此设备、此页面、此观察状态下的页面枚举收益，未测量完整任务耗时或其他页面。原始结果保留在 `artifacts/page-sweep-shop-before-20260923.json` 和 `artifacts/page-sweep-shop-after-frame-cache-20260923.json`。可复用的只读脚本为 `scripts/python/probe_alas_page_sweep.py`。

重跑原版 ALAS Freebies 完整流程返回成功，用时 128.203 秒，战令无可领项、档案钥匙 `300/300`，没有补给包领取等资源动作；临时配置已删除。原始失败与成功记录分别保留在 `artifacts/freebies-after-frame-cache-20260923.json` 和 `artifacts/freebies-after-frame-cache-r2-20260923.json`。之前的 669.125 秒完整流程与本次起点及状态不完全相同，不能将两次完整耗时之比当作独立性能基准。

验证：`tests/test_alas_adapter_shop.py`、`tests/test_adapter_frame.py`、`tests/test_adapter_session_runtime_handle.py`、`tests/test_alas_adapter_boundary.py`、`tests/test_semantic_task_isolation.py` 共 133 项通过，包括前台切走后拒绝点击、过期帧拒绝输入、未确认商店页时拒绝复用导航回执。没有执行新的任务支持晋级。
