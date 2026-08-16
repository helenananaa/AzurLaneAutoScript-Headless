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

## Qualified daily claim and disabled value

The fresh daily invocation in
[`integration/alas/reward-daily-mission-r2-live-validation-receipt.json`](../integration/alas/reward-daily-mission-r2-live-validation-receipt.json)
enabled only `Reward.CollectMission`.  The original `Reward` task ran for
344.563 seconds, dispatched exactly one `mission.claim` at the typed
`task/claim/all` target, exhausted the grant, then used `task/page/back` and
proved the main task page was visible.  The temporary configuration was
removed after the task returned.

The companion
[`integration/alas/reward-daily-mission-disabled-live-validation-receipt.json`](../integration/alas/reward-daily-mission-disabled-live-validation-receipt.json)
sets all five Reward claim options false.  It executes the same original task,
returns to the typed main page, clears its temporary configuration, and records
an empty dispatch list.  Together with the deterministic complete boolean
replay, these two receipts qualify both declared values of
`Reward.CollectMission`; no weekly, oil, coin, or experience claim is inferred
from this qualification.
