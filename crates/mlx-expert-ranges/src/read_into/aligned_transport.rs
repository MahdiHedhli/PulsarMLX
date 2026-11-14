//! Buffered transfers over the descriptors of one sealed expert role.
use super::*;
use std::io;

mod geometry;
use geometry::{alignment, backing, geometry, reservation};

pub const MAX_BACKING: u64 = MAX_SELECTED_BYTES + 3 * (16384 - 1);
pub const CONTROL: u64 = 65536;
pub const RECORD_LIMIT: usize = 16384;
const NATIVE: u64 = usize::MAX as u64;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
pub enum Mode {
    BufferedExact,
    BufferedAlignedWindow,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
pub enum Kind {
    #[serde(rename = "buffered-exact")]
    Exact,
    #[serde(rename = "buffered-aligned-window")]
    Window,
    #[serde(rename = "buffered-edge-exact")]
    Edge,
}
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
pub struct Window {
    pub kind: Kind,
    pub begin: u64,
    pub bytes: u64,
    pub delta: u64,
    pub logical_begin: u64,
    pub logical_bytes: u64,
}
impl Window {
    fn transfer(self, mode: Mode) -> Self {
        if mode == Mode::BufferedExact {
            Self {
                kind: Kind::Exact,
                begin: self.logical_begin,
                bytes: self.logical_bytes,
                delta: 0,
                ..self
            }
        } else {
            self
        }
    }
}
#[derive(Debug, Clone, Copy, Serialize)]
pub struct Ledger {
    pub logical_bytes: u64,
    pub candidate_bytes: u64,
    pub largest_request: u64,
    pub minimum_backing: u64,
    pub backing_bytes: u64,
    pub head_slack: u64,
    pub tail_slack: u64,
    pub usable_bytes: u64,
    pub control_required: u64,
    pub control_reserved: u64,
    pub additional_reservation: u64,
}

/// The backing never changes length or address. Alignment is checked anew for each plan.
pub struct Scratch {
    storage: Box<[u8]>,
}
impl Scratch {
    pub fn new(plan: &WindowPlan<'_, '_>, budget: u64) -> Result<Self> {
        reservation(plan.minimum, plan.control, budget).map_err(limit)?;
        let n = plan.minimum as usize;
        let mut v = Vec::new();
        v.try_reserve_exact(n)
            .map_err(|e| refusal("ALLOCATION", e))?;
        if v.capacity() != n {
            return Err(limit("inexact scratch allocation"));
        }
        v.resize(n, 0);
        Ok(Self {
            storage: v.into_boxed_slice(),
        })
    }
    pub fn backing_bytes(&self) -> usize {
        self.storage.len()
    }
}
/// Observation of one attempted transfer. A failed exact-at read can have written a prefix.
#[derive(Debug, Clone, Copy, Default, Serialize)]
pub struct Effect {
    pub attempted: bool,
    pub returned_bytes: Option<u64>,
    pub copied: u64,
}
#[derive(Debug, Serialize)]
pub struct TransportReceipt {
    pub schema: &'static str,
    pub mode: Mode,
    pub role: ExpertRole,
    pub binding: [u8; 32],
    pub descriptor_stamps: [[u8; 32]; 3],
    pub descriptor_lengths: [u64; 3],
    pub alignment: u64,
    pub windows: [Window; 3],
    pub transfers: [Window; 3],
    pub effects: [Effect; 3],
    pub logical_attempts: u64,
    pub logical_requested: u64,
    pub attempted: u64,
    pub requested: u64,
    pub completed: u64,
    pub logical_delivered: u64,
    pub copies: u64,
    pub copied: u64,
    pub candidate_overread: u64,
    pub attempted_overread: u64,
    pub completed_overread: u64,
    pub edge_attempts: u64,
    pub coalescing_overread: u64,
    pub physical_bytes: Option<u64>,
    pub syscalls: Option<u64>,
    pub cache_observed: Option<bool>,
    pub published: bool,
    pub ledger: Ledger,
}

#[derive(Debug)]
pub struct TransportFailure {
    pub cause: Refusal,
    pub receipt: TransportReceipt,
}

#[must_use = "consume the filled capability before publishing the destination"]
pub struct FilledTransportPlane<'dst> {
    filled: FilledPlane<'dst>,
    receipt: TransportReceipt,
}
impl<'dst> FilledTransportPlane<'dst> {
    pub fn into_parts(self) -> (FilledPlane<'dst>, TransportReceipt) {
        (self.filled, self.receipt)
    }
}

fn limit(detail: &'static str) -> Refusal {
    refusal("WINDOW", detail)
}

fn stamp_digest(held: &HeldFile) -> [u8; 32] {
    let s = &held.stamp;
    let mut h = Sha256::new();
    h.update(b"buffered-window-descriptor/1");
    for n in [s.dev, s.ino, s.len] {
        h.update(n.to_le_bytes());
    }
    for n in [s.mtime, s.mtime_ns, s.ctime, s.ctime_ns] {
        h.update(n.to_le_bytes());
    }
    h.finalize().into()
}

/// Borrows the original plan, its three descriptor objects and role. Only observations are serializable.
pub struct WindowPlan<'p, 'src> {
    plan: &'p ExpertPlan<'src>,
    role: ExpertRole,
    held: [&'p HeldFile; 3],
    stamps: [[u8; 32]; 3],
    binding: [u8; 32],
    a: u64,
    windows: [Window; 3],
    largest: u64,
    minimum: u64,
    control: u64,
}
impl<'p, 'src> WindowPlan<'p, 'src> {
    pub fn new(plan: &'p ExpertPlan<'src>, role: ExpertRole, a: u64) -> Result<Self> {
        alignment(a).map_err(limit)?;
        let plane = plan
            .record
            .planes
            .get(role.index())
            .ok_or_else(|| limit("missing role"))?;
        let held = plane.ranges.each_ref().map(|r| &plan.source.held[&r.shard]);
        let component = |i: usize| {
            let r = &plane.ranges[i];
            geometry(a, held[i].stamp.len, r.begin, r.len, NATIVE).map_err(limit)
        };
        let windows = [component(0)?, component(1)?, component(2)?];
        let largest = windows.iter().map(|w| w.bytes).max().unwrap();
        let minimum = backing(a, largest, plan.record.selected_bytes, NATIVE).map_err(limit)?;
        // The inherited receipt clones these strings plus three SHA-256 strings.
        // Charge their UTF-8 bytes and a compact formatting envelope (6x worst JSON escape).
        let text = [
            &plan.source.identity,
            &plan.record.checkpoint,
            &plane.role,
            &plane.module,
            &plane.resolved_from,
            &plane.metadata_dtype,
        ]
        .into_iter()
        .chain(plane.ranges.iter().flat_map(|r| [&r.tensor, &r.shard]))
        .try_fold(3 * 64u64, |v, s| v.checked_add(s.len() as u64))
        .ok_or_else(|| limit("control overflow"))?;
        // 8192 covers fixed structures, temporary counters, SHA/formatter scratch, bounded
        // failure text and non-string inherited JSON syntax/numbers. Reserve two report
        // structures for transfer/return, as well as the full transport encoding allowance.
        let fixed = 8192
            + RECORD_LIMIT as u64
            + (size_of::<Self>() + 2 * size_of::<TransportReceipt>() + size_of::<FilledPlane>())
                as u64;
        let control = text
            .checked_mul(7)
            .and_then(|v| v.checked_add(fixed))
            .ok_or_else(|| limit("control overflow"))?;
        reservation(minimum, control, u64::MAX).map_err(limit)?;
        let stamps = held.map(stamp_digest);
        let mut hash = Sha256::new();
        hash.update(b"pulsarmlx.buffered-window-plan/1");
        serde_json::to_writer(&mut hash, &plan.record).map_err(|e| refusal("PLAN", e))?;
        hash.update([role.index() as u8]);
        hash.update(a.to_le_bytes());
        for s in &stamps {
            hash.update(s);
        }
        Ok(Self {
            plan,
            role,
            held,
            stamps,
            binding: hash.finalize().into(),
            a,
            windows,
            largest,
            minimum,
            control,
        })
    }
    pub fn minimum_reservation(&self) -> u64 {
        self.minimum + CONTROL
    }

    fn layout(&self, scratch: &Scratch) -> Ledger {
        let backing = scratch.storage.len() as u64;
        let residue = scratch.storage.as_ptr() as usize as u64 & (self.a - 1);
        let head = (self.a - residue) & (self.a - 1);
        let usable = backing.checked_sub(head).unwrap_or(0);
        Ledger {
            logical_bytes: self.windows.iter().map(|w| w.logical_bytes).sum(),
            candidate_bytes: self.windows.iter().map(|w| w.bytes).sum(),
            largest_request: self.largest,
            minimum_backing: self.minimum,
            backing_bytes: backing,
            head_slack: head,
            usable_bytes: usable,
            tail_slack: usable.checked_sub(self.largest).unwrap_or(0),
            control_required: self.control,
            control_reserved: CONTROL,
            additional_reservation: backing + CONTROL,
        }
    }

    pub fn read<'dst>(
        &self,
        mode: Mode,
        scratch: &mut Scratch,
        dst: PlaneDestination<'dst>,
        budget: u64,
    ) -> std::result::Result<FilledTransportPlane<'dst>, TransportFailure> {
        self.read_with(mode, scratch, dst, budget, |held, buf, begin| {
            held.file.read_exact_at(buf, begin)
        })
    }

    fn read_with<'dst>(
        &self,
        mode: Mode,
        scratch: &mut Scratch,
        dst: PlaneDestination<'dst>,
        budget: u64,
        mut read: impl FnMut(&HeldFile, &mut [u8], u64) -> io::Result<()>,
    ) -> std::result::Result<FilledTransportPlane<'dst>, TransportFailure> {
        let mut ledger = self.layout(scratch);
        // PlaneDestination retains its three caller-supplied hash Strings on success.
        let expected_bytes = dst
            .expected
            .iter()
            .try_fold(0u64, |v, s| v.checked_add(s.capacity() as u64));
        let required = expected_bytes.and_then(|n| ledger.control_required.checked_add(n));
        if let Some(n) = required {
            ledger.control_required = n;
        }
        let mut report = TransportReceipt {
            schema: "pulsarmlx.buffered-window-transfer/1",
            mode,
            role: self.role,
            binding: self.binding,
            descriptor_stamps: self.stamps,
            descriptor_lengths: self.held.map(|h| h.stamp.len),
            alignment: self.a,
            windows: self.windows,
            transfers: self.windows.map(|w| w.transfer(mode)),
            effects: [Effect::default(); 3],
            logical_attempts: 0,
            logical_requested: 0,
            attempted: 0,
            requested: 0,
            completed: 0,
            logical_delivered: 0,
            copies: 0,
            copied: 0,
            candidate_overread: ledger.candidate_bytes - ledger.logical_bytes,
            attempted_overread: 0,
            completed_overread: 0,
            edge_attempts: 0,
            coalescing_overread: 0,
            physical_bytes: None,
            syscalls: None,
            cache_observed: None,
            published: false,
            ledger,
        };
        let exec = (|| {
            // All changing numeric fields are u64 (at most 20 decimal digits).
            // Measure this exact schema before I/O, reserving 20 extra bytes per
            // mutable integer and 4 per mutable boolean/null tag. Arrays are fixed.
            struct Count(usize);
            impl io::Write for Count {
                fn write(&mut self, b: &[u8]) -> io::Result<usize> {
                    self.0 += b.len();
                    Ok(b.len())
                }
                fn flush(&mut self) -> io::Result<()> {
                    Ok(())
                }
            }
            let mut encoded = Count(0);
            serde_json::to_writer(&mut encoded, &report).map_err(|e| refusal("WINDOW", e))?;
            if encoded.0 + 32 * 20 + 8 * 4 > RECORD_LIMIT {
                return Err(limit("transport encoding limit"));
            }
            reservation(
                ledger.backing_bytes,
                required.ok_or_else(|| limit("control overflow"))?,
                budget,
            )
            .map_err(limit)?;
            if ledger.usable_bytes < self.largest {
                return Err(limit("insufficient aligned scratch"));
            }
            let head = ledger.head_slack as usize;
            let active = &mut scratch.storage[head..head + self.largest as usize];
            self.plan.fill_with(self.role, dst, |held, bytes, offset| {
                let i = report.logical_attempts as usize;
                // fill_with increments its two source counters immediately before every
                // invocation. These call-local deltas exclude other users of the same source.
                report.logical_attempts += 1;
                report.logical_requested += bytes.len() as u64;
                let transfer = report.transfers.get(i).ok_or(io::ErrorKind::InvalidInput)?;
                if !std::ptr::eq(self.held[i], held)
                    || geometry(self.a, held.stamp.len, offset, bytes.len() as u64, NATIVE).ok()
                        != Some(self.windows[i])
                {
                    return Err(io::Error::new(
                        io::ErrorKind::InvalidInput,
                        "sealed component mismatch",
                    ));
                }
                let aligned = transfer.kind == Kind::Window;
                let effect = &mut report.effects[i];
                let overread = transfer.bytes - transfer.logical_bytes;
                effect.attempted = true;
                report.attempted += 1;
                report.requested += transfer.bytes;
                report.attempted_overread += overread;
                report.edge_attempts += u64::from(transfer.kind == Kind::Edge);
                if aligned {
                    let window = &mut active[..transfer.bytes as usize];
                    read(held, window, transfer.begin)?;
                    let start = transfer.delta as usize;
                    bytes.copy_from_slice(&window[start..start + bytes.len()]);
                    report.copies += 1;
                    report.copied += transfer.logical_bytes;
                    effect.copied = transfer.logical_bytes;
                } else {
                    read(held, bytes, transfer.begin)?;
                }
                effect.returned_bytes = Some(transfer.bytes);
                report.completed += transfer.bytes;
                report.completed_overread += overread;
                report.logical_delivered += transfer.logical_bytes;
                Ok(())
            })
        })();
        match exec {
            Ok(filled) => {
                report.published = true;
                Ok(FilledTransportPlane {
                    filled,
                    receipt: report,
                })
            }
            Err(cause) => Err(TransportFailure {
                cause,
                receipt: report,
            }),
        }
    }
}
#[cfg(test)]
mod tests;
