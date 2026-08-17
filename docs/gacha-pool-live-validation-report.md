# Gacha pool live validation report

## Scope

This validation completes the five declared `Gacha.Pool` values with the
original ALAS `Gacha` task.  Every receipt starts from an empty typed
construction queue, records the configured pool and the actually selected
normal pool, verifies the exact cube/coin delta, and removes its temporary
configuration.

| Configured pool | Actual result | Receipt |
|---|---|---|
| `light` | Original task submitted one Light order. | `integration/alas/gacha-light-daily-seed-validation-receipt.json` |
| `event` | Original task submitted two Event orders. | `integration/alas/gacha-event-two-live-validation-receipt.json` |
| `heavy` | Original task submitted and quick-finished one Heavy order: 2 cubes, 1500 coins, and one quick item. | `integration/alas/gacha-heavy-r1-live-validation-receipt.json` |
| `special` | Original task submitted two Special orders. | `integration/alas/gacha-special-two-live-validation-receipt.json` |
| `wishing_well` | The fifth entry was unavailable.  The original `gacha_goto_pool()` returned `light`; the task then submitted and quick-finished one Light order: 1 cube, 600 coins, and one quick item. | `integration/alas/gacha-wishing-well-unavailable-r2-live-validation-receipt.json` |

The Wishing Well case is not presented as a fifth-pool construction.  It is a
real execution of the pinned original fallback contract for an unavailable
Wishing Well: configured `wishing_well` deterministically routes to Light.
When the seasonal fifth entry is available, original ALAS instead requires a
manual Wishing Well configuration and refuses to automate that user-owned
selection.
