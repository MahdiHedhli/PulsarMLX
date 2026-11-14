//! Reader-owned aligned scratch and bounded observations for the opt-in fixed policy.
use super::*;
pub use crate::read_into::aligned_transport::read_policy::Policy;
use crate::read_into::aligned_transport::{
    read_policy::{PolicyReceipt, Preparation, PreparedPolicy, MAX_ADDITIONAL, POLICY_CONTROL},
    Scratch, WindowPlan, CONTROL as BASE_CONTROL,
};

const ROLES: [ExpertRole; 3] = [ExpertRole::Gate, ExpertRole::Up, ExpertRole::Down];
const MAX_RECORD_BYTES: usize = 2048;
const BOOKKEEPING_LIMIT: u64 = 8192;

#[derive(Clone, Copy, Debug, Serialize)]
pub struct PolicyLedger {
    pub policy: Policy,
    pub page_size: u64,
    pub max_occurrences: usize,
    pub role_capacity: usize,
    pub role_record_bytes: usize,
    pub receipt_bookkeeping: u64,
    pub receipt_bytes: u64,
    pub scratch_backing_bytes: u64,
    pub base_control_bytes: u64,
    pub policy_control_bytes: u64,
    pub transport_bytes: u64,
    pub total: u64,
}

#[derive(Debug, Serialize)]
#[serde(tag = "kind", rename_all = "snake_case")]
pub enum RoleOutcome {
    SetupFailure {
        setup: Preparation,
    },
    Transfer {
        receipt: PolicyReceipt,
        retired_live: usize,
        retired_released: usize,
        kernel_close_observed: Option<bool>,
    },
}

/// Each transfer carries the original complete Rust025 receipt, even for a failed fill.
#[derive(Debug, Serialize)]
pub struct RoleRecord {
    pub owner: u64,
    pub invocation: u64,
    pub epoch: u64,
    pub wave: u8,
    pub bank: u8,
    pub generation: u64,
    pub expert: u32,
    pub binding: Hash256,
    pub role: ExpertRole,
    pub verified: bool,
    pub primary_phase: Option<&'static str>,
    pub outcome: RoleOutcome,
}

pub(super) struct FixedReader {
    ledger: PolicyLedger,
    scratch: Scratch,
    records: Vec<RoleRecord>,
    pub(super) verified_discards: (u64, u64),
}

fn admitted_plan(cache: &CopiedResidency, expert: usize) -> Result<ExpertPlan<'_>> {
    let d = cache.demand(u32::try_from(expert).map_err(|_| overflow())?)?;
    CopiedResidency::plan_for(
        &cache.source,
        &cache.class,
        d,
        cache.content,
        &cache.bindings[expert].hashes,
    )
}

impl FixedReader {
    pub(super) fn new(
        cache: &CopiedResidency,
        policy: Policy,
        available: u64,
        max_occurrences: usize,
    ) -> Result<(Self, PolicyLedger)> {
        if cache.is_quarantined() {
            return Err(refusal("QUARANTINE", "input cache unavailable"));
        }
        if !(1..=MAX_OCCURRENCES).contains(&max_occurrences) {
            return Err(refusal("BUDGET", "fixed policy occurrence capacity"));
        }
        let role_capacity = max_occurrences * ROLES.len();
        let role_record_bytes = size_of::<RoleRecord>();
        bounded(
            role_record_bytes as u64,
            MAX_RECORD_BYTES as u64,
            "role record layout",
        )?;
        // Inline state plus two transient role moves and fixed accounting/encoder frames.
        let receipt_bookkeeping =
            (size_of::<Self>() + size_of::<PolicyLedger>() + 2 * role_record_bytes + 2048) as u64;
        bounded(
            receipt_bookkeeping,
            BOOKKEEPING_LIMIT,
            "policy receipt bookkeeping",
        )?;
        let receipt_bytes = add(
            receipt_bookkeeping,
            mul(role_capacity as u64, role_record_bytes as u64)?,
        )?;
        let page_size = safetensors_catalog::admission::read_policy::page_size()
            .map_err(|reason| refusal("POLICY", reason))?;
        // Size the one reusable backing from real offsets in each sealed expert, without
        // fresh opens, setters, payload reads, or keeping an array of borrowed plans.
        let mut largest = (0, 0, ExpertRole::Gate);
        for expert in 0..cache.bindings.len() {
            let plan = admitted_plan(cache, expert)?;
            for role in ROLES {
                let window = WindowPlan::new(&plan, role, page_size)?;
                let cost = PreparedPolicy::minimum_budget(&window);
                if cost > largest.0 {
                    largest = (cost, expert, role);
                }
            }
        }
        let (transport_bytes, expert, role) = largest;
        bounded(transport_bytes, MAX_ADDITIONAL, "fixed transport ceiling")?;
        let total = add(transport_bytes, receipt_bytes)?;
        let base = total_charge(cache.working_bytes(), cache.ledger().tuple_bytes)?;
        bounded(
            add(base, total)?,
            available,
            "standing fixed staging envelope",
        )?;
        let plan = admitted_plan(cache, expert)?;
        let window = WindowPlan::new(&plan, role, page_size)?;
        let scratch = Scratch::new(&window, transport_bytes - POLICY_CONTROL)?;
        let scratch_backing_bytes = scratch.backing_bytes() as u64;
        if add(scratch_backing_bytes, BASE_CONTROL + POLICY_CONTROL)? != transport_bytes {
            return Err(refusal("BUDGET", "unexpected fixed scratch backing"));
        }
        let mut records = Vec::new();
        records
            .try_reserve_exact(role_capacity)
            .map_err(|e| refusal("ALLOCATION", e))?;
        if records.capacity() != role_capacity {
            return Err(refusal("BUDGET", "inexact policy receipt capacity"));
        }
        let ledger = PolicyLedger {
            policy,
            page_size,
            max_occurrences,
            role_capacity,
            role_record_bytes,
            receipt_bookkeeping,
            receipt_bytes,
            scratch_backing_bytes,
            base_control_bytes: BASE_CONTROL,
            policy_control_bytes: POLICY_CONTROL,
            transport_bytes,
            total,
        };
        Ok((
            Self {
                ledger,
                scratch,
                records,
                verified_discards: (0, 0),
            },
            ledger,
        ))
    }
    pub(super) fn records(&self) -> &[RoleRecord] {
        &self.records
    }
    pub(super) fn clear(&mut self) {
        self.records.clear();
        self.verified_discards = (0, 0);
    }
    pub(super) fn preflight(&self, occurrences: usize, tuple_bytes: u64) -> Result<()> {
        let n = occurrences as u64;
        let roles = mul(n, ROLES.len() as u64)?;
        bounded(
            roles,
            self.records.capacity() as u64,
            "fixed policy receipt capacity",
        )?;
        // All new observations are call-local. Per component there is at most one
        // open/descriptor/setter/read/bounce, and at most two partial pages of overread.
        let components = mul(roles, 3)?;
        let extra = mul(components, mul(2, self.ledger.page_size - 1)?)?;
        add(mul(n, tuple_bytes)?, extra)?;
        Ok(())
    }
    pub(super) fn fill(
        &mut self,
        plan: &ExpertPlan<'_>,
        stamp: &Stamp,
        parts: &mut Parts,
        cancelled: &mut impl FnMut() -> bool,
        mut verified: impl FnMut(ExpertRole),
    ) -> Result<()> {
        for role in ROLES {
            check_cancel(cancelled)?;
            if self.records.len() == self.records.capacity() {
                return Err(refusal("BUDGET", "fixed policy role evidence full"));
            }
            let window = WindowPlan::new(plan, role, self.ledger.page_size)?;
            let (outcome, result) = match PreparedPolicy::prepare(
                &window,
                self.ledger.policy,
                self.ledger.transport_bytes,
            ) {
                Err(failure) => (
                    RoleOutcome::SetupFailure {
                        setup: failure.setup,
                    },
                    Err(failure.cause),
                ),
                Ok(prepared) => {
                    let index = role.index();
                    let expected = stamp.hashes[index].map(|hash| safetensors_catalog::hex(&hash));
                    let [w, s, b] = &mut parts[index];
                    let dest = PlaneDestination::new(w, s, b, expected.clone());
                    let (receipt, result) =
                        match prepared.read(&mut self.scratch, dest, self.ledger.transport_bytes) {
                            Err(failure) => (failure.receipt, Err(failure.cause)),
                            Ok(filled) => {
                                let (plane, receipt) = filled.into_parts();
                                let observed = plane.into_receipt();
                                let plane = &plan.record().planes[index];
                                let valid = observed.role == role
                                    && observed.checkpoint == plan.record().checkpoint
                                    && observed.metadata_snapshot_sha256
                                        == plan.record().metadata_snapshot_sha256
                                    && observed.actual_sha256 == expected
                                    && same_plane(&observed.plane, plane)
                                    && observed.range_attempts == 3
                                    && observed.requested_bytes
                                        == plane.ranges.iter().map(|r| r.len).sum::<u64>();
                                let result = if valid {
                                    Ok(())
                                } else {
                                    Err(refusal(
                                        "CONTENT",
                                        "verified role receipt differs from admitted tuple",
                                    ))
                                };
                                (receipt, result)
                            }
                        };
                    let retired = prepared.retire();
                    (
                        RoleOutcome::Transfer {
                            receipt,
                            retired_live: retired.live,
                            retired_released: retired.released,
                            kernel_close_observed: retired.kernel_close_observed,
                        },
                        result,
                    )
                }
            };
            self.records.push(RoleRecord {
                owner: stamp.owner,
                invocation: stamp.invocation,
                epoch: stamp.epoch,
                wave: stamp.wave,
                bank: stamp.bank,
                generation: stamp.generation,
                expert: stamp.demand.key.expert,
                binding: stamp.demand.binding,
                role,
                verified: result.is_ok(),
                primary_phase: result.as_ref().err().map(|e| e.phase),
                outcome,
            });
            result?;
            // Evidence and retirement are complete before a test hook or cancellation callback can unwind.
            verified(role);
        }
        check_cancel(cancelled)?;
        plan.validate_source()
    }
}

#[cfg(all(test, target_os = "macos"))]
mod tests;
