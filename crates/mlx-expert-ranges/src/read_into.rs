//! Exclusive, role-scoped fills from the descriptors retained by a sealed plan.
//! Expected hashes are supplied by the caller's independently frozen content
//! authority. Metadata identity alone is not payload provenance.
use super::*;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
#[serde(rename_all = "lowercase")]
pub enum ExpertRole {
    Gate,
    Up,
    Down,
}
impl ExpertRole {
    pub fn index(self) -> usize {
        match self {
            Self::Gate => 0,
            Self::Up => 1,
            Self::Down => 2,
        }
    }
}

pub struct PlaneDestination<'dst> {
    parts: [&'dst mut [u8]; 3],
    expected: [String; 3],
}
impl<'dst> PlaneDestination<'dst> {
    pub fn new(
        weights: &'dst mut [u8],
        scales: &'dst mut [u8],
        biases: &'dst mut [u8],
        expected: [String; 3],
    ) -> Self {
        Self {
            parts: [weights, scales, biases],
            expected,
        }
    }
}

#[derive(Debug, Clone, Serialize)]
pub struct ReadIntoReceipt {
    pub schema: &'static str,
    pub metadata_snapshot_sha256: String,
    pub checkpoint: String,
    pub role: ExpertRole,
    pub plane: PlaneRecord,
    pub actual_sha256: [String; 3],
    pub requested_bytes: u64,
    pub range_attempts: u64,
}

/// Holds the exclusive destination borrows until explicitly consumed. A failure
/// returns no capability even when the destination contains partial bytes.
#[must_use = "consume into_receipt before publishing or using the filled storage"]
pub struct FilledPlane<'dst> {
    _destination: PlaneDestination<'dst>,
    receipt: ReadIntoReceipt,
}
impl FilledPlane<'_> {
    pub fn into_receipt(self) -> ReadIntoReceipt {
        self.receipt
    }
}

impl ExpertPlan<'_> {
    pub fn read_plane_into<'dst>(
        &self,
        role: ExpertRole,
        destination: PlaneDestination<'dst>,
    ) -> Result<FilledPlane<'dst>> {
        self.fill_with(role, destination, |held, bytes, begin| {
            held.file.read_exact_at(bytes, begin)
        })
    }

    fn fill_with<'dst>(
        &self,
        role: ExpertRole,
        mut destination: PlaneDestination<'dst>,
        mut read: impl FnMut(&HeldFile, &mut [u8], u64) -> std::io::Result<()>,
    ) -> Result<FilledPlane<'dst>> {
        let plane = self
            .record
            .planes
            .get(role.index())
            .ok_or_else(|| refusal("PLAN", "missing sealed role"))?;
        // Validate every destination before the first write, including empty,
        // oversized and non-native-size lengths; never accept a prefix buffer.
        for (part, range) in destination.parts.iter().zip(&plane.ranges) {
            if u64::try_from(part.len()).ok() != Some(range.len) {
                return Err(refusal("DESTINATION", "all three exact lengths required"));
            }
        }
        if destination.expected.iter().any(|s| {
            s.len() != 64
                || !s
                    .bytes()
                    .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
        }) {
            return Err(refusal(
                "CONTENT",
                "three canonical expected SHA-256 values required",
            ));
        }
        for held in self.source.held.values() {
            held.check()?;
        }
        let mut hashes = [String::new(), String::new(), String::new()];
        let mut requested = 0u64;
        for (i, range) in plane.ranges.iter().enumerate() {
            let held = &self.source.held[&range.shard];
            held.check()?;
            self.source
                .requested_payload_bytes
                .fetch_add(range.len, Ordering::Relaxed);
            self.source
                .payload_read_calls
                .fetch_add(1, Ordering::Relaxed);
            requested += range.len; // bounded by the sealed tuple's 32 MiB cap
            read(held, &mut destination.parts[i], range.begin).map_err(|e| refusal("READ", e))?;
            held.check()?;
            hashes[i] = digest(destination.parts[i]);
            if hashes[i] != destination.expected[i] {
                return Err(refusal("CONTENT", "selected component digest mismatch"));
            }
        }
        for held in self.source.held.values() {
            held.check()?;
        }
        Ok(FilledPlane {
            _destination: destination,
            receipt: ReadIntoReceipt {
                schema: "pulsarmlx.read-into-plane/1",
                metadata_snapshot_sha256: self.source.identity.clone(),
                checkpoint: self.record.checkpoint.clone(),
                role,
                plane: plane.clone(),
                actual_sha256: hashes,
                requested_bytes: requested,
                range_attempts: 3,
            },
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn partial_io_failure_counts_attempt_and_returns_no_capability() {
        let f = crate::test_support::fixture(128, 64, 3, false, 0, true);
        let source = BoundedSource::open(&f.root).unwrap();
        let plan = source.plan(f.request.clone()).unwrap();
        let control = plan.load().unwrap();
        let hashes = std::array::from_fn(|c| digest(control.bytes(0, c).unwrap()));
        let mut parts: [Vec<u8>; 3] =
            std::array::from_fn(|c| vec![0xa5; control.bytes(0, c).unwrap().len()]);
        let [w, s, b] = &mut parts;
        let before = source.payload_read_calls();
        let mut calls = 0;
        let result = plan.fill_with(
            ExpertRole::Gate,
            PlaneDestination::new(w, s, b, hashes),
            |held, bytes, begin| {
                calls += 1;
                if calls == 2 {
                    bytes[0] = 0xff;
                    return Err(std::io::ErrorKind::UnexpectedEof.into());
                }
                held.file.read_exact_at(bytes, begin)
            },
        );
        assert!(matches!(result,Err(e) if e.phase=="READ"));
        assert_eq!(source.payload_read_calls() - before, 2);
        assert_eq!(parts[0], control.bytes(0, 0).unwrap());
        assert_eq!(parts[1][0], 0xff);
        assert!(parts[2].iter().all(|b| *b == 0xa5));
    }
}
