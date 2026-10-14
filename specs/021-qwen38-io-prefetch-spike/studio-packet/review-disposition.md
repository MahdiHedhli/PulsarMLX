# Exact Studio packet static review and local disposition

## Submission and verdict

Reviewer: explicitly selected `gemini-3.8-flash-high`, existing `agy` route.
Conversation `24816d64-7321-4be5-b46b-8568c8853d58`; terminal `SUCCESS`, one turn,
nonempty response, CLI exit0. Verdict **ACCEPT_FOR_STATIC_PACKET**;
**zero confirmed defects**. Runtime execution remains **BLOCKED**.
No automatic denial occurred. No Claude/Anthropic identity, alternate account,
new credentials, permission-rule changes, purchase or rerouting was used.

Exact submitted UTF-8 bytes are `review-input-v1.json`: **110,654 bytes**,
SHA-256 `83d731a63bcd13ff0d52a78bd78b25260e0c47bf21b4028d60e631115b836920`.
`review-manifest-v1.json` records every submitted file's identity. The11 supplied
text files comprise the packet, its manifest, new harness/generator/tests and
unchanged synthetic memory/session/pager context. The33-file source/spec/fixture
manifest provides identities of remaining dependencies; their full contents
were not independently reviewed anew. No weights, checkpoint Python, credentials
or unrelated worktree data were exported.

The reviewer was instructed to use only supplied text and no tools, execution,
browsing, file access or modification. Submission was from a temporary isolated
directory holding only the sanitized packet. CLI used `--sandbox`, explicitly
selected Gemini, and no permission bypass flag. Its only stderr warning says
`--mode plan` has no effect with slash expansion disabled; the no-tools/no-code
review scope was explicit in the submitted instructions. Raw report, stderr
and exact argv without duplicated payload are retained in `gemini-review-v1*`.

## Triage and limits of the report

No repair/revision was requested, so all33 frozen file bytes remain unchanged
from the reviewed packet. The review accepted isolation/lock requirements,
staging/ownership/resource contracts, numerical distinctions and blocked command
ordering. It correctly identified missing upstream pins/goldens, runtime lock,
driver/fences/sampler, hardware window and actual execution authority as
prerequisites rather than existing qualifications.

Several phrases in the report overstate what static text can establish:

- Its claimed digest verification and statements that tests "execute clean"
  are not independent executions. **Local** hashing, fixture regeneration and
  recorded test outputs provide that evidence. Model-written hashes are not an
  independent cryptographic implementation. `file:///private/tmp/...` links and
  line references in the report are not reliable workspace references.
- `Budget`/`MemoryLedger` enforce synthetic logical and injected-observation
  checks; they do not implement a physical process-tree sampler or prevent real
  device/heap overshoot. The48/40/8/16 GiB physical acceptance remains unqualified.
  The5 ms polling/cadence and120 s runtime wall limit are packet requirements,
  not implemented/observed backend behavior.
- `SyntheticSession` deliberately accepts authenticated marked fixtures,
  including the fixture constructor token; it cannot admit a real checkpoint.
  The future production session must use public `admit_checkpoint_bound` and a
  real authenticated fixed/page path. No production driver was added here.
- The scalar L2 clamp formula is **analytic fixture policy**, not evidence of
  upstream DeltaNet epsilon placement, recurrence or gate equations. Nonzero
  L2/RMS discrimination is demonstrated; zero/tiny model parity remains blocked.
  Likewise the two-token reset and causal candidate filter do not establish
  model hash/reset/indexer/top-k semantics.
- The fixture generator unit test compares parsed objects; the separate local
  audit compares full regenerated JSON bytes. Preinstall lock/interpreter/wheel/
  resolver metadata must be reviewed first; `environment-verification.json` is
  the required **postinstall** receipt, not a circular preinstall condition.

These corrections narrow review claims without changing accepted code,
requirements, reference tolerances or authority. No actual numerical/hardware
parity, package compatibility or M2 throughput is inferred from the verdict.

## Local evidence and final gate

- `focused.txt`: **14 passed**.
- `regression.txt`: **138 applicable Qwen synthetic tests passed** (previous124
  plus14 new tests).
- `analytic-result.json`: **27 analytic probes passed**, no runtime execution,
  upstream parity explicitly blocked.
- `initial-red.txt`: prior12-test stage had two missing-fixture errors; retained
  rather than presented as a completed pass.
- `identity-result.json` / `frozen-files.json`: **33 exact source/spec/fixture
  identities match**. Manifest/envelope self-references are excluded and sealed
  externally through validation/review manifests.
- `validation.json`: exact test commands, local Python3.14.6 identity, raw output
  hashes and source manifest digest. This is not Python3.13 qualification.
- `local-audit.json`: byte-exact fixture regeneration, unchanged existing
  scheduler/adapter/checkpoint manifest/completed goal graph/feature selector,
  diff/credential-pattern/large-file review. Final staging check follows review.

Only this Qwen owner worktree changed. No Studio/GLM work, checkpoint read,
checkpoint Python, package installation/download, GPU/MLX/model/inference,
benchmark, push, merge or old-goal edit occurred. New CLI only checks tiny scalar
fixtures and small source artifacts; it has no runtime command.

Remaining exact prerequisites/blocked commands are in README's E0–P0 table.
Minimum owner action for resource acquisition is a scope permitting retrieval
and verification of the pinned Python3.13 interpreter, dependency metadata/
wheels and independent upstream reference sources/fixtures. No installation
follows until those exact locks/artifacts are reviewed. A separately scheduled
GLM-idle Studio window and explicit tiny device/reference execution permission
are then needed, together with a reviewed real driver/fence/sampler. Real
checkpoint rehash/reads, bundled-code execution, paged inference and M2 timing
remain distinct actual-owner gates. Local source packet closure does not request
another generic design approval and does not reopen the completed prior goal.
