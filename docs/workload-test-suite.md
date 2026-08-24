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
