# SurfaceFlinger 按需编译候选实验

本轮验证了 `service.sf.prime_shader_cache=false` 的运行时效果和回退，
没有修改默认入口、镜像或持久化属性。结论是值得做冷启动候选实验，尚不作为
默认配置或稳定提速承诺。

## 方法

同一 r75 release、r5 AVD、Emulator PID 565 和 Android boot ID
`fa3b2ebf-d7f9-4005-b158-73ee8742e930` 下，依次设置 true、false、true，
通过 userdebug 的 `su 0` 执行准确的属性设置和 `ctl.restart surfaceflinger`。
每次核对 AVD console 名称和设备连接，游戏先 force-stop；SurfaceFlinger 的
既有 onrestart 会重启 zygote/framework。此操作没有禁用 SELinux。

等待新 SurfaceFlinger PID 的 `Boot is finished` 日志后，再用原 KvmBackend
完成 Android/网络检查及带 `-force-gfx-st` 的游戏冷启动。实验没有游戏界面输入。

这是**框架重启**对照：内核、userdata、宿主和缓存没有重新冷启动。不能把它
当成从模拟器停止到游戏就绪的冷启动数据。最初 Android-only 启动输出仅作
准备记录，不纳入本轮对照。

## 结果

| 指标 | 开启预编译 | 关闭预编译 | 恢复开启 |
| --- | ---: | ---: | ---: |
| 框架重启至 SF 完成，宿主观测 | 36.068 秒 | 6.099 秒 | 15.266 秒 |
| SF 自报启动完成 | 35.641 秒 | 5.469 秒 | 14.753 秒 |
| shader 批量预编译 | 122 个 / 35.327 秒 | 未观察到批量预编译 | 122 个 / 14.463 秒 |
| 随后游戏 ready | 超时，observer unavailable | 17.414 秒 | 11.937 秒 |

关闭后的 SurfaceFlinger dumpsys 记录 `shaders cached since last dump/primeCache: 1`，
证明这个已观察到的页面路径只按需产生很少的 shader，不代表所有后续页面的数量。
候选游戏 PID 5432，generation 1、age 322 ms，通过现有状态检查；随后进入
原生 PhoneLoginActivity，正确报告 login-required。恢复开启后游戏 PID 7257，
generation 1、age 463 ms，同样通过语义检查。

最初开启组游戏在原有等待时限内没有得到语义状态，返回 unavailable；错误
保留，未放宽检查。游戏日志还记录 SDK 异常，但未证明它是超时原因。恢复开启
后成功，因此不能把最初失败归因于开关，也不能拿该失败计算游戏启动提速。

两次开启组自身差异很大，且关闭组的随后游戏 ready 比恢复组多约 5.5 秒。
SDK/网络、缓存及宿主调度均未受严格控制，无法据此定位这 5.5 秒的原因，也
无法保证没有首次使用代价。仅将成功的两组框架和游戏耗时相加，约为
23.5 秒与 27.2 秒；这仍不是完整冷启动或稳定收益结论。

## 收尾与后续

- 已将属性恢复 true，并观察到重新预编译及游戏语义就绪，验证了回退。
- 属性非持久化；默认启动脚本和 release 没有改动，停止虚拟机后此次设置不保留。
- `Accounts: 0`；没有账号输入、游戏任务执行或资源消费。
- 正常 Stop 返回 0，userdata 保留。
- 本轮无产品代码修改，不重复运行无关离线回归，不提升支持等级。

下一步应在独立候选中设置可靠的启动期属性，保留原 release，做真正的冷启动
及首次游戏使用对照。不能将晚到的 ADB setprop 当作冷启动配置，也不应为注入
任意 Emulator 属性而放宽 SELinux。若需镜像调整，使用保留源码增量构建即可，
不需要清理输出或全量重编。

原始记录和本轮一次性探测脚本：`artifacts/local-kvm/shader-prime-20260908/`。
脚本仅供本轮实验，不是日常启动入口。日志采集仅依赖可读的 framework 缓冲，
内核日志权限警告不影响本报告使用的 SF 事件，也不表示取得了完整 kernel trace。
