# ALAS adapter v2 login-flow inventory

Status: C01 review inventory; no behavior has moved in this step.

This document freezes the complete login-owned surface before C02 extracts the
flow. It is descriptive, not an authorization to add observations or input.
Unknown and unsupported branches remain fail-closed.

## 1. Pinned inputs

| Item | Pinned value |
| --- | --- |
| Core commit at inventory | `47d289c72c09971d28d7ac2b4b71224fd5ab1387` |
| Upstream ALAS commit | `81ccf63b4540f00241628c82a58c02c7a2bb11af` |
| Upstream `module/handler/login.py` SHA-256 | `f252a6aefe336605b3550b9d91a17e78f05e728b2be6f4c1d7b1a3beecfa3429` |
| Combined patch SHA-256 | `57ddcadc72f6d124043c5d3d6e3ddf3e0a0c16f1d5cc83f9c72764df361d320c` |
| Adapter source SHA-256 | `ab17676bd321d8cd066ab2b7e97bdbdfdbbe11e92921665c2893fa12bd7c96c1` |

The C01 review reran the A02 execute verifier. The combined patch applied to a
transient detached worktree at the pinned upstream commit, all 24 changed Python
files compiled, the transient worktree was removed, and the upstream checkout
remained clean.

## 2. ALAS ownership and entrypoints

The integration patch changes only `LoginHandler.handle_app_login()`:

1. obtain `device.semantic_adapter`;
2. call `begin_login()` before the original handler body;
3. retain the original screenshot-interval `try/finally`;
4. call `end_login()` in an outer `finally`.

The original `_handle_app_login()` loop, its branch order, timers, `continue`
behavior, `login_success` state, and completion conditions remain owned by ALAS.
The adapter must not turn that loop into a controller-side script.

Controller entrypoints are:

| Entrypoint | Current contract |
| --- | --- |
| `begin_login()` | Calls the package gate, rejects every already-active flow, then creates `_LoginFlowContext` with a 20-second passive-transition deadline. |
| `end_login()` | Clears the login context. It is idempotent and performs no observation or input. |
| `appear()` / `match_template_color()` | Preserve ALAS boolean presence semantics, including the bounded stale/foreground grace. |
| `click()` | Resolves only an exact reviewed semantic target and delegates the final input to `SemanticOracle`. |

While login is active, `begin_mission_reward`, `begin_mail`, `begin_commission`,
`begin_tactical`, `begin_research`, `begin_dorm`, `begin_build`, and
`begin_campaign_pre_sortie` all reject nesting. `begin_login()` likewise rejects
itself and every other active flow.

## 3. Context and timers

`_LoginFlowContext` has exactly two fields:

| Field | Reads | Writes |
| --- | --- | --- |
| `passive_transition_until` | Suppresses a repeated login-entry probe after its click; permits unknown presence probes to return false during a bounded transition; admits transient observer/foreground failures. | Initialized to `now + 20s`; set to `now + 60s` after selected reviewed login clicks. |
| `entry_receipt` | Prevents a repeated `LOGIN_CHECK` result during the passive transition. | Set only after a successful `login/enter` click. |

`_observer_stale_since` is adapter-wide rather than login-owned. `appear()` treats
the three existing snapshot-coherence messages as transient. It also treats
`game activity is not top-resumed` as transient only while login is active.
Those failures return `False` during the login transition or for at most five
seconds from the first stale observation, then raise unchanged.

ALAS additionally owns its `confirm_timer`, `orientation_timer`, per-resource
interval timers, and local `login_success` flag. C02 must compare those timer and
sleep boundaries without moving them into the adapter.

## 4. Exact observation inventory

There are no dynamic login resource patterns.

| ALAS resource or branch | Primitive | Semantic observation(s) | Current result and context effect |
| --- | --- | --- | --- |
| `MAIN_GOTO_CAMPAIGN_WHITE` | `appear` via `is_in_main()` | `enabled("main/battle")` | One of the two exact proofs that ALAS reached main. |
| `MAIN_GOTO_FLEET` | `appear` via `is_in_main()` | `enabled("main/formation")` | The second exact main-page proof. |
| `LOGIN_CHECK` | `match_template_color` / `appear` | Registry handler calls `enabled("login/enter")`. | Returns the exact enabled state. After an entry receipt and inside the passive window it returns `False` without a package-gate or oracle call. |
| `LOGIN_ANNOUNCE`, `LOGIN_ANNOUNCE_2` | `appear` | `enabled("overlay/bulletin/close")` | Both aliases deliberately share one exact target. |
| `POPUP_CANCEL` | `appear` | `enabled("overlay/network-reconnect/cancel")` | Presence half of ALAS' normal confirm-pair check. |
| `POPUP_CONFIRM` while login is active | `appear` | In order: `enabled("overlay/login-data-expired/confirm")`, then `enabled("overlay/network-reconnect/confirm")`. | `True` for exactly one target, `False` for none, and gate-closed for two. This contextual branch currently does not invoke a new package gate before these reads; `begin_login()` already gated entry. |
| `POPUP_CONFIRM_WHITE` | `appear` | `enabled("overlay/login-data-expired/confirm")` | Exact white expired-data confirmation branch. |
| unknown direct login assets | `appear` | No asset-specific observation. | `False` only while the passive window is active or `_known_login_surface_exists()` independently proves a reviewed surface; otherwise raises `AlasSemanticUnmapped`. |
| `GOTO_MAIN` | `appear` | `_goto_main_target()` probes the reviewed page roots below. | `True` only when exactly one reviewed return target exists; ambiguity raises. |

`_known_login_surface_exists()` first calls `campaign_is_in_map()`. Either boolean
result proves that the oracle recognized a reviewed campaign/main/startup
surface. If that typed query closes, it falls back to `enabled()` checks for:

- `overlay/bulletin/close`;
- `overlay/network-reconnect/confirm`;
- `overlay/login-data-expired/confirm`.

`_goto_main_target()` admits exactly one of:

- `campaign-menu/page/back`, proven by `campaign_menu_is_entry()` plus enabled;
- `build/page/back`, proven by typed build queue state plus enabled;
- `task/page/back`, proven by exact root existence plus enabled;
- `research-menu/page/back`, proven by exact root existence plus enabled;
- `research/page/back`, proven by exact root existence plus enabled.

Zero targets means absent. More than one target is ambiguous and gate-closed.

## 5. Exact action inventory

Login currently has no dedicated action-budget field. This is frozen behavior for
C02 parity, not approval for a future nonzero production policy.

| ALAS resource | Exact action target | State mutation after receipt |
| --- | --- | --- |
| `LOGIN_CHECK` | `login/enter` | Store `entry_receipt`; extend passive transition to 60 seconds. |
| `LOGIN_ANNOUNCE`, `LOGIN_ANNOUNCE_2` | `overlay/bulletin/close` | Extend passive transition to 60 seconds. |
| annotated `POPUP_CONFIRM_WHITE_LOGIN` | normalized to `POPUP_CONFIRM_WHITE`, then `overlay/login-data-expired/confirm` | Extend passive transition to 60 seconds. |
| annotated `POPUP_CONFIRM_LOGIN` | normalized to `POPUP_CONFIRM`, then the unique target from `_login_popup_target()` | Expired-data confirm extends the transition. Network-reconnect confirm currently does not. |
| `GOTO_MAIN` | the unique target returned by `_goto_main_target()` | No login-context field changes. |

Every action goes through the package gate before `oracle.click()`. The
contextual normal-confirm target is selected before that click-time package gate;
C02 must preserve this observable ordering. Reordering it is a later reviewed
safety change, not extraction parity.

`POPUP_CANCEL` is observed by `handle_popup_confirm('LOGIN')` but is not clicked
by that ALAS branch. Unknown clicks remain `AlasSemanticUnmapped` or a more
specific flow-context failure.

## 6. Original LoginHandler branch accounting

The following table accounts for every branch in pinned
`LoginHandler._handle_app_login()` and the reachable `ui_page_main_popups()`
call. “Unsupported” means the branch is intentionally not made true by semantic
mode; it does not mean ALAS may fall back to pixels or coordinates.

The direct handler's complete static resource set is:

`ANDROID_NO_RESPOND`, `AVATAR_EXPIRED`, `BACK_ARROW`, `EVENT_LIST_CHECK`,
`GOTO_MAIN`, `LOGIN_ANNOUNCE`, `LOGIN_ANNOUNCE_2`, `LOGIN_CHECK`,
`LOGIN_GAME_UPDATE`, `LOGIN_RETURN_INFO`, `LOGIN_RETURN_SIGN`, and
`MAINTENANCE_ANNOUNCE`.

The called main-popup method adds this complete static set:

`BATTLE_PASS_NEW_SEASON`, `BATTLE_PASS_NOTICE`, `GET_ITEMS_1`, `GET_ITEMS_2`,
`GET_SHIP`, `META_CHECK`, `MONTHLY_PASS_NOTICE`, `PLAYER_CHECK`, and
`SHIPYARD_CHECK`, while reusing `BACK_ARROW`, `EVENT_LIST_CHECK`, `GOTO_MAIN`,
`LOGIN_ANNOUNCE`, `LOGIN_ANNOUNCE_2`, and `LOGIN_RETURN_SIGN`. Its delegated
helpers additionally probe `GUILD_POPUP_CONFIRM`, `GUILD_POPUP_CANCEL`,
`GET_MISSION`, and `POPUP_SINGLE_WHITE`. `handle_popup_confirm('LOGIN')` probes
`POPUP_CANCEL`, `POPUP_CONFIRM`, and `POPUP_CONFIRM_WHITE`; ALAS temporarily
annotates the clicked confirm name with the `_LOGIN` suffix.

| Original ALAS branch | Current semantic disposition |
| --- | --- |
| orientation watch and screenshot | ALAS retains timing and lifecycle ownership. Semantic mode supplies no pixel evidence. |
| `is_in_main()` and confirm timer | Closed by exact `main/battle` or `main/formation` presence; ALAS retains the four-count timer and loop break. |
| `LOGIN_CHECK` | Exact read and exact click supported. |
| `ANDROID_NO_RESPOND` | Unsupported presence. It is safely false only during bounded login grace or on a separately proven login surface; otherwise the foreground/unknown failure propagates. Its raw system-dialog click is never authorized. |
| `LOGIN_ANNOUNCE`, `_2` | Exact shared bulletin-close read and click supported. |
| `EVENT_LIST_CHECK` then `BACK_ARROW` | Not admitted as a login-owned event-list branch. Presence remains false/closed, so the generic back click is unreachable. |
| maintenance announce and game update | Unsupported presence; false only under bounded/proven login surface, then closed if the surface cannot be proven. |
| CN user agreement | Pixel color search has no semantic contract. A raw agreement swipe requires campaign-map scope and closes; a dynamic `AGREEMENT_CONFIRM` click is unmapped. |
| return sign, return info, avatar expired | Unsupported presence; false only under bounded/proven login surface. No click is authorized. |
| normal and white login confirmation | Exact expired-data/network-reconnect observations and exact confirm clicks are supported as listed above. Ambiguity closes. |
| urgent commission (`GET_MISSION`) | Not admitted in login scope; presence remains false/closed and its click is unreachable. |
| main popup: guild, reward popups, ship reward, monthly/battle notices, item/mail popup, shipyard/meta/player recovery | Not admitted as login-owned resources. They remain false only under bounded/proven login surface. No associated click is authorized. |
| main popup: login announcements | Exact bulletin-close support is reused. |
| main popup or final `GOTO_MAIN` | Supported only through one unique reviewed return target. Generic back or raw coordinates are not used. |
| successful return | ALAS returns `True`; the integration `finally` closes login scope and restores screenshot interval. |

## 7. Package-gate and oracle call order

The C02 parity fixture must compare these sequences exactly:

1. `begin_login`: package gate, then nesting check, then context creation.
2. fresh `LOGIN_CHECK`: package gate, then one `enabled("login/enter")`.
3. repeated `LOGIN_CHECK` after entry receipt inside grace: no package gate and no
   oracle call; result is `False`.
4. mapped ordinary presence: package gate, then one target read.
5. contextual `POPUP_CONFIRM` presence: two ordered candidate reads until tuple
   construction completes; no additional package gate in this helper.
6. unknown presence: package gate, then passive deadline or known-surface proof.
7. exact click: resolve contextual alias if any, package gate, `oracle.click`, then
   receipt/context mutation.
8. `GOTO_MAIN`: package gate before the target-discovery reads and exact click.
9. `end_login`: no package gate and no oracle call.

The flow contains no sleep call in the adapter. ALAS owns all sleeps, screenshot
intervals, interval timers, and loop retries.

## 8. Exceptions and fail-closed outcomes

| Condition | Current outcome |
| --- | --- |
| Login begins while any flow is active | `SemanticGateClosed("nested semantic ALAS flow is not allowed")` |
| Package identity is not admitted | Original package-gate exception propagates. |
| Both login confirm candidates are enabled | `SemanticGateClosed("login popup target is ambiguous")` |
| Login confirm click has no unique candidate | `SemanticGateClosed("login popup identity is not proven")` |
| Unknown presence outside bounded/proven login surface | `AlasSemanticUnmapped` |
| Unknown or context-invalid click | `AlasSemanticUnmapped` or the exact existing flow-context error |
| Stale/coherence failure inside grace | `False`; after the bounded window the original exception propagates. |
| Activity not top-resumed during login handoff | `False` only within the bounded login/stale grace; then the original exception propagates. |
| Raw agreement/system-dialog input | Rejected by semantic raw-input/campaign-scope checks or unmapped-resource checks. |

No exception may be translated into a broad `False` outside the existing bounded
presence rules.

## 9. Evidence and known gaps

Existing checked tests cover:

- exact login entry appearance/click and receipt mutation;
- bulletin close and bounded unknown presence;
- nested-flow rejection;
- expired-data popup selection and click;
- stale snapshot and foreground-handoff grace;
- B05 old/new `LOGIN_CHECK` result, oracle-call, package-gate, and exception
  parity;
- proof that only `LOGIN_CHECK` currently enters the registry;
- integration-patch `begin_login()` / `end_login()` ownership hooks.

Known gaps that C02-C04 must not conceal:

- there is no pinned Device-free replay of the complete original login loop;
- there is no live qualification for maintenance, update, Android dialog, CN
  agreement, returning-player, avatar-expired, or the broad main-popup set;
- the B05 result frame is an explicitly unbound read-only compatibility envelope,
  not an atomic observer frame and not action evidence;
- registry dispatch does not yet emit the final structured trace required by the
  later frame/policy milestones;
- current login actions have no dedicated budget and must not imply a nonzero
  production policy;
- normal reconnect confirm does not extend the passive window, unlike the other
  recorded login clicks.

## 10. C01 exit decision

Every branch in the pinned original login handler and every login-context branch
in `AlasSemanticAdapter` is classified above as exact-supported,
bounded-presence-only, or fail-closed unsupported. No dynamic pattern or hidden
budget remains unlisted.

C02 may now extract login mappings, context logic, and derived observations into
the login flow module, but it must keep the old implementation as the parity
oracle and must not add a resource, action, budget, live input, or broader false
fallback.
