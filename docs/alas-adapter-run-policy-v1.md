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
SHA-256 of the explicit example identity
`alas-adapter-v2:zero-input-example-task`. Every grant and the deadline are
zero, and recovery is `qualification-stop`.

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
| `ALAS_SEMANTIC_CAMPAIGN_COMBAT_BUDGET` | `campaign.combat` |
| `ALAS_SEMANTIC_CAMPAIGN_VIEWPORT_SWIPE_BUDGET` | `campaign.viewport_swipe` |

Absent legacy variables produce zero grants. The three retained boolean
variables preserve their historical exact-`1` behavior and translate to a
single compatibility grant; the already removed commission-reward boolean is
still rejected on presence. An explicit policy may replace the default legacy
grant set, but cannot be combined with any nonzero legacy grant. F02 does not
yet claim that this list is sufficient task capability closure; F03 owns that
preflight decision.
