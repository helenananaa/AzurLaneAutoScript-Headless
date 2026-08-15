# ALAS semantic adapter v2 execution plan

- Status: execution draft
- Branch: `codex/alas-adapter-v2-plan`
- Baseline: `a580b2d593226fb96104eff97301515aae9f329a`
- Pinned upstream ALAS: `81ccf63b4540f00241628c82a58c02c7a2bb11af`
- Scope: controller-side ALAS semantic adaptation and its upstream integration

## 1. Decision

Continue the ALAS adaptation by stabilizing the adapter kernel before adding
more task coverage. ALAS remains the sole owner of task selection, branching,
loops, timers, retries, navigation, combat, and state mutation. Headless code
replaces only observation and final input dispatch boundaries.

The execution order is fixed:

1. freeze and characterize the current behavior;
2. split the adapter internally without changing the ALAS-facing API;
3. introduce atomic semantic frames and explicit flow scopes;
4. require capability-closure admission from one immutable run policy;
5. reduce the upstream integration to a reviewable patch series;
6. qualify G36 through the original live `_goto()` post-click state machine;
7. consider unattended promotion only after repeated runs and recovery gates.

Do not implement G36 by scripting the post-click phase sequence in a harness.
Do not broaden unknown observations into `False`, and do not fall back to the
NULL framebuffer, OCR, template rectangles, raw coordinates, or generic input.

## 2. Current baseline

The baseline is healthy as a research and qualification implementation, but it
is not an extensible production adapter yet.

- G35 qualified the natural out-of-sight camera branch. Original ALAS owned
  `_goto -> in_sight -> focus_to -> device.swipe_vector -> Camera.update` and
  reached its final `device.click(grid)` statement. The grid click remained
  intercepted with `grid_input_injected=false` and
  `production_enabled=false`.
- The current suite passed `432/432` during the design audit.
- The canonical integration patch applies to the pinned upstream ALAS tree.
- `python/alas_headless/alas_adapter.py` is approximately 5,500 lines and
  exposes approximately 268 methods.
- `python/alas_headless/semantic_oracle.py` is approximately 7,900 lines.
- `integration/alas/0001-semantic-oracle-hooks.patch` is approximately 1,700
  lines and touches 24 upstream files.
- Semantic configuration currently has roughly 39 distinct
  `ALAS_SEMANTIC_*` environment references.
- Combat evidence coverage remains canonical `16/41`, defensive `18/54`,
  actions `12/38`, and blockers `1/4`; `production_ready=false`.
- Runtime lifecycle abstractions now exist separately for KVM, external ADB,
  and deferred backends, but `AlasSemanticSession` still constructs an
  `AdbObserverBridge` directly.

These numbers are baseline observations, not acceptance targets. Re-measure
them after every structural phase and update this document if the source moves.

## 3. Non-negotiable invariants

### 3.1 State-machine ownership

- ALAS owns every normal and defensive branch.
- The adapter may bracket an ALAS flow and translate an observation or action.
- The adapter must not reproduce ALAS wait loops, retry loops, timer behavior,
  result handling, fleet mutation, or map mutation.
- A qualification harness may set up a starting state and collect evidence,
  but it may not manufacture the sequence later claimed as live ALAS behavior.

### 3.2 Fail-closed observation

- Every supported observation is derived from an exact typed semantic frame.
- Unknown ALAS resource names, primitives, flow contexts, phases, and direct
  pixel reads raise a classified gate error.
- An unmapped observation never silently returns `False`.
- A known discriminated state may prove mutually exclusive alternatives false.
  For example, a proven `BattleResult(grade="S")` may answer A/B/C/D queries
  false without requiring five independent screen reads.

### 3.3 Fail-closed action

- Every action is authorized from a fresh immutable frame lease.
- The lease binds PID, package/runtime compatibility identity, observer schema
  and driver revision, generation, flow scope, action capability, target
  identity, and remaining budget. A game update does not invalidate a lease
  merely because its version or file digest changed.
- Coordinates are output data, never authority. An action still requires exact
  Unity path, enabled/interactable state, bounds, screen geometry, foreground,
  top EventSystem raycast, blockers, and a permitted postcondition.
- Once input is dispatched, the budget is consumed before subsequent receipt
  validation so a partial failure cannot replay the action.
- Raw click, long-click, multi-click, swipe, drag, and backend input remain
  rejected unless a typed action adapter explicitly owns that operation.

### 3.4 Identity and evidence

- The pinned ALAS revision, adapter core revision, integration patch-series
  hash, Android/game/ANGLE identity, observer schema, runtime lock, run policy,
  and task configuration must be part of the evidence identity.
- Evidence from a different identity cannot promote or overwrite this run.
- Qualification-only capabilities have no implicit production opt-in.

## 4. Target architecture

```text
Original ALAS state machine
  -> ALAS port facade
       -> flow-scope stack
       -> typed observation request
       -> typed action intent
  -> flow adapter registry
       -> common navigation
       -> mission / commission / tactical / research
       -> dorm / build
       -> campaign / combat
  -> immutable SemanticFrame lease
       -> SemanticOracle projections
       -> Unity main-thread observer
  -> action gate and budget ledger
       -> RuntimeHandle input executor
       -> ADB / KVM / Redroid / external device
  -> capability manifest + immutable run policy
  -> receipts and bounded runtime trace
```

The adapter stays in the ALAS Python process. Moving the ALAS-facing facade to
another process would add latency and serialization around native ALAS objects,
timers, and call order without improving the current trust boundary. The Unity
observer remains behind its existing credential-checked local protocol.

## 5. Proposed module layout

Keep `alas_headless.alas_adapter` and `AlasSemanticSession` as compatibility
facades until all current integration calls have migrated.

```text
python/alas_headless/adapter/
  __init__.py
  ports.py                 # Protocols and request/receipt value objects
  errors.py                # Classified fail-closed errors
  frame.py                 # SemanticFrame, lease, refresh/invalidation rules
  scope.py                 # FlowScope and nested scope stack
  capabilities.py          # Observation/action/recovery capability identifiers
  policy.py                # Immutable run-policy parser and validator
  registry.py              # Flow-adapter registration and dispatch
  session.py               # Session lifecycle and dependency injection
  facade.py                # Existing ALAS-facing method compatibility
  pixel_guard.py           # Explicit unsupported pixel-access sentinel
  flows/
    common.py
    login.py
    mission.py
    mail.py
    commission.py
    tactical.py
    research.py
    dorm.py
    build.py
    campaign.py
    combat.py
```

Static name-to-meaning mappings may be stored as validated declarative data.
Derived state, mutually exclusive phase inference, and action postconditions
remain code with focused tests. Do not move executable predicates into loosely
validated JSON.

## 6. Core contracts

The following structures describe the required semantics. Exact Python names
may change during implementation, but weakening their fields requires a design
review.

### 6.1 Semantic frame

```python
@dataclass(frozen=True)
class SemanticFrame:
    frame_id: str
    pid: int
    generation: int
    scene_handle: int
    captured_monotonic_ns: int
    age_ms: float
    fingerprint: RuntimeFingerprint
    raw_state_sha256: str
    projections: Mapping[str, object]
```

Frame rules:

- one semantic `device.screenshot()` refresh creates or advances one frame;
- all subsequent `appear`, OCR, map-view, HP/level, and flow-state reads use
  that exact frame until the next refresh;
- a reader may not issue a hidden refresh to make one query pass;
- an input invalidates the current frame immediately;
- the next post-input frame must have a greater generation and the same PID,
  unless an explicitly authorized recovery changes the PID;
- truncation, parse errors, incoherent endpoint generations, stale age, or
  fingerprint drift invalidate the whole frame, not one field.

### 6.2 Flow scope

```python
@dataclass(frozen=True)
class FlowScope:
    scope_id: str
    kind: str
    operation: str
    parent_scope_id: str | None
    task_config_sha256: str
    allowed_capabilities: frozenset[str]
    deadline_monotonic_ns: int
```

Replace the current mutually exclusive per-flow context fields with a checked
scope stack. Only explicitly declared parent/child combinations are legal.
This supports real ALAS nesting such as navigation into a reward subflow while
still rejecting accidental context leakage.

Every `begin_*` must return a scope token. Every `end_*` must close that exact
token in `finally`; out-of-order or leaked scopes fail the session.

### 6.3 Observation request

```python
@dataclass(frozen=True)
class ObserveRequest:
    scope_id: str
    primitive: str
    alas_resource: str
    parameters: Mapping[str, object]
    frame_id: str
```

Dispatch uses `(flow kind, operation, primitive, ALAS resource)`, not only the
resource name. This makes reused names such as `BACK_ARROW` and
`POPUP_CONFIRM` contextual by construction.

### 6.4 Action intent and receipt

```python
@dataclass(frozen=True)
class ActionIntent:
    intent_id: str
    scope_id: str
    capability: str
    logical_action: str
    target_semantic_id: str
    frame_id: str
    expected_postcondition: str

@dataclass(frozen=True)
class ActionReceipt:
    intent_id: str
    pid: int
    before_generation: int
    action_generation: int
    semantic_id: str
    unity_path: str
    bounds: Bounds
    point: Point
    top_raycast: bool
    injected: bool
    backend_method: str
```

The ALAS facade may continue returning current receipt types while the migration
is in progress, but all live actions must ultimately pass through one ledger.

### 6.5 Runtime handle

`AlasSemanticSession` must receive a prepared runtime handle instead of owning
backend discovery or constructing ADB directly.

```python
class RuntimeHandle(Protocol):
    fingerprint: RuntimeFingerprint
    capabilities: RuntimeCapabilities

    def observer_request(self, request: str) -> Mapping[str, object]: ...
    def foreground_component(self) -> str: ...
    def tap(self, x: int, y: int) -> None: ...
    def swipe(self, x1: int, y1: int, x2: int, y2: int, ms: int) -> None: ...
```

An `AdbRuntimeHandle` may wrap the existing `AdbObserverBridge` first. KVM,
Redroid, TCG, ARM64 QEMU, and external-device lifecycle choices remain in their
backend modules. No adapter flow may branch on backend kind.

## 7. Capability and policy model

Runtime lifecycle capabilities and ALAS semantic capabilities are related but
separate namespaces.

Semantic capability classes:

- observation: page, map, camera, combat phase, result, HP/level, blocker;
- action: named Button click, grid click, viewport gesture, typed scrollbar;
- recovery: game restart, Android restart, observer rebind, controlled manual
  takeover boundary;
- evidence: raw trace completeness, receipt verification, source-call surface.

At session admission compute:

```text
required capabilities for exact task/config
  intersection observer/evidence manifest
  intersection runtime handle capabilities
  intersection run-policy grants
  intersection recovery closure
```

Any missing item stops before ALAS starts the mutating flow.

Replace the growing production environment-variable surface with one strict
run-policy document. During migration, environment variables may be parsed into
the same model, but conflicting old and new settings must fail.

Minimum policy fields:

```json
{
  "schema": "alas-headless.run-policy/v1",
  "profile_id": "cn-9.7.10-12-4-normal-one-battle",
  "upstream_alas_commit": "81ccf63b4540f00241628c82a58c02c7a2bb11af",
  "runtime_lock_sha256": "...",
  "task_config_sha256": "...",
  "grants": {
    "campaign.stage_entry": 0,
    "campaign.viewport_swipe": 0,
    "campaign.grid_click": 0
  },
  "deadline_seconds": 0,
  "recovery_policy": "qualification-stop"
}
```

All examples and checked-in defaults remain zero-input.

## 8. Upstream integration strategy

Do not replace the current patch with runtime monkey-patching. Maintain a
pinned, reproducible patch series:

```text
integration/alas/series/
  0001-semantic-device-and-module-ports.patch
  0002-semantic-frame-clock-and-pixel-guard.patch
  0010-mission-mail-flow-ports.patch
  0020-commission-tactical-flow-ports.patch
  0030-research-dorm-build-flow-ports.patch
  0040-campaign-map-camera-flow-ports.patch
  0050-combat-observation-and-action-ports.patch
  series.json
```

`series.json` binds patch order, SHA-256, upstream commit, and the minimum
adapter protocol version. Generate the distributable combined patch from this
series; do not hand-edit two divergent representations.

The core patch should own only stable choke points:

- semantic session attachment and cleanup;
- semantic frame refresh at the screenshot boundary;
- shared observation primitives;
- final click/swipe dispatch;
- explicit pixel-access rejection.

Task patches may adapt narrow direct-pixel algorithms to typed domain inputs,
but must not change the owning ALAS loop or branch order.

## 9. Execution phases

Each phase is a separate reviewable commit. Do not combine structural work and
new live input authority in one commit.

### Phase 0: freeze the baseline

Deliverables:

- record source line/method counts and the current environment-variable set;
- record the 432-test baseline and current combat coverage audit;
- verify the combined patch applies to pristine pinned upstream;
- capture the expected public adapter method inventory;
- add a machine-readable baseline manifest without copying ignored live
  evidence into Git.

Acceptance:

- main and worktree source remain behaviorally identical;
- no action budget or production flag changes;
- `git diff --check` and the full suite pass.

Stop if the pinned upstream checkout is dirty or not at the exact commit.

### Phase 1: introduce contracts behind the existing facade

Deliverables:

- create `adapter/ports.py`, `errors.py`, `scope.py`, and `registry.py`;
- implement compatibility calls from `AlasSemanticAdapter` and
  `AlasSemanticSession`;
- preserve every existing public method and exception class;
- add contract tests for scope mismatch, unknown dispatch, and receipt identity.

Acceptance:

- no integration-patch changes;
- existing golden receipts serialize identically;
- all current tests pass plus new contract tests;
- direct calls to the legacy facade and registry produce equivalent results.

Rollback: revert the phase commit. No data or runtime migration exists.

### Phase 2: extract flow adapters

Order:

1. mission and mail;
2. commission and tactical;
3. research, dorm, and build;
4. campaign pre-sortie;
5. campaign map, camera, and combat.

For each flow:

- move its mappings, context, derived states, actions, and proof builders;
- register the flow through the central registry;
- retain facade forwarding methods temporarily;
- run the flow-specific replay before moving the next flow;
- delete the old branch only after source and golden-trace parity.

Acceptance per flow:

- unchanged ALAS query/action order;
- unchanged budgets and fail-closed exceptions;
- no newly accepted resource or input;
- no cross-flow mutable state remains in the extracted module;
- full suite passes.

### Phase 3: make semantic frames transactional

Deliverables:

- add `SemanticFrame` and lease lifecycle;
- route semantic `device.screenshot()` to one explicit refresh;
- serve all reads in one ALAS iteration from the same frame;
- invalidate frames after actions and require a newer post-action generation;
- introduce the unsupported pixel sentinel and inventory every triggered direct
  pixel consumer in the pinned replay surface;
- adapt only the narrow direct inputs already proven by G19/G20 contracts.

Acceptance:

- tests prove no hidden refresh within one frame;
- cross-generation Button/UI/map composition is impossible;
- stale-frame and use-after-action reads fail;
- every direct pixel read in a supported flow produces a classified failure;
- no black-frame absence result is accepted.

Stop if the pixel sentinel changes normal non-semantic ALAS behavior.

### Phase 4: add immutable policy and capability closure

Deliverables:

- strict `run-policy/v1` parser;
- capability identifiers and exact task-profile requirements;
- environment-to-policy compatibility parser;
- preflight report listing satisfied, missing, and forbidden capabilities;
- recovery-closure requirements for every post-input state;
- policy and capability hashes in action receipts and runtime evidence.

Acceptance:

- all checked-in examples grant zero actions;
- a missing observation, action, blocker, or recovery capability fails before
  the first mutating input;
- unknown policy fields, duplicate grants, booleans used as integers, negative
  budgets, and identity mismatch fail;
- no backend type appears in a flow adapter.

### Phase 5: split and verify the upstream patch series

Deliverables:

- deterministic patch-series builder;
- pristine pinned-upstream apply test;
- Python compile/import test against the fully patched tree;
- actual original-ALAS replays against that patched tree;
- source call-surface inventory for observations, actions, direct pixels, and
  unsupported Device access;
- removal of string-presence-only checks where an executable check can replace
  them.

Acceptance:

- each patch applies independently in order and none applies out of order;
- generated combined patch has a deterministic SHA-256;
- reverse apply restores the exact upstream tree;
- a newly introduced upstream query or Device call fails the call-surface gate;
- default non-semantic ALAS behavior remains unchanged.

### Phase 6: G36 original live post-click handoff

G36 is allowed only after Phases 0-5 pass.

Qualification profile:

- pinned CN game 9.7.10 and pinned ALAS revision;
- exact 12-4 normal-mode configuration used by G35;
- one admitted ordinary combat target;
- fresh same-PID map and target recheck after the natural camera branch;
- exactly one grid-click grant;
- no qualification harness actions after the grid click;
- recovery policy fixed before input.

Required live ownership:

```text
original _goto(target, expected="combat")
  -> original device.click(grid) through ActionPort
  -> original arrival/combat wait loop
  -> original combat_appear
  -> original combat
     -> combat_preparation
     -> combat_execute
     -> combat_status
  -> original HP/level update
  -> original arrival confirmation
  -> original map/fleet/battle mutation
  -> original predict/find_path_initial
```

The adapter may provide typed phase, result, blocker, map, HP/level, and action
observations. It may not call the ALAS methods above in place of `_goto()`.

Pre-input gate:

- exact upstream/task/runtime/policy identity;
- current frame fresh, coherent, same PID, and untruncated;
- target route, node, geometry, top raycast, foreground, and blockers valid;
- canonical normal-path observation closure complete;
- every configuration-reachable defensive branch is mapped, proven impossible,
  or covered by the frozen qualification recovery boundary;
- all expected post-grid action ports qualified;
- one unused grid-click budget and no unrelated action grants.

Positive evidence:

- action receipt for the original grid click;
- original ALAS call trace showing the complete post-click owner chain;
- strictly increasing semantic frames from click through stable map;
- `battle_count + 1`, ammunition decrement, target enemy cleared, and fleet at
  the admitted target;
- no harness-injected combat/result/map actions;
- no unknown observation, direct pixel read, dropped trace record, transport
  rejection, or identity drift;
- explicit cleanup and post-run read-only checkpoint.

Negative tests must include stale lease, covered target, PID change, policy
hash change, unknown phase, unexpected grade, active blocker, action reorder,
missing HP/level, map drift, extra click, and recovery-capability absence.

G36 success is one controlled qualification, not unattended production.

### Phase 7: repeated workload and production admission

Before execution, freeze numerical gates for:

- consecutive ordinary sorties;
- maximum observer age and request latency;
- zero unknown observation/action/pixel access;
- zero dropped or rejected mandatory evidence records;
- game-process restart and observer rebind;
- Android-runtime restart where the backend claims it;
- cleanup, task resumption, and account-state preservation.

Run counts and latency limits must be chosen from baseline evidence before the
qualification starts. Do not weaken them after a failed run. Hardware/backend
claims remain fingerprint-specific.

Production admission requires a separate review that changes the checked-in
run policy from zero-input. Passing G36 alone must not change defaults.

## 10. Validation commands

Run from this worktree unless a phase explicitly targets the pristine upstream
checkout:

```powershell
$env:PYTHONPATH = 'python'
python -m pytest -q
python -m compileall -q python scripts/python tests
git diff --check
git status --short --branch
```

Patch validation must name the exact pristine checkout:

```powershell
git -C H:\program\AzurLaneAutoScript-upstream-readonly rev-parse HEAD
git -C H:\program\AzurLaneAutoScript-upstream-readonly apply --check `
  H:\program\AzurLaneAutoScript-Headless-alas-adapter-v2-plan\integration\alas\0001-semantic-oracle-hooks.patch
```

Do not run reverse-apply or apply operations against an unverified working tree.

## 11. Required review checkpoints

Request review at these boundaries:

1. contracts and directory layout before moving flow behavior;
2. first extracted flow before repeating the pattern;
3. semantic screenshot/frame-clock design before patching `Device`;
4. run-policy schema and capability taxonomy before replacing environment
   variables;
5. generated patch series before deleting the original combined source;
6. G36 pre-input evidence bundle before authorizing the live grid click;
7. G36 result before defining production repetition gates.

No checkpoint may be approved solely from unit-test counts. Include actual
ALAS replay, patch application, identity, trace completeness, and relevant live
evidence for the claimed boundary.

## 12. Risks and controls

| Risk | Control |
| --- | --- |
| Structural refactor silently broadens behavior | Golden receipts, source-call inventory, zero new capabilities in Phases 1-3 |
| One resource name means different things by page | Dispatch on flow/operation/primitive/resource, not resource alone |
| Multiple observer calls compose an impossible frame | Screenshot-scoped immutable frame lease |
| NULL framebuffer silently makes pixel checks false | Unsupported pixel sentinel and direct-access inventory |
| Action succeeds and later observation fails | Pre-input capability plus recovery closure; consume budget at dispatch |
| Adapter becomes backend-specific | Inject `RuntimeHandle`; forbid backend branches in flow modules |
| Environment-variable combinations become unauditable | Strict immutable run policy with one evidence-bound hash |
| Upstream update introduces a new branch | Executable patched-tree replay and source-call surface gate |
| Qualification harness is mistaken for ALAS ownership | Require the original live call chain after the grid click |
| One successful battle is promoted to unattended | Separate repeated-workload and recovery phase; defaults remain zero |

## 13. Completion definitions

### Adapter v2 structural completion

- compatibility facade remains usable by the pinned integration;
- flow code is split into registered modules;
- one ALAS screenshot iteration uses one immutable semantic frame;
- unsupported pixel access is explicit;
- session depends on a runtime handle rather than constructing its backend;
- action authority comes from one immutable policy and ledger;
- upstream integration is a deterministic patch series;
- all current flows and evidence replay with no behavior broadening.

### G36 completion

- one exact live grid click is issued only by original ALAS `_goto()`;
- the complete live post-click combat/result/map loop remains ALAS-owned;
- required observation, action, blocker, and recovery closure is satisfied;
- final native ALAS state and semantic map checkpoint agree;
- evidence is complete, identity-bound, and independently verifiable;
- production and unattended flags remain disabled.

### Unattended-production completion

- separately frozen repetition, latency, stability, and recovery gates pass;
- rollback and account-state boundaries are verified;
- an explicit review approves a nonzero production policy;
- documentation distinguishes exact supported profile from all unsupported
  tasks, game versions, ABIs, backends, and configurations.

## 14. Atomic implementation runbook

This section is the normative execution order. Earlier sections explain the
design; this section tells the implementer what to do next. Execute one step at
a time. Do not begin a step while the previous step has an unmet exit gate.

Rules for every step:

1. start with `git status --short --branch` and require only the changes named
   by the current step;
2. do not mix a refactor with a new capability, budget, mapping, or live input;
3. run the focused test first, then the full suite;
4. run `git diff --check` before committing;
5. inspect the actual diff before committing;
6. use the suggested commit boundary unless review explicitly combines steps;
7. if an existing test must change, first explain which old behavior is being
   replaced and prove that the safety boundary is not weaker;
8. preserve every failed live artifact and never relax a frozen gate to pass.

### Milestone A: freeze a machine-readable baseline

#### Step A01: add a baseline-audit script

Preconditions:

- worktree branch is `codex/alas-adapter-v2-plan` or its implementation
  successor;
- `HEAD` descends from `a580b2d`;
- pinned upstream checkout is clean at `81ccf63`.

Create:

- `scripts/python/audit_alas_adapter_baseline.py`;
- `tests/test_alas_adapter_baseline.py`.

The script must read source without importing or starting ALAS and output one
canonical JSON document containing:

- schema `alas-headless.adapter-baseline/v1`;
- current core Git commit;
- pinned upstream commit from one checked-in source of truth;
- line and method counts for `alas_adapter.py` and `semantic_oracle.py`;
- combined integration-patch file count and line count;
- sorted `ALAS_SEMANTIC_*` variable names found in tracked Python/patch files;
- public methods of `AlasSemanticAdapter` and `AlasSemanticSession`;
- current combat manifest coverage counts;
- SHA-256 of the combined patch and combat observer manifest.

The test must reject unstable key order, absolute paths, timestamps, dirty-tree
content, malformed coverage, and missing pinned identities.

Commands:

```powershell
$env:PYTHONPATH = 'python'
python scripts/python/audit_alas_adapter_baseline.py `
  --output artifacts/adapter-baseline.json
python -m pytest -q tests/test_alas_adapter_baseline.py
python -m pytest -q
git diff --check
```

Exit gate:

- repeated runs produce byte-identical JSON;
- no source outside the script/test is changed;
- full suite passes.

Commit boundary: `test: freeze ALAS adapter baseline inventory`

#### Step A02: add an executable pinned-patch check

Create:

- `scripts/python/verify_alas_patch_tree.py`;
- focused tests using a temporary Git fixture.

The verifier must:

1. require an explicit upstream path;
2. require an exact clean `HEAD` equal to the pinned commit;
3. run `git apply --check` on the combined patch;
4. copy or create a disposable worktree before applying the patch;
5. apply the patch only in the disposable tree;
6. compile the patched Python files;
7. report a canonical result with patch SHA-256 and changed-file list;
8. remove only the disposable worktree it created.

It must refuse a dirty upstream, wrong commit, missing `.git`, unexpected patch
paths, or a pre-existing output directory.

Commands:

```powershell
$env:PYTHONPATH = 'python'
python scripts/python/verify_alas_patch_tree.py `
  --upstream H:\program\AzurLaneAutoScript-upstream-readonly `
  --patch integration/alas/0001-semantic-oracle-hooks.patch `
  --plan
python -m pytest -q tests/test_alas_integration_patch.py
python -m pytest -q
```

Exit gate:

- plan mode is read-only;
- executable test uses only a disposable tree;
- the original upstream status remains clean.

Commit boundary: `test: execute pinned ALAS patch verification`

### Milestone B: create the adapter kernel without changing behavior

#### Step B01: create the package and error taxonomy

Create:

- `python/alas_headless/adapter/__init__.py`;
- `python/alas_headless/adapter/errors.py`;
- `tests/test_adapter_errors.py`.

Define classified errors under the existing `SemanticGateClosed` boundary:

- `AdapterContractError`;
- `FlowScopeError`;
- `UnknownObservationError`;
- `UnsupportedPixelRead`;
- `StaleFrameError`;
- `CapabilityClosureError`;
- `ActionLeaseError`.

Do not replace existing public exceptions yet. Add tests for inheritance and
safe messages; messages must not contain account, token, command output, or raw
observer payloads.

Exit gate:

- importing `alas_headless.adapter` has no ADB, socket, subprocess, environment,
  or filesystem side effects;
- full suite passes.

Commit boundary: `refactor: add semantic adapter kernel errors`

#### Step B02: add immutable port value objects

Create:

- `python/alas_headless/adapter/ports.py`;
- `tests/test_adapter_ports.py`.

Implement frozen, strictly validated value objects for:

- `FlowScope` and `FlowScopeToken`;
- `SemanticFrameIdentity`;
- `ObserveRequest` and `ObserveResult`;
- `ActionIntent`, `ActionLease`, and the v2 action receipt;
- protocol definitions for observation, action, and runtime-handle ports.

Validation must reject booleans as integers, empty identifiers, noncanonical
capability names, negative generations, unordered bounds, points outside
bounds, false top-raycast on injected actions, and PID/fingerprint mismatch.

Do not connect these types to `AlasSemanticAdapter` in this step.

Exit gate:

- value objects round-trip through canonical dictionaries used by tests;
- no behavior or integration patch changes;
- full suite passes.

Commit boundary: `refactor: define semantic adapter port contracts`

#### Step B03: implement a checked flow-scope stack

Create:

- `python/alas_headless/adapter/scope.py`;
- `tests/test_adapter_scope.py`.

Implement:

- root-scope open and exact-token close;
- allowlisted parent/child relationships;
- rejection of sibling overlap, duplicate close, out-of-order close, token from
  another session, and session shutdown with leaked scopes;
- a context manager that always attempts exact close in `finally`;
- read-only inspection for trace fields without exposing mutable state.

Initially allow only current non-nested behavior. Add a parent/child pair only
when an actual pinned ALAS call chain requires it and a replay covers it.

Exit gate:

- randomized operation-sequence tests never leave an invalid stack accepted;
- no current adapter context has been migrated yet;
- full suite passes.

Commit boundary: `refactor: add checked ALAS flow scope stack`

#### Step B04: implement registry dispatch

Create:

- `python/alas_headless/adapter/registry.py`;
- `tests/test_adapter_registry.py`.

Registry keys are `(flow kind, operation, primitive, resource)`. Implement:

- exact registration;
- duplicate-registration rejection;
- exact dispatch;
- explicit pattern handlers for dynamic resources such as indexed rows;
- ambiguity rejection when two patterns match;
- deterministic capability inventory;
- unknown request failure that includes safe identifiers but no payload data.

Do not add a catch-all handler. Do not return `False` for an unknown request.

Exit gate:

- exact, pattern, ambiguous, and unknown cases are covered;
- registry import is side-effect free;
- full suite passes.

Commit boundary: `refactor: add contextual adapter registry`

#### Step B05: route one read-only resource through the new kernel

Choose `LOGIN_CHECK` or another read-only mapping with stable existing tests.
Do not choose an action or a contextually reused resource.

Modify:

- `alas_adapter.py` to construct the registry behind the compatibility facade;
- the smallest suitable flow module;
- focused adapter tests.

Keep the old implementation available only as a test oracle during this step.
The test must invoke both paths over the same fake oracle frame and compare
result, oracle calls, package-gate calls, and exception behavior.

Exit gate:

- one named read uses registry dispatch;
- every other resource follows the old path;
- no integration patch or public method changes;
- full suite passes.

Commit boundary: `refactor: route first ALAS observation through registry`

### Milestone C: extract flows one at a time

Apply Steps C01-C04 separately to each flow in this order:

1. login;
2. mission;
3. mail;
4. commission;
5. tactical;
6. research;
7. dorm;
8. build;
9. campaign pre-sortie and fleet preparation;
10. campaign map/camera;
11. combat observation/action.

Do not migrate the next flow until the current flow has completed C04.

#### Step C01: inventory the selected flow

Before editing behavior, produce a review note or machine-readable test fixture
listing:

- `begin/end` entrypoints;
- ALAS resource names and primitives;
- dynamic resource patterns;
- semantic target IDs and derived states;
- action targets and budget fields;
- context fields read or mutated;
- package-gate and oracle calls;
- expected exceptions;
- pinned live/offline evidence and replay tests.

Exit gate: every branch in the old flow implementation is accounted for.

No commit is required if the inventory is kept in the implementation commit's
review notes; otherwise use `docs: inventory <flow> adapter surface`.

#### Step C02: create the flow module with parity tests

Create `python/alas_headless/adapter/flows/<flow>.py` and a focused test file.
Move static mappings, derived-state logic, and context state for that flow.

Run old and new implementations against the same fake frames. Compare:

- results and exceptions;
- package-gate call count;
- semantic-oracle request sequence;
- action intent and receipt fields;
- budget before/after state;
- flow close behavior after success and failure.

The new flow is not active in production dispatch yet.

Exit gate: parity tests cover every item from C01.

#### Step C03: switch facade dispatch for the selected flow

Modify only the selected flow's facade methods to call the registry module.
Preserve public method names and return types. Keep compatibility conversion at
the facade boundary rather than leaking old types into the new flow.

Run:

```powershell
$env:PYTHONPATH = 'python'
python -m pytest -q tests/test_alas_adapter.py
python -m pytest -q tests/test_semantic_oracle.py
python -m pytest -q
git diff --check
```

Also run the selected flow's original-ALAS replay/qualification script when one
exists. Live input is not authorized by this migration.

Exit gate:

- facade uses only the new module for this flow;
- no new supported query or action exists;
- old and new evidence receipts remain equivalent.

#### Step C04: delete the old flow implementation

Delete only branches proven unused after C03. Run `rg` for old context fields,
mapping constants, helper names, and duplicated budget handling. Remove exports
only when no pinned patch or script imports them.

Exit gate:

- no duplicated implementation remains;
- public compatibility imports still work;
- full suite and actual flow replay pass;
- source counts are recorded in the commit notes.

Commit boundary for C02-C04: `refactor: extract <flow> semantic adapter`

### Milestone D: decouple session transport from ADB

#### Step D01: add an ADB runtime-handle adapter

Create:

- `python/alas_headless/adapter/runtime_handle.py`;
- `tests/test_adapter_runtime_handle.py`.

Wrap the existing `AdbObserverBridge`; do not duplicate its subprocess logic.
Expose observer request, foreground, tap, swipe, PID, and fingerprint through
the v2 runtime-handle protocol.

Exit gate:

- bridge behavior and classified ADB tracing are unchanged;
- handle cannot provision, start, stop, or silently reconnect a backend;
- full suite passes.

Commit boundary: `refactor: wrap ADB bridge as semantic runtime handle`

#### Step D02: inject the handle into `AlasSemanticSession`

Add an optional explicit `runtime_handle` constructor argument. During
migration, `from_environment()` may create the ADB wrapper through one factory,
but `open()` must operate only on the protocol.

Tests must cover:

- explicit handle path;
- legacy environment path;
- conflicting handle and ADB arguments;
- handle fingerprint mismatch;
- close after partial open;
- no subprocess use with a fake handle.

Exit gate: session behavior is equivalent and all existing callers work.

Commit boundary: `refactor: inject runtime handle into semantic session`

#### Step D03: remove direct bridge knowledge from flow code

Search for `AdbObserverBridge`, `.bridge`, `adb`, serial, and backend kinds in
adapter flow modules. Move identity and package verification behind the handle
and package gate. Keep direct ADB only inside the bridge/handle implementation
and runtime qualification code.

Exit gate:

- no flow module imports ADB or backend implementations;
- existing process-lease semantics still bind the same PID/package;
- full suite passes.

Commit boundary: `refactor: isolate adapter flows from ADB backend`

### Milestone E: introduce atomic frame semantics

#### Step E01: add controller-side `SemanticFrame`

Create:

- `python/alas_headless/adapter/frame.py`;
- `tests/test_adapter_frame.py`.

First build frames from existing atomic oracle state without changing ALAS
integration. Validate identity, generation, scene, age, completeness, and raw
payload digest. Add frame acquire, borrow, invalidate, and close operations.

Exit gate:

- a frame cannot mix different generations or fingerprints;
- action invalidation blocks all later reads from that frame;
- full suite passes.

Commit boundary: `refactor: add immutable semantic frame lease`

#### Step E02: make facade reads consume an explicit current frame

Add a session `refresh_frame()` method. Migrate one read-only flow first, then
the remaining extracted flows. A flow read may use the current frame or fail
with `StaleFrameError`; it may not refresh implicitly.

Tests must count observer requests and prove that multiple reads in one frame
cause one acquisition. Transition retry helpers must acquire a deliberately new
frame between attempts and record that transition.

Exit gate:

- no migrated flow performs a hidden oracle refresh;
- old non-frame paths are removed after all flows migrate;
- full suite and flow replays pass.

Commit boundary: `refactor: bind adapter reads to semantic frames`

#### Step E03: patch the ALAS screenshot clock

Add the smallest upstream patch change so that, only in semantic mode,
`Device.screenshot()` refreshes the current semantic frame. Normal ALAS must
retain its current screenshot implementation byte-for-byte outside the guarded
branch.

Update actual patched-tree tests, not only patch-string tests. Prove:

- one screenshot advances the frame;
- repeated observations do not refresh;
- an action forces the next screenshot to acquire a newer generation;
- screenshot interval/timer ownership remains ALAS-owned;
- closing the session clears the frame.

Exit gate: original ALAS replay call order is unchanged.

Commit boundary: `feat: use ALAS screenshot as semantic frame clock`

#### Step E04: add the unsupported pixel sentinel

Create `pixel_guard.py` and install the sentinel only in semantic mode. Start in
an audit mode that records and raises on array conversion, slicing, cropping,
OpenCV/NumPy coercion, and template access.

Run all pinned original-ALAS replays and produce a direct-pixel inventory. For
each hit choose exactly one outcome:

- adapt the narrow method input to an already proven typed projection;
- mark the branch unsupported in capability closure;
- exclude it only if pinned source/config analysis proves it unreachable.

Never implement a black-array fallback.

Exit gate:

- supported replay paths have zero unclassified pixel access;
- unsupported paths stop with the exact classified error;
- non-semantic ALAS is unchanged.

Commit boundary: `feat: reject unsupported pixels in semantic mode`

### Milestone F: replace environment budgets with immutable policy

#### Step F01: implement `run-policy/v1`

Create:

- `python/alas_headless/adapter/policy.py`;
- `integration/alas/policies/zero-input.example.json`;
- `tests/test_adapter_policy.py`.

Implement strict exact-field parsing, canonical JSON hashing, identity binding,
nonnegative integer grants, deadline validation, and recovery-policy enum.

Exit gate: checked-in policy grants zero actions and malformed policies fail.

Commit boundary: `feat: add immutable ALAS semantic run policy`

#### Step F02: translate legacy environment variables into policy grants

Implement one compatibility translator. It must:

- parse every current variable with existing validation;
- produce the same zero/default or bounded grants;
- reject deprecated booleans already rejected by current code;
- reject simultaneous explicit policy and nondefault legacy grants;
- emit only safe deprecation trace fields, not noisy warnings per query.

Use table-driven tests covering every variable found by A01.

Exit gate: existing environment-based tests pass through the translator.

Commit boundary: `refactor: translate legacy semantic grants to policy`

#### Step F03: add action ledger and capability closure

Create:

- `python/alas_headless/adapter/capabilities.py`;
- `python/alas_headless/adapter/ledger.py`;
- focused tests.

Implement exact required/available/granted/recovery set comparison. Preflight
must return a canonical report and refuse mutation when anything is missing.
The ledger consumes an action grant at dispatch and never restores it after an
ambiguous or failed backend call.

Exit gate:

- all current action paths consume the central ledger;
- zero-input policy remains the default;
- partial closure always fails before input;
- full suite passes.

Commit boundary: `feat: gate semantic actions on capability closure`

#### Step F04: remove per-flow budget ownership

One flow at a time, replace mutable integer budget fields with ledger leases.
Keep facade query methods such as `*_allowed()` only as compatibility views.

For each flow prove:

- identical zero-budget behavior;
- identical one-use behavior where already qualified;
- reuse, nested flow, exception, and session-close behavior;
- receipt contains policy hash and capability ID.

Exit gate: no action budget is stored in a flow context.

Commit boundary: one `refactor: move <flow> authority to action ledger` commit
per flow family.

### Milestone G: convert the upstream integration to a patch series

#### Step G01: define series manifest and builder

Create:

- `integration/alas/series/series.json`;
- `scripts/python/build_alas_patch_series.py`;
- builder tests.

The first manifest may contain the existing combined patch as one member. The
builder must validate order, upstream commit, paths, and SHA-256, then produce a
byte-deterministic combined patch.

Exit gate: generated output is byte-identical to the current combined patch.

Commit boundary: `build: define deterministic ALAS patch series`

#### Step G02: split the core port patch

Using a disposable patched upstream worktree, isolate only session attachment,
frame clock, shared observation primitives, final input ports, and pixel guard
into `0001`/`0002`. Generate patches from Git commits rather than manually
cutting hunks.

Exit gate:

- core patches compile but do not claim task coverage alone;
- task patches applied afterward restore the exact full patched tree;
- combined patch result matches the pre-split patched tree.

Commit boundary: `build: split ALAS semantic core patch`

#### Step G03: split task patches in flow order

Split mission/mail, commission/tactical, research/dorm/build, campaign, and
combat. After each split:

- apply the prefix series to pristine upstream;
- compile/import affected modules;
- run relevant original-ALAS replay;
- verify full series tree equivalence;
- update manifest hashes.

Exit gate: every patch has one ownership theme and deterministic order.

Commit boundary: one `build: split <flow> ALAS integration patch` per group.

#### Step G04: make the series authoritative

Generate the legacy combined patch in validation/release tooling. Add a test
that fails if checked-in generated output differs. Update documentation and
runtime lock inputs to bind the series manifest hash.

Exit gate: there is only one editable source of integration truth.

Commit boundary: `build: make ALAS patch series authoritative`

### Milestone H: close the exact G36 pre-input surface

#### Step H01: define the exact task profile

Create a zero-input profile for pinned 12-4 normal one-battle qualification.
Bind all ALAS configuration values that affect `_goto()` and combat branches,
including fleet lock, ambush, auto mode, submarine mode, retirement, story,
event mode, save-items behavior, and expected end.

Exit gate: changing any bound value changes the profile hash and invalidates
preflight.

Commit boundary: `test: freeze G36 ALAS task profile`

#### Step H02: regenerate the source/replay capability surface

Run pinned original ALAS with a rejecting Device and complete call recorder.
Produce exact sets for:

- observation requests by primitive;
- direct typed-state reads;
- action targets;
- pixel accesses;
- sleep/timer boundaries;
- Device methods;
- configuration-reachable defensive roots.

Compare with G19/G28 surfaces. Any added or removed call requires review; do not
silently update the expected set.

Exit gate: the exact task profile has a reviewed capability requirement file.

Commit boundary: `test: freeze G36 capability surface`

#### Step H03: close normal-path observations

Acquire or reuse identity-bound evidence to produce typed discriminated states
for preparation, executing, result S, experience S, enemy searching, stable map,
HP, and levels. Map ALAS queries through the combat flow adapter.

Do not require independent negative screen templates where a reviewed typed
union proves alternatives mutually exclusive. Unknown grades or phases remain
closed.

Exit gate:

- normal-path replay is built entirely from raw observer records;
- all normal-path queries resolve without fixture phase tokens;
- no input is injected.

Commit boundary: `feat: close G36 normal combat observations`

#### Step H04: close reachable defensive and recovery requirements

For each defensive root from H02, do one of:

- qualify exact observation and action evidence;
- prove it unreachable from the frozen configuration/source;
- require qualification-stop/manual takeover recovery before the grid click.

Ambush, retirement, story, alternate result, guild/mission popup, network, and
mis-click paths must be explicit rows in the preflight report.

Exit gate: preflight has no implicit unknown branch.

Commit boundary: `feat: close G36 defensive capability preflight`

#### Step H05: run an input-free live G36 preflight

Add or update the qualifier to:

1. attach to the exact runtime identity;
2. acquire a fresh map;
3. let original ALAS choose target/route;
4. let original ALAS perform any admitted camera branch;
5. recheck the exact top-raycast target;
6. compute capability/recovery closure;
7. stop at original `device.click(grid)`;
8. emit a signed/hash-bound preflight bundle with
   `grid_input_injected=false`.

Run it at least twice from unchanged state to detect nondeterministic surface
or target selection. Do not add a live-click switch in this step.

Exit gate: repeated preflights select the same logical branch and complete with
zero unknown calls and zero input.

Commit boundary: `test: qualify input-free G36 preflight`

### Milestone I: execute and verify G36

#### Step I01: add a qualification-only one-click policy

Create the policy only after H05 review. It grants exactly one
`campaign.grid_click` for the exact preflight identity and has a short deadline.
It grants no generic clicks, result actions beyond already qualified exact
targets, arbitrary swipe, or production capability.

The policy must not be the checked-in default. Store only a redacted template
or generator inputs if the live policy binds local evidence paths.

Exit gate: policy validation passes and any changed identity refuses it.

Commit boundary: `test: define G36 one-click qualification policy`

#### Step I02: add explicit mutation arming to the qualifier

Require two independent switches, following runtime qualification precedent:

- `--execute`;
- `--allow-semantic-input`.

Plan mode and either switch alone must be input-free. The qualifier must show
the exact target, capability, remaining action count, recovery policy, and
output directory before execution without exposing account data.

Exit gate: CLI tests prove all refusal combinations and pre-existing output
directory refusal.

Commit boundary: `feat: arm controlled G36 semantic input`

#### Step I03: perform the controlled live run

This is an operational gate, not an automatic test step.

Before running:

- verify device serial and foreground package;
- verify exact PID/runtime lock/game/ANGLE/ALAS/policy hashes;
- archive the accepted H05 preflight;
- ensure the recovery owner is available;
- ensure no unrelated emulator or benchmark contention is present;
- create a new evidence output directory.

Execute once. Do not rerun automatically after any input-attempt failure.

Immediately after execution collect:

- action receipt and complete runtime trace;
- original ALAS call-order trace;
- post-run stable semantic map;
- battle/ammunition/fleet/native-map state;
- unknown/pixel/transport/drop counts;
- cleanup outcome.

Stop conditions after dispatch include any unknown call, stale/missing frame,
unexpected popup/grade, PID drift, trace loss, ALAS exception, or map mismatch.
Use only the frozen recovery policy; do not improvise raw input.

No commit is made until I04 independently verifies the artifact.

#### Step I04: add an offline G36 verifier

Create a verifier that accepts only the captured evidence bundle and immutable
manifests. It must recompute hashes and prove every G36 positive/negative
condition from Section 9 without connecting to ADB.

Tests must tamper each critical field independently: PID, generation, call
order, action count, raycast, policy hash, phase, grade, HP/level, map state,
trace completeness, recovery, and cleanup.

Exit gate:

- accepted artifact verifies offline;
- every tamper fixture fails at the intended gate;
- verifier reports `production_enabled=false`.

Commit boundary: `test: verify controlled G36 live handoff`

#### Step I05: document the exact G36 result

Update `docs/status.md`, README summary, integration README, and a dedicated
G36 report. State separately:

- what original ALAS owned;
- which adapter observations/actions were used;
- whether input occurred;
- exact supported fingerprint/profile;
- failed/negative attempts;
- remaining production and recovery gaps.

Exit gate: documentation contains no unattended or cross-backend claim.

Commit boundary: `docs: record G36 live ALAS handoff qualification`

### Milestone J: repeated qualification and production review

#### Step J01: freeze workload gates before running

Use G36 trace evidence to set, document, and commit numerical thresholds for
repetition, latency, age, errors, cleanup, game recovery, and Android recovery.
Do not derive thresholds after observing the qualification results.

Commit boundary: `test: freeze ALAS repeated-workload gates`

#### Step J02: implement an input-bounded repeated runner

The runner uses the same task profile and policy system, with a finite total
action count and output directory per episode. It stops on the first failed
episode and never resumes automatically after an ambiguous input result.

Exit gate: synthetic/offline failure injection proves stop and cleanup rules.

Commit boundary: `feat: add bounded ALAS repeated qualification runner`

#### Step J03: qualify game and runtime recovery separately

Run game-process recovery first. Run Android recovery only on a backend that
declares and has already qualified it. Require new PID where appropriate,
identical immutable fingerprint, observer rebind, fresh frame, and task-state
reconciliation before any resumed action.

Do not combine the first recovery qualification with the first repeated
workload.

#### Step J04: request explicit production-policy review

Only after repeated and recovery reports pass, prepare a diff that changes a
specific checked-in policy or production gate. The review must include exact
scope, rollback, unsupported cases, evidence fingerprints, and default impact.

Until that review is accepted, all defaults remain zero-input and
`production_ready=false`.

## 15. Recommended commit sequence

The expected implementation history is intentionally fine-grained:

```text
test: freeze ALAS adapter baseline inventory
test: execute pinned ALAS patch verification
refactor: add semantic adapter kernel errors
refactor: define semantic adapter port contracts
refactor: add checked ALAS flow scope stack
refactor: add contextual adapter registry
refactor: route first ALAS observation through registry
refactor: extract login semantic adapter
refactor: extract mission semantic adapter
...
refactor: extract combat semantic adapter
refactor: wrap ADB bridge as semantic runtime handle
refactor: inject runtime handle into semantic session
refactor: isolate adapter flows from ADB backend
refactor: add immutable semantic frame lease
refactor: bind adapter reads to semantic frames
feat: use ALAS screenshot as semantic frame clock
feat: reject unsupported pixels in semantic mode
feat: add immutable ALAS semantic run policy
refactor: translate legacy semantic grants to policy
feat: gate semantic actions on capability closure
refactor: move <flow> authority to action ledger
build: define deterministic ALAS patch series
build: split ALAS semantic core patch
build: split <flow> ALAS integration patch
build: make ALAS patch series authoritative
test: freeze G36 ALAS task profile
test: freeze G36 capability surface
feat: close G36 normal combat observations
feat: close G36 defensive capability preflight
test: qualify input-free G36 preflight
test: define G36 one-click qualification policy
feat: arm controlled G36 semantic input
test: verify controlled G36 live handoff
docs: record G36 live ALAS handoff qualification
```

Pause for review after the first registry-routed resource, the first extracted
flow, the screenshot frame clock, policy admission, authoritative patch series,
input-free G36 preflight, and controlled G36 result.
