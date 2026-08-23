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
- 没有 game/Android recovery、cleanup 和 runtime-lock 的仓库化 runner；
- 没有长期 soak、热状态、资源占用和休眠/唤醒证据；
- 主线尚未实现独立 `macos-hvf` lifecycle backend。

下一阶段应先通过现有 `external-adb` 边界完成 Mac 上的登录/主页面、observer
freshness、重启恢复和一个零/低 mutation ALAS 任务，再决定是否实现负责 AVD
启停、ready、recover 和 cleanup 的 `macos-hvf` backend。
