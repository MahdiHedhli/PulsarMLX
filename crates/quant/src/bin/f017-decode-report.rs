use std::alloc::{GlobalAlloc, Layout, System};
use std::hint::black_box;
use std::sync::atomic::{AtomicUsize, Ordering};
use std::time::Instant;

use quant::{
    decode_iq2_xxs_matrix, decode_iq3_xxs_matrix, decode_q6_k_matrix, decode_q8_0_matrix,
    IQ2_XXS_BLOCK_BYTES, IQ3_XXS_BLOCK_BYTES, Q6_K_BLOCK_BYTES, QK8_0, QK_K,
};

const ROWS: usize = 8;
const ROW_WIDTH: usize = 256;
const SAMPLES: usize = 31;

struct CountingAllocator;

static ALLOCATIONS: AtomicUsize = AtomicUsize::new(0);
static DEALLOCATIONS: AtomicUsize = AtomicUsize::new(0);
static REALLOCATIONS: AtomicUsize = AtomicUsize::new(0);
static ALLOCATED_BYTES: AtomicUsize = AtomicUsize::new(0);
static DEALLOCATED_BYTES: AtomicUsize = AtomicUsize::new(0);

unsafe impl GlobalAlloc for CountingAllocator {
    unsafe fn alloc(&self, layout: Layout) -> *mut u8 {
        ALLOCATIONS.fetch_add(1, Ordering::Relaxed);
        ALLOCATED_BYTES.fetch_add(layout.size(), Ordering::Relaxed);
        System.alloc(layout)
    }

    unsafe fn dealloc(&self, pointer: *mut u8, layout: Layout) {
        DEALLOCATIONS.fetch_add(1, Ordering::Relaxed);
        DEALLOCATED_BYTES.fetch_add(layout.size(), Ordering::Relaxed);
        System.dealloc(pointer, layout)
    }

    unsafe fn realloc(&self, pointer: *mut u8, layout: Layout, new_size: usize) -> *mut u8 {
        REALLOCATIONS.fetch_add(1, Ordering::Relaxed);
        if new_size > layout.size() {
            ALLOCATED_BYTES.fetch_add(new_size - layout.size(), Ordering::Relaxed);
        } else {
            DEALLOCATED_BYTES.fetch_add(layout.size() - new_size, Ordering::Relaxed);
        }
        System.realloc(pointer, layout, new_size)
    }
}

#[global_allocator]
static ALLOCATOR: CountingAllocator = CountingAllocator;

#[derive(Clone, Copy)]
struct AllocationSnapshot {
    allocations: usize,
    deallocations: usize,
    reallocations: usize,
    allocated_bytes: usize,
    deallocated_bytes: usize,
}

fn reset_allocations() {
    for counter in [
        &ALLOCATIONS,
        &DEALLOCATIONS,
        &REALLOCATIONS,
        &ALLOCATED_BYTES,
        &DEALLOCATED_BYTES,
    ] {
        counter.store(0, Ordering::Relaxed);
    }
}

fn allocations() -> AllocationSnapshot {
    AllocationSnapshot {
        allocations: ALLOCATIONS.load(Ordering::Relaxed),
        deallocations: DEALLOCATIONS.load(Ordering::Relaxed),
        reallocations: REALLOCATIONS.load(Ordering::Relaxed),
        allocated_bytes: ALLOCATED_BYTES.load(Ordering::Relaxed),
        deallocated_bytes: DEALLOCATED_BYTES.load(Ordering::Relaxed),
    }
}

fn synthetic_bytes(bytes_per_block: usize, scale_at_end: bool) -> Vec<u8> {
    let blocks = ROWS * (ROW_WIDTH / if bytes_per_block == 34 { QK8_0 } else { QK_K });
    let mut encoded = Vec::with_capacity(blocks * bytes_per_block);
    for block_index in 0..blocks {
        let start = encoded.len();
        encoded.extend((0..bytes_per_block).map(|offset| {
            ((block_index.wrapping_mul(17) + offset.wrapping_mul(31) + 7) & 0xff) as u8
        }));
        if scale_at_end {
            encoded[start + bytes_per_block - 2..start + bytes_per_block]
                .copy_from_slice(&0x3c00_u16.to_le_bytes());
        } else {
            encoded[start..start + 2].copy_from_slice(&0x3c00_u16.to_le_bytes());
        }
    }
    encoded
}

fn median(values: &mut [u128]) -> u128 {
    values.sort_unstable();
    values[values.len() / 2]
}

fn report<F>(name: &str, encoded: &[u8], exactness: &str, mut decode: F)
where
    F: FnMut(&[u8], &mut [f32]),
{
    let mut destination = vec![0.0_f32; ROWS * ROW_WIDTH];
    decode(encoded, &mut destination);

    let mut durations = Vec::with_capacity(SAMPLES);
    reset_allocations();
    let started = Instant::now();
    for _ in 0..SAMPLES {
        let sample_started = Instant::now();
        decode(encoded, &mut destination);
        durations.push(sample_started.elapsed().as_nanos());
        black_box(&destination);
    }
    let elapsed = started.elapsed();
    let snapshot = allocations();
    let median_nanos = median(&mut durations);
    let seconds = median_nanos as f64 / 1_000_000_000.0;
    let throughput_mib = encoded.len() as f64 / seconds / (1024.0 * 1024.0);
    let checksum = destination
        .iter()
        .fold(0_u32, |sum, value| sum.wrapping_add(value.to_bits()));

    println!(
        "format={name} rows={ROWS} cols={ROW_WIDTH} encoded_bytes={} median_decode_ns={median_nanos} throughput_mib_s={throughput_mib:.3} samples={SAMPLES} allocs={} reallocs={} alloc_bytes={} deallocs={} dealloc_bytes={} exactness={exactness} checksum=0x{checksum:08x} wall_ms={}",
        encoded.len(),
        snapshot.allocations,
        snapshot.reallocations,
        snapshot.allocated_bytes,
        snapshot.deallocations,
        snapshot.deallocated_bytes,
        elapsed.as_millis(),
    );
}

fn main() {
    let q8 = synthetic_bytes(34, false);
    let q6 = synthetic_bytes(Q6_K_BLOCK_BYTES, true);
    let iq2 = synthetic_bytes(IQ2_XXS_BLOCK_BYTES, false);
    let iq3 = synthetic_bytes(IQ3_XXS_BLOCK_BYTES, false);

    report(
        "Q8_0",
        &q8,
        "golden_identical_existing_strict_tests",
        |bytes, output| {
            decode_q8_0_matrix(bytes, ROWS, ROW_WIDTH, output).expect("valid synthetic Q8_0");
        },
    );
    report(
        "Q6_K",
        &q6,
        "golden_identical_existing_strict_tests",
        |bytes, output| {
            decode_q6_k_matrix(bytes, ROWS, ROW_WIDTH, output).expect("valid synthetic Q6_K");
        },
    );
    report(
        "IQ2_XXS",
        &iq2,
        "golden_identical_existing_strict_tests",
        |bytes, output| {
            decode_iq2_xxs_matrix(bytes, ROWS, ROW_WIDTH, output).expect("valid synthetic IQ2_XXS");
        },
    );
    report(
        "IQ3_XXS",
        &iq3,
        "golden_identical_existing_strict_tests",
        |bytes, output| {
            decode_iq3_xxs_matrix(bytes, ROWS, ROW_WIDTH, output).expect("valid synthetic IQ3_XXS");
        },
    );
}
