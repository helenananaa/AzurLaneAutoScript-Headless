# Apple Silicon Mac / HVF 登录页验证报告

本报告记录 2026-08-20 在真实 Apple Silicon MacBook Air 上完成的 Android
Emulator / Hypervisor.Framework 资格结果，并在 2026-08-23 通过局域网 SSH 对保留
证据进行了只读复核。

结论按证据范围表述：**Apple Silicon Mac + Android Emulator/HVF 已运行 API 32
ARM64 guest、ANGLE NULL observer 和国服 9.7.10 ARM64 游戏，并到达类型化
`LoginUI2` 登录页。** 这不是账号登录成功、ALAS 任务运行、recovery 或长期 soak
证明。

## 宿主与 guest

- 宿主：Apple Silicon MacBook Air，`arm64`；
- macOS：26.6.2（25G83）；
- Android Emulator：37.1.11.0（build 15917651）；
- 加速：`emulator -accel-check` 返回 `Hypervisor.Framework OS X Version 26.6`；
- AVD：`alas_api32_arm64`；
- guest：Android API 32 Google APIs，`arm64-v8a`；
- 资源：4 vCPU、3072 MiB RAM、40 GiB data partition；
- 启动：`-no-window -no-audio -no-boot-anim -accel on`；
- AVD 图形设置：SwiftShader；游戏 GLES 通过单独的 ANGLE NULL 路由。

保留的 `emu-launch-params.txt` 明确记录 `-accel on`，因此这条路径属于
Apple Silicon 同架构 ARM64 guest 的 HVF 加速路径，不是 Linux KVM，也不是纯
TCG 结果。

## 游戏与 observer 结果

- 包名：`com.bilibili.azurlane`；
- 游戏版本：`versionCode=9710`、`versionName=9.7.10`；
- 主 ABI：`arm64-v8a`；
- 前台 Activity：`com.manjuu.azurlane.MainActivity`；
- ANGLE 路由目标：`com.bilibili.azurlane`；
- 游戏进程：保留快照中的 PID 7547；
- observer protocol：`alas-headless.observer/v1`；
- observer 状态：`ok`；
- driver revision：`be80ce591a481c12d60c50d6040d40c035b40a2b`；
- 快照：1280×720，generation 1421，`age_ms=52`，Unity 主线程读取；
- 原始 observer 快照记录 109 个 Button；筛选后的活动 Button 切片有 11 个，
  `truncated=false`、`error_count=0`；
- UI 切片记录 5 个 Text 和 25 个 Image，均未截断且无错误；
- 登录页身份：`LoginUI2(Clone)`；
- 已读到的精确路径包括 `current_server`、`Licence_btn`、`private_btn`、
  `repair_button`、`opBtn` 和登录页根节点。

保留摘要直接记录：

```text
pid=7547
login=LoginUI2
```

这证明的不只是屏幕上出现了登录画面：Unity observer 同时识别到了登录页根节点、
控件路径、文本/图片切片和新鲜 generation。

## 保留证据与哈希

原始证据保留在局域网 Mac 的 `~/alas-headless/evidence/`；游戏资源、账号数据和
原始大文件不进入 Git。本报告记录用于复核身份的 SHA-256：

| 文件 | SHA-256 |
|---|---|
| `mac-login-20260820/summary.txt` | `6edbf131cbd4ff38dd239a3d3ba3d6b6913b075a65311c8560f106113a115ec4` |
| `mac-login-20260820/package.txt` | `916e4ba732a097cbf8f6cf5c8909a00003d2dddc7ca0a83a636b7e46f8653947` |
| `mac-login-20260820/activity.txt` | `a1bd36bf7f7234175e35f52e53cd5590b2710665d865c3995a913b8d29b23a46` |
| `mac-login-20260820/angle-route.txt` | `8c93d2e7b2b3fc1dec26b0140c5f1d85f0f539c54109f1ea2fb5f91ca1107ccd` |
| `mac-login-20260820/snapshot.json` | `6d0c2e52d0c7e2a7c84389a3361e96ef8784a888c5aa9128b8d899f284620401` |
| `mac-login-20260820/buttons.json` | `37316db48bf0f0afb407fcceb6ca270caad2f604627242d9c76c0d9b6c334107` |
| `mac-login-20260820/ui.json` | `c7c9c1cbbd1e1d34340af7768e8158f4cef45945462b5e43adb4d3013d68f120` |
| `mac-g4-login/after-agree-seed.png` | `55fdd247d241e543c97a820f0edae875f664844dc9ade2e1e3a67a5a7daf1f05` |
| `mac-g4-login/screen-12.png` | `206759da7584d44a36e948f5e80f42597f121c3536ccbe235683b3a030e4751a` |
| `AngleLibraries-observer-arm64.apk` | `8670115d326ddc39ccc5ae2cd36352e7377c3c23f8360aa358649ec959e40ccb` |
| `azurlane-cn-9.7.10-base.apk` | `e6d3ef4baac2509cc97a289b91bfd5f9d0dcd7ad8994880a192298983208699f` |

## 当前边界与下一步

本次结果可以把 `Apple Silicon Mac + Android Emulator` 从“后续候选”提升为
“真实探索：G4 登录页与 typed observer 已通过”。仍不能写成完整支持，原因是：

- 没有账号登录和主页面闭环；
- 没有当前 ALAS task workload；
- 没有长期 soak、热状态、资源占用和休眠/唤醒证据；
- 没有快照恢复或多实例资格。

独立 `macos-hvf` backend、exact runtime lock、重启恢复与 cleanup 已在后续
2026-09-07 资格中通过。下一阶段是在用户设备侧完成账号登录后，验证主页面和一个
零/低 mutation ALAS 任务。

仓库中的 guest 只读 preflight 可先发现唯一正在运行的 ARM64 Emulator，并生成
绑定该 serial 的 `external-adb` 候选配置。它不启动 AVD、不修改 guest/ANGLE
路由、不启动游戏，也不创建 observer forward；和任何 ADB inventory 命令一样，
当本机 ADB server 尚未运行时，它可能启动这个 host-local server：

```bash
PYTHONPATH=python python3 scripts/python/preflight_macos_hvf_external_adb.py \
  --avd-name alas_api32_arm64 \
  --output /tmp/alas-macos-hvf-preflight.json
```

只有 host、HVF、AVD、唯一 ADB transport、API/ABI 与游戏包身份全部通过时，输出
中的 `runtime_config` 才非空。示例字段见
`integration/runtime/external-adb.macos-hvf.example.json`；实机运行时必须使用
preflight 发现的 serial 和工具路径，不能直接假定示例端口。

独立生命周期后端的计划输入见
`integration/runtime/macos-hvf.config.example.json` 和
`integration/runtime/runtime-lock.macos-hvf.example.json`。两者只用于生成计划；
示例哈希不得用于实机 qualification。实机执行前必须从当前 Mac/AVD、ANGLE APK
和集成产物生成 exact runtime lock。

游戏按必需的 `-force-gfx-st` 冷启动后，可用一次性诊断入口读取原子 typed frame；
该入口只创建一个 PID 绑定的临时 ADB forward，并在退出时删除：

```bash
PYTHONPATH=python python3 scripts/python/probe_macos_hvf_observer.py \
  --serial emulator-5554 \
  --adb "$HOME/Library/Android/sdk/platform-tools/adb"
```

如 typed state 命中仓库已审查的国服更新下载弹窗，可用
`accept_macos_hvf_login_update.py --allow-update-download` 给出一次性下载确认；脚本
复用 `SemanticOracle` 的精确文案、唯一按钮、bounds、前台 Activity、PID 与新鲜帧
门，不新增坐标回退。该开关只授权一次普通资源更新确认，不授权购买、账号或数据
清除操作。

## 2026-09-06 开发复验

本轮在同一台 Apple Silicon Mac 上完成了新的开发级复验，但尚未生成 exact runtime
lock，因此不提升正式支持状态：

- mDNS SSH、`darwin/arm64`、macOS 26.6.2、HVF、`alas_api32_arm64`、API 32
  ARM64 guest 与唯一 `emulator-5554` 均通过新 preflight；
- 仓库新增独立 `macos-hvf` backend，负责 owned AVD 的 start、ready、game/Android
  recovery、observer cleanup 和 stop；不宣称快照恢复、多实例或 host metrics；
- 游戏按 `-force-gfx-st` 冷启动后，原子 observer 返回 `status=ok`、主线程、新鲜
  generation、正确 package/PID 与固定 ANGLE revision；
- 首次版本检查因当时代理节点无法访问目标 HTTPS 而出现 typed 网络弹窗。恢复可用
  TUN 节点后，复用既有 `SemanticOracle` 更新合同，以一次输入确认 638.4 MB 普通
  资源更新；336 个文件完成、失败为 0；
- 更新完成后的旧 Unity 帧变陈旧，按冷启动合同恢复到新 PID；随后 observer 恢复至
  亚百毫秒 age 并自然进入同包 `com.gsc.phone_login.PhoneLoginActivity`；
- Native Activity 可访问性诊断发现非空手机号字段、禁用的“下一步”和独立账号登录
  入口。本轮未读取字段内容、未点击账号入口、未提交凭据，因此仍没有主页面或 ALAS
  workload 证据。

这次复验关闭了 Mac/HVF 的 host、AVD、启动、ANGLE NULL、更新与 game recovery
开发路径；正式 qualification 仍需 exact runtime lock、backend runner 的完整
start-to-cleanup 收据，以及用户在设备侧完成账号登录后的主页面和零输入 workload。

## 2026-09-07 exact lifecycle/recovery 资格

本轮以实现提交 `67ec146c2e5ea3b4b97b2126d0615697b84d43d3` 生成 account-free
identity、provision profile、空资源声明与 exact runtime lock。runtime lock SHA-256
为 `0728bb29bd2ef8dd2c2f29255e43266f3891100fb08561ccfe1b1e315549f6f6`，其中：

- system image：`8428c469f6e3a6056f68ad2fd175e61a70ca6e6cffa58ee0b444a6616a39d26f`；
- provision profile：`e1447acd880e96105534f69ae210d81b3f4b9e3acbf40e794e1f662214f88340`；
- ANGLE APK：`8670115d326ddc39ccc5ae2cd36352e7377c3c23f8360aa358649ec959e40ccb`；
- game base APK：`e6d3ef4baac2509cc97a289b91bfd5f9d0dcd7ad8994880a192298983208699f`；
- `libil2cpp.so`：`0359952f19c449e7a0fcef8a3164fb1cb1dc23d5fd8ef33d17cde72367e9267f`。

三条独立 runner 结果：

| Gate | Phases | PID 证据 | Trace | Cleanup |
|---|---:|---|---|---|
| lifecycle | 10/10 pass | baseline observer 已绑定 | 32 records，0 dropped/invalid | device 0，forward 0 |
| game recovery | 14/14 pass | `1692 -> 4381` | 49 records，0 dropped/invalid | device 0，forward 0 |
| Android recovery | 17/17 pass | `1743 -> 1721`，含 ADB offline | 62 records，0 dropped/invalid | device 0，forward 0 |

三个 manifest 的 observed fingerprint 均与 exact lock 一致，且
`cleanup_failure_code=null`。本机索引拒绝项为 0。原始 manifest、trace、identity、
lock 与索引保留在本地 `evidence/runtime/macos-hvf/qualification-20260907/`，Mac 侧
保留同名 evidence 根目录。

这使 Apple Silicon Mac/HVF 达到工程生命周期基线，但仍不是登录后 ALAS 或生产
资格。未读取或提交账号信息，resource manifest 的共享路径为空；账号登录、主页面、
代表性 workload、soak、快照恢复和多实例仍保持未验证。
