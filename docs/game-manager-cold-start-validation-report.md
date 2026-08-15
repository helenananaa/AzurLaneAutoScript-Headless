# Game Manager cold-start and update-tolerance validation

## Outcome

The Headless GameManager cold-restart path passed a live validation on
2026-08-15. The normal session path no longer rejects an installed game because
its version, base APK digest, or `libil2cpp.so` digest differs from the original
9.7.10 evidence build. It checks the concrete package shape needed to attempt
the runtime, launches the game, and lets the observer and semantic contracts
report an actual incompatibility if one is encountered.

This is update-tolerant startup, not a claim that every future game version is
already semantically compatible. The live device still had CN 9.7.10 installed;
acceptance of a changed version and split APK layout is covered by deterministic
tests rather than a fabricated live update.

## Runtime policy

The default GameManager/session path requires:

- the exact configured package and MainActivity component;
- one numeric package PID and a new PID after a cold restart;
- the supported native ABI (`x86_64` for this profile);
- one base APK path and one discoverable `libil2cpp.so`;
- the pinned ANGLE observer driver revision and protocol schemas;
- the expected foreground component, coherent generations, and a fresh frame
  before semantic input.

It does not calculate or compare the game base APK or `libil2cpp.so` digest.
The semantic runtime identity schema is v2 and contains package, component,
required ABI, and observer driver revision, but no installed game version or
game-file digest. Explicit forensic fingerprint helpers remain available for
evidence collection; they are not called by normal startup.

Runtime qualification follows the same compatibility decision. It may record
the observed game version and `libil2cpp.so` digest in its evidence fingerprint,
but neither value is compared with the old game section of the runtime lock.
The Android build/API/ABI and installed ANGLE APK remain exact qualification
boundaries because they define the observer runtime rather than the mutable game
client.

## Live environment

| Item | Observed value |
| --- | --- |
| AVD | `H:\AndroidAVD\alas_game_api32_x64.avd` |
| ADB serial | `emulator-5580` |
| Android | API 32, cold boot with `-no-snapshot` |
| Package | `com.bilibili.azurlane` |
| Component | `com.bilibili.azurlane/com.manjuu.azurlane.MainActivity` |
| Installed game | CN `9.7.10`, version code `9710` |
| Game ABI | `x86_64` |
| ANGLE revision | `be80ce591a481c12d60c50d6040d40c035b40a2b` |

The previous Android Framework instance had lost its `activity`, `package`, and
`window` services after a system_server Watchdog kill. A user-authorized AVD
cold boot restored `boot_completed=1`, all three services, and a live
system_server before the game test began. This host recovery is recorded so it
is not confused with a game-startup failure.

## Live sequence

The original patched ALAS `game_manager()` entry owned the tested sequence.
The adapter did not call a synthetic login helper in place of ALAS.

| Time (Asia/Shanghai) | Event |
| --- | --- |
| `22:24:44.025` | ALAS entered `FORCE STOP AZURLANE` |
| `22:24:46.220` | semantic cold restart submitted with `-force-gfx-st` |
| `22:24:48.398` | original login handler entered |
| `22:25:12.331` | typed `login/enter` clicked at the exact `LoginUI2(Clone)` target |
| `22:25:12.332` | ALAS reported `Login success` |

The compatibility check and launch submission completed in about 2.2 seconds.
The log contained no game-package hashing phase. After login, Android reported
PID `1981`, the exact MainActivity as both top-resumed and focused, and the game
was left running when the temporary validation process ended.

## Independent observer read

An independent `GET /v1/state` read on the PID-bound observer returned:

| Field | Value |
| --- | ---: |
| Protocol/status | `alas-headless.observer/v1` / `ok` |
| PID / ABI | `1981` / `x86_64` |
| Snapshot generation | `1921` |
| Scene / semantic generation | `2` / `2` |
| Frame age | `49 ms` |
| Total / active buttons | `190` / `40` |
| Button extraction errors | `0` |
| UI stage / method mask | `100` / `15` |

The active hierarchy was already past login and contained the monthly-sign-in
and award surfaces. The driver revision matched the pinned ANGLE revision.
This independently proves a fresh post-login semantic runtime on the new game
PID rather than only trusting the `Login success` log line.

## Deterministic validation

The complete repository suite passed after the policy change:

```text
1014 passed, 46 warnings in 144.38s
```

Focused regression tests additionally prove that:

- an installed `10.0.0` / version code `10000` is accepted;
- a package with one base APK plus split APKs is accepted;
- the compatibility path fails if any `sha256sum` command is attempted;
- an unsupported ABI is rejected before launch;
- semantic runtime identity changes with the required ABI, not with a game
  version or game-file digest;
- runtime qualification accepts a game version and `libil2cpp.so` digest that
  differ from the runtime lock while retaining exact ANGLE validation.

`git diff --check` also passed.

## Remaining boundaries

- A real post-9.7.10 client was not installed during this validation. Its first
  run must still prove observer attachment, semantic mappings, and login/main
  behavior.
- ARM64, other package/server variants, different Activities, and missing or
  relocated IL2CPP layouts are not qualified by this x86_64 result.
- Stop failure, start failure, login failure, repeated PID turnover, and the
  full 600-second observer-start timeout remain negative live cases.
- The strict package fingerprint API remains diagnostic-only. Reintroducing it
  into a normal GameManager/session path requires an explicit policy change and
  new update-tolerance review.
