//! The request body: `Content-Length` or a chunked `Transfer-Encoding`, within the body
//! limit.
//!
//! - When the last comma-separated value of `Transfer-Encoding` is `chunked` (stripped,
//!   lower-cased), the body is decoded from chunks: a size line of at most 1025 bytes read
//!   as Python's `int(line.split(b";")[0].strip(), 16)`, the chunk, and `\r\n`; after the
//!   zero chunk, up to 64 trailer lines of at most 8193 bytes, up to a blank one. A bad size,
//!   a size line without `\n`, a short chunk or a missing `\r\n` is 400 "malformed chunked
//!   request body"; a running total over the limit is 413 before that chunk is read.
//! - A request with both a `Content-Length` header and a `Transfer-Encoding` header that
//!   names `chunked` among its comma-separated values (any such header, not only the first)
//!   is 400 before any body byte is read (approved deviation P-2; the donor silently prefers
//!   chunked). The transport refuses it before the handler is called, on every route and
//!   for every served method; [`read_body`] checks again.
//! - Otherwise `Content-Length` (first header of that name) is read as Python's `int()`: not
//!   an integer, or negative, is 400 "invalid Content-Length"; over the limit is 413 before
//!   any body byte is read; absent means an empty body. A body shorter than its length
//!   because the client closed is returned short, as Python's `rfile.read(n)` returns it.
//!
//! Behavior reference: project-maya serve/server.py:5375-5381 and 5416-5455 at 7e68a30f.

use std::time::Duration;

use tokio::io::AsyncBufRead;

use super::config::{py_hex_chunk_size, py_int, trim_ascii_space, ENV_MAX_BODY_MIB};
use super::head::Headers;
use super::io::{read_line, read_up_to, ReadFail};
use super::response::ClientGone;
use crate::error::ApiError;

/// The 400 message of a malformed chunked body.
pub const MALFORMED_CHUNKED: &str = "malformed chunked request body";

/// The 400 message of a `Content-Length` that is not a non-negative integer.
pub const INVALID_CONTENT_LENGTH: &str = "invalid Content-Length";

/// The 400 message of a request with both `Content-Length` and a chunked
/// `Transfer-Encoding` (approved deviation P-2, owner decision of 2026-11-14).
pub const CONFLICTING_FRAMING: &str =
    "both Content-Length and a chunked Transfer-Encoding were sent; send only one";

/// The longest chunk-size line Python reads (`readline(1025)`).
const CHUNK_SIZE_LINE: usize = 1025;

/// The longest trailer line Python reads (`readline(8193)`).
const TRAILER_LINE: usize = 8193;

/// The most trailer lines Python reads.
const MAX_TRAILERS: usize = 64;

/// Why no body was returned.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum BodyError {
    /// The body is refused: answer this error (the donor's `BadBody`) with
    /// [`Responder::error`](super::Responder::error).
    Refused(ApiError),
    /// The client went away or a read timed out: answer nothing and return, so the
    /// connection closes (Python's `TimeoutError` and `ConnectionError` paths).
    Gone(ClientGone),
    /// The body was already read, or the connection's reading side was given to the client
    /// watcher.
    Unavailable,
}

impl From<ReadFail> for BodyError {
    fn from(fail: ReadFail) -> Self {
        match fail {
            ReadFail::TimedOut => BodyError::Gone(ClientGone::TimedOut),
            // A reset is Python's silent ConnectionError; any other socket error also ends
            // the connection without an answer.
            ReadFail::Io => BodyError::Gone(ClientGone::Disconnected),
        }
    }
}

/// The 413 answer for a body over `limit` bytes.
///
/// Behavior reference: project-maya serve/server.py:5437-5440 and 5451-5454 at 7e68a30f;
/// the variable is renamed under approved deviation BRAND-1 (contracts/naming.md).
pub fn too_large(limit: u64) -> ApiError {
    ApiError::bad_body(
        413,
        format!(
            "the request body is larger than {} MiB ({ENV_MAX_BODY_MIB} raises the limit)",
            limit >> 20
        ),
    )
}

/// True when the request is chunked by the donor's rule: the last comma-separated value of
/// the first `Transfer-Encoding` header, stripped and lower-cased, is `chunked`.
pub fn is_chunked(headers: &Headers) -> bool {
    let te = headers.get("Transfer-Encoding").unwrap_or("");
    let last = te.rsplit(',').next().unwrap_or("");
    console_pyjson::pystr::strip(last, None).to_lowercase() == "chunked"
}

/// True when the request carries both framings (approved deviation P-2): a `Content-Length`
/// header (any value, empty included) and a `Transfer-Encoding` header with a
/// comma-separated value that is `chunked` once stripped and lower-cased, in any position
/// and in any of the `Transfer-Encoding` headers.
pub fn has_conflicting_framing(headers: &Headers) -> bool {
    headers.get("Content-Length").is_some()
        && headers.get_all("Transfer-Encoding").any(|te| {
            te.split(',')
                .any(|v| console_pyjson::pystr::strip(v, None).to_lowercase() == "chunked")
        })
}

/// Reads the request body.
pub(crate) async fn read_body<R: AsyncBufRead + Unpin>(
    reader: &mut R,
    headers: &Headers,
    limit: u64,
    timeout: Duration,
) -> Result<Vec<u8>, BodyError> {
    // Approved deviation P-2: ambiguous framing is refused, not resolved. The transport
    // already refused it before dispatch; this is the second guard.
    if has_conflicting_framing(headers) {
        return Err(BodyError::Refused(ApiError::bad_body(
            400,
            CONFLICTING_FRAMING,
        )));
    }
    if is_chunked(headers) {
        return read_chunked(reader, limit, timeout).await;
    }
    let length = match headers.get("Content-Length") {
        None => 0,
        Some(text) => match py_int(text) {
            Some(v) if !v.negative => v.magnitude,
            _ => {
                return Err(BodyError::Refused(ApiError::bad_body(
                    400,
                    INVALID_CONTENT_LENGTH,
                )))
            }
        },
    };
    if length > limit {
        return Err(BodyError::Refused(too_large(limit)));
    }
    Ok(read_up_to(reader, length, timeout).await?)
}

async fn read_chunked<R: AsyncBufRead + Unpin>(
    reader: &mut R,
    limit: u64,
    timeout: Duration,
) -> Result<Vec<u8>, BodyError> {
    let malformed = || BodyError::Refused(ApiError::bad_body(400, MALFORMED_CHUNKED));
    let mut body = Vec::new();
    let mut total: u64 = 0;
    loop {
        let line = read_line(reader, CHUNK_SIZE_LINE, timeout).await?;
        let size = py_hex_chunk_size(&line).ok_or_else(malformed)?;
        if size.negative || !line.ends_with(b"\n") {
            return Err(malformed());
        }
        if size.magnitude == 0 {
            for _ in 0..MAX_TRAILERS {
                let trailer = read_line(reader, TRAILER_LINE, timeout).await?;
                if trim_ascii_space(&trailer).is_empty() {
                    break;
                }
            }
            return Ok(body);
        }
        total = total.saturating_add(size.magnitude);
        if total > limit {
            return Err(BodyError::Refused(too_large(limit)));
        }
        let piece = read_up_to(reader, size.magnitude, timeout).await?;
        if piece.len() as u64 != size.magnitude {
            return Err(malformed());
        }
        let end = read_up_to(reader, 2, timeout).await?;
        if end != b"\r\n" {
            return Err(malformed());
        }
        body.extend_from_slice(&piece);
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    const T: Duration = Duration::from_secs(5);
    const LIMIT: u64 = 1 << 20;

    fn headers(list: &[(&str, &str)]) -> Headers {
        Headers::from_pairs(
            list.iter()
                .map(|(k, v)| ((*k).into(), (*v).into()))
                .collect(),
        )
    }

    async fn body(list: &[(&str, &str)], mut raw: &[u8]) -> Result<Vec<u8>, BodyError> {
        read_body(&mut raw, &headers(list), LIMIT, T).await
    }

    fn refused(status: u16, message: &str) -> Result<Vec<u8>, BodyError> {
        Err(BodyError::Refused(ApiError::bad_body(status, message)))
    }

    #[tokio::test]
    async fn content_length_follows_the_donor() {
        assert_eq!(body(&[], b"ignored").await, Ok(Vec::new()));
        assert_eq!(
            body(&[("Content-Length", "3")], b"abcdef").await,
            Ok(b"abc".to_vec())
        );
        assert_eq!(
            body(&[("content-length", " +3 ")], b"abc").await,
            Ok(b"abc".to_vec())
        );
        assert_eq!(
            body(&[("Content-Length", "-0")], b"abc").await,
            Ok(Vec::new())
        );
        // A client that closes early leaves a short body (Python's read(n)).
        assert_eq!(
            body(&[("Content-Length", "20")], b"{}").await,
            Ok(b"{}".to_vec())
        );
        for bad in ["abc", "-5", "", "1 2", "0x10", "1.0"] {
            assert_eq!(
                body(&[("Content-Length", bad)], b"").await,
                refused(400, "invalid Content-Length"),
                "{bad:?}"
            );
        }
        // The first Content-Length header counts.
        assert_eq!(
            body(&[("Content-Length", "1"), ("Content-Length", "2")], b"ab").await,
            Ok(b"a".to_vec())
        );
        assert_eq!(
            body(&[("Content-Length", "1048577")], b"").await,
            refused(413, "the request body is larger than 1 MiB (PULSAR_CONSOLE_MAX_BODY_MIB raises the limit)")
        );
        assert_eq!(
            body(&[("Content-Length", &"9".repeat(40))], b"").await,
            Err(BodyError::Refused(too_large(LIMIT)))
        );
    }

    #[tokio::test]
    async fn chunked_bodies_follow_the_donor() {
        let te = [("Transfer-Encoding", "chunked")];
        assert_eq!(
            body(&te, b"5\r\nhello\r\n0\r\n\r\n").await,
            Ok(b"hello".to_vec())
        );
        assert_eq!(
            body(
                &te,
                b"3;x=y\r\nabc\r\n2\nde\r\n0\r\nTrailer: 1\r\nMore: 2\r\n\r\nrest"
            )
            .await,
            Ok(b"abcde".to_vec())
        );
        assert_eq!(
            body(
                &[("Transfer-Encoding", "gzip, Chunked ")],
                b"1\r\nx\r\n0\r\n"
            )
            .await,
            Ok(b"x".to_vec())
        );
        // Not chunked unless chunked is last.
        assert_eq!(
            body(&[("Transfer-Encoding", "chunked, gzip")], b"1\r\nx").await,
            Ok(Vec::new())
        );
        for bad in [
            &b"zz\r\nab\r\n0\r\n\r\n"[..],
            b"-1\r\n",
            b"2\r\nab",
            b"2\r\nabXX0\r\n\r\n",
            b"3\r\nab",
            b"1",
            b"",
        ] {
            assert_eq!(
                body(&te, bad).await,
                refused(400, "malformed chunked request body"),
                "{bad:?}"
            );
        }
        let mut big = b"100001\r\n".to_vec();
        big.extend_from_slice(b"never read");
        assert_eq!(
            body(&te, &big).await,
            Err(BodyError::Refused(too_large(LIMIT)))
        );
        // A running total: two chunks that are each under the limit.
        let mut two = b"80000\r\n".to_vec();
        two.extend(std::iter::repeat_n(b'x', 0x80000));
        two.extend_from_slice(b"\r\n80001\r\n");
        assert_eq!(
            body(&te, &two).await,
            Err(BodyError::Refused(too_large(LIMIT)))
        );
        // 64 trailer lines are read at most; the body is returned after them.
        let mut trailers = b"1\r\nq\r\n0\r\n".to_vec();
        for _ in 0..70 {
            trailers.extend_from_slice(b"T: v\r\n");
        }
        assert_eq!(body(&te, &trailers).await, Ok(b"q".to_vec()));
    }

    #[tokio::test]
    async fn both_framings_are_refused() {
        // Approved deviation P-2.
        assert_eq!(
            body(
                &[("Content-Length", "5"), ("Transfer-Encoding", "chunked")],
                b"5\r\nhello\r\n0\r\n\r\n"
            )
            .await,
            refused(400, CONFLICTING_FRAMING)
        );
        assert_eq!(
            body(
                &[("Transfer-Encoding", "chunked"), ("Content-Length", "")],
                b""
            )
            .await,
            refused(400, CONFLICTING_FRAMING)
        );
        // Chunked anywhere in any Transfer-Encoding header counts, not only the donor's
        // decoding rule (the last value of the first header).
        for te in [
            &[("Transfer-Encoding", "chunked, gzip")][..],
            &[
                ("Transfer-Encoding", "gzip"),
                ("Transfer-Encoding", "chunked"),
            ],
            &[("transfer-encoding", " CHUNKED ")],
        ] {
            let mut list = te.to_vec();
            list.push(("Content-Length", "2"));
            assert!(has_conflicting_framing(&headers(&list)), "{list:?}");
            assert_eq!(
                body(&list, b"ab").await,
                refused(400, CONFLICTING_FRAMING),
                "{list:?}"
            );
        }
        // A Transfer-Encoding without chunked, with a Content-Length, is the donor's plain
        // path; so is chunked framing alone.
        let plain = [("Transfer-Encoding", "gzip"), ("Content-Length", "2")];
        assert!(!has_conflicting_framing(&headers(&plain)));
        assert_eq!(body(&plain, b"ab").await, Ok(b"ab".to_vec()));
        assert!(!has_conflicting_framing(&headers(&[(
            "Transfer-Encoding",
            "chunked"
        )])));
        assert!(!has_conflicting_framing(&headers(&[
            ("Transfer-Encoding", "xchunked"),
            ("Content-Length", "1")
        ])));
    }
}
