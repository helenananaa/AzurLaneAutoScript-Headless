# Main 12-4 official auto-search validation

## Outcome

The bounded `Main` task passed one live normal 12-4 run on
`emulator-5580`. Fleet 1 was assigned the mob duty and fleet 2 the boss duty;
the submarine fleet was disabled. The official game owned every map movement
and battle after sortie. ALAS waited passively, accepted only the exact total
reward panel, then completed its normal RunCount and Scheduler bookkeeping.

The reciprocal fleet-duty order is admitted by the same exact typed contract
and has a deterministic adapter test. It was not claimed as a second live run.

## Live evidence

| Item | Result |
| --- | --- |
| Stage/mode | `12-4`, `campaign_main`, `normal` |
| Fleets | `(1, 2, 0)` |
| Duties | fleet 1 `mob`, fleet 2 `boss` |
| Official combat automation | checked; completion generation `11378` |
| Passive wait | `519.0s` |
| Accepted result | exact `LevelStageTotalRewardPanel(Clone)/Window/Fixed/ButtonExit` |
| RunCount | `1 -> 0` |
| Scheduler | disabled after success |
| ALAS combat budget | `0` |
| ALAS viewport-swipe budget | `0` |
| Raw-input fallback | not used |

The machine-readable receipt is
`integration/alas/main-12-4-auto-search-live-validation-receipt.json`. It binds
the observer revision `be80ce591a481c12d60c50d6040d40c035b40a2b` and observer
APK SHA-256
`97d9ea8c30b62d2b82a94aa7f130e8cc006318d4fe72b4aed93a2779942257da`.

## Recovery note

During qualification the game received a rendering hot patch and the AVD was
cold-booted. A diagnostic launch made with `monkey` produced the expected black
NULL-backend surface but no semantic ticks because it omitted Unity's
`-force-gfx-st` argument. Relaunching with the same single-threaded graphics
argument used by the formal ALAS runtime restored fresh typed snapshots. This
diagnostic launch is not part of the passing receipt.

## Scope boundary

This evidence covers only normal 12-4, fleets 1 and 2, one mob duty plus one
boss duty, no submarine, no 2x book, and official auto-search. Other stages,
events, task instances, fleet numbers, fleet lock, submarine use, and ALAS-owned
map combat remain separate qualification scopes.
