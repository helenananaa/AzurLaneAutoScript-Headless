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
