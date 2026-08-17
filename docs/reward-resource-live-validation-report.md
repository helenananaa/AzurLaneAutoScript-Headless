# Reward resource live validation

The resource switches use the original `Reward.run()` and `reward_receive()`
path.  A resource is actionable only when its exact `bubble/Text` value is a
positive integer, its bubble Button is topmost, and the reward-summary page is
typed and generation-coherent.  A merely visible resource card is not treated
as a claim.

On `emulator-5580`, Oil was `32` before the original task, dispatched exactly
one `reward/resource/oil` input, and was `0` afterward. Coin independently
went from `108` to `0` through exactly one `reward/resource/coin` input. Exp
independently went from `8` to `0` through exactly one `reward/resource/exp`
input. Every enabled run restored the typed main page. A current
`CollectExp=false` run emitted no resource dispatches and also restored the
main page.

The receipts are `integration/alas/reward-oil-live-validation-receipt.json`,
`integration/alas/reward-coin-live-validation-receipt.json`, and
`integration/alas/reward-resource-disabled-live-validation-receipt.json` for
the earlier Oil/Coin evidence, plus
`integration/alas/reward-exp-live-validation-receipt.json` and
`integration/alas/reward-exp-disabled-live-validation-receipt.json` for the
current Exp true/false pair. All three resource switches are qualified.
