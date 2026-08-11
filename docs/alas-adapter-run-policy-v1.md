# ALAS semantic run-policy/v1

Step F01 introduces the immutable parser and identity envelope only. It does
not yet replace legacy environment variables or authorize any adapter action;
those transitions belong to F02 and F03.

`python/alas_headless/adapter/policy.py` accepts exactly these top-level fields:

- `schema`;
- `profile_id`;
- `upstream_alas_commit`;
- `runtime_lock_sha256`;
- `task_config_sha256`;
- `grants`;
- `deadline_seconds`;
- `recovery_policy`.

Unknown, missing, or duplicate fields fail with `RunPolicyError`. Commit and
SHA-256 identities must be lowercase exact-length hex. Grant names must be
canonical tokens and values must be non-boolean nonnegative bounded integers.
The deadline uses the same integer rule. The recovery enum currently admits
only `qualification-stop` and `manual-takeover`; neither value creates action
authority by itself.

The policy hash is computed from ASCII canonical JSON with sorted keys and no
insignificant whitespace. It is derived by the frozen `RunPolicy` and cannot
be supplied independently by a caller. `RunPolicyIdentity` binds the exact
upstream ALAS commit, runtime-lock hash, and task-config hash at parse time or
through a later explicit check.

`integration/alas/policies/zero-input.example.json` is the checked-in safe
example. Its runtime hash is bound to
`integration/runtime/runtime-lock.example.json`; its task-config hash is the
canonical SHA-256 of
`integration/alas/profiles/g36-12-4-normal-one-battle.zero-input.json`.
That strict profile freezes the pinned CN 9.7.10, ALAS revision, 12-4 normal
configuration, one-battle end condition, and every `_goto()`/combat branch
setting admitted by G36. Every grant and the deadline remain zero, and
recovery is `qualification-stop`.

F01 validates capability-token syntax but deliberately does not invent the
required capability taxonomy. F03 must compare these grant tokens against the
exact task requirements and reject unknown, missing, forbidden, or incomplete
recovery closure before mutation.

## F02 legacy compatibility taxonomy

F02 translates the frozen A01 environment surface once, when the semantic
session is created. It retains these compatibility grant IDs:

| Legacy authority | Policy grant |
| --- | --- |
| `ALAS_SEMANTIC_ALLOW_MISSION_CLAIM_ONCE` | `mission.claim` |
| `ALAS_SEMANTIC_ALLOW_MAIL_MUTATIONS` | `mail.mutation` |
| `ALAS_SEMANTIC_ALLOW_TACTICAL_REWARDS` | `tactical.reward` |
| `ALAS_SEMANTIC_TACTICAL_ASSIGN_BUDGET` | `tactical.assign` |
| `ALAS_SEMANTIC_COMMISSION_REWARD_BUDGET` | `commission.reward` |
| `ALAS_SEMANTIC_COMMISSION_START_BUDGET` | `commission.start` |
| `ALAS_SEMANTIC_RESEARCH_REWARD_BUDGET` | `research.reward` |
| `ALAS_SEMANTIC_RESEARCH_START_BUDGET` | `research.start` |
| `ALAS_SEMANTIC_DORM_COLLECT_BUDGET` | `dorm.collect` |
| `ALAS_SEMANTIC_DORM_FEED_BUDGET` | `dorm.feed` |
| `ALAS_SEMANTIC_BUILD_SUBMIT_BUDGET` | `build.submit` |
| `ALAS_SEMANTIC_CAMPAIGN_STAGE_ENTRY_BUDGET` | `campaign.stage_entry` |
| `ALAS_SEMANTIC_CAMPAIGN_FLEET_MUTATION_BUDGET` | `campaign.fleet_mutation` |
| `ALAS_SEMANTIC_CAMPAIGN_SORTIE_BUDGET` | `campaign.sortie` |
| `ALAS_SEMANTIC_CAMPAIGN_COMBAT_BUDGET` | `campaign.grid_click` |
| `ALAS_SEMANTIC_CAMPAIGN_VIEWPORT_SWIPE_BUDGET` | `campaign.viewport_swipe` |

Absent legacy variables produce zero grants. The three retained boolean
variables preserve their historical exact-`1` behavior and translate to a
single compatibility grant; the already removed commission-reward boolean is
still rejected on presence. An explicit policy may replace the default legacy
grant set, but cannot be combined with any nonzero legacy grant. F02 does not
yet claim that this list is sufficient task capability closure; F03 owns that
preflight decision.

## F03 capability closure and action ledger

`TaskCapabilityProfile` binds one canonical profile ID and task-config SHA-256
to four available-capability requirements: observations, actions, recoveries,
and evidence. `required_grants` is a strict subset of `required_actions`.
This distinction is intentional: a task can require already-qualified exact
follow-up action ports while arming only one policy-controlled initiating
action, such as the G36 `campaign.grid_click`.

Admission produces `alas-headless.capability-closure/v1`. Its canonical report
contains the exact required and available sets, positive policy grants,
selected recovery, missing sets, unrelated grants, readiness, and a derived
SHA-256. A session refuses construction when:

- a required capability is not implemented by the supplied inventory;
- a required action grant is zero or absent;
- a positive grant is unrelated to the exact task profile;
- the selected recovery differs from the required and available recovery;
- the profile ID or task-config hash differs from the explicit run policy.

The default inventory advertises `recovery.qualification_stop` only. The
`manual-takeover` policy enum does not imply that its operational ownership
boundary is implemented.

`ActionLedger` consumes a positive grant under a lock immediately before the
final mutation backend call. A backend exception, ambiguous result, later
receipt failure, exhausted grant, incomplete closure, or closed session never
restores authority. F03 initially kept the legacy per-flow budget as a
temporary second gate; F04 has now removed every duplicate flow owner.

### F04 migration status

Mission and mail are the first migrated family. Their flow contexts retain
only ALAS-owned observation, navigation, and state-machine cache. Mission's
`mission_claim_allowed()` is now a compatibility view of
`ActionLedger.allowed("mission.claim")`; mail mutation admission reads the
same ledger directly. Ending or reopening either flow never recreates a grant.

Every ledger-backed `ActionReceipt` now carries the exact lowercase policy
SHA-256 and capability ID. `MissionClaimReceipt` propagates those fields from
the one claim action. A partial authority annotation is invalid, and ordinary
navigation receipts remain explicitly unarmed with both fields absent.

Commission and tactical are the second migrated family. Their shared context
keeps selected-row, transition-proof, popup-chain, and idempotency receipts,
but no reward/start/assignment budget or initial reward boolean. Commission's
reward/start compatibility queries and every tactical pre-confirm gate read
the ledger. A tactical finish receipt, rather than a stale permission flag,
owns its exact popup-close chain after the one reward grant is consumed.

Research, dorm, and build are the third migrated family. Their contexts keep
only project/queue evidence, navigation and transition receipts, stable dorm
panel state, and build preparation proof. Research start/reward, dorm
collect/feed, and build submit authority now comes exclusively from the
ledger, including multi-item dorm feeds. Reopening a flow cannot recreate a
grant, and a backend exception permanently consumes the dispatched grant.

Campaign is the final migrated family. Its context retains ALAS-owned stage,
fleet, sortie, map, camera, target-recheck, and combat evidence, but none of
the six campaign action budgets. Stage entry, fleet mutation, sortie, grid
click, viewport swipe, and qualification-only camera positioning all query
and consume the run ledger. Flow reopen preserves only genuinely unused
run-wide grants; it never reconstructs the configured allowance.
