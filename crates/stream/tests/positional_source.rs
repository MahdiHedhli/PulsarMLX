use std::collections::VecDeque;
use std::fs::{self, OpenOptions};
use std::io;
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicUsize, Ordering};
use std::sync::{Arc, Mutex};

use stream::{
    ExpertSource, OwnedSlab, PositionalRead, PositionalSource, Read, ReaderShard, ShardPath,
    MatrixReadSpec, ReadTelemetry, SourceError,
};

static NEXT_TEMP_FILE: AtomicUsize = AtomicUsize::new(0);

// This intentionally fails to compile if `OwnedSlab` ever gains `Clone`.
const _: fn() = || {
    trait AmbiguousIfClone<A> {
        fn marker() {}
    }

    impl<T: ?Sized> AmbiguousIfClone<()> for T {}

    struct ImplementsClone;
    impl<T: Clone> AmbiguousIfClone<ImplementsClone> for T {}

    let _ = <OwnedSlab as AmbiguousIfClone<_>>::marker;
};

struct TestFile {
    path: PathBuf,
}

impl TestFile {
    fn new(label: &str, bytes: &[u8]) -> Self {
        let serial = NEXT_TEMP_FILE.fetch_add(1, Ordering::Relaxed);
        let path = std::env::temp_dir().join(format!(
            "pulsar-mlx-positional-{label}-{}-{serial}.bin",
            std::process::id()
        ));
        fs::write(&path, bytes).expect("write positional-source fixture");
        Self { path }
    }

    fn path(&self) -> &Path {
        &self.path
    }

    fn truncate(&self, len: u64) {
        OpenOptions::new()
            .write(true)
            .open(&self.path)
            .expect("open fixture for truncation")
            .set_len(len)
            .expect("truncate fixture");
    }
}

impl Drop for TestFile {
    fn drop(&mut self) {
        let _ = fs::remove_file(&self.path);
    }
}

#[derive(Clone, Copy, Debug)]
enum ReadAction {
    Limit(usize),
    Interrupted,
    Zero,
}

#[derive(Clone)]
struct ReaderProbe {
    calls: Arc<AtomicUsize>,
    requests: Arc<Mutex<Vec<(u64, usize)>>>,
}

impl ReaderProbe {
    fn calls(&self) -> usize {
        self.calls.load(Ordering::SeqCst)
    }

    fn requests(&self) -> Vec<(u64, usize)> {
        self.requests.lock().expect("request log lock").clone()
    }
}

struct ScriptedReader {
    bytes: Vec<u8>,
    actions: Mutex<VecDeque<ReadAction>>,
    probe: ReaderProbe,
}

impl ScriptedReader {
    fn new(bytes: &[u8], actions: impl IntoIterator<Item = ReadAction>) -> (Self, ReaderProbe) {
        let probe = ReaderProbe {
            calls: Arc::new(AtomicUsize::new(0)),
            requests: Arc::new(Mutex::new(Vec::new())),
        };
        (
            Self {
                bytes: bytes.to_vec(),
                actions: Mutex::new(actions.into_iter().collect()),
                probe: probe.clone(),
            },
            probe,
        )
    }
}

impl PositionalRead for ScriptedReader {
    fn read_at(&self, destination: &mut [u8], local_offset: u64) -> io::Result<usize> {
        self.probe.calls.fetch_add(1, Ordering::SeqCst);
        self.probe
            .requests
            .lock()
            .expect("request log lock")
            .push((local_offset, destination.len()));

        let action = self
            .actions
            .lock()
            .expect("action queue lock")
            .pop_front()
            .unwrap_or(ReadAction::Limit(usize::MAX));
        match action {
            ReadAction::Interrupted => Err(io::Error::from(io::ErrorKind::Interrupted)),
            ReadAction::Zero => Ok(0),
            ReadAction::Limit(limit) => {
                let start = usize::try_from(local_offset).unwrap_or(usize::MAX);
                let available = self.bytes.len().saturating_sub(start);
                let count = destination.len().min(available).min(limit);
                if count != 0 {
                    destination[..count].copy_from_slice(&self.bytes[start..start + count]);
                }
                Ok(count)
            }
        }
    }
}

fn reader_shard(
    base: u64,
    length: u64,
    identity: &str,
    reader: impl PositionalRead + 'static,
) -> ReaderShard {
    ReaderShard::new(base, length, identity, Box::new(reader))
}

fn expect_source_error<T>(result: Result<T, SourceError>) -> SourceError {
    match result {
        Ok(_) => panic!("operation unexpectedly succeeded"),
        Err(error) => error,
    }
}

#[test]
fn single_shard_reads_first_last_and_exact_end() {
    let file = TestFile::new("single", &[10, 11, 12, 13, 14]);
    let mut source = PositionalSource::open(file.path()).expect("open single shard");

    let first = source
        .fetch_exact(Read { offset: 0, len: 1 })
        .expect("read first byte");
    assert_eq!(first.range(), Read { offset: 0, len: 1 });
    assert_eq!(first.payload(), &[10]);

    let exact_end = source
        .fetch_exact(Read { offset: 2, len: 3 })
        .expect("read ending exactly at shard end");
    assert_eq!(exact_end.range(), Read { offset: 2, len: 3 });
    assert_eq!(exact_end.payload(), &[12, 13, 14]);

    let last = source
        .fetch_exact(Read { offset: 4, len: 1 })
        .expect("read last byte");
    assert_eq!(last.payload(), &[14]);
    assert_eq!(
        last.payload().len(),
        usize::try_from(last.range().len).unwrap()
    );
}

#[test]
fn split_layout_routes_exact_boundaries_without_concatenation() {
    let first = TestFile::new("split-a", &[10, 11, 12, 13]);
    let second = TestFile::new("split-b", &[20, 21, 22]);
    let mut source = PositionalSource::open_split(&[
        ShardPath {
            base: 100,
            path: first.path().to_path_buf(),
        },
        ShardPath {
            base: 104,
            path: second.path().to_path_buf(),
        },
    ])
    .expect("open contiguous split layout");

    assert_eq!(
        source
            .fetch_exact(Read {
                offset: 101,
                len: 3,
            })
            .expect("read ending at first shard boundary")
            .payload(),
        &[11, 12, 13]
    );
    assert_eq!(
        source
            .fetch_exact(Read {
                offset: 104,
                len: 3,
            })
            .expect("read beginning at second shard boundary")
            .payload(),
        &[20, 21, 22]
    );
    assert_eq!(
        source
            .fetch_exact(Read {
                offset: 106,
                len: 1,
            })
            .expect("read final logical byte")
            .payload(),
        &[22]
    );

    match expect_source_error(source.fetch_exact(Read {
        offset: 103,
        len: 2,
    })) {
        SourceError::StraddlesShard {
            offset,
            len,
            shard_end,
        } => {
            assert_eq!((offset, len, shard_end), (103, 2, 104));
        }
        other => panic!("expected StraddlesShard, got {other:?}"),
    }
}

#[test]
fn split_layout_may_start_at_a_nonzero_base() {
    let file = TestFile::new("nonzero-base", &[1, 2, 3]);
    let mut source = PositionalSource::open_split(&[ShardPath {
        base: 4096,
        path: file.path().to_path_buf(),
    }])
    .expect("generic source accepts nonzero first base");

    assert_eq!(
        source
            .fetch_exact(Read {
                offset: 4096,
                len: 3,
            })
            .expect("read nonzero-base shard")
            .payload(),
        &[1, 2, 3]
    );
}

#[test]
fn layout_rejects_empty_and_zero_length_shard_sets() {
    match expect_source_error(PositionalSource::open_split(&[])) {
        SourceError::EmptyShardSet => {}
        other => panic!("expected EmptyShardSet, got {other:?}"),
    }

    let empty = TestFile::new("empty", &[]);
    match expect_source_error(PositionalSource::open(empty.path())) {
        SourceError::ZeroLengthShard { shard } => assert_eq!(shard, 0),
        other => panic!("expected ZeroLengthShard, got {other:?}"),
    }
}

#[test]
fn layout_rejects_duplicate_descending_gapped_and_overlapping_bases() {
    let (reader, _) = ScriptedReader::new(&[0; 8], []);
    let (other, _) = ScriptedReader::new(&[0; 8], []);
    match expect_source_error(PositionalSource::from_readers(vec![
        reader_shard(10, 4, "duplicate-a", reader),
        reader_shard(10, 4, "duplicate-b", other),
    ])) {
        SourceError::UnsortedShards { previous, shard } => {
            assert_eq!((previous, shard), (0, 1));
        }
        other => panic!("expected UnsortedShards for duplicate bases, got {other:?}"),
    }

    let (reader, _) = ScriptedReader::new(&[0; 8], []);
    let (other, _) = ScriptedReader::new(&[0; 8], []);
    match expect_source_error(PositionalSource::from_readers(vec![
        reader_shard(20, 4, "descending-a", reader),
        reader_shard(10, 4, "descending-b", other),
    ])) {
        SourceError::UnsortedShards { previous, shard } => {
            assert_eq!((previous, shard), (0, 1));
        }
        other => panic!("expected UnsortedShards for descending bases, got {other:?}"),
    }

    let (reader, _) = ScriptedReader::new(&[0; 8], []);
    let (other, _) = ScriptedReader::new(&[0; 8], []);
    match expect_source_error(PositionalSource::from_readers(vec![
        reader_shard(10, 4, "gap-a", reader),
        reader_shard(15, 4, "gap-b", other),
    ])) {
        SourceError::ShardGap {
            previous_end,
            next_base,
        } => assert_eq!((previous_end, next_base), (14, 15)),
        other => panic!("expected ShardGap, got {other:?}"),
    }

    let (reader, _) = ScriptedReader::new(&[0; 8], []);
    let (other, _) = ScriptedReader::new(&[0; 8], []);
    match expect_source_error(PositionalSource::from_readers(vec![
        reader_shard(10, 5, "overlap-a", reader),
        reader_shard(14, 4, "overlap-b", other),
    ])) {
        SourceError::ShardOverlap {
            previous_end,
            next_base,
        } => assert_eq!((previous_end, next_base), (15, 14)),
        other => panic!("expected ShardOverlap, got {other:?}"),
    }
}

#[test]
fn layout_end_arithmetic_is_checked() {
    let (reader, _) = ScriptedReader::new(&[0; 2], []);
    match expect_source_error(PositionalSource::from_readers(vec![reader_shard(
        u64::MAX - 1,
        2,
        "overflow",
        reader,
    )])) {
        SourceError::LayoutOverflow { shard, base, len } => {
            assert_eq!((shard, base, len), (0, u64::MAX - 1, 2))
        }
        other => panic!("expected LayoutOverflow, got {other:?}"),
    }
}

#[test]
fn ranges_reject_zero_overflow_below_base_and_beyond_end() {
    let (reader, probe) = ScriptedReader::new(&[0; 8], []);
    let mut source =
        PositionalSource::from_readers(vec![reader_shard(100, 8, "range-validation", reader)])
            .expect("open injected source");

    match expect_source_error(source.fetch_exact(Read {
        offset: 100,
        len: 0,
    })) {
        SourceError::ZeroLengthRead { offset } => assert_eq!(offset, 100),
        other => panic!("expected ZeroLengthRead, got {other:?}"),
    }
    match expect_source_error(source.fetch_exact(Read {
        offset: u64::MAX,
        len: 2,
    })) {
        SourceError::RangeOverflow { offset, len } => {
            assert_eq!((offset, len), (u64::MAX, 2));
        }
        other => panic!("expected RangeOverflow, got {other:?}"),
    }
    match expect_source_error(source.fetch_exact(Read { offset: 99, len: 1 })) {
        SourceError::BelowBase { offset, first_base } => {
            assert_eq!((offset, first_base), (99, 100));
        }
        other => panic!("expected BelowBase, got {other:?}"),
    }
    match expect_source_error(source.fetch_exact(Read {
        offset: 108,
        len: 1,
    })) {
        SourceError::BeyondEnd {
            offset,
            len,
            virtual_end,
        } => assert_eq!((offset, len, virtual_end), (108, 1, 108)),
        other => panic!("expected BeyondEnd at logical end, got {other:?}"),
    }
    match expect_source_error(source.fetch_exact(Read {
        offset: 107,
        len: 2,
    })) {
        SourceError::BeyondEnd {
            offset,
            len,
            virtual_end,
        } => assert_eq!((offset, len, virtual_end), (107, 2, 108)),
        other => panic!("expected BeyondEnd past logical end, got {other:?}"),
    }

    assert_eq!(probe.calls(), 0, "invalid ranges must not issue I/O");
}

#[cfg(target_pointer_width = "32")]
#[test]
fn range_length_must_fit_the_allocation_size() {
    let length = u64::from(u32::MAX) + 1;
    let (reader, probe) = ScriptedReader::new(&[], []);
    let mut source =
        PositionalSource::from_readers(vec![reader_shard(0, length, "allocation-width", reader)])
            .expect("open injected large logical shard");

    match expect_source_error(source.fetch_exact(Read {
        offset: 0,
        len: length,
    })) {
        SourceError::LengthTooLarge { len } => assert_eq!(len, length),
        other => panic!("expected LengthTooLarge, got {other:?}"),
    }
    assert_eq!(probe.calls(), 0);
}

#[test]
fn invalid_batch_is_prevalidated_before_any_reader_io() {
    let (reader, probe) = ScriptedReader::new(&[0; 8], []);
    let mut source =
        PositionalSource::from_readers(vec![reader_shard(500, 8, "batch-prevalidation", reader)])
            .expect("open injected source");

    match expect_source_error(source.fetch_batch(&[
        Read {
            offset: 500,
            len: 2,
        },
        Read {
            offset: 507,
            len: 2,
        },
    ])) {
        SourceError::BeyondEnd {
            offset,
            len,
            virtual_end,
        } => assert_eq!((offset, len, virtual_end), (507, 2, 508)),
        other => panic!("expected BeyondEnd, got {other:?}"),
    }
    assert_eq!(
        probe.calls(),
        0,
        "the valid batch prefix must not be read before all ranges validate"
    );
}

#[test]
fn positional_loop_retries_interrupted_and_advances_after_partial_reads() {
    let (reader, probe) = ScriptedReader::new(
        b"abcdefg",
        [
            ReadAction::Limit(2),
            ReadAction::Interrupted,
            ReadAction::Limit(1),
        ],
    );
    let mut source =
        PositionalSource::from_readers(vec![reader_shard(1000, 7, "partial-reader", reader)])
            .expect("open injected source");

    let slab = source
        .fetch_exact(Read {
            offset: 1001,
            len: 5,
        })
        .expect("complete partial reads around Interrupted");

    assert_eq!(slab.payload(), b"bcdef");
    assert_eq!(
        probe.requests(),
        vec![(1, 5), (3, 3), (3, 3), (4, 2)],
        "Interrupted retries the same offset; only returned bytes advance it"
    );
}

#[test]
fn zero_read_before_completion_is_a_structured_short_read() {
    let (reader, probe) = ScriptedReader::new(b"abcdef", [ReadAction::Limit(2), ReadAction::Zero]);
    let mut source =
        PositionalSource::from_readers(vec![reader_shard(700, 6, "zero-reader", reader)])
            .expect("open injected source");

    match expect_source_error(source.fetch_exact(Read {
        offset: 700,
        len: 6,
    })) {
        SourceError::ShortRead {
            shard,
            local_offset,
            expected,
            actual,
        } => assert_eq!((shard, local_offset, expected, actual), (0, 0, 6, 2)),
        other => panic!("expected ShortRead, got {other:?}"),
    }
    assert_eq!(probe.requests(), vec![(0, 6), (2, 4)]);
}

#[test]
fn truncation_after_open_is_a_short_read_not_partial_success() {
    let file = TestFile::new("truncate", b"abcdefgh");
    let mut source = PositionalSource::open(file.path()).expect("open fixture before truncation");
    file.truncate(3);

    match expect_source_error(source.fetch_exact(Read { offset: 0, len: 8 })) {
        SourceError::ShortRead {
            shard,
            local_offset,
            expected,
            actual,
        } => assert_eq!((shard, local_offset, expected, actual), (0, 0, 8, 3)),
        other => panic!("expected ShortRead after truncation, got {other:?}"),
    }
}

#[test]
fn batch_preserves_input_order_and_duplicate_ranges() {
    let file = TestFile::new("batch-order", b"abcdefgh");
    let mut source = PositionalSource::open(file.path()).expect("open batch fixture");
    let reads = [
        Read { offset: 4, len: 2 },
        Read { offset: 0, len: 2 },
        Read { offset: 4, len: 2 },
        Read { offset: 2, len: 2 },
    ];

    let slabs = source.fetch_batch(&reads).expect("fetch ordered batch");
    assert_eq!(slabs.len(), reads.len());
    for (slab, expected_range) in slabs.iter().zip(reads) {
        assert_eq!(slab.range(), expected_range);
    }
    assert_eq!(slabs[0].payload(), b"ef");
    assert_eq!(slabs[1].payload(), b"ab");
    assert_eq!(slabs[2].payload(), b"ef");
    assert_eq!(slabs[3].payload(), b"cd");
}

#[test]
fn batch_io_failure_returns_only_the_error() {
    let (reader, probe) = ScriptedReader::new(
        b"abcdefgh",
        [
            ReadAction::Limit(usize::MAX),
            ReadAction::Limit(1),
            ReadAction::Zero,
        ],
    );
    let mut source =
        PositionalSource::from_readers(vec![reader_shard(0, 8, "batch-io-error", reader)])
            .expect("open injected source");

    let result = source.fetch_batch(&[Read { offset: 0, len: 2 }, Read { offset: 2, len: 4 }]);
    match expect_source_error(result) {
        SourceError::ShortRead {
            shard,
            local_offset,
            expected,
            actual,
        } => assert_eq!((shard, local_offset, expected, actual), (0, 2, 4, 1)),
        other => panic!("expected ShortRead, got {other:?}"),
    }
    assert_eq!(probe.calls(), 3);
}

#[test]
fn owned_payload_survives_source_drop_and_thread_move() {
    fn assert_send<T: Send>() {}
    assert_send::<PositionalSource>();
    assert_send::<OwnedSlab>();

    let file = TestFile::new("owned", b"owned-payload");
    let slab = {
        let mut source = PositionalSource::open(file.path()).expect("open ownership fixture");
        source
            .fetch_exact(Read { offset: 6, len: 7 })
            .expect("fetch owned payload")
    };

    let (range, payload) = std::thread::spawn(move || (slab.range(), slab.payload().to_vec()))
        .join()
        .expect("move slab to another thread");
    assert_eq!(range, Read { offset: 6, len: 7 });
    assert_eq!(payload, b"payload");
}

#[test]
fn matrix_whole_read_matches_row_reads_and_tracks_telemetry() {
    let bytes: Vec<u8> = (0_u8..64_u8).collect();
    let file = TestFile::new("matrix-whole", &bytes);
    let mut source = PositionalSource::open(file.path()).expect("open matrix fixture");

    let shape = MatrixReadSpec {
        tensor_offset: 0,
        rows: 8,
        row_bytes: 8,
    };

    let mut whole_traffic = ReadTelemetry::default();
    let matrix = source
        .fetch_matrix_whole(shape, 64, &mut whole_traffic)
        .expect("fetch whole matrix");
    let matrix_payload: Vec<u8> = matrix
        .iter()
        .flat_map(|slab| slab.payload().iter().copied())
        .collect();

    let mut row_traffic = ReadTelemetry::default();
    let rows = source
        .fetch_matrix_rows(shape, &mut row_traffic)
        .expect("fetch matrix rows");
    let row_payload: Vec<u8> = rows
        .iter()
        .flat_map(|slab| slab.payload().iter().copied())
        .collect();

    assert_eq!(matrix_payload.len(), 64);
    assert_eq!(matrix_payload, row_payload);
    assert_eq!(whole_traffic.request_count, 1);
    assert_eq!(whole_traffic.requested_bytes, 64);
    assert_eq!(whole_traffic.actual_bytes, 64);
    assert_eq!(row_traffic.request_count, 8);
    assert_eq!(row_traffic.requested_bytes, 64);
    assert_eq!(row_traffic.actual_bytes, 64);
}

#[test]
fn matrix_read_honors_request_sizing_and_chunks() {
    let bytes: Vec<u8> = (0_u8..100_u8).collect();
    let file = TestFile::new("matrix-chunk", &bytes);
    let mut source = PositionalSource::open(file.path()).expect("open matrix chunk fixture");

    let shape = MatrixReadSpec {
        tensor_offset: 0,
        rows: 10,
        row_bytes: 9,
    };

    let mut telemetry = ReadTelemetry::default();
    let chunks = source
        .fetch_matrix_whole(shape, 32, &mut telemetry)
        .expect("fetch matrix in chunks");

    assert!(chunks.len() >= 2);
    let chunk_rows = chunks.iter().map(|slab| slab.payload().len()).collect::<Vec<_>>();
    assert_eq!(chunk_rows.iter().sum::<usize>(), 90);
    assert_eq!(telemetry.request_count, chunk_rows.len() as u64);
    assert_eq!(telemetry.requested_bytes, 90);
    assert_eq!(telemetry.actual_bytes, 90);
}
