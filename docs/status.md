# Validation status

Status is evidence-scoped. A later gate is not implied by an earlier pass.

## 2026-08-26

### Event C/D stage coverage and TimeLimit are live complete on the current event

- The original `EventC` and `EventD` tasks now complete official auto-search
  for C1-C3 and D1-D3 through the normal scheduler entry. The fresh C2, C3,
  D2, and D3 receipts each show `RunCount 1 -> 0`, the matching `LastStage`,
  return to the event page, no validation errors, and no raw-input fallback.
  Evidence is retained in
  `integration/alas/eventc-c2-auto-search-live-validation-receipt-20260826-r1.json`,
  `integration/alas/eventc-c3-auto-search-live-validation-receipt-20260826-r1.json`,
  `integration/alas/eventd-d2-auto-search-live-validation-receipt-20260826-r1.json`,
  and
  `integration/alas/eventd-d3-auto-search-live-validation-receipt-20260826-r1.json`.
- D3 exposed a dedicated hard-stage underlay (`Chapter_2050026`) in addition
  to the shared B3 route (`Chapter_2050006`). Both exact identities are now
  accepted; an unknown chapter remains rejected rather than guessed.
- `EventGeneral.TimeLimit` completed both live directions after fresh coherent
  observer state returned: an expired limit disabled the event with zero
  sortie, while a future limit admitted exactly one C1 run and returned
  cleanly. Evidence is
  `integration/alas/event-general-time-limit-expired-live-validation-receipt-20260826-r1.json`
  and
  `integration/alas/event-general-time-limit-future-eventc-c1-live-validation-receipt-20260826-r1.json`.
- A natural D3 dock-full popup was identified by its exact `强化/拓展/整理`
  controls. The recovery port delegates `整理` to ALAS's configured official
  one-click retirement transaction, never selects premium `拓展`, and keeps
  `强化` as the other ALAS-owned branch. This live encounter retired 95 ships
  (`930/930 -> 835/930`) and preserved their equipment, but the original run
  reached the equipment-preservation dialog before the reconnect classifier
  fix. The repaired automatic dock-full path is therefore covered offline and
  remains pending one fresh natural end-to-end live reproduction; it is not
  promoted as live complete by the later clean D3 sortie.

### Daemon typed idle soak, bounded sortie, and 12-4 official auto-search are live-qualified

- The original `AzurLaneDaemon.run_once()` completed a 180-second typed-only
  main-page soak with `Daemon.EnterMap=true`: all 63 iterations returned
  `idle`, observer generations advanced from `84200` to `84952` with 64
  distinct samples, the game PID remained `24414`, and the Daemon sent no tap
  or mutation. The temporary configuration was removed and the pre-existing
  observer-forward set was unchanged. Evidence is
  `integration/alas/daemon-idle-soak-live-validation-receipt-20260826-r4.json`.
- A separate reversible run selected exact stage `1-1` through the existing
  campaign boundary, then handed its typed map-preparation frame to the
  original Daemon branch. Daemon used one reviewed input to reach fleet
  preparation; the validator cancelled through the exact fleet back control
  and proved restoration of chapter `1-1`. No sortie started, oil remained
  `4127`, the PID remained `24414`, and the only mutation capability consumed
  was the initial `campaign.stage_entry`. Evidence is
  `integration/alas/daemon-enter-map-live-validation-receipt-20260826-r3.json`.
- The positive bounded run kept that same ALAS-owned campaign transaction,
  required the inherited fleet tuple `(1, 0, 0)`, manual-search state and
  `Use2xBook=false` to match configuration exactly, and allowed no fleet
  mutation. The original Daemon then owned both preparation branches, entered
  the exact `LevelGrid` map root, and the validator withdrew before combat and
  restored the main page. PID `24414` remained stable; only
  `campaign.stage_entry` and `campaign.sortie` were dispatched. The successful
  run consumed 10 oil and removed its temporary configuration. Evidence is
  `integration/alas/daemon-sortie-live-validation-receipt-20260826-r9.json`.
- The full positive run selected exact `12-4`, reconciled the live fleet from
  `(1, 2, 1)` to configured `(1, 2, 0)` through the original ALAS fleet
  preparation loop, proved `fleet1=mob` and `fleet2=boss`, and handed combat
  entirely to the game's official auto-search. The adapter used zero campaign
  combat and zero viewport-swipe budget after sortie, observed
  `CombatUIStandard`, waited `526.36` seconds for the exact total-reward
  panel, closed its reviewed exit, and restored the main page with PID `24414`
  unchanged. Oil changed exactly `2799 -> 2482`: the proven 10-oil map entry
  plus six 42-oil mob battles and one 55-oil boss battle, for 317 total. The
  temporary configuration was removed. Evidence is
  `integration/alas/daemon-auto-search-live-validation-receipt-20260826-r8.json`.
- This proves bounded main-page residence and one exact active-context sortie,
  not unattended production completeness. A cold-start inherited MAP/FLEET
  overlay still lacks a trusted stage/config ownership chain and remains
  fail-closed. Disconnect/rare-popup handling and a materially longer
  cross-scene soak remain open, so the Daemon panel stays `P`.

### WarArchives winter-crown A1 is live complete

- The adapter now replaces the archive category/card boundary, all 45 archive
  cards identifiable in the pinned CN client, letter-coded stage selection,
  normal/hard switching, Data Key counters, and the exact five-key entry
  confirmation. The original ALAS `CampaignWarArchives` remains responsible
  for stage routing, map logic, enemy selection, combat, stop conditions, and
  scheduling.
- A controlled winter-crown A1 run consumed `295 -> 290` Data Keys, cleared
  four normal enemies and the boss, acknowledged the exact grade, reward, and
  statistics surfaces, and returned to the archive stage page at `290/300`.
  Two transient geometry/result transitions stopped before input and resumed
  only after their exact typed postconditions were re-proven. Evidence is
  `integration/alas/war-archives-live-validation-receipt-20260826-r18.json`.
- Red-dyed A1 remains locally unsupported because its upstream map script
  calls `fleet_2_push_forward()` toward empty cell C2, outside the reviewed
  enemy/pickup grid-input boundary. Three ALAS archive values
  (`war_archives_20230525_cn`, `war_archives_20230803_cn`, and
  `war_archives_20240725_cn`) have no matching card in the pinned CN game data
  and fail only that requested task. Other archive cards share the offline
  navigation contract but are not claimed as individually live-qualified.

### Meowfficer Fort typed action boundary is complete offline

- The current dock reports Fort `0/8`. A typed inspection of the Fort page
  confirmed that all eight slots are empty; its `batch` control opens the cat
  assignment page rather than performing chores. The selection page was
  closed without choosing a cat or consuming resources.
- Semantic mode now asks the adapter for the exact dock state before the
  original `meow_fort()` red-dot branch. With zero occupied slots it returns
  `False` without input, allowing the original task to schedule normally.
  When at least one cat is already assigned, the adapter now enters the
  original Fort page and runs only the exact active `play`, `feed`, or `clean`
  controls derived from the reviewed clone hierarchy, stopping when the typed
  chore list becomes empty. It does not assign or rearrange the user's cats.
- The controlled original-task run preserved every typed resource and counter,
  injected no Android input, used no mutation dispatch, and scheduled the next
  server update. Evidence is
  `integration/alas/meowfficer-fort-empty-live-validation-receipt-20260826-r1.json`.
  The occupied-slot action path is covered offline and can re-enter live
  qualification after at least one cat is assigned in game and a real chore
  becomes available.

### Meowfficer once-a-day collection and requeue is live complete

- The original pinned `RewardMeowfficer.run()` remains the task owner. In
  semantic mode its existing `once_a_day` branch now reads exact dock/training
  counters, collects one completed cat when dock capacity permits, evaluates
  the acquisition rarity and typed talent sprites, reuses the original queue
  order, closes the training page, and writes the original 150–210 minute
  schedule.
- A controlled API 32 x86_64 run started with 8 completed slots and collected
  one ordinary tiered-talent SSR. With `RetainTalentedGold=true`, the adapter
  proved that its three talents were tiered and cancelled the unnecessary lock
  prompt. It then auto-selected one gold box, confirmed the exact `1/1` queue,
  and returned to the dock.
- The postcondition was capacity `37/40 -> 38/40`, completed slots `8/10 ->
  7/10`, and gold boxes `469 -> 468`; coins stayed `109505` and purchase quota
  stayed `15/15`. All nine inputs
  have semantic IDs, generations, and Unity paths; raw mutation dispatches are
  zero. Evidence is
  `integration/alas/meowfficer-train-positive-live-validation-receipt-20260826-r7.json`.
- Tierless or otherwise unknown talents remain conservatively classified as
  special. The exact acquisition `lock`/`unlock` controls and the nested
  confirmation are now typed, so enabled purple/gold retention locks the card
  before continuing; generation rather than card identity permits multiple
  visually identical cats to be collected in one seamlessly run.
- The enhancement port now selects the configured 1–12 target by exact card
  bounds, admits material only at or below `MaxFeedLevel`, proves each selected
  marker and the `n/10` counter, submits through the exact nested confirmation,
  and requires generation advance plus a coin decrease without level
  regression. No-material, level-30, coin-limit, invalid-index, and in-battle
  conditions preserve the original ALAS result contract. Sunday and
  `seamlessly` plans are therefore admitted again.
- Live typed inspection also closed the current-client hierarchy drift: the
  dock exposes 16 numeric `frame/content/0..15/info` cards instead of the old
  `ComanderCatTpl/info/icon` sample. Both exact structures are supported and
  covered. The current visible first 12 ALAS targets are all level 30, so an
  `EnhanceIndex=1`, `MaxFeedLevel=5` run returned `leveled_max` before input;
  coins, capacity, box counts, and every dock counter remained identical and
  no raw mutation dispatch occurred. Evidence is
  `integration/alas/meowfficer-enhance-level-max-live-validation-receipt-20260826.json`.
- Positive purchasing also sets the exact requested count and verifies quota,
  coin, and total-box deltas. These new positive purchase, occupied Fort,
  multi-collect, special-lock, and enhancement branches are offline-complete;
  live promotion remains pending on their corresponding natural states. For
  enhancement specifically, re-entry requires a visible configured target
  below level 30 plus at least one unlocked material at or below
  `MaxFeedLevel`. The panel therefore remains `B`.

## 2026-08-25

### EventSp official auto-search main path is live complete

- The original pinned `EventSp` task started from the semantic main page,
  selected `event_20260813_cn/SP`, proved the exact remaining `1/1` attempt,
  100% clear state, official auto-search availability, and the reviewed
  `(fleet1, fleet2, submarine) = (1, 2, 0)` tuple before its only sortie.
- The fleet tuple already matched, so no fleet mutation occurred. Generation
  `687801 -> 687952` proved the sortie and `CombatUIStandard(Clone)` handoff.
  The game then owned the complete map and combat path for 315 seconds; ALAS
  sent no combat, grid, viewport, camera-positioning, or recovery input.
- The same supervised runner observed official combat-auto at generation
  `691127`, the Boss total-reward exit at generations `691162/691163`, returned
  to the event page, and read the exact `0/1` attempt at generation `691263`.
  `StopCondition.RunCount` persisted `1 -> 0` and the task scheduled the next
  server update at `2026-08-26 00:00`.
- The qualification passed with `run_result=true`, an empty validation-error
  list, `recovery_total=0`, and no raw-input fallback. The first invocation on
  the retained older materialized tree stopped before worker launch or Android
  input because its source did not match the required rollback guard; the
  successful run used a clean locked `81ccf63` worktree with the authoritative
  89-member patch series. Evidence is retained in
  `integration/alas/eventsp-sp-auto-search-live-validation-receipt-20260825-r10.json`
  and
  `integration/alas/eventsp-sp-auto-search-live-validation-receipt-20260825-r11.json`.
- EventSp is promoted from partial (`P`) to main-path complete (`L`), not full
  (`F`). Other fleet tuples, non-default shared campaign fields, and future
  event layouts remain localized qualification work.

## 2026-08-23

### Apple Silicon Mac reaches the typed G4 login boundary under HVF

- A real M1 MacBook Air runs Android Emulator 37.1.11 with an API 32 ARM64
  guest, `-no-window`, and `-accel on`; a fresh read-only check reports
  `Hypervisor.Framework OS X Version 26.6` available.
- The ARM64 CN 9.7.10 game is the resumed foreground Activity and is explicitly
  routed through the ARM64 ANGLE observer driver. The retained observer snapshot
  reports `status=ok`, generation 1421, `age_ms=52`, Unity-main-thread access,
  and the exact `LoginUI2(Clone)` root.
- The active semantic slices contain 11 Buttons, 5 Text records, and 25 Images
  without truncation or observer errors. Exact login paths include current
  server, licence, privacy, repair, opening, and login-page roots.
- This promotes Apple Silicon Mac + Android Emulator/HVF from future candidate
  to a real G4 login-page/typed-observer exploration. It does not prove account
  login, the main page, an ALAS workload, recovery, cleanup, soak, or a dedicated
  `macos-hvf` backend. Evidence hashes and the retained-host boundary are in the
  [Mac/HVF login validation report](mac-apple-silicon-hvf-login-validation-report.md).

## 2026-08-24

### Event shared map capability is closed offline

- The shared event entry now continues into the same typed ALAS map projection
  for A/B/SP normal maps and the reviewed C1-D3 effective-hard maps. Unrelated
  hard maps remain behind the existing 11-4 boundary.
- The projection no longer treats a legal movable event enemy as static-map
  drift. Typed sirens may leave `MS` cells only with
  `MAP_HAS_MOVABLE_ENEMY`; typed normal enemies require the independent
  `MAP_HAS_MOVABLE_NORMAL_ENEMY` capability. Boss and land placement remain
  unchanged and fail closed.
- Focused map/adapter validation passes without Android input. This is an
  offline shared-capability closure only; EventB-D and EventSp still need their
  own live map/combat/result receipts before support promotion.

### GemsFarming now has typed normal and hard main paths

- The pinned upstream `GemsFarming.run` method is executed directly in replay;
  the adapter does not replace its campaign loop, ship-change ordering,
  emotion/Lv32 handling, run-count decision, task switch, retry, or delay
  state machine.
- All six task-specific settings are validated before that method can act:
  `ChangeFlagship`, `ChangeVanguard`, `CommissionLimit`, `CommonCV`, `CommonDD`,
  and `EquipmentCode.ExportToConfig`. Replay admits all 600 legal combinations
  and rejects six representative malformed values.
- Branch replay covers defaults, every option enabled, Lv32 completion,
  flagship-only emotion handling, exhausted run count, replacement failure
  short-circuiting, and task switching. Its mutation budget is zero and it
  performs no Android input.
- Semantic mode now preserves that original loop while replacing only its
  normal Formation fleet-index read, Dock filters/candidates, and exact
  flagship/first-vanguard selection and confirmation. Candidate cards bind
  duplicate ship IDs by card bounds and carry typed name, sprite, class,
  rarity, level, emotion, fleet/status and actionable bounds. The original
  ALAS `max(...)` choice and flagship fleet-precedence rules remain unchanged.
- The normal-mode `ship_equip` branch now keeps ALAS's original
  unload/change/mount order and replaces only `ship_equipment_take_off/on`.
  Pinned ALAS equipment codes contain exactly five entries (`0/0/0/0/0` for
  the empty code), so the typed port captures and transfers only the five
  regular slots by exact ID and enhancement. Special weapons remain attached
  to the source ship. The port rejects assigned duplicate inventory cards,
  proves every mounted regular slot, and retains the pending loadout after a
  localized failure so recovery can resume.
- Live validation on the pinned API 32 x86_64 AVD selected Fleet 6, admitted
  ten eligible common carriers and one exact level-100 common destroyer, then
  confirmed Langley in `main_1` and Spence in `vanguard_1` with a two-mutation
  budget. The original Arromanches and Napoli were subsequently restored to
  those same typed roles; final generation `289388` contains the original six
  hero roots. The receipt is
  `integration/alas/gems-farming-normal-ship-live-validation-receipt-20260824-r1.json`.
- That receipt also closes two field-level omissions in the support ledger:
  `CommonCV=any` selected Langley, while `ChangeVanguard=ship` with
  `CommonDD=any` selected Spence and proved it in `vanguard_1` before restoring
  Napoli. These are live-partial values; the named CommonDD selectors are not
  inferred from them.
- A controlled Fleet 1 flagship development run initially captured all six
  visible slots. Review against pinned ALAS then corrected that overreach:
  `51000/11260/26600/1260/600`, all at `+10`, are the five equipment-code
  slots, while special weapon `12300 +10` must remain attached to South
  Dakota. A clean same-ship five-slot unload/mount round trip passed live.
- A later live attempt additionally proved `+0` equipment as an icon with no
  level Text, the occupied-slot `EquipmentInfoUI` action labels, bounded Dock
  virtual-list stabilization, and both `UICamera`/`OverlayCamera` detail-back
  paths. The implementation now replaces occupied slots individually, unloads
  target-only regular slots, admits an absent locked special slot on level-1
  ships, and avoids the surface-fleet-to-submarine wrap at Fleet 6 -> 1.
- Production-candidate non-empty `ship_equip` now has a live receipt. Opening
  Fleet 6 `main_1` records the current typed ship sprite and fleet index, so
  its Dock card is classified as `current` instead of incorrectly satisfying
  `status=free`. This preserves ALAS's same-fleet-first/fallback precedence
  while exposing the two genuinely free Ranger cards. The original
  `max(level, emotion)` decision selected the first tied free card, production
  `take_off -> replace -> take_on` transferred Ranger's existing slot 1
  `18100 +0` and slot 2 `19000 +0`, and generation `109477` read both items
  back from the target Ranger. Fleet 6 retained a Ranger flagship with the
  same loadout and the UI returned to Fleet 1 at generation `109588`. Duplicate
  Rangers expose the same typed ship ID, so hidden instance identity is not
  claimed. See
  `integration/alas/gems-farming-normal-ship-equip-live-validation-receipt-20260825-r2.json`.
- The earlier incompatible paths remain fail-closed: Fleet 1 South Dakota ->
  Ranger rejected battleship gear and Fleet 6 Arromanches -> Ranger rejected
  ship-restricted gear. The earlier Ranger -> Langley empty-code run still
  covers only the empty branch.
- A clean live qualification now covers the complete normal `1-1` path in one
  uninterrupted original `GemsFarming.run` invocation: it starts on the
  campaign page, enters chapter 1-1, sorties Fleet 6 as the exact single-fleet
  profile, completes the ordinary and boss battles, handles both result
  stacks, persists `StopCondition.RunCount` one-to-zero and
  `Scheduler.Enable=false`, and returns to the campaign page without raw-input
  fallback. The camera boundary re-proves the
  complete logical map across Unity's boss-appearance translation/perspective
  motion; non-uniform movement still fails closed when a translated hazard
  area must be preserved, and degenerate axes on a one-row map do not create
  false movement. One exact no-progress grid retry is admitted only with an
  additional combat budget unit and a completely unchanged fleet, enemy,
  ammunition, and map state. See
  `integration/alas/gems-farming-task-live-validation-receipt-20260825-r3.json`.
- Hard mode is now a live main path, but not every hard stage is compatible
  with Ranger. The 11-4 first Fleet 1 main slot exposes `label_7`, and the
  extracted game tables identify type 7 as a full carrier; Ranger 107041 is
  type 6, a light carrier. The previous empty result was therefore the correct
  structural outcome, not a broken Dock filter. The reviewed 12-1 profile has
  a type-6-compatible first main slot and retains the original ALAS
  `fleet1_all_fleet2_standby` role assignment.
- A bounded 12-1 vacancy run removed only the existing Fleet 1 flagship, then
  let the original `HardNotSatisfied -> hard_fleet_prepare()` branch own the
  replacement. The typed Dock admitted three free Rangers and original ALAS
  `max(level, emotion)` selected the level-9/emotion-119 card. The confirmed
  postcondition was ship 107041, sprite `tujizhe`, in the flagship role, after
  which both hard fleets were satisfied. See
  `integration/alas/gems-farming-hard-task-live-validation-receipt-20260825-r25.json`.
- The immediately following original task run completed the already-progressed
  12-1 Boss map, results, award close, stable campaign-page return, RunCount
  one-to-zero and scheduler disable with no raw-input fallback. See
  `integration/alas/gems-farming-hard-task-live-validation-receipt-20260825-r26.json`.
  Its historical top-level `passed=false` is a runner-classification defect:
  that version required a replacement to occur again in the completion run,
  although `run_result=true` and every task-completion postcondition passed.
  The runner now requires replacement evidence only when
  `--seed-hard-vacancy` explicitly requests that component. The two immutable
  receipts are retained rather than rewritten or consuming another unchanged
  hard attempt merely to alter the classifier bit.
- GemsFarming is therefore promoted from partial (`P`) to main-path complete
  (`L`), not full (`F`). A clean five-slot cross-ship compatibility path and
  the unexercised replacement-trigger branches for Lv32/emotion remain
  localized fail-closed gaps. A real
  `[ConnectionReset]` overlay was recovered only through its exact reviewed
  confirm target; map cells stayed blocked while the overlay was present.
  Edge-clamped camera motion retains its typed-map identity and upper-bound
  checks without imposing a post-input minimum displacement. The `extra`
  value `enhanceable` is only ALAS's candidate filter; GemsFarming has no
  separate post-replacement enhancement action to qualify.
- A later read-only account preflight cycled all six normal fleets, opened only
  the typed first-vanguard detail, and read five occupied regular equipment
  slots on every source ship. The primary guns are cruiser/large-cruiser-class
  rather than a prepared empty DD loadout, so this account has no low-risk
  empty-source shortcut for a Spence `ship_equip` run. No fleet or equipment
  mutation occurred, Fleet 1 was restored, and the exact Formation back target
  returned to the main page. The preflight receipt is
  `integration/alas/gems-farming-vanguard-equipment-preflight-20260825-r1.json`;
  it records a re-entry condition rather than promoting the unsupported branch.
- That re-entry condition has now been exercised with a reversible empty-source
  fixture. Production typed take-off captured Napoli's exact five regular slots,
  the ordinary `CommonDD=any` decision selected the sole level-100 Spence, and
  production take-on proved the empty target loadout. Cleanup then found Napoli
  by exact ship ID and sprite through a bounded typed Dock traversal and restored
  all five original slots. The fifth inventory slot required one fail-closed
  retry; no approximate item was selected. Fleet 1 and the main page were
  restored at generation `607249`. This promotes the `ship_equip` value only
  for an empty source; non-empty five-slot cross-ship compatibility remains a
  localized gap. See
  `integration/alas/gems-farming-vanguard-ship-equip-live-validation-receipt-20260825-r1.json`.
- A second reversible fixture closes the genuinely non-empty vanguard transfer.
  Game tables prove Napoli's slot-4 `1760 +10` steering gear and slot-5
  `2400 +10` repair toolkit admit Spence's type-1 destroyer. Production
  take-off captured those two slots, `CommonDD=any` again selected the sole
  level-100 Spence, and production take-on read both exact items back from
  Spence. They were then unloaded before restoring Napoli, so no equipment was
  stranded on the temporary ship; Napoli's original five slots and Fleet 1
  were restored at generation `637655`. The first target inventory traversal
  failed closed before mounting `1760`; the exact retry passed. Store reset now
  proves the upper scroll boundary instead of assuming any visible grid index
  below seven is already at the top. See
  `integration/alas/gems-farming-vanguard-ship-equip-live-validation-receipt-20260825-r2.json`.
- A zero-mutation Fleet 6 Dock preflight exercised every named CommonCV filter.
  Bogue exposed one free candidate, Hermes two, Langley none on the current
  account, and Ranger two; no candidate was confirmed and the exact Dock and
  Formation cancel targets returned to the main page. This extends live
  observation coverage without claiming action-qualified named selectors. See
  `integration/alas/gems-farming-common-cv-filter-preflight-20260825-r1.json`.
- The following CommonDD probe exposed a real atomicity defect: if Dock filter
  snapshots failed to stabilize, `CustomIndexUI(Clone)` remained open and the
  generic Dock cancellation could not own the surface. Candidate observation
  now rolls back through the unique reviewed red filter cancel and then the
  exact Dock cancel before re-raising the original classified error. A live
  occurrence returned through Formation to the main page with no ship or
  equipment mutation; named CommonDD values remain unpromoted. See
  `integration/alas/gems-farming-filter-recovery-live-validation-receipt-20260825-r1.json`.
- All four named CommonDD values now have zero-mutation live filter evidence.
  `favourite` returned an empty page. The Aulick/Foote and Cassin/Downes faction
  filters exposed the free level-100 Spence, but their exact name rules
  correctly excluded it. The Z20/Z21 filter exposed the exact two named ships,
  both level 77 with non-free `green` status, so the level-100/free admission
  contract rejected them. No ship was confirmed and Fleet 1/main were restored
  at generation `646434`. These are observation-qualified safe empty results;
  only `CommonDD=any` is action-qualified on this account. See
  `integration/alas/gems-farming-common-dd-filter-preflight-20260825-r1.json`.

## 2026-08-22

### Event/Event2/EventA-D/EventSp shared entry is closed offline

- The seven pinned event panels share nine groups and 54 base fields. EventA-D
  each add the two existing EventDaily fields, producing 386 panel-field
  instances in total. Event/Event2 dispatch wrappers are structurally
  identical, EventA-D dispatch wrappers are structurally identical, and all
  seven preserve their own config/device identity and intended original runner.
- `0420-event-shared-entry-runtime.patch` adds one task-family entry contract.
  Event folders must be exact repository-local `event_YYYYMMDD_region` names;
  direct Event stages must be safe map names; A-D admit only their own logical
  A/B/C/D stages or the pinned T/HT aliases; EventSp admits only `sp`; A-D/SP
  retain normal entry mode. The guard runs before semantic scope creation,
  A-D directory enumeration, and SP path probing.
- The existing EventDaily contract still owns StageFilter and LastStage. In
  particular, stale LastStage values are still reset at the server-day boundary
  before validation, so this phase does not reorder ALAS persistence or
  scheduling behavior.
- Deterministic replay admits 81 valid entry rows and rejects 80 malformed
  rows. The fully patched old-upstream tree contains the exact current
  `event_20260813_cn` A1-D3/SP inventory of 13 scripts; the clean pinned tree
  also proves the older A-D-to-T/HT alias family. Mutation budget is zero and
  no Android input is injected.
- The authoritative series now has 87 members. Its combined SHA-256 is
  `933bf331...43e476`; a clean pinned-upstream replay applies 141 changed files
  and compiles all 140 changed Python files. Login/frame-clock and pixel
  inventory replays pass with zero unclassified pixel accesses and no Android
  input injection. The focused suite passes 70 tests, and the full repository
  suite passes 1,413 tests with 50 warnings. Evidence is in
  `integration/alas/event-shared-entry-equivalence-20260822.json` and
  `integration/alas/event-shared-entry-patch-tree-verification-20260822/`.
- No battle was started for this structural phase. Existing live scope remains
  honest: Event and EventA stay `L`; Event2 lacks an independent instance
  receipt; EventB-D and EventSp still require their own live closures; first
  acquisition `NEW_SHIP` remains explicitly skipped until naturally triggered.

### Main/Main2/Main3 shared configuration is closed at the L boundary

- The three pinned normal-campaign panels expose the same ordered nine groups
  and 54 fields, for 162 panel-field instances. Their argument declarations,
  template values, and `AzurLaneAutoScript.main/main2/main3` dispatch wrappers
  are structurally identical after normalizing the one intentional difference,
  `Scheduler.Command`; each wrapper preserves its own config/device identity
  and forwards its own stage through `campaign_main/normal`.
- `0410-main-shared-config-runtime.patch` validates all six StopCondition
  values for `Main`, `Main2`, and `Main3` after the existing route guard and
  before switch validation, semantic scope creation, navigation, or input.
  Integers must be non-boolean and nonnegative, map achievement must be one of
  the five pinned values, and both switches must be real booleans. Event and
  other campaign families retain their prior behavior.
- Deterministic evidence admits 60 legal configuration rows and rejects 45
  malformed rows across the three instances with mutation budget zero and no
  Android input. The original ALAS stop-condition methods remain responsible
  for comparison, decrement, persistence, stage progression, and scheduling.
  Existing 192-route and 15-loop replay evidence remains authoritative.
- At the Main shared-config phase boundary the authoritative series had 86 members. Its combined SHA-256 was
  `0a730a59...81de66`; a clean pinned-upstream replay applies 140 changed files
  and compiles all 139 changed Python files. Login/frame-clock and pixel
  inventory replays pass with zero unclassified pixel accesses and no Android
  input injection. The focused suite passes 60 tests, and the full repository
  suite passes 1,408 tests with 50 warnings. Evidence is in
  `integration/alas/main-shared-config-equivalence-20260822.json` and
  `integration/alas/main-shared-config-patch-tree-verification-20260822/`.
- This closes shared configuration equivalence, not every live action branch.
  Main/Main2/Main3 therefore remain `L`: existing normal 1-1 receipts bind all
  three task entries and Main has a 12-4 official-auto-search receipt, while
  fleet lock, submarines, other fleet numbers, and broader stage/action
  combinations still need natural live coverage. `GetNewShip` remains
  explicitly skipped until a real first-acquisition trigger exists.

### Research six-field runtime contract is closed at the L boundary

- Patch member `0402-research-six-field-runtime.patch` validates the original
  ALAS selector's `PresetFilter`, `CustomFilter`, `UseCoin`, `UseCube`, and
  `UsePart` values, plus the original delay branch's `AllowDelay`, before the
  values affect selection. The contract is exact for all 26 pinned presets,
  all four resource strategies, nonempty text, and real booleans; malformed
  types or values fail closed without changing the upstream state machine.
- The offline replay covers all 26 presets, 36 resource-policy rows, both
  delay booleans, reset ordering, sufficient/insufficient resources, and
  queue-full behavior. Read-only Unity transition retries now cover the
  five-card view and delegated queue-add image without injecting input or
  weakening the final coherent snapshot requirement.
- A current live `UseCoin=only_05_hour, AllowDelay=true` run passed end to end
  and started `D-781-MI` with one exact 3000-gold confirmation. Separate
  `only_no_project` runs issued one exact 3000-gold confirmation for
  `D-737-MI` and one exact 3-cube confirmation for `H-387-MI`.
- Those latter two raw receipts remain honestly `passed=false`: each had
  already exhausted its one-shot start grant when a post-dispatch transition
  read failed. Recovery did not repeat either resource confirmation; it
  completed the pending queue-add confirmation and proved the final exact
  queue as `D-781-MI` running, then `D-737-MI` and `H-387-MI` waiting, with
  two slots free. The split proof is recorded in
  `integration/alas/research-resource-policy-recovery-20260822.json`.
- `UseCoin` now has action evidence for all four strategies. `UseCube` still
  lacks a naturally available half-hour card for `only_05_hour`; `UsePart`
  lacks qualifying cards for its two conditional strategies; preset and
  free-form filter live coverage is intentionally non-exhaustive; and the
  insufficient-resource delay branch remains account-condition dependent.
  Research therefore stays `L`, not `F`. No research-list refresh was used.
- At the Research phase boundary the authoritative series had 85 members. Its combined SHA-256 was
  `84e9b6a6...0e2c8a`; a clean pinned-upstream replay applied all 140 changed
  files and compiled all 139 changed Python files. Current login/frame-clock
  replays and the pixel inventory pass with zero unclassified pixel accesses
  and no Android input injection. The focused suite passes 681 tests and the
  full repository suite passes 1,403 tests with 50 warnings.

### Month Boss hard kill is live

- Hard 仲裁者·司特莲库斯·VIII was killed. Fleet 4 skipped on 士气过低, fleet 2
  took a real fight and DEFEAT, fleet 3 entered CombatUI and the OS grade
  page (`点击继续`) plus `AwardInfoUI` rewards. r61 then saw an empty boss
  radar in the retained room, logged `BOSS clear`, `MAP EXIT` to 核心区前哨站,
  and dock-repaired at Gibraltar for 1250.
- OS grade pages are EventTrigger surfaces, not campaign `BATTLE_STATUS_S`.
  Appear/click now use VICTORY→S / DEFEAT→D and tap 点击继续. AwardInfo is
  not a story dialogue. A retained locked room skips the mission list.
- `boss_clear` returned true. Dock repair at Gibraltar cost 1250. The
  follow-up `handle_fleet_resolve` no longer dies on a post-dock fleet-bar
  remount: `click_operation_siren_fleet_bar` retries bounded incoherent
  observer generations, then live-switched fleets 1-4 at Gibraltar.
  None needed the zone-22 cure. Evidence:
  `integration/alas/operation-siren-month-boss-hard-r61-live-20260822.json`
  and
  `integration/alas/operation-siren-fleet-resolve-r62-live-20260822.json`.
  `OpsiMonthBoss` hard kill, reward, exit, repair, and resolve check are live.
- Evidence scope remains narrower than a clean task acceptance: r61 records
  `boss_clear_results[0].returned=true`, but its overall receipt ends as
  `passed=false` / `SystemExit: 1`; r62 independently passes the post-dock
  fleet-selection check. The panel therefore remains `B` until a clean
  end-to-end rerun plus the remaining `CheckAdaptability=false`,
  `ForceRun=false`, normal-success, and non-default fleet-filter branches.
- After the matrix refresh and patch-series repair, the full repository suite
  passes `1365/1365` with 50 warnings. The authoritative 81-member combined
  patch applies cleanly to the locked `81ccf63` upstream, and the support
  matrix plus pixel-inventory hash gates pass against the rebuilt artifact.
  This closes the repository-test blocker only; it does not widen r61's live
  evidence scope or promote `OpsiMonthBoss` above `B`.

### Current upstream configuration delta is recorded

- GitHub `master` was re-read at
  `d816310324bf686dff3252b37efbb997d9a328a4`: its raw configuration surface is
  68 panels, 315 unique non-Storage fields, and 1,296 panel-field instances.
  Relative to the locked 60/278/1,217 baseline, eight panels, 37 fields, and 79
  instances were added; none were removed.
- All additions belong to EventShop or Island panels. Operation Siren remains
  16 panels, 41 unique fields, and 131 instances with zero structural delta.
  The new panels are recorded as out-of-lock/unadapted rather than folded into
  the authoritative pinned ledger. Evidence:
  `integration/alas/upstream-config-delta-20260822.json`.

### Month Boss hard: repair first, then a later fleet actually fights

- Gibraltar dock repair is live: all six HP bars 100%, repair icons false,
  agony false. Low resolve is a separate 士气过低 prompt and is not cleared
  by the dock.
- A skipped fleet sitting on the boss shadow remounts `fleet_bar` onto that
  neighbour. Skip now keys the remembered SET by the turn's fleet index, not
  the stacked HUD number. The skipped fleet is walked off the boss cell
  before the next turn. Live r57: fleet 4 took 士气过低, moved off by
  `(1, 0)`, fleet 2 entered CombatUI (`Combat preparation` / `Combat execute`).
- The OS grade page then fail-closed on `BATTLE_STATUS_S` (`combat action
  resource is not visible`) while `NewBattleResultGradePage` showed
  `点击继续` plus both `VICTORY` and `DEFEAT` assets. Kill/reward is not
  claimed. `OpsiMonthBoss` remains `B`.

### Operation Siren monthly-boss entrance is the upper compass wormhole

- The monthly-boss compass can show two white `?` icons. The upper one is the
  wormhole entrance; the right one is a buoy. Normal and hard use that same
  entrance: original ALAS walks the yellow `!` when it is still on the
  wormhole, otherwise the white `?` that belongs to `chongdong02`, never the
  nearby `fubiao3`.
- `operation_siren_radar_targets("question")` joins radar `guidepost` ids to
  `chongdong02(Clone)` even when that model is truncated in the Image slice.
  Adjacent-route crossings now join only to `taban_jinzhi`, so a buoy sitting
  next to the fleet cannot steal the wormhole click. Hard-room entry still
  uses original `go_month_boss_room`, with the stale pixel
  `radar.select(is_exclamation)` replaced by typed `task` targets.
- Live hard entry was not re-run in this turn: the qualification AVD was on
  `LoginUI2` with 您在别处登录 after the previous process died. No hard-room
  combat or reward is claimed. `OpsiMonthBoss` remains `B`.

### Month Boss fleet rotation no longer treats a neighbour's map mark as defeat

- Hard-room entry via the upper wormhole `?` is live. Fleet 4 then took a real
  D-rank. Fleets 2/3/1 were skipped while walking because a one-frame map-chibi
  `marks/damage/1` sample treated stacked neighbours as already defeated.
- Original ALAS does not inspect that map mark while walking. Skip now remembers
  only the fleet that just received the D-rank (or the exact 士气过低 prompt).
  Left portrait `agony` remains sunk/repair. Later fleets still take their turn.
  Hard kill/reward is not claimed. `OpsiMonthBoss` remains `B`.

## 2026-08-21

### Operation Siren Abyssal default path live-qualified

- The original ALAS Abyssal path consumed one real Siren coordinate and 100
  action points to enter `加勒比海A-深渊海域` at corrosion level 6. Fleet 4
  activated the exact locked guidepost, defeated the boss, and completed the
  battle/result and repeated `AwardInfoUI` reward layers.
- Victory is no longer inferred from HP. The nearest passage changes from
  `taban_jinzhi(Clone)` to `taban(Clone)`; ALAS refocuses the selected fleet,
  moves onto that exact unlocked model, confirms the irreversible Abyssal
  exit, and dismisses the exact `WorldOverviewUI` return surface.
- The live postcondition returned to Liverpool. Coins moved
  `99408 -> 115743`, beacon points `100 -> 150`, daily beacon points
  `0 -> 50`, and the standard dock repair path repaired 725 coins of damage
  before positively returning to `WorldPortUI`.
- Long boss effects now keep a committed Operation Siren combat alive across
  bounded stale/coherence gaps. Reward closes no longer require an unrelated
  mission owner, and dock repair tolerates the reviewed `UIMain -> UIOrigin`
  remount plus a swallowed first back click.
- Patch member `0100-operation-siren-abyssal-runtime.patch` carries the
  upstream runtime delta. Live evidence is recorded in
  `integration/alas/operation-siren-abyssal-live-qualification-20260821.json`.
  The default main path is `L`; optional pre-entry `UseLogger` consumption and
  every free-form fleet-filter permutation remain conditional.

## 2026-08-20

### Operation Siren Stronghold main path live-qualified

- The globe observer now identifies a Stronghold from the exact selected-zone
  title, `塞壬要塞` type, and reviewed Stronghold sprite set. It does not use
  the legacy 3D red-vortex HSV search, screenshots, OCR, or framebuffer data.
  The live globe found `NA海域西北C` (zone 93) and `东大陆架A` (zone 121).
- Zone 93 completed the original ALAS Stronghold path: globe focus and unpin,
  entry, recon order, official auto-search, the exact paired start/no-event
  notifications, submarine-return confirmation, fleet selection, and combat.
  Exact suppression progress moved `100 -> 20 -> 0%`.
- Zone 121 then completed the second live path. The globe focus now anchors
  from the exact `SVFloatPanel/.../point` position and uses a bounded 8-pixel
  local probe, including the dense East Continental Shelf E boundary between
  Liverpool and Brest. Adjacent-zone titles are rejected rather than accepted
  as the requested zone. The exact `东大陆架A-塞壬要塞海域` title reached `0%`;
  the zero-percent precheck ended fleet rotation, returned to Liverpool,
  repaired the post-combat damage for 750 coins, and verified fleets 1-4 were
  all free of low resolve.
- Fleet availability is now two independent states. The selected map chibi's
  `fleet_N/marks/damage/1` image (`name=1`, `sprite=200`) is low resolve. Left
  portrait `agony` controls mean a sunk ship needs port overhaul. Fleet 4's
  repair state short-circuited the chibi check and was skipped; healthy Fleet
  2 completed the remaining Stronghold combat.
- A bounded startup lease lets a newly started Operation Siren task recover an
  already-running auto-search transition until an exact local-map or globe
  hierarchy reappears. Unrelated tasks do not inherit the lease. The obsolete
  source-only Stronghold skip was removed from the authoritative 48-member
  patch series; member 0098 contains the upstream runtime delta.
- An accepted exact auto-search click now has two normal outcomes. Searchable
  events move the switch to `on` or enter combat; an empty map emits the paired
  start/no-event notices, or settles back to `off` after a bounded debounce,
  and ends the map search normally. Stable `off` is no longer reported as an
  enable failure, while the transition lease still suppresses duplicate clicks.
- Retained order panels are closed by the exact typed back target, including a
  bounded retry when Unity remounts the panel from `LevelCamera` to
  `OverlayCamera`. Port startup question clearing now reads exact radar targets
  and returns empty without invoking the legacy radar pixel mask. Active combat
  frames no longer call the local-map auto-search switch reader.
- Evidence is recorded in
  `integration/alas/operation-siren-live-qualification-20260820.json`.
  The 48-member combined patch was separately applied and compiled on a clean
  `81ccf63b` worktree; the ALAS-focused suite passed `715/715`, followed by a
  `26/26` focused rerun after verifier updates. Login/frame-clock replay and
  the pixel inventory report zero unclassified pixel accesses; the inventory's
  one classified access remains the pre-existing denied defensive branch, not
  an Operation Siren runtime path.
  OpsiStronghold is promoted to `L`, not `F`: the default main path is live,
  while both ForceRun values and the full free-form fleet-filter space have
  not each received independent live coverage.

### Operation Siren Month Boss failure semantics corrected

- Month Boss no longer equates low resolve with the left portrait `agony`
  control or with zero HP. A timeout/flagship-loss defeat can retain HP and is
  read from the exact selected-chibi damage marker; a sunk ship is separately
  classified as requiring port repair.
- Inside a non-retreatable Boss room, either state makes that fleet
  unavailable. The original fleet order rotates without issuing another boss
  movement to the defeated fleet. If every configured fleet is exhausted, the
  client return is challenge failure rather than victory; a retained room is
  left before port repair and low-resolve recovery begin.
- A normal safe-zone victory was live-observed clearing low resolve. Successful
  Month Boss settlement and hard difficulty remain unproven, so Month Boss is
  still evidence-scoped partial support.

### Exercise full semantic flow live-qualified

- Patch member `0380-exercise-full-flow-port.patch` completes typed opponent
  inspection, separate execute/refresh grants, S/D settlement, official
  low-HP quit and retry/refresh recovery. The authoritative series now has 45
  members and applies cleanly to pinned upstream `81ccf63b`.
- Original ALAS runs passed `easiest` (`7 -> 6`), `max_exp` (`6 -> 5`), a
  forced low-HP quit (`2 -> 2`), and an `easiest_else_exp` refresh/retry that
  exited, refreshed all four rivals, then won (`4 -> 3`). No raw-input
  fallback was admitted and all action grants closed exactly.
- All seven declared Exercise fields are now consumed and fail-closed. Four
  opponent modes are implemented; only natural live samples for non-aggressive
  clock windows and `OpponentTrial > 1` remain qualification gaps.

### Hard 11-4 official auto-search live-qualified

- The restored 9.7.328 duty tab is read from fresh immutable frames and its
  selected postcondition is awaited before role rows are consumed. A live API
  32 x86_64 run proved both required fleets, exact `all/standby` duties, and a
  100% stage before the one authorized sortie.
- After sortie, ALAS issued no map, combat, or viewport input. The observer
  proved the official `CombatUIStandard` auto-battle state, then accepted only
  the exact 11-4 total-reward `ButtonExit`; the successful run waited 45.922
  seconds and used no raw-input fallback.
- A transient `LevelGrid` between sortie and the official auto-search roots no
  longer downgrades into manual-map confirmation. Hard multi-run continuation
  now consumes a separate sortie lease at the exact total-reward Continue
  control before resetting the process-local proof context.
- Evidence is recorded in
  `integration/alas/hard-11-4-auto-search-live-validation-receipt.json`.
  Qualification remains limited to 11-4 with HardFleet=1. The official Hard
  contract is fleet 1 `all`, fleet 2 `standby`; it does not claim that both
  fleets fight. HardFleet=2 and other Hard stages remain fail-closed.

## 2026-08-19

### Hard 11-4 manual-map clear reached 100%

- Three live API 32 x86_64 Hard 11-4 runs advanced the stage to an exact typed
  `100%`. Fleet 1 cleared all six mob battles, including the last at zero ammo;
  fleet 2 retained `5/5` ammo and defeated the boss at A8. Every combat used
  the game's official auto-battle control.
- The bounded semantic path covered map projection and recovery, fleet-role
  preservation, a random ambush evade, an urgent-commission popup, partial
  routes, and battle-status/item/experience result pages. The two retained
  success receipts report no raw-input fallback.
- Official map auto-search is now admitted only when the exact stage progress
  is greater than 95%; an ordinary map root no longer counts as proof that the
  official auto-search started. The stage reached 100% only after consuming
  today's third and final Hard attempt, so the end-to-end official map-auto run
  remains pending the next daily reset.
- Support is intentionally limited to 11-4 with HardFleet=1 and the exact
  fleet-1-mob/fleet-2-boss role split. HardFleet=2 remains rejected because the
  current client has removed DutySelect, and no other Hard stage is inferred.
  Patch member `0370-hard-11-4-semantic-clear-port.patch` raises Hard from `B`
  to `L`; live evidence is in the two `hard-11-4-*-receipt.json` files.

### Guild ordinary-member main path

- The API 32 x86_64 CN client completed the ordinary-member Guild path with
  exact typed navigation across lobby, logistics, and operations. The lobby
  report store was claimed from `20/20`; logistics supply changed from `1/3`
  to `0/3`; the already-finished `100/100` weekly mission was correctly
  treated as non-claimable; and all three daily exchanges followed the
  configured priority (`Coolant`, `Merit`, then `PlateTorpedoT3`) before the
  observer proved zero remaining and all submit controls disabled.
- Operation node `7-1` opened its exact dispatch detail and formation pages.
  Official recommendation filled four empty slots, effect became 158, and one
  independently budgeted `guild.dispatch` confirmation changed participation
  from `1/33` to `2/33`, total effect from 246 to 494, and the action control
  from `formationBtn` to `doing_btn`.
- Patch member `0360-guild-flow-port.patch` retains `RewardGuild.run()`'s
  lobby-to-logistics-to-operations order and replaces Guild pixel mechanics
  with typed state and action boundaries. `guild.claim`, `guild.exchange`, and
  `guild.dispatch` have separate integer grants. New-mission selection,
  join-threshold behavior, officer-only new-operation creation, and Boss combat
  remain fail-closed until their corresponding live states are available.
- Guild is promoted from `O` to `L`, not `F`. The authoritative series now has
  43 members and applies cleanly to pinned upstream. Live evidence is recorded
  in `integration/alas/guild-main-path-live-validation-receipt.json`.

## 2026-08-18

### Main 12-4 official auto-search

- `Main` now supports one bounded normal 12-4 official auto-search run with
  fleet 1 and fleet 2 selected, submarines disabled, and either
  `fleet1_mob_fleet2_boss` or `fleet1_boss_fleet2_mob`. Both role orders are
  exact typed contracts; the first order completed a live API 32 x86_64 run,
  while the reversed order is covered by the same fail-closed adapter path and
  an explicit deterministic test.
- ALAS owns chapter navigation, fleet selection, duty-role selection, sortie,
  and final acceptance. After sortie, the official game owns all map movement
  and combat. The live run used zero campaign-combat and viewport-swipe budget,
  repeatedly proved the official combat `AutoBtn` checked, waited 519 seconds,
  accepted only the exact 12-4 total-reward panel, decremented RunCount to zero,
  disabled the Scheduler task, and used no raw-input fallback. Evidence is in
  `integration/alas/main-12-4-auto-search-live-validation-receipt.json`.
- The authoritative series now has 41 members; member 0340 contains the five
  narrow upstream ALAS hooks for role selection, official-auto admission,
  passive completion, and result hand-off. This does not promote auto-search
  for other stages, events, tasks, fleet numbers, fleet lock, submarines, or
  2x-book use.

### Main 1-1 through 16-4 route admission

- Main, Main2, and Main3 now share a fail-closed normal-campaign route
  contract for all 64 pinned upstream modules from 1-1 through 16-4. The
  verifier executes all 192 task/stage combinations through the original
  ALAS `CampaignRun.handle_stage_name()` on both the patched and pristine
  pinned trees; eight malformed, out-of-range, event, and mode cases are
  rejected with zero Android input.
- `CampaignRun.run()` enforces the task, stage, event, and mode contract before
  campaign switch validation, semantic pre-sortie scope, navigation, or any
  input. Main-family tasks accept only `campaign_main` plus `normal`; hard mode
  remains owned by the separate Hard task, while non-Main campaign families
  retain their existing routing behavior.
- The only attached device is currently MuMu running EN package
  `com.YoStarEN.AzurLane` 9.3.6. It does not match the pinned CN package and
  fingerprint, and no compatible semantic observer is available, so it was
  not used as evidence and no account-changing input was sent. Main retains
  its prior 12-4 live result; Main2/Main3 remain offline-only `P`.
- The authoritative 41-member patch applies to pristine pinned upstream and
  all 128 changed Python files compile. The complete repository suite passes
  1,139/1,139 with 50 upstream deprecation/syntax warnings; support-matrix,
  baseline, pixel-inventory, and combined-patch hashes are synchronized.

### Main task instances and bounded RunCount replay

- The pinned ALAS `CampaignRun._run()` now executes in an input-free replay
  for each independent `Main`, `Main2`, and `Main3` configuration instance.
  Every instance is bound to its own Scheduler command and to the declared
  `campaign_main` normal route instead of inheriting Main by assertion.
- Each task covers one run, two runs, a persisted one-run remainder, an
  interrupted pre-success run, and a bounded unlimited-count run. Across 15
  scenarios, ALAS decrements only after `campaign.run()` returns, disables the
  task exactly at zero, preserves the remainder after `ScriptEnd`, and leaves
  unlimited count unchanged. Mutation budget and Android input remain zero.
- Main remains `L` from its existing 12-4 live path. Main2 and Main3 remain
  `P` because independent live task startup and map completion are still not
  proven; offline instance coverage is not promoted to live evidence.

### Tactical experience-overflow configuration complete on the live client

- Three completed courses were claimed with no new assignment budget. Little
  Renown's level-9 `小骑士的射击训练` then exposed the exact live boundary
  `5750/5800` against an 11-book inventory spanning T1 through T4.
- With overflow disabled and all limits zero, original
  `_tactical_books_filter_exp()` removed nine books and retained only the two
  mandatory base 100-exp T1 books. The probe stopped before selection, left
  the assignment grant at one, consumed no book, and restored main.
- With overflow enabled at T1/T2/T3/T4 limits `100/250/750/1450`, the same
  method admitted the 150/300/800/1500-exp tier boundaries. Original ALAS then
  selected `Blue_T4`, issued exactly one typed `tactical/course/confirm`,
  exhausted the grant, scheduled the task, and left the same skill on a
  running card with roughly 12 hours remaining.
- The first full receipt is intentionally retained as `passed=false`: the
  course succeeded, but the validator initially treated the `first` preset as
  a book lacking a semantic position. The runner now resolves `first` to the
  first filtered book, and a separate zero-mutation postcondition receipt
  binds the successful dispatch to the running physical skill card. Evidence:
  `integration/alas/tactical-overflow-strict-live-validation-receipt.json`,
  `integration/alas/tactical-overflow-live-validation-receipt.json`, and
  `integration/alas/tactical-overflow-postcondition-live-validation-receipt.json`.
- All five `ControlExpOverflow` fields are therefore complete. Tactical stays
  `L` only because rapid training is a limited-time activity unavailable on
  the current client.

### Research, Mail, and Observer WIP split and evidence boundary

- Research now has four independent upstream patch members for selected-detail
  entry, queue entry, code-bound card selection, and atomic exact-cost start.
  Seven successful resource-policy receipts are retained only as historical
  stage evidence because their source hashes predate this closure; no Research
  field is promoted from those receipts.
- A new 2026-08-18 current-account requalification then exercised the split
  flow against the current adapter. It closed the typed queue-capacity handoff,
  exact component-family prompt mapping, and duplicate-code selection by
  binding the upstream-selected 0-based position to a fresh matching code.
  Bounded starts consumed exactly 8,000 coins, three cubes, and 20 torpedo T1
  parts across two coin, one cube, and one part projects. Three `do_not_use`
  runs consumed no resources and retained their start grants.
- The final source-bound run used `AllowDelay=true`, observed the original
  no-match and enforced-fallback decisions, safely selected one of two
  `C-153-MI` cards by position, started one resource-free project, and restored
  scheduling. It does not prove the insufficient-resource delay decision.
  The five-slot queue is now full until its first project completes around
  2026-08-19 01:44 local time, so the earlier resource receipts remain stage
  evidence after the later duplicate-code fix; Research stays `L`.
- The Mail qualifier declares exact maintenance, merit, and trade-license
  configurations and grants. Existing maintenance and merit attempts failed
  their mail-count postcondition, so the negative receipts remain local
  artifacts and Mail support is unchanged.
- Daily, Tactical, and Research observer fixes remain typed and fail closed.
  They add no pixel fallback and grant no new production authority. See
  [the WIP closure record](alas-wip-closure-20260818.md).
- The 40-member patch applies cleanly to pinned ALAS `81ccf63`; the
  zero-mutation configuration attack matrix passes, focused integrity tests
  pass 41/41, and the full repository suite passes 1,135/1,135 with 49
  warnings.

## 2026-08-17

### Tactical: book filter complete on the live client

- The original Tactical task loaded `BlueT1 > RedT1 > YellowT1 > BlueT2 >
  RedT2 > YellowT2 > first`, sorted a real 11-book inventory, and selected
  `Blue_T1` at position 9. It then issued exactly one typed
  `tactical/course/confirm` input; its grant reached zero and slot 4 remained
  running for ship `102011` with skill `快速装填`. The source-hash-bound receipt
  is `integration/alas/tactical-filter-r1-live-validation-receipt.json`.
- Original-state-machine replay already covers matching priorities, `first`
  fallback, no-match cancellation, Unicode normalization, and malformed rules.
  `Tactical.TacticalFilter` is therefore complete; `RapidTrainingSlot` remains
  separately blocked by the current non-event period.
- A 2026-08-19 recovery run also claimed one completed course, accepted both
  exact official continue-prompt wordings and the `ConnectionReset` reconnect
  code, then filled the fourth slot through original ALAS.  A second zero-budget
  run began and ended with four identical running slots and never entered Dock;
  see `integration/alas/tactical-empty-slot-fill-r4-live-validation-receipt.json`
  and `integration/alas/tactical-full-slot-r5-live-validation-receipt.json`.

### Dorm: feed switch and priority filter complete on the live client

- `Dorm.Feed` is now complete for both booleans.  The enabled original-ALAS
  task consumed exactly the dynamically planned typed food card(s), exhausted
  its granted input budget, observed the matching inventory delta, and restored
  the main page.  The complementary disabled task returned success with zero
  feed dispatches and the same cleanup.  The source-hash-bound receipts are
  `integration/alas/dorm-feed-r10-live-validation-receipt.json` and
  `integration/alas/dorm-feed-r11-disabled-live-validation-receipt.json`.
- `Dorm.FeedFilter` is also complete: all 1,956 nonempty unique orderings of
  the six declared food values remain covered by the original-state-machine
  replay, while the live client passed both the default priority list and the
  single UI value `"1000"`.  The latter is important because original
  ConfigUpdater canonicalizes that textarea value to an integer before
  `RewardDorm.run()`; the adapter accepts only the six exact legal integer
  singletons on that compatibility path.  Its real task clicked only
  `dorm/feed/item/50001`, changed inventory `17863 -> 17862`, and returned to
  main; see `integration/alas/dorm-feed-r13-filter-1000-live-validation-receipt.json`.
- A fresh 2026-08-19 single-value `"20000"` run covered the complementary
  no-stock branch.  The account had `0/40000` food capacity available but zero
  20000-value items; original ALAS entered and exited Feed with no typed food
  dispatch, preserved every inventory count and restored main.  See
  `integration/alas/dorm-feed-r14-filter-20000-no-stock-live-validation-receipt.json`.
  One 20000-value item is still required for the consuming live postcondition.
  `Dorm.Collect` is now complete as well: when the current account exposed a
  real collectable dorm reward, the original task issued exactly one typed
  `dorm.collect`, exhausted its grant, changed the quick-collect control from
  available to absent, preserved all six dorm slots, and returned to main; see
  `integration/alas/dorm-collect-live-validation-receipt.json`.

### Reward: daily-mission claim switch complete on the live client

- `Reward.CollectMission=true` now has a fresh original-ALAS daily task pass
  with the other four Reward claim switches disabled.  It issued exactly one
  typed `task/claim/all` `mission.claim`, exhausted its grant, and returned to
  the typed main page.  The complementary false invocation ran the original
  Reward task with all claims disabled, emitted no mutation dispatch, returned
  to the main page, and removed its temporary configuration.  Both hash-bound
  receipts are recorded in `integration/alas/reward-daily-mission-r2-live-validation-receipt.json`
  and `integration/alas/reward-daily-mission-disabled-live-validation-receipt.json`.
  `Reward.CollectMission` is complete; independent resource-switch
  qualification is recorded below.

### Reward: weekly-mission claim switch complete on the live client

- The prior original-ALAS `Reward.CollectWeeklyMission=true` run used exactly
  one typed `task/weekly-progress/claim`, exhausted its grant, and returned to
  the main page.  The new current-code `false` run entered and exited the
  original Reward task without any `mission.claim` dispatch, resource change,
  or retained temporary configuration.  The paired receipts are
  `integration/alas/reward-weekly-mission-live-validation-receipt.json` and
  `integration/alas/reward-weekly-mission-disabled-r1-live-validation-receipt.json`.
  `Reward.CollectWeeklyMission` is complete independently of daily missions
  and resource-collection switches.

### Reward: Oil, Coin, and Exp resource switches complete on the live client

- Resource bubbles are now admitted only with an exact positive typed amount,
  not merely because their card is clickable.  The original `Reward.run()`
  with Oil alone changed `32 -> 0` through exactly one typed
  `reward/resource/oil` input; Coin alone changed `108 -> 0` through exactly
  one typed `reward/resource/coin` input; Exp alone changed `8 -> 0` through
  exactly one typed `reward/resource/exp` input. The Exp-disabled task made no
  resource input and restored the main page. See
  `integration/alas/reward-oil-live-validation-receipt.json`,
  `integration/alas/reward-coin-live-validation-receipt.json`, and
  `integration/alas/reward-resource-disabled-live-validation-receipt.json`,
  `integration/alas/reward-exp-live-validation-receipt.json`, and
  `integration/alas/reward-exp-disabled-live-validation-receipt.json`.

### Gacha: all declared Amount values complete on the live client

- Light-pool `Gacha.Amount=1..10` has now passed one real original-ALAS task
  per declared value with `UseTicket=false` and `UseDrill=true`.  Every run
  began and ended on a typed empty queue, returned `true`, and consumed exactly
  `N` cubes, `600*N` coins, and `N` quick-finish tools.  The Amount=10 run
  returned true after `995.235` seconds (`3571 -> 3561` cubes, `48199 ->
  42199` coins, `2595 -> 2585` tools) and exercised the real four-slot
  finished-state recovery before closing all reward cards.  The hash-bound
  source receipts and their per-value summaries are in
  `integration/alas/gacha-light-amounts-1-10-live-validation-receipt.json`.
  `Gacha.Amount` is therefore complete for every declared value; this does not
  promote the separately unqualified event-ticket surface.

### Gacha: all declared Pool values complete on the live client

- The original ALAS task now has a resource-receipted execution for every
  configured `Gacha.Pool` value.  Existing Light, Event, and Special runs are
  joined by a new Heavy run that consumed exactly 2 cubes, 1500 coins, and one
  quick-finish item before returning to an empty queue.  On the current client
  the Wishing Well fifth entry is unavailable; with `Pool=wishing_well`, the
  original `gacha_goto_pool()` returned `light`, then consumed exactly one
  Light order (1 cube, 600 coins, and one quick-finish item) and returned to an
  empty queue.  This is the original current-state fallback, not a claim that
  a configured seasonal Wishing Well was automated.  See
  `docs/gacha-pool-live-validation-report.md` and its five linked receipts.

## 2026-08-16

### Gacha: real two-order pools and semantic queue-finish recovery

- The original ALAS `Gacha` task submitted two Event orders from an empty
  queue.  Cubes changed from `3672` to `3668`, coins from `107499` to
  `104499`, and the resulting typed queue timers were `01:29:55` and
  `01:59:55`.  It then submitted two Special orders from an empty queue with
  the same exact `4`-cube/`3000`-coin delta and two typed timers.  The
  receipts are `integration/alas/gacha-event-two-live-validation-receipt.json`
  and `integration/alas/gacha-special-two-live-validation-receipt.json`.
- A later default Light run retried only complete read-only snapshots while
  the Unity pool, confirmation, and queue views settled.  The original task
  returned success and changed cubes from `3664` to `3663`, coins from
  `103999` to `103399`, and the empty queue to one `00:27:39` timer; see
  `integration/alas/gacha-light-daily-seed-validation-receipt.json`.
- The semantic queue implementation now proves the batch-finish button, the
  exact Chinese quick-finish confirmation and owned-tool count, the NewShip
  result, and AwardInfo close.  A real recovery consumed one quick-finish
  tool, closed all three pages, and proved the queue empty; see
  `integration/alas/gacha-light-drill-recovery-live-validation-receipt.json`.
- The native `UseDrill=true` Light task now completed under the original ALAS
  state machine: it returned true after `890.078` seconds, reduced cubes by
  `1`, coins by `600`, and quick-finish tools by `1`, closed both NewShip and
  AwardInfo, and ended with an empty typed queue.  The session layer delegates
  build-owned result aliases before generic reward handling; see
  `integration/alas/gacha-light-drill-task-r7-live-validation-receipt.json`.
  `Gacha.UseDrill` is therefore complete for both boolean values.  Event ticket
  inventory was absent, so `UseTicket` still has no positive ticket-consumption
  evidence.  The current unavailable Wishing Well fallback is qualified
  separately above.

### Restart: real cold recovery and Scheduler durable state

- The original scheduler was run with all 50 declared Scheduler instances and
  their 15 declared interval/server-update equivalence classes.  Every instance
  used the original `AzurLaneConfig` queue and persistence paths for command
  identity plus success, failure, and server-update `NextRun` writes.  A normal
  disabled task (`Main.Enable=false`) was not queued; `Restart.Enable` itself
  is an upstream locked `state` field and only admits true.
- A focused patch makes scheduled `Restart` skip only the pre-restart first
  screenshot, so a stopped game can reach `LoginHandler.app_restart()`.  On a
  semantic device the same handler delegates cold startup to the session-owned
  `-force-gfx-st` launcher; the ordinary device stop/start path remains
  unchanged.
- On `emulator-5580`, a disabled-package execution failed with exit code 1 and
  no leaked observer forwards; re-enabling then recovered from no PID to PID
  `25778` and logged in.  A second run turned PID `25778` into `27548`, logged
  in, persisted next server update, and left zero forwards.  The first service
  startup was also verified to take the exact server-update skip path without
  an app restart.  The receipt and bounded reproducer are in
  `integration/alas/restart-live-validation-receipt.json` and
  `scripts/python/run_alas_restart_live_validation.py`.
- The disabled-package root `ObserverTransportError` is present in the ALAS
  log, but this workspace lacks optional `onepush` and upstream notification
  handling then exposes `ModuleNotFoundError`.  That notification masking is
  an `Alas.Error/OnePushConfig` limitation, not a false Restart success; it
  remains outside this Restart promotion.

## 2026-08-15

### Guild: nine settings gated before task ownership

- The six Guild switches, monthly start-date limit, `0..1` join threshold, and
  text exchange filter now form one immutable, fail-closed snapshot before the
  Guild task, direct logistics consumers, and direct operation consumers take
  state, observe a page, or reach an input branch.
- Recorder-only replay retains the original no-enabled-module stop, logistics
  only, operations only, and combined task dispatch/order. Invalid values emit
  no recorder event. This run has mutation budget `0` and makes no device,
  account, guild, resource, task, or Android-input change.
- Page availability, OCR, mission selection, exchange candidates/currency,
  operation progress, dispatch, Boss battle, postconditions, and real input
  remain unadapted; this is offline-only evidence.

### PrivateQuarters: four settings replayed before UI or currency work

- `PrivateQuarters.BuyRoses`/`BuyCake`/`TargetInteract` now accept only exact
  booleans, while `TargetShip` accepts exactly the seven declared ship ids.
  The task, shop-filter, and item-eligibility consumers all take one strict
  snapshot before UI navigation, filter construction, currency comparison, or
  an interaction can be reached.
- Recorder-only replay executes all 56 declared four-field combinations through
  the original task forwarding. It retains the original four gift filters and
  the rose-coin and cake-gem boundary decisions; malformed values stop with no
  recorder events. There is no device, account, currency, target interaction,
  task mutation, or Android input.
- This is offline-only evidence for all four fields. Private Quarters page
  availability, item OCR, currency observations, shopping, daily-count
  observation, ship lookup, interactions, postconditions, and all input remain
  unadapted.

### Coalition/CoalitionSp: shared enums replayed before any task state

- `Coalition.Mode` now accepts exactly `easy`/`normal`/`hard`/`sp`,
  and `Coalition.Fleet` exactly `single`/`multi`, before Coalition run,
  per-run overrides, or combat preparation. Invalid values stop before stage
  normalization, task state, stateful overrides, observation, or device input.
- Recorder-only source replays preserve the original single-fleet emotion
  override, SP forced-multi override, and the second-combat emotion decision
  for both fleet values. The final map entry and combat calls are in-memory
  recorders, not Android input.
- This is offline-only evidence for the two shared settings. Coalition
  availability, navigation, battle execution, rewards, postconditions,
  observation, and all Android input remain unadapted.

### Raid/RaidDaily: current Raid four-mode live path with localized qualification gaps

- `Raid.Mode` admits only the four declared difficulties and `Raid.UseTicket`
  only real booleans before `RaidRun` work begins. The ticket-confirmation
  replay runs both original confirm/cancel branches with their two final-input
  boundaries replaced by a recorder; malformed values stop before observation
  or device input.
- `RaidDaily.StageFilter` canonicalizes separators and whitespace, rejects
  duplicate/unknown/empty stages, and replays every one of the 64 non-repeating
  ordered subsets of `easy`/`normal`/`hard`/`ex`. The normal forwarding and
  EX reward-routing decisions execute only in memory; invalid filters stop
  before any RaidDaily stateful boundary.
- The pinned `raid_20260212` daily counter now reads the exact typed
  `BossRushVerSardiniaSPUI/Battle/Nodes/5001..5004` surface for
  `easy`/`normal`/`hard`/`ex`. Non-EX values must be a unique `n/15` counter;
  EX uses its exact `times/Text` path. Unknown events, roots, duplicate values,
  stale generations, and malformed counters fail closed. The original
  `RaidDaily.run()` loop owns filtering, retries, execution, and scheduling;
  pixel mode is unchanged, while semantic mode does not enter the still
  unsupported optional Raid reward-dot branch.
- The current CN `raid_20260827` surface is independently typed from the pinned
  baseline: `ActivityBossAmatsukazeUI(Clone)` must expose exactly the reviewed
  easy/normal/hard/EX slots plus the distinct advanced-challenge slot. Remaining
  attempts and PT are exact text reads; swapping EX with the advanced challenge,
  duplicate counters, stale frames, blockers, or incomplete fleet/precombat
  state fail closed at the affected Raid action.
- The original ALAS `RaidRun` state machine now owns the current semantic flow:
  main-to-Raid entry, difficulty selection, fleet recommendation/readiness,
  precombat entry, the optional first-time informational notice, one bounded
  re-entry after that notice, true sortie, battle result cleanup, and return to
  the Raid page. Only the true precombat start consumes the sortie grant.
- Four controlled one-battle runs completed through the original ALAS task with
  no raw-input fallback. The authoritative receipts record `easy` `14→13` and
  PT `30→60`, `normal` `15→14` and PT `60→130`, `hard` `15→14` and PT
  `130→250`, and `ex` ticket `1→0` and PT `250→562`:
  `integration/alas/current-raid-easy-live-validation-receipt-20260827-r10.json`,
  `integration/alas/current-raid-normal-live-validation-receipt-20260829-r8.json`,
  `integration/alas/current-raid-hard-live-validation-receipt-20260829-r2.json`,
  and `integration/alas/current-raid-ex-live-validation-receipt-20260829-r6.json`.
- The 2026-08-29 resource update kept APK `9.7.10` and advanced the live hot
  resource version to `9.7.343`. It exposed three additive compatibility gaps:
  a non-EX counter disappears when it reaches zero, the Raid cards animate
  briefly after a result, and an off-page precombat probe could observe an
  independently advancing UI generation. The adapter now accepts a hidden
  zero only after two coherent generations prove the other counters and exact
  page health, passively waits through the result mount window, and reads the
  full precombat projection only after its exact start candidate exists.
- The original `RaidDaily` task also completed a controlled zero-ticket branch
  on hot version `9.7.343`: `StageFilter=ex`, all five Reward collection flags
  disabled, and fleet-mutation/sortie/combat budgets all zero. EX remained
  `0→0`, PT remained `592`, no stage/fleet/sortie receipt was emitted, the task
  returned to the Raid page, and ALAS scheduled the next server-update run.
  `integration/alas/current-raid-daily-empty-ex-live-validation-receipt-20260829-r1.json`
  is the authoritative limited-live receipt.
- After the 2026-08-30 reset, the original task cleared the last four `easy`
  attempts and moved PT `1112→1232` with exactly four stage/fleet/sortie
  sequences and no raw fallback. That first receipt remains deliberately
  failed because the then-unmapped hidden-zero post-read terminated after the
  useful game work. A fresh run with `easy=0` subsequently passed: no battle
  input, no PT change, exact Raid-page return, and natural next-day scheduling.
  The authoritative post-fix receipt is
  `integration/alas/current-raid-daily-easy-zero-state-live-validation-receipt-20260830-r1.json`;
  the failed diagnostic is retained as
  `integration/alas/current-raid-daily-easy-full-clear-live-validation-receipt-20260830-r1.json`.
- Reward-enabled EX is now closed across an honestly segmented recovery chain.
  The first run dispatched exactly one original mission claim and exposed three
  EX tickets, then failed on the returning TaskScene identity before any EX
  input. A deliberately interrupted first EX battle was reattached through the
  original `Combat.combat_execute()` path; five typed result/reward receipts
  drained its orphan result and left EX `2`, PT `1544`. The final passing run
  consumed those two tickets in one `RaidDaily` instance, moved EX `2→0` and PT
  `1544→2168`, and emitted exactly two stage/fleet/sortie sequences. The honest
  r1/r3 failures and r4 pass are kept separately instead of being presented as
  one uninterrupted pass:
  `integration/alas/current-raid-daily-reward-ex-live-validation-receipt-20260830-r1.json`,
  `integration/alas/current-raid-daily-reward-ex-live-validation-receipt-20260830-r3.json`,
  and `integration/alas/current-raid-daily-reward-ex-live-validation-receipt-20260830-r4.json`.
- A final combined-filter run used `StageFilter="easy > normal"` with `easy=0`
  and `normal=14`. The same original task instance skipped easy without input,
  completed all fourteen normal battles, moved normal `14→0` and PT
  `2168→3148`, emitted exactly fourteen stage/fleet/sortie sequences, used no
  reward or recovery path, and scheduled `RaidDaily` for the next server day.
  `integration/alas/current-raid-daily-easy-normal-full-clear-live-validation-receipt-20260830-r2.json`
  is the authoritative pass.
- A fresh original `Restart` scheduler task then cold-started the game with the
  mandatory `-force-gfx-st` contract, turned PID `5252→7648`, completed the
  typed login to main, scheduled itself for the next server day, and left no
  new ADB forward. The verified `restart-warm` capture contains 1,829 trace
  records and no in-game resource capability:
  `integration/alas/current-raid-restart-warm-workload-20260830-r1`.
  Immediately afterward, `StageFilter="easy > normal"` re-entered the current
  Raid on PID `7648`, read both cleared stages as zero, kept PT at `3148`,
  emitted no stage/fleet/sortie/mission receipt, used no raw fallback, and
  scheduled `RaidDaily` again. The post-restart pass is
  `integration/alas/current-raid-daily-post-restart-zero-state-live-validation-receipt-20260830-r1.json`.
- The upstream `RaidDaily` configuration locks `StopCondition.RunCount` to
  zero, so the integration no longer propagates a pseudo single-battle limit;
  bounded validation budgets stay in the evidence runner rather than changing
  the task state machine. On current `raid_20260827`, `Raid.UseTicket=false` is
  live-qualified. The original Raid state machine now also admits
  `Raid.UseTicket=true` through one narrow zero-ticket compatibility branch: it
  opens the exact multiple-sortie panel, requires count `1`, ticket `0/0`, and
  the unique disabled-ticket marker, closes the panel, then falls back to one
  ordinary sortie. Positive ticket selection, toggle, and final commit remain
  localized fail-closed actions rather than being guessed.
- A zero-sortie-budget live probe now maps the update's exact
  `ActivityBossPrecombatUI(Clone)/adapt/right/multiple` entry and
  `ContinuousOperationWindowUI(Clone)/window/top/btnBack` close action. The
  panel proved default count `1`, hard bonus count `14`, estimated oil `25`,
  and ticket inventory `0/0`; its ticket checkbox was disabled with
  `checkmark_ban`. Six typed navigation inputs opened the hard precombat page,
  opened and closed this panel, and returned through fleet selection to Raid.
  Hard remained `14/15`, PT remained `3148`, and the sortie grant stayed zero.
  The zero-ticket fallback is covered by focused parser/adapter tests, fresh
  patched-tree compilation, login/frame-clock replays, and a pixel-boundary
  verifier with zero unclassified access or Android input. Its end-to-end live
  execution still awaits the next attempt reset because all ordinary attempts
  are currently zero. Positive count selection, ticket toggle, and the panel's
  battle commit remain closed.
- The distinct fifth slot now has an exact `raid/advanced/entry` typed input,
  separate from EX. A zero-sortie-budget live click in the current zero-ticket
  state stayed on the reviewed Raid root and exposed no fleet, precombat, or
  advanced surface. It was not repeated and consumed no resource; advanced
  execution remains unsupported rather than being guessed from the EX flow.
- Hard was then cleared from `14→0` and PT moved `3148→4828` across an honestly
  segmented recovery chain. r3 completed eight battles before a fleet-start
  transition stopped advancing; r4 completed one battle before the host-side
  runner hung at its typed result, whose orphan result was recovered by r5;
  r5 completed one more battle and exposed the missing current-Raid result
  owner; after that owner was added, r6 recovered the retained result and
  completed the final four battles. The chain emitted fourteen real sorties,
  used no raw-input fallback, and consumed the hard grant `14→0`, but it is not
  presented as one uninterrupted pass. The final passing receipt is
  `integration/alas/current-raid-daily-hard-full-clear-live-validation-receipt-20260830-r6.json`;
  r3 and r5 remain as the corresponding failed receipts.
- Actual cross-day wakeup, end-to-end live zero-ticket fallback, a positive
  ticket-consuming final commit, advanced challenge execution, and a complete
  easy round remain open. Normal has an uninterrupted full clear; hard has the
  segmented recovery-backed full clear described above.

### Hospital: recommendation switch replayed before any UI work

- `Hospital.UseRecommendFleet` is now exact-boolean and fail-closed at both
  `Hospital.run()` and `HospitalCombat.combat_preparation()`. Invalid values
  stop before the Hospital UI path and before the preparation loop can inspect
  or click a fleet surface.
- Recorder-only replay executes the original occupied-fleet skip, enabled
  recommendation, and disabled/manual-takeover decisions. It also proves the
  configuration value reaches the original preparation branch in both boolean
  states; the recommendation final-input boundary is a recorder, not a device.
- Hospital navigation, candidates, recommendation clicks, combat, rewards,
  postconditions, observation, and all Android input remain unadapted. This is
  an offline-only field promotion with a zero mutation budget.

### Awaken: original-task live cognitive-awakening closure

- `Awaken.LevelCap` and `Awaken.Favourite` now have an exact, fail-closed
  contract at the first executable statement of pinned upstream `Awaken.run()`.
  Only `level120`/`level125` and real booleans are admitted; enum aliases,
  casing changes, integer booleans, and wrong types stop before any
  `awaken_run` call.
- The original `Awaken.run()` retains level-125 array-first ordering, its
  `awaken_run()` loops, scheduling, and exit decisions. Semantic mode now uses
  narrow begin/phase/next/finish ports: they prove the official Dock and
  favourite scope, select the exact `可认知觉醒`/`可认知觉醒 II` filter, read
  coins/chips/arrays from exact sprites, and commit only a sufficient modal
  under an `awaken.execute` grant.
- Live receipts cover all-scope 120→125 with arrays, favourite-scope 105→110
  through the original level-125 chip fallback, and a level-120 100→105 chip
  transaction. Completion is accepted only from the exact official result
  text; the receipt records both the unlocked cap and observed ship level so
  stored EXP (for example 105→110 producing level 106) is not misreported.
- A subsequent level-120 run proves the empty-candidate exit consumes no
  action grant. Every run restores the Dock filter and favourite scope, leaves
  through the exact Dock back control, proves the main page, schedules the
  original server-update delay, and removes its temporary configuration.
- Qualification consumed only the explicitly authorized official resources:
  20,000 coins, 2,000 Cognitive Chips, and 200 Cognitive Arrays across five
  reconnaissance/qualification awakenings. No paid-resource purchase path was
  invoked; the account finishes with 707 coins, 73,490 chips, and 8,997 arrays.

### Configuration interaction attack matrix: pinned-source, fixed-seed, zero-input pass

- `verify_alas_configuration_attack_matrix.py` now composes the existing
  configuration contracts only where their gates share an ALAS ownership path:
  campaign pre-sortie (`Campaign`, `Fleet`, `HpControl`, `Submarine`), central
  `Emotion` construction, and Scheduler/EventGeneral/TaskBalancer/Optimization
  queue decisions. It does not invent a second campaign, scheduler, or combat
  state machine.
- The fixed seed `0xA1A5C0DE` produces 21 campaign pairwise rows, 18 scheduler
  pairwise rows, and 32 valid -> invalid -> valid state sequences. Eight named
  minimal invalid cases cover integer-as-bool aliases, invalid fleet identity,
  NaN threshold, active submarine, reversed scheduler range, bool coin limit,
  infinite interval, and unknown idle mode. A failure includes its stable seed
  and row/sequence id instead of being reported as an unreproducible fuzz hit.
- Every invalid pre-sortie case stops at its exact gate before the semantic
  pre-sortie scope. The matrix checks no configuration value is rewritten, no
  action authority is minted, and no contract source exposes click, gesture,
  screenshot, crop, OCR, or template fallback. The gate order is pinned to the
  authoritative campaign patch, with emotion validation preceding original
  object ownership.
- The matrix runs the existing original-method replays against the clean pinned
  `81ccf63` checkout: scheduler, fleet, HP control, emotion, submarine,
  EventGeneral/TaskBalancer, and optimization. The HP replay now supplies a
  source-only six-bar fixture as well as the semantic stub, so it proves the
  same original weight branch on clean upstream without a framebuffer or
  server-specific UI layout.
- All records are in memory, mutation budget remains `0`, and no runtime,
  account, game action, Android input, or resource mutation is performed. This
  hardens existing offline claims; it does not promote any field's live,
  observation, or action dimension.

## 2026-08-14

### Campaign clear mode: shared boolean decision replayed across 16 panels

- `Campaign.UseClearMode` now passes an exact-boolean contract before the
  original `FastForwardHandler.handle_fast_forward()` method mutates any map
  capability flags. The same declaration surface is pinned across Main,
  GemsFarming, event, raid, coalition, War Archives, and daily variants.
- Memory-only replay executes the original unavailable, disabled, enabled,
  clear-all, unchanged-switch, and changed-switch paths. It verifies all ten
  original map-feature suppressions, auto-search and 2x-book propagation,
  exact `on/off` switch requests, and the conditional animation wait.
- Six non-boolean values fail closed, including integer lookalikes. No
  `FAST_FORWARD` control was observed or clicked on a live account and no
  Android input occurred. Offline is complete for this field, while action
  remains missing and live/observation remain partial until a typed clear-mode
  toggle plus postcondition is qualified on both available and unavailable
  stages.

### EventGeneral and TaskBalancer: five original stop/switch decisions replayed

- `EventGeneral.PtLimit/TimeLimit` and `TaskBalancer.Enable/CoinLimit/TaskCall`
  now pass one complete contract before each original PT, time, coin, and task
  switch method. PT accepts non-negative integers and the punctuation formats
  pinned ALAS normalizes; time values are bounded naive datetimes, and task
  calls are restricted to Main/Main2/Main3.
- Frozen-clock and memory-only replay executes original PT decisions at zero,
  below, and equality; default/future/expired time limits; zero/below/equality
  coin observations; event-task disable/reset writes; and all three exact
  `task_delay(5) -> task_call() -> task_stop()` sequences. Static evidence pins
  every runtime consumer across campaign, coalition, raid, hospital, and
  auto-search combat modules.
- Nine malformed/bounds cases fail closed. `PtLimit` now reads only the exact
  active `xNNN` Unity text on a fully proven event selector; malformed,
  truncated, duplicated, incoherent, or wrong-page records fail closed. On the
  current CN account, `17060/17060` stopped before sortie with oil unchanged at
  11119, while `17060/17061` admitted exactly one D1 run and returned with
  17180 points and 10925 oil. Both receipts used the original ALAS disable/run
  paths and no raw-input fallback. `TimeLimit` subsequently completed both live
  directions: an expired limit stopped with zero sortie, while a future limit
  admitted one C1 run.
- TaskBalancer now reads only the exact active event `gold_value`, brackets it
  with the same proven event surface, and rejects malformed, truncated, stale,
  duplicated, or wrong-stage values. The live account yielded coherent typed
  coin observations without pixel access. The last bounded D3 run completed at
  23:59:35, but ALAS reloaded scheduler state and switched to an already-due
  `Restart` before evaluating the coin threshold. The failed receipt
  `integration/alas/event-general-task-balancer-main-live-validation-receipt-20260826-r9.json`
  is retained as blocker evidence, not support evidence. The validation runner
  now writes unrelated-task isolation into its one-use temporary seed so a
  later event can re-enter directly; real Main/Main2/Main3 switch recovery and
  anti-loop evidence remain missing.

### Submarine shared configuration: inactive surface complete, active input refused

- The four `Submarine` fields shared by 12 map panels now validate before
  campaign navigation. With `Fleet=0`, all 40 combinations of five modes, two
  auto-search roles, and four boss distances retain pinned ALAS's inactive
  semantics. Fleet indices 1 and 2 are both classified but fail before legacy
  fleet-selection, strategy, movement, or combat-call input.
- The replay directly executes original combat-call decisions, boss-only mode
  mapping, both auto-search setting values, and all four boss-distance plans.
  The three movement distances select `(5,5)/(4,5)/(3,5)` on one comparable
  native grid fixture; open-ocean support correctly skips movement. Two active
  combat-call final-input boundaries are captured without delegation.
- Six malformed values and ten active fleet/mode cases fail closed. The
  GemsFarming panel's narrower two-mode UI is recorded separately from the
  other 11 panels' five-mode surface. No fleet was selected, submarine moved,
  combat support called, device connected, or Android input injected; only the
  four fields' offline dimensions are promoted.

### Emotion shared configuration: all 11 bookkeeping fields classified

- All 11 `Emotion` fields shared by 17 campaign, raid, coalition, and hospital
  panels now pass a central contract when original ALAS constructs `Emotion`.
  The three public modes preserve exact calculate/ignore truth behavior; the
  pinned Hard task's internal `nothing` override is explicitly admitted but is
  not presented as a fourth public option.
- Both fleet surfaces cover values `0..150`, bounded naive record datetimes,
  all four control thresholds, all three recovery locations, and both oath
  values. The original mapping replay executes 48 fleet property combinations,
  elapsed and future record updates, all four FleetOrder reduction vectors,
  the pre-entry 2x-book multiplier, an already-recovered wait, and a post-battle
  record update.
- `keep_exp_bonus + not_in_dormitory`, which pinned ALAS otherwise discovers
  later as `RequestHumanTakeover`, now fails before the original emotion object
  takes ownership. Nine malformed/bounds cases and both fleets' incompatible
  pair are refused. Replay scheduler writes are temporary in-memory captures;
  no real task delay, sleep, account mutation, dormitory action, or Android
  input occurs. Only offline dimensions are promoted, not live observation or
  action completeness.

### EnemyPriority shared configuration: original target ordering replayed

- `EnemyPriority.EnemyScaleBalanceWeight` now validates the complete pinned
  three-value enum before campaign navigation across its 11 shared panels.
  Unknown, case-changed, empty, non-text, and boolean values fail closed.
- The input-free replay directly executes original ALAS `clear_enemy()` and
  `clear_filter_enemy()` against one comparable native `GridInfo` fixture.
  `default_mode`, `S1_enemy_first`, and `S3_enemy_first` select `C1`, `B1`,
  and `A1` respectively; the filter path proves that the two explicit modes
  replace the campaign filter exactly as upstream specifies. Same-scale ties
  retain original weight/cost ordering, and an empty enemy set returns without
  a target.
- Static source evidence pins all five runtime consumers. Seven chosen targets
  are captured at the original `clear_chosen_enemy()` final-input boundary;
  no device connection, map click, mutation, or Android input occurs. Actual
  clicks remain governed by the existing semantic grid identity, raycast,
  freshness, budget, and post-state gates, so only the field's offline
  dimension is promoted and its existing live/action dimensions are unchanged.

### HpControl shared configuration: deterministic decisions and early refusal

- All eight `HpControl` fields shared by 11 normal/event campaign panels now
  have an input-free contract against the pinned, patched ALAS tree. Ratio
  inputs cover zero, defaults, one, out-of-range, non-finite, wrong-type, and
  boolean cases. Fleet weights require exactly three positive integers and
  preserve ALAS's Chinese-comma normalization.
- The replay directly executes original `hp_get()`, `_expected_scout_order()`,
  `hp_retreat_triggered()`, and `handle_emergency_repair_use()`. It proves
  weighted HP `0.9/0.8/0.7 -> 0.9/0.4/0.175`, scout-order classes, the strict
  low-HP `< threshold` boundary, and one emergency-repair final-input boundary.
- The three enabled branches remain explicitly refused before campaign
  navigation: HP balancing still ends in a coordinate drag, emergency repair
  still uses unqualified combat templates/input, and low-HP retreat still
  enters the legacy withdrawal loop. Defaults with all three toggles disabled
  are admitted; no device connection, mutation, or Android input occurs.
- This promotes only the eight fields' offline dimension. Observation and live
  values already recorded elsewhere are not broadened, actions remain missing,
  and the 11 panels stay below full support.

### Task hoarding: bounded original scheduler time path

- `Optimization.TaskHoardingDuration` now passes the original ALAS `hoarding`
  property and the existing scheduler replay for `0`, `1`, `15`, and `1440`
  whole minutes. Negative, larger-than-one-day, fractional, textual, boolean,
  missing, and malformed values fail before `get_next_task()` time arithmetic.
- The one-day ceiling is an explicit Headless safety bound against accidental
  unbounded task deferral. ALAS still owns pending/waiting classification,
  priority, `is_hoarding_task`, `NextRun` adjustment, persistence, and loops.
- The other Optimization fields are deliberately not promoted. Screenshot
  intervals are clamped and consumed during `Device` initialization, before
  the current scheduler gate, and have not been correlated with semantic frame
  freshness across backends. `WhenTaskQueueEmpty=close_game` still reaches the
  legacy `app_stop()` path without a verified package-process lease; `goto_main`
  and `stay_there` still need queue-empty recovery replays. Re-entry requires an
  initialization-time pure gate plus frame-clock/backend evidence, and a leased
  semantic process-stop port for `close_game`.

### Mail shared configuration: all boolean combinations classified offline

- The four `Mail` toggles now pass all 16 boolean combinations through the
  pinned, patched `MailWhite.run()` state machine with navigation and
  `mail_claim()` replaced by input-free stubs. Four representative non-boolean
  values fail before flow ownership or navigation.
- The replay preserves the original no-claim early return, including the
  delete-only combination. Selected claim combinations reach the unchanged
  final `mail_claim()` call with all four values intact; no claim, delete,
  confirmation, device connection, or Android input occurs.
- This promotes only the four fields' offline dimension. Existing mail action
  grants remain default-denied and budgeted, and observation/action/live stay
  partial; destructive live authority is not broadened.

### Fleet shared configuration: complete offline classification and early refusal

- The nine shared `Fleet` fields used by 12 normal/event campaign panels now
  pass a 68-case, input-free replay against the pinned and patched ALAS tree.
  All Fleet 1 indices `1..6`, Fleet 2 `0..6`, and both step ranges `2..5`
  preserve ALAS's original boss/current/reversed-fleet routing.
- Source audit proves `Fleet1Formation` and `Fleet2Formation` have no original
  ALAS business/state-machine read outside generated configuration; the new
  bounded pre-navigation gate is their only patched read. Semantic mode therefore
  accepts the existing `double_line` baseline but rejects `line_ahead` and
  `diamond` before navigation instead of pretending the setting took effect.
- All five combat modes are classified. Only `combat_auto` is admitted because
  the other four still require untyped directional or weapon input. All four
  Fleet orders preserve original ALAS boss routing offline, while semantic
  campaign navigation remains limited to the reviewed
  `fleet1_mob_fleet2_boss` order.
- The campaign patch calls the pure configuration gate before opening its
  semantic pre-sortie context. Invalid integers, booleans, enums, and every
  valid-but-unqualified branch fail closed with mutation budget `0` and no
  Android input. This promotes only the nine fields' offline dimension; their
  observation, action, and live dimensions remain partial.
- Repository-root `pytest -q` is now scoped to `tests/`, so ignored ALAS
  archives can no longer become accidental test modules.

### Official one-click retirement: live transaction and typed port passed

- The game-owned quick-retirement settings are now read and enforced from the
  exact Unity Toggle groups despite unrelated dock-card Toggle/Image caps:
  unique-ship protection on, priority `R -> SR -> N`, fully-limit-broken
  duplicates keep none, and non-fully-limit-broken duplicates follow
  `OneClickRetire.KeepLimitBreak`.
- A controlled CN 9.7.10/API 32 run retired the official selection of 68 ships.
  Dock usage changed exactly `882/910 -> 814/910`; the reward dialog reported
  1026 coins and 22 medals. This exposes and fixes the upstream one-click
  path's hard-coded `total += 10` assumption in semantic mode.
- The official elite-or-higher warning was re-proven before confirmation. The
  following equipment page contained 18 item types / 113 units; all selections
  were cleared and the exact "all equipment goes to storage" exit was used, so
  zero equipment was disassembled.
- `retirement.execute` is default-denied and single-use-budgeted. ALAS still
  owns when retirement is invoked; the semantic port owns only the official
  transaction and returns its observed count. `enhance`, `old_retire`, and a
  destructive `do_not_keep` live run remain unqualified.
- Durable live evidence is
  `artifacts/retirement-live-20260814.json`; focused settings, transaction,
  capacity-delta, equipment-preservation, adapter-ledger, and patch tests pass.
- The official zero-candidate branch is now live-proven independently: the
  game returned the exact TipPanel message `没找到符合条件的舰船`, while capacity
  remained `814/910` and selected count remained zero. No destructive confirm
  was clicked. Semantic mode records this result, consumes the one transaction
  grant, and asks ALAS for human takeover instead of entering legacy pixel
  retries. Evidence: `artifacts/retirement-no-candidate-live-20260814.json`.
- An exact `NetworkDown` or `HostNotFound` Msgbox can interrupt settings,
  selection, confirmation, reward, or equipment handling and be reconnected
  inside the same bounded transaction. Any other popup remains fail-closed;
  the retirement-specific insertion test passes without broadening the prompt.

### Retirement mode entry: complete offline classification, legacy mode refused

- `Retirement.RetireMode` now accepts exactly the pinned ALAS declaration:
  `one_click_retire`, `enhance`, and `old_retire`. Seven malformed, wrong-type,
  or unknown values fail before game-tip handling or any retirement page event.
- Input-free replay executes the original `_retire_amount` mapping, preserving
  the 3000 one-click/enhancement scan ceiling plus old-retire `retire_all=3000`
  and `retire_10=10`. It also executes the original one-click and old-retire
  handlers through gems-farming flagship handling, quit, and
  `DOCK_FULL_TRIGGERED`, with every destructive method replaced by a recorder.
- The original `handle_retirement()` dispatch remains authoritative for the
  reviewed one-click and enhancement transactions. In Headless semantic mode,
  valid `old_retire` now fails before game tips, Dock/retirement detection,
  selection, or confirmation because that legacy path still depends on
  unreviewed framebuffer and coordinate input. Non-Headless ALAS keeps its
  original old-retire route.
- The replay mutation budget is `0`: no ship was retired or enhanced and no
  Android input occurred. This promotes only `Retirement.RetireMode.offline`
  to complete; old-retire observation/action/live remain incomplete, and the
  General panel remains `P` rather than `F` or `L`.

### Enhancement: ALAS task route, detailed config, and official transaction passed

- `Enhance.ShipToEnhance`, `Enhance.CheckPerCategory`, and `Enhance.Filter`
  now have a typed, fail-closed policy parser. It accepts only `all/favourite`,
  a positive check count, and the eight reviewed ship-type tokens; invalid or
  duplicate filters no longer fall through to upstream random selection.
- The official enhancement page exposes a non-destructive typed preview for
  the exact target name, attribute current/max/EXP/addition values, and every
  recommended material's slot, level, rarity sprite, and ship sprite.
- A live CN 9.7.10 run on `那智.改` used the official recommendation button:
  seven level-1 `bg1` ships were selected and cannon preview changed from
  `196/197 +0` to `+1 (25/25)`. The typed clear action returned the material
  count to zero and the preview to `+0 (0/25)`; no ship was consumed.
- Durable evidence is
  `artifacts/enhancement-preflight-live-20260814.json`.
- The observer's retained-object scan no longer truncates Image discovery at
  4096 before active records are filtered. Image sources now use a separate
  16384-entry thread-local pool and `/v1/ui` reports both source count and
  capacity. Large response snapshots are also thread-local, keeping them off
  the detached server thread's stack.
- The first rebuilt APK exposed that stack hazard and crashed before any game
  input; the previous APK was restored immediately and the game recovered.
  After the response snapshots were moved off-stack, APK SHA-256
  `e400d4e0ba829aac3498b07df4be957cb9f51457a7ed1e942c30c19c9efe2406`
  cold-started successfully and returned a complete `4051/16384` Image-source
  enumeration on the selected enhancement page.
- A repeated official recommendation selected the same seven Lv.1 `bg1`
  materials. Every active Image below each material card matched the closed
  reviewed shape; any unexpected lock, favourite, equipment, or future overlay
  now makes the protection proof false. The live preview therefore reported
  `material_protection_proven=true`, then official clear returned material
  count to zero. No enhancement confirmation was clicked.
- After explicit destructive-test authorization, the official recommendation
  and exact `ok_btn` completed one real enhancement on `那智.改`. Seven reviewed
  Lv.1 `bg1` ships were consumed; dock usage changed `814/910 -> 807/910`, and
  cannon changed exactly from previewed `196/197 +1` to `197/197 +0` while all
  other attributes remained unchanged.
- The official follow-up equipment page contained five item types / 14 units.
  Its exact all-selection was cleared, disassembly was cancelled, and the
  exact confirmation that all equipment goes to storage was accepted. No
  equipment was disassembled. Evidence is
  `artifacts/enhancement-live-20260814.json`.
- The execution port now treats an empty official recommendation as a normal
  skip. A non-empty recommendation requires complete Image enumeration, the
  closed material-card protection proof, Lv.1/bg1-only materials, and a real
  positive attribute preview before its single confirmation. It never retries
  an unobserved destructive input, and the equipment-preservation flow is part
  of the transaction receipt.
- The pinned ALAS `enhance_ships()` method retains category ordering,
  per-category checks, totals, retry/exit decisions, and `_retire_amount`.
  Semantic mode validates `ShipToEnhance`, `CheckPerCategory`, and `Filter`
  before the legacy random-type branch, then replaces only category entry,
  one selection transaction, category leave, and final Dock reset.
- A separate default-zero `enhancement.execute` budget, translated from
  `ALAS_SEMANTIC_ENHANCEMENT_BUDGET`, bounds official recommendation attempts.
  `all`/`favourite` switching, the eight ship-type
  filter mappings, candidate-card identity, enhancement-tab entry, return, and
  default Dock reset are semantic-only. A live non-destructive smoke exercised
  favourite on/off, `dd`, one exact candidate (`格里芬`), enhancement preview
  with zero selected materials, back, and reset; no recommendation or confirm
  was clicked in that smoke.
- The retained ALAS task loop is deterministic-test covered for ordered filters,
  per-category checking, no-material skips, budget exhaustion, cleanup, invalid
  configuration, and default denial. A naturally empty-material live branch
  remains unrun; that is an evidence gap, not a pixel fallback.
- `Enhance.Filter` is now fully live-qualified: the exact typed Dock selection
  was exercised for `dd`, `cl`, `ca`, `bb`, `cv`, `repair`, `ss`, and `others`.
  Each run selected its reviewed native index and confirmed it; the final reset
  selected the exact `无限制` option before returning the normal Dock state.
  Evidence: `integration/alas/enhancement-filter-matrix-r1-live-validation-receipt.json`.
- `Enhance.ShipToEnhance` is now fully live-qualified across both public values:
  the original ALAS task made one real `all`-scoped transaction and one real
  `favourite`-scoped transaction. The latter seeded exactly one named ship,
  then proved the normal Dock scope/filter reset and removed the temporary
  favourite mark. Evidence: `integration/alas/enhancement-task-all-dd-r2-live-validation-receipt.json`
  and `integration/alas/enhancement-task-favourite-dd-r4-live-validation-receipt.json`.
- `Enhance.CheckPerCategory` remains partial. A live value of two reached a
  real confirmed enhancement, but the client took longer than the old
  five-second equipment-preservation handoff and the invocation therefore did
  not emit two verified execution receipts. It is not promoted until a single
  original ALAS call records both configured transactions.

### StopCondition priority port: typed map achievement and fleet levels passed

- `MapAchievement` now reads the exact stage-detail percentage, three Unity
  star Images, and the CN threat-safe label instead of framebuffer colors in
  semantic mode. The original ALAS five-value stop truth table and
  `StageIncrease` state transition remain the owners.
- `ReachLevel` now reads the six reviewed in-map level Texts in ALAS slot order.
  The original crossing rule still rejects implausible large level gaps; map
  initialization now captures the semantic pre-battle levels before returning
  from the typed projection path.
- The positive node contract is grounded in the existing 12-4 stage-detail
  snapshot and G25 fleet-stat review. Offline tests also cover partial stars,
  malformed/out-of-range percentages, incomplete stars, level ordering, and
  level 126 fail-closed.
- The actual pinned ALAS methods now run through 77 deterministic assertions,
  including the 40-row map-achievement truth table, oil boundaries, stage
  advancement, level crossing, and concurrent stop precedence. Static source
  proof places finite `RunCount` decrement after `campaign.run()` returns and
  before the post-run stop check; unlimited count remains guarded.
- `GetNewShip=true` remains deliberately unqualified: ordinary `GET_SHIP` is
  not evidence of the narrower first-acquisition `NEW_SHIP` marker. Per the
  user's direction, no probabilistic ship grind was attempted; this branch is
  explicitly skipped and remains fail-closed pending a natural sample.
- The 17-member patch includes the StopCondition, retirement, formal
  enhancement, and shared Scheduler fail-closed contracts. The Scheduler gate
  validates all 50 six-field task surfaces before the original ALAS queueing
  method; offline replay covers 15 configuration equivalence classes without
  running a real account task queue. Against pinned upstream `81ccf63b`, the
  patch applies as 106 changed files, all 105 patched Python files compile, and
  the repository suite passes `959/959` tests, including Operation Siren task configuration, Optimization configuration, BattlePass configuration, Daemon configuration, OpsiDaemon configuration, BuyFurniture configuration, Retirement mode configuration, Gacha configuration, Shipyard task configuration, Exercise configuration, Commission configuration, Dorm configuration, Benchmark configuration, Game Manager configuration, Data Key configuration, Campaign switch configuration, Reward configuration, SupplyPack configuration, Hard configuration,
  Daily configuration, EventDaily rotation, Tactical configuration, Campaign clear mode, EventGeneral, TaskBalancer, HpControl,
  task-hoarding, EnemyPriority, Emotion, and Submarine replay additions.

### Exercise full semantic flow: implemented and live-qualified

- The task entry now validates all seven declared Exercise fields before any
  navigation or input. Strategies and opponent modes retain their exact enum
  domains, trials require positive integers, HP threshold is `0..1`, HP confirm
  wait is finite `0 <= value < 300`, refresh value is integer `0..6`, and the
  refresh record is a bounded naive datetime. The contract enumerates 53,760
  representative valid combinations and rejects 48 invalid single-field cases.
- Remaining attempts, season day/clock, all four rivals' two power values, and
  each main/vanguard level are read from exact typed Unity state. Rival details
  are inspected in four explicit enter/read/back cycles, including partial
  fleets padded only after their real one-to-three cards are proven.
- Execute and refresh are separate integer action grants. One grant authorizes
  one original ALAS battle entry or one official opponent refresh; exhaustion
  stops the original loop cleanly. A refresh waits until the precombat overlay
  has fully disappeared, persists the original refresh count, then re-reads all
  four replacement rivals before sorting again.
- Battle completion owns the exact S/D grade, award, statistics, optional item
  information, and merit-shop stack. Low-HP handling reads the two typed duel
  bars, starts `LowHpConfirmWait` only when low HP is first observed, and uses
  the official pause -> leave -> confirm -> preparation-back flow. Continuous
  recovery is proven before another refresh or attempt is allowed.
- Real original-ALAS runs passed `easiest` (`7 -> 6`) and `max_exp` (`6 -> 5`).
  A forced low-HP max-exp run exited after the configured wait with attempts
  unchanged (`2 -> 2`). The `easiest_else_exp` run exited its first rival,
  consumed one refresh grant, inspected four new fleets, selected the new
  easiest rival, won, and changed attempts `4 -> 3`. Receipts are under
  `integration/alas/exercise-*-live-validation-receipt.json`.
- All four opponent modes are now implemented and have live path evidence
  (including earlier `leftmost`). The remaining qualification-only gaps are
  natural live samples for the seven non-aggressive clock windows and
  `OpponentTrial > 1`; their runtime branches and bounds are covered offline
  but were not forced by changing the account clock or deliberately losing
  additional attempts.

### Shipyard PR/DR configuration: eight-field entry contract and safe purchase subset

- PR series accepts exact integers `1..6`, DR series `2..5`, and both ship
  indices exact integers `0..6`. Both `LastRun` values require bounded,
  timezone-naive datetimes. `BuyAmount` accepts exact integers `0..15`, the
  range for which pinned ALAS has an explicit per-item price table. All eight
  fields are validated at the first
  executable statement of `RewardShipyard.run()`, before scheduler mutation,
  page navigation, coin reads, or blueprint use.
- Pinned replay covers 1,437 accepted contract cases and rejects 58 invalid
  single-field cases. The unchanged focus method yields 32 selectable
  PR series/index pairs, six index-zero disabled branches, and four series-after-
  two/index-six restrictions. Original DR-before-PR dispatch is preserved,
  including independent amounts, both-zero stop, exact 04:00 run boundary,
  DR-only skip, and PR already-run delay/stop behavior.
- Original PR/DR prices are replayed for purchases 1 through 16. The verified
  1..15 totals are 8,250 PR coins and 22,200 DR coins; equality buys all 15 and
  one coin short buys 14. Successful `BP_BUY` paths write the frozen current
  time to the rarity-specific `LastRun`; confirmation is an input-free stub.
- Navigation, series/ship selection, coin reads, blueprint use, and purchase are
  fixtures. Mutation budget is `0`; no coin or blueprint is consumed and no
  Android input occurs. Both `LastRun` fields move to `offline=complete`; both
  `BuyAmount` fields move only to `offline=partial`. Pinned ALAS assigns a
  fallback price above 15, but the current observer cannot prove the displayed
  quantity or total price, so those values are explicitly rejected before
  navigation rather than being silently accepted or spent. Re-entry above 15 requires typed quantity,
  unit/total price, balance, confirm, and post-purchase receipts. Actual PR/DR
  page identity, blueprint sufficiency, strengthen limits, purchase confirmation,
  and recovery remain incomplete; Shipyard stays at its account boundary.

### Gacha pool, amount, ticket, and drill: offline contract passed

- `Pool` accepts the five pinned values, `Amount` exact integers `1..10`, and
  `UseTicket/UseDrill` exact booleans. The guard runs before semantic build scope
  entry, resource reads, queue handling, or any submit path.
- The 200-value configuration matrix preserves original pool cost classes,
  event-only ticket detection, ticket-first/cube remainder splitting, and
  post-submit drill flushing. Original pool routing also covers unavailable
  event/wishing-well fallback and configured wishing-well refusal; four
  affordability cases preserve exact coin/cube reductions. Twenty-five invalid
  single-field cases fail before scope entry.
- All navigation, OCR, ticket inventory, preparation, submit, queue flush, and
  semantic scope operations are fixtures. Mutation budget is `0`; no build is
  submitted and no ticket, cube, coin, or drill is consumed.
- These four fields move only to `offline=complete`. Existing live evidence is
  still limited to one Light order. Multi-order submits, every other pool,
  ticket consumption, drill acceleration, queue collection/full recovery,
  resource-shortfall UI, and post-submit receipts remain incomplete; no further
  destructive replay was authorized or attempted.

### Game Manager restart configuration: fully qualified

- `GameManager.AutoRestart` admits exact booleans before the original task can
  stop the app. Invalid values fail before normal or semantic lifecycle calls.
- Pinned replay preserves stop-only behavior for `false`, stop/start/login for
  normal `true`, and semantic cold-restart/login for Headless `true`, covering
  both backend modes without replacing the original task entry.
- Live runs on 2026-08-16 completed `false` from running and already-stopped
  states, two consecutive successful cold restarts (`7133 -> 8748 -> 10361`),
  package-disabled launch failure, missing-ADB stop failure, a real network
  login failure, recovery after each fault, and the unshortened 600-second
  observer-start timeout (`605.746s`).
- GameManager now closes the semantic session in `finally`. After clearing 49
  historical leaked forwards, all success and error cases ended with zero
  matching ADB forwards. Replay proves the same cleanup after stop, restart and
  login exceptions.
- Final restoration left MainActivity foreground at PID `21799`. An independent
  observer read returned status `ok`, generation `4210`, frame age `79 ms`, 45
  Buttons and zero extraction errors; ANGLE and network settings were restored.
- Normal startup now checks package shape and ABI but does not hash or pin the
  installed game version. Tests accept a synthetic updated 10.0.0 split APK
  and reject any unexpected `sha256sum` in the compatibility path. Exact
  Android/ANGLE/observer boundaries remain pinned.
- The field is fully supported for the qualified CN x86_64 semantic profile.
  Other packages, ABIs and Activities remain separate runtime profiles. See the
  [cold-start validation report](game-manager-cold-start-validation-report.md)
  and machine-readable live receipt.

### EventStory SkipBattle: explicitly deferred

- Pinned upstream exposes `EventStory.SkipBattle` as a locked `true` value but
  never reads it; `run_event_story()` always restarts the app at battle.
- The existing semantic patch adapts story-node observation but does not add a
  non-skip battle state machine. Treating locked `true` as both values would be
  a false completion claim.
- Supporting `false` requires upstream business behavior or a reviewed battle
  continuation state machine, deterministic observation across representative
  event layouts, and battle/settlement fixtures. Until then the field remains
  partial and unknown story/battle states remain fail-closed.

### Benchmark device and scene configuration: full semantic matrix passed

- `Benchmark.DeviceType` admits exactly the five values declared by pinned
  ALAS, while `Benchmark.TestScene` admits screenshot, click, or their combined
  scene. Both fields are validated before the original task can uninstall an
  app, navigate, benchmark a device method, or enter the semantic branch.
- Pinned normal-backend replay covers the complete 5 x 3 matrix and preserves
  original SDK-30 candidate filtering, including Plone and VMOS differences.
  Semantic replay preserves screenshot-only, click-only, and combined observer
  selection without pretending the legacy device type changes semantic timing.
- On the live semantic client, `run_alas_benchmark_live_validation.py` invoked
  the unmodified 15-sample loop for every 5 x 3 configuration, recorded the
  required zero-or-one observer/input timing lists, returned to the main page
  after every case, and removed every temporary config. The receipt is
  `integration/alas/benchmark-live-validation-receipt.json` (15/15 passed,
  218.342 seconds total).
- `DeviceType` is therefore complete as a declared-and-validated Headless
  semantic configuration provenance. It does not claim that this one device
  physically provides the legacy Plone, cloud, or VMOS transports. `TestScene`
  is complete for the actual semantic observer and reversible settings round
  trip; the final return-to-main port makes odd 15-sample control runs safe.

### Dorm collection, feeding, and food filter configuration: complete

- `Dorm.Collect` and `Dorm.Feed` admit exact booleans, and `Dorm.FeedFilter`
  admits any non-empty unique ordering or subset of the six food values known
  by pinned ALAS. The validator preserves ALAS whitespace and Unicode greater-
  than separator normalization while rejecting empty, duplicate, unknown,
  malformed, and non-string rules.
- The guard is the first executable statement of `RewardDorm.run()`, before the
  semantic Dorm scope begins, navigation occurs, or collection/feeding can use
  account resources. All-disabled still disables and stops the task; the other
  three switch combinations preserve original dispatch and the 3-ship 417-
  minute scheduler delay.
- Replay covers all 1,956 possible non-empty unique food priority orders and all
  four switch combinations, or 7,824 admitted configurations. Original feed
  boundaries retain strict `fill > food`, empty-priority fallback, and no-food
  behavior. Twenty-two invalid single-field cases fail closed.
- The deterministic fixtures retain mutation budget `0`; no reward collection,
  food consumption, navigation, screenshot/OCR, or Android input occurs during
  offline replay. Live receipts now cover enabled and disabled feeding, exact
  inventory/capacity deltas, a single-value filter, main-page recovery, and a
  real collection whose quick-collect control changed from present to absent.
  Together with the full filter replay, all three Dorm fields are complete.

### Dorm furniture configuration: live set purchase plus safe post-set all boundary

- `BuyFurniture.Enable` admits exact booleans, `BuyOption` admits only the
  pinned `set/all` values, and `LastRun` is a bounded timezone-naive datetime.
  Dorm validates the full surface before semantic scope entry; direct
  `BuyFurniture.run()` also validates before its first datetime operation.
- Frozen-clock replay preserves the original six-day boundary: one second
  overdue and exact equality run, while one second early and future records
  skip. A completed multi-candidate loop restores both pages and records the
  frozen current time in `BuyFurniture_LastRun`.
- Both options reach their exact original button mapping. Coin greater than or
  equal to a positive price remains affordable; insufficient coin and zero
  price remain failures. Nineteen malformed, wrong-type, timezone, and range
  cases fail before Dorm scope or furniture handling.
- The adapter now targets the current theme-detail controls directly: `set`
  selects the native purchase-set button, `all` selects the distinct native
  purchase-all button, and final payment accepts only the furniture-coin
  action. It also clears the empty-food popup before entering the shop and
  rejects non-limited themes without spending purchase authority.
- The live `set` run bought the current event theme through one typed
  `shop.purchase`; furniture coins changed `4693 -> 3363`, gems stayed `5022`,
  `LastRun` was written, the six-ship 278-minute delay was scheduled, and the
  task returned to main. See
  `integration/alas/dorm-furniture-set-live-validation-receipt.json`.
- Buying the set caused that event theme to disappear from this account's
  candidate list. The subsequent configured `all` run recognized that the
  first remaining theme was an ordinary non-limited theme, spent neither its
  purchase grant nor currency, wrote `LastRun`, and recovered to main. See
  `integration/alas/dorm-furniture-all-post-set-boundary-receipt.json`.
  The native `all` button and final-submit path are implemented and replayed,
  but a final live `all` purchase needs another unowned event theme or account;
  Dorm therefore remains `L` and the BuyFurniture fields remain `P`.

### Daemon and OpsiDaemon polling switches: offline branch contract passed

- `Daemon.EnterMap`, `OpsiDaemon.RepairShip`, and
  `OpsiDaemon.SelectEnemy` admit only exact booleans. The normal and Operation
  Siren guards are the first executable statements of their existing
  `run_once()` methods, before screenshot polling and, for OpsiDaemon, before
  `OSConfig` merge or override.
- Replay executes both normal `EnterMap` values and all four OpsiDaemon switch
  combinations. Enabled normal polling preserves MAP_PREPARATION before
  FLEET_PREPARATION, with exact early returns for each target; disabled polling
  probes neither controlled target while retaining unrelated ambush handling.
- OpsiDaemon preserves port-repair precedence and the exact enter, dock repair,
  quit, interval-reset sequence. When no port is present, nearest-object probing
  follows only if selection is enabled; both disabled switches touch neither
  final boundary. Twenty-one non-boolean values fail before polling or merge.
- Every map click, port action, and nearest-object selection is a recorder.
  Mutation budget is `0`; no repair, movement, target selection, screenshot,
  navigation, or Android input occurs. All three fields move only to
  `offline=complete`. Real map-entry postconditions, port HP/resource deltas,
  selected-target identity, long-running recovery, and rare popup branches
  remain incomplete, so both daemon panels stay `P`.

### Battle Pass collection: typed ordinary-claim live path passed

- `BattlePass.Collect` admits only exact booleans. Its guard is the first
  executable statement of `Freebies.run()`, before any BattlePass, DataKey,
  Mail, or SupplyPack child can be constructed.
- Replay executes both original dispatch branches. Disabled mode retains Mail
  without touching BattlePass; enabled mode preserves BattlePass before Mail.
  The final `task_delay(server_update=True)` remains exact in both cases.
- Seven non-boolean values still fail at zero events in replay. Live typed
  validation then identified the exact Reward entrance and World Cruise page,
  clicked only ordinary `btn_all`, closed the delayed AwardInfo receipt, and
  proved the ordinary claim notice absent afterward. The separate paid
  `btn_pay`/lock control was never clicked and no premium input was issued.
- A later original `Freebies` run also completed the no-reward branch and
  recovered from an inherited Shop page through exact `shop/home`. Paid-track
  collection and broader account/season variants remain unqualified, so the
  field is live-partial and the panel stays `P`.

### Global Optimization runtime settings: offline original-method replay passed

- `Optimization.ScreenshotInterval` and `CombatScreenshotInterval` accept only
  finite non-boolean numbers before the shared timer can change. Original-method
  replay preserves normal and combat clamps/writeback, the lower nemu/LD cap,
  the scrcpy override, and unrestricted explicit code-set intervals.
- `Optimization.WhenTaskQueueEmpty` accepts exactly the three declared modes.
  Frozen-clock replay preserves stay, goto-main and close-game ordering plus the
  due-task bypass. Invalid values fail before `config.get_next()` instead of
  falling back silently to stay-there.
- Replay admits 9 valid classes and rejects 25 malformed values at zero input.
  Device, wait and resource-release effects are recorders; mutation budget is
  `0`. Cross-backend frame timing, long-wait reload, app-stop/Restart leases and
  return-to-main postconditions remain incomplete, so Alas stays `P`.
- `Emulator.ScreenshotDedithering` is explicitly not promoted: semantic
  screenshot returns before its original pixel-denoising branch. Supporting it
  would require a defined semantic-frame preprocessing contract, not hidden
  fallback to rendered pixels or OpenCV.

### Operation Siren Month Boss: defeated-fleet rotation qualified

- On `emulator-5580`, the normal Month Boss route now uses typed radar/grid
  observations from port coordinates `(-4, -2) -> (-3, 0) -> (-3, 2)`, then
  identifies `event_7000010` / `chongdong` as the exact `task` entrance. The
  transition is accepted only after `MAP_EXIT` appears and event IDs move to
  the `703` room namespace.
- `OpsiMonthBoss.ForceRun` is now a real runtime consumer: exact booleans are
  replayed, the enabled branch bypasses only the adaptability precheck, and
  the live configuration was restored to `false` after qualification.
- Fleet lock `on -> off`, retained-room recovery, the exact four-row fleet
  selector, Boss radar event `7032007/boss`, the challenge panel, first-entry
  information prompt, precombat start, combat, and defeat result
  `BATTLE_STATUS_D` were live-proven without framebuffer or raw-input fallback.
- Defeat no longer uses HP. Low resolve is the exact selected map-chibi
  `fleet_N/marks/damage/1` image (`name=1`, `sprite=200`); left portrait
  `agony` controls are a separate needs-port-repair signal. Fleet 4 retained
  nonzero HP while low resolve was present. The original `boss_clear` loop
  skipped the unavailable fleet, selected Fleet 3, and controlled exhaustion
  returned `False` instead of retrying a defeated fleet. Successful Boss
  settlement and hard difficulty remain unproven. Daily mission navigation
  likewise reached Forward Base 154; its accepted exact auto-search toggle
  returned to `off`, which is now correctly handled as the normal no-searchable-
  event terminal instead of an enable failure.
- Evidence: `integration/alas/operation-siren-live-qualification-20260820.json`;
  reproducible ALAS delta:
  `integration/alas/series/0095-operation-siren-typed-navigation.patch` and
  `integration/alas/series/0096-operation-siren-boss-resolve.patch`,
  `integration/alas/series/0097-operation-siren-special-zone-recovery.patch`,
  and `integration/alas/series/0098-operation-siren-stronghold-runtime.patch`.

### Operation Siren task configuration: offline original-method replay passed

- `OpsiMonthBoss.Mode` admits exactly `normal` and `normal_hard`, while
  `CheckAdaptability` admits exact booleans. Replay executes the original
  `clear_month_boss()` and `month_boss_delay()` branches, including normal/hard
  selection, hard-complete skip, the `203/203/156` threshold, and delay/stop
  ordering.
- `OpsiObscure.ForceRun` preserves the original disabled stop and enabled
  task-switch continuation branches through `clear_obscure()` and
  `os_obscure()`.
- `OpsiDaily.UseTuningSample` preserves the original use versus skip branch
  through `os_daily()` without changing mission acceptance, zone reset, daily
  mission completion, or next-update delay ordering.
- `OpsiHazard1Leveling.TargetZone` admits exactly `0`, `22`, and `44`.
  Original-method replay preserves the default `0 -> 22` mapping and both
  explicit safe-zone choices through the strategic-search boundary.
- `OpsiMeowfficerFarming.HazardLevel` admits exactly `3`, `4`, `5`, `6`, and
  `10`; each value reaches the original `zone_select()` argument and preserves
  fleet, order, auto-search, postprocessing, and task-switch ordering.
- `OpsiMeowfficerFarming.ActionPointPreserve` admits non-negative integers.
  Replay preserves the original zero-value submarine override and the
  2,000-point effective clamp; malformed values fail before logging, config
  overrides, action-point checks, or device state.
- `OpsiMeowfficerFarming.TargetZone` preserves numeric IDs and CN, EN, JP, and
  TW names through the pinned original `ZoneManager.name_to_zone()`. Resolution
  now occurs before action-point checks: malformed types fail closed and an
  unknown name preserves the original human-takeover result without task or
  device mutation.
- `OpsiGeneral.UseLogger` preserves storage entry, optional coordinate-logger
  use, and checkout ordering for both booleans. Invalid values fail before
  storage navigation.
- `OpsiGeneral.BuyActionPointLimit` covers all six declared weekly limits and
  `OilLimit` preserves the exact `oil >= cost + reserve` boundary. Purchase
  input is a recorder only; malformed limits fail before the purchase button.
- `OpsiGeneral.RepairThreshold` preserves negative disable, exact rounded-HP
  boundary repair, and no-repair branches. Non-finite and above-one values fail
  before HP observation or port navigation.
- `OpsiGeneral.DoRandomMapEvent` preserves the original no-rescan and full-map
  rescan branches. Explicit `current`/`full` API requests remain independent;
  malformed config fails before ash, combat, drop, HP, or map state.
- `OpsiGeneral.AkashiShopFilter` uses the pinned upstream selector grammar and
  preserves blank fallback, Unicode separators, priority, CL1 PurpleCoins
  exclusion, and exact coin sufficiency. Invalid tokens fail before item
  pretreatment; filtering and coin checks are record-only with no purchase.

### Operation Siren shared OpsiGeneral/OpsiDaemon runtime: bounded live closure

- `operation_siren.action_point_use`, `operation_siren.port_repair`, and
  `operation_siren.daemon_move` are explicit ledger capabilities. Every grant
  defaults to zero, a positive grant is single-use, and the resulting receipt
  is stamped with the capability and policy hash. Cancel actions remain safe
  and do not consume a grant.
- The original `ActionPointHandler.handle_action_point()` now uses typed AP,
  four exact item identities/counts, selected identity, and the native oil
  offer text. It no longer trusts the pinned upstream progressive-price table:
  the live offer changed after purchase from `1000 oil / 100 AP` to
  `2000 oil / 200 AP`. The bounded proof joined the exact pre/post snapshots:
  AP `240 -> 340`, oil `16077 -> 15077`, and weekly remaining `4 -> 3`.
  The subsequent zero-budget run held all three values fixed and recorded no
  pixel fallback. Qualification used two explicitly authorized weekly oil
  purchases in total; no coins were spent.
- AP above `MAX:200` is valid after boxes or oil purchases. The typed world
  summary now follows legacy ALAS's defensive `>600` rejection boundary rather
  than incorrectly treating the natural-regeneration capacity as a hard cap.
- `OpsiDaemon.RepairShip` now closes before port entry when no repair grant is
  present. With authorization, the exact port/dock path is available; the live
  six-ship fleet was already full HP, so it returned without a repair prompt,
  coin change, or HP change. A damaged-fleet confirmation remains conditional.
- `OpsiDaemon.SelectEnemy` replaces the pixel radar prediction path with typed
  reviewed sprites, original port-adjacent question fixup, unique Manhattan
  nearest selection, camera clamp, stale-state recheck, and a budgeted relative
  grid input. Gibraltar exposed no target and returned `waiting`; tied,
  unknown, truncated, and long-distance EMP-dependent states fail closed.
- `UseLogger`, `DoRandomMapEvent`, and `AkashiShopFilter` retain their original
  offline-equivalent branches and now point at existing typed storage,
  auto-search/map-event, and shop transaction boundaries. Their enabling live
  conditions were not present, so they remain partial rather than being
  promoted from implementation evidence alone.
- Evidence: `integration/alas/series/0400-opsi-general-daemon-runtime.patch`,
  `integration/alas/opsi-general-daemon-zero-budget-live-20260822.json`,
  `integration/alas/opsi-general-daemon-oil-transition-proof-20260822.json`,
  and `integration/alas/opsi-general-daemon-patch-tree-verification-20260822/result.json`.

- `OpsiShop.PresetFilter` covers all five declared presets from pinned
  `OS_SHOP`; `CustomFilter` preserves custom priority and blank fallback.
  The current unified port shop is now read as 19 typed cards rather than a
  fixed 20-slot assumption, including canonical item/currency identity, price,
  remaining count, and balance. On 2026-08-21 the original `OpsiShop` task used
  the custom filter to buy exactly one `DevelopmentMaterialT2`: remaining count
  `3 -> 2` and Special Exchange Tickets `1205 -> 1200`. The atomic action
  re-proved the selected card before input and both resource postconditions
  afterward; when ADB reported an ambiguous tap timeout, it resumed only after
  the exact quantity-one dialog proved the tap had landed, avoiding a duplicate
  purchase. Retained shop state no longer runs initial auto search, and the
  supply entry requires typed shop identity rather than conflating the port
  supply button with an open shop. Evidence is
  `integration/alas/operation-siren-shop-live-qualification-20260821.json`.
  Yellow-coin purchases, the other four presets live, insufficient balance,
  refresh, and all-port branches remain open, so this is `L`, not `F`.
- `OpsiVoucher.Filter` runs pinned `voucher_redirect()` and the original shop
  grammar, preserving Logger expansion, tier expansion, archive-token removal,
  Unicode separators, and intentional empty skip. Invalid tokens and types fail
  before voucher-page work. The unified `WorldShopUI` exposes exactly 22 typed
  cards with canonical icon identity, amount, remaining/total, price, Oil or
  Voucher currency, sold-out state, and a typed Voucher balance. On 2026-08-21
  the original `OpsiVoucher` task used `HECombatPlan` as its reviewed filter,
  entered from the Operation Siren map, selected the exact visible card, and
  committed one quantity-one exchange: remaining `28 -> 27` and Voucher balance
  `21592 -> 21492`. The confirmation re-proves the item name and both item-icon
  copies, and the atomic action requires both resource deltas before success;
  transient dialog projections are retried within a bound and never cause a
  second item tap. The task then returned to the map and scheduled the next
  monthly reset. Evidence is
  `integration/alas/operation-siren-voucher-live-qualification-20260821.json`.
  Oil-cost items and exhaustive live priority/insufficient-balance variants
  remain open, so this is `L`, not `F`.
- `OpsiArchive` now completes the original purchase-and-clear loop instead of
  stopping at a read-only logger inventory. A zero-budget run cleared the
  pre-existing T2 chain with 9 committed missions. The next bounded run bought
  `LoggerArchiveT4`: stock `1 -> 0`, Voucher balance `20692 -> 19892`, exact
  icon `Wdanganluopan4`, and capability `shop.purchase`. Its first pass exposed
  a real post-combat frame where the local map was visible before either
  auto-search control mounted; member 0105 now treats that as non-actionable
  and waits without input. A recovery run then committed the remaining 8 T4
  missions, including multi-battle maps, and the postcondition probe found only
  the normal monthly Arbiter row. Evidence is in the three archive live
  receipts and the typed mission-list probes dated 2026-08-21. Fleet 2-4,
  `Submarine=true`, insufficient balance, and the complete failure matrix are
  still open, so `OpsiArchive` is promoted from `B` to `L`, not `F`.
- `OpsiAshAssist.Tier` preserves the original tier-visibility wait, OCR
  comparison, up to five beacon rotations, and current-beacon fallback for
  exact integer thresholds. Malformed values fail before the first page
  observation or click. No artificial level range is imposed because pinned
  ALAS declares none. The live semantic path now binds the exact selected
  candidate index, level, HP, candidate count, and remaining attempts before
  every next-candidate tap, then rejects stale or ambiguous identity. A bounded
  live run covered `-1`, `0`, and `15` with zero input and `16` with the
  original five rotations (`7→8→1→2→3→4`) plus fallback. Attempts remained
  `3/3`, selected HP remained `1600000`, no sortie was started, and no account
  resource changed. Evidence is
  `integration/alas/opsi-ash-assist-tier-live-20260822.json`; the field is now
  five-dimension complete, while the OpsiAshAssist task panel still lacks the
  no-target, unavailable-fleet, sortie, combat, and reward chains.
- `OpsiAshBeacon.EnsureFullyCollected` preserves both original action-point
  reserve branches in `os_hazard1_leveling()` and `os_meowfficer_farming()`.
  With an enabled, uncollected beacon, `false` retains the normal 200/1,000
  reserve and `true` temporarily selects zero; malformed values fail before
  config overrides, scheduler actions, or map input. It does not create,
  attack, request help for, or collect a beacon.
- `OpsiAshBeacon.AttackMode` accepts exactly `current` and
  `current_dossier`, then replays the original `_begin_meta()` selection
  branches with recorder-only input: beacon priority, dossier skip, dossier
  entrance, and dossier-page exit. Malformed values fail before the first page
  observation; no combat, help request, reward collection, or Android input
  occurs.
- `OpsiAshBeacon.OneHitMode`, `RequestAssist`, and
  `DossierAutoAttackMode` accept exact booleans and replay the original
  `_satisfy_attack_condition()` / `_pre_attack()` choices with recorders:
  inspect-and-delay, help-request selection, and dossier auto-attack
  selection. Malformed values fail before page observation; recorder stubs do
  not send help requests, start auto attack, enter combat, collect rewards, or
  inject Android input.
- `OpsiExplore.SpecialRadar` preserves the original tuning-sample use and
  `recon_scan` decisions in `_os_explore()`. The same value, together with
  `OpsiExplore.ForceRun`, `OpsiObscure.ForceRun`,
  `OpsiAbyssal.ForceRun`, and `OpsiStronghold.ForceRun`, preserves the
  original recon/submarine task-delay exclusions in
  `AzurLaneConfig.opsi_task_delay()`.
- `OpsiExplore.LastZone` preserves the original resume cursor for zero,
  ordered zone IDs, numeric text, and pinned multilingual zone names. A saved
  zone resumes at the following configured zone; malformed, unknown, or
  out-of-order values fail before map navigation instead of silently restarting
  exploration from the beginning.
- `OpsiFleet.Fleet` now validates all four declared indexes at the original
  `OSFleet.fleet_set()` selector boundary. `OpsiFleet.Submarine` validates both
  booleans at `MapOrderHandler.os_order_execute()`, preserving scan/submarine
  dispatch, the submarine completion wait, and scheduler-delay arguments.
- `OpsiFleetFilter.Filter` uses the pinned original `Filter` grammar and
  preserves fleet order, `CallSubmarine`, Unicode separators and hyphens,
  duplicate suppression, standby positions, unavailable-fleet empty results,
  and scheduler submarine delays. Invalid rules fail before parser state,
  scheduler mutation, fleet selection, or task input.
- One hundred seventy valid classes pass and 246 malformed values fail before task,
  scheduler, map, combat, coordinate, or inventory state changes. Mutation
  budget is `0`; all effects are recorders, with no combat, item consumption,
  or Android input. Thirty-one fields now have complete offline classification.

### GeneralShop custom-item choices: offline predicate contract passed

- `GeneralShop.ConsumeCoins` and `GeneralShop.BuySkinBox` accept exact booleans
  before the original `shop_check_custom_item()` predicate reads item state.
  Replay covers the 550,000-coin boundary, custom skin-box price/amount/
  known-item checks, and both disabled branches; malformed values fail before
  item inspection.
  - `GeneralShop.UseGems` now has the same exact-boolean gate before the original
    `shop_check_item()` predicate. Replay retains Coins precedence, disabled-gem
    rejection, and equal/insufficient gem-price boundaries; malformed values do
    not inspect an item.
  - `GeneralShop.Refresh` is gated before the original `run()` loop. Recorder
    replay retains the empty-filter exit, disabled one-pass behavior, successful
    refresh-and-second-pass behavior, and unavailable-refresh stop; malformed
    values fail before either recorder call.
  - `GeneralShop.Filter` is checked against the pinned upstream shop selector
    grammar before the original property trims it. Replay preserves the default,
    Unicode separators, and intentional blank-filter skip; unknown or trailing
    tokens and non-text input fail before filtering.
  - This recorder suite remains the exhaustive predicate proof. The later
    reward-shop live qualification below adds typed inventory/balance reads and
    the bounded shared transaction port; it does not retroactively claim every
    GeneralShop mutation branch.

### GuildShop entry choices: offline predicate contract passed

  - `GuildShop.Refresh` is gated before the original loop. Recorder replay
    retains the empty-filter exit, disabled refresh, 110-coin threshold,
    successful second pass, and unavailable-refresh stop.
  - `GuildShop.Filter` is checked against the pinned upstream shop selector
    grammar before trimming. The default, Unicode separator, and intentional
    blank-filter skip remain equivalent; unknown/trailing tokens and non-text
    input fail before filtering.
  - All 12 GuildShop secondary choices are checked against the pinned
    `argument.yaml` options and generated defaults before the loop can reach
    `ShopClerk.shop_get_choice()`. Every allowed option is replayed; invalid
    text and type values fail before any recorder call.
  - These tests remain recorder-only. The later live qualification proves the
    default filter/no-match path and one exact GuildShop refresh, while the 12
    secondary-choice dialogs remain unverified.

### MedalShop2 entry choices: offline predicate contract passed

  - `MedalShop2.Filter` is checked against the pinned upstream selector grammar
    before the original property trims it. The default, Unicode separator, and
    intentional blank-filter skip remain equivalent; unknown/trailing tokens
    and non-text input fail before filtering.
  - All six MedalShop2 secondary choices are checked against their pinned
    `argument.yaml` options and generated defaults before the shop loop can
    reach `ShopClerk.shop_get_choice()`. Every allowed value is replayed;
    malformed text and types fail before any recorder call.
  - This suite remains the all-values parser proof. The later live qualification
    proves the default filter selecting `DR` and one exact purchase; the six
    secondary-choice dialogs remain unverified.

### Reward-shop transactions: bounded live qualification passed

- The original `ShopFrequent` flow entered the current GeneralShop, classified
  ten typed cards, read `35709` Coins and `5022` Gems, found no default-filter
  match, and exited with a zero transaction budget. A separate low-risk
  `BoxT2` positive probe was rejected before click when a MaaTouch reconnect
  made the exact Coins balance ambiguous; Coins and Gems stayed unchanged.
- The original `ShopOnce` flow traversed Merit, Guild, Core monthly, and Medal
  tabs with exact selected-tab ownership. Zero-budget execution completed with
  balances `350245 / 110550 / 27692 / 3606` and no purchase or refresh.
- One bounded MedalShop2 purchase selected the exact index-6 `DR` card at price
  20. Medal balance changed `3626 -> 3606`, stock changed `4/5 -> 3/5`, the
  award overlay was closed once, and no second purchase was attempted.
- One bounded GuildShop refresh matched the exact 50-GuildCoins prompt and
  dispatched only `shop/refresh/confirm`. Balance changed
  `110600 -> 110550`, inventory changed, and refresh availability changed
  `true -> false`.
- Merit/Core filter entry and Merit refresh now have strict contracts in the
  pinned upstream path. Unknown tokens and non-booleans fail before shop input.
  `shop.purchase` remains an integer budget; identity, currency, balance,
  quantity-one, stock, and postcondition drift all fail closed. Evidence is in
  `integration/alas/reward-shop-live-20260822.json`.

### Screenshot error-capture settings: offline predicate contract passed

  - `Emulator.ScreenshotDedithering` and `Error.SaveError` require exact
    booleans before a semantic frame request or native screenshot method.
  - `Error.ScreenshotLength` preserves ALAS's integer coercion and `1..300`
    deque bound. Invalid values fail closed before a frame request; valid
    values are replayed through the semantic frame branch and deque boundary.
  - Replay records timer and semantic-frame calls only. It performs no real
    screenshot, image denoising, error-image persistence, file write, device
    action, or Android input. Real frame content and error-recovery artifacts
    therefore remain unverified.

### EmulatorInfo text settings: offline predicate contract passed

  - `EmulatorInfo.name` and `EmulatorInfo.path` preserve ALAS's textarea
    trimming, newline removal, and legacy `None`/`False`/`True` sentinel
    normalization before emulator discovery can read either value.
  - Only text or null is admitted. Invalid types fail before constructing the
    `EmulatorInfo` value; replay performs no path probe, process discovery,
    emulator startup, config writeback, device action, or Android input.

### OnePush configuration: offline parser boundary passed

  - `Error.OnePushConfig` accepts ALAS's YAML mapping streams and preserves
    document-order overrides before resolving a provider. The default
    `provider: null` configuration continues to skip delivery.
  - Invalid YAML, scalar/list documents, non-text keys, and non-text providers
    close before provider lookup. Replay substitutes the provider and its
    `notify` method, so it performs zero network requests and zero real
    notification deliveries.

### Equipment-code configuration: offline parser boundary passed

  - `EquipmentCode.Config` accepts only YAML mapping streams. It preserves
    document-order overrides for code lookup and for the in-memory writeback
    intent used by the export helper.
  - Invalid text closes before either lookup can reach equipment application or
    an export can request config writeback. Replay uses only an in-memory
    configuration substitute; it performs no device navigation, equipment
    import, persistent config write, or Android input.

### Error recovery toggle: offline decision contract passed

  - `Error.HandleError` now admits only a real boolean at every direct read:
    app start, app stop, no-combat withdrawal, and exhausted-battle withdrawal.
    The two internal task paths which deliberately override it to `true` do
    not consume a user-provided value.
  - Replay invokes parent and withdrawal substitutes only. Disabled and invalid
    values stop before those boundaries; no app restart, withdrawal, device
    action, or Android input is performed.

- The previous AST-only audit incorrectly treated dynamically constructed
  `deep_get()` paths as absent consumers. Source-bound replay now verifies
  those string consumers explicitly. Headless gives the pinned-upstream
  zero-read `OpsiMonthBoss.ForceRun` field both scheduler-delay exclusion and a
  narrow runtime meaning: when enabled it bypasses only the adaptability
  precheck. `OpsiDaily.DoMission=false` retains optional tuning-sample use but
  skips mission acceptance/clearing until server update. Both are
  exact-boolean, fail-closed boundaries.
- Month Boss coordinate navigation, fleet selection, low-resolve/repair
  separation, combat defeat, fleet rotation, and all-fleets-exhausted failure
  are live capabilities. Successful settlement, hard difficulty, and reward
  postconditions remain incomplete, so OpsiMonthBoss and OpsiObscure stay `B`.

### Commission preset, custom filter, and major switch: offline contract passed

- `Commission.PresetFilter` admits exactly the six declared values,
  `DoMajorCommission` admits exact booleans, and `CustomFilter` admits the
  original category/genre/duration/`shortest` grammar with ALAS whitespace,
  Unicode separator, and Unicode hyphen normalization.
- The first executable statement after the original `run()` docstring validates
  all three fields before semantic Commission scope entry, reward handling, or
  dispatch. Empty, malformed, unsupported, and wrong-typed values fail closed;
  the original silent unknown-preset fallback is retained only as replay
  evidence and is unreachable through the guarded entry.
- Replay preserves all six presets in day and night contexts: cube/chip/oil use
  their night variants, 24-hour presets remain unchanged, and custom remains
  custom. All nine pinned filter sources parse through the original Filter,
  covering 53 unique tokens, representative priority ordering, and Unicode
  normalization. Sixteen validity/status/category cases preserve major-off and
  major-on admission behavior.
- Twelve preset/major combinations and 22 invalid single-field cases run with
  mutation budget `0`. Reward, start, UI, scheduler, and semantic-scope methods
  are fixtures; no reward is claimed, no commission is started, and no
  screenshot/OCR or Android input occurs. The fields move only to
  `offline=complete`; live nonzero-oil starts, each preset against changing
  rows, major dispatch, cancellation, and consecutive scheduling remain open.

### Data Key collection: typed full-capacity live branch passed

- `DataKey.Collect` and `DataKey.ForceCollect` admit exact booleans at the
  beginning of original `Freebies.run()`, before BattlePass, DataKey, Mail, or
  SupplyPack can navigate. Disabled DataKey collection still preserves Mail
  and next-server-update scheduling.
- Pinned replay covers all four switch combinations and 12 invalid
  single-field cases. Original `DataKey.data_key_collect()` is also replayed
  for already-collected, exact-full forced/unforced, and one-slot-free states.
- The exact uncollected `state_before` control now has a typed final-input
  method. It requires the reviewed Archives root, coherent EX/SP toggle state,
  one uncollected control with delegated raycast, valid bounds, no blocker, and
  the exact foreground package. An already-collected or ambiguous state cannot
  dispatch input.
- The original `Freebies` task ran live with `DataKey.Collect=true`,
  `ForceCollect=false`, all Mail mutations disabled, and SupplyPack/BattlePass
  disabled. It observed `300/300`, preserved the uncollected state, made zero
  Data Key claim calls, returned success, and scheduled `2026-08-26 00:00:00`.
  The temporary ALAS config was removed; the receipt is
  `integration/alas/freebies-data-key-capacity-live-validation-receipt-20260825-r1.json`.
- The full-capacity warning popup is now typed structurally: it requires the
  reviewed Archives root, exact `300/300`, both custom buttons, and the zero-key
  warning markup. Live validation opened it through the exact collect control
  and safely clicked typed cancel, proving the counter remained `300/300`.
  Confirm is exposed only inside the original DataKey flow when
  `ForceCollect=true` and a preceding collect receipt exists. It has now been
  clicked live after the exact claim; the standard AwardInfo overlay was closed
  through its exact target. Because the daily transition is irreversible, the
  initial run and final postcondition are split: an independent original-task
  rerun proves active `state_after` sprite `remaster_key_got`, counter `300/300`,
  and zero repeated claim/confirm actions. A single uninterrupted passing
  receipt must wait for the next uncollected day; this is not reported as one.

### Campaign shared switch configuration: offline contract passed

- `Campaign.UseFleetLock`, `UseAutoSearch`, `Use2xBook`, and `AmbushEvade`
  admit exact booleans at the first statement of original `CampaignRun.run()`.
  Invalid values fail before stage-name routing, map loading, navigation, or
  semantic pre-sortie scope.
- Pinned replay covers all 16 boolean combinations and 24 invalid single-field
  cases. It executes original fast-forward auto-search/2x-book selection,
  fleet-lock on/off selection, and ambush evade/attack dispatch.
- Switch widgets and ambush handlers are deterministic fixtures: no real map
  method, combat, book consumption, page input, or Android injection occurs;
  mutation budget is `0`.
- These four fields move only to `offline=complete`. Their real UI
  postconditions, non-clear maps, unavailable controls, ambush detection and
  evade failure remain live/action gaps; `Campaign.Name`, `Event`, and `Mode`
  remain partial because their dynamic routing surface is outside this batch.

### Reward collection configuration: offline contract passed

- `Reward.CollectOil`, `CollectCoin`, `CollectExp`, `CollectMission`, and
  `CollectWeeklyMission` admit exact booleans at the start of original
  `Reward.run()`, before page navigation or any claim attempt. The shared
  `RaidDaily.run()` entry validates the same five-field surface before its EX
  reward path can inspect `CollectMission`.
- Pinned replay covers all 32 boolean combinations plus 20 invalid single-field
  cases. It executes original Reward forwarding and scheduler tails, RaidDaily
  EX mission forwarding for both values, and the non-EX bypass.
- No real reward, mission, or weekly claim method is called. Mutation budget is
  `0`, with no page input or Android injection; invalid values fail before both
  runtime entries can navigate.
- These five fields move only to `offline=complete`. Resource caps, daily and
  weekly claim postconditions, red dots, number rows, empty pages, and special
  ship rewards remain live gaps and are not inferred from replay.

### SupplyPack typed zero-price boundary and no-free live path passed

- `SupplyPack.Collect` admits only booleans at the beginning of original
  `Freebies.run()`, before BattlePass, DataKey, Mail, or SupplyPack can run.
  Disabled preserves Mail and next-server-update scheduling; enabled alone
  dispatches the original SupplyPack module.
- `SupplyPack.DayOfWeek` admits exact integers 0-6 and preserves ALAS's
  Monday-zero `server_today >= target` comparison. Invalid bounds, booleans,
  floats, text numbers, and missing values fail before page navigation.
- Pinned replay executes original `Freebies.run()` and `SupplyPack.run()` for
  both collect values, all seven target weekdays against Wednesday, and the
  exact 21000-oil guard: 14 accepted and 10 invalid cases.
- The adapter now identifies only a unique numeric gift card whose name is a
  free/weekly label and whose displayed price is exactly `0` or `免费`; paid
  cards are excluded by focused tests. The post-card purchase confirmation is
  still fail-closed until a natural free-card sample can be reviewed.
- The original combined `Freebies` task was rerun live with oil `4477`, reached
  the typed gift-pack page, observed no free card, performed zero purchase
  actions, returned success, and scheduled `2026-08-27 00:00:00`. This completes the
  no-free safe branch, not a real free-pack claim receipt, so both fields and
  the Freebies panel remain partial.

### Hard stage and fleet configuration: offline contract passed

- `Hard.HardStage` is now constrained to the 64 map modules present in pinned
  upstream, from 1-1 through 16-4. Original `campaign_11_4`, underscore, and
  whitespace spellings canonicalize before semantic pre-sortie scope; absent,
  partial, malformed, or non-text stages fail closed before map loading.
- `Hard.HardFleet` admits exact integer 1 or 2 and preserves the original
  mutually exclusive fleet-order overrides. Booleans, text, floats, and other
  integers fail before the original state machine.
- Pinned replay executes original `CampaignHard.run()` and `_run_hard()` map
  loading, module import, MAP assignment, UI stage, remaining-run loop,
  auto-search exit, next-day delay, and Reward scheduling with 68 accepted and
  17 invalid contract cases.
- Replay mutation budget is `0`; device, import, OCR, and campaign execution are
  fixtures, with no map entry, battle, hard attempt consumption, or Android
  input. Both fields move only to `offline=complete`; the existing 11-4 live
  boundary is not evidence that all 64 stages or both fleets work live.

### Daily: two challenge types now run through official auto combat

- The shared Daily group now validates all seven stage selectors, six fleet
  selectors, and `UseDailySkip` before the original `daily_run()` state
  machine. Five regular selectors admit exactly skip/first/second/third; both
  module-development selectors admit exactly skip/first/second; fleets admit
  exact integers 1-6; and the skip switch admits only booleans.
- Pinned replay executes original `get_daily_stage_and_fleet()`, `daily_enter()`,
  `daily_run_one()`, and `run()` decisions for standard and emergency-module
  layouts, skip versus normal controls, the Supply Line fleet-zero exception,
  disabled skip, inactive cards, and zero remaining attempts.
- The contract covers 64 accepted and 80 invalid single-field cases. Invalid
  values fail before `daily_run`; valid replay never invokes the real
  `daily_execute()`, enters combat, consumes an attempt, or injects Android
  input. Mutation budget remains `0`.
- The semantic path now identifies the centered challenge from its exact title
  sprite instead of assuming ALAS's static weekday position, selects a typed
  stage row and an exact fleet index from 1 through 6, and authorizes only the
  final pre-combat start through `daily.execute`. Repeated start polling is
  idempotent and cannot consume a second grant for the same preparation page.
- On the API 32 x86_64 AVD, the original ALAS Daily state machine selected
  Tactical Training `second` with fleet 2 and Fierce Assault `first` with fleet
  1, delegated each battle to the game's official auto-combat, drained the
  grade/statistics/reward stack, and returned to the Daily page. The checked-in
  receipt binds each sortie to challenge, stage, fleet, observer generation,
  exact start path, bounds, policy hash, and the exact `6 -> 4` budget balance.
- The current expanded-stage surface exposes exact normal, one-time quick, and
  bulk-quick buttons. Normal mode is live-qualified; `UseDailySkip=true` has a
  typed, budgeted bulk-quick action but was deliberately not consumed during
  this acceptance run. The other weekday challenge types, remaining
  stages, fleets 3-6, Supply Line's special fleet-zero route, and limited-time
  Emergency Module Development remain offline-only. Daily therefore stays `L`
  rather than being promoted to full support.

### EventA-D daily stage rotation: offline contract passed

- `EventDaily.StageFilter` is now bound to its actual scheduler command. Every
  ordered non-empty subset of A1-A3, B1-B3, C1-C3, and D1-D3 is accepted;
  cross-panel stages, duplicates, empty entries, stage 4, partial matches, and
  non-text values fail closed before campaign file discovery.
- `EventDaily.LastStage` admits only numeric `0` or a current-panel stage. The
  validation deliberately remains after ALAS's original server-day expiry
  check: a stale invalid cursor is reset to `0`, while a non-stale cross-panel
  cursor is rejected before any stage run.
- The pinned `CampaignABCD.run()` executes 76 accepted and 48 invalid contract
  cases plus priority, resume-after-cursor, filtered cursor, missing script,
  no-match disable/stop, `TaskEnd`, locked-stage human takeover, and stale
  cursor reset scenarios. ALAS still owns file filtering, campaign invocation,
  task-switch handling, persistence, delays, and final server-update schedule.
- Replay uses temporary configuration, mutation budget `0`, and no Android
  input. No stage was entered and no oil was consumed. Only both fields'
  `offline` dimensions move from partial to complete; existing partial
  observation/action/live evidence is unchanged.

### Tactical overflow and new-student configuration: offline contract passed

- Eight Tactical fields now fail closed before the original ALAS decision
  methods: `ControlExpOverflow.Enable/T1Allow/T2Allow/T3Allow/T4Allow` and
  `AddNewStudent.Enable/Favorite/MinLevel`. The replay covers 34 accepted
  configurations and 12 invalid values; overflow limits are exact integers in
  `0..5800`, while student level accepts `1..125` and normalized decimal text.
- The original `_tactical_books_filter_exp()` runs against boundary book
  fixtures. Disabled overflow retains only the special 100-exp book at a
  level-10 threshold, enabled overflow preserves each configured T1-T4
  boundary and rejects the over-boundary book, and a non-maxed skill preserves
  all nine fixtures.
- `Favorite` had not reached semantic candidate selection before this batch.
  It is now forwarded to the existing exact shared Dock favourite toggle
  before candidates are read; the patched replay proves the call order and
  preserves the selected ship and original confirmation waits.
- `AddNewStudent` now also has a true device proof chain. Disabled preserves
  pre-existing running-course identities with no assignment; enabled enters the
  original receive, Dock, skill, book, and final confirmation branches. The
  live client exposes `off` alone for the ordinary Dock scope and retains both
  layers for favourite scope, so both scopes were toggled and produced their
  distinct candidate sets before selecting level-120 ships.
- The original confirmations started 204044 and 306064 respectively. Their
  immediate post-confirmation card tree retained old identities at the same
  Unity roots; the semantic parser now groups physical card bounds and the
  postcondition receipts prove each selected ship remains in its expected
  running course. `AddNewStudent.Enable/Favorite/MinLevel` are therefore fully
  supported. `ControlExpOverflow` was subsequently completed on the 2026-08-18
  live `5750/5800` boundary described above.

### Tactical book priority and rapid-training slots: offline contract passed

- `Tactical.TacticalFilter` now accepts only complete original-ALAS grammar
  tokens: optional `Same`, colour, T1-T4, and the `first` fallback. Original
  Unicode separators and hyphens are normalized, while blank entries, trailing
  garbage, partially matched tokens, non-text values, and ambiguous empty
  filters fail closed before book observation or selection.
- The pinned `_tactical_books_choose()` method executes seven deterministic
  orderings: same-colour, colour+tier, colour-only, tier-only, `first`, no-match
  cancellation, and Unicode-normalized input. ALAS still owns the sorter,
  initial focus, final start/cancel branch, and all retry/state-machine logic.
- `Tactical.RapidTrainingSlot` strictly admits `do_not_use` and slots 1-4. The
  original `handle_rapid_training()` maps them to the exact four offsets,
  preserves the unavailable-button false result, and clears the original
  class-start interval only after the modeled rapid-training input boundary.
- The combined ten-field Tactical replay now covers 45 accepted and 20 invalid
  configurations with mutation budget `0` and no Android input. No rapid-use
  count was consumed and no book was selected on an account. Both fields move
  only from `offline=partial` to `offline=complete`; their existing partial
  observation/action/live evidence is not promoted.

### EventB ship-drop closure: implementation passed, natural live proof pending

- The persisted B1 failure proves a generic `NewShipUI(Clone)` acquisition
  hierarchy for `西弗吉尼亚`: one full-screen `shake_panel/click` Button plus
  coherent display-name, dialogue-name, ship-type, and dialogue Text records.
- `GET_SHIP` now exposes that typed page to the original ALAS
  `handle_get_ship()` state machine and revalidates the same current-frame
  identity before one continue input. The contract is stage- and ship-agnostic;
  a topmost Msgbox or non-top raycast refuses the underlying input.
- The exact network reconnect prompt is rechecked if `network_down` mounts
  between the session's first popup probe and its combat-observer read. Only the
  reviewed reconnect pair is exposed; all other combat blockers still raise.
- At the user's direction, no further B1 run was made because the ship drop is
  probabilistic. The saved failure had the reconnect Msgbox above NewShipUI, so
  it does not provide an uncovered top-raycast live action frame. Consequently
  the combat manifest's `GET_SHIP` selector/action variants remain blank and
  `NEW_SHIP` (the first-acquisition marker) remains unqualified.
- Focused tests pass `189/189`; the repository test suite passes `761/761`.
  This is an offline implementation closure, not a claim that B1 or the natural
  ship-drop input has now been live-qualified.

## 2026-08-12

### I02 controlled G36 mutation arming: implementation passed

- The controlled-input CLI defaults to a read-only policy/target plan and
  exposes no serial or account data in its summary.
- `--execute` and `--allow-semantic-input` are independently required; either
  switch alone refuses before any ADB or ALAS access.
- A dual-armed invocation refuses a pre-existing evidence directory without
  modifying it. Live dispatch remains reserved for the explicit I03
  operational gate, so I02 itself injected no input. The full Python suite
  passes `664/664`.

See [G36 controlled-input arming](g36-controlled-input-arming.md).

### I01 G36 one-click qualification policy: implementation passed

- The checked-in artifact is an inert generator input, not a live or default
  policy; it contains no serial, PID, local evidence path, or account data.
- It accepts only the signed H05 bundle and exact stable runtime/map/ALAS/E3
  target identity, then emits one 30-second `campaign.grid_click` grant with
  `qualification-stop` recovery and `production_enabled=false`.
- Identity, target, authority, deadline, recovery, and production-marker
  tampering fail closed. The full Python suite passes `661/661`.
- I01 performs no device connection or input. The policy remains disconnected
  until I02 adds two independent mutation-arm switches.

See [G36 one-click qualification policy](g36-one-click-qualification-policy.md).

### H05 rendered G36 live preflight: qualification passed

- A visible `1280x720` AVD on PID `3094` retained the pinned game, observer,
  runtime, task-profile, defensive-closure, and upstream ALAS identities.
- Original ALAS selected `battle_0`, fleet 1, enemy E3, and route
  `F5,F4,F3,E3` twice from one unchanged map.
- Both original `_goto()` prefixes reached `device.click(grid)` with identical
  E3 path, point, bounds, and top-raycast geometry. Generations were
  `43830 -> 43839` and `43849 -> 43858`.
- The signed bundle is
  `a8dfdb91c41da228b49dc706c0f6496ef3bb94e10b875ad08a541779af10a240`;
  Android, grid, camera, and aggregate input flags are false, unknown calls are
  zero, and capability/production promotion remain false.
- Authorized stage/fleet/sortie, one bounded intermediate F5 movement, and
  exact network recovery were setup-only and excluded from both H05 runs.

See [G36 input-free live preflight](g36-live-preflight-validation-report.md).

## 2026-08-11

### G35 natural `_goto()` camera branch: qualification passed

- A qualification-only, default-zero camera setup contract accepts only an
  empty sea cell, at most two original-ALAS correction gestures, and an exact
  typed completion that clears unused budget. It has no environment-variable
  production opt-in.
- After setup placed the camera at F3 and closed its context, ALAS reacquired
  the map and independently selected the same `battle_0`, fleet 1, enemy F6,
  and `E8,E7,E6,F6` route.
- Original `_goto(F6)` owned the out-of-sight branch and naturally called
  `in_sight -> focus_to(F4) -> device.swipe_vector -> Camera.update`. The live
  `(870,434) -> (870,317)` gesture moved F3 -> F4 while preserving all 68
  logical cells with `0.001030` pixel maximum projective residual.
- `_goto()` continued to the fresh exact top-raycast F6 grid and its own
  `device.click(grid)` statement. That click was intercepted:
  `grid_input_injected=false` and `production_enabled=false`.
- The first setup attempt F6 -> F4 is retained as negative evidence; its
  second correction was rejected before input by the former one-gesture cap.
  No grid or combat input occurred in either attempt.
- The next gate is the guarded final grid click followed by original ALAS's
  live post-click wait/combat/result/map-mutation state machine. Harness-driven
  replay is not sufficient evidence for that ownership handoff.
- The full Python suite passes `384/384`; the canonical patch remains clean on
  pinned ALAS `81ccf63`.

See [G35 natural `_goto()` camera validation](g35-natural-goto-camera-validation-report.md).

### G34 original camera update and `_goto()` recheck: qualification passed

- The canonical patch now replaces only `Camera._update_view()` input during a
  semantic session. Original ALAS retains `Camera.update()`, its wait loop,
  camera-coordinate prediction, centering, global-to-local conversion, and
  `_goto()` control flow.
- A typed projective `View` derived the live camera as F4, then ALAS's original
  camera chain injected one `(539,497) -> (553,296)` gesture and observed F6
  at generation `29110`. All 68 cells remained logically identical; maximum
  projective residual was `0.000792` pixels.
- Original `_goto()` rechecked the fresh exact top-raycast F6 grid and reached
  its own `device.click(grid)` statement. That call was captured, not injected:
  `grid_input_injected=false` and `production_enabled=false`.
- The live proof used the original `focus_to(F6)` as a qualification prelude
  because F6 was already within `_walk_sight`. It proves post-swipe camera and
  `_goto()` ownership, but not a naturally out-of-sight `_goto()`-initiated
  camera gesture.
- The next gate remains input-only adaptation: qualify that natural branch or
  authorize the rechecked grid click while leaving the original post-click
  state machine intact. Edge correction, fleet movement, combat, repeated
  sorties, and the campaign-menu no-op race remain open.
- The full Python suite passes `379/379`; the canonical patch applies cleanly
  to pinned ALAS `81ccf63`.

See [G34 ALAS camera-view continuation](g34-alas-camera-view-continuation-validation-report.md).

### G33 typed campaign viewport: qualification passed; production remains disabled

- Original ALAS selected enemy F6 and owned the complete camera request path
  through `focus_to -> map_swipe -> _map_swipe -> device.swipe_vector`; the
  adapter translated only that final typed gesture.
- The accepted same-PID proof moved `(603,331) -> (481,507)` over 390 ms at
  generations `3002 -> 3004 -> 3020`, preserved all 68 logical cells, and
  ended with F6 at an exact top-raycast Unity path.
- A normalized planar homography validates the real perspective-projected map
  movement. Its maximum residual was `0.001125` pixels; logical-map drift,
  singular projection, inconsistent direction, covered target, and budget
  reuse all fail closed.
- The canonical patch restores original `handle_auto_search()` ownership
  before map-preparation proceed. The live run proved the checked Toggle went
  on -> off before map entry, preventing the game's auto-search from racing
  the qualifier.
- The viewport budget defaults to zero, the qualifier stops before any grid
  click, and the proof explicitly records `production_enabled=false` and
  `post_swipe_alas_view_update_owner=false`.
- The next gate is the original live `_goto()` post-swipe view update and
  target recheck. Fleet movement, combat, post-click map mutation, repeated
  sorties, and the campaign-menu no-op transition race remain open.
- The full Python suite passes `371/371`; the canonical patch applies cleanly
  to pinned ALAS `81ccf63`.

See [G33 campaign viewport validation](g33-campaign-viewport-validation-report.md).

## 2026-08-10

### G32 controlled episode contract: fail-closed; viewport input still open

- G32 now binds a qualification-only grid receipt, concurrent trace, checked
  S-result positive controls, bounded resource-action receipts, and a stable
  post-combat map checkpoint into one deterministic verifier.
- The receipt explicitly records that ALAS owns branch selection and its
  original `_goto()` prefix, while the current live post-click sequence is
  still driven by the controlled evidence harness. It cannot claim full live
  ALAS state-machine ownership or production readiness.
- A recent fully verified raw trace can issue an immutable same-PID package
  lease; ADB commands are bounded, transient recorder failures are counted,
  and active blockers suppress rare/result candidates.
- The canonical patch now brackets the original login handler with a semantic
  context and recognizes an unfinished map as completion of campaign-menu
  navigation without replacing either state machine.
- Live PID `3366` proved login -> main -> campaign -> resumed 12-4 and the
  original ALAS `battle_0` decision for route `D3,C3,B3`. The attempted B3
  coordinate was HUD-covered and opened `制空权确保`; the relaxed map-cell rule
  was removed and this condition now fails closed.
- No positive battle episode is claimed. The next gate is a typed map-viewport
  swipe requested by ALAS's existing camera logic, followed by a fresh
  top-raycast cell proof. Coverage remains `16/41`, defensive `18/54`, actions
  `12/38`, blockers `1/4`, and `production_ready=false`. The full Python suite
  passes `351/351`; the canonical patch applies cleanly to pinned ALAS
  `81ccf63`.

See [G32 controlled combat episode contract](g32-controlled-combat-episode-contract-report.md).

### G31 multiplex acquisition: one watcher covers eight rare surfaces

- `--profile all` now evaluates guild, mission, A-D battle grades, and A/B
  experience pages from one continuously captured raw trace.
- A cheap typed prefilter avoids repeated eight-profile trace analysis on
  ordinary map frames without dropping raw samples; the final trace is always
  fully recomputed and verified.
- Exactly one match exports one review draft. Multiple matches are ambiguous,
  set evidence incomplete, and export no draft. Nothing is auto-applied.
- The final real run captured 10 samples at generations `113131..113155` on
  PID `23161`, with zero endpoint rejects, duplicates, or ambiguities. All
  eight profiles remained absent.
- Coverage stays canonical `16/41`, defensive `18/54`, actions `12/38`, and
  blockers `1/4`; `production_ready=false`.
- The combined G29-G31 focused suite passes `18/18`.
- The full Python suite passes `336/336`.

See [G31 combat-surface multiplex validation](g31-alas-combat-surface-multiplex-validation-report.md).

### G30 passive result acquisition: six profiles ready; no live promotion

- The G29 watcher now also supports A-D battle grades and A/B experience pages.
  Their exact path structure is pinned to the already-qualified S resource and
  action mappings; reference drift fails closed.
- A candidate requires three adjacent complete frames, the exact grade sprites
  and invariant page records, one top-raycast original-ALAS target, and stable
  geometry. It produces a review draft only and never changes the manifest.
- A fresh real map trace captured 11 samples at generations `107224..107246`
  on PID `23161`, with zero endpoint rejects, duplicates, or ambiguities. All
  six passive profiles correctly remained absent and unpromoted.
- Coverage remains canonical `16/41`, defensive `18/54`, actions `12/38`, and
  blockers `1/4`; `production_ready=false`.
- The combined G29/G30 focused suite passes `12/12`.
- The full Python suite passes `330/330`.

See [G30 passive result-surface validation](g30-alas-passive-result-surface-validation-report.md).

### G29 rare-surface acquisition: watcher passed; live dialogs absent

- A zero-input watcher now targets paired guild confirm/cancel and mission
  go/acknowledge controls without changing original ALAS control flow.
- Qualification requires three adjacent coherent samples, both controls
  top-raycast actionable, stable exact paths/names, and bounded geometry.
  Ambiguity, coverage, missing controls, or drift fails closed.
- A match emits only a deterministic G27 review draft. G29 never applies the
  draft, changes the manifest, imports ALAS, or injects input.
- The current real map run captured 25 samples at generations
  `101652..101756` on PID `23161`, with zero endpoint rejects, duplicates, or
  ambiguities. Neither rare dialog was present, so both profiles remain
  unqualified and no mapping was promoted.
- Coverage remains canonical `16/41`, defensive `18/54`, actions `12/38`, and
  blockers `1/4`; `production_ready=false`.
- Focused G29 tests pass `6/6`; the full Python suite passes `324/324`.

See [G29 rare-surface acquisition validation](g29-alas-rare-surface-acquisition-validation-report.md).

### G28 defensive branch replay: 16 source paths pass; mappings unchanged

- Sixteen Device-free scenarios now run original ALAS methods for A-D result
  grades, A/B experience pages, contextual guild/mission popups, retirement,
  story, and ambush evasion. Exact query, click, sleep, return, and short-circuit
  order is pinned.
- The replay record binds ALAS commit `81ccf63` plus four source-file hashes.
  Independent verification confirms all source files still match, the campaign
  object is restored, and `input_injected=false`.
- Existing traces do not contain repeated complete evidence for these inputs:
  alternate grades are absent, guild popup has only one old observation, and
  mission/ambush/retirement/story roots have no promotable trace. G28 therefore
  reports `live_mapping_promoted=false`.
- Coverage remains canonical `16/41`, defensive `18/54`, actions `12/38`, and
  blockers `1/4`. Branch and blocker reviews remain incomplete,
  `production_ready=false`, and production still stops at G18.
- The full suite passes `318/318`; the maximum original ordinary-combat replay
  still passes ten phases and 135 calls over the unchanged 41 canonical names.

See [G28 defensive-branch replay validation](g28-alas-defensive-branch-replay-validation-report.md).

### G27 action variants and nested branches: adapter expanded; production closed

- Manifest v3 represents each original-ALAS action as one or more mutually
  exclusive Unity variants. `MAP_PREPARATION_CANCEL` now resolves the distinct
  stage-information and fleet-selection back buttons; zero or overlapping
  variants fail closed.
- The source-derived defensive contract now includes `EXERCISE_CHECK` and
  `STORY_LETTERS_ONLY`, for exact totals of 54 queries and 38 action targets.
  Ambush, retirement, and story roots plus their incomplete blocker entries are
  explicit; original ALAS remains the state-machine owner.
- Historical repeated raw frames promoted `CAMPAIGN_CHECK`,
  `MAP_PREPARATION`, `FLEET_PREPARATION`, and
  `BATTLE_PREPARATION_WITH_OVERLAY`, plus four action variants. The current
  12-4 map was only read: eight baseline samples were captured with no input.
- Current coverage is canonical `16/41`, defensive `18/54`, actions `12/38`,
  and blockers `1/4`. Fleet stats are qualified, but branch and blocker review
  remain incomplete, so `production_ready=false` and G18 remains the production
  stop.
- The full suite passes `313/313`; focused observer/map tests pass `69/69`.
  The ten-phase original-ALAS replay still passes 135 calls over the unchanged
  41 canonical names, restores source state, and injects no input.

See [G27 action-variant and nested-branch validation](g27-alas-action-variant-and-nested-branch-validation-report.md).

### G26 defensive input surface: popup cancel pass; production closed

- The canonical 41-query replay is now explicitly separated from the complete
  52-name pinned defensive query surface and 37 original-ALAS click targets.
  A new independent `branch_review_complete` gate prevents 41/41 from being
  mistaken for true-branch closure.
- Observation and action mappings are separate. Contextual resources require
  the exact click target selected by original ALAS; the headless layer does
  not choose confirm versus cancel or replace handler control flow.
- On PID `23161`, a reversible retreat dialog produced eight complete raw
  frames. `POPUP_CANCEL`, true-branch `POPUP_CONFIRM`, and their exact action
  targets were promoted from generations `36266,36269,36275`; only the
  cancel target was tapped, and the 12-4 map remained open.
- Current coverage is canonical `13/41`, defensive `14/52`, actions `9/37`.
  Fleet stats remain qualified, but branch and blocker reviews are incomplete,
  so `production_ready=false` and production remains stopped at G18.
- The full suite passes `311/311`; focused observer tests pass `29/29`, the
  maximum original-ALAS replay still passes 135 queries over the unchanged 41
  canonical names, and the G26 popup receipt verifies two resources plus two
  actions.

See [G26 defensive input-surface validation](g26-alas-defensive-input-surface-validation-report.md).

### G25 combat input closure: switch, radar, and fleet stats pass; production closed

- Original ALAS now owns an optional automation-off branch before its unchanged
  preparation loop. The ten-phase maximum replay passed with 135 queries over
  the same 41 names and an original `AUTOMATION_SWITCH` action.
- Exact live mappings were promoted for `AUTOMATION_OFF` and
  `MAP_ENEMY_SEARCHING`; six ordered HP bars and levels are also qualified.
  Coverage is `12/41`, but blocker review remains incomplete and
  `production_ready=false`.
- On PID `23161`, original ALAS admitted D3 and the guarded chain advanced
  preparation, S result, item, and experience pages. A 20 ms trace captured
  four complete radar generations, and the final map proved D3 cleared with
  ammunition `2 -> 1`.
- Active Unity objects hidden behind preparation/result pages are now masked at
  the observation boundary to match original ALAS foreground `appear()`
  semantics; no state-machine method was changed.
- Three real traces compiled into a seven-frame automation-switch fixture. The
  full suite passes `310/310`; observer build/install and mapping receipt
  verification passed. Production remains stopped at G18.

See [G25 combat input-closure validation](g25-alas-combat-input-closure-validation-report.md).

### G24 combat preparation and observer fixture: live chain pass, production closed

- Original ALAS now accepts an optional automation-confirm phase before its
  unchanged preparation loop. The full nine-phase Device-free qualification
  passed with 135 queries over 41 names and seven virtual actions.
- Exact live mappings were promoted for `AUTOMATION_CONFIRM`,
  `AUTOMATION_CONFIRM_CHECK`, `AUTOMATION_ON`, and `BATTLE_PREPARATION`.
  Coverage is `10/41`; blockers and fleet stats remain incomplete, so
  `production_ready=false`.
- On PID `19079`, original ALAS admitted and clicked J3, then one-use exact
  action commits advanced preparation, S result, item, and experience pages.
  The stable map proved J3 cleared and ammunition `3 -> 2`.
- Three adjacent traces compiled into a phase-label-free seven-frame fixture.
  Generation `8017` captured `RadarEffectUI(Clone)` and `8034` captured the
  stable map. Only one radar generation was available, so
  `MAP_ENEMY_SEARCHING` remains unpromoted.
- The full suite passes `306/306`; the observer APK verifies. Each new mapping
  receipt was verified at promotion time, and the final receipt verifies the
  current `10/41` manifest. The production runner remains stopped at G18.

See [G24 combat preparation and observer validation](g24-alas-combat-preparation-observer-validation-report.md).

### G23 controlled combat acquisition: E5 closure pass, production still closed

- Original ALAS selected and reached E5 over `C6,C5,D5,E5`; one exact
  qualification-only grid input produced a 220-frame map/loading/combat/result
  trace on stable PID `13448`.
- Exact mappings were promoted for `BATTLE_STATUS_S`, `GET_ITEMS_1`,
  `EXP_INFO_S`, `GET_MISSION`, and `PAUSE`. With G22 `IN_MAP`, current coverage
  is `6/40`; blockers and fleet stats remain incomplete, so
  `production_ready=false`.
- Four result-chain actions each required two stable generations and one-use
  authorization. A separate map read then proved fleet 1 at E5, ammo `3 -> 2`,
  E5 cleared, fleet 2 unchanged at F8, and the original current-fleet marker.
- The original ALAS replay now admits only four bounded 6-8 frame sequences,
  allowing optional `GET_ITEMS_1` and `GET_MISSION` in their observed
  positions. Base replay remains 104/38; the full branch passes 126/40. No ALAS
  state-machine method was replaced.
- The newly observed `qz1` destroyer maps into ALAS's existing `Light` genre.
  The full suite passes `302/302`, Python 3.7 import passes, both original-ALAS
  replay variants pass, and the canonical patch reverse-apply check passes.

See [G23 controlled combat acquisition](g23-alas-controlled-combat-acquisition-validation-report.md).

### G22 combat mapping promotion: first real mapping, still fail-closed

- Three complete G21 raw frames at generations `137332`, `137335`, and
  `137337` prove the same three-anchor `IN_MAP` identity. The versioned
  manifest now reports exact resource coverage `1/38`.
- The exact `[NetworkDown]` surface is recorded as one named three-selector
  all-of blocker: actionable cancel Button, exact `取 消` child, and exact
  content Text. One selector alone no longer activates a compound blocker.
- Blocker completeness is a separate explicit gate and remains false. The one
  verified blocker is partial evidence, fleet HP/levels remain unqualified,
  and `production_ready=false`.
- A strict promotion tool binds selected generations, full trace SHA-256,
  frame hashes, selectors, and before/after manifest hashes into a committed
  receipt. A separate verifier replays the exact production selector matcher
  against the raw trace and rejects receipt/frame/manifest drift.
- Fourteen focused tests and the full `281/281` suite pass. Coverage remains
  fail-closed; no Android input was used, and the canonical ALAS patch/state
  machine, G18 production stop, D6, and combat budget are unchanged.

See [G22 combat mapping promotion](g22-alas-combat-mapping-promotion-validation-report.md).

### G21 combat evidence acquisition: pipeline pass, battle trace blocked

- At G21, the 38-resource combat mapping became a strict versioned JSON
  manifest; its audit honestly reported `0/38`, with blocker and six-ship stat
  mappings unqualified.
- A package-verified, input-free recorder persists coherent raw snapshot,
  Button, and UI triples with per-frame SHA-256, increasing generations,
  atomic output, and rejection reasons. Trace files cannot contain phase
  labels or map projections.
- Six exact generations can be selected for deterministic phase-local
  Button/Image/Text candidate diffs. The compiler derives the last two full
  campaign-map projections offline through the existing G13 parser and emits a
  phase-label-free G20 fixture; it never edits the manifest automatically.
- Twelve focused tests and the full `279/279` suite pass. A live blocked-surface
  recorder smoke captured three complete samples at `137332..137337`, PID
  `19277`, with no rejected triples, duplicates, or input.
- One separately recorded, package-verified exact network-reconnect confirm at
  generation `130033` briefly removed the dialog at `130098..130099`; it later
  returned. The underlying 12-4/D6 records remained visible, but complete map
  proof correctly failed under the renewed Msgbox.
- No D6 or combat input was injected. The ALAS patch/state machine and G18
  production stop are unchanged.

See [G21 combat trace pipeline](g21-alas-combat-trace-pipeline-validation-report.md).

### G20 exact combat observer input: contract pass, live mappings open

- G19's six replay phases can now be built from complete raw Unity observer
  snapshots. Fixture phase labels, OCR, image templates, coordinates, and
  scripted booleans are not accepted as production evidence.
- The original ALAS chain's `104` presence calls are pinned to an exact
  `38`-resource surface; both added and removed upstream queries now fail.
- Every resource requires reviewed exact full paths and record identity. The
  three post-grid action resources additionally require actionable top-raycast
  Unity Buttons; all frames require complete Button/Text/Image slices, coherent
  PID/generations, game/driver identity, blockers, and hash-bound payloads.
- A test-only complete six-frame fixture drives the same G19 replay without a
  phase field. Tampering, unqualified coverage, active blocker, non-top
  raycast, and resource-surface drift fail closed.
- The G20 live manifest was `0/38`, with blockers and six-ship HP/level
  mappings also unqualified. Therefore `production_ready=false`, the canonical
  ALAS patch was unchanged, and D6 input remained closed at G18.
- The suite passes `275/275`. Current read-only generations
  `119693..119695` remained complete (`96` Buttons, `60` Texts, `320` Images)
  and still showed the exact `[NetworkDown]` text; no input was injected.

See [G20 ALAS combat observer contract](g20-alas-combat-observer-contract-validation-report.md).

### G19 original combat state machine: pinned Device-free replay pass

- Six strictly increasing typed frames now represent battle preparation,
  combat execution, S result, experience result, enemy searching, and the
  stable post-battle map. Extra/reordered frames or resource/flag/stat drift
  fail before replay.
- Real pinned ALAS executed its original `_goto()`, `combat_appear()`,
  `combat()`, `combat_preparation()`, `combat_execute()`, `combat_status()`,
  enemy-searching handler, arrival confirmation, native grid mutation, and
  path rebuild.
- The exact virtual actions were D6, `BATTLE_PREPARATION`, `BATTLE_STATUS_S`,
  and `EXP_INFO_S`. No adapter or ADB method was called.
- The isolated native result was battle `0 -> 1`, ammo `5 -> 4`, D6 enemy
  removed, current fleet retained, source MAP restored, projected map
  unchanged, and shared ALAS timers unchanged.
- The original chain made `104` queries over `38` allowlisted ALAS resources;
  any new upstream query prevents success rather than silently returning false.
- Current read-only generations `103330..103331` remained complete with
  `96` Buttons, `60` Texts, `320` Images and the exact `[NetworkDown]` blocker.
- The suite passes `267/267`; the reusable qualification script passes; the
  canonical patch remains clean and identical to patchcheck.

See [G19 ALAS combat state replay](g19-alas-combat-state-replay-validation-report.md).

### G18 original ALAS `_goto()` prefix: pinned zero-input pass

- After the G17 admission, an isolated campaign shell now calls the original
  `_goto(target, expected)` and captures its own `device.click(grid)` boundary.
  The adapter click port is never invoked, the budget remains unspent, and no
  ADB input occurs.
- ALAS owns the exact sequence: low-HP retreat check, original
  `fleet_ensure()`, visibility/focus, zero-vector map swipe, grid centering,
  global-to-local conversion, color-baseline ordering, and final grid click.
  Only the fleet/camera/view/color inputs are supplied semantically.
- Low-HP retreat, fleet/index drift, stale map or decision data, native target
  drift, early Device access, changed grid annotation, any real swipe, and any
  second click fail before input.
- Real pinned `campaign_12_4.Campaign` reproduced D6 as local D3 with sight
  `(-3, 0, 3, 2)`, reached all eight expected calls, restored the exact native
  map/grid dictionaries, and left the projected map unchanged.
- A fresh read-only live request at generations `91862..91863` remained
  complete (`96` Buttons, `60` Texts, `320` Images) and still showed the exact
  `[NetworkDown]` prompt. No current live execution is claimed.
- The full suite passes `261/261`; sources compile; the canonical patch applies
  cleanly and exactly matches the exercised checkout diff.

See [G18 ALAS `_goto()` input preview](g18-alas-goto-input-preview-validation-report.md).

### G17 campaign combat admission: contract pass, live execution still closed

- A separate `ALAS_SEMANTIC_CAMPAIGN_COMBAT_BUDGET` now defaults to `0`; the
  first slice accepts only exactly `1` and binds it to the immutable ALAS
  decision plus the same stable semantic map object.
- The qualified shape is deliberately minimal: current fleet and one typed
  `fighting` enemy share the target cell, native cost is `0`, and both the full
  route and goto route contain only that node. Movement, fleet switching,
  bosses, pickups, and multi-node routes remain closed.
- ALAS's original `_goto()` grid annotation is recognized only at its existing
  `device.click(grid)` input boundary. The exact Unity Button is revalidated
  for path, geometry, top raycast, foreground, screen bounds, and blockers;
  the budget is consumed immediately after the tap and cannot replay.
- The independent completion contract requires ALAS battle count `+1`, target
  object removal, current fleet still on target, ammunition `-1`, stable map
  topology, and a newer complete generation.
- A Device-free replay derived `68` passable and `20` land cells from the real
  pinned `campaign_12_4.MAP` and accepted exactly D6 object `1204090` with
  ammunition `5` and cell path `chapter_cell_quad_6_4`.
- The patched runner intentionally raises `ScriptEnd` after admission
  preflight and before calling `goto()`: the original `_goto()` and combat
  observation closure is not yet qualified, so G17 performs no live grid tap.
- A fresh read-only observer sample at generations `74795..74797` was healthy
  and complete (`96` Buttons, `60` Texts, `320` Images) but still contained the
  exact `[NetworkDown]` overlay. No input was injected.
- The full controller/integration suite passes `253/253`; the canonical patch
  applies cleanly to the pinned upstream SHA.

See [G17 campaign combat admission](g17-campaign-combat-admission-validation-report.md).

### G16 original ALAS campaign decision: pinned decision-only pass

- The indexed shadow map now runs ALAS's original `battle_function()` on an
  isolated campaign/config shell and intercepts the first public `goto()`
  admission before ALAS's `goto()` implementation runs.
- Pinned real `campaign_12_4.Campaign` selected `battle_0`, logical fleet `1`
  (`cell_fleet_shengwang_younv`), and enemy `D6` from origin `D6`, with
  expected `combat`, native cost `0`, route `D6`, and native goto nodes `D6`.
- ALAS's original emotion check returned at values `119/119`; any timed wait
  fails closed. Class-level road grids, the projected map, and real config
  were unchanged after the transaction.
- Device access, `_goto()`, fleet switching, map control, scanning, combat,
  retreat, and branches without a projected enemy/ammo decision all fail
  closed.
- A fresh live read at generation `59956` still found the exact
  `[NetworkDown]` blocker over the same fleet identity. No input was injected,
  and no fresh complete same-process decision is claimed.
- The full controller/integration suite passes `245/245`; the canonical patch
  applies cleanly to the pinned upstream SHA and exactly matches the exercised
  checkout's full Git diff.

See [G16 ALAS campaign decision preview](g16-alas-campaign-decision-preview-validation-report.md).

### G15 fleet-index reconciliation: live passive and pinned native pass

- The current displayed fleet now comes from one exact `1|2` top-stage Text
  plus a unique exact match between a `cell_fleet_*` marker suffix and the
  displayed fleet's typed ship sprites.
- Three live read-only generations `33896 -> 33905 -> 33913` consistently
  reported displayed fleet `1`, six roster sprites, map markers
  `cell_fleet_shengwang_younv/cell_fleet_ying`, and only
  `cell_fleet_shengwang_younv` as the roster match. No input was injected.
- The exact `[NetworkDown]` overlay remained present. A full map-model call
  failed closed, so no fresh same-process indexed projection is claimed.
- The projection now supplies ALAS `fleet_show_index`, logical
  `fleet_current_index`, indexed fleet locations, and one native
  `is_current_fleet` flag. It reuses ALAS's own reversed-fleet rule.
- Pinned real-ALAS tests passed both normal (`fleet1=D6`, `fleet2=F8`, current
  `1`) and reversed (`fleet1=F8`, `fleet2=D6`, current `2`) configurations.
- Map control, fleet switching, movement, combat, retreat, and rewards remain
  uncalled and unmapped. The suite passes `235/235`; the canonical patch
  applies cleanly and exactly matches the exercised checkout.

See [G15 fleet-index validation](g15-campaign-fleet-index-validation-report.md).

### G14 read-only ALAS map synchronization: pinned native-object pass

- The G13 model now projects transactionally into a deep-copied native ALAS
  `CampaignMap`; ALAS's own `map_data_init()`, `find_path_initial()`, and
  `_find_path()` remain the data/path owners.
- A Device-free run against pinned `campaign_12_4.Campaign` reproduced the
  live generation `4817` topology and dynamic state: 68 passable cells, 20
  land cells, fleets `D6/F8`, enemies `C6/D6`, and ammunition `F2`.
- Native ALAS routes were produced for both semantic fleet markers. Temporary
  costs/connections were then reset, and configuration changes made by shadow
  initialization were restored.
- Semantic marker-to-ALAS fleet-index identity is deliberately unresolved.
  `fleet_1_location` and `fleet_2_location` remain empty, so this projection
  cannot start ALAS movement accidentally.
- `map_control_init()`, scanning, fleet switching, grid movement, combat,
  retreat, and rewards are not called or mapped.
- A current read-only live check at generation `21296` still found the exact
  `[NetworkDown]` overlay above the loaded map. No input was injected, and no
  new same-process live pass is claimed.
- The controller/integration suite passes `230/230`; the canonical patch
  applies cleanly to the pinned upstream SHA and exactly matches the exercised
  checkout's full Git diff.

See [G14 ALAS map synchronization validation](g14-alas-map-sync-validation-report.md).

### G13 read-only campaign map model: live ALAS pass

- The stable `12-4` model combines ALAS's own `11x8` shape and exact 20-cell
  land topology with complete Unity state: 92 Buttons, 300 Images, and 55
  Texts, all non-truncated and unchanged across two increasing generations.
- It reported 68 passable cells, fleets `D6/F8` with `5/5` ammo, enemies
  `C6/D6` with typed class/scale/level/fighting state, and the `event4`
  ammunition pickup at `F2`.
- Fleet localization no longer depends on visible `shadow` Images. Each
  active fleet child carries its `cell_fleet_*` ancestor world position and
  must match one grid Button uniquely. Both live distances were exactly zero;
  the next-nearest cells were about `1.528` away.
- The final campaign replay used stage/fleet/sortie budgets `0/0/0`, replaced
  input injection with a rejecting assertion, logged the model at generation
  `4817`, and returned `ALAS_G13_READ_ONLY_MAP_RESULT True` before upstream
  retreat.
- One controlled `1/3/1` sortie recreated the map after the observer update.
  Its later generic `POPUP_CONFIRM_WHITE` probe failed closed after arrival;
  no grid, movement, combat, retreat, or reward input occurred.
- A later recurring `[NetworkDown]` overlay left the underlying map loaded but
  blocked the read-only model exactly as intended; no obscured map state was
  returned.
- Final observer APK SHA-256:
  `bb9bdaa7838182731296ce5ab4f6f17aad0394660aa7b24c245a1ccfed18b220`.
  The controller/integration suite passes `225/225`.

See [G13 campaign map-model validation](g13-campaign-map-model-validation-report.md).

### G12 campaign sortie: one exact input and real map-root proof

- `ALAS_SEMANTIC_CAMPAIGN_SORTIE_BUDGET` is independent, defaults to `0`, and
  qualifies only the exact positive value `1`. Fleet validity, disabled
  auto-search/2x, submarine mode, fleet order, oil, and the unique sortie
  target are all revalidated before ALAS's original sortie click.
- The budget-zero final command returned
  `ALAS_G12_SORTIE_BUDGET0_FINAL True` after exact fleet reconciliation and
  cancel, with no sortie. A later budget-one replay injected exactly one
  `campaign/fleet-preparation/sortie` at `2026-08-10 11:20:51.703`.
- The original map postcondition failed closed because it assumed a nonexistent
  `LevelScene(Clone)` root. After restart, the game restored the same `12-4`
  map. Generation `3103` proved the real `LevelCamera/.../LevelGrid` root, 70
  reviewed map Button paths, three fixed Image/sprite anchors, and
  `IN_MAP=True`.
- The first map attempt exposed a recursive IL2CPP liveness stack failure. The
  final observer uses non-recursive `Resources.FindObjectsOfTypeAll(Type)` and
  a bounded approximately 10 Hz typed-snapshot cadence. It remained fresh and
  stable on the recovered map beyond the earlier failure window.
- No grid, fleet movement, combat, retreat, or reward input occurred. The
  evidence is intentionally split rather than spending another sortie merely
  for a same-process success line.
- Final observer APK SHA-256:
  `7481e25e6a5d51e05101b55befdd331a051b76181819fe80ce676b7c26bbb38a`.
  The relevant controller/integration suite passes `220/220`.

See [G12 campaign sortie validation](g12-campaign-sortie-validation-report.md).

### G11 campaign fleet preparation: exact three-mutation reversible pass

- The pinned campaign command now calls ALAS's original
  `self.fleet_preparation()` and preserves the existing `FleetPreparation` and
  `FleetOperator` branch, retry, dropdown, and selection loops. Semantic mode
  replaces only reviewed typed observations and exact input endpoints.
- `ALAS_SEMANTIC_CAMPAIGN_FLEET_MUTATION_BUDGET` is independent and defaults
  to `0`. Preflight simulates ALAS's ordered branch decisions before any fleet
  input. The positive run reconciled `(1, 2, 1) -> (1, 2, 0)` using exactly
  `fleet/2/clear`, `submarine/1/clear`, and `option/2`, then returned
  `ALAS_G11_FLEET_BUDGET3_FINAL True`.
- The final-artifact budget-zero command injected no fleet input and returned
  `ALAS_G11_FINAL_ARTIFACT_BUDGET0 True` with generations
  `1220 -> 1237 -> 1245`. An independent re-entry found the original
  `(1, 2, 1)` selection restored at generation `1051`; the second cancel
  returned to the same chapter/stage set at generation `1057` with
  `IN_MAP=False`.
- Dropdown navigation and idempotent empty-row clears do not consume mutation
  budget. Any failure closes the dropdown if necessary and invokes ALAS's
  original cancel loop. Hard mode and formation-layout changes remain closed.
- The fleet sortie target remains absent from the native raycast allowlist and
  adapter click map. No sortie, map movement, combat, or reward input occurred.
- The final observer APK SHA-256 is
  `29f49a33318321b1c38fa2e590879701159d6404beabfe59af54a2fccb6ef91f`.
  The controller suite passes `217/217`; the 22-file canonical patch applies
  cleanly to `81ccf63b4540f00241628c82a58c02c7a2bb11af`, compiles, and matches
  the live patched source by SHA-256.

See [G11 campaign fleet-preparation validation](g11-campaign-fleet-preparation-validation-report.md).

### G10 campaign pre-sortie: bounded reversible ALAS pass

- The original ALAS campaign navigation, chapter/stage selection,
  `enter_map()`, and `enter_map_cancel()` loops remain in control. Semantic
  mode replaces their reviewed OCR/template/page/input ports; one narrow
  safety checkpoint cancels and stops at proven fleet preparation.
- `ALAS_SEMANTIC_CAMPAIGN_STAGE_ENTRY_BUDGET` defaults to `0`. The zero-budget
  full command returned `True` before stage input. The budget-1 command clicked
  exact `12-4`, exact map-preparation proceed, and exact fleet-preparation
  cancel, then returned `ALAS_CAMPAIGN_BUDGET1_FINAL_ARTIFACT True`.
- The final-artifact proof generations were `2102 -> 2120 -> 2132`. A final
  independent read at generation `2208` observed `马里亚纳风云上`, stages `12-1` through `12-4`,
  no preparation layer, and `IN_MAP=False`.
- The fleet sortie `start_button` remains outside the native raycast allowlist
  and semantic click map. Formation changes, sortie, map movement, combat, and
  rewards remain closed.
- Stale-root transition windows failed closed during development. Their final
  tolerance is limited to a proven map-proceed or cancel receipt and a finite
  deadline. A final cold-start run also exposed chapter-page settling after
  campaign-menu entry; that exact input is receipt-cached and its incomplete
  page check is passive only inside the existing finite campaign transition
  window. The legacy direct `campaign_extract_name_image()` caller now receives
  typed stage Buttons instead of pixels.
- The observer APK SHA-256 is
  `6bd736dadb3741599ce2d9d449c474356ebbbe7d7b4b21ffcf55ca3e37b9c2c9`.
  The controller suite passes `209/209`. The 21-file ALAS patch applies cleanly
  to `81ccf63b4540f00241628c82a58c02c7a2bb11af`; every patched file matches the
  live source by SHA-256 and compiles.
- An earlier login automatically received a `1500`-coin login/daily reward.
  External ALAS test configurations also recorded scheduler/emotion and
  screenshot-benchmark updates. These side effects are disclosed and are not
  part of the campaign authorization.

See [G10 campaign pre-sortie validation](g10-campaign-pre-sortie-validation-report.md).

## 2026-08-09

### G9 bounded task inputs: three full ALAS replays passed; Gacha recovery pending

- The pinned patch now brackets the original Tactical, Research, Dorm, and
  Gacha `run()` implementations without replacing their state machines. ALAS
  still owns ship/book/project/food/pool filtering, retry and popup loops,
  queue filling, and scheduling; semantic mode replaces only reviewed
  observations, OCR values, and exact input endpoints.
- The five completed input slices are read-only research selection alignment,
  one bounded research start, full research queue/reward/scheduling I/O,
  tactical course assignment, and dorm collect/feed plus one construction
  submit. Every mutating slice is default-closed behind an integer budget.
- Live adapter passes assigned `Hipper` with skill `荆棘与坚盾` and a matching
  T4 book; claimed five queued research completions and one finished card,
  then started exact project `G-412` after matching its `1500`-coin prompt.
- Dorm quick collect used its exact control. Feed input targets the food-card
  `icon_bg`, not the adjacent purchase `+`, and proved inventory
  `17783 -> 17782` plus food `0 -> 1000`.
- Complete patched commands now return `TACTICAL_RESULT=True`,
  `RESEARCH_RESULT=True`, and `DORM_RESULT=True`, preserving ALAS navigation,
  filtering, retry loops, and scheduling. Dorm's full replay also tolerated
  slow CourtYard hierarchy rebuilds and a network-reconnect prompt without
  replaying a food-card input.
- Construction previously selected the heavy pool, cross-checked `3662` cubes
  and `84908` coins against the exact one-order `2`-cube/`1500`-coin prompt,
  and reached a typed queue countdown. The current full Gacha replay selected
  Light and submitted one exact `1`-cube/`600`-coin order, but returned
  `GACHA_RESULT=False` because the ALAS warning alias was initially allowed to
  confirm the order one state too early. Preparation and order aliases are now
  disjoint. The resulting natural countdown remains fail-closed to a fresh
  task context and is neither accelerated nor collected.
- Observer APK SHA-256 is
  `bfd782b307de51621dfd8f796962e25ffbc7bbba12b60e8204631c6ba15729fc`.
  The final G4 package/observer evidence is
  `evidence/g4-game-init-20260809T114938Z-emulator-5580`. The controller suite
  passes `197/197`; Python compilation, diff whitespace, native observer build,
  installation, package fingerprint, and clean application plus compilation
  of the pinned ALAS patch pass.
- A corrected full Gacha command replay requires the queue to be empty again.
  Event/wishing-well construction, multi-order submission,
  accelerating or collecting an existing queue, stage selection, map/battle
  input, and Lua state remain closed.

See [G9 patched-ALAS task replay validation](g9-alas-task-replay-validation-report.md).

### G8 real ALAS reward and commission slice: clean bounded pass

- A clean checkout of pinned upstream ALAS commit
  `81ccf63b4540f00241628c82a58c02c7a2bb11af` completed the real `Reward`
  command twice. Both runs observed typed claimable state and stopped before
  claim because the mission claim budget was zero.
- The real `Commission` command completed once with start budget zero. ALAS
  scanned typed rows, applied its existing `cube` preset, selected three daily
  candidates, and stopped before row input.
- Two separately bounded start invocations selected `高阶战术研发II` and
  `高阶战术研发I`. Each revalidated the exact typed row/detail identity, assigned
  ships, zero oil cost, and one remaining budget unit before one input. Their
  post-states were proved with the matching identity, decreasing countdown,
  exact `tag_ongoing` marker, and `取消` action label. No third start was made.
- The second positive run returned from the proven detail to the list, then a
  redundant ALAS tab reset encountered a transient truncated Image snapshot.
  Complete transition reads now receive a bounded retry, and the pinned patch
  skips that reset once the independent start budget is exhausted.
- When `高阶战术研发I` finished, a separate integer reward budget of one admitted
  the exact commission finish input only after the typed finished counter was
  read as `1` twice, including immediately before the click. ALAS then closed
  the reviewed ship-EXP and award popups.
- That original reward command did not finish its proof: the combined reward
  and award view filled the observer's 64-Button buffer and correctly failed
  closed as truncated. The native capacity was raised to 128 and rebuilt. After
  a `-force-gfx-st` restart, the snapshot was complete at 58/128, the exact
  finished counter was `0`, and a full reward/start-budget-zero `Commission`
  replay returned successfully without a second claim or a third start.
- At that historical recovery point, the remaining running commission was
  parsed as `1/4` and scheduled for `2026-08-09 16:52:07`. That first claim
  remains recovery-qualified rather than being rewritten as an in-context
  `CommissionRewardProof`.
- A later five-row daily list qualified exact typed multipage scrolling. The
  reviewed handle moved from normalized top through `0.695` to bottom `0.998`
  and returned to `0.010`; actionable row indexes changed `0-3 -> 0-4 -> 1-4`.
  The ALAS replay deduplicated overlapping viewports by stable list mode and
  row index, reporting exactly five daily rows and one running commission.
  Single-page urgent state was proven by complete typed absence of both scroll
  track and handle. Generic swipe and drag paths remain closed.
- A separate one-hour `日常资源开发III` start was allowed to finish naturally.
  The next real ALAS reward call used reward budget `1` and start budget `0`,
  logged `SemanticCommissionReward 1 -> 0` with the reviewed ship-EXP and
  AwardInfo close chain, and returned successfully. An exact dashboard read
  and full dual-budget-zero ALAS replay then proved counter `0`, five pending
  rows, and zero running rows. Commission reward budget `1` is therefore now
  clean-qualified in addition to the preserved earlier recovery evidence.
- One exact `[NetworkDown]` prompt blocked the pre-reward page. Its reviewed
  Chinese prompt/labels and top-raycast confirm target were live-proven and
  restored the page. Larger budgets, nonzero-oil rows, cancellation, and
  unattended repeated starts remain unqualified. See the
  [G8 validation report](g8-alas-reward-commission-validation-report.md).
- Final observer APK SHA-256:
  `3b86a745cefbc2a493b941571e6929e965cd7f44be4a2a14ccfa257efdf99fed`.
  The controller suite passes `148/148`; Python compilation, native build,
  diff whitespace, and clean pinned-patch application checks pass.

### G7 typed task surfaces and read-only campaign: passed in reviewed scope

- The typed controller now models the reward dashboard, commission rows and
  empty marker, tactical slots and countdowns, five research cards,
  construction pool/cost, dorm occupancy/food/comfort/floor, and the visible
  campaign chapter/stage labels. Missing, duplicate, truncated, incoherent, or
  contradictory records fail closed.
- The pinned ALAS patch retains the original mission, commission, tactical,
  and research state machines. It supplies typed observation, countdown, and
  safe-popup inputs; the dorm scheduler obtains its occupied-slot count from
  typed state. The patch applies cleanly to upstream commit
  `81ccf63b4540f00241628c82a58c02c7a2bb11af`.
- Live adapter validation completed exact reward-to-tactical entry, observed
  four empty tactical slots, and returned through the contextual ALAS
  `BACK_ARROW`. Earlier in the same controlled session, four completed
  tactical rewards were received and every exact “continue learning” prompt
  was canceled; no new class was started.
- Live dorm state was `6/6` occupied slots, `0/40000` food, `454` comfort, and
  floor `1`; the exact statistics confirmation and return controls were
  validated. Feeding, collecting, decorating, and ship assignment remain
  unmapped.
- Live construction state was pool `heavy`, `3661` cubes, `2` cubes/build, and
  `1500` coins/build. The ALAS `GOTO_MAIN` alias returned through the exact
  construction `back_btn`; the construction start control remains
  presence-only and cannot be clicked through the adapter.
- Live campaign validation entered only the normal chapter list, read chapter
  `马里亚纳风云上` and stages `12-1` through `12-4` with their typed names,
  then returned. Generic `BACK_ARROW` remained unmapped; no stage, formation,
  sortie, or battle control was clicked.
- The final observer APK SHA-256 is
  `3c05c2bf913464ad7dee7a0e62c4fea3b5919a5c59c6a11d2274c8bd867d6c4e`.
  The controller suite passes `109/109`; Python compilation, diff whitespace,
  native observer build, installation, package fingerprint, and clean pinned
  patch application checks also passed.
- This is not a full unattended ALAS pass. Commission selection/start,
  tactical course assignment, research selection/start, dorm mutations,
  construction submission, campaign stage selection, map control, battle
  control, and Lua state are still closed.

### G6 typed UI and mission sidebar: passed in reviewed scope

- `GET /v1/ui` now exposes bounded, typed Toggle, UGUI Text, TextMesh Pro, and
  Image records. The final live capture reported method mask 15, zero observer
  errors, and no Image truncation.
- Typed text includes UTF-8 content and exact RectTransform bounds. The ALAS OCR
  hook resolves only text inside the requested OCR area and rejects missing,
  overlapping, truncated, malformed, out-of-bounds, and alphabet-invalid
  matches.
- Six exact task-sidebar Image paths expose selected/unselected sprite identity.
  Only those reviewed paths receive native EventSystem top-raycast evaluation.
- A live task-page loop selected weekly, observed `icon_week_sel`, returned to
  all, and exited to main. No reward input was injected by this loop.
- Final observer APK SHA-256:
  `fbc288dbe20e0264e90d522772922b72a24d799888e0804cd47781727475a571`.
  The read-only final capture is
  `evidence/g6-semantic-ui-20260809T030729Z-emulator-5580`; see the
  [G6 validation report](g6-semantic-ui-report.md).

### Post-G5 ALAS state-machine reuse: implemented; full live rerun pending

- The integration patch no longer calls a replacement mission flow from the
  top of `Reward.reward_mission()`. It brackets an adapter context and leaves
  ALAS's original notice, navigation, collect, claim, receive, retry, timeout,
  and daily/weekly ordering in control.
- ALAS reward observations from `appear()`, `match_template_color()`, and
  `image_color_count()` now consume typed semantic input. Normal `click()` is
  translated to reviewed semantic actions; raw coordinate and gesture paths
  remain rejected.
- `MISSION_MULTI`, `MISSION_SINGLE`, `MISSION_UNFINISH`, mission-page identity,
  the default sidebar, and `GET_ITEMS_1`/`GET_ITEMS_2` have explicit adapters.
  A claimable/unfinished state requires the same signature across two
  increasing observer generations.
- The separate environment opt-in now creates a one-claim budget per ALAS
  `reward_mission()` invocation. The budget is discarded in `finally`, and a
  missing opt-in refuses the claim before ADB input.
- Weekly-tab state and exact semantic input are now reviewed and live-proven at
  the adapter boundary. Weekly-only end-to-end execution, positive mission
  red-dot behavior, numeric-row claiming, ship-reward popups, and empty-page
  inference remain closed.
- This refactor has unit coverage and was syntax/lifecycle checked against the
  clean pinned upstream commit. The historical G5 claim evidence below still
  predates this ownership change, so the complete ALAS-owned claim path is not
  yet a new live pass.

### G5a/G5b - ALAS mission no-claim and controlled claim-all: passed

- The final observer evaluates the exact task-page back and `GetAllButton`
  paths plus bounded task-row `get_btn` and `go_btn` shapes. The controller
  accepts only exact numeric row indexes. These targets are subject to the same
  top-EventSystem-raycast gate as earlier actions.
- Mission state must have the same non-unknown signature across at least two
  increasing generations. Duplicate rows, clipped claim controls, blockers,
  and mere absence of task Buttons fail closed.
- The pinned upstream ALAS patch routes `Reward.reward_mission()` through the
  semantic adapter only when semantic mode is explicitly enabled. Claim input
  requires the separate `ALAS_SEMANTIC_ALLOW_MISSION_CLAIM_ONCE=1` opt-in.
- G5a entered the exact main task Button, observed five stable unfinished
  `go_btn` rows, returned to main, and injected zero claim inputs.
- G5b's zero-claim preflight observed a unique actionable `GetAllButton` and
  three numeric-row `get_btn` targets, all with top-raycast proof.
- The controlled run injected exactly one claim at `GetAllButton`, observed the
  exact `AwardInfoUI(Clone)/items/close`, closed it, and proved claim rows
  changed from three to zero while five unfinished rows remained stable.
- It then returned through the exact task back Button. An independent second
  task-page run reported `nothing-claimable`, and a no-input main-page oracle
  found no blockers with all eight reviewed targets actionable.

Primary evidence is in
`evidence/g4-game-init-20260809T013349Z-emulator-5580`; see the
[G5 validation report](g5-mission-validation-report.md).

### Final-driver regressions: passed

- Final observer ANGLE APK SHA-256:
  `990454578249bfb96df7d3d3fcbabf48fee1174f75ccc0063e544813232615c7`.
- The real game passed login/main reachability and a 40-second sustained run:
  40/40 valid samples, 36 fresh, generations 2 through 28, and 27 distinct
  generations. This did not repeat the earlier formal settings round trip.
- G3 passed in `evidence/g3-observer-20260809T013932Z-emulator-5570` with the
  exact contract Button raycast, foreground/freshness refusal, and recovery.
- G2 passed in `evidence/g2-null-20260809T014015Z-emulator-5570`: 47.117
  seconds, 20 structured events, three scenes, eight completed readbacks over
  the full run, and zero readback errors.

## 2026-08-08

### G0 - baseline capture tooling: implemented and exercised

- `capture-g0.ps1` completed against `127.0.0.1:16384` and
  `com.bilibili.azurlane` without failed commands.
- The evidence manifest's file sizes and SHA-256 values were independently
  rechecked.
- The live process mapped native x86_64 `libunity.so`, `libil2cpp.so`, EGL,
  GLES, and Vulkan/emulation libraries.
- This is environment provenance, not proof of the active game renderer. A
  separate same-host SwiftShader comparison now exists for the G2 Unity
  contract, but it is not a same-guest game baseline for MuMu.

### G1 - NULL GLES contract: passed on the validation host

- ANGLE is pinned to `be80ce591a481c12d60c50d6040d40c035b40a2b`.
- The x86_64 Android driver APK builds with only the NULL renderer enabled.
- The Android loader successfully selects the custom package for only the
  contract probe package.
- A final 3,600-second run passed shader/program, buffer, texture, FBO, query,
  draw, fence, direct readback, PBO readback, swap pacing, and logical surface
  checks.
- Observed identity: `Google Inc. (NULL)` / `ANGLE (NULL, NULL, )`.
- Observed surface: `1280x720`; direct and PBO RGBA: `00000000`.
- The final heartbeat reported 219,300 frames at 60.000 FPS. The 121 memory/CPU
  samples showed PSS falling from 94,703 KiB to 74,355 KiB and RSS falling from
  176,380 KiB to 153,348 KiB. The post-warm-up PSS trend was approximately
  +2 KiB/minute, with no monotonic growth.
- Coarse `top` samples reported 0.73% mean CPU, 4% p95, and 4% maximum.
- No fatal signal, Android Runtime fatal, or context-loss marker was found in
  the captured process logs.
- Driver and probe APK hashes revalidated against the manifest. All modified
  Android ANGLE settings were restored to their original unset state, and the
  game PID remained unchanged throughout the package-isolated test.

See the [G1 validation report](g1-validation-report.md) for artifact hashes,
evidence scope, and remaining limitations.

### G2 - Unity contract and software baseline: passed

- The contract was built with Unity `2022.3.62f3` changeset `96770f904ca7`,
  IL2CPP, and x86_64 only. The final APK SHA-256 is
  `94ee95a8a6988c6b360047c66739cace3e1201e7b389b6d0e61503284ffeb696`.
- The original package-isolated 80-second functional run used
  `ANGLE (NULL, NULL, )`, OpenGLES3, and a `1280x720` logical surface.
- `Update`, `FixedUpdate`, `WaitForEndOfFrame`, animated UI state, five scene
  transitions, and app pause/resume all advanced without process restart.
- A safe test-button click changed its semantic marker from `contract/button`
  to `contract/button-clicked` with generation 2.
- All 15 AsyncGPUReadback requests completed with 1,024 zero-filled bytes;
  there were no errors or timeouts.
- The run produced 31 structured events and six heartbeats. The final heartbeat
  reported 1,800 updates, 3,365 fixed updates, and 1,799 end-of-frame resumes.
- PSS/RSS changed from 160,195/243,128 KiB to 154,475/238,372 KiB. Coarse
  process CPU samples averaged 5.87% with an 8% maximum.
- No fatal signal or context-loss marker was found. APK hashes matched the
  manifest, all ANGLE settings were restored, the test process was stopped,
  and the game PID remained `7547`.
- The software comparison used Android Emulator `37.1.11`, the same API 32
  x86_64 AVD/image, identical Unity APK and `1280x720` surface, and separate
  cold QEMU processes for official `-gpu swiftshader` and package-routed NULL.
- SwiftShader and NULL both passed the full functional contract. Host QEMU
  sustained CPU fell from 2.0551 to 0.5178 core equivalents (-74.8%). CPU time
  per 1,000 Updates fell 71.6%, so the advantage remains after accounting for
  the NULL leg's lower Update count.
- Host QEMU median working set fell 9.54%; Android app median PSS/RSS fell
  7.67%/4.83%. The fail-closed comparison manifest passed with no failures.
- Final evidence is in
  `evidence/g2-system-20260808T111131Z-emulator-5570`,
  `evidence/g2-null-20260808T111610Z-emulator-5570`, and
  `evidence/g2-comparison-20260808T112155Z`.

See the [G2 validation report](g2-validation-report.md) for the evidence scope.

### G3 - Observer contract: passed on the Unity contract workload

- The ANGLE component found all 32 allowlisted IL2CPP exports through the
  in-memory ELF dynamic table despite Android linker-namespace isolation;
  `RTLD_DEFAULT`, soname `RTLD_NOLOAD`, and full-path `RTLD_NOLOAD` remained
  unavailable.
- The unmodified Unity Android activity accepted the `unity` Intent extra
  `-force-gfx-st`. NULL Surface Swap and managed `Update()` then executed on
  the same Unity main-thread TID.
- Main-thread typed snapshots used Unity liveness enumeration for
  `UnityEngine.UI.Button`, fixed getter invocation, active scene handles, and
  monotonic snapshot/scene/semantic generations.
- A local abstract Unix socket exposed only `GET /v1/snapshot`, checked
  `SO_PEERCRED`, rejected an arbitrary invocation-shaped request, and returned
  a fixed `alas-headless.observer/v1` schema.
- The safe contract click changed one active Button from interactable to
  non-interactable and advanced semantic generation. A later scene transition
  advanced scene generation.
- Pressing Home changed the top-resumed package to Launcher and made the last
  snapshot stale. The action gate stayed closed; resuming restored a fresh,
  higher-generation snapshot.
- The observer also exposes `GET /v1/buttons` with fixed schema
  `alas-headless.buttons/v1`, bounded records, full hierarchy paths, Canvas
  identity, state flags, screen/ADB points, and four-corner RectTransform
  bounds. It exposes no object addresses or generic invocation.
- Final G3 evidence with bounds and top-raycast validation is
  `evidence/g3-observer-20260809T013932Z-emulator-5570`; its manifest passed
  with no failures. The final observer ANGLE and Unity APK SHA-256 values are
  `990454578249bfb96df7d3d3fcbabf48fee1174f75ccc0063e544813232615c7`
  and `87e845359bc1d957b0c75f685f461b017ed6e05d0a593088683511400e8e99ba`.
- A final 47.117-second G2 regression with the 32-symbol, typed-bounds,
  reviewed-target raycast observer passed in
  `evidence/g2-null-20260809T014015Z-emulator-5570`: 900 Updates, 1,689
  FixedUpdates, 899 end-of-frame resumes, eight completed readbacks over the
  full run, and zero readback errors.

See the [G3 validation report](g3-validation-report.md) for evidence scope and
remaining limitations.

### G4 - harmless real-game closed loop: passed

- After the user completed agreement and account login, Chinese 9.7.10 reached
  its login/main Unity UI on the dedicated API 32 x86_64 AVD under NULL.
- A 120-second no-input run produced 120/120 structurally valid samples,
  113 fresh samples, generations 2 through 99, and 98 distinct generations;
  no fatal marker was found.
- The game exposed exact paths and bounds for login and the main-page battle,
  formation, settings, mail, shop, dock, task, and build Buttons.
- The action runner clicked only the exact login target, waited for an exact
  `battle` postcondition, detected and dismissed the known bulletin overlay,
  entered settings at `(1221,36)`, observed 23 settings Buttons, clicked the
  exact settings `back_btn` at about `(57,54)`, and verified that main
  battle/settings targets and the exact foreground Activity returned. Every
  injected target was independently the top `EventSystem.RaycastAll` result at
  its point (or an ancestor of that result).
- The standard-library Python oracle independently passed a live no-input smoke
  over all 14 reviewed ALAS aliases (seven main semantics), including top
  raycast identity. It checks schema, package, PID, peer UID, driver revision,
  foreground component, freshness, generation coherence, unique path mapping,
  bounds, and known blockers.
- The ALAS-name bridge in this historical G4 run mapped only 14 reviewed
  aliases for seven main-page semantics and used the then-current strict game
  fingerprint gate. Current normal startup instead checks package/component,
  ABI and IL2CPP layout without pinning the mutable game version or file
  digests; the observer revision and action gates remain exact. Unmapped assets
  and raw multi-click/long-click/swipe/drag calls raise instead of injecting
  coordinates.

Evidence is in
`evidence/g4-game-init-20260808T160921Z-emulator-5580`,
`evidence/g4-game-init-20260808T172750Z-emulator-5580`, and
`evidence/g4-game-init-20260808T172941Z-emulator-5580` (including
`alas-adapter-live.json`). G4 is passed. The later G5a result covers only the
mission no-claim branch and does not retroactively broaden G4. See the
[G4 validation report](g4-preflight-report.md).

## Android loader compatibility found during G1

Android's `GraphicsEnvironment` requests a developer ANGLE package with the
Vulkan platform token even when the application did not choose a renderer.
The NULL-only build therefore needs a narrow loader-token translation before
display construction. It also needs common RGBX Android configs and an
implementation of swap-with-damage used by HWUI. These are maintained as
separate patches so each compatibility behavior remains auditable.

### 2026-08-16 Commission full qualification: passed

- Real ALAS runs started zero-oil tactical/resource commissions and a major
  `高阶自主训练`; the latter confirmed the exact 1200-oil prompt and reached
  a decreasing `tag_ongoing` countdown.
- One running tactical commission was reopened, cancelled through the exact
  `确定放弃任务？` prompt, observed absent from the running set, and refilled
  by a subsequent complete ALAS Commission run.
- A real positional-list bug was fixed: after a start reorders rows, ALAS now
  rebinds the intended commission by immutable typed fields before clicking
  the fresh signature, rather than trusting a stale row index.
- A two-slot live regression then started two identical pending
  `日常资源开发VI` rows in one ALAS invocation: the first used current row 2,
  the rescan used fresh row 3, both reached `tag_ongoing`, and the command
  returned to 4/4 running with next run `2026-08-16 12:50:21`.
- `cube`, `cube_24h`, `chip`, `chip_24h`, `oil`, and `custom`, plus
  `DoMajorCommission=false/true`, each completed a separate live dynamic-list
  run. All eight runs preserved 4/4 running state and scheduled the earliest
  completion at approximately `2026-08-16 12:02:29`.
- The Commission panel and its three configuration fields now have complete
  configuration, observation, action, offline, and live evidence. The support
  matrix promotes Commission from `L` to the repository's first `F` panel.

See [G8 real ALAS reward and commission validation](g8-alas-reward-commission-validation-report.md).
### Operation Siren META beacon one-hit path live-qualified

- Created one Bristol META Lv15 beacon from exact typed `200/200` points and
  observed the post-create `100/200`, `1600000` HP, and `3/3` attempt state.
- The runtime requested world, guild, and friend assistance, preserved explicit
  own-beacon task ownership across adapter refreshes, confirmed the saved META
  formation, entered automatic combat, drained both result pages, and returned
  to the exact current-beacon detail page.
- The typed HP delta reported `276085` damage and the original OneHitMode logic
  delayed the next check by 30 minutes. A saved formation with zero main or
  vanguard power now fails closed before sortie instead of repeatedly accepting
  an unactionable confirmation.
- The exact result-action transition lease now survives an intermediate stable
  result page until its bounded deadline, covering multi-page META results
  without relaxing unrelated stale-frame handling.
- Boss-kill reward collection, `current_dossier`, dossier auto-attack, and the
  non-one-hit branch remain conditional rather than claimed complete.

### Operation Siren exploration main path live-qualified

- A single real `OpsiExplore` invocation started at `LastZone=0` and visited
  all 72 zones in the upstream exploration order. Every visit selected the
  SAFE layer, `zone_failures` remained empty, and no dangerous zone was
  entered.
- The 1605.407-second run exercised typed panel unpin, repeated neighboring
  zone re-anchors, the bounded local-probe path, global typed-anchor recovery,
  SAFE/stronghold overlap selection, the already-at-target branch, and the
  accepted-auto-search-then-off outcome when no searchable event remains.
- Completion persisted `LastZone=0`, `SpecialRadar=false`, and
  `NextRun=2026-09-01 00:00:00`; the temporary validation configuration was
  removed. The final 56-member patch series also applied to clean upstream
  `81ccf63b` and compiled every changed Python file. Login, frame-clock, and
  pixel-inventory replays passed with no raw Android input or unclassified
  pixel access.
- Storage now observes all six tuning-sample item identities through exact
  typed item id and sprite pairs. Zero samples is a proven no-op; a nonzero
  sample count still fails closed until actual typed consumption is live
  qualified.
- `OpsiExplore` is therefore promoted from `B` to `L`, not `F`. Remaining live
  closures are a dangerous-zone run with tuning samples present, Fleet 2-4,
  `Submarine=true`, and `SpecialRadar=true`.

### Operation Siren daily empty-day branches live-qualified

- `DoMission/UseTuningSample` completed all four boolean combinations on the
  same final semantic-oracle revision. Each real task returned normally,
  scheduled `NextRun=2026-08-22 00:00:00`, and removed its temporary config.
- `DoMission=false` never opened the mission overview; `DoMission=true`
  entered and left it, excluded the persistent monthly-boss row, and observed
  zero executable daily missions. `UseTuningSample=true` entered storage and
  proved a typed zero-sample no-op; false bypassed storage exactly.
- The first no-sample mission run exposed an incorrect selected-zone
  prerequisite on the globe-level mission-overview button. The fixed oracle
  still requires the exact globe page, unique actionable button, valid bounds,
  top raycast, and no blocker, but correctly permits an unpinned globe.
- `OpsiDaily.DoMission` moves from offline-only `O` to live-boundary `B`;
  `UseTuningSample` remains `B` with stronger two-value evidence. Actual daily
  mission combat, nonzero sample consumption, Fleet 2-4, and
  `Submarine=true` remain unqualified.

### Operation Siren obscure-zone main path live-qualified

- The native observer image capacity is now `1408`. In addition to the existing
  ordinary, fleet and trailing budgets, a 384-entry rolling `walk_quad` reserve
  retains dense local-map grids and the unique obscure-zone passage on large
  maps. The rebuilt driver revision is
  `506b76f698b5089aaa29c4e7908b48edb8532a44`; the installed APK SHA-256 is
  `585b197a485c597249892047ff080ca0b4aaeeb3c7ac81ca9d74a2d3835353e6`.
- Real original-ALAS runs consumed typed obscure coordinates, selected the exact
  `OBSCURE` pin, exercised Fleets 1/2/3/4, confirmed reconnaissance and
  `Submarine=true`, completed multi-combat auto-search with submarine support,
  and separated low resolve from the left-side sunk/repair marker.
- Inventory entrance taps now retry only after re-proving an actionable typed
  coordinate card. Checkout accepts both the exact confirmation branch and the
  observed no-confirm direct globe transition, while requiring the storage page
  to disappear, the globe to be visible, and the pinned type to remain exact.
- Closing an action-point panel no longer reselects the normal base zone over an
  obscure or abyssal coordinate. The runtime waits for the same special-zone
  type to remount and fails closed if it does not. A live run with displayed scan
  base cost 5 and discounted confirmation cost 4 also established that the
  prompt cost is dynamic; its full order-specific text remains mandatory and the
  confirmed cost may not exceed the displayed base cost.
- Cleared obscure maps identify the unique
  `event_1000034/chuansong01(Clone)` passage, move it into the safe viewport,
  click it, settle walking, confirm exact exit prompts atomically, and return to
  an ordinary zone. An uncleared map's persistent title and exit hint no longer
  masquerade as a malformed passage when the passage model has not spawned.
- The post-search loot grid can remain mounted above the still-active local-map
  hierarchy. It is now recognized by the exact special-zone title, loot item
  grid and unique overlay back button, then dismissed before any passage input.
  Exit confirmation is attempted from one fresh coherent snapshot; a prompt
  that disappears between loop iterations is treated as absent and re-probed,
  never clicked through stale coordinates.
- `OpsiObscure` is promoted from `B` to `L`. `ForceRun=true` continuous looping
  and the complete abnormal-state/value matrix remain open, so this is not an
  `F` claim.

### Operation Siren monthly-boss defeat recovery hardened

- The normal Arbiter room now uses the unique typed boss radar target for
  direct attacks and exact typed grid steps while the target is outside the
  safe viewport. It no longer converts a stale legacy radar coordinate into a
  boss click.
- A defeated fleet is recognized independently through the exact low-resolve
  prompt/map marker or the left portrait repair marker. The one-button prompt
  is cancelled atomically and the fleet is remembered unavailable for the
  remainder of the session, so timeout and flagship-loss defeats do not depend
  on HP reaching zero.
- Real runs rotated Fleet 4, 2, 3, and 1 after each became unavailable and
  reached the all-fleets-exhausted branch. A separate passed bounded receipt
  re-entered the normal room, exited it, returned to the ordinary map, and
  preserved the failed-attempt scheduling branch. Full port recovery was also
  observed live, including typed Gibraltar repair and four-fleet low-resolve
  rechecks.
- Patch member `0124-operation-siren-month-boss-recovery.patch` applies to clean
  upstream `81ccf63b`; all changed upstream Python files compile. The focused
  adapter/oracle/series/matrix suite passes 596 tests, and the pixel inventory
  reports zero unclassified accesses and no Android input injection.
- `OpsiMonthBoss` remains `B`: this account still cannot prove a successful
  normal kill/reward stack or the hard-mode combat path, so those conditions
  are not promoted to `F`.
