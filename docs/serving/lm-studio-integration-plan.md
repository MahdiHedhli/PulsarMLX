# LM Studio integration plan (opt-in, not implemented)

Status: **plan only.** Nothing in this document has been executed. LM Studio is
not installed, not configured, and not connected in this repository, and no
real model has been attached to the serving path.

This exists so that an eventual integration starts from stated preconditions
rather than being improvised.

## Why this is opt-in

LM Studio is a separate local application with its own model storage, its own
OpenAI-compatible server, and its own logging. Pointing PulsarMLX at it, or
exposing PulsarMLX to it, moves real prompt and completion content across a
process boundary this repository does not control. That must be a deliberate,
per-user choice, off by default, and it must not be reachable by simply having
LM Studio installed.

## Preconditions that are not yet met

`SERVING-LMS-ADAPTER-PRIVACY-01` remains **open**. It requires evidence, not
assertion, for both of the following before any adapter is enabled:

1. **Local endpoint and key separation.** The LM Studio endpoint and its
   credential must be configured independently of any cloud provider endpoint
   or key, with no shared default, no fallback from one to the other, and no
   path by which an absent local configuration silently reaches a cloud
   provider. Evidence must show a request cannot leave the local host when the
   adapter is selected.
2. **No content logging.** Prompts and completions must not be written to logs
   by the adapter, at any log level. Evidence must be a capture at the most
   verbose level showing request and response content absent, in the manner of
   SAPI-09, extended to cover the adapter.

Neither has evidence today. Until both do, the adapter stays unimplemented and
unreferenced from user-facing configuration.

## Boundaries this plan does not cross

- No LM Studio installation or configuration is performed by this repository.
- No cloud provider credential is reused for a local endpoint, in either
  direction.
- No checkpoint, weights or tokenizer assets are introduced.
- Any local server started for testing stays loopback-only and is stopped
  afterwards.

## Proposed sequence

1. Specify the adapter boundary in the Spec Kit artifacts: which routes it
   maps, which it refuses, and what it does when LM Studio is absent. Failing
   closed is the only acceptable answer to an absent local endpoint.
2. Build the adapter behind an explicit opt-in that defaults to off, with the
   endpoint and credential supplied separately from any cloud configuration.
3. Produce `SERVING-LMS-ADAPTER-PRIVACY-01` evidence:
   - a destination guard test in the style of SAPI-06, proving no non-local
     destination is reachable while the adapter is selected;
   - a fresh-process capture in the style of SAPI-09 at maximum verbosity,
     proving prompt and completion content is absent from adapter logs.
4. Qualify the adapter against a synthetic LM Studio stand-in first, so the
   protocol mapping is tested without a real model.
5. Only then consider a real-model run, which is a separate task with its own
   authorization, and which this plan does not grant.

## Relationship to the synthetic server

The synthetic server is the reference for the protocol subset. An LM Studio
adapter must not widen what PulsarMLX claims to support: if a route or
parameter is not qualified against the synthetic server, the adapter does not
expose it. Real-model behaviour through LM Studio is not evidence about
PulsarMLX's own runtime backends.
