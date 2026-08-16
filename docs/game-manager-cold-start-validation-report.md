# Game Manager cold-start and update-tolerance validation

## Outcome

The Headless GameManager panel completed live qualification on 2026-08-16.
Both `AutoRestart` values, an already-stopped app, repeated PID turnover,
start/transport/login failures, the full 600-second observer-start timeout,
recovery, and observer-forward cleanup were exercised through the original
patched ALAS entry. The normal session path no longer rejects an installed game because
its version, base APK digest, or `libil2cpp.so` digest differs from the original
9.7.10 evidence build. It checks the concrete package shape needed to attempt
the runtime, launches the game, and lets the observer and semantic contracts
report an actual incompatibility if one is encountered.

This is update-tolerant startup, not a claim that every future game version is
already semantically compatible. The live device still had CN 9.7.10 installed;
acceptance of a changed version and split APK layout is covered by deterministic
tests rather than a fabricated live update.

Within the qualified CN x86_64 semantic profile, `GameManager.AutoRestart` is
therefore fully supported. Other packages, ABIs and Activities remain separate
runtime profiles rather than values of this field.

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

## Full lifecycle qualification

The 2026-08-16 run added the previously missing lifecycle branches. The
machine-readable source is
[`integration/alas/game-manager-live-validation-receipt.json`](../integration/alas/game-manager-live-validation-receipt.json).

| Case | Live result |
| --- | --- |
| `AutoRestart=false`, game running | PID `1981` stopped; seven samples over 45 seconds found no package PID and no relaunch |
| `AutoRestart=false`, already stopped | exited `0` and remained stopped |
| repeated `AutoRestart=true` | `7133 -> 8748 -> 10361`; both runs reached `Login success` and `Login to main confirm` |
| start failure | disabling the exact package produced exit `1`, no PID and no observer forward; re-enable recovered to PID `12030` |
| full observer timeout | native graphics deliberately withheld the observer; the production 600-second bound failed after `605.746s`, left PID `13790`, injected no login input and leaked no forward |
| login network failure | one reversible Android `eth0` OUTPUT reject caused fail-closed stale observation after `134.364s`; no login click occurred and removal recovered to PID `21799` |
| stop transport failure | a missing ADB executable exercised the real 90-second stop-verification window; exit `1` after `93.638s`, PID stayed `21799`, and no forward leaked |

Live qualification exposed 49 observer forwards retained by earlier standalone
GameManager invocations. GameManager now closes its semantic session in a
`finally` block on success, disabled mode, restart failure and login failure.
After removing the historical forwards, two consecutive successful restarts
and every failure case each ended with zero matching forwards. Deterministic
replay also asserts cleanup after stop, restart and login exceptions.

The final restoration check proved the game package enabled, ANGLE selection
restored to `angle`, the temporary network rule absent, MainActivity foreground,
and a fresh PID `21799` observation at generation `4210`, age `79 ms`, with 45
buttons and zero extraction errors. The independent probe closed its own
forward, leaving the host count at zero.

## Profile boundaries

- A future client update still needs ordinary runtime compatibility evidence;
  GameManager does not promise semantic mappings for software that does not yet
  exist. Version and split-layout admission are nevertheless covered without a
  hard-coded game digest.
- ARM64, other package/server variants, different Activities, and missing or
  relocated IL2CPP layouts are different runtime profiles and are not inferred
  from this x86_64 qualification.
- The strict package fingerprint API remains diagnostic-only. Reintroducing it
  into a normal GameManager/session path requires an explicit policy change and
  new update-tolerance review.
