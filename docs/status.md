# Validation status

Status is evidence-scoped. A later gate is not implied by an earlier pass.

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
- Nine malformed/bounds cases fail closed. No event PT or coin was read from a
  live account, no task was actually disabled, called, delayed, or stopped, and
  no Android input occurred. Live promotion still requires typed page-specific
  PT/coin observations, server/local-time correlation, and scheduler recovery
  receipts proving the target task starts without a loop; only offline
  dimensions are promoted here.

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
- The pinned ALAS `enhance_ships()` task now delegates semantic mode before any
  legacy framebuffer/random-type branch. It passes `ShipToEnhance`,
  `CheckPerCategory`, and `Filter` unchanged into the strict policy and returns
  the observed number of consumed ships instead of a hard-coded increment.
- A separate default-zero `enhancement.execute` budget, translated from
  `ALAS_SEMANTIC_ENHANCEMENT_BUDGET`, bounds official recommendation attempts.
  `all`/`favourite` switching, the eight ship-type
  filter mappings, candidate-card identity, enhancement-tab entry, return, and
  default Dock reset are semantic-only. A live non-destructive smoke exercised
  favourite on/off, `dd`, one exact candidate (`格里芬`), enhancement preview
  with zero selected materials, back, and reset; no recommendation or confirm
  was clicked in that smoke.
- The complete ALAS task loop is deterministic-test covered for ordered filters,
  per-category checking, no-material skips, budget exhaustion, cleanup, invalid
  configuration, and default denial. A full `favourite` destructive task and a
  naturally empty-material live branch remain unrun to avoid unnecessary ship
  consumption; those are evidence gaps, not pixel fallbacks.

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

### Exercise consumed configuration: offline contract passed

- `ExerciseStrategy` accepts the eight values declared by pinned ALAS,
  `OpponentChooseMode` accepts its four declared modes, and `OpponentTrial`
  accepts exact positive integers. `LowHpThreshold` is bounded to `0..1`,
  `OpponentRefreshValue` to integer `0..6`, and `OpponentRefreshRecord` to a
  bounded naive datetime. The guard is the first executable statement in
  `Exercise.run()`, before page entry, opponent inspection, or combat.
- Pinned replay covers all 488 strategy/hour decisions for hours 0 through 60,
  including ALAS's hour-zero behavior and every Friday-to-Sunday consumption
  window. It also preserves each mode's opponent ordering, the `leftmost`
  detail-scan bypass, normal mode dispatch, and trial success/exhaustion
  boundaries for 1, 2, and 3 attempts. Frozen-server-time replay additionally
  covers all seven same-day refresh values, previous/future-day zeroing, and
  five in-task increments; low-HP replay covers strict `0.01`, inclusive
  configured thresholds, confirmation pending/reached/stale, and defender-bar
  disappearance.
- The contract enumerates 10,752 representative valid combinations and rejects
  40 invalid single-field cases. The original zero-trial fallback is recorded
  as unreachable compatibility evidence because zero now fails closed.
- Mutation budget is `0`: opponent OCR/state, scheduler, and combat calls are
  fixtures, with no real Exercise attempt, battle, screenshot/OCR, page input,
  or Android injection. These six consumed fields are `offline=complete` only;
  live opponent power/levels and period observation, refresh persistence,
  semantic HP observation, actual retries/fights, settlement, and failure
  recovery remain incomplete.
- `LowHpConfirmWait` is explicitly unsupported in pinned upstream: it is
  declared and documented, but no runtime method reads it, while combat creates
  `Timer(1.5, count=2)` unconditionally. Re-enter only with an upstream-owned or
  separately reviewed mapping from the field to that timer plus deterministic
  elapsed-time and live semantic-HP evidence; this patch does not invent one.

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

### Game Manager restart configuration: offline contract passed

- `GameManager.AutoRestart` admits exact booleans before the original task can
  stop the app. Invalid values fail before normal or semantic lifecycle calls.
- Pinned replay preserves stop-only behavior for `false`, stop/start/login for
  normal `true`, and semantic cold-restart/login for Headless `true`, covering
  both backend modes without replacing the original task entry.
- Device and semantic lifecycle methods are fixtures. Mutation budget is `0`;
  no real process stop, start, login, or Android input occurs.
- The field moves only to `offline=complete`. Existing live evidence covers
  one enabled cold restart; disabled mode, already-stopped state, start/stop
  failures, login failure, and retry bounds remain live gaps.

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

### Benchmark device and scene configuration: offline contract passed

- `Benchmark.DeviceType` admits exactly the five values declared by pinned
  ALAS, while `Benchmark.TestScene` admits screenshot, click, or their combined
  scene. Both fields are validated before the original task can uninstall an
  app, navigate, benchmark a device method, or enter the semantic branch.
- Pinned normal-backend replay covers the complete 5 x 3 matrix and preserves
  original SDK-30 candidate filtering, including Plone and VMOS differences.
  Semantic replay preserves screenshot-only, click-only, and combined observer
  selection without pretending the legacy device type changes semantic timing.
- Twelve invalid single-field cases fail before any entry event. All benchmark,
  observer, and input operations are fixtures: mutation budget is `0`, no real
  uninstall/navigation/benchmark or Android input occurs.
- Both fields move only to `offline=complete`. Device-specific timing quality,
  unavailable transports, and live screenshot/click capability remain live
  evidence requirements.

### Dorm collection, feeding, and food filter configuration: offline contract passed

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
- Dorm methods are deterministic fixtures: mutation budget is `0`; no reward
  collection, food consumption, navigation, screenshot/OCR, or Android input
  occurs. The fields move only to `offline=complete`; live empty-collection,
  partial food inventory, post-feed food/capacity proof, and recovery failures
  remain open.

### Dorm furniture configuration: interval and option decisions passed offline

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
- Payment entry, OCR, confirmation, page recovery, and Dorm scope are all
  recorders. Mutation budget is `0`: no navigation, furniture purchase, coin
  consumption, or Android input occurred. Only the three fields' offline
  dimension is promoted; live countdown/ownership, balance/price, purchase
  receipt, and recovery evidence remain incomplete, so Dorm stays `L`.

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

### Battle Pass collection switch: offline dispatch contract passed

- `BattlePass.Collect` admits only exact booleans. Its guard is the first
  executable statement of `Freebies.run()`, before any BattlePass, DataKey,
  Mail, or SupplyPack child can be constructed.
- Replay executes both original dispatch branches. Disabled mode retains Mail
  without touching BattlePass; enabled mode preserves BattlePass before Mail.
  The final `task_delay(server_update=True)` remains exact in both cases.
- Seven non-boolean values fail at zero events. Every child is a recorder;
  mutation budget is `0`, and no navigation, reward claim, or Android input
  occurs. Only `offline` becomes complete. Real entrance/red-dot observation,
  free versus paid rewards, no-reward handling, claim receipts, and recovery
  remain incomplete, so Freebies stays `P`.

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
- `OpsiShop.PresetFilter` covers all five declared presets from pinned
  `OS_SHOP`; `CustomFilter` preserves custom priority and blank fallback.
  CL1 and exhausted-count exclusions remain original. Unknown presets,
  malformed types, and invalid tokens fail before item pretreatment, with no
  purchase, refresh, currency mutation, or Android input.
- `OpsiVoucher.Filter` runs pinned `voucher_redirect()` and the original shop
  grammar, preserving Logger expansion, tier expansion, archive-token removal,
  Unicode separators, and intentional empty skip. Invalid tokens and types fail
  before voucher-page work; no exchange, scrolling, or Android input occurs.
- `OpsiAshAssist.Tier` preserves the original tier-visibility wait, OCR
  comparison, up to five beacon rotations, and current-beacon fallback for
  exact integer thresholds. Malformed values fail before the first page
  observation or click. No artificial level range is imposed because pinned
  ALAS declares none.
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
- One hundred thirty valid classes pass and 216 malformed values fail before task,
  scheduler, map, combat, coordinate, or inventory state changes. Mutation
  budget is `0`; all effects are recorders, with no combat, item consumption,
  or Android input. Twenty-eight fields now have complete offline classification.
- The previous AST-only audit incorrectly treated dynamically constructed
  `deep_get()` paths as absent consumers. Source-bound replay now verifies
  those string consumers explicitly. Only `OpsiMonthBoss.ForceRun` and
  `OpsiDaily.DoMission` remain zero-read in pinned upstream and explicitly
  unsupported; Headless does not invent behavior for them.
- Real coordinate use, navigation, fleet filtering, combat, rewards, and
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

### Data Key collection configuration: offline contract passed

- `DataKey.Collect` and `DataKey.ForceCollect` admit exact booleans at the
  beginning of original `Freebies.run()`, before BattlePass, DataKey, Mail, or
  SupplyPack can navigate. Disabled DataKey collection still preserves Mail
  and next-server-update scheduling.
- Pinned replay covers all four switch combinations and 12 invalid
  single-field cases. Original `DataKey.data_key_collect()` is also replayed
  for already-collected, exact-full forced/unforced, and one-slot-free states.
- The real `_data_key_collect()` loop is never called. Mutation budget is `0`,
  with no key receipt, page input, popup confirmation, or Android injection.
- Both fields move only to `offline=complete`. The existing 300/300 live
  observation is not evidence for forced collection, a new key receipt,
  capacity-limit popup handling, or post-claim inventory changes.

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

### SupplyPack collect and weekday configuration: offline contract passed

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
- The real `supply_pack_buy()` method is never called; replay records only
  whether ALAS would produce a free-pack candidate. Mutation budget is `0`,
  with no claim, item change, page input, or Android injection. Both fields
  move only to `offline=complete`; current live absence is not a claim receipt.

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

### Daily fourteen-field configuration: offline contract passed

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
- All fourteen fields move only to `offline=complete`. Existing observation,
  action, and live statuses remain unchanged; only Tactical Training stage two
  with its current fleet has prior live closure.

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
- These results use mutation budget `0` and no Android input. No live student
  assignment or book consumption was attempted. Remaining evidence includes a
  Tactical-context live proof of the typed favourite control and candidate
  state, real book inventory/current-skill-exp observation, and a stable exact
  assignment postcondition with a safe rollback. Therefore only `offline` is
  complete for these eight fields; live/action status is unchanged.

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
- The ALAS-name bridge maps only 14 reviewed aliases for seven main-page
  semantics. It independently verifies version, ABI, base APK, and IL2CPP
  hashes. Unmapped assets and raw multi-click/long-click/swipe/drag calls raise
  instead of injecting coordinates.

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
