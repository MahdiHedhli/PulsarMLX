#![cfg(target_os = "macos")]

use stream::{
    MetalBridge, StableSlabAllocator, StableSlabConfig, ZeroingPolicy,
};

#[test]
fn page_aligned_slab_is_registered_once_and_reused_for_metal_checksum() {
    let allocator = StableSlabAllocator::new(StableSlabConfig::new(
        4096,
        4096,
        1,
        ZeroingPolicy::ZeroInitialize,
    ))
    .expect("valid page-aligned slab allocator");
    let mut slab = allocator.acquire().expect("allocate stable slab");
    for (index, byte) in slab.as_mut_slice().iter_mut().enumerate() {
        *byte = (index % 251) as u8;
    }
    let expected = slab
        .as_slice()
        .iter()
        .fold(0_u32, |sum, &byte| sum.wrapping_add(byte as u32));
    let address = slab.as_ptr() as usize;
    assert_eq!(address % 4096, 0);

    let bridge = MetalBridge::new().expect("Metal context and checksum pipeline");
    let registration = bridge.register(&slab).expect("zero-copy Metal registration");
    assert_eq!(MetalBridge::registered_address(&registration), address);
    assert_eq!(bridge.checksum(&registration).expect("Metal checksum"), expected);
    assert_eq!(bridge.checksum(&registration).expect("Metal checksum reuse"), expected);
}
