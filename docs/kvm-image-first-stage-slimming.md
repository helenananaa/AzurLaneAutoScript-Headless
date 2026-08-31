# KVM image first-stage slimming

This change introduces the project-owned `alas_kvm_x86_64` Goldfish product.
It is deliberately narrower than `sdk_phone64_x86_64`, but it is not the AOSP
`sdk_slim_x86_64` test image. The project still needs real Android system
surfaces for WebView login, package installation, permission handling,
diagnosis, and recovery.

## Preserved boundary

The first stage keeps the standard Android framework, SELinux enforcement,
Binder, FBE and storage services, ADB, package installation, permission and
intent resolution, networking and TLS, WebView, CJK-capable input, SystemUI,
Settings, Launcher3, and the qualified Goldfish/KVM vendor stack. The game,
game resources, account data, ALAS configuration, and ANGLE NULL observer stay
externally installed and independently upgradable.

Launcher3 remains the recovery HOME for this stage. Replacing it with a small
project-owned rescue HOME is a separate change and must not be conflated with
package removal.

## Removed in this stage

The product omits generic camera, gallery, clock, calendar, contacts, dialer,
messaging, music, search, theme, wallpaper, dream, print, MTP, webcam, CTS shim,
and device-demo packages. The build script validates the final
`product_packages.txt` inventory: every required boundary module must be
present and every declared first-stage removal must be absent before a passing
image manifest can be written.

## Qualification boundary

Repository tests and an AOSP product-config check prove only that the source
contract is internally consistent. Support status must not be promoted until a
fresh candidate image proves boot and ADB readiness, WebView initialization,
external package install and upgrade, zero-account pre-login state, ANGLE NULL
observer freshness, userdata persistence, game recovery, Android recovery, and
rollback. Screenshots are not an acceptance signal while the game uses ANGLE
NULL.

## First candidate result

The 2026-08-27 incremental candidate built as
`alas_kvm_x86_64-trunk_staging-userdebug`. Its package-policy receipt reports
875 product modules, all 23 required modules present, and all 36 declared
first-stage removals absent. Allocated logical partition content decreased from
1,527,808,000 to 1,372,250,112 bytes: 155,557,888 bytes (about 148.4 MiB or
10.2%) removed while preserving the qualified partition envelope for rollback.

An independent no-snapshot AVD then passed two cold boots at 27.063 and 27.093
seconds. Both reported Android 14/API 34, x86_64, `alas_kvm_x86_64`, SELinux
Enforcing, a ready `com.android.webview` provider, and `Accounts: 0`; the
userdata sentinel remained present on the second boot. The candidate was
stopped after qualification and the existing v7 runtime remained active.

This is an image-foundation result, not game-path qualification. External game
installation and upgrade, ANGLE NULL and observer freshness, game recovery,
Android recovery, and rollback remain the re-entry conditions before support
promotion.

## External-install validation

The follow-up validation used the same independent AVD and did not touch the
running v7 instance. The pinned 9.7.10 Bilibili APK installed from an empty
package state in 113 seconds. A same-version `adb install -r` replacement then
completed in 94 seconds: `firstInstallTime` remained unchanged,
`lastUpdateTime` advanced, the selected ABI remained x86_64, and the installed
base APK SHA-256 remained identical to the KVM archive. This proves external
installation and replace-install, not a cross-version application migration.

The pinned x86_64 ANGLE observer installed with `--force-queryable`. The four
ANGLE settings survived a no-snapshot cold restart together with both APKs and
the existing userdata sentinel. Before and after the restart, the game used a
new exact PID, `GraphicsEnvironment` selected `org.chromium.angle`, the observer
resolved the installed `libil2cpp.so`, and a PID-bound `alas.g3.<pid>` socket
was published. WebView 119 remained ready and Android continued to report
`Accounts: 0`.

Typed Unity state did not become ready in the original candidate. Both launches
stopped after `RouteProcessService /init/agreement subscribe`; no agreement
callback or `AgreementWebActivity` followed, and snapshot/UI/buttons stayed
`unavailable`. That result was initially classified as an external agreement
configuration boundary. The follow-up investigation below supersedes that
classification for this candidate.

## Network-provisioning root cause and repair

The original candidate had no usable Android network: both `eth0` and `wlan0`
were down, there was no IP address or route, DNS lookup failed, and a packet
capture around the agreement subscription contained no packets. The custom
product included the generic AOSP `Provision` package. That package can mark
setup complete, but unlike the Goldfish `SdkSetup` package inherited by the
standard emulator product, it does not create and enable the emulator's
`AndroidWifi` network. A diagnostic-only `cmd wifi connect-network AndroidWifi
open` made the unchanged candidate obtain `10.0.2.16`, generate the 510-byte
`config_agreement.0`, open `AgreementWebActivity`, and publish
`ALAS_G3_BOOTSTRAP_READY {"swap":1}`. This isolated the failure to image
provisioning rather than the game service.

The product now requires `SdkSetup` and explicitly forbids generic `Provision`.
The package policy covers both sides of that boundary. Incremental build
`kvm-slim-stage1-wifi-fix-20260827-r3` passed with 874 modules, no missing
required module, and no forbidden module; its build manifest is:

```text
/srv/android-archive/kvm/evidence/kvm-slim-stage1-wifi-fix-20260827-r3/manifest.json
```

`sys.boot_completed=1` can precede Goldfish Wi-Fi connection by several
seconds. The KVM runtime therefore keeps the existing framework/package-manager
check and additionally waits for completed device provisioning plus a connected
Wi-Fi interface with an assigned IP before it launches the game. This check is
KVM-local; it does not add the emulator contract to external ADB backends.

A newly provisioned, no-snapshot AVD then proved the image-level repair without
any manual Wi-Fi command or copied userdata. On its first boot `SdkSetup`
created `AndroidWifi`, the guest obtained `10.0.2.16/24`, DNS was
`10.0.2.3`, and TCP 443 to `api.biligame.net` succeeded. `device_provisioned`
and `user_setup_complete` became 1 while `Accounts: 0` remained true.

The pinned game and x86_64 observer were then installed from the KVM APK
archive. An exact `-force-gfx-st` cold launch generated a fresh 510-byte
agreement configuration, opened the exact `AgreementWebActivity`, and reached
`ALAS_G3_BOOTSTRAP_READY {"swap":1}`. The 65-byte `config_data.xml` still had
no `initial_agreement_tag`; no agreement control was clicked, no previous
consent was copied, and no screenshot or coordinate input was used. A second
cold boot automatically reconnected Wi-Fi, retained both APKs and agreement
files, and reproduced the same activity and observer-ready result. Live
evidence is retained at:

```text
/srv/android-archive/kvm/evidence/kvm-slim-stage1-wifi-fix-live-20260827-r1/manifest.json
```

The validation AVD was stopped and retained, while the existing v7 service
remained active and untouched. Emulator 34.2.7 still exits with SIGSEGV after
its graceful `emu kill` helper completes; the ports and test unit were cleared,
and the second boot proved that userdata was persisted despite that separate
host-emulator shutdown defect.

This repair qualifies fresh-image network provisioning, agreement callback,
ANGLE observer bootstrap, and cold-boot persistence. It does not qualify the
post-consent `LoginUI2(Clone)` path, the approximately 28 GiB resource download,
Android recovery, or runtime release rollback. Those remain the re-entry
conditions before support promotion or the next partition-envelope reduction.

## Second-stage result

The second stage removes eight additional standalone modules: enterprise
provisioning (`ManagedProvisioning`), companion-device UI
(`CompanionDeviceManager`), SIM and NFC helper applications (`Stk`, `Tag`, and
`SecureElement`), `SoundPicker`, `BackupRestoreConfirmation`, and
`DynamicSystemInstallationService`. Credential Manager, the telephony core,
all APEX modules, WebView, networking, Settings, Launcher3, and the recovery
surfaces remain unchanged.

The first live candidate exposed a pre-existing first-stage dependency defect:
the retained Bluetooth PBAP service repeatedly crashed because
`ContactsProvider` had been removed. The final product therefore restores
`ContactsProvider` from `base_system.mk` and the package policy now requires it.
Enabling Bluetooth on the repaired image left `com.android.bluetooth` alive and
produced no `Failed to find provider com.android.contacts` failure.

Final incremental build `kvm-slim-stage2-contacts-fix-20260827-r2` passed with
867 modules, no missing required modules, and no forbidden module present. Its
allocated logical partition content is 1,358,774,272 bytes. Relative to the
Wi-Fi-fixed first stage this is a net reduction of 13,475,840 bytes (about
12.9 MiB); relative to the original 1,527,808,000-byte image it removes
169,033,728 bytes (about 161.2 MiB or 11.1%). The build manifest is:

```text
/srv/android-archive/kvm/evidence/kvm-slim-stage2-contacts-fix-20260827-r2/manifest.json
```

A new no-snapshot AVD created from the final image booted Android 14 with
SELinux Enforcing, `Accounts: 0`, `ContactsProvider` installed, and automatic
`AndroidWifi` provisioning at `10.0.2.16/24`; TCP 443 to
`api.biligame.net` passed. A retained game userdata AVD on the same final
system image preserved the pinned game, agreement configuration, empty consent
marker, ANGLE routing, and observer package. The observer reached
`ALAS_G3_BOOTSTRAP_READY {"swap":1}`, but the external agreement callback did
not reopen `AgreementWebActivity` within the single 90-second retry window.
That was the result of this bounded run; the routing diagnosis below supersedes
its earlier interpretation as an unconfirmed image capability.

No agreement input, account data, screenshots, resource download, workload
dataset, soak, or 12-4 run was used. Both test AVDs were stopped and retained;
the existing v7 service remained active and untouched. Final live evidence is
retained at:

```text
/srv/android-archive/kvm/evidence/kvm-slim-stage2-contacts-fix-live-20260827-r1/manifest.json
```

## Agreement re-entry root cause and durable network repair

DEX inspection showed that cached `config_agreement.0` is not sufficient to
route the SDK to the agreement page. `InitAgreementRouteService` still waits
for the asynchronous `/api/agreement/config` callback before invoking the
reviewed `AgreementWebActivity` route. The build host's `sing-box` TUN policy
sent this domestic HTTPS request through the selected proxy, whose upstream
returned `remote error: rejected`; the guest therefore remained in
`MainActivity` after the subscription log even though the WebView provider was
healthy.

The host now routes the required Bilibili/Biligame suffixes directly while
retaining the existing SSH-host direct rule. With the same final image and
retained game userdata, a cold start entered the exact component
`com.bilibili.azurlane/com.base.gsc_agreement_library.AgreementWebActivity`
after two seconds. Android then loaded WebView 119 and the x86_64
`libwebviewchromium.so` from the x86_64-only APK. The process was force-stopped
before the SDK's ten-second fallback, and root inspection confirmed the consent
preferences remained empty. No agreement control was clicked.

This investigation also found that Android's public captive-portal probe can
permanently disable `AndroidWifi` on a fresh userdata even when the guest's
required outbound path works. The dedicated `alas_kvm_x86_64` provisioning
path now sets `captive_portal_mode=0` before adding the emulator network. Android
14's `NetworkMonitor` treats the intentionally skipped probe as a successful
validation instead of recording a no-internet failure.

The focused incremental build completed in 1 minute 57 seconds with source lock
`7fb76e1be0cec08c2273f478a5526b0db562833481e148f2d0317371e00e87d3`.
A new no-snapshot AVD booted without manual Wi-Fi input, obtained
`10.0.2.16/24`, reported `NETWORK_SELECTION_ENABLED` and `VALIDATED`, reached
`api.biligame.net:443`, and automatically reconnected after one reboot. The
temporary instance was then stopped; the existing v7 service was not switched.
Evidence is retained at:

```text
/srv/android-archive/kvm/evidence/kvm-webview-x86_64-agreement-fix-20260827-r1
/srv/android-archive/kvm/evidence/20260827T115541Z/manifest.json
/srv/android-archive/kvm/evidence/kvm-wifi-captive-portal-ignore-live-20260827-r1
```

## Five-language resource and font trim

The next KVM-only pass keeps English, Simplified Chinese, Traditional Chinese,
Japanese, and Korean. `PRODUCT_LOCALES` is assigned after all inherited product
makefiles so `languages_default.mk` cannot append the full Android locale list
back into `PRODUCT_AAPT_CONFIG`. The final value is exactly:

```text
en_US zh_CN zh_TW ja_JP ko_KR
```

The Noto package list is also product-scoped. It retains the JP, KR, SC, TC,
and HK faces in `NotoSansCJK-Regular.ttc`, English Roboto/Noto Serif, emoji,
flags, and the two Android symbol subsets. The unused 26 MiB
`NotoSerifCJK-Regular.ttc` and unrelated Noto families are absent. Other AOSP
products still receive the upstream font list.

The first incremental build proved the font policy and reduced `system` by
54,992,896 bytes. Static inspection then found that an earlier placement of
`PRODUCT_LOCALES` had only declared the preferred locales: inherited defaults
were still packaging every translation. Moving the override after all product
inheritance made AAPT perform the intended resource trim. The second incremental
build completed successfully in 9 minutes 8 seconds without a clean build.

Relative to the immediate pre-trim KVM candidate, the five dynamic partition
images now occupy 1,095,847,936 bytes instead of 1,254,133,760 bytes: a reduction
of 158,285,824 bytes (about 151.0 MiB). The exported emulator `system.img`
remains 2,159,017,984 bytes because that file is the fixed super-partition
envelope; the shrink is in allocated partition content and therefore becomes
available when the envelope is reduced later.

Representative APK results confirm that the translation payload was actually
removed. English remains in each APK's unqualified default resources, while
`aapt2 dump configurations` reports only `ja`, `ko`, `zh-rCN`, and `zh-rTW` as
language-qualified configurations:

| APK | Before | After |
|---|---:|---:|
| Settings | 69,190,189 | 25,211,437 |
| SystemUI | 29,887,292 | 20,380,476 |
| Launcher3QuickStep | 32,588,473 | 30,462,649 |

`fc-query` reports the retained TTC faces as Noto Sans CJK JP, KR, SC, TC, and
HK, with `en`, `ja`, `ko`, `zh-cn`, `zh-hk`, and `zh-tw` coverage. A fresh,
no-snapshot userdata booted in about 29 seconds with Android 14, x86_64-only,
SELinux Enforcing, `Accounts: 0`, and `en-US` default locale. `AndroidWifi`
received `10.0.2.16/24`, and TCP 443 to `api.biligame.net` passed. All required
font files were present, the removed CJK serif file was absent, and the boot log
contained no missing-font or Minikin failure.

A bounded retained-userdata game launch published
`ALAS_G3_BOOTSTRAP_READY {"swap":1}` at four seconds without a crash. That v3
userdata already contained `initial_agreement_tag=1`, so this run did not and
cannot claim a fresh `AgreementWebActivity` re-entry. No consent state was
changed and no agreement input was sent. The temporary fresh userdata was
deleted after validation, the retained v3 userdata was kept, and the existing
v7 service remained active and untouched.

An attempted removal of AdServices, DeviceLock, HealthFitness,
OnDevicePersonalization, and UWB was deliberately abandoned before compilation:
Soong rejected the OnDevicePersonalization system-server classpath fragment.
All APEX changes were rolled back. Mainline classpath APEX removal therefore
remains a separate dependency-closure project, not part of this low-risk trim.

Build evidence is retained at:

```text
/srv/android-archive/kvm/evidence/20260827T123412Z/manifest.json
/srv/android-archive/kvm/evidence/kvm-five-locale-filter-20260827-r1/manifest.json
/srv/android-archive/kvm/evidence/kvm-resource-filter-fix-rebind-20260827-r1.json
```

## Dynamic-partition envelope trim

The KVM-only build profile now uses a 1.25 GiB dynamic-partition group and a
1.258 GiB super partition. The current five partition images total
1,095,847,936 bytes, leaving about 235 MiB of growth room inside the group.

The first incremental package correctly produced the smaller `super.img`, but
the exported emulator image remained 2,159,017,984 bytes. The cause was
`mk_combined_img.py`: its two-partition shortcut overwrote the old image with
`dd conv=notrunc` without checking whether the rounded partition layout had
changed. It therefore retained the old GPT and zero-filled tail after an
envelope reduction. The product patch now computes the expected combined-image
size and removes only a size-mismatched stale output before rebuilding its GPT.
This preserves the fast path when the layout is unchanged.

The corrected incremental build completed in 1 minute 48 seconds. Its measured
sizes are:

| Artifact | Before | After | Reduction |
|---|---:|---:|---:|
| `super.img` envelope | 2,155,872,256 | 1,350,565,888 | 805,306,368 |
| exported `system.img` | 2,159,017,984 | 1,353,711,616 | 805,306,368 |
| compressed system-image ZIP | 564,088,132 | 563,291,713 | 796,419 |

The 768 MiB raw-image reduction is a host-disk, cache, archive-extraction, and
runtime-bundle benefit. It barely changes download size because the removed
tail was almost entirely compressible zero space. It also does not reduce guest
RAM; memory sizing remains a separate runtime experiment.

A single fresh no-snapshot userdata boot verified the new GPT and envelope. It
reported product `alas_kvm_x86_64`, x86_64-only ABI, Android boot completion,
SELinux Enforcing, `device_provisioned=1`, `Accounts: 0`, Wi-Fi address
`10.0.2.16/24`, and successful TCP 443 egress. The temporary AVD used 1.3 GiB
of allocated host storage at the end of this bounded boot and was then deleted.
The existing v7 service remained active and was not switched.

Evidence is retained at:

```text
/srv/android-archive/kvm/evidence/kvm-envelope-1250m-20260827-r1/manifest.json
/srv/android-archive/kvm/evidence/kvm-qemu-envelope-rebuild-fix-rebind-20260827-r1.json
/srv/android-archive/kvm/evidence/kvm-envelope-1250m-qemu-fix-20260827-r1/manifest.json
```
