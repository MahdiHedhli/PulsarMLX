# R001 mounted-source resume blocker

## Result

`R001_FOUNDATION_BLOCKED_SOURCE_CHECKPOINT`

The expected checkpoint directory is present on the M1 Ultra SMB mount, and
all six exact shard paths can be statted. Their sizes match committed authority
and sum to `238,458,632,928` bytes. The mounted share denies content reads with
`EPERM`, however, so R001 cannot read even the eight-byte GGUF preamble.

The graph stopped at N1. It did not parse a live header, hash a shard, construct
the checkpoint-set hash, design a bundle, implement a repacker, generate a
fixture, or run a benchmark.

## Resume authority

- R001 branch: `feat/r001-expert-store-repack`.
- Resume HEAD: `46aa3532145d9c7ee88c49ec227b59bba6119b5b`.
- Host: ColPanicM2, Apple M2 Max, 64 GiB.
- Source mount: `<m1-ultra-home-share>` using SMB 3.0.2.
- Source directory: `<m1-ultra-glm52-checkpoint>`.
- Candidate classification: `CORRUPT_OR_UNREADABLE` as defined by the R001
  discovery contract. This classification denotes failed readability and does
  not assert that stored bytes are corrupt.

## Stat-only shard evidence

| Shard | Size bytes | Expected SHA-256 | Content result |
|---|---:|---|---|
| `00001` | 9,423,744 | `7bf96eeabbe887e58b6c44364962731ddc9dc5bf46fec8d097c1dff64bea4a18` | unexecuted |
| `00002` | 49,105,028,960 | `d94adaa58ddd5abbcf2514192958084416b1aa36bd4d21409028a164341bac36` | unexecuted |
| `00003` | 49,143,176,640 | `1cd0b1a3d9d939ce5a184c548f1b1c42edafaf1856cb0d7e586a2884a366256b` | unexecuted |
| `00004` | 49,143,176,640 | `10f3965db697a46ba66494475045af183c1bcaf639984160930c91a377816d3e` | unexecuted |
| `00005` | 49,143,176,640 | `40d7d4524ff07e0f9af494fb13130dc7090184800cc5af0a1563188b076af50d` | unexecuted |
| `00006` | 41,914,650,304 | `eeceb9084350e64be8eebcd1f19ab14bbbb6b40132c86d77ffc65e72f425044d` | unexecuted |

All exact file stats succeeded. Directory enumeration and direct content reads
returned `Operation not permitted`. Partial-download marker status therefore
remains unverified rather than being reported absent.

## Set-hash definition

Committed implementation
`scripts/research/glm52_checkpoint_identity.py` constructs the set identity in
expected shard order. For each shard it appends the ASCII lowercase hexadecimal
SHA-256 digest and then the ASCII decimal byte length to one SHA-256 state,
without separators. It does not hash concatenated checkpoint bytes.

Expected set SHA-256:
`d7d1e6a8f8ab11726a7f1e43e4d8f02ed73f04ee27ffb876915147a568b9afee`.

The set result is `UNEXECUTED`, not accepted, because no shard content hash was
available.

## Restrictions preserved

- No write was attempted under the mount.
- No mount option, permission, ACL, owner, or extended attribute was changed.
- No remote command was executed.
- No checkpoint byte was copied or downloaded.
- The F017 checkout was observed only with bounded branch/HEAD/remote commands.
- No full repack or inference ran.

## Required recovery

Restore read access for the existing share outside this graph, without changing
checkpoint contents. The minimum admission probe is a successful read of the
first eight bytes from shard `00001`, yielding GGUF magic and version. Resume at
N1 only after that probe succeeds. N2 must then hash all six shards sequentially
and compare stable pre/post stats before N3 begins.

## Evidence

- Exact local evidence:
  `<r001-artifact-root>/r001-resume-preflight-local-0001.json`.
- Local evidence SHA-256:
  `092c423faa220a91e424577653d6910223a0cbbcc0368f655e394485eb3e2c8b`.
- Start: `2026-08-27T05:11:58Z`.
- Completion: `2026-08-27T05:13:58Z`.
- Exit status: `1` because the required content-read gate failed.

