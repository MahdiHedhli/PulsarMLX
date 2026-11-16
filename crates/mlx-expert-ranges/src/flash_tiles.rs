//! Descriptor-bound cold text forward. Only contiguous row tiles, one expert/head plane at a time.
use super::*;
use mlx_affine::module::ByteSlice;
pub const MAX_ROWS: usize = 64;
const MAX_READ: usize = 4 * 1024 * 1024;
const MAX_TRAFFIC: u64 = 14_500_000_000;
pub struct FlashRows {
    src: BoundedSource,
}
pub struct Matrix {
    pub rows: usize,
    pub cols: usize,
    pub bits: u32,
    slices: [ByteSlice; 3],
}
impl FlashRows {
    pub fn new(path: &Path, snapshot: &str, witness: &serde_json::Value) -> Result<Self> {
        if !path.is_absolute() || path.canonicalize().map_err(|e| refusal("PATH", e))? != path {
            return Err(refusal("PATH", "noncanonical root"));
        }
        let src = BoundedSource::open(path)?;
        if src.metadata_snapshot() != snapshot {
            return Err(refusal("CUSTODY", "metadata snapshot"));
        }
        for (k, f) in &src.held {
            let st = &f.stamp;
            let obs = serde_json::json!([
                st.dev,
                st.ino,
                st.len,
                st.mtime as i128 * 1_000_000_000 + st.mtime_ns as i128,
                st.ctime as i128 * 1_000_000_000 + st.ctime_ns as i128
            ]);
            if witness.get(k) != Some(&obs) {
                return Err(refusal("CUSTODY", k));
            }
            f.check()?;
        }
        Ok(Self { src })
    }
    /// Admit the full real text model while only immutable metadata has been read.
    pub fn new_checked_text(
        path: &Path,
        snapshot: &str,
        witness: &serde_json::Value,
    ) -> Result<Self> {
        let rows = Self::new(path, snapshot, witness)?;
        super::text_config::admit(&rows.src)?;
        Ok(rows)
    }
    fn fetch(&self, s: ByteSlice, off: u64, n: u64) -> Result<Vec<u8>> {
        if n == 0 || n > MAX_READ as u64 || off.checked_add(n).is_none_or(|e| e > s.len) {
            return Err(refusal("BUDGET", "row range"));
        }
        let name = self
            .src
            .checkpoint
            .shard_name(s.shard)
            .map_err(|e| refusal("RANGE", e))?;
        let h = &self.src.held[name];
        h.check()?;
        let start = s
            .begin
            .checked_add(off)
            .ok_or_else(|| refusal("OVERFLOW", "offset"))?;
        if start.checked_add(n).is_none_or(|e| e > h.stamp.len)
            || self
                .src
                .requested_payload_bytes()
                .checked_add(n)
                .is_none_or(|v| v > MAX_TRAFFIC)
        {
            return Err(refusal("BUDGET", "range outside receipt"));
        }
        self.src
            .requested_payload_bytes
            .fetch_add(n, Ordering::Relaxed);
        self.src.payload_read_calls.fetch_add(1, Ordering::Relaxed);
        let mut b = vec![0; n as usize];
        h.file
            .read_exact_at(&mut b, start)
            .map_err(|e| refusal("READ", e))?;
        h.check()?;
        Ok(b)
    }
    pub fn raw(&self, k: &str) -> Result<(Vec<u64>, String, Vec<u8>)> {
        if !k.starts_with("language_model.") {
            return Err(refusal("ROLE", "only text"));
        }
        let m = self
            .src
            .checkpoint
            .catalog()
            .get(k)
            .ok_or_else(|| refusal("WEIGHT", k))?;
        if !matches!(m.dtype, Dtype::Bf16 | Dtype::F32)
            || k.ends_with(".scales")
            || k.ends_with(".biases")
        {
            return Err(refusal("ROLE", "expected small raw parameter"));
        }
        let b = self.fetch(
            ByteSlice {
                shard: m.shard,
                begin: m.data_begin,
                len: m.byte_len,
            },
            0,
            m.byte_len,
        )?;
        Ok((m.shape.clone(), m.dtype.as_str().to_owned(), b))
    }
    pub fn matrix(&self, k: &str, group: Option<usize>) -> Result<Matrix> {
        if !k.starts_with("language_model.") {
            return Err(refusal("ROLE", "only text"));
        }
        let kind = classify_module(self.src.checkpoint.catalog(), Some(&self.src.config), k)
            .map_err(|e| refusal("RECIPE", e))?;
        let ModuleKind::Quantized(t) = kind else {
            return Err(refusal("RECIPE", "packed affine required"));
        };
        let indices: Vec<_> = group.into_iter().map(|x| x as u64).collect();
        let sl = t.expert_slice(&indices).map_err(|e| refusal("RANGE", e))?;
        let bits = t.spec().bits.get();
        let rows = t.out_features();
        let cols = t.in_features();
        if t.spec().group_size.get() != 64
            || !matches!(bits, 4 | 8)
            || t.scales().dtype != Dtype::Bf16
            || t.biases().dtype != Dtype::Bf16
            || rows == 0
            || rows > 154880
            || cols == 0
            || cols > 24576
            || cols % 64 != 0
        {
            return Err(refusal("RECIPE", k));
        }
        Ok(Matrix {
            rows: rows as usize,
            cols: cols as usize,
            bits,
            slices: [sl.weight, sl.scales, sl.biases],
        })
    }
    pub fn tile(&self, m: &Matrix, row: usize, n: usize) -> Result<[Vec<u8>; 3]> {
        if n == 0 || n > MAX_ROWS || row.checked_add(n).is_none_or(|z| z > m.rows) {
            return Err(refusal("BUDGET", "tile rows"));
        }
        let stride = [
            m.cols * m.bits as usize / 8,
            m.cols / 64 * 2,
            m.cols / 64 * 2,
        ];
        let read = |i: usize| {
            if m.slices[i].len != m.rows as u64 * stride[i] as u64 {
                return Err(refusal("RANGE", "wrong row stride"));
            }
            self.fetch(
                m.slices[i],
                (row * stride[i]) as u64,
                (n * stride[i]) as u64,
            )
        };
        Ok([read(0)?, read(1)?, read(2)?])
    }
    pub fn finish(&self) -> Result<(u64, u64)> {
        for f in self.src.held.values() {
            f.check()?
        }
        Ok((
            self.src.requested_payload_bytes(),
            self.src.payload_read_calls(),
        ))
    }
}
