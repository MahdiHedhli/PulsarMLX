# F017 Event-04 Runtime Hardening — Opus Cycle 01 Response

Reviewed head: `35d456d6209353e86280f5833bca6460bf96c76d`

Reviewer: `claude-opus-5` (fresh read-only detached worktree)

Session: `262d035f-fee7-4f1e-a9d1-bb5a52f6c052`

## Verdict

`REJECT`

## Blocking

- `B1 LIVE_MINT_GATE_STALENESS_MAKES_EVENT_04_UNEXECUTABLE`: the immutable
  mint observation was re-aged by every later parse. A checkpoint identity
  pass can legitimately exceed the freshness window, making later consumer
  parsing reject otherwise valid installed authority. Validate the threshold
  at the observation timestamp; enforce freshness when collecting the mint
  sample and again from a new package-start sample.

## Non-blocking required

- `N1 EVENT04_SHARDS_UNBOUND_FROM_ACCEPTED_CHECKPOINT`: live operator approval
  shard records were copied without exact equality to committed production
  metadata.
- `N2 PRE_TRY_PRODUCTION_FAILURES_LEAVE_NO_DURABLE_CAPSULE`: authorization
  parsing, scope checks, test-control rejection, and emergency-root handling
  occurred outside the production terminalization boundary.

## Defense in depth

- `D1`: malformed mint-gate shapes could escape through raw type/key errors.
- `D2`: production lease acquisition lacked a mirror rejection of synthetic
  roots and names.
- `D3`: synthetic-root manifest catalog SHA was not compared with candidate
  catalog authority.
- `D4`: failed-transition comparison used the outcome's value on both sides.
- `D5`: six early authorizer outcomes and forty-one coordinator outcomes were
  reported without distinguishing their realization boundary.
- `D6`: tighten readiness and approval schema, freshness, census, and binding.
- `D7`: historical-worktree cleanup lacked a failure-path post-cleanup census.
- `D8`: synthetic hardlinked shards were not rejected.

The reviewer reported material disagreement with Gemini because `B1` was on a
future live branch not exercised by the checkpoint-free success qualification.
The reviewer could not run local Python or hash commands under its read-only
permission profile; findings were derived from committed-byte inspection.
