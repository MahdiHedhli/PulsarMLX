use std::error::Error;
use std::fmt;
use std::fs::File;
use std::io;
use std::path::{Path, PathBuf};

use crate::Read;

/// One path in a contiguous logical shard layout.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ShardPath {
    pub base: u64,
    pub path: PathBuf,
}

#[derive(Debug, Clone, Copy)]
pub struct MatrixReadSpec {
    pub tensor_offset: u64,
    pub rows: u64,
    pub row_bytes: u64,
}

impl MatrixReadSpec {
    pub fn total_bytes(&self) -> Option<u64> {
        self.rows.checked_mul(self.row_bytes)
    }
}

#[derive(Debug, Default, Clone, Copy)]
pub struct ReadTelemetry {
    pub request_count: u64,
    pub requested_bytes: u64,
    pub actual_bytes: u64,
}

/// An exact, owned payload returned by an [`ExpertSource`].
///
/// This type deliberately does not implement `Clone`: transferring a fetched
/// expert slab should be explicit, and its bytes remain valid independently of
/// the source that produced them.
#[derive(Debug, PartialEq, Eq)]
pub struct OwnedSlab {
    range: Read,
    bytes: Box<[u8]>,
}

impl OwnedSlab {
    pub fn range(&self) -> Read {
        self.range
    }

    pub fn payload(&self) -> &[u8] {
        &self.bytes
    }
}

/// Backend-neutral exact expert byte source.
pub trait ExpertSource: Send {
    fn fetch_exact(&mut self, read: Read) -> Result<OwnedSlab, SourceError>;

    fn fetch_batch(&mut self, reads: &[Read]) -> Result<Vec<OwnedSlab>, SourceError>;
}

/// Injectable positional-reader seam used by the portable source.
pub trait PositionalRead: Send + Sync {
    fn read_at(&self, destination: &mut [u8], local_offset: u64) -> io::Result<usize>;
}

#[cfg(unix)]
impl PositionalRead for File {
    fn read_at(&self, destination: &mut [u8], local_offset: u64) -> io::Result<usize> {
        std::os::unix::fs::FileExt::read_at(self, destination, local_offset)
    }
}

#[cfg(windows)]
impl PositionalRead for File {
    fn read_at(&self, destination: &mut [u8], local_offset: u64) -> io::Result<usize> {
        std::os::windows::fs::FileExt::seek_read(self, destination, local_offset)
    }
}

/// An already-opened logical shard, primarily for alternate source adapters
/// and deterministic contract tests.
pub struct ReaderShard {
    base: u64,
    length: u64,
    identity: String,
    reader: Box<dyn PositionalRead>,
}

impl ReaderShard {
    pub fn new(
        base: u64,
        length: u64,
        identity: impl Into<String>,
        reader: Box<dyn PositionalRead>,
    ) -> Self {
        Self {
            base,
            length,
            identity: identity.into(),
            reader,
        }
    }
}

struct OpenShard {
    base: u64,
    end: u64,
    #[allow(dead_code)]
    identity: String,
    reader: Box<dyn PositionalRead>,
}

/// A portable exact source backed by retained file handles and positional I/O.
pub struct PositionalSource {
    shards: Vec<OpenShard>,
    first_base: u64,
    virtual_end: u64,
}

impl PositionalSource {
    pub fn open(path: &Path) -> Result<Self, SourceError> {
        Self::open_split(&[ShardPath {
            base: 0,
            path: path.to_path_buf(),
        }])
    }

    pub fn open_split(shards: &[ShardPath]) -> Result<Self, SourceError> {
        if shards.is_empty() {
            return Err(SourceError::EmptyShardSet);
        }

        let mut readers = Vec::with_capacity(shards.len());
        for (shard, entry) in shards.iter().enumerate() {
            let file = File::open(&entry.path).map_err(|source| SourceError::Io {
                operation: "open",
                shard,
                local_offset: 0,
                source,
            })?;
            let length = file
                .metadata()
                .map_err(|source| SourceError::Io {
                    operation: "metadata",
                    shard,
                    local_offset: 0,
                    source,
                })?
                .len();
            readers.push(ReaderShard::new(
                entry.base,
                length,
                format!("shard-{shard}"),
                Box::new(file),
            ));
        }
        Self::from_readers(readers)
    }

    /// Read whole-row chunks. A zero cap means the entire matrix is one request;
    /// a nonzero cap smaller than one row is refused before any reader call.
    /// Chunks are all prevalidated in a bounded-memory first pass. The returned
    /// vector retains the complete matrix: the cap bounds I/O, not total residency.
    pub fn fetch_matrix_whole(
        &mut self,
        spec: MatrixReadSpec,
        max_request_bytes: u64,
        telemetry: &mut ReadTelemetry,
    ) -> Result<Vec<OwnedSlab>, SourceError> {
        let too_large = || SourceError::MatrixParameterTooLarge {
            rows: spec.rows,
            row_bytes: spec.row_bytes,
        };
        if spec.rows == 0 || spec.row_bytes == 0 {
            return Err(SourceError::ZeroLengthMatrix {
                tensor_offset: spec.tensor_offset,
            });
        }
        let total = spec.total_bytes().ok_or_else(too_large)?;
        let end = spec
            .tensor_offset
            .checked_add(total)
            .ok_or(SourceError::RangeOverflow {
                offset: spec.tensor_offset,
                len: total,
            })?;
        let rows = usize::try_from(spec.rows).map_err(|_| too_large())?;
        let row_bytes = usize::try_from(spec.row_bytes).map_err(|_| too_large())?;
        if total > isize::MAX as u64 {
            return Err(too_large());
        }
        if max_request_bytes != 0 && max_request_bytes < spec.row_bytes {
            return Err(SourceError::MatrixRequestLimit {
                row_bytes: spec.row_bytes,
                max_request_bytes,
            });
        }
        let rows_per_chunk = if max_request_bytes == 0 {
            rows
        } else {
            usize::try_from((max_request_bytes / spec.row_bytes).min(spec.rows))
                .map_err(|_| too_large())?
        };
        if spec.tensor_offset < self.first_base {
            return Err(SourceError::BelowBase {
                offset: spec.tensor_offset,
                first_base: self.first_base,
            });
        }
        if end > self.virtual_end {
            return Err(SourceError::BeyondEnd {
                offset: spec.tensor_offset,
                len: total,
                virtual_end: self.virtual_end,
            });
        }
        // Total/end arithmetic above proves intermediate offsets and lengths fit.
        // Recreate this iterator for the I/O pass rather than storing per-row plans.
        let chunks = || {
            (0..rows).step_by(rows_per_chunk).map(|row| Read {
                offset: spec.tensor_offset + (row * row_bytes) as u64,
                len: ((rows - row).min(rows_per_chunk) * row_bytes) as u64,
            })
        };
        for read in chunks() {
            self.validate(read)?;
        }
        let mut out = Vec::new();
        for read in chunks() {
            out.push(self.fetch_exact_with_telemetry(read, telemetry)?);
        }
        Ok(out)
    }

    pub fn fetch_matrix_rows(
        &mut self,
        spec: MatrixReadSpec,
        telemetry: &mut ReadTelemetry,
    ) -> Result<Vec<OwnedSlab>, SourceError> {
        self.fetch_matrix_whole(spec, spec.row_bytes, telemetry)
    }

    /// Constructs a source over injected positional readers.
    ///
    /// This is public so alternate adapters can share the exact source
    /// contract; callers must provide the snapshotted physical lengths.
    #[doc(hidden)]
    pub fn from_readers(shards: Vec<ReaderShard>) -> Result<Self, SourceError> {
        if shards.is_empty() {
            return Err(SourceError::EmptyShardSet);
        }

        let mut opened: Vec<OpenShard> = Vec::with_capacity(shards.len());
        for (shard, entry) in shards.into_iter().enumerate() {
            if entry.length == 0 {
                return Err(SourceError::ZeroLengthShard { shard });
            }
            let end = entry
                .base
                .checked_add(entry.length)
                .ok_or(SourceError::LayoutOverflow {
                    shard,
                    base: entry.base,
                    len: entry.length,
                })?;

            if let Some(previous) = opened.last() {
                if entry.base <= previous.base {
                    return Err(SourceError::UnsortedShards {
                        previous: shard - 1,
                        shard,
                    });
                }
                if entry.base > previous.end {
                    return Err(SourceError::ShardGap {
                        previous_end: previous.end,
                        next_base: entry.base,
                    });
                }
                if entry.base < previous.end {
                    return Err(SourceError::ShardOverlap {
                        previous_end: previous.end,
                        next_base: entry.base,
                    });
                }
            }

            opened.push(OpenShard {
                base: entry.base,
                end,
                identity: entry.identity,
                reader: entry.reader,
            });
        }

        let first_base = opened[0].base;
        let virtual_end = opened
            .last()
            .expect("nonempty shard layout was checked")
            .end;
        Ok(Self {
            shards: opened,
            first_base,
            virtual_end,
        })
    }

    fn validate(&self, read: Read) -> Result<ValidatedRead, SourceError> {
        if read.len == 0 {
            return Err(SourceError::ZeroLengthRead {
                offset: read.offset,
            });
        }
        let end = read
            .offset
            .checked_add(read.len)
            .ok_or(SourceError::RangeOverflow {
                offset: read.offset,
                len: read.len,
            })?;
        if read.offset < self.first_base {
            return Err(SourceError::BelowBase {
                offset: read.offset,
                first_base: self.first_base,
            });
        }
        if end > self.virtual_end {
            return Err(SourceError::BeyondEnd {
                offset: read.offset,
                len: read.len,
                virtual_end: self.virtual_end,
            });
        }
        let len =
            usize::try_from(read.len).map_err(|_| SourceError::LengthTooLarge { len: read.len })?;

        let shard = match self
            .shards
            .binary_search_by_key(&read.offset, |entry| entry.base)
        {
            Ok(shard) => shard,
            Err(insertion) => insertion - 1,
        };
        let entry = &self.shards[shard];
        if end > entry.end {
            return Err(SourceError::StraddlesShard {
                offset: read.offset,
                len: read.len,
                shard_end: entry.end,
            });
        }

        Ok(ValidatedRead {
            range: read,
            shard,
            local_offset: read.offset - entry.base,
            len,
        })
    }

    fn fetch_validated(&self, read: ValidatedRead) -> Result<OwnedSlab, SourceError> {
        self.fetch_validated_tracked(read, None)
    }

    fn fetch_validated_tracked(
        &self,
        read: ValidatedRead,
        mut telemetry: Option<&mut ReadTelemetry>,
    ) -> Result<OwnedSlab, SourceError> {
        let mut bytes = vec![0_u8; read.len].into_boxed_slice();
        let mut actual = 0_usize;
        while actual < read.len {
            let remaining = &mut bytes[actual..];
            let local_offset = read.local_offset + actual as u64;
            match self.shards[read.shard]
                .reader
                .read_at(remaining, local_offset)
            {
                Ok(0) => {
                    return Err(SourceError::ShortRead {
                        shard: read.shard,
                        local_offset: read.local_offset,
                        expected: read.len,
                        actual,
                    });
                }
                Ok(count) if count > remaining.len() => {
                    return Err(SourceError::DestinationLength {
                        expected: remaining.len(),
                        actual: count,
                    });
                }
                Ok(count) => {
                    actual += count;
                    if let Some(traffic) = telemetry.as_deref_mut() {
                        // The full request's accounting capacity was prechecked.
                        traffic.actual_bytes += count as u64;
                    }
                }
                Err(source) if source.kind() == io::ErrorKind::Interrupted => continue,
                Err(source) => {
                    return Err(SourceError::Io {
                        operation: "read",
                        shard: read.shard,
                        local_offset,
                        source,
                    });
                }
            }
        }

        Ok(OwnedSlab {
            range: read.range,
            bytes,
        })
    }

    fn fetch_exact_with_telemetry(
        &mut self,
        read: Read,
        telemetry: &mut ReadTelemetry,
    ) -> Result<OwnedSlab, SourceError> {
        let count = telemetry
            .request_count
            .checked_add(1)
            .ok_or(SourceError::TelemetryOverflow)?;
        let requested = telemetry
            .requested_bytes
            .checked_add(read.len)
            .ok_or(SourceError::TelemetryOverflow)?;
        telemetry
            .actual_bytes
            .checked_add(read.len)
            .ok_or(SourceError::TelemetryOverflow)?;
        let validated = self.validate(read)?;
        telemetry.request_count = count;
        telemetry.requested_bytes = requested;
        self.fetch_validated_tracked(validated, Some(telemetry))
    }
}

impl ExpertSource for PositionalSource {
    fn fetch_exact(&mut self, read: Read) -> Result<OwnedSlab, SourceError> {
        let validated = self.validate(read)?;
        self.fetch_validated(validated)
    }

    fn fetch_batch(&mut self, reads: &[Read]) -> Result<Vec<OwnedSlab>, SourceError> {
        let validated = reads
            .iter()
            .copied()
            .map(|read| self.validate(read))
            .collect::<Result<Vec<_>, _>>()?;
        validated
            .into_iter()
            .map(|read| self.fetch_validated(read))
            .collect()
    }
}

#[derive(Clone, Copy)]
struct ValidatedRead {
    range: Read,
    shard: usize,
    local_offset: u64,
    len: usize,
}

#[derive(Debug)]
pub enum SourceError {
    TelemetryOverflow,
    EmptyShardSet,
    ZeroLengthShard {
        shard: usize,
    },
    UnsortedShards {
        previous: usize,
        shard: usize,
    },
    ShardGap {
        previous_end: u64,
        next_base: u64,
    },
    ShardOverlap {
        previous_end: u64,
        next_base: u64,
    },
    LayoutOverflow {
        shard: usize,
        base: u64,
        len: u64,
    },
    ZeroLengthRead {
        offset: u64,
    },
    RangeOverflow {
        offset: u64,
        len: u64,
    },
    BelowBase {
        offset: u64,
        first_base: u64,
    },
    BeyondEnd {
        offset: u64,
        len: u64,
        virtual_end: u64,
    },
    StraddlesShard {
        offset: u64,
        len: u64,
        shard_end: u64,
    },
    LengthTooLarge {
        len: u64,
    },
    DestinationLength {
        expected: usize,
        actual: usize,
    },
    ShortRead {
        shard: usize,
        local_offset: u64,
        expected: usize,
        actual: usize,
    },
    ZeroLengthMatrix {
        tensor_offset: u64,
    },
    MatrixRequestLimit {
        row_bytes: u64,
        max_request_bytes: u64,
    },
    MatrixParameterTooLarge {
        rows: u64,
        row_bytes: u64,
    },
    Io {
        operation: &'static str,
        shard: usize,
        local_offset: u64,
        source: io::Error,
    },
}

impl fmt::Display for SourceError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::TelemetryOverflow => write!(formatter, "read telemetry counter overflow"),
            Self::EmptyShardSet => write!(formatter, "the shard set is empty"),
            Self::ZeroLengthShard { shard } => {
                write!(formatter, "shard {shard} has zero length")
            }
            Self::UnsortedShards { previous, shard } => write!(
                formatter,
                "shard {shard} is not ordered after shard {previous}"
            ),
            Self::ShardGap {
                previous_end,
                next_base,
            } => write!(
                formatter,
                "shard layout has a gap between {previous_end} and {next_base}"
            ),
            Self::ShardOverlap {
                previous_end,
                next_base,
            } => write!(
                formatter,
                "shard layout overlaps at {next_base} before {previous_end}"
            ),
            Self::LayoutOverflow { shard, base, len } => write!(
                formatter,
                "shard {shard} range overflows: base {base}, length {len}"
            ),
            Self::ZeroLengthRead { offset } => {
                write!(formatter, "read at offset {offset} has zero length")
            }
            Self::RangeOverflow { offset, len } => {
                write!(formatter, "read range overflows: offset {offset}, length {len}")
            }
            Self::BelowBase { offset, first_base } => write!(
                formatter,
                "read offset {offset} is below first shard base {first_base}"
            ),
            Self::BeyondEnd {
                offset,
                len,
                virtual_end,
            } => write!(
                formatter,
                "read at {offset} with length {len} exceeds logical end {virtual_end}"
            ),
            Self::StraddlesShard {
                offset,
                len,
                shard_end,
            } => write!(
                formatter,
                "read at {offset} with length {len} straddles shard end {shard_end}"
            ),
            Self::LengthTooLarge { len } => {
                write!(formatter, "read length {len} does not fit the allocation size")
            }
            Self::DestinationLength { expected, actual } => write!(
                formatter,
                "reader reported {actual} bytes for a destination of length {expected}"
            ),
            Self::ShortRead {
                shard,
                local_offset,
                expected,
                actual,
            } => write!(
                formatter,
                "short read from shard {shard} at local offset {local_offset}: expected {expected}, got {actual}"
            ),
            Self::ZeroLengthMatrix { tensor_offset } => {
                write!(formatter, "matrix read with zero logical length at tensor offset {tensor_offset}")
            }
            Self::MatrixRequestLimit { row_bytes, max_request_bytes } => write!(formatter, "matrix row {row_bytes} exceeds request limit {max_request_bytes}"),
            Self::MatrixParameterTooLarge { rows, row_bytes } => {
                write!(formatter, "matrix params overflow: rows {rows}, row_bytes {row_bytes}")
            }
            Self::Io {
                operation,
                shard,
                local_offset,
                source,
            } => write!(
                formatter,
                "{operation} failed for shard {shard} at local offset {local_offset}: {source}"
            ),
        }
    }
}

impl Error for SourceError {
    fn source(&self) -> Option<&(dyn Error + 'static)> {
        match self {
            Self::Io { source, .. } => Some(source),
            _ => None,
        }
    }
}
