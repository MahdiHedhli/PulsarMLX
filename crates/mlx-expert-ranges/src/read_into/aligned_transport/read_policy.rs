//! Permanent per-open policy requests for sealed synthetic file windows.
use super::core::{PathKind, Progress, Reader, Span};
use super::*;
pub use platform::Policy;
use safetensors_catalog::admission::read_policy::{
    self as platform, FixedDescriptor, Setup, SetupFailure,
};

pub const POLICY_CONTROL: u64 = 65536;
pub const POLICY_RECORD_LIMIT: usize = 32768;
pub const MAX_ADDITIONAL: u64 = MAX_BACKING + CONTROL + POLICY_CONTROL;

#[derive(Clone, Copy, Debug, Serialize)]
pub struct Preparation {
    pub policy: Policy,
    pub role: ExpertRole,
    pub binding: [u8; 32],
    pub original_stamps: [[u8; 32]; 3],
    pub lengths: [u64; 3],
    pub alignment: u64,
    pub page_size: Option<u64>,
    pub map: [Option<usize>; 3],
    pub slots: [Option<Setup>; 3],
    pub live: usize,
    pub released: usize,
    pub kernel_close_observed: Option<bool>,
    pub minimum_reservation: u64,
    pub policy_control: u64,
}
#[derive(Debug)]
pub struct PrepareFailure {
    pub cause: Refusal,
    pub setup: Preparation,
}
pub struct PreparedPolicy<'w, 'p, 's> {
    window: &'w WindowPlan<'p, 's>,
    files: [Option<FixedDescriptor>; 3],
    originals: [Option<&'w HeldFile>; 3],
    setup: Preparation,
}
#[derive(Debug, Clone, Copy, Serialize, PartialEq, Eq)]
pub enum Route {
    #[serde(rename = "buffered-requested-aligned-window")]
    BufferedWindow,
    #[serde(rename = "nocache-requested-aligned-window")]
    NoCacheWindow,
    #[serde(rename = "buffered-edge-exact")]
    OriginalEdge,
}
#[derive(Debug, Clone, Copy, Serialize)]
pub struct Component {
    pub route: Route,
    pub begin: u64,
    pub bytes: u64,
    pub delta: u64,
    pub logical_begin: u64,
    pub logical_bytes: u64,
}
#[derive(Debug, Serialize)]
pub struct PolicyReceipt {
    pub schema: &'static str,
    pub setup: Preparation,
    pub components: [Component; 3],
    #[serde(flatten)]
    progress: Progress,
    pub ledger: Ledger,
    pub combined_reservation: u64,
    pub policy_control_required: u64,
    pub coalescing_overread: u64,
    pub physical_bytes: Option<u64>,
    pub cache_bypass_observed: Option<bool>,
    pub syscalls: Option<u64>,
    pub physical_memory: Option<u64>,
    pub performance: Option<u64>,
    pub published: bool,
}
impl PolicyReceipt {
    pub fn encoded_bytes(&self) -> usize {
        core::encoded_size(self).expect("fixed numeric JSON schema")
    }
}
#[derive(Debug)]
pub struct PolicyFailure {
    pub cause: Refusal,
    pub receipt: PolicyReceipt,
}
#[must_use]
pub struct FilledPolicyPlane<'dst> {
    filled: FilledPlane<'dst>,
    receipt: PolicyReceipt,
}
impl<'dst> FilledPolicyPlane<'dst> {
    pub fn into_parts(self) -> (FilledPlane<'dst>, PolicyReceipt) {
        (self.filled, self.receipt)
    }
}

fn policy_error(s: &'static str) -> Refusal {
    refusal("POLICY", s)
}
fn policy_cost() -> u64 {
    // Three File/stamp witnesses are inline. Allow two typed reports plus the preparation and
    // the shared execution frame, one full compact encoding and bounded temporary path/errors.
    (POLICY_RECORD_LIMIT
        + size_of::<PreparedPolicy>()
        + 2 * size_of::<PolicyReceipt>()
        + size_of::<Preparation>()
        + size_of::<Progress>()
        + 8192) as u64
}
impl<'w, 'p, 's> PreparedPolicy<'w, 'p, 's> {
    pub fn minimum_budget(window: &WindowPlan) -> u64 {
        window.minimum_reservation() + POLICY_CONTROL
    }
    pub fn prepare(
        window: &'w WindowPlan<'p, 's>,
        policy: Policy,
        budget: u64,
    ) -> std::result::Result<Self, PrepareFailure> {
        Self::prepare_with(
            window,
            policy,
            budget,
            platform::page_size(),
            FixedDescriptor::open,
        )
    }
    fn prepare_with(
        window: &'w WindowPlan<'p, 's>,
        policy: Policy,
        budget: u64,
        page: std::result::Result<u64, &'static str>,
        mut open: impl FnMut(
            &RootDirectory,
            &str,
            &File,
            Policy,
        ) -> std::result::Result<FixedDescriptor, SetupFailure>,
    ) -> std::result::Result<Self, PrepareFailure> {
        let mut setup = Preparation {
            policy,
            role: window.role,
            binding: window.binding,
            original_stamps: window.stamps,
            lengths: window.held.map(|h| h.stamp.len),
            alignment: window.a,
            page_size: page.ok(),
            map: [None; 3],
            slots: [None; 3],
            live: 0,
            released: 0,
            kernel_close_observed: None,
            minimum_reservation: Self::minimum_budget(window),
            policy_control: POLICY_CONTROL,
        };
        let mut files = [None, None, None];
        let mut originals = [None; 3];
        let root = &window.plan.source._directory;
        let result = (|| {
            let page = page.map_err(policy_error)?;
            if !matches!(page, 4096 | 16384) || window.a != page {
                return Err(policy_error("PAGE_ALIGNMENT"));
            }
            if budget < setup.minimum_reservation || policy_cost() > POLICY_CONTROL {
                return Err(policy_error("POLICY_BUDGET"));
            }
            for h in window.held {
                h.check()?;
            }
            let ranges = &window.plan.record.planes[window.role.index()].ranges;
            for (i, held) in window.held.iter().enumerate() {
                if let Some(j) = window.held[..i]
                    .iter()
                    .position(|h| std::ptr::eq(*h, *held))
                {
                    setup.map[i] = setup.map[j];
                    continue;
                }
                let slot = setup.live;
                setup.map[i] = Some(slot);
                held.check()?;
                match open(root, &ranges[i].shard, &held.file, policy) {
                    Ok(fresh) => {
                        let obs = fresh.setup();
                        setup.slots[slot] = Some(obs);
                        files[slot] = Some(fresh);
                        originals[slot] = Some(*held);
                        setup.live += 1;
                        if obs.original_stamp != Some(window.stamps[i])
                            || obs.fresh_stamp != Some(window.stamps[i])
                        {
                            return Err(policy_error("STAMP_BINDING"));
                        }
                    }
                    Err(failure) => {
                        setup.slots[slot] = Some(failure.observation);
                        setup.released += usize::from(failure.observation.fresh_owned);
                        return Err(policy_error(failure.reason));
                    }
                }
                held.check()?;
            }
            for h in window.held {
                h.check()?;
            }
            for f in files.iter().flatten() {
                f.check().map_err(|_| policy_error("FRESH_MUTATION"))?;
            }
            Ok(())
        })();
        if let Err(cause) = result {
            drop(files);
            setup.released += setup.live;
            setup.live = 0;
            return Err(PrepareFailure { cause, setup });
        }
        Ok(Self {
            window,
            files,
            originals,
            setup,
        })
    }

    pub fn observation(&self) -> Preparation {
        self.setup
    }
    pub fn retire(self) -> Preparation {
        let mut s = self.setup;
        drop(self);
        s.released += s.live;
        s.live = 0;
        s
    }
    fn checks(&self) -> Result<()> {
        for h in self.window.held {
            h.check()?;
        }
        for f in self.files.iter().flatten() {
            f.check().map_err(|_| policy_error("FRESH_MUTATION"))?;
        }
        Ok(())
    }
    fn receipt(&self, ledger: Ledger, progress: Progress, published: bool) -> PolicyReceipt {
        let components = self.window.windows.map(|w| Component {
            route: if w.kind == Kind::Edge {
                Route::OriginalEdge
            } else if self.setup.policy == Policy::BufferedRequested {
                Route::BufferedWindow
            } else {
                Route::NoCacheWindow
            },
            begin: w.begin,
            bytes: w.bytes,
            delta: w.delta,
            logical_begin: w.logical_begin,
            logical_bytes: w.logical_bytes,
        });
        PolicyReceipt {
            schema: "pulsarmlx.fixed-descriptor-transfer/1",
            setup: self.setup,
            components,
            progress,
            ledger,
            combined_reservation: ledger.additional_reservation + POLICY_CONTROL,
            policy_control_required: policy_cost(),
            coalescing_overread: 0,
            physical_bytes: None,
            syscalls: None,
            cache_bypass_observed: None,
            physical_memory: None,
            performance: None,
            published,
        }
    }
    pub fn read<'dst>(
        &self,
        scratch: &mut Scratch,
        dst: PlaneDestination<'dst>,
        budget: u64,
    ) -> std::result::Result<FilledPolicyPlane<'dst>, PolicyFailure> {
        self.read_with(scratch, dst, budget, |source, bytes, at| match source {
            Source::Fresh(f) => f.read_exact_at(bytes, at),
            Source::Original(h) => h.file.read_exact_at(bytes, at),
        })
    }
    fn read_with<'dst>(
        &self,
        scratch: &mut Scratch,
        dst: PlaneDestination<'dst>,
        budget: u64,
        transfer: impl FnMut(Source<'_>, &mut [u8], u64) -> io::Result<()>,
    ) -> std::result::Result<FilledPolicyPlane<'dst>, PolicyFailure> {
        let reader = PolicyReader {
            prepared: self,
            transfer,
        };
        let base_budget = budget.checked_sub(POLICY_CONTROL).unwrap_or(0);
        let (result, ledger, progress) =
            core::execute(self.window, false, scratch, dst, base_budget, reader);
        let receipt = self.receipt(ledger, progress, result.is_ok());
        match result {
            Ok(filled) => Ok(FilledPolicyPlane { filled, receipt }),
            Err(cause) => Err(PolicyFailure { cause, receipt }),
        }
    }
}
enum Source<'a> {
    Fresh(&'a FixedDescriptor),
    Original(&'a HeldFile),
}
struct PolicyReader<'a, 'w, 'p, 's, F> {
    prepared: &'a PreparedPolicy<'w, 'p, 's>,
    transfer: F,
}
impl<F: FnMut(Source<'_>, &mut [u8], u64) -> io::Result<()>> Reader
    for PolicyReader<'_, '_, '_, '_, F>
{
    fn preflight(&self, ledger: Ledger, p: Progress) -> Result<()> {
        if self.prepared.receipt(ledger, p, false).encoded_bytes() + 32 * 20 + 8 * 4
            > POLICY_RECORD_LIMIT
        {
            return Err(policy_error("RECORD_LIMIT"));
        }
        self.prepared.checks()
    }
    fn before(&self, i: usize, _held: &HeldFile, s: Span, bytes: &[u8]) -> Result<()> {
        let p = self.prepared;
        let page = p.window.a;
        let index = p.setup.map[i].ok_or_else(|| policy_error("SOURCE_MAP"))?;
        let f = p
            .files
            .get(index)
            .and_then(Option::as_ref)
            .ok_or_else(|| policy_error("SOURCE_MAP"))?;
        // A fresh slot is paired to the *first original held object*, independent of stamp equality.
        if !p.originals[index].is_some_and(|h| std::ptr::eq(h, p.window.held[i]))
            || f.setup().fresh_stamp != Some(p.window.stamps[i])
        {
            return Err(policy_error("SOURCE_MAP"));
        }
        if matches!(s.route, PathKind::Interior)
            && (bytes.as_ptr() as usize % page as usize != 0
                || s.begin % page != 0
                || s.bytes % page != 0)
        {
            return Err(policy_error("UNALIGNED_REQUEST"));
        }
        p.checks()
    }
    fn transfer(&mut self, i: usize, h: &HeldFile, s: Span, bytes: &mut [u8]) -> io::Result<()> {
        let source = match s.route {
            PathKind::Interior => Source::Fresh(
                self.prepared.files[self.prepared.setup.map[i].unwrap()]
                    .as_ref()
                    .unwrap(),
            ),
            PathKind::Edge => Source::Original(h),
            PathKind::Direct => return Err(io::ErrorKind::InvalidInput.into()),
        };
        (self.transfer)(source, bytes, s.begin)
    }
    fn after(&self) -> Result<()> {
        self.prepared.checks()
    }
}
#[cfg(test)]
mod tests;
