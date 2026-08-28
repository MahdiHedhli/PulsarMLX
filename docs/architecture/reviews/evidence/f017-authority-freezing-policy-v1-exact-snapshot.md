# F017 Authority-Freezing Policy v1

## Policy declaration

- Policy ID: `f017-authority-freezing-policy-v1`
- Version: `1.0.0`
- Declarer: F017 planner
- Declaration authority: explicit F017 owner instruction to correct and freeze
  this policy
- Attributes at publication: `BANKED`, `PINNED`, `TEMPORALLY_FROZEN`,
  `OPERATIONALLY_RATIFIED`
- Effective boundary: commit-pinned publication of this policy and its adjacent
  SHA-256 sidecar
- Scope: F017 phases launched after the effective boundary
- Existing authority: prompts already issued before the effective boundary
  remain governed by their own pinned bytes; this policy does not amend them
  retroactively
- Evolution: append-only adjudicated successor; never edit this version in
  place after publication

## 1. Core rule

Ceremony scales with irreversibility, temporal dependence, and shared reliance.

Freeze only what must remain stable to:

- make an irreversible action safe;
- prevent post-observation rule changes;
- keep a banked result interpretable;
- make a multi-party commitment unambiguous.

Everything else remains versioned and replaceable.

## 2. Artifact attributes and terminal status

The following are attributes, not mutually exclusive states. An artifact may
simultaneously be `BANKED`, `PINNED`, `TEMPORALLY_FROZEN`, and
`OPERATIONALLY_RATIFIED`. Schemas and evidence must preserve every applicable
attribute rather than projecting one lossy `state` value.

- **LIQUID:** Versioned working material that may change.
- **BANKED:** Exact historical bytes and provenance are retained.
- **PINNED:** An execution or result identifies the exact version it used.
- **TEMPORALLY_FROZEN:** Defined before observation so it cannot be changed in
  response to results.
- **INSTANTIABLE:** A real producer and checker can create and validate it end
  to end.
- **OPERATIONALLY_RATIFIED:** Qualified for use at a consequential boundary.
- **CONSUMED:** A consumable authority instance has been used by its authorized
  irreversible act or result.
- **SUPERSEDED:** Replaced prospectively by an adjudicated successor.
- **REVOKED:** Prohibited from future use because a material defect was
  established.

`CONSUMED`, `SUPERSEDED`, and `REVOKED` are terminal with respect to future
authority. `CONSUMED` applies only to artifacts whose declared semantics are
consumable; binding a reusable contract to a result does not consume the
contract. A consumed one-shot authority cannot be reused. A superseded or
revoked artifact cannot authorize new work.

Banking or pinning does not imply ratification. Temporal freezing does not
imply instantiability.

## 3. Declaration authority and unavailable-planner behavior

The phase authority owner declares freeze transitions.

For F017, the F017 planner is the phase authority owner and sole prompt issuer.
A worker, implementer, generator, validator, or reviewer cannot independently
expand the freeze set, amend a transition node, or ratify an artifact.

An independent reviewer evaluates whether declared transition requirements
were satisfied. The reviewer does not create transition authority.

A human operator remains the final authority for any separately human-gated
irreversible act.

If the planner is unavailable, including during an overnight graph, the graph
must not self-declare or infer a transition. It must preserve completed
reversible work, park at `DECLARATION_REQUIRED` or `HUMAN_REQUIRED` as
appropriate, publish the named finding and safe terminal evidence, and wait
for a planner-issued version-forward amendment or successor phase.

## 4. Freeze Transition Table

Every phase specification must declare at launch:

- each artifact expected to cross a freeze boundary;
- all current and intended attributes;
- the exact transition node;
- the reason for freezing;
- its producer;
- its checker or consumer;
- required qualification evidence;
- required binders or reviewers;
- whether human authorization is required;
- the consequence of failure.

Example:

| Artifact | Transition | Node | Prerequisites | Declarer |
|---|---|---|---|---|
| Numeric tolerances | `LIQUID` to `TEMPORALLY_FROZEN` | Before observing numerical results | Derivation and independent review | F017 planner |
| Repack manifest | `LIQUID` to `OPERATIONALLY_RATIFIED` | Before deployment consumption | Producer, validator, complete-scope qualification | F017 planner |
| One-shot authorization | `LIQUID` to `OPERATIONALLY_RATIFIED` | Immediately before execution | All bound authorities accepted plus fresh human GO | Human-gated F017 phase |
| Generator version | `LIQUID` to `PINNED` | When evidence is generated | Exact commit and test result | Executing graph under declared table |

A transition occurs only at its declared node and only after its prerequisites
pass.

If execution discovers that an undeclared artifact must be frozen, that
discovery is a mandatory named finding:

`UNDECLARED_FREEZE_TRANSITION_REQUIRED`

The worker must bank the discovery, its affected boundary, and the smallest
required transition. It must deliver the configured NTFY milestone through a
machine-local alias without serializing the resolved topic. It must not ratify
the artifact opportunistically or silently absorb the transition into
“reversible scope.” Work may continue only when it is independently reversible
and cannot influence, precompute, consume, or cross the discovered boundary.
Otherwise the graph parks at `DECLARATION_REQUIRED` pending a planner-issued
amendment or successor phase.

## 5. Two prerequisite rules

### 5.1 Operational instantiability rule

Do not operationally ratify a contract, schema, authority, interface, or
manifest unless:

- a real producer can instantiate it;
- a real checker or consumer can validate it;
- their schemas and interpretations agree;
- the end-to-end path has been demonstrated;
- relevant failure cases fail closed.

A design-only artifact may be reviewed, banked, pinned, or temporally frozen,
but it cannot be represented as production authority merely because its JSON
or prose is internally consistent.

### 5.2 Pre-observation rule and falsification

Facts whose value depends on preceding observation must be temporally frozen
early, even when no operational producer exists yet.

This includes:

- numerical contracts;
- tolerance derivations;
- stage vocabulary;
- accounting units;
- comparison rules;
- success and failure predicates;
- exclusion criteria.

Such an artifact must be labeled:

`TEMPORALLY_FROZEN_NOT_OPERATIONALLY_RATIFIED`

It prevents post-result rule changes but cannot authorize execution or
acceptance until producer-consumer instantiability is separately demonstrated.

Observed results may falsify a temporally frozen derivation, but they may never
select, tune, or establish its replacement. A replacement requires a
version-forward successor whose derivation method and inputs are declared and
temporally frozen before any new result is observed. Prior observations may be
used only as explicitly labeled historical evidence when the successor method
predeclares how they are used; they cannot be silently treated as an
independent confirmation set.

## 6. Freeze and operationally ratify

Operational ratification is appropriate when an artifact:

- authorizes checkpoint access, ledger advancement, identity consumption,
  live installation, one-shot execution, or release;
- is consumed by an irreversible act;
- defines a shared normative contract used by two or more independently acting
  parties;
- defines a security or capability boundary whose reinterpretation could make
  prior work unsafe;
- binds a banked result whose meaning cannot otherwise be reconstructed.

Historical bytes remain immutable. Changes require an adjudicated successor.

## 7. Bank and pin without ratifying tooling

Preserve the exact version used when an artifact:

- generated, transformed, or validated evidence;
- is needed to reproduce a historical run;
- participated in a result’s provenance chain.

This normally includes:

- generators;
- validator implementations;
- test harnesses;
- evidence builders;
- benchmark runners.

The tool remains liquid and versionable. The exact historical version is
pinned to the result it produced.

When a validator gates an irreversible act, its acceptance policy and accepted
schema must be operationally ratified. The exact validator implementation is
separately pinned and qualified as part of the trusted execution path. Pinning
the implementation alone is insufficient.

Example: a release wrapper consumes a ratified release-authority policy and
closed schema. `validate_release_authority_v5` is the pinned, qualified
implementation enforcing them. A future `v6` validator may replace `v5`
without changing the policy, but it cannot authorize release until it is
qualified against the same ratified policy and shown not to widen acceptance.
Changing the release policy or schema requires its own declared successor and
ratification transition.

## 8. Keep liquid

Keep artifacts replaceable when they govern only reversible work, including:

- unimplemented design details;
- prototypes and spikes;
- local benchmarks;
- checkpoint-free repack experiments;
- synthetic fixtures;
- implementation plans;
- development tooling.

Freeze only their safety invariants, external interfaces, or pre-observation
facts when those independently meet a freeze rule.

## 9. Designs

Design review is advisory and risk-reducing. It is not proof of production
behavior.

Before implementation, freeze only:

- pre-observation facts;
- security invariants;
- capability boundaries;
- externally shared interfaces.

Treat the remaining design as a hypothesis. Implementation and qualification
determine whether it is instantiable.

A design that no implementation can faithfully realize is rejected evidence,
not accepted production authority.

## 10. Error, supersession, revocation, and adjudication

Frozen artifacts are never silently edited or “unfrozen.”

When a frozen artifact is found materially wrong, issue:

1. a version-forward successor artifact;
2. an adjudication record;
3. an impact assessment;
4. updated guards preventing future use of the defective artifact.

The F017 planner issues the adjudication record. When any affected result or
authority was `OPERATIONALLY_RATIFIED` or `CONSUMED`, an independent reviewer
must review the impact assessment before the adjudication can close.

The adjudication record must state:

- the defective artifact’s exact path, version, and digest;
- the defect and how it was discovered;
- the violated invariant;
- the corrected successor and digest;
- why mutation in place is prohibited;
- every authorization, execution, result, or downstream artifact that depended
  on it;
- the disposition of each dependency;
- whether any unconsumed authority is revoked;
- required requalification, replay, or containment.

Each affected result receives one explicit disposition:

- `UNAFFECTED`
- `REINTERPRETATION_REQUIRED`
- `REQUALIFICATION_REQUIRED`
- `INVALIDATED`
- `UNKNOWN_PENDING_REVIEW`

An unconsumed token or authorization bound to a revoked artifact expires
immediately and cannot migrate to the successor. A consumed irreversible act
cannot be undone; it requires an incident record, impact analysis, and explicit
downstream disposition.

Supersession changes future authority. It does not rewrite historical truth.

## 11. Repair-loop rule

Repair budgets are ceilings, not targets:

- reversible implementation work: up to 10 bounded loops;
- design and review work: normally 3–5 loops;
- live-authority or irreversible execution work: 1–2 loops with any required
  fresh human authorization.

Stop early when:

- the same structural blocker survives repeated repairs;
- the required fix changes a frozen premise;
- authority becomes unstable;
- the work crosses an undeclared freeze boundary;
- the required change exceeds the phase scope.

## 12. Launch checklist and required artifact

Before launching a phase, the planner must answer:

1. Which artifacts remain liquid?
2. Which artifacts will be banked or pinned?
3. Which artifacts must be temporally frozen before observation?
4. Which artifacts are expected to become operationally ratified?
5. At exactly which node does each transition occur?
6. Who produces, checks, reviews, and declares each transition?
7. Is producer-consumer instantiability demonstrated?
8. What stops the phase if an undeclared freeze need appears?
9. How will a later defect be superseded and its downstream impact adjudicated?

The answers must be committed as the phase’s machine-checkable or
canonical-text **Freeze Transition Table**, with an exact path and SHA-256 bound
by the launch prompt. The execution response must compare declared transitions
with observed transitions and report every mismatch. Reviewers evaluate the
committed table, not an uncommitted explanation or reconstructed intent.

If the table is absent, incomplete, not commit-pinned, or inconsistent with the
launch prompt, the phase is not ready to launch.

## 13. Policy evolution

This version is frozen at commit-pinned publication. It may be banked, pinned,
and consumed by future phase specifications, but it must not be edited in
place.

Any correction or policy change requires:

- a version-forward successor;
- a planner-issued adjudication record;
- an impact assessment of phases that bound this version;
- independent review when a ratified or consumed result is affected;
- explicit prospective activation at a declared boundary.
