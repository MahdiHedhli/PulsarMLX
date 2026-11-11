use super::support::{fixture, Fixture};
use mlx_expert_ranges::{residency::*, BoundedSource};
use sha2::{Digest, Sha256};
pub const CONTENT: Hash256 = [0x52; 32];
pub fn component(bits: [u32; 3], expert: u32, r: usize, c: usize) -> Vec<u8> {
    let (n, k) = if r == 2 { (128, 64) } else { (64, 128) };
    let len = if c == 0 {
        n * k * bits[r] as usize / 8
    } else {
        n * (k / 64) * 2
    };
    vec![(1 + 40 * r + 7 * expert as usize + c) as u8; len]
}
pub fn hashes(bits: [u32; 3]) -> Vec<TupleHashes> {
    (0..3)
        .map(|expert| {
            std::array::from_fn(|r| {
                std::array::from_fn(|c| Sha256::digest(component(bits, expert, r, c)).into())
            })
        })
        .collect()
}
pub fn setup(mixed: bool) -> (Fixture, CopiedResidency) {
    let f = fixture(128, 64, 3, mixed, 0, true);
    let source = BoundedSource::open(&f.root).unwrap();
    let meta = source.metadata_snapshot().to_owned();
    let cache = CopiedResidency::new(
        source,
        7,
        &f.request,
        ContentAuthority {
            checkpoint: f.root.file_name().unwrap().to_str().unwrap(),
            metadata: &meta,
            content: CONTENT,
            hashes: &hashes(f.request.bits),
        },
        u64::MAX,
        1024,
    )
    .unwrap();
    (f, cache)
}
