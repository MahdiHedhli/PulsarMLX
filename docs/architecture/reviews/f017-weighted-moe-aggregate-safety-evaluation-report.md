# F017 Weighted-MoE Aggregate Safety Evaluation

Disposition: `ROUTE NOT PROVEN INVARIANT`.

The checkpoint-free analytical consumer evaluated the unchanged frozen
weighted-MoE aggregate theorem from the eight reuse-authorized canonical expert
down outputs. Two fresh evaluations produced byte-identical public evidence.

## Bound inputs

- starting head: `e36179c3642bd326c898a9dfa09fe2a48a56c99e`
- aggregate theorem: `ff1a15c29b79681458d74452c8c72dde9c9bf5eb44637d05a7e4ea9eb1525fac`
- route evidence: `a4f3e1afe84be2cade1ed6c1728b2f82cd0ff2d22e8a964779f3216baf124eb4`
- coefficient evidence: `834eefb7e0f127e12768285097dc3601135c1c1ff8ef0e871d65f59af1bc6b1f`
- output reuse authorization: `b370d3c3dd938eeadd18f34fabab89077319b979b994b97ffa33afddf2bffa28`
- selected experts: `[250, 10, 237, 73, 62, 177, 218, 28]`
- joint selected-weight sum: `[2.4999999999999996, 2.5000000000000004]`

## Frozen-theorem result

- nominal aggregate LE-f64 SHA: `5a30a81b6e10b126ac22a3be991e5f5c6486372068888f699625b684eb85fc70`
- direct enclosure SHA: `fd90befc19705ad086dba33e6d76bb2b1480c7d9f8999d9da7ead3cc6b7eeb93`
- centered enclosure SHA: `b117198b8402f34b35ba6f57a036b03fb596c88b405117e4c562450b5d07edc4`
- sound intersection SHA: `adbbbef090c4d10acc80d0216cc82b5a8dbe299dad4baad1a0d957f661762a50`
- maximum-absolute perturbation: `1.3373477198218997e-05` — PASS, factor `1168.357321615716`
- RMSE perturbation: `2.0649012042555876e-06` — PASS, factor `3783.4739908616907`
- cosine lower bound: `0.9990571244636769` — FAIL, factor `0.10605853704716413`
- global aggregate safety factor: `0.10605853704716413`
- mathematical aggregate qualification: FAIL
- engineering H=2: FAIL

The failed cosine enclosure is load-bearing under the frozen all-three-budgets
rule. No theorem, guard, coefficient threshold, or R10 budget was changed.

## Preserved facts and isolation

- selected-set membership: 1,984 / 1,984 PASS
- coefficient qualification: 0 / 8 FAIL
- REAL-1, REAL-2, and REAL-3: REJECTED unchanged
- DPREFIX-EXACT-1: canonical unchanged
- checkpoint reads: 0
- shard opens: 0
- real-payload ledger: 163 -> 163
- representative M1-F0: not authorized and not executed

Next action: independent review of the aggregate failure. Do not change the
frozen theorem or budgets.
