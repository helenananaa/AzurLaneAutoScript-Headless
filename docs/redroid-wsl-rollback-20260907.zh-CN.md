# 本地 WSL 镜像回滚演练

本轮新增本地镜像 A→B→A 演练入口，复用统一 WSL Redroid backend 完成游戏冷启动、
typed observer 与空登录页检查。演练不更换 Project 默认候选，不覆盖其 userdata，
也不重新复制约 57.8 GB 公共资源。

## 实现与调用

- `python/alas_headless/redroid_image_trial.py`：候选预检查、临时容器、阶段验证、
  回滚检查和原 Project 恢复。
- `scripts/wsl/manage-redroid-rollback-overlay.sh`：仅在 Redroid 数据域旁的本次
  `rollback-labs/run-*` 目录管理临时挂载与清理；root 限于挂载、受限清理，以及普通
  用户无权读取的写层大小和控制文件哈希采样。
- `scripts/python/qualify_redroid_wsl_rollback.py`：计划与执行入口。

```powershell
$env:PYTHONPATH = 'python'
python scripts/python/qualify_redroid_wsl_rollback.py `
    --config evidence/redroid-wsl-runtime-20260907-r1/runtime-config.json `
    --lock evidence/redroid-wsl-runtime-20260907-r1/runtime-lock.json `
    --candidate-image sha256:833b09b1f81d09c0d8023d3ae81841f8ecabb5510ce7047c631d36361dfa4140 `
    --output evidence/redroid-wsl-rollback-new-plan
```

不加 `--execute` 只检查现有镜像/容器身份并写计划。执行时另选新的输出目录并加
`--execute`。候选必须已经在本地 Docker 缓存中；不会拉取镜像或访问退役构建机。
计划中的动态端口由 Docker 发布后读取，始终绑定 loopback。

执行顺序：

1. 检查候选存储配置，确认 Project 处于空登录页，再停止 Project。
2. 以停止后的 Project `/data` 为只读 lower，创建基准 overlay，启动当前镜像。
3. 基准实例通过登录前检查后写入基准标记；停止实例并将基准 overlay 冻结为只读。
4. 在基准 overlay 上创建候选写层，启动候选镜像，验证基准标记仍在并写入候选标记。
5. 停止候选、卸载候选 overlay，重新启用基准 overlay，启动当前镜像。
6. 检查基准标记保留、候选标记消失。清理全部临时容器/挂载后才恢复原 Project。

这两层 overlay 用于隔离试验写入和回到试验前状态，不是新的正式 userdata 存储格式。
原 Project 仍使用已有的单一持久化 host-directory `/data`。

## 真实旧候选的阻塞

本地缓存的 `wsl-headless-trim-r1`（`f87a8ce...`）在试验中停在 Android 早期启动，
ADB 未就绪。两次失败都清理了试验挂载并恢复了原 Project。

对停止的镜像检查后发现，它和 `wsl-five-locale-font-r1`（`1f1d6a6...`）的
`/vendor/etc/fstab.redroid` 都仍要求 `/dev/block/alas_metadata`、
`/dev/block/alas_userdata` 和 `fileencryption=...`。当前镜像没有这份旧 fstab。
这些镜像属于已退役的 block/FBE 存储路线，不能因为同为 API 34/x86_64 或
fingerprint 相同就当作当前 host-directory 模式的可用回退版本。

新增检查只在镜像试验入口读取这一个小文件：创建不启动、无 userdata 绑定的
临时检查容器，复制配置后立即移除。它在停止 Project 前拒绝上述明确不兼容的
候选；普通注释和文件不存在不被误判。这项检查约数秒，避免再次中断 Project
并等待一次不可能成功的启动。没有恢复旧 FBE，也没有用空文件掩盖旧 fstab。

检查收据：`evidence/redroid-wsl-rollback-20260907-r1/retired-storage-preflight/manifest.json`。

## 受控候选的性质

受控候选 `833b09b...` 从当前 `2e6e03e...` 镜像的停止容器派生，只增加
`/system/etc/alas-rollback-fixture.txt` 和 `qualification-fixture=rollback-only` 标签。
没有启动 Android、挂载 userdata、复制游戏/账号数据或改变 Project 的默认镜像标签。
它复用已有镜像层，只增加一个很小的文件层；身份见
`evidence/redroid-wsl-rollback-20260907-r1/fixture/identity.json`。

镜像层和 userdata 使用两组独立标记：前者证明真的切换并返回了镜像内容，后者
证明候选新增的数据不会残留在回滚后的基准写层中。受控候选的成功只能验证这套
替换/回滚机制，不能证明真实版本升级、降级、数据迁移或 ALAS 任务兼容性。

## 验证边界

离线相关回归为 **121 passed、2 skipped**，包含试验阶段失败后的清理/恢复顺序、
挂载仍忙时不重启 Project、临时容器所有权、动态 ADB 绑定、路径边界，以及旧 FBE
配置拒绝和无害注释兼容。没有修改 ALAS patch series 或任务支持台账。

真实版本回退、登录后的 ALAS 工作负载、长时间 soak、多实例与原生 Linux 仍需
各自证据。

## 最终实机结果

`evidence/redroid-wsl-rollback-20260907-r1/fixture-run-1/manifest.json` 为通过收据，
`verification.json` 对阶段结果、当前实现哈希和最终设备/清理状态再次核对。
执行期间实现文件没有改变。

| 阶段 | 到空登录页耗时 | 写层采样 | 镜像诊断文件 |
|---|---:|---:|---|
| 当前镜像 + 基准写层 | 46.063 秒 | 24,532 KiB | 不存在 |
| 受控候选 + 候选写层 | 44.485 秒 | 25,268 KiB | 存在 |
| 当前镜像 + 恢复的基准写层 | 50.360 秒 | 24,788 KiB | 不存在 |

三阶段都有新鲜递增的语义帧，并以唯一空输入、disabled 下一步和 `Accounts: 0`
到达原生手机号页。回滚后基准 userdata 标记仍存在，候选 userdata 标记不存在。
停止后的原始数据目录中，packages.xml、settings_secure.xml 与资源 version.txt
在整个试验前后的哈希相同；这是抽查文件未变化的证据，不冒充全盘逐字节复验。

临时容器、overlay 挂载、写层目录、保活进程和本次 ADB 连接均已清理。原 Project
恢复后再次通过语义帧推进与空登录页检查，资源版本仍为 `9.7.356`，`/data` 为
`0771 system:system`。受控候选的小型镜像层和构造用诊断文件保留供复验，默认
Project 镜像仍是 `2e6e03e...`。

本轮完成的是**真实容器上的受控镜像/写层回滚演练**。没有可供本地 host-directory
模式直接回退的已验证历史发布镜像；已有旧 FBE 镜像仍明确不兼容，不能把受控
候选的 PASS 转换成它们的支持声明。
