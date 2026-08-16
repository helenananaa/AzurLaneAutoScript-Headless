# Reward mission live validation

## Scope

This validation uses the pinned upstream ALAS commit
`81ccf63b4540f00241628c82a58c02c7a2bb11af`, CN client 9.7.10 on
`emulator-5580`, and observer revision
`be80ce591a481c12d60c50d6040d40c035b40a2b`.

Only `Reward.CollectWeeklyMission=true` was enabled.  Oil, coin, experience,
and daily-mission collection were explicitly false in the temporary ALAS
configuration.  The original `Reward` task kept ownership of page navigation,
scheduling, and the weekly task flow.

## Qualified weekly claim

[`integration/alas/reward-weekly-mission-live-validation-receipt.json`](../integration/alas/reward-weekly-mission-live-validation-receipt.json)
records a passing original-ALAS invocation:

- it entered the typed main task control, selected the exact weekly tab, and
  dispatched exactly one `mission.claim` input at
  `TaskListForWeekPage(Clone)/task_progress/get_btn`;
- the single mission-claim grant was exhausted after that dispatch;
- the adapter accepts only the typed AwardInfo/AwardInfo1/NewShipUI receipt
  chain.  A real deferred `NewShipUI` was observed and closed through the
  exact `reward/new-ship/continue` semantic target during this qualification;
- cleanup used the typed task back control and proved the main task page was
  visible again.  The temporary configuration was removed.

The test covers both boolean values at the configuration boundary: the
existing deterministic Reward replay covers `false`, and this invocation
covers the enabled value and one real claim.  Missing progress rewards produce
no input; ambiguous task identity, unknown popups, or an excessive receipt
chain remain closed rather than being dismissed with a generic screen tap.

## Daily row status

[`integration/alas/reward-mission-live-validation-receipt.json`](../integration/alas/reward-mission-live-validation-receipt.json)
is retained as a diagnostic historical run, not a passing qualification.  It
proves that original `Reward.reward_mission()` dispatched one exact numeric
row target and exhausted its grant, but its old runner called `close()` on the
adapter instead of its session after the ALAS call had returned.  The runner
has since been corrected and the row-center/AwardInfo primitive has been
checked on the device, but a fresh original-ALAS daily-row pass is still
required before `Reward.CollectMission` or the whole Reward panel can be
marked fully supported.
