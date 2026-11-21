use crate::{
    graph::{Provider, R},
    native::{self, DeviceKind, NativeContext},
};
use mlx_expert_ranges::flash_tiles::{FlashRows, Matrix, MAX_ROWS};
use mlx_native_affine::dtype::Dtype;
use std::path::Path;
extern "C" {
    fn studio017_aux(
        x: *const f32,
        w: *const f32,
        n: i32,
        k: i32,
        rank: i32,
        f: *mut f32,
        ids: *mut u32,
        stream: crate::ffi::mlx_stream,
    ) -> i32;
    fn studio017_limits() -> i32;
    fn studio017_affine4(
        x: *const u16,
        w: *const u8,
        s: *const u8,
        b: *const u8,
        cols: i32,
        n: i32,
        out: *mut u16,
        stream: crate::ffi::mlx_stream,
    ) -> i32;
}
fn err(e: impl std::fmt::Display) -> String {
    e.to_string()
}
fn decode(dtype: &str, bytes: &[u8]) -> R<Vec<f32>> {
    let v: Vec<_> = match dtype {
        "F32" if bytes.len() % 4 == 0 => bytes
            .chunks_exact(4)
            .map(|b| f32::from_le_bytes(b.try_into().unwrap()))
            .collect(),
        "BF16" if bytes.len() % 2 == 0 => bytes
            .chunks_exact(2)
            .map(|b| f32::from_bits((u16::from_le_bytes(b.try_into().unwrap()) as u32) << 16))
            .collect(),
        _ => return Err("unexpected scalar format".into()),
    };
    if v.is_empty() || v.iter().any(|f| !f.is_finite()) {
        return Err("empty/nonfinite tensor".into());
    }
    Ok(v)
}
pub struct Metal {
    src: FlashRows,
    ctx: NativeContext,
}
impl Metal {
    pub fn open(root: &Path, snapshot: &str, w: &serde_json::Value) -> R<Self> {
        let src = FlashRows::new_checked_text(root, snapshot, w).map_err(err)?;
        native::ensure_error_handler();
        if !native::metal_available().map_err(err)? {
            return Err("Metal unavailable".into());
        }
        native::set_default_device_gpu().map_err(err)?;
        let ctx = NativeContext::new(DeviceKind::Gpu).map_err(err)?;
        if unsafe { studio017_limits() } != 0 {
            return Err("allocator limits refused".into());
        }
        Ok(Self { src, ctx })
    }
    fn run_tile(&self, m: &Matrix, row: usize, n: usize, x: Option<&[f32]>) -> R<Vec<f32>> {
        let [pw, sc, bi] = self.src.tile(m, row, n).map_err(err)?;
        copied_tile(&self.ctx, m.cols, m.bits, n, &pw, &sc, &bi, x)
    }
    pub fn finish(self) -> R<serde_json::Value> {
        let (bytes, reads) = self.src.finish().map_err(err)?;
        self.ctx.synchronize().map_err(err)?;
        let peak = native::peak_memory().map_err(err)?;
        drop(self);
        native::drain_residual_error("studio017 teardown");
        let (live, freed) = native::handle_census();
        if live != 0
            || native::double_free_attempts() != 0
            || !native::cleanup_errors().is_empty()
            || native::handler_messages() != 0
            || peak > 512 << 20
        {
            return Err("native cleanup/allocator".into());
        }
        Ok(
            serde_json::json!({"logical_bytes":bytes,"reads":reads,"native_allocator_peak":peak,"affine_handles_freed":freed,"affine_live":live}),
        )
    }
}
impl Provider for Metal {
    fn linear(&mut self, path: &str, g: Option<usize>, x: &[f32]) -> R<Vec<f32>> {
        if path.ends_with(".mlp.gate") {
            if g.is_some() || x.len() != 4096 {
                return Err("router geometry".into());
            }
            let (sh, dt, raw) = self.src.raw(&format!("{path}.weight")).map_err(err)?;
            if sh != [288, 4096] || dt != "BF16" {
                return Err("router weight geometry".into());
            }
            let weights = decode(&dt, &raw)?;
            let mut y = vec![0.; 288];
            // SAFETY: self.ctx owns this same-thread stream for the synchronous
            // call; aux borrows it without retaining or freeing it.
            if unsafe {
                studio017_aux(
                    x.as_ptr(),
                    weights.as_ptr(),
                    4096,
                    288,
                    0,
                    y.as_mut_ptr(),
                    std::ptr::null_mut(),
                    self.ctx.borrowed_stream(),
                )
            } != 0
            {
                return Err("native F32 router".into());
            }
            return Ok(y);
        }
        let m = self.src.matrix(path, g).map_err(err)?;
        if x.len() != m.cols || (m.bits == 4) != path.contains(".switch_mlp.") {
            return Err("packed width/recipe".into());
        }
        let mut out = Vec::with_capacity(m.rows);
        for row in (0..m.rows).step_by(MAX_ROWS) {
            out.extend(self.run_tile(&m, row, MAX_ROWS.min(m.rows - row), Some(x))?)
        }
        Ok(out)
    }
    fn tensor(&mut self, path: &str) -> R<Vec<f32>> {
        let (_, dt, raw) = self.src.raw(path).map_err(err)?;
        decode(&dt, &raw)
    }
    fn embedding(&mut self, path: &str, t: usize) -> R<Vec<f32>> {
        let m = self.src.matrix(path, None).map_err(err)?;
        if (m.rows, m.cols, m.bits) != (154880, 4096, 8) {
            return Err("embedding geometry".into());
        }
        self.run_tile(&m, t, 1, None)
    }
    fn partition(&mut self, c: &[f32], k: usize) -> R<Vec<usize>> {
        if c.len() != 288 || k != 8 || c.iter().any(|x| !x.is_finite()) {
            return Err("invalid router scores".into());
        }
        let a: Vec<_> = c.iter().map(|x| -*x).collect();
        let mut out = [0u32; 8];
        // SAFETY: self.ctx remains live on its owning thread throughout aux.
        if unsafe {
            studio017_aux(
                a.as_ptr(),
                std::ptr::null(),
                288,
                8,
                1,
                std::ptr::null_mut(),
                out.as_mut_ptr(),
                self.ctx.borrowed_stream(),
            )
        } != 0
        {
            return Err("native router partition".into());
        }
        Ok(out.iter().map(|&i| i as usize).collect())
    }
}

pub(crate) fn copied_tile(
    ctx: &NativeContext,
    cols: usize,
    bits: u32,
    n: usize,
    pw: &[u8],
    sc: &[u8],
    bi: &[u8],
    x: Option<&[f32]>,
) -> R<Vec<f32>> {
    if !matches!(bits, 4 | 8)
        || n == 0
        || n > MAX_ROWS
        || cols == 0
        || cols > 24576
        || cols % 64 != 0
        || pw.len() != n * cols * bits as usize / 8
        || sc.len() != n * cols / 64 * 2
        || bi.len() != sc.len()
        || x.is_some_and(|v| v.len() != cols)
    {
        return Err("invalid copied tile shape".into());
    }
    if bits == 4 && x.is_some() {
        let x = x.unwrap();
        if cols > 4096 || x.iter().any(|y| !y.is_finite() || y.to_bits() & 65535 != 0) {
            return Err("4-bit BF16 geometry/edge".into());
        }
        let input: Vec<u16> = x.iter().map(|y| (y.to_bits() >> 16) as u16).collect();
        let mut out = vec![0u16; n];
        // SAFETY: ctx stays borrowed for this synchronous call on its owning
        // thread. affine4 neither retains nor frees the stream, and evaluates
        // and synchronizes it before copying output, including after 8-bit ops.
        let rc = unsafe {
            studio017_affine4(
                input.as_ptr(),
                pw.as_ptr(),
                sc.as_ptr(),
                bi.as_ptr(),
                cols as i32,
                n as i32,
                out.as_mut_ptr(),
                ctx.borrowed_stream(),
            )
        };
        if rc != 0 {
            native::drain_residual_error("affine4 Metal kernel");
            eprintln!("affine4 error: {:?}", native::cleanup_errors());
            return Err(format!(
                "packed BF16 affine4 status {rc}: handler count {}",
                native::handler_messages()
            ));
        }
        return decode(
            "BF16",
            &out.iter().flat_map(|v| v.to_le_bytes()).collect::<Vec<_>>(),
        );
    }
    let w = ctx
        .import(Dtype::U32, &[n, cols * bits as usize / 32], pw)
        .map_err(err)?;
    let scale = ctx.import(Dtype::BF16, &[n, cols / 64], sc).map_err(err)?;
    let bias = ctx.import(Dtype::BF16, &[n, cols / 64], bi).map_err(err)?;
    let z = if let Some(x) = x {
        let mut raw = Vec::with_capacity(x.len() * 2);
        for t in x {
            if !t.is_finite() || t.to_bits() & 65535 != 0 {
                return Err("non-BF16 projection input".into());
            }
            raw.extend_from_slice(&((t.to_bits() >> 16) as u16).to_le_bytes());
        }
        let v = ctx.import(Dtype::BF16, &[1, cols], &raw).map_err(err)?;
        ctx.quantized_matmul(&v, &w, &scale, &bias, true, 64, bits)
            .map_err(err)?
    } else {
        ctx.dequantize(&w, &scale, &bias, 64, bits).map_err(err)?
    };
    let out = z.evaluate().map_err(err)?.host_copy().map_err(err)?;
    let shape = if x.is_some() { [1, n] } else { [n, cols] };
    if out.shape != shape || out.dtype != Dtype::BF16 {
        return Err("native result shape/dtype".into());
    }
    decode("BF16", &out.bytes)
}
