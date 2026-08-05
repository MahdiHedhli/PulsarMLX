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
                Ok(count) => actual += count,
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
