# AzurLaneAutoScript Headless

**English** | [简体中文](README.md)

Remove rendering overhead and run ALAS on a much broader range of devices.

AzurLaneAutoScript Headless runs the Azur Lane Unity client with ANGLE's NULL
renderer, skipping real image generation and its GPU, video-memory, and frame
transport costs. It reads typed Unity UI state directly and exposes it to a
pinned ALAS runtime. This changes both how automation observes the game and
where it can run, including devices without a hardware GPU, without KVM, or
with limited resources.

Every observation and input is explicitly mapped. Unknown, ambiguous, stale,
or unreviewed state fails closed instead of silently falling back to pixels.

> **Project status:** research-grade and usable for qualified task paths. This
> is not yet a turnkey replacement for a normal ALAS installation or a claim of
> complete unattended task coverage.

[Task support](docs/alas-config-support-matrix.md) ·
[Runtime support](docs/runtime-support-matrix.md) ·
[Architecture](docs/architecture.md) ·
[Latest validation](docs/status.md) ·
[ALAS integration](integration/alas/README.md)

## Two core goals

This repository solves two connected problems.

### 1. Stop rendering and recognizing frames

Traditional game automation renders every frame, captures and transports it,
then acts through OCR, template matching, and remembered coordinates. That
pipeline consumes GPU time, video memory, memory bandwidth, and CPU, and may
mistake a similar, covered, or partially loaded screen for the intended state.

This project reads structured UI state directly from Unity:

- skip real image rendering through a pinned ANGLE NULL-only driver;
- observe Buttons, Text, Images, Toggles, and layout directly from Unity;
- preserve upstream ALAS task state machines instead of replacing them;
- admit only context-bound, reviewed actions with fresh postconditions;
- reject unknown state without screenshot, OCR, or raw-coordinate fallback.

### 2. Bring ALAS to more devices

Once the device no longer has to continuously produce visible frames, the
runtime can target a much wider hardware range than a conventional emulator:

- x86_64 Linux servers and Android Emulator with KVM;
- cloud hosts without nested virtualization through Redroid;
- constrained environments where QEMU TCG is the available fallback;
- ARM64 Linux, rooted Android devices, and guests hosted by ordinary ARM
  devices;
- an ARM64 Emulator accelerated by Hypervisor.Framework on Apple Silicon Mac;
- explicitly identified devices whose lifecycle is owned outside this project
  and attached through external ADB.

This does not mean every combination has reached the same level of production
ALAS support. Broad device reach is a core project track, so runtime, observer,
game, recovery, and ALAS workload evidence are recorded separately for every
platform instead of being collapsed into a single supported/unsupported label.

## What works today

The current pinned configuration surface contains 60 ALAS panels. Support is
tracked per panel and per configuration branch rather than inferred from a
single successful run.

| Level | Panels | Meaning |
|---|---:|---|
| Fully qualified (`F`) | 9 / 60 | Required configuration values and necessary exception paths are closed for the qualified environment. |
| Live main path (`L`) | 26 / 60 | At least one real-device main path is closed; not every configuration value is qualified. |
| Offline only (`O`) | 6 / 60 | Contract, replay, or stub evidence exists without a live task closure. |
| Partial (`P`) | 10 / 60 | Some task behavior is implemented or reachable, but important branches remain open. |
| At a known boundary (`B`) | 8 / 60 | Work safely reaches an account, resource, date, or observation boundary. |
| Missing (`M`) | 1 / 60 | A task-level semantic adaptation is still missing. |

Representative qualified work includes:

- normal and event campaign paths through original ALAS routing;
- reward, commission, restart, research, dorm, tactical, and construction
  task paths with bounded live evidence;
- multiple Operation Siren navigation, farming, shop, archive, and boss paths;
- typed campaign map, fleet, enemy, resource, popup, and result observations;
- default-closed action budgets, exact target checks, and postcondition proofs;
- deterministic replay, pinned patch-series verification, and failure tests.

These examples do not imply that every task, server, account state, campaign
layout, or configuration combination is supported. The authoritative details
and remaining gaps are in the
[configuration support matrix](docs/alas-config-support-matrix.md). The latest
evidence receipts and regressions are recorded in
[validation status](docs/status.md).

## How it works

The runtime keeps observation, decision ownership, and input separate:

```text
Pinned Azur Lane Unity client
        |
        v
ANGLE NULL renderer + in-process semantic observer
        |
        | typed, generation-bound UI snapshots
        v
Fail-closed ALAS adapter
        |
        | reviewed presence checks and bounded actions
        v
Original ALAS task state machines
```

The semantic observer reads Unity objects on the Unity main thread and exposes
typed local snapshots. The adapter translates only reviewed ALAS resources and
actions. Before dispatch, it can require the expected page context, active and
interactable state, exact geometry, top EventSystem raycast ownership, a fresh
generation, an explicit input budget, and a verifiable postcondition.

ALAS remains responsible for task selection, retries, filtering, scheduling,
navigation logic, and recovery. The adapter supplies a constrained observation
and input boundary; it is not a second automation engine.

See [architecture](docs/architecture.md) for component boundaries and
[acceptance gates](docs/acceptance-gates.md) for the evidence model.

## Safety model

Headless mode is deliberately fail-closed:

- no automatic fallback to screenshots, OCR, template matching, or old asset
  rectangles while a semantic session is active;
- no generic click, swipe, drag, or confirmation path without an explicit
  reviewed mapping;
- live execution uses resource budgets appropriate to the requested task;
  closed-by-default qualification experiments do not impose zero input on every task;
- stale, incomplete, incoherent, covered, or ambiguous UI state is rejected;
- fully qualified support is scoped to exact game, runtime, ALAS, and evidence
  identities; runtime compatibility is attempted through capability and semantic contracts;
- fail-closed behavior is being narrowed to the affected capability or task, retaining exact
  package, foreground/PID, freshness, and input-target checks;
- a successful offline replay does not promote a path to live support.

Review the support matrix and configure the requested task's resource budget
before a live run. Revision drift alone does not make the adapter unusable,
and passing current runtime contracts does not establish fully qualified
support. See the [ALAS robustness audit](docs/alas-robustness-audit-20261002.zh-CN.md)
for the reviewed restrictions and remaining work.

## Start here

Choose the path that matches what you want to validate.

### Inspect the controller and contracts

The Python controller tests do not require a game installation or an ALAS
checkout:

```powershell
$env:PYTHONPATH = 'python'
python -m unittest discover -s tests -p 'test_*.py'
```

### Build the ANGLE NULL runtime

ANGLE must be built on Linux. On Windows, the supported development path uses
WSL2. The scripts bootstrap the pinned checkout, apply the reviewed patches,
and build the base and observer driver APKs:

```bash
cd /mnt/h/program/AzurLaneAutoScript-Headless
./scripts/wsl/bootstrap-angle.sh
./scripts/wsl/apply-angle-patches.sh
./scripts/wsl/build-angle-null.sh
./scripts/wsl/build-gles-contract.sh
./scripts/wsl/apply-angle-g3-patches.sh
./scripts/wsl/build-angle-null-observer.sh
```

These commands build the runtime foundation. They do not install or route a
game package and do not start an ALAS workload.

### Validate the Unity observer contract

The contract project is locked to Unity `2022.3.62f3`. Build the Android player
with that editor:

```powershell
Unity.exe -batchmode -quit `
  -projectPath H:\program\AzurLaneAutoScript-Headless\unity\HeadlessContract `
  -executeMethod Alas.Headless.Contract.Editor.BuildAndroidPlayer.Build `
  -logFile -
```

The default output is an x86_64 IL2CPP APK at
`unity/HeadlessContract/Build/HeadlessContract.apk`. Then run the observer
contract against a prepared Android guest:

```powershell
.\scripts\windows\run-g3-observer.ps1 `
  -Serial emulator-5570 `
  -AngleApk <observer-AngleLibraries.apk> `
  -UnityApk .\unity\HeadlessContract\Build\HeadlessContract.apk
```

Device serials and artifact paths are environment-specific examples. Do not
copy them into an unrelated emulator setup without checking the runtime lock.

### Integrate the pinned ALAS checkout

The staged integration targets upstream ALAS commit
`81ccf63b4540f00241628c82a58c02c7a2bb11af`. It is an ordered, hash-checked
patch series and is opt-in; default ALAS behavior is unchanged until the
integration is explicitly applied and enabled.

Follow the [ALAS integration guide](integration/alas/README.md) to build and
verify the patch series. Task-specific live runners are qualification tools,
not a universal launcher. Each runner has its own fingerprint, configuration,
input-budget, and recovery requirements.

## Runtime support

Removing the hardware-GPU requirement has opened several validated paths across
servers, containers, software virtualization, and physical devices. Every cell
below is evidence-scoped: booting Android, passing ANGLE NULL, reaching the game
login boundary, and running a long-lived ALAS workload are four different
claims.

| Host and Android path | Current status | Validated scope | Main boundary |
|---|---|---|---|
| x86_64 Linux + KVM / Android Emulator | **Mainline executable; most mature** | API 32 x86_64, ANGLE NULL, Unity, observer, game and Android recovery; current ALAS tasks have separate live evidence | Long soak, capacity, and multi-instance density remain open |
| External ADB | **Mainline executable** | Attaches to an exact device and enforces identity, lifecycle, and recovery contracts | Does not own provisioning, root, upgrades, or persistence |
| x86_64 Linux + Redroid | **Real-host exploration** | Binder, containers, ANGLE NULL, observer, complete resources, restart persistence, and the login screen without `/dev/kvm` | Mainline backend, current OCI rollback, and ALAS workload are not closed |
| ARM64 Linux + Redroid | **Strong platform/update exploration** | Dual-ABI artifacts, G1/G2/G3, APK/resource updates, restart, persistence, and real OCI rollback | No real game or ALAS evidence; backend remains plan-only |
| x86_64 QEMU TCG | **Partial; fallback** | Q1/Q2/Q3, long Unity run, observer freshness, and game privacy boundary | WebView black screen and System UI ANR block deeper game qualification; slower than KVM |
| Rooted ARM64 Android device | **Real tooling exploration** | Systemless ANGLE install, verify, remove, and rollback; G1 NULL-renderer contract | Current game, full observer, ALAS, thermal behavior, and long runs are unverified |
| Unrooted ARM64 phone/tablet as QEMU host | **Experimental partial pass** | Hosts an ARM64 guest under ordinary app permissions; ANGLE NULL, Unity, and no-input pre-login game boundary | No acceleration and very slow; no observer, ALAS, or recovery closure |
| Unrooted device routing the release game directly | **Currently unsupported** | A debug/queryable GLES probe can load debug ANGLE | A locked user build cannot route side-loaded debug ANGLE into the release game |
| Apple Silicon Mac + Android Emulator/HVF | **Engineering baseline: dedicated backend, lifecycle, and both recovery gates passed** | M1, API 32 ARM64, Hypervisor.Framework, and an exact runtime lock; owned-AVD lifecycle, game recovery, Android reboot recovery, and cleanup passed on the real host | Account login, main page, ALAS workload, soak, snapshot restore, and multi-instance qualification remain open |
| Intel Mac + Android Emulator/HVF | **Future candidate** | Same-architecture x86/x86_64 guest path is feasible | No repository-owned Intel Mac lifecycle or game evidence |

The table describes a cross-device program instead of hiding maturity
differences behind a vague "cross-platform" label. x86_64 KVM is the first
formal support candidate, but Redroid, TCG, ARM64, and physical-device work are
not side quests: together they test how far ALAS can move once real rendering
is removed from the runtime contract.

See the [runtime support matrix](docs/runtime-support-matrix.md) for exact host,
ABI, Android, backend, recovery, and open-blocker boundaries. Reproducible image
construction and rollback are documented separately in the
[Android image foundation runbook](docs/android-image-foundation-runbook.zh-CN.md).
The real-host result is recorded in the
[Apple Silicon Mac / HVF login validation report](docs/mac-apple-silicon-hvf-login-validation-report.md).

## Repository map

- `python/alas_headless` — fail-closed controller and semantic adapter library.
- `integration/alas` — commit-pinned upstream ALAS integration patch series,
  profiles, manifests, and qualification evidence.
- `patches/angle` — base ANGLE NULL-renderer compatibility patches.
- `patches/angle-g3` and `overlays/angle-g3` — semantic observer patches and
  sources.
- `probes/gles-contract` — Android GLES contract workload.
- `unity/HeadlessContract` — pinned Unity IL2CPP observer contract project.
- `scripts/wsl` — ANGLE bootstrap, patch, and build scripts.
- `scripts/windows` — Android execution, capture, and comparison scripts.
- `scripts/python` — replay, verification, evidence, and bounded live runners.
- `tests` — controller, adapter, patch-series, contract, and regression tests.
- `docs` — architecture, support matrices, runbooks, and validation reports.

Generated APKs, Android images, extracted game files, account data, raw
captures, and Unity/Gradle build state stay in ignored local paths such as
`artifacts`, `evidence`, `Build`, and `Library`. Durable repository evidence is
stored as compact receipts, manifests, hashes, and reports rather than large
binaries.

## Documentation

- [Configuration support matrix](docs/alas-config-support-matrix.md) — the
  authoritative 60-panel support and open-branch ledger.
- [Runtime support matrix](docs/runtime-support-matrix.md) — supported and
  experimental host, ABI, Android, and backend combinations.
- [Apple Silicon Mac / HVF login validation](docs/mac-apple-silicon-hvf-login-validation-report.md) — real-host ARM64 Emulator, ANGLE NULL, game login, and typed-observer evidence.
- [Architecture](docs/architecture.md) — observer, adapter, controller, and
  fail-closed boundaries.
- [Validation status](docs/status.md) — chronological evidence-scoped results.
- [Runtime foundation](docs/runtime-foundation.md) — lifecycle, artifact lock,
  trace, recovery, and cleanup contracts.
- [Top-down ALAS roadmap](docs/alas-topdown-roadmap.md) — task ordering and
  completion criteria.
- [ALAS integration guide](integration/alas/README.md) — pinned patch-series
  construction and integration details.

## License and third-party boundaries

Except where a file or directory carries a different notice, this project is
licensed under GNU GPL v3.0 only (`GPL-3.0-only`); see [LICENSE](LICENSE). The
pinned ALAS integration patch is GPL-covered. ANGLE patches and overlay sources
retain ANGLE's BSD-style license. Attribution and distribution boundaries are
recorded in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

The repository intentionally excludes built APKs, Android images, game
packages and resources, account data, and local evidence captures. Publishing
this source does not authorize redistribution of those outputs. Binary releases
require a separate provenance, notice, corresponding-source, and privacy
review.

This is an unofficial research project and is not affiliated with or endorsed
by the Azur Lane rights holders, ALAS maintainers, Google/ANGLE, or Unity.
