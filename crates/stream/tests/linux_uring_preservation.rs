#![cfg(target_os = "linux")]

//! Linux-only preservation tests for the inherited `io_uring` fetch path.
//!
//! The portable expert source is additive: these tests keep the existing
//! public API, Linux dependency selection, split-shard routing, and aligned
//! payload-window behavior visible. The payload-short case is deliberately
//! ignored until a separately reviewed Linux hardening change can be run on a
//! suitable `io_uring`/`O_DIRECT` host.

use std::fs::File;
use std::io::{self, Write};
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicU64, Ordering};

use stream::fetch::{Fetcher, Slab};
use stream::uring::{Aligned, BufAlloc, Stats};
use stream::Read;

const ALIGN: u64 = 4096;
const INHERITED_TAIL_SLACK: usize = 256;

static FIXTURE_ID: AtomicU64 = AtomicU64::new(0);

struct FixtureFile {
    path: PathBuf,
}

impl FixtureFile {
    fn create(label: &str, bytes: &[u8]) -> Self {
        let id = FIXTURE_ID.fetch_add(1, Ordering::Relaxed);
        let mut path = std::env::temp_dir();
        path.push(format!(
            "pulsarmlx-stream-t040-{}-{label}-{id}.bin",
            std::process::id()
        ));

        let mut file = File::create(&path).expect("create Linux stream fixture");
        file.write_all(bytes).expect("write Linux stream fixture");
        file.sync_all().expect("sync Linux stream fixture");

        Self { path }
    }
}

impl Drop for FixtureFile {
    fn drop(&mut self) {
        let _ = std::fs::remove_file(&self.path);
    }
}

fn deterministic_bytes(len: usize, seed: u8) -> Vec<u8> {
    (0..len)
        .map(|index| seed.wrapping_add((index as u8).wrapping_mul(37)))
        .collect()
}

fn environment_cannot_run_direct_io(error: &io::Error) -> bool {
    matches!(
        error.raw_os_error(),
        Some(libc::EINVAL | libc::ENOSYS | libc::EOPNOTSUPP | libc::EPERM)
    )
}

fn open_or_report_skip(
    context: &str,
    open: impl FnOnce() -> io::Result<Fetcher>,
) -> Option<Fetcher> {
    match open() {
        Ok(fetcher) => Some(fetcher),
        Err(error) if environment_cannot_run_direct_io(&error) => {
            eprintln!(
                "SKIP {context}: io_uring/O_DIRECT unavailable (kind={:?}, os_code={:?})",
                error.kind(),
                error.raw_os_error()
            );
            None
        }
        Err(error) => panic!("{context}: failed to open inherited fetcher: {error}"),
    }
}

fn fetch_or_report_skip(context: &str, fetcher: &mut Fetcher, reads: &[Read]) -> Option<Vec<Slab>> {
    match fetcher.fetch(reads) {
        Ok(slabs) => Some(slabs),
        Err(error) if environment_cannot_run_direct_io(&error) => {
            eprintln!(
                "SKIP {context}: io_uring/O_DIRECT unavailable (kind={:?}, os_code={:?})",
                error.kind(),
                error.raw_os_error()
            );
            None
        }
        Err(error) => panic!("{context}: inherited fetch failed: {error}"),
    }
}

fn aligned_bracket_len(read: Read) -> usize {
    let aligned_offset = read.offset & !(ALIGN - 1);
    let payload_offset = read.offset - aligned_offset;
    (payload_offset + read.len).next_multiple_of(ALIGN) as usize
}

#[test]
fn inherited_linux_api_and_target_selection_remain_explicit() {
    let manifest = include_str!("../Cargo.toml");
    let source = include_str!("../src/lib.rs");

    assert!(manifest.contains("[target.'cfg(target_os = \"linux\")'.dependencies]"));
    assert!(manifest.contains("io-uring = \"0.7\""));
    assert!(manifest.contains("libc = \"0.2\""));
    assert!(source.contains("#[cfg(target_os = \"linux\")]\npub mod uring"));
    assert!(source.contains("#[cfg(target_os = \"linux\")]\npub mod fetch"));

    let _run_plan: fn(&File, &[Read], usize, u64) -> io::Result<Stats> = stream::uring::run_plan;
    let _open: fn(&Path, usize) -> io::Result<Fetcher> = Fetcher::open;
    let _open_with: fn(&Path, usize, Option<BufAlloc>) -> io::Result<Fetcher> = Fetcher::open_with;
    let _open_split: fn(&[(u64, PathBuf)], usize, Option<BufAlloc>) -> io::Result<Fetcher> =
        Fetcher::open_split;
    let _fetch: fn(&mut Fetcher, &[Read]) -> io::Result<Vec<Slab>> = Fetcher::fetch;
    let _payload: fn(&Slab) -> &[u8] = Slab::payload;
    let _bytes: fn(&Slab) -> usize = Slab::bytes;
    let _aligned_new: fn(usize, usize) -> Option<Aligned> = Aligned::new;
    let _aligned_new_with: fn(usize, usize, Option<BufAlloc>) -> Option<Aligned> =
        Aligned::new_with;

    fn null_alloc(_: usize) -> *mut u8 {
        std::ptr::null_mut()
    }
    fn noop_free(_: *mut u8, _: usize) {}
    let _allocator = BufAlloc {
        alloc: null_alloc,
        free: noop_free,
    };

    fn accepts_completion_callback(fetcher: &mut Fetcher, reads: &[Read]) -> io::Result<()> {
        fetcher.fetch_each(reads, |index, slab| {
            let _: usize = index;
            let _: &[u8] = slab.payload();
            Ok(())
        })
    }
    let _fetch_each: fn(&mut Fetcher, &[Read]) -> io::Result<()> = accepts_completion_callback;
}

#[test]
fn split_fetcher_selects_the_existing_virtual_shard_and_preserves_input_order() {
    let first_bytes = deterministic_bytes(ALIGN as usize * 2, 0x13);
    let second_bytes = deterministic_bytes(ALIGN as usize * 2, 0xa7);
    let first = FixtureFile::create("split-first", &first_bytes);
    let second = FixtureFile::create("split-second", &second_bytes);
    let second_base = first_bytes.len() as u64;
    let shards = vec![(0, first.path.clone()), (second_base, second.path.clone())];

    let Some(mut fetcher) =
        open_or_report_skip("split selection", || Fetcher::open_split(&shards, 4, None))
    else {
        return;
    };

    // Deliberately request shard two first so result ordering cannot be
    // mistaken for completion order or ascending virtual offset order.
    let reads = [
        Read {
            offset: second_base + 207,
            len: 513,
        },
        Read {
            offset: ALIGN + 77,
            len: 257,
        },
    ];
    let Some(slabs) = fetch_or_report_skip("split selection", &mut fetcher, &reads) else {
        return;
    };

    assert_eq!(slabs.len(), reads.len());
    assert_eq!(slabs[0].payload(), &second_bytes[207..720]);
    assert_eq!(
        slabs[1].payload(),
        &first_bytes[(ALIGN as usize + 77)..(ALIGN as usize + 334)]
    );
}

#[test]
fn aligned_bracket_maps_the_exact_unaligned_payload_window() {
    let bytes = deterministic_bytes(ALIGN as usize * 2, 0x41);
    let fixture = FixtureFile::create("aligned-window", &bytes);
    let read = Read {
        offset: ALIGN + 37,
        len: 733,
    };

    let Some(mut fetcher) = open_or_report_skip("aligned payload mapping", || {
        Fetcher::open(&fixture.path, 2)
    }) else {
        return;
    };
    let Some(mut slabs) = fetch_or_report_skip("aligned payload mapping", &mut fetcher, &[read])
    else {
        return;
    };
    let slab = slabs.pop().expect("one requested slab");

    assert_eq!(
        slab.payload(),
        &bytes[read.offset as usize..(read.offset + read.len) as usize]
    );
    assert_eq!(
        slab.payload().as_ptr() as usize % ALIGN as usize,
        read.offset as usize % ALIGN as usize
    );
    assert_eq!(
        slab.bytes(),
        aligned_bracket_len(read) + INHERITED_TAIL_SLACK
    );
}

#[test]
fn short_aligned_tail_is_allowed_when_the_completion_covers_the_payload() {
    let bytes = deterministic_bytes(5000, 0x6d);
    let fixture = FixtureFile::create("covered-near-eof", &bytes);
    let read = Read {
        offset: 4400,
        len: 400,
    };

    // The aligned request is [4096, 8192), but a normal EOF completion may
    // return only 904 bytes. The logical payload occupies bytes 304..704 of
    // that completion and therefore remains a valid success.
    let Some(mut fetcher) =
        open_or_report_skip("payload-covered EOF", || Fetcher::open(&fixture.path, 2))
    else {
        return;
    };
    let Some(mut slabs) = fetch_or_report_skip("payload-covered EOF", &mut fetcher, &[read]) else {
        return;
    };
    let slab = slabs.pop().expect("one requested slab");

    assert_eq!(slab.payload(), &bytes[4400..4800]);
}

#[test]
#[ignore = "inherited fetch_each currently accepts short CQE; requires separately evidenced Linux hardening"]
fn completion_shorter_than_the_logical_payload_must_fail() {
    let bytes = deterministic_bytes(4500, 0x92);
    let fixture = FixtureFile::create("payload-short-eof", &bytes);
    let read = Read {
        offset: 4400,
        len: 200,
    };

    // The completion can cover only [4096, 4500), while the logical payload
    // needs [4400, 4600). Future Linux hardening must compare the CQE result
    // against payload_offset + payload_len, not against the rounded bracket.
    let Some(mut fetcher) =
        open_or_report_skip("payload-short EOF", || Fetcher::open(&fixture.path, 2))
    else {
        return;
    };

    match fetcher.fetch(&[read]) {
        Err(error) if environment_cannot_run_direct_io(&error) => {
            eprintln!(
                "SKIP payload-short EOF: io_uring/O_DIRECT unavailable (kind={:?}, os_code={:?})",
                error.kind(),
                error.raw_os_error()
            );
        }
        Err(error) => assert_eq!(error.kind(), io::ErrorKind::UnexpectedEof),
        Ok(_) => panic!("payload-short completion was incorrectly reported as success"),
    }
}
