# ALAS semantic pixel-access inventory

This note records Step E04 of
`docs/alas-adapter-v2-execution-plan.md`. The machine-readable inventory is
`integration/alas/pixel-access-inventory-e04.json`; the verifier is
`scripts/python/verify_alas_pixel_inventory.py`.

## Boundary

Only semantic mode replaces `device.image` with `SemanticPixelGuard`. The
normal ALAS screenshot branch is still byte-identical to pinned upstream after
removing the guarded semantic insertion. The guard contains only safe frame
identity and never creates a black, zero-filled, synthetic, or recoverable
pixel array.

Every attempted array conversion, NumPy protocol, slice, index, crop, copy,
iteration, buffer export, metadata read, explicit OpenCV boundary, or template
access records a typed `PixelAccessRecord` and raises the exact
`UnsupportedPixelRead`. Telemetry failure cannot replace that fail-closed
exception. A real `numpy.asarray()` coercion is included in the focused tests.

## Replay inventory

Seven pinned replay families are represented. The updated actual patched-login
replay installs a pixel guard and remains 4/4 with zero classified or
unclassified accesses. The actual patched screenshot/Device replay records one
classified `template-access` and proves that `GET_MISSION.match()` is never
entered after the rejection.

The older checked replay families remain bound to their existing reports and
records:

- reward/commission uses reviewed typed ports;
- campaign decision/goto is Device-free or stops at the final input boundary;
- ordinary combat replay is Device-free and typed;
- G28 contains one qualification-only synthetic `image_crop:info_bar` call;
- campaign camera continuation consumes typed geometry, not framebuffer data.

The current inventory therefore contains two triggered direct-pixel
consumers, both classified as unsupported capabilities:

1. `Device.handle_night_commission` template access. `GET_MISSION` is not a
   reviewed typed login observation, and the source branch is time-gated but
   reachable.
2. G28 ambush info-bar cropping. Its checked record is qualification-only,
   contains no promoted live mapping, and cannot authorize production pixels.

No consumer is silently excluded and no new typed adapter is claimed. Future
capability closure must keep `device.night-commission-template` and
`combat.ambush-info-bar-pixels` missing until independently qualified.

## Executed result

The ignored local verifier result is `artifacts/pixel-inventory-e04.json`:

- replay surfaces: 7;
- triggered consumers: 2;
- classified accesses: 2;
- unclassified accesses: 0;
- Android input: false;
- production ready: false.

The canonical patch also reverse-checks against the actual E04 patched tree.
Full patch application, compilation, replay parity, and the repository-wide
test suite remain commit gates.
