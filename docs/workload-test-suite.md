# ALAS Headless workload test suite

This suite answers a narrower question than functional qualification: after a
runtime, image, VM, or container change, did the same real workload become
faster, lighter, or more stable?

The suite does not replace ALAS task state machines. Task profiles call the
original ALAS implementation, while the collector records a uniform runtime
trace around it. ANGLE NULL remains enabled; no profile captures screenshots,
starts an observer sidecar, or falls back to raw input.

## Implemented profiles

| Profile | Workload | Account effect | Normal use |
| --- | --- | --- | --- |
| `semantic-io` | Original Benchmark `screenshot_click`, `screenshot`, and `click`; one `emulator` provenance value and the original 15-sample loop per scene | Reversible settings round trip; no game resource operation | Every runtime candidate |
| `reward-readonly` | Original Reward daily and weekly branches with all five collection switches disabled | No mutation dispatch | Every runtime candidate |
| `restart-warm` | One original Restart scheduler task and running-PID turnover | Restarts the game process; no game resource operation | Image or lifecycle milestone |
| `idle-soak` | Typed main-page check, passive wait, and typed final check | No input or account mutation | Release candidate |
| `main-12-4-official-auto` | Original Main runner enters 12-4 once and delegates map movement and combat to the game's official auto-search | One bounded ordinary sortie; no premium currency or purchase capability | Sustained Unity/image milestone, after noncombat profiles |

`semantic-io` and `idle-soak` normalize the starting surface before the timed
capture. The exact bulletin blocker, when present, is closed by original ALAS
`UI.ui_additional`, and original `Benchmark.semantic_ensure_main` restores the
main page. This preflight is recorded in workload metadata and explicitly
excluded from performance timing.

`Research.Use*=do_not_use` is deliberately absent from the zero-mutation suite.
The current original task may still start a resource-free project, which changes
account state even though coins, cubes, and parts are not consumed. A future
`ui-scan` profile needs a reviewed original-ALAS stop boundary before that final
start action.

## Run one profile

Set the exact ALAS checkout, online ADB serial, and observer driver revision.
The selected serial must match the seed configuration; the collector does not
guess from documentation examples.

```powershell
$alasRootForWorkload = 'H:\program\AzurLaneAutoScript-alas-topdown-live'
$driverForWorkload = '<40-character-driver-sha1>'
$captureRoot = 'H:\program\AzurLaneAutoScript-Headless\artifacts\workload-captures'

python scripts/python/collect_alas_noncombat_workload.py `
  --profile semantic-io `
  --alas-root $alasRootForWorkload `
  --serial emulator-5580 `
  --driver-revision $driverForWorkload `
  --output-directory "$captureRoot\semantic-io-r1"
```

For a short development soak, use 30 minutes. Longer release-candidate runs can
increase this up to two hours.

```powershell
python scripts/python/collect_alas_noncombat_workload.py `
  --profile idle-soak `
  --alas-root $alasRootForWorkload `
  --serial emulator-5580 `
  --driver-revision $driverForWorkload `
  --idle-duration-seconds 1800 `
  --output-directory "$captureRoot\idle-30m-r1"
```

The official-auto profile has a separate collector because it wraps the
bounded Main live runner and records the passive game-owned combat interval:

```powershell
python scripts/python/collect_alas_auto_combat_workload.py `
  --alas-root $alasRootForWorkload `
  --serial emulator-5580 `
  --driver-revision $driverForWorkload `
  --output-directory "$captureRoot\main-12-4-auto-r1"
```

It grants one sortie and zero post-sortie combat/viewport input. The resource
receipt records the successful sortie and reports oil as unobserved unless a
typed counter was actually captured; it never invents an oil delta.

Every output directory is new and contains:

- `result.json`: profile result, typed postconditions, device identity, and
  sampler integrity;
- `runtime-trace.jsonl`: append-only semantic/runtime trace;
- `resource-receipt.json`: the resource contract and its evidence basis;
- `baseline-summary.json`: CPU, RSS, I/O, observer latency, request rate, and
  trace-integrity summary.

During `restart-warm`, a small number of guest or observer failures is expected
while the old PID is absent and the new process is not ready. Acceptance uses
the typed login result, PID turnover, and the start/end observer-forward delta;
it does not pretend that the restart window was continuously available.

The resource receipt never invents a resource counter. If the workload has no
resource action but no oil/coin/cube counter was read, it records the counters
as unobserved and identifies the action-surface or dispatch evidence instead.

Verify copied or retained captures before comparison:

```powershell
python scripts/python/verify_alas_workload_capture.py `
  "$captureRoot\semantic-io-r1" `
  "$captureRoot\idle-30m-r1"
```

The verifier accepts both noncombat and official-auto schema families. It
requires correlated run IDs, hashes for result/trace/resource receipt, complete
trace accounting, no screenshot or observer sidecar, no raw-input fallback,
and the official-auto one-sortie/zero-combat-input contract. A retained legacy
capture that predates receipt hashing may be sealed by an additive
`verification-manifest.json`; the original four capture artifacts are not
rewritten. Use `--seal-legacy` once on an unsealed retained directory, then run
the ordinary verifier without that write switch on later checks:

```powershell
python scripts/python/verify_alas_workload_capture.py `
  --seal-legacy "$captureRoot\main-12-4-auto-legacy"
```

The retained 2026-08-24 KVM development set currently has verified successful
captures for all four noncombat profiles plus
`main-12-4-official-auto`. Failed setup/recovery attempts remain retained but
are not comparison baselines. The successful official-auto capture is the
first functional sustained-load slice; normal comparison still requires the
repetition rhythm below.

## Comparison rhythm

Use the smallest profile that can see the optimization:

1. Run `semantic-io` three times and compare the median when changing observer,
   ADB, semantic adapter, or input paths.
2. Run `restart-warm` three times when changing image startup, process lifecycle,
   package launch, or observer reconnection.
3. Run `reward-readonly` when changing ALAS navigation, task dispatch, or typed
   page mappings.
4. Run one 30-minute `idle-soak` after a candidate passes the short profiles;
   use a longer soak only at a milestone.
5. Run the official-auto battle workload last when the change can affect Unity
   sustained load.

One account should run live profiles sequentially. Builds, offline replay, and
contract tests can run in parallel across environments, but real Android/Unity
performance remains a live-client measurement. Compare the same profile,
profile version, seed state, sampling interval, and repetition rule across x86,
ARM, KVM, Redroid, and TCG results.

## Account-free battle capsule (W0)

Convert an already verified official-auto capture into a versioned,
account-free workload capsule and bind it to the offline G36 semantic combat
replay:

```powershell
$env:PYTHONPATH = 'python'
python scripts/python/compile_alas_battle_capsule.py `
  <verified-capture-directory> `
  integration/alas/g36-normal-observer-replay.json `
  <new-capsule.json>
python scripts/python/run_alas_battle_capsule.py <new-capsule.json>
```

Compilation fails closed unless the source capture verifies and the semantic
replay is passing, pixel-free, input-free, and explicitly not
production-ready. The default run mode only validates and summarizes the
schedule. Optional `--mode host-proxy` executes a time-scaled, single-process
CPU/memory/write proxy with explicit caps; it never launches Android or injects
input.

This is a W0 harness and regression workload. It preserves the shape of a real
battle trace and the calls made by the semantic combat path, but does not
reproduce Android guest scheduling, GPU/driver behavior, PSI, zram, or major
faults. It therefore cannot replace W1 live battle qualification or prove that
a 3 GiB KVM guest is sufficient.

## Original-ALAS offline battle rehearsal

At an implementation milestone, run the same capsule through a freshly patched
disposable worktree made from the clean pinned ALAS checkout:

```powershell
$env:PYTHONPATH = 'python'
python scripts/python/run_alas_battle_capsule.py `
  <verified-capsule.json> `
  --mode alas-replay `
  --alas-upstream E:\Disk0Merged\H\program\AzurLaneAutoScript-upstream-readonly `
  --output <new-offline-result.json>
```

This mode applies the canonical ALAS patch series in a temporary worktree, then
calls the original ALAS `_goto`, `combat`, `combat_preparation`,
`combat_execute`, and `combat_status` state-machine methods against the frozen
typed observer fixture. It requires the fresh replay to match the capsule's
upstream commit, task configuration, observer fixture, stage, target, phases,
virtual actions, call plan, and artifact hash. Pixel access, Android input,
changed battle/ammo post-state, or incomplete cleanup fails closed.

The defensive-preflight artifact is checked separately. Every root must be an
explicit qualified row or a qualification stop before the original grid click;
a stop after that boundary, duplicate root, stale replay binding, or inconsistent
grid-click decision is rejected. A passing result is classified only as
`W1-offline-rehearsal-only`: it uses no Android runtime or account and never
authorizes a live sortie. Live W1 still requires all defensive roots qualified,
a fresh typed preflight on the selected runtime, and an explicit one-battle
resource budget and user authorization.
