# Mac 登录前诊断与资源采样

这条开发路径无需账号登录，不注入游戏输入，也不提升 ALAS 任务支持等级。
既有 exact lifecycle/recovery 资格仍见 `mac-apple-silicon-hvf-login-validation-report.md`。

## 等待登录

Mac 后端在进程存在、前台为国服包的已审查原生
`com.gsc.phone_login.PhoneLoginActivity` 时，抛出独立的
`RuntimeAwaitingUserLogin`，错误码为 `awaiting-user-login`。它不属于
`RuntimeBackendNotReady`，调用方应提示用户完成登录，不应因此循环重启。
其他包、未知 Activity 和缺失 PID 保留原有等待/超时行为。

该分类仅用于诊断，不放宽 Unity 的前台、PID、freshness 或输入合同。
用户完成登录后用 `wait_recovered_game_ready()` 重新观察，避免再次启动游戏；
实际任务仍须通过 observer 和原有语义输入校验。资格 runner 保留未通过结果及
专门原因，并按原有规则清理 owned AVD，不将等待登录记作资格成功。

## 有界采样

在 Mac 上使用按实际 SDK、AVD 和可用端口填写的 runtime config：

```bash
python3 scripts/python/sample_macos_hvf_runtime.py \
  --config /absolute/path/runtime-config.json \
  --output /absolute/path/new-samples.jsonl \
  --duration 120 --interval 10
```

脚本检查 Mac/HVF 和 AVD，启动自己的模拟器，等待 Android，按
`-force-gfx-st` 冷启动游戏。输出文件必须是新文件，结束时停止自己的 AVD，
保留 userdata，并删除自己创建的 observer forward。运行中的同 serial 设备不会
被接管。该命令属于会启动和停止模拟器的开发采样，不是只读 attach 工具。

输出包含：

- 启动至 Unity 前台或原生登录页的耗时；这不是到 observer 或主页面的耗时。
- owned emulator 进程及其子进程的 `ps` CPU 和 RSS 合计。
- 宿主物理内存、swap 已用量、带实际 page size 的 VM counters。
- Unity 前台时的 observer request 耗时、generation、age、PID 和原子帧标记。
- 原生登录页时明确记录等待登录，省略 Unity observer 请求。

`ps` CPU 是系统提供的 CPU 使用指标，100% 约对应一个逻辑核，不能当作精确
固定区间 CPU 差分。RSS 合计可能重复计算共享页；宿主 swap 和 VM counters
包含其他应用，不归因给模拟器。采样失败记为 null 和局部错误，不伪造零值，
不阻断游戏运行。observer 字段是诊断值，不表示已通过完整 action admission。
日志不记录登录字段、账号内容、UI 文本或像素。

先保留默认 30 Hz；如比较 15/30 Hz，应分别使用配置副本和独立输出，比较相同
typed 场景，排除启动阶段并检查 generation 和 age。不能把登录前的测量结果
推广为战斗性能。快照、休眠恢复、多实例和长时间稳定性均不是本次采样的证明范围。

## 2026-09-07 开发采样

真实 ARM64 Mac / 16 GiB / 保留的 `alas_api32_arm64` AVD，30 Hz 冷启动：

- Android 启动至 Unity 前台共 21.43 秒，随后采样 120 秒，共 13 次。
- 前两次 observer 不可用，之后 11 次返回同 PID 1897、原子帧、匹配 identity；
  generation 从 12 推进到 1006，age 为 3～88 ms。
- 后 11 次进程树 CPU 为 62.0%～91.9%，RSS 合计约 5.58～5.63 GiB；
  启动初期 CPU 曾到 553%，不能混入稳态范围。宿主 swap 已用量均为 0。
- 最终 cleanup 记录成功；另行 ADB readback 确認 device 和 forward 均为空。
- 未出现原生登录 Activity，等待登录分类及等待 observer 中途切换的清理行为
  通过离线测试覆盖，本次不宣称该分支实机通过。

原始 JSONL 为本地 `artifacts/mac-prelogin-dev/samples-30hz.jsonl`，Mac 侧为
`~/alas-headless/artifacts/mac-prelogin-dev-20260907/samples-30hz.jsonl`。
Mac 侧同目录保留采样代码，上传包为旁边的 `mac-prelogin-dev-20260907.tar.gz`。
采样后的本地修订补充 locale 固定和 observer 等待期间的登录分类，未重跑不相关
的生命周期资格；旧 qualification 证据未重写。保留默认 30 Hz，未宣称降频收益。
