# PulsarMLX F017 DPREFIX-REAL-1 Numerical-Surface Non-Execution Review

## Verdict

`DENSE-PREFIX M1-F(-1) NOT EXECUTED`

The released package passed its historical identity preflight, candidate
self-verification, and host admission. A deeper checkpoint-free execution
surface reconciliation nevertheless proved that the frozen real Tier-B
qualification cannot be instantiated from the reviewed executable and oracle
outputs.

The exact candidate binary records intermediate stage SHA-256 identities and
retains the final layer-3-entry vector, but it does not retain intermediate
candidate values or independently derived max-absolute-error, RMSE, and cosine
metrics. The instantiated oracle similarly returns intermediate hashes plus
the final vector. The frozen Tier-B contract requires per-layer and
intermediate-attention numerical metrics, while the terminal evidence schema
requires at least five numerical surfaces. Hash pairs cannot derive those
metrics.

Crossing the consumption boundary would therefore guarantee an unqualifiable
consumed attempt. Execution stopped before any checkpoint file was opened for
a payload and before any positional read.

## Banked evidence

- Raw evidence:
  `docs/architecture/reviews/evidence/f017-dense-prefix-real-attempt-1-not-executed-numerical-surface-v1.json`
- Raw evidence SHA-256:
  `a730fb123fd86319b199579c79bdcbff1b282b7f7ec4003daa694f9e37a176b6`
- Append-only attempt-ledger successor:
  `docs/architecture/reviews/evidence/f017-dense-prefix-attempt-ledger-v3.json`
- Attempt-ledger SHA-256:
  `1de57b2ce2a4e5e50e698394ba960cb4390242dcd88982df92f4cdb5649242a5`
- Real-payload ledger remains SHA-256:
  `a0edafdcd0279fb28e08c69a86a9c95ddd19e013b73a1e92f7620734456a9339`

## Preserved state

- Attempt: `DPREFIX-REAL-1`
- Authorized: true
- Consumed: false
- Executed: false
- Checkpoint accessed: false
- Payloads / packed bytes read: `0 / 0`
- Ledger: `59 -> 59`
- Automatic retry: false
- Automatic representative M1-F0 continuation: false
- Real layer-3 state: not created

The candidate executable, oracle package, config, authorization binding,
prompt, 40-entry allowlist, Q4/Q6 identity gates, numerical thresholds, and
all historical evidence remain unchanged.

## Required remediation

Prepare and independently review successor candidate/oracle execution surfaces
that retain paired numerical values (or derive the frozen metrics inside an
independently auditable boundary) for every required Tier-B stage. That work
must produce a new exact executable/package identity and a new release. The
current attempt remains unconsumed; no execution retry or downstream action is
authorized by this evidence.
