# G36 qualification-only one-click policy

I01 adds an inert, checked-in generator input at
`integration/alas/policies/g36-one-click.generator.json`. It is not a default
run policy and cannot be loaded by the normal `run-policy/v1` loader. It
contains no local evidence path, serial, PID, account value, or production
enablement.

The generator accepts only the checked H05 bundle and binds both its signed
bundle SHA-256 and a canonical stable identity covering the runtime, map,
original ALAS decision, exact E3 top-raycast target, original `_goto()` call
order, defensive closure, and stop boundary. The resulting qualification
envelope contains a standard run policy with exactly one
`campaign.grid_click`, a 30-second deadline, and
`qualification-stop` recovery. It explicitly reports
`production_enabled=false`.

Generate an ephemeral envelope into a new local path with:

```powershell
$env:PYTHONPATH = 'python'
python scripts/python/build_g36_one_click_policy.py `
  --output artifacts/g36-i03/live-policy.json
```

The command refuses an existing output. Changing any run-policy identity,
H05 bundle field, exact target identity, authority amount, deadline bound,
recovery, or production marker fails closed. I01 does not connect this policy
to the live qualifier and injects no input; dual arming is added only in I02.
