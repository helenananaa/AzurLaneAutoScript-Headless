# Repository Instructions

## Project mission

This repository runs the Azur Lane Unity client with the pinned ANGLE NULL
renderer and supplies typed Unity semantic state to a pinned ALAS revision.

The adapter exists to replace ALAS screenshot, OCR, template-matching, and
reviewed input ports in semantic mode. It is not a replacement automation
engine.

The pinned game and ALAS revisions are reproducible qualification baselines,
not blanket runtime allowlists. The product goal is to remain useful across
routine upstream ALAS and game updates whenever the required behavior can still
be identified safely.

## Architectural invariants

- Preserve the original ALAS task state machines.
- ALAS continues to own task selection, scheduling, filtering, retries,
  navigation, combat flow, recovery, timers, and success/error decisions.
- Do not create a second state machine, parallel task engine, duplicate map
  model, or adapter-owned workflow when the behavior already belongs to ALAS.
- Adapt only the necessary observation/OCR/template/input boundary to typed
  semantic state.
- Preserve ALAS screenshot timing semantics: in semantic mode a screenshot
  boundary refreshes the immutable semantic frame.
- Never manufacture a black, zero-filled, synthetic, or recoverable pixel
  array as a semantic screenshot substitute.
- Keep compatibility failures scoped to the affected capability, task, or
  branch. An unsupported optional task must not prevent unrelated supported
  tasks from running.

## Headless and screenshot rules

The primary local AVD is currently:

`H:\AndroidAVD\alas_game_api32_x64.avd`

Verify that the path still exists before using it. Do not assume an emulator
serial from documentation examples; discover and bind the exact device.

The Headless Unity runtime has a mandatory cold-start contract. Every game
launch or restart, including update and recovery restarts, must pass the Unity
extra `-force-gfx-st`; do not use a plain `am start` for this package. The
equivalent explicit ADB launch is:

```powershell
adb -s <discovered-serial> shell am start -W --es unity '-force-gfx-st' -n com.bilibili.azurlane/com.manjuu.azurlane.MainActivity
```

An observer socket existing after a plain launch is not runtime-health
evidence: without this Unity argument the socket may exist while main-thread
semantic export remains unavailable. When that symptom appears, first verify
the actual launch contract. Recover by force-stopping the exact package and
cold-starting it with the required Unity extra, then re-validate the exact
package, foreground activity/PID, fresh coherent generation, and required
typed semantic surface before continuing. Do not diagnose this condition from
the framebuffer or work around it with screenshot or coordinate input.

When the game is routed through ANGLE NULL:

- a black emulator/ADB screenshot of the game is expected;
- do not use screenshots for visual QA, navigation, state diagnosis, or task
  acceptance;
- do not disable ANGLE NULL merely to inspect the game visually unless the task
  explicitly requires a separate rendered-mode investigation;
- use typed observer state, semantic traces, generations, action receipts, and
  postconditions instead.

System UI or other non-game surfaces may have different behavior. A visible or
black framebuffer alone is not evidence that the semantic runtime is healthy
or broken.

## Fail-closed semantic boundary

- Do not fall back to screenshots, OCR pixels, template matching, old asset
  rectangles, approximate coordinates, or generic input when semantic state is
  unavailable.
- Missing, ambiguous, stale, truncated, malformed, obscured, or unsupported
  state must fail closed.
- Require the exact package, foreground activity/PID, coherent fresh
  generation, unique reviewed mapping, actionable target, blocker checks, and
  relevant postcondition before input.
- Unsupported direct pixel access must raise a classified error rather than
  silently returning false or consuming a black frame.
- Apply fail-closed behavior at the narrowest safe boundary. Unknown state in
  one task or feature should stop that task or branch, not disable the entire
  adapter when independent capabilities remain usable.

## Live-device safety

- Begin diagnosis with typed observation, but do not require a separate user
  confirmation for every input after the user has requested live adaptation,
  qualification, task execution, or an end-to-end flow.
- Treat such a request as task-scoped authority for the normal, recoverable
  game and emulator operations reasonably required to reach the requested
  outcome. This may include clicking, swiping, navigation, entering stages,
  combat, claiming ordinary task rewards, retreating, and restarting the game
  or emulator when recovery requires it.
- Use a practical bounded action/resource budget appropriate to the requested
  task and record what was consumed. Do not force the budget to zero when that
  would prevent the explicitly requested live adaptation or qualification.
- Prefer the least costly viable path, but do not stop useful progress merely
  because a normal task consumes routine in-game attempts, oil, coins, items,
  or other expected resources.
- Require separate explicit authorization for purchases, premium-currency
  spending, account binding or credential changes, destructive userdata/AVD
  reset, uninstall/reinstall that may lose state, or materially unrelated
  account-wide mutations.
- Stop repeated input when typed state does not advance. Inspect the exact
  generation, target, blocker, path, sprite, and task context before resuming.
- Confirm the target stage, task configuration, package, server/account state,
  and runtime identity before collecting live evidence.

## Upstream compatibility and graceful degradation

- Treat `integration/alas/upstream-lock.json` as the reproducible, fully
  qualified baseline. Do not use revision equality alone as a reason to reject
  an otherwise compatible installed ALAS or game version.
- Prefer capability detection, schema/protocol negotiation, semantic identity,
  structural checks, and focused smoke tests over global exact-version gates.
- When ALAS or the game changes, first attempt to keep the existing supported
  surface running. Reuse stable interfaces and tolerate additive fields,
  reordered objects, harmless metadata drift, and unrelated feature changes.
- Isolate optional and task-specific integrations. If an updated feature is not
  understood, mark only that capability unavailable and return a clear,
  localized error when the user enables it; continue serving independent
  supported tasks.
- Do not fail global startup because one resource mapping, task panel, scene,
  popup, or optional observer field changed. Establish the smallest affected
  capability set and degrade only that set.
- Do not guess through a safety-critical incompatibility. After compatible and
  bounded fallback paths are exhausted, fail the affected action explicitly
  with the observed version, missing capability, and recovery/re-entry
  condition.
- Exact versions and hashes remain mandatory for reproducible builds, patch
  application, qualification evidence, and claims of fully verified support.
  Best-effort runtime compatibility beyond the baseline must be reported as
  such rather than rejected or promoted to fully qualified support.
- When changing an ALAS patch-series member, update and verify the member hash,
  combined patch, manifest, and dependent evidence.
- Do not relax hashes, support classifications, fail-closed assertions, or
  expected evidence merely to make a verifier pass.

## Evidence and support claims

- Keep offline contract/replay evidence separate from controlled live-device
  evidence.
- A typed port, passing replay, default configuration, or one successful
  account path does not prove broad task or field support.
- Distinguish fully qualified baseline support from best-effort compatibility
  on a newer upstream version. Lack of full qualification does not by itself
  require disabling capabilities whose runtime contracts still pass.
- Treat `integration/alas/support-matrix-ledger.json` as the structured support
  authority and keep its generated documentation consistent.
- Report configuration, observation, action, recovery, offline validation, and
  live validation separately.
- Preserve known blockers and re-entry conditions instead of promoting an
  incomplete path to supported.

## Risk-based gates and development friction

Do not add a guard, gate, approval step, exact-value check, allowlist, action
budget, evidence requirement, or mandatory test merely because it appears more
strict. Strictness is not a goal by itself. The burden of proof is on the new
restriction: it must prevent a concrete, credible failure that is not already
covered at an existing boundary, and its development cost must be proportionate
to that risk.

- For every new gate, identify the concrete failure it prevents, the affected
  capability and action, why an existing boundary is insufficient, what the
  failure looks like, and the exact recovery or re-entry condition. If these
  cannot be stated clearly, do not add the gate.
- Put a justified gate at the narrowest boundary that owns the risk. Do not
  turn a task-local uncertainty, optional-field drift, or qualification gap
  into global startup rejection, unrelated capability denial, or a blanket
  zero-action policy.
- Do not use cryptography, signatures, secrets, process handshakes, exact
  hashes, or duplicate provenance wrappers where every relevant producer and
  consumer already runs with the same authority and the mechanism cannot
  defend against the stated threat. Use plain run correlation and structural
  validation when that is the real requirement.
- Do not use exact revision, source hash, template hash, harmless metadata,
  object ordering, additive fields, emulator serial examples, or historical
  evidence identity as a runtime compatibility gate unless exact identity is
  required for that specific action. Prefer capability detection, semantic or
  structural checks, explicit device discovery, and localized degradation.
- Separate the development loop from qualification and release gates. Exact
  patch hashes, regenerated evidence, exhaustive matrices, full regression,
  soak, and live qualification belong at meaningful milestones or support
  promotion—not after every ordinary implementation edit.
- A new gate must have focused coverage for both sides: the credible unsafe
  case is rejected, and a representative harmless or compatible case remains
  allowed. Do not create large combinatorial test matrices without a concrete
  decision or regression they protect.
- Prefer deleting or simplifying an existing restriction when its original
  threat is absent, duplicated, or no longer credible. Preserve useful run
  identity, observability, and classified errors without presenting them as a
  security boundary they cannot provide.
- Never weaken the genuine safety boundaries in this file to improve velocity:
  typed-only input, exact package/foreground/PID checks, fresh coherent state,
  unique actionable targets, blocker and postcondition checks, ambiguous-input
  handling, and explicit authorization for premium, credential, destructive,
  or materially unrelated account actions remain mandatory.

## Validation

Development velocity is an explicit project concern. Scale validation to the
risk and scope of the change; do not spend most of the implementation cycle on
unnecessary repeated testing.

- During active iteration, run the smallest focused test, compile check, or
  verifier that can catch regressions in the code currently being changed.
- Batch coherent edits before running broader suites. Do not rerun the full
  repository suite after every small documentation, mapping, fixture, or
  implementation change.
- Run broader regression, patch-series, and live qualification gates at useful
  milestones, before a support-status promotion, and before final handoff when
  the accumulated risk justifies them.
- Do not repeat an unchanged expensive test or live flow unless relevant code,
  inputs, runtime identity, upstream state, or prior evidence has changed, or
  the previous result was inconclusive or flaky.
- Reuse trustworthy existing fixtures and evidence for intermediate work, then
  perform targeted fresh validation for the behavior actually changed.
- Never let test breadth become a substitute for implementing the requested
  capability. Keep forward development progress visible while maintaining
  proportionate confidence.
- Always validate a changed safety-critical action boundary, destructive or
  premium-resource guard, patch/hash contract, or evidence promotion before
  relying on it.

For repository Python tests, set:

```powershell
$env:PYTHONPATH = 'python'
python -m pytest -q tests
```

Do not use bare repository-root `pytest -q`; it may collect retained upstream
or evidence trees under `artifacts`.

Run focused tests first. When changing ALAS integration or support metadata,
also run the relevant patch-series, patch-tree, support-matrix, and
configuration verifiers documented under `integration/alas` and
`scripts/python`.

Compatibility changes should include focused tests for both the pinned
baseline and representative upstream drift. Include task-isolation coverage:
one unavailable feature must not break discovery, admission, or execution of
unrelated supported tasks.

## Repository hygiene

- Inspect Git status before editing and preserve unrelated user changes.
- Treat `artifacts`, `evidence`, integration receipts, hashes, runtime locks,
  and generated matrices as provenance-bearing data.
- Do not delete, regenerate, rewrite, or promote evidence unless the requested
  task requires it and the corresponding verifier is run.
- Keep documentation claims evidence-scoped; this remains a research-grade
  runtime, not a universal drop-in ALAS replacement.
