//! Synthetic-only child of graph.rs. Does not open a checkpoint, read grants,
//! run a real model, or supply golden routes/tensors to any candidate operation.
//! scripts/research/studio017_synthetic_fixture.py generates the independent comparison object.
use super::*;
use crate::{
    native::{self, DeviceKind, NativeContext},
    provider::copied_tile,
};
use serde_json::Value;
use std::collections::BTreeMap;
unsafe extern "C" {
    fn studio017_aux(
        x: *const f32,
        w: *const f32,
        n: i32,
        k: i32,
        rank: i32,
        f: *mut f32,
        ids: *mut u32,
    ) -> i32;
    fn studio017_limits() -> i32;
    fn studio017_synthetic_silu_bits(x: u16, s: *mut u16, o: *mut u16) -> i32;
}
const S: Shape = Shape {
    d: 8,
    vocab: 32,
    layers: 5,
    dense_layers: 3,
    dense_ff: 12,
    expert_ff: 4,
    experts: 10,
    select: 8,
    kda_h: 2,
    kda_d: 4,
    sparse_h: 2,
    sparse_d: 4,
    qrank: 4,
    latent: 4,
    index_h: 2,
    index_d: 4,
};
fn salt(p: &str) -> usize {
    p.bytes().fold(17, |h, c| (h * 3 + c as usize) % 101)
}
fn words(a: &[u8], bits: u32) -> Vec<u8> {
    let count = 32 / bits as usize;
    assert_eq!(a.len() % count, 0);
    a.chunks_exact(count)
        .flat_map(|ch| {
            let mut word = 0u32;
            for (i, &v) in ch.iter().enumerate() {
                assert!((v as u32) < 1 << bits);
                word |= (v as u32) << (i as u32 * bits);
            }
            word.to_le_bytes()
        })
        .collect()
}
fn halves(x: &[f32]) -> Vec<u8> {
    x.iter()
        .flat_map(|v| ((v.to_bits() >> 16) as u16).to_le_bytes())
        .collect()
}
fn affine(p: &str, rows: usize, width: usize, plane: usize, bits: u32) -> Vec<u8> {
    let h = salt(p);
    let mut a = vec![8u8; rows * 64];
    for i in 0..rows {
        let j = (i + h + plane) % width;
        let amp = if p == "language_model.lm_head" {
            if i == 17 {
                14
            } else {
                1 + i % 4
            }
        } else {
            1 + (i + plane + h) % 5
        };
        a[64 * i + j] += amp as u8;
        a[64 * i + (j + 1) % width] += 1;
    }
    words(&a, bits)
}
struct Fixture {
    ctx: NativeContext,
}
impl Provider for Fixture {
    fn tensor(&mut self, p: &str) -> R<Vec<f32>> {
        let n = if p.ends_with(".fn") {
            24 * 4 * 8
        } else if p.ends_with(".base") {
            24
        } else if p.ends_with(".scale") {
            3
        } else if p.ends_with("e_score_correction_bias") {
            10
        } else if p.ends_with("conv1d.weight") {
            3 * 8 * 4
        } else if p.ends_with("A_log") {
            2
        } else if p.ends_with("dt_bias") {
            8
        } else if p.ends_with("index_kpool_compress_gate") {
            4 * 8
        } else if p.ends_with("k_norm.bias") {
            4
        } else if p.ends_with("norm.weight") {
            if p.contains("self_attn.") {
                4
            } else {
                8
            }
        } else {
            return Err(format!("unknown synthetic raw {p}"));
        };
        let h = salt(p);
        Ok((0..n)
            .map(|j| {
                if p.ends_with("e_score_correction_bias") {
                    j as f32 / 16.
                } else if p.ends_with("norm.weight") {
                    1.
                } else if p.ends_with(".fn") {
                    (((j + h) % 9) as i32 - 4) as f32 / 128.
                } else if p.ends_with(".base") {
                    (((j * 3 + h) % 13) as i32 - 6) as f32 / 8.
                } else if p.ends_with(".scale") {
                    [1., 0.5, 0.75][j]
                } else if p.ends_with("conv1d.weight") {
                    (((j + h) % 7) + 1) as f32 / 8.
                } else if p.ends_with("A_log") {
                    ((j % 3) as i32 - 1) as f32 / 8.
                } else if p.ends_with("dt_bias") {
                    ((j % 7) as i32 - 3) as f32 / 16.
                } else if p.ends_with("k_norm.bias") {
                    ((j % 3) as i32 - 1) as f32 / 16.
                } else {
                    (((j + h) % 7) as i32 - 3) as f32 / 32.
                }
            })
            .collect())
    }
    fn embedding(&mut self, p: &str, t: usize) -> R<Vec<f32>> {
        assert_eq!(p, "language_model.model.embed_tokens");
        assert_eq!(t, 10);
        let a: Vec<_> = (0..64)
            .map(|i| if i < 8 { ((i + t) % 7 + 1) as u8 } else { 0 })
            .collect();
        let z = copied_tile(
            &self.ctx,
            64,
            8,
            1,
            &words(&a, 8),
            &halves(&[0.125]),
            &halves(&[0.]),
            None,
        )?;
        Ok(z[..8].into())
    }
    fn linear(&mut self, p: &str, group: Option<usize>, x: &[f32]) -> R<Vec<f32>> {
        if p.ends_with(".mlp.gate") {
            // Exercise the real F32 [288,4096] router primitive with a zero-padded synthetic block.
            let mut aa = [0f32; 4096];
            aa[..x.len()].copy_from_slice(x);
            let mut w = vec![0f32; 288 * 4096];
            let mut out = [0f32; 288];
            for i in 0..10 {
                for j in 0..8 {
                    w[i * 4096 + j] = (((i + j) % 5) as i32 - 2) as f32 / 16.;
                }
            }
            if unsafe {
                studio017_aux(
                    aa.as_ptr(),
                    w.as_ptr(),
                    4096,
                    288,
                    0,
                    out.as_mut_ptr(),
                    std::ptr::null_mut(),
                )
            } != 0
            {
                return Err("synthetic native router".into());
            }
            return Ok(out[..10].into());
        }
        let key = p.rsplit('.').next().unwrap();
        let rows = match key {
            "q_proj" | "k_proj" | "v_proj" | "o_proj" | "down_proj" | "wq_b" | "q_b_proj"
            | "f_b_proj" | "g_b_proj" => 8,
            "k_norm" | "f_a_proj" | "g_a_proj" | "kv_a_proj_with_mqa" | "wk" | "embed_q"
            | "q_a_proj" | "unembed_out" => 4,
            "b_proj" => 2,
            "lm_head" => 32,
            "gate_proj" | "up_proj" => {
                if p.contains("shared_experts") || p.contains("switch_mlp") {
                    4
                } else {
                    12
                }
            }
            _ => return Err(format!("unknown synthetic projection {p}")),
        };
        let bits = if p.contains("switch_mlp.") { 4 } else { 8 };
        let mut pad = [0.; 64];
        pad[..x.len()].copy_from_slice(x);
        copied_tile(
            &self.ctx,
            64,
            bits,
            rows,
            &affine(p, rows, x.len(), group.unwrap_or(0), bits),
            &halves(&vec![1. / 16.; rows]),
            &halves(&vec![-0.5; rows]),
            Some(&pad),
        )
    }
    fn partition(&mut self, c: &[f32], k: usize) -> R<Vec<usize>> {
        let mut a = [f32::MAX; 288];
        for (i, &v) in c.iter().enumerate() {
            a[i] = -v;
        }
        let mut ids = [0u32; 8];
        assert_eq!(k, 8);
        if unsafe {
            studio017_aux(
                a.as_ptr(),
                std::ptr::null(),
                288,
                8,
                1,
                std::ptr::null_mut(),
                ids.as_mut_ptr(),
            )
        } != 0
        {
            return Err("rank".into());
        }
        Ok(ids.iter().map(|i| *i as usize).collect())
    }
}
#[derive(Default)]
struct Audit {
    vectors: BTreeMap<(usize, String), Vec<f32>>,
    routes: Vec<(usize, Vec<usize>, Vec<f32>)>,
}
impl Witness for Audit {
    fn vector(&mut self, i: usize, n: &str, x: &[f32]) -> R<()> {
        assert!(self.vectors.insert((i, n.into()), x.into()).is_none());
        Ok(())
    }
    fn route(&mut self, i: usize, ids: &[usize], weights: &[f32], gap: f32) -> R<()> {
        assert!(gap > 0.);
        self.routes.push((i, ids.into(), weights.into()));
        Ok(())
    }
}
fn bf_rank(v: f32) -> i32 {
    let sign = if v.is_sign_negative() { -1 } else { 1 };
    (((v.to_bits() >> 16) & 0x7fff) as i32) * sign
}
fn check_bf(x: &[f32], v: &Value, label: &str) {
    let r = v.as_array().unwrap();
    assert_eq!(x.len(), r.len());
    for (i, (&a, b)) in x.iter().zip(r).enumerate() {
        let b = b.as_f64().unwrap() as f32;
        assert_eq!(a.to_bits() & 65535, 0);
        assert!(
            (bf_rank(a) - bf_rank(b)).abs() <= 1,
            "{label} lane {i}: {a} vs {b}"
        );
    }
}
include!("native_controls_full_width.rs");
include!("native_controls_stream_reuse.rs");

fn packed_control(ctx: &NativeContext, bits: u32) -> R<()> {
    // Cross a group boundary: nonzero x samples nibble/byte order, two scales
    // and opposite biases. A wrong axis, word order or missing bias changes result.
    let rows = 8;
    let cols = 128;
    let mut a = Vec::new();
    let mask = (1u32 << bits) - 1;
    for r in 0..rows {
        for c in 0..cols {
            a.push(((7 * c + 3 * r + 1) as u32 & mask) as u8);
        }
    }
    let mut x = vec![0.; cols];
    for (i, v) in [(0, 1.), (7, -0.5), (64, 0.25), (115, 2.)] {
        x[i] = v;
    }
    let mut sc = Vec::new();
    let mut bi = Vec::new();
    let mut expect = Vec::new();
    for r in 0..rows {
        sc.extend([0.25, 1.]);
        bi.extend([-3., 0.5]);
        let mut exact = 0.;
        for c in 0..cols {
            exact += x[c] * (f32::from(a[r * cols + c]) * sc[r * 2 + c / 64] + bi[r * 2 + c / 64]);
        }
        expect.push(bf(exact));
    }
    let out = copied_tile(
        ctx,
        cols,
        bits,
        rows,
        &words(&a, bits),
        &halves(&sc),
        &halves(&bi),
        Some(&x),
    )?;
    assert_eq!(out, expect, "real BF16 QMM bits={bits}");
    Ok(())
}
#[test]
#[ignore = "only the explicitly admitted finite Studio017 synthetic machine population"]
fn copied_packed_native_and_five_layer_reference() {
    native::ensure_error_handler();
    assert!(native::metal_available().unwrap());
    native::set_default_device_gpu().unwrap();
    let ctx = NativeContext::new(DeviceKind::Gpu).unwrap();
    assert_eq!(unsafe { studio017_limits() }, 0);
    // Adjudicate the BF16 multiplication boundary for affine embedding decode.
    // The same packed input distinguishes a fused final round from two BF16 rounds.
    let observed = copied_tile(
        &ctx,
        64,
        8,
        1,
        &words(&[3u8; 64], 8),
        &halves(&[1.0078125]),
        &halves(&[-2.96875]),
        None,
    )
    .unwrap();
    assert_eq!(observed.len(), 64);
    assert!(observed
        .iter()
        .all(|x| x.to_bits() == observed[0].to_bits()));
    let deq_bits = observed[0].to_bits() >> 16;
    eprintln!(
        "studio017_synthetic_embedding_f32bits={:08x} value={}",
        observed[0].to_bits(),
        observed[0]
    );
    assert!(
        [0x3d60, 0x3d80].contains(&deq_bits),
        "unexpected affine result"
    );
    // Regression for the identically zero affine row with nonrepresentable BF16 quartet sum.
    let mut input = [0.0; 64];
    input[..4].copy_from_slice(&[1.0, 1. / 256., 1. / 256., 1. / 256.]);
    let zero = copied_tile(
        &ctx,
        64,
        4,
        1,
        &words(&[8u8; 64], 4),
        &halves(&[1. / 16.]),
        &halves(&[-0.5]),
        Some(&input),
    )
    .unwrap();
    assert_eq!(
        zero,
        [0.0],
        "zero decoded weight must annihilate every input"
    );
    packed_control(&ctx, 4).unwrap();
    packed_control(&ctx, 8).unwrap();
    full_width_affine_controls(&ctx).unwrap();
    let (mut sg, mut si) = (0u16, 0u16);
    assert_eq!(
        unsafe { studio017_synthetic_silu_bits(0x3d88, &mut sg, &mut si) },
        0
    );
    eprintln!("studio017_synthetic_sigmoid_bf16={sg:04x} silu_bf16={si:04x}");
    assert_eq!((sg, si), (0x3f04, 0x3d0c));
    assert_eq!(silu_b(0.06640625).to_bits() >> 16, si as u32);
    let mut p = Fixture { ctx };
    let mut audit = Audit::default();
    let (logits, token) = cold(&mut p, &mut audit, 10, S).unwrap();
    // Golden is deliberately deserialized only after the candidate's return.
    let g: Value = serde_json::from_str(include_str!("native-fixture-golden.json")).unwrap();
    assert_eq!(token, g["token"].as_u64().unwrap() as usize);
    eprintln!(
        "studio017_fixture_logits={logits:?} routes={:?}",
        audit.routes
    );
    for ((layer, label), values) in &audit.vectors {
        if label == "layer.streams" || label == "attention.output" || label == "ffn.output" {
            eprintln!("fixture_layer={layer} stage={label} values={values:?}");
        }
    }
    check_bf(&logits, &g["logits"], "synthetic logits");
    assert_eq!(audit.routes.len(), 2);
    for (row, (i, ids, weights)) in g["routes"].as_array().unwrap().iter().zip(&audit.routes) {
        assert_eq!(*i, row[0].as_u64().unwrap() as usize);
        let ids_r = row[1].as_array().unwrap();
        for (k, id) in ids.iter().enumerate() {
            let j = ids_r
                .iter()
                .position(|q| q.as_u64() == Some(*id as u64))
                .unwrap();
            let v = row[2][j].as_f64().unwrap() as f32;
            assert!((weights[k] - v).abs() <= 4e-5 + 4e-6 * v.abs());
        }
    }
    for row in g["layers"].as_array().unwrap() {
        let i = row[0].as_u64().unwrap() as usize;
        for (n, j) in [
            ("attention.output", 1),
            ("ffn.output", 2),
            ("layer.streams", 3),
        ] {
            check_bf(&audit.vectors[&(i, n.into())], &row[j], n);
        }
    }
    p.ctx.synchronize().unwrap();
    drop(p);
    assert_eq!(native::handle_census().0, 0);
    assert_eq!(native::double_free_attempts(), 0);
    assert!(native::cleanup_errors().is_empty());
    assert_eq!(native::handler_messages(), 0);
    assert_eq!(deq_bits,0x3d60,"reviewed reference currently uses a single final BF16 round; preserve this observation on mismatch");
}
