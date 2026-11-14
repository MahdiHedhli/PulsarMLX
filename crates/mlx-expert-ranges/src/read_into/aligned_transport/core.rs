//! Shared descriptor transfer accounting. These internal routes carry no cache-policy authority.
use super::*;

#[derive(Clone, Copy)]
pub(super) enum PathKind {
    Direct,
    Interior,
    Edge,
}
#[derive(Clone, Copy)]
pub(super) struct Span {
    pub route: PathKind,
    pub begin: u64,
    pub bytes: u64,
    pub delta: u64,
    pub logical_bytes: u64,
}
impl Span {
    fn new(w: Window, direct: bool) -> Self {
        if direct {
            return Self {
                route: PathKind::Direct,
                begin: w.logical_begin,
                bytes: w.logical_bytes,
                delta: 0,
                logical_bytes: w.logical_bytes,
            };
        }
        Self {
            route: if w.kind == Kind::Edge {
                PathKind::Edge
            } else {
                PathKind::Interior
            },
            begin: w.begin,
            bytes: w.bytes,
            delta: w.delta,
            logical_bytes: w.logical_bytes,
        }
    }
}
#[derive(Clone, Copy, Debug, Serialize)]
pub(super) struct Progress {
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
}
impl Progress {
    pub(super) fn empty(l: Ledger) -> Self {
        Self {
            effects: [Effect::default(); 3],
            logical_attempts: 0,
            logical_requested: 0,
            attempted: 0,
            requested: 0,
            completed: 0,
            logical_delivered: 0,
            copies: 0,
            copied: 0,
            candidate_overread: l.candidate_bytes - l.logical_bytes,
            attempted_overread: 0,
            completed_overread: 0,
            edge_attempts: 0,
        }
    }
}
pub(super) fn encoded_size<T: Serialize>(v: &T) -> Result<usize> {
    struct Count(usize);
    impl io::Write for Count {
        fn write(&mut self, b: &[u8]) -> io::Result<usize> {
            self.0 = self
                .0
                .checked_add(b.len())
                .ok_or(io::ErrorKind::InvalidData)?;
            Ok(b.len())
        }
        fn flush(&mut self) -> io::Result<()> {
            Ok(())
        }
    }
    let mut count = Count(0);
    serde_json::to_writer(&mut count, v).map_err(|e| refusal("WINDOW", e))?;
    Ok(count.0)
}
pub(super) trait Reader {
    fn preflight(&self, ledger: Ledger, p: Progress) -> Result<()>;
    fn before(&self, _i: usize, _held: &HeldFile, _span: Span, _buf: &[u8]) -> Result<()> {
        Ok(())
    }
    fn transfer(&mut self, i: usize, held: &HeldFile, span: Span, buf: &mut [u8])
        -> io::Result<()>;
    fn after(&self) -> Result<()> {
        Ok(())
    }
}
pub(super) fn execute<'dst>(
    plan: &WindowPlan,
    direct: bool,
    scratch: &mut Scratch,
    dst: PlaneDestination<'dst>,
    base_budget: u64,
    mut reader: impl Reader,
) -> (Result<FilledPlane<'dst>>, Ledger, Progress) {
    let mut ledger = plan.layout(scratch);
    let required = dst
        .expected
        .iter()
        .try_fold(ledger.control_required, |cost, s| {
            cost.checked_add(s.capacity() as u64)
        });
    if let Some(n) = required {
        ledger.control_required = n;
    }
    let mut progress = Progress::empty(ledger);
    let result = (|| {
        reader.preflight(ledger, progress)?;
        reservation(
            ledger.backing_bytes,
            required.ok_or_else(|| limit("control overflow"))?,
            base_budget,
        )
        .map_err(limit)?;
        if ledger.usable_bytes < plan.largest {
            return Err(limit("insufficient aligned scratch"));
        }
        let head = ledger.head_slack as usize;
        let active = &mut scratch.storage[head..head + plan.largest as usize];
        let mut refusal_from_route = None;
        let filled = plan.plan.fill_with(plan.role, dst, |held, bytes, begin| {
            let i = progress.logical_attempts as usize;
            progress.logical_attempts += 1;
            progress.logical_requested += bytes.len() as u64;
            let w = *plan.windows.get(i).ok_or(io::ErrorKind::InvalidInput)?;
            if !std::ptr::eq(plan.held[i], held)
                || geometry(plan.a, held.stamp.len, begin, bytes.len() as u64, NATIVE).ok()
                    != Some(w)
            {
                return Err(io::Error::new(
                    io::ErrorKind::InvalidInput,
                    "sealed component mismatch",
                ));
            }
            let span = Span::new(w, direct);
            let interior = matches!(span.route, PathKind::Interior);
            let buf = if interior {
                &mut active[..span.bytes as usize]
            } else {
                &mut bytes[..]
            };
            if let Err(reason) = reader.before(i, held, span, buf) {
                refusal_from_route = Some(reason);
                return Err(io::ErrorKind::InvalidInput.into());
            }
            let extra = span.bytes - span.logical_bytes;
            progress.effects[i].attempted = true;
            progress.attempted += 1;
            progress.requested += span.bytes;
            progress.attempted_overread += extra;
            progress.edge_attempts += u64::from(matches!(span.route, PathKind::Edge));
            reader.transfer(i, held, span, buf)?;
            progress.effects[i].returned_bytes = Some(span.bytes);
            progress.completed += span.bytes;
            progress.completed_overread += extra;
            if interior {
                let off = span.delta as usize;
                bytes.copy_from_slice(&active[off..off + bytes.len()]);
                progress.effects[i].copied = span.logical_bytes;
                progress.copies += 1;
                progress.copied += span.logical_bytes;
            }
            progress.logical_delivered += span.logical_bytes;
            if let Err(reason) = reader.after() {
                refusal_from_route = Some(reason);
                return Err(io::ErrorKind::InvalidData.into());
            }
            Ok(())
        });
        if let Some(cause) = refusal_from_route {
            return Err(cause);
        }
        let filled = filled?;
        reader.after()?;
        Ok(filled)
    })();
    (result, ledger, progress)
}
