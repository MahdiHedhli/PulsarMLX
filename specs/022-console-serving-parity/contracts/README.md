# Contracts for Feature 022: PulsarMLX Console Serving Parity

- **Status**: Index, dated 2026-11-14. Milestone M0 writes the five documents marked
  "written" below. Every other document is planned and is written by the work package
  named in its row. No contract here describes working software: nothing in this
  increment is built yet, and when built it can at most be "qualified on synthetic
  backends".
- **Feature**: `specs/022-console-serving-parity`, branch `feat/022-console-serving-parity`
- **Plan of record**: the owner-approved plan of 2026-11-14, carried into
  [`../plan.md`](../plan.md) and [`../tasks.md`](../tasks.md)

## What a contract is here

A contract states externally observable behavior or an interface between parts of
PulsarMLX Console, precisely enough that a test can be written from it by someone who has
not read the implementation. ADR 0004's independent tests (evidence C in
[parity-ledger.md](parity-ledger.md)) are written from these documents. Where a contract
reproduces project-maya behavior, it cites the donor file and line at the pinned commit
`7e68a30f2f208056195352129188661fb6b94445`; where it departs from it, it cites the
deviation id in [deviations.md](deviations.md).

Contracts follow the house style of the existing feature contracts (for example
`specs/020-mlx-safetensors-affine/contracts/catalog-contract.md`): a short status header,
rules stated as checkable statements, tables where they help, and open questions listed,
never silently decided.

## Index

Status values: **written** (exists in this milestone), **planned** (written by the named
package), **file, not a document** (a machine-read file, listed for completeness).
Paths are relative to this directory unless they start with `console/`.

### Cross-cutting (milestone M0)

| Document | Subject | Written by | Status |
| --- | --- | --- | --- |
| `README.md` | This index | GOV-06 | written |
| [`backend-seam.md`](backend-seam.md) | The two-level backend seam: token level (descriptor, capabilities, request, events, terminal, failures, cancel, pause, wrap, threading, at-least-once delivery and the event ledger, usage rules, the synthetic-only guard) and event level | GOV-06 (draft 0.1); frozen as 1.0 by ENG-01 after engine-track review | written (draft) |
| [`naming.md`](naming.md) | Naming rules of decision B2 and the old-to-new name table | GOV-06 (seed); extended by every package that ports a name | written (seed) |
| [`parity-ledger.md`](parity-ledger.md) | Definition of parity, ledger schema, evidence sources, checker rules, row listing and re-pinning | GOV-06; checker by CNF-12 | written |
| [`deviations.md`](deviations.md) | The deviation register of record, with the proposals the owner approved, declined or deferred on 2026-11-14 | GOV-06; each package adds its tests | written |
| `console/parity/ledger.json` | The 913-row parity ledger | GOV-06 (skeleton, all rows `pending`); every package | file, not a document |

The planner records are the per-area design proposals written before the plan was
approved; they are not in the repository. The engine planner record named the seam
document for ENG-01 `engine-seam.md`; this feature uses the fixed name `backend-seam.md`
instead, and no `engine-seam.md` is created. The conformance planner record placed the
ledger and register under `contracts/`; the ledger lives at `console/parity/ledger.json`
and the register in this directory. "Decision B1" to "decision B13" are the binding
cross-cutting decisions restated in [`../tasks.md`](../tasks.md), section "Binding
cross-cutting decisions". Open items from every contract are collected, with stable ids,
in [`../checklists/analysis.md`](../checklists/analysis.md).

### HTTP surface (milestones M1 and M4)

| Document | Subject | Written by | Status |
| --- | --- | --- | --- |
| `http/` (index, one Markdown document and JSON Schema per route) | Every route and method, request and response shapes, status codes; the route inventory gate | API-20 | planned |
| `http/` transport section | HTTP/1.0 transport that closes after each response, body limits, disconnect detection (decision B1) | API-02 with API-20 | planned |
| `http/` security section | Host allowlist, `Origin` checks, content type, admin gating, API keys (SEC-1, decision B8) | API-03 with API-20 | planned |
| Error conventions | Error body shapes, status mapping, messages before and after the first byte of a stream | API-01 with API-20 | planned |
| OpenAI Chat Completions stream grammar | SSE chunk sequence, finish reasons, usage chunk, `[DONE]` | API-08 | planned |
| Anthropic Messages stream grammar | `message_start` through `message_stop`, thinking and tool blocks | API-09 | planned |
| `cli.md` | `pulsar-console` command line, the ready line, exit codes | API-17 with CNF-07 | planned |
| Monitoring routes | `/health`, `/status`, `/v1/status`, `/metrics`, Prometheus names | API-06 | planned |
| Resumable web streams | `strata_resume`, `/v1/strata/stream`, `/v1/strata/cancel`, answer retention (PRIV-1) | API-10 | planned |

### Prompt and output (milestone M2)

| Document | Subject | Written by | Status |
| --- | --- | --- | --- |
| `parser-events.md` | Streaming output parser events and tool-call syntaxes | PRM-09 | planned |
| `output-pipeline.md` | Detokenization, stops, thinking resume, the run state machine | PRM-12 | planned |
| Prompt and output test map | Mapping of prompt-side donor tests to Rust tests and synthetic templates | PRM-17 | planned |

### Engine (milestone M3)

| Document | Subject | Written by | Status |
| --- | --- | --- | --- |
| Engine line protocol | The line protocol as a PulsarMLX contract, with project-maya's cited as prior art (plan section 6) | ENG-04 | planned |
| Engine conformance profiles | The protocol profile every engine passes and the GLM-family profile | ENG-18 | planned |

### Responses, MCP, attachments and media (milestones M5 and M6)

| Document | Subject | Written by | Status |
| --- | --- | --- | --- |
| `responses.md` | Responses API objects, limits, store, structured output | RSP-01, RSP-02 | planned |
| Responses stream grammar | `response.created` through `response.completed`, sequence numbers, background replay | RSP-04 with RSP-07 | planned |
| `mcp.md` | MCP client configuration, stdio and Streamable HTTP transports, tool loop events | RSP-09, RSP-10, RSP-11 | planned |
| Attachments | File parts in the three dialects, the `/attach` and `/pdf` routes, reader limits | RSP-16 | planned |
| `media.md` | Picture and video sources (SEC-4), the vision seam, the DSI1 and MMI1 file formats (MMI1 documented although not built, LIC-2) | RSP-17, RSP-18 | planned |

### Operations and model management (milestones M4 and M7)

| Document | Subject | Written by | Status |
| --- | --- | --- | --- |
| `ops-environment.md` | Settings sources and precedence, environment naming (with [naming.md](naming.md)) | OPS-02 | planned |
| `ops-*.md` (routes and persisted files) | Model routes, settings profiles, delete plan, switch and restart, savings, update contract, and the files each writes | OPS-23 | planned |
| Fetch and supervise | Progress lines, exit codes and restart protocol of `pulsar-console fetch` and `supervise` (PLAT-3) | OPS-11, OPS-16 | planned |

### Dashboard (milestone M8)

| Document | Subject | Written by | Status |
| --- | --- | --- | --- |
| `ui-server/` (index, routes, streams, restart protocol, storage, URLs and export, theming and icons, Markdown subset, security, schemas, CNF-15 endpoint list, `testdata/`) | The UI-to-server contract the Phase 1 dashboard uses and the Phase 2 rewrite targets, including the endpoints the dashboard calls, checked against the route table | WEB-05, with CNF-15 | planned |

### Conformance machinery (milestones M1 and M10)

| Document | Subject | Written by | Status |
| --- | --- | --- | --- |
| `conformance-scenario.schema.json` | Scenario file format | CNF-02 | file, not a document |
| `rename-map.json` | Branding renames applied to the reference corpus, each linked to a deviation id | CNF-02 | file, not a document |
| `volatile-fields.json` | Fields normalized as volatile, each with a donor citation | CNF-02 | file, not a document |
| `routes.json`, `config-inventory.json`, `errors.json` | Inventories extracted statically from the pinned donor source | CNF-12 | file, not a document |

Paths marked as a directory (`http/`, `ui-server/`) and names given here as a subject
rather than a file are the planner records' proposals; the writing package fixes the final
file name and updates this index in the same change. No path here may match a repository
`.gitignore` trap name.

## Rules for every contract in this directory

1. A contract is written or changed only by the package named in the index, or by a later
   package that records the change and its reason in the document's header.
2. A contract states planned behavior as planned. It never describes behavior as working
   or measured until the exact command, environment and result are recorded
   (constitution principle III).
3. Every difference from project-maya cites a deviation id. A difference with no id is a
   defect in the contract or a proposal for the owner, never a silent choice.
4. Every new name follows [naming.md](naming.md) and is added to its table.
5. Example values are obviously fake: no real-looking credentials, no tokens of 16
   characters or more, no UUID literals, and no literal values for keys named `host` or
   `user` (use substitution tokens such as `{{loopback}}`).
6. project-maya is named where provenance requires it and never as product identity.
7. Files adapted or translated from project-maya, and Rust modules that cite donor
   behavior, follow the provenance header rule in
   [`docs/upstream/PROJECT_MAYA.md`](../../../docs/upstream/PROJECT_MAYA.md#attribution),
   section "Attribution".
