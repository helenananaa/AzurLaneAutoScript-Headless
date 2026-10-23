# 主线整合与最终回归（2026-10-23）

本轮将已有 ALAS 适配、Redroid、KVM 和 Mac/HVF 成果整合回主线，并更新本机运行
入口。没有重建 Android 镜像，没有启动游戏任务，也没有提升支持台账中的等级。

## 合入范围

| 开发线 | 合入的分支末端 | 范围 |
| --- | --- | --- |
| 公共 ALAS 适配 | `f877924` | 当前语义帧、原任务连续性、手动地图、科研当前状态与原调度停止 |
| Redroid | `7cf907a` | 已包含上述适配；WSL 生命周期、当前完整 Main、日常调度和恢复证据 |
| KVM | `9075259` | 本地管理、持久化与生命周期修复、启动优化候选、公共接口延迟导入 |
| Mac/HVF | `cedbec0` | 独立后端、登录前采样、游戏/Android 恢复及 cleanup |

保留各分支提交及原始证据；状态文档的重叠追加内容均保留。公共导出接口采用 KVM
的延迟加载方式，同时保留 ALAS 的潜艇状态和 Mac/HVF 导出，避免平台合并丢失接口。

## 当前能力与运行入口

60 个面板的台账为 F=9、L=31、P=10、B=7、O=3、M=0，共 278 个唯一字段。
中英文 README 已与此口径一致。Windows AVD 与本机 WSL Redroid 的完整手动
12-4 Main、日常有界调度、配置重入、组件强化和容器恢复使用先前留存的实机证据，
不将本轮离线整合记成新实机验证。

新入口 `scripts/windows/run-alas-local-scheduler.ps1` 从自身位置定位主仓库，从
运行包 manifest 读取已有 ALAS、Python、ADB、持久配置与资源额度，转交原运行器。
默认最多执行三个原调度命令，`-Continuous` 明确启用持续模式，`-Plan` 只输出计划。
任务调度、恢复、计时与 NextRun 仍由原 ALAS 负责。

本机运行包 `E:/Runtime/ALAS/redroid-x86_64-local-20261023` 的 README 和 manifest
已转到主仓库，修改前文件另存备份。原 observer、OCI、userdata、账号、资源及
任务配置不变。manifest 的原实机提交身份保留，主线入口提交单独记录。
使用方法见[本机运行入口](local-runtime-entry.zh-CN.md)。这不是可移机安装包。

## 修复的回归问题

首次完整测试在收集商店测试时失败：该测试依赖旧工作树的
`artifacts/campaign-preparation/upstream`，并在 pytest 进程内导入 ALAS。
改为从相邻锁定上游和当前正式补丁生成真正的被测模块，执行原方法及真实 Item
类，复用已有源码回放方式验证售罄过滤及不制造像素数组。保留原断言，同时避免
给控制器 CI 引入无关 OCR、设备和 GUI 依赖。定向复验通过。

原生方法测试多处引用旧工作树的临时源码，导致执行报错或直接跳过。现统一通过
`tests/alas_test_source.py` 获取当前正式补丁树：默认从锁定 checkout 创建一次性
worktree，进程退出时清理；本机可显式复用已验证的 `ALAS_TEST_ROOT`。
历史实机帧仍按原样保留，缺失时明确跳过，不用合成数据替代。

同时更新了原生循环演进后的测试夹具：两次出击使用真实 Session 门面；
演习恢复明确配置不存在的结果按钮；导航夹具保留原 orphan-result 探测入口。
删除的 boss stage-wait 快捷分支由完整原 ALAS 结算循环测试覆盖。完整帧中缺少
邮件返回控件可返回普通不匹配，但点击、错误包名、截断帧仍拒绝；没有放宽
输入检查或增加第二套任务流程。

干净 Python 环境还暴露出 CI 缺少 `pkg_resources` 和原生 ALAS 网格/配置导入
依赖。已补全独立测试环境的依赖清单，不依赖 Anaconda 预装包；没有安装 OCR
引擎或设备驱动，也没有改动本机已有 Python 环境。

## 验证记录

完整日志、JUnit XML、补丁应用/编译收据及当前运行树比较保存在
`artifacts/main-integration-20261023/`。运行环境为 Windows、仓库 `PYTHONPATH=python`，
首轮复用 `ALAS_TEST_ROOT=E:/Runtime/ALAS/redroid-live-20261022`；最终回归取消
该变量，使用锁定上游和正式补丁自动生成的临时树。

最终统一回归：**7,948 passed / 246 skipped / 0 failed**，耗时 745.47 秒。
246 个跳过项分为 208 个留存帧或可选本地证据、30 个显式 `ALAS_TEST_ROOT`
配置用例及 8 个平台条件用例。30 个配置用例另行指向已核对的运行树补测，全部通过。
跳过项不是实机资格证明。首轮失败及中间日志保留，完整通过记录为
`full-suite-final.log` / `full-suite-final.xml`。

233 成员补丁的成员/组合哈希、从锁定上游应用并编译、支持矩阵及上游配置源、
配置交互矩阵均通过。当前运行树的 160 个补丁文件与正式补丁生成的内容一致
（比较时归一化 LF）。整合不修改该补丁身份。

隔离 venv（Windows / Python 3.12.7，按 CI 依赖清单安装）通过 542 项定向测试，
50 项缺少留存帧而跳过；可完整收集 8,194 项测试，`pip check` 通过。
WSL Bash 入口语法检查与 POSIX 生命周期定向回归通过 104 项；另行通过原生
observer C++ 完整行接收测试 1 项。8 个 Windows 平台跳过中，6 个由这些 WSL
用例覆盖；2 个 Windows reparse/symlink 契约仍受当前符号链接权限限制而跳过，
在 Linux 上也因 Windows 专属契约跳过，未将它们记成通过。
这些是本机验证记录，不冒充 GitHub Actions 或 Mac 实机结果。

## 保留的资格边界

- 自然满仓后的退役/强化、保留装备、原图续战到任务结束仍缺不中断连续证据。
- 日常组合自然下一轮唤醒、长期无人值守与多实例仍未资格化。
- 本机已登录 userdata 的真实发布版本升级、迁移及回退尚未资格化。
- 本机 WSL 任务结果不推广为原生 Linux、ARM64 或 Mac 的账号任务证明。
- 近期游戏和 ALAS 基线以外的运行契约兼容，不等于完整实机支持资格。

相关来源：[双端 Main](campaign-camera-refresh-20261022.zh-CN.md)、
[Redroid 连续性](redroid-continuity-20261023.zh-CN.md)、
[KVM 生命周期](kvm-local-lifecycle-20260907.zh-CN.md)、
[Mac/HVF](mac-apple-silicon-hvf-login-validation-report.md)。
