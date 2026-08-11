# ALAS semantic screenshot frame-clock validation

This note records the Step E03 boundary from
`docs/alas-adapter-v2-execution-plan.md`. It does not authorize any new live
input and it does not claim pixel compatibility, which remains Step E04.

## Patched boundary

The pinned ALAS `Screenshot.screenshot()` keeps ownership of
`_screenshot_interval.wait()` and `_screenshot_interval.reset()`. Immediately
after those calls, one guarded semantic-mode branch calls
`semantic_session.refresh_frame()`, stores the returned immutable
`SemanticFrame` as the current `device.image` placeholder, and returns it.

When no semantic session is attached, removing that five-line insertion
reconstructs the pristine pinned source byte-for-byte. The higher-level
`Device.screenshot()` remains unchanged, so its `stuck_record_check()`,
fallback handling, night-commission hook, and return order remain ALAS-owned.

The temporary `SemanticFrame` image value is deliberately not a pixel
substitute. Step E04 must replace it with the classified unsupported-pixel
sentinel before any supported semantic replay may consume `device.image` as an
array. No black or synthetic image is introduced.

## Executed evidence

`scripts/python/verify_alas_screenshot_frame_clock.py` reads and executes the
actual patched `Screenshot.screenshot()` and `Device.screenshot()` method ASTs
from a disposable pinned ALAS worktree. Its E03 result is ignored local
evidence at `artifacts/screenshot-frame-clock-e03.json`.

The verifier proves:

- successful order is `stuck_record_check -> interval.wait -> interval.reset
  -> session.refresh_frame -> handle_night_commission`;
- frame IDs advance from `frame-10-1` to `frame-10-2` across screenshots;
- repeated login observations add zero observer requests;
- the reviewed fake-runtime login action invalidates generation 10;
- a same-generation post-action screenshot fails after ALAS has performed its
  interval wait/reset, and generation 11 succeeds;
- closing the real `AlasSemanticSession` clears the leased frame;
- the verifier injects no Android input.

The canonical combined patch was also reapplied and compiled from pristine
upstream commit `81ccf63b4540f00241628c82a58c02c7a2bb11af`. The patched login
handler replay remains 4/4 with unchanged semantic action order, closed scopes,
and `android_input_injected=false`; its ignored result is
`artifacts/login-flow-replay-e03.json`.

The current combined-patch surface is therefore 25 Python files. The C01
inventory's 24-file count and old patch hash remain historical evidence bound
to its recorded core commit; they are not rewritten as if E03 had existed at
that checkpoint.

## Remaining gate

E03 does not make raw pixels available. E04 must inventory every direct pixel
consumer reached by pinned replays and make each one either use an already
proved typed projection or stop with an exact `UnsupportedPixelRead`. Normal
non-semantic ALAS must remain unchanged.
