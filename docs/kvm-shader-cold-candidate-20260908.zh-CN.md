# 按需 shader 候选：真实冷启动与回退结果

已增量构建并发布独立候选
`kvm-r75-x86_64-shader-ondemand-20260908-r1`，通过两次冷启动、游戏语义就绪和
原镜像回退。**未证实稳定的整体提速，默认仍保留原镜像**；候选产物保留供继续
测量。没有登录账号、重置 userdata 或执行 ALAS 任务。

## 实现与构建

候选只在 KVM 产品的 `PRODUCT_SYSTEM_PROPERTIES` 中增加
`service.sf.prime_shader_cache=false`。属性随 system 镜像在启动时加载，
不是 ADB 启动后注入，也没有放宽 SELinux。

原补丁和默认 profile 保留不动，独立补丁、锁定文件和 profile 位于
`integration/runtime/kvm-shader-candidate-20260908/`。原 source-lock 校验器
把补丁文件名固定为基线路径，本次允许 `integration/runtime` 内独立的相对
`.patch` 路径，继续拒绝越界路径并保留 project、摘要、消息和完整源码树验证。
内容摘要不匹配的补丁仍由构建校验拒绝。

构建前核对 KVM/Redroid 挂载 UUID、manifest、1355 项库存、原同步收据及所有权。
WSL 约 56 GiB 内存可用、KVM 盘约 712 GiB 空闲、Windows E 盘约 2.3 TB 空闲。
沿用 KVM 独立源码/输出，以非 root 构建用户 J32 增量运行，构建耗时 2 分 52 秒；
未清理输出或重新同步。发布使用既有摘要与复制一致性校验，保留原 release。
构建产物中的属性及实际 guest getprop 均已核实为 false。

保留源码和输出现在对应候选锁，继续构建时须用候选 source-lock/profile；
默认 runtime 仍可使用原 release，两者不能混作同一构建身份。

## 冷启动结果

四次均从模拟器停止开始，使用同一 r5 AVD 和原游戏资源；构建/发布结束后才
采集性能数据。每次都使用原 backend 的 Unity 冷启动契约及完整就绪检查。

| 指标（秒） | 原镜像 | 候选首次 | 候选再次 | 回退原镜像 |
| --- | ---: | ---: | ---: | ---: |
| Windows 整个 Start 入口 | 83.44 | 92.56 | 70.45 | 67.82 |
| ready 总耗时 | 71.84 | 80.50 | 55.67 | 57.40 |
| 等待 ADB | 22.26 | 33.32 | 22.34 | 18.16 |
| framework | 18.83 | 14.36 | 13.18 | 15.59 |
| 网络 | 3.56 | 5.09 | 4.66 | 3.63 |
| 游戏启动调用 | 3.83 | 4.43 | 3.45 | 3.32 |
| 等待游戏语义状态 | 23.36 | 23.29 | 12.03 | 16.70 |

四次结果均为 semantic-ready，随后正常 Stop 返回 0。候选首次 generation 1 /
age 682 ms，后续观察到 generation 15 / age 110 ms；候选再次 generation 1 /
age 294 ms。回退原镜像也取得新鲜语义状态。

原镜像日志生成 122 个 shader，预编译约 18.74 秒；回退后再次生成 122 个，
约 16.33 秒。候选两次都未观察到该批量预编译日志，属性来源及机制已验证。
但候选 SF 启动完成仍约 15 秒：冷启动还有框架等其他工作，不能把前一轮框架
重启实验的巨大差值外推到冷启动。

首次换入候选日志记录系统分区变化后的包缓存重建，因此补测一次同镜像冷启动。
这并不能证明首次 ADB 阶段较慢完全由缓存重建造成。候选再次的 ready 比回退
原镜像短约 1.7 秒，而 Windows 总入口反而长约 2.6 秒，当前样本不足以作稳定
提速结论。没有隐藏候选首次更慢的结果，也不把功能通过等同于性能胜出。

## 验证与收尾

- 相关 Windows 聚焦测试共 78 passed、2 skipped。
- 构建进行了补丁摘要、完整 patch tree、包策略和产物校验；发布及切换进行了
  release 摘要验证。四份启动/正常停止记录及 false 属性读回已检查并汇总。
- `Accounts: 0`，没有账号输入、购买或游戏资源消费；此轮不声称登录后任务支持。
- 已通过原切换工具回退原镜像，AVD 配置自动备份；最终正常停机，userdata 保留。
- 候选保留但不设为默认。原默认 runtime-config/profile 无需修改即可使用。
- 这不是独立第二构建、字节级可复现或多实例资格。

收据：`integration/runtime/kvm-shader-candidate-20260908/cold-receipt.json`；
原始数据：`artifacts/local-kvm/shader-cold-20260908/`；构建原始数据在 KVM 域
`evidence/kvm-shader-candidate-20260908-r1/`。候选目录 README 记录了选择与回退方式。
