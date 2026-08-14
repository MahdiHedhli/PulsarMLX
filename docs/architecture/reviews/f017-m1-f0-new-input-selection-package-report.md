# PulsarMLX F017 M1-F0 New-Input Selection Package Report

## Outcome

`BLOCKED — M1-F FIXTURE FAMILY UNSUITABLE`

The complete eight-fixture family is immutable and checkpoint-independent, but
the pre-frozen planning estimator shows it is not a responsible bounded real
experiment under the unchanged `S >= 4.0` route-stability gate.

## Identity and prior disposition

- starting SHA / remote SHA: `1fe04c22a00f1a36ec73ee4d8c9f7a65ee909ce2`
- docs-only descendants at start: none
- accepted route evidence: `980b6a78ae04b816e1f9e563790f5a2d123723292dd0432a0218972d0f80593e`
- stability contract: `da05364470f7fc5fbdc930441be1ea269af01b6a87173df34e467bcc0b0df9d7` (unchanged)
- fixture 1: accepted as oracle route discovery; unsuitable for production
  route freeze; safety factor `0.5609105150995247`
- expert-specific M1-F inventory: not frozen

## Real-payload ledger

The new evidence-derived ledger SHA is
`4c18419f4fdffce931ddf8bfab6a15164cce65578ad830290ed0c1d636f152a5`.
Its exact total is 45 payload reads. The reported 37 was a scoped subtotal; it
omitted M1-C (1), M1-D attempt 3 (1), and M1-E attempts 1 and 3 (6). M1-B's
28,444 storage reads remain recorded as checkpoint identity/catalog/header
scans and contribute zero tensor payloads.

## Fixture family

The family preserves the existing checkpoint-independent random-normal fixture
semantics because no previously accepted realistic hidden-state distribution
exists. It uses CPython 3.13.13, NumPy 2.4.5, PCG64, layer 3, position 0, DSA
`range_fill([0])`, width 6,144, and the existing signed-zero/subnormal/dynamic-
range stress prefix.

| Ordinal | Seed | Fixture SHA-256 | Package SHA-256 | Hidden SHA-256 |
|---:|---:|---|---|---|
| 0 | 17017007 | `fcfb85468c77664d94112d81ef647c5419d5bdd594bb604df970e499f488e5d5` | `8e83938f78631fdc858979d78614f4fec97e7086c7e360997ff524967f55f009` | `df90c07d4138ddb38ec7a74ed0970ecd1dceaaa86765c976960189eb5d73fb43` |
| 1 | 17017008 | `d54fd138220c23afd13b2061ba5fd52dd80ebbbcc9727d61fd4d05da3f74b96d` | `6cdaa0d88886b649c623a80916e520eb2dea902aa354b23f67b0b5a2d4832886` | `2cdcefce9f2bb33cd2df9e06809d316c8c1e85b05791ad5606b138b3f8c32ded` |
| 2 | 17017009 | `5c8e554ae200671954ab1b54b5ae933bc5e9532aaf30af1467d3e6e453275546` | `d693ae13c987eb4fa24fdeecebeb95990a4320f16dd47cec09fd65c948a12907` | `8e87171a7a775f638ed60977d1c010f5c77b86a9ac150e943f091db8cdf2b17a` |
| 3 | 17017010 | `b51e51059114559c93fab6f7e07ac1ae4174a60cc4aead7dfa5395ff1f18dcae` | `dfaed14db2f36ceba7a1832d3080316ac18bfcec86ed0fb406e9d2915554a0fe` | `51e43f9a7bf4ae147c14efa3d1b6786ffef52a93b3cda6dac62a44620edc25dd` |
| 4 | 17017011 | `b4691d6dda8a612fab6c1631b775e1b5de705696392868a4e6ce93ca3d68b0c0` | `6c706cb7fe066bf20adc76e730c4b9c3172f3756b0e8ce95b7b089d0e1cb60d2` | `4d3d0ff3d9c949e39ee431b50b7fa5ea3dd491014df7f4e97f068cb4c1f7a48d` |
| 5 | 17017012 | `25de896c8fe918f23535788965d61f0e6fcbf12ea833f5ed4c0bddbcc51b46be` | `7890df062aa0481b692dfa976d191d7052b01b03dfe00ecd428465eb955c2103` | `dd51084c4c7d030a679bb0549fe2a2a80d2fbd4f1dac1d2a17846c6da076df6d` |
| 6 | 17017013 | `e5df2f70f19654213267cd72bdb719d26c3f4666ab0b2889cb832d03d8afb4bc` | `f88a582f094501843601a5ff48e5f64f2bba90fa07b10ee5b492baf6490d7c9b` | `39ab4450c971dad6792971844808ae61315399f4b16578dc51d4b70405a915ed` |
| 7 | 17017014 | `cd56513211e5f37a46899a4dbd0026647d078f285776ce7ef00ccf334b8fac62` | `4192386b76b5d67050d4c011a22d61eac35893a78838dc2e782349b1c2782f6f` | `7f5cdead58575a5344fa74b607031dbd2bf795865793cce27a906c068e0d9327` |

Ladder-generator SHA is `0097e78a55cf5d8911a2715cebf7e024606a69713d08d7f3bc07ac04864d60f0`;
the accepted fixture-1 generator remains byte-identical at `8dd7e9b8a4e4a6bfdb5a71535dabd28b4495209df326a88650b6831efc26d32d`.
Ladder SHA is `59c55a26d12ff9e0fdbe488608c4cb7ffb1a2082d322dec85ee5ef37719c3ed2`.
Selection is the first qualifying ordinal; execution must evaluate and bank all
eight outcomes.

## Qualification-rate estimate

Estimator contract SHA is
`440b5dd26d20753275db36159755e06b1fc20e740d1689d774fe90b1289e7954`;
result SHA is `91a80f4634e6fedf6d3a26a91d7576e0f411e110b13dd282b6633d873c6f517d`.
One million samples produced zero qualifiers. The predicted rate is 0 with a
Wilson 95% interval `[0, 0.000003841444063944942]`. S quantiles at 1%, 10%,
50%, 90%, and 99% are `0.0017092`, `0.0240922`, `0.158771`, `0.523970`, and
`1.043800`; maximum observed S is `3.129417`.

For eight independent fixtures, point-estimate `P(any)` is 0. Even using the
Wilson upper per-fixture rate, `P(any)` is only `0.0000307311`, below the
pre-frozen `0.9` adequacy threshold. Correlation is not estimable from one
banked fixture; positive correlation would make the independent approximation
optimistic.

## Contracts and reusable work

- analytical retention v2 SHA: `d80260e9c146dca4fa10987b12f681655c1d476d1b9b2a91ca16479ec97e8c21`;
  phase configs can declare arbitrary required analytical values/hashes, and
  PASS rejects omissions.
- generic expert-slice validator: implemented and tested for experts 0, 1, 15,
  166, and 255 plus overflow rejection.
- decoded reuse contract SHA: `e061bb16af5bda05c39fd439c76c17447e2af0093369bb00fb14062425cead16`;
  a future approved family could reuse one immutable 12-payload decode package,
  with a budget of one shard open, 12 reads, 139,217,920 compressed bytes, and
  666,430,464 decoded bytes.
- generic dispatch instrumentation: not advanced after the phase-7 hard stop.
- overnight estimator soak: 1,000,000 samples; fixture determinism is covered
  by exact regeneration tests.

## Review and stop state

- internal review: `NO-GO`
- adversarial packet: `docs/architecture/reviews/f017-m1-f0-new-input-selection-adversarial-packet.md`
- final-head CI: required after banking; exact run is reported in closeout/final response
- real checkpoint access: 0
- new M1-F0 route discovery: false
- Q6_K qualification: false
- M1-F execution: false
- P1: blocked

Exact next action: independently review the negative estimator and select a
different checkpoint-independent fixture-family design (or independently
tighten the pre-candidate error analysis without weakening the frozen contract)
before preparing any new real-access authorization.
