//! Bounded socket reads with the per-operation timeout.
//!
//! Every wait for the socket gets its own timeout, as Python's `socket.settimeout` gives
//! each `recv` and `send`; a request that keeps trickling bytes is never cut by an overall
//! deadline.
//!
//! Behavior reference: project-maya serve/server.py:5354-5362 at 7e68a30f, and CPython 3.14
//! `socketserver.StreamRequestHandler.setup` (the handler's `timeout`).

use std::io;
use std::time::Duration;

use tokio::io::{AsyncBufRead, AsyncBufReadExt};

/// Why a read ended without its data.
#[derive(Debug)]
pub(crate) enum ReadFail {
    /// One wait for the socket took longer than the per-operation timeout.
    TimedOut,
    /// The socket failed (reset, or another error).
    Io,
}

/// Waits for buffered data, within `limit`. An empty slice is end of file.
async fn fill<R: AsyncBufRead + Unpin>(reader: &mut R, limit: Duration) -> Result<&[u8], ReadFail> {
    match tokio::time::timeout(limit, reader.fill_buf()).await {
        Err(_) => Err(ReadFail::TimedOut),
        Ok(Err(_)) => Err(ReadFail::Io),
        Ok(Ok(buf)) => Ok(buf),
    }
}

/// Python `readline(max)`: bytes up to and including the next `\n`, or `max` bytes, or what
/// is left before end of file (possibly nothing).
pub(crate) async fn read_line<R: AsyncBufRead + Unpin>(
    reader: &mut R,
    max: usize,
    limit: Duration,
) -> Result<Vec<u8>, ReadFail> {
    let mut out = Vec::new();
    while out.len() < max {
        let want = max - out.len();
        let (taken, complete) = {
            let buf = fill(reader, limit).await?;
            if buf.is_empty() {
                break;
            }
            let window = buf.get(..buf.len().min(want)).unwrap_or(buf);
            match window.iter().position(|&b| b == b'\n') {
                Some(pos) => {
                    out.extend_from_slice(window.get(..=pos).unwrap_or(window));
                    (pos + 1, true)
                }
                None => {
                    out.extend_from_slice(window);
                    (window.len(), false)
                }
            }
        };
        reader.consume(taken);
        if complete {
            break;
        }
    }
    Ok(out)
}

/// Python `read(n)` on a buffered socket file: up to `n` bytes, fewer only at end of file.
/// Memory grows with the bytes received, never with `n` alone.
pub(crate) async fn read_up_to<R: AsyncBufRead + Unpin>(
    reader: &mut R,
    n: u64,
    limit: Duration,
) -> Result<Vec<u8>, ReadFail> {
    let mut out = Vec::new();
    let mut remaining = n;
    while remaining > 0 {
        let taken = {
            let buf = fill(reader, limit).await?;
            if buf.is_empty() {
                break;
            }
            let take = usize::try_from(remaining).map_or(buf.len(), |r| r.min(buf.len()));
            out.extend_from_slice(buf.get(..take).unwrap_or(buf));
            take
        };
        reader.consume(taken);
        remaining = remaining.saturating_sub(taken as u64);
    }
    Ok(out)
}

/// True for the errors Python reports as `ConnectionError` (reset, aborted, broken pipe,
/// refused): the client went away.
pub(crate) fn is_connection_error(e: &io::Error) -> bool {
    matches!(
        e.kind(),
        io::ErrorKind::ConnectionReset
            | io::ErrorKind::ConnectionAborted
            | io::ErrorKind::BrokenPipe
            | io::ErrorKind::ConnectionRefused
    )
}

#[cfg(test)]
mod tests {
    use super::*;

    const T: Duration = Duration::from_secs(5);

    #[tokio::test]
    async fn readline_stops_at_newline_limit_or_eof() {
        let mut r: &[u8] = b"ab\ncd\nefgh";
        assert!(matches!(read_line(&mut r, 100, T).await, Ok(v) if v == b"ab\n"));
        assert!(matches!(read_line(&mut r, 2, T).await, Ok(v) if v == b"cd"));
        assert!(matches!(read_line(&mut r, 100, T).await, Ok(v) if v == b"\n"));
        assert!(matches!(read_line(&mut r, 100, T).await, Ok(v) if v == b"efgh"));
        assert!(matches!(read_line(&mut r, 100, T).await, Ok(v) if v.is_empty()));
    }

    #[tokio::test]
    async fn read_up_to_is_short_only_at_eof() {
        let mut r: &[u8] = b"0123456789";
        assert!(matches!(read_up_to(&mut r, 4, T).await, Ok(v) if v == b"0123"));
        assert!(matches!(read_up_to(&mut r, 0, T).await, Ok(v) if v.is_empty()));
        assert!(matches!(read_up_to(&mut r, u64::MAX, T).await, Ok(v) if v == b"456789"));
    }
}
