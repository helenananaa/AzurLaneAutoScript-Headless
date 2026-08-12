# G36 controlled-input arming

I02 introduces `scripts/python/qualify_g36_controlled_input.py` as the only
entry point for the I03 mutation gate. Its default mode is a read-only plan
that validates the accepted H05 bundle and I01 policy, then prints the exact
E3 target, capability, one remaining action, 30-second deadline,
`qualification-stop` recovery, policy hash, and resolved output directory.
It prints no serial or account data.

Mutation requires both `--execute` and `--allow-semantic-input`. Either switch
alone is rejected during argument validation. With both switches present, an
existing output directory is rejected without changing it. I02 deliberately
does not fall back to the H05 setup qualifier; the actual one-shot operational
call is connected and invoked as the next, explicit I03 gate.

Plan example:

```powershell
$env:PYTHONPATH = 'python'
python scripts/python/qualify_g36_controlled_input.py `
  --serial emulator-5580 `
  --alas-root H:\program\AzurLaneAutoScript-g36-h05 `
  --output-directory artifacts\g36-i03
```
