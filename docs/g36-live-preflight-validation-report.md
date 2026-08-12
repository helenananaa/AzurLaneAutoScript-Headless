# G36 input-free live preflight validation

Date: 2026-08-12

## Outcome

H05 passed twice on one unchanged rendered 12-4 map. Original ALAS selected
`battle_0`, route `F5 -> F4 -> F3 -> E3`, and the E3 combat target in both
runs. Its original `_goto()` prefix reached the exact `device.click(grid)`
statement and stopped without dispatching it. The checked bundle reports zero
Android, grid, camera, or other input and zero unknown calls.

This does not promote a capability and is not production readiness. The H04
recovery policy remains `qualification-stop`, `grid_click_allowed=false`, and
the next mutation step still requires a separately reviewed one-click policy.

## Runtime identity

- AVD serial: `emulator-5580`
- Visible rendered surface: `1280x720`
- Package/component: `com.bilibili.azurlane` /
  `com.bilibili.azurlane/com.manjuu.azurlane.MainActivity`
- Stable game PID: `3094`
- Runtime fingerprint SHA-256:
  `9e9728a00a1d9f671aa1dc419808845f6b2555f78b7c9a08ead75ef9af3ba3db`
- Observer/ANGLE revision:
  `be80ce591a481c12d60c50d6040d40c035b40a2b`
- Installed observer APK SHA-256:
  `7125f8eb697a90932c03b3f9573d526e340a23e654a620a1a0652f0720308471`
- Pinned upstream ALAS commit:
  `81ccf63b4540f00241628c82a58c02c7a2bb11af`

## Setup boundary

Setup inputs are excluded from both signed H05 runs. With the user's explicit
authorization, original ALAS entered 12-4, advanced map preparation, reconciled
fleet selection, and dispatched sortie. The initial live decision was the long
route `E8,E7,E6,E5,F5,F4,F3,E3` with optimized goto nodes `F5,E3`, which the
bounded combat admission correctly refused.

One setup-only exact top-raycast F5 grid action then executed ALAS's first
intermediate goto. A later map proved fleet 1 at F5 with unchanged ammunition
and unchanged D3/E3 enemies. Exact `[NetworkDown]` overlays observed during
failed qualification attempts were treated as setup recovery; the H05 run that
encountered one stopped without input before a later invocation reconnected.
No setup action is represented as part of the signed zero-input bundle.

The rendered observer advances continuously. Setup-only ALAS screenshots used
an exact snapshot/buttons/UI join and admitted a frame only when all three
generations matched. The two H05 runs used normal direct typed map reads and did
not inherit this setup compatibility path.

## Repeated runs

| Run | Map/decision/recheck generations | Branch and route | Target geometry |
| --- | --- | --- | --- |
| 1 | `43830 / 43830 / 43839` | `battle_0`, `F5,F4,F3,E3` | E3, `(609.072, 138.965)`, top raycast |
| 2 | `43849 / 43849 / 43858` | `battle_0`, `F5,F4,F3,E3` | E3, `(609.072, 138.965)`, top raycast |

Both runs used the same cell path and bounds
`(552.164,104.794)-(664.774,174.468)`. The stable logical-state hash is
`27946531a948462f6d67edec5418a64848e20a1bb506cdcd04c4b01f1927b273`,
and the stable map hash is
`a752b85f129277e30d5dd7fb6bf90f8e90a4adb30f15c98c1871489e3025d36a`.

The original call order was identical in both runs:

`hp_retreat_triggered -> fleet_set -> in_sight -> focus_to_grid_center -> convert_global_to_local -> ambush_color_initial -> enemy_searching_color_initial -> device.click`

The camera branch was owned by original ALAS and resolved as a zero-vector
centering check; no camera gesture was required or injected.

## Signed artifact

- Checked bundle: `integration/alas/g36-live-preflight.json`
- Bundle SHA-256:
  `a8dfdb91c41da228b49dc706c0f6496ef3bb94e10b875ad08a541779af10a240`
- Signature:
  `sha256:a8dfdb91c41da228b49dc706c0f6496ef3bb94e10b875ad08a541779af10a240`
- Task configuration SHA-256:
  `bea8b149ecd634dcd33d8972c3eae69db8bbbb1e5c4951c3c11159211f489b2f`
- H04 defensive preflight SHA-256:
  `7c3a699d9cd48c5794120e0fe12dc9a28cf084e2e702b98ffb53203d116e3c2b`

The builder revalidates two ordered runs, identical runtime identity, logical
state, map signature, original decision, target geometry, camera ownership,
call order, recovery closure, zero unknown calls, and every zero-input field
before computing the signature.
