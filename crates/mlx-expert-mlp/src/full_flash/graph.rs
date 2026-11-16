//! Fixed GLM-5.3-Flash mixed-4/8 text-only graph. One real input ID, cold position zero.
//! No reference, expected ID/logits, route override, persistent decoder, or sampling input.
//! Backend tensors use f32 buffers to carry represented bf16/F32 checkpoint values on the host.
//! Packed matmuls, the router projection and original argpartition are provider operations.
pub type R<T> = Result<T, String>;
pub trait Provider {
    /// Real affine module (without ".weight"). group selects expert/head on axis 0.
    /// Packed projection input and result are represented BF16. Unpacked .mlp.gate is F32.
    fn linear(&mut self, path: &str, group: Option<usize>, x: &[f32]) -> R<Vec<f32>>;
    /// A small, nonpacked raw parameter, validated against the complete immutable schema.
    fn tensor(&mut self, path: &str) -> R<Vec<f32>>;
    /// One dequantized row of the untied embedding module, returned as represented BF16.
    fn embedding(&mut self, path: &str, token: usize) -> R<Vec<f32>>;
    /// MLX argpartition(-corrected, k-1)[:k] in native order (not sorted afterward).
    fn partition(&mut self, corrected: &[f32], k: usize) -> R<Vec<usize>>;
}
pub trait Witness {
    /// The witness sink can hash raw F32 lanes or capture them under its own fixed budget.
    /// Errors, including cancellation, propagate before the next operation.
    fn vector(&mut self, layer: usize, name: &str, x: &[f32]) -> R<()>;
    fn route(&mut self, layer: usize, ids: &[usize], weights: &[f32], cutoff_gap: f32) -> R<()>;
}
#[derive(Copy, Clone)]
struct Shape {
    d: usize,
    vocab: usize,
    layers: usize,
    dense_layers: usize,
    dense_ff: usize,
    expert_ff: usize,
    experts: usize,
    select: usize,
    kda_h: usize,
    kda_d: usize,
    sparse_h: usize,
    sparse_d: usize,
    qrank: usize,
    latent: usize,
    index_h: usize,
    index_d: usize,
}
const FLASH: Shape = Shape {
    d: 4096,
    vocab: 154880,
    layers: 45,
    dense_layers: 3,
    dense_ff: 12288,
    expert_ff: 2048,
    experts: 288,
    select: 8,
    kda_h: 64,
    kda_d: 128,
    sparse_h: 64,
    sparse_d: 256,
    qrank: 1536,
    latent: 512,
    index_h: 32,
    index_d: 128,
};
const EPS: f32 = 1e-5;
const HC_EPS: f32 = 1e-6;
fn finite(x: &[f32], name: &str) -> R<()> {
    if x.is_empty() || x.iter().any(|v| !v.is_finite()) {
        Err(format!("empty or nonfinite: {name}"))
    } else {
        Ok(())
    }
}
fn exact(v: Vec<f32>, n: usize, path: &str) -> R<Vec<f32>> {
    if v.len() != n {
        return Err(format!("shape {path}: {} != {n}", v.len()));
    }
    finite(&v, path)?;
    Ok(v)
}
fn bf(x: f32) -> f32 {
    // All admitted values must be finite. Preserve exceptional values for rejection.
    if !x.is_finite() {
        return x;
    }
    let b = x.to_bits();
    f32::from_bits((b.wrapping_add(0x7fff + ((b >> 16) & 1))) & 0xffff_0000)
}
fn bvec(v: Vec<f32>, path: &str) -> R<Vec<f32>> {
    if v.iter().any(|x| bf(*x).to_bits() != x.to_bits()) {
        Err(format!("output is not represented bf16: {path}"))
    } else {
        Ok(v)
    }
}
fn param(p: &mut impl Provider, base: &str, key: &str, n: usize) -> R<Vec<f32>> {
    let path = format!("{base}.{key}");
    exact(p.tensor(&path)?, n, &path)
}
fn proj(
    p: &mut impl Provider,
    base: &str,
    key: &str,
    id: Option<usize>,
    x: &[f32],
    n: usize,
) -> R<Vec<f32>> {
    let path = format!("{base}.{key}");
    finite(x, &path)?;
    let v = exact(p.linear(&path, id, x)?, n, &path)?;
    if key == "gate" && base.ends_with(".mlp") {
        Ok(v)
    } else {
        bvec(v, &path)
    }
}
fn sig(x: f32) -> f32 {
    1.0 / (1.0 + (-x).exp())
}
fn silu_b(x: f32) -> f32 {
    bf(x * bf(sig(x)))
}
/// Partition accumulation into lanes to avoid a 16384-term single-precision serial chain.
/// Distinct reduction order from the independent reference is intentional.
fn dot(x: &[f32], y: &[f32]) -> f32 {
    debug_assert_eq!(x.len(), y.len());
    let mut a = [0.0f32; 32];
    for (i, (&x, &y)) in x.iter().zip(y).enumerate() {
        a[i % 32] = x.mul_add(y, a[i % 32]);
    }
    for step in [16, 8, 4, 2, 1] {
        for i in 0..step {
            a[i] += a[i + step];
        }
    }
    a[0]
}
fn rms(x: &[f32], wt: &[f32]) -> Vec<f32> {
    let inv = (dot(x, x) / (x.len() as f32) + EPS).sqrt().recip();
    x.iter().zip(wt).map(|(a, b)| bf((a * inv) * b)).collect()
}
fn norm(p: &mut impl Provider, base: &str, key: &str, x: &[f32]) -> R<Vec<f32>> {
    let w = param(p, base, key, x.len())?;
    let y = rms(x, &w);
    finite(&y, key)?;
    Ok(y)
}
fn normalized_l2(x: &mut [f32], scale: f32) {
    let inv = (dot(x, x) + 1e-6).sqrt().recip();
    for a in x {
        *a = bf((*a * inv) * scale)
    }
}
fn layer_norm(x: &[f32], w: &[f32], bias: &[f32]) -> Vec<f32> {
    let mean = x.iter().sum::<f32>() / x.len() as f32;
    let dev: Vec<_> = x.iter().map(|v| v - mean).collect();
    let inv = (dot(&dev, &dev) / x.len() as f32 + 1e-6).sqrt().recip();
    (0..x.len())
        .map(|i| bf((dev[i] * inv).mul_add(w[i], bias[i])))
        .collect()
}
struct Mix {
    pre: [f32; 4],
    post: [f32; 4],
    comb: [[f32; 4]; 4],
    collapsed: Vec<f32>,
}
fn hyper(p: &mut impl Provider, base: &str, x: &[f32], d: usize) -> R<Mix> {
    // Metal form: upstream-hyper-connection.txt:70-103 has epsilon inside the
    // initial softmax denominator as well as after the division, unlike CPU ops.
    let f = param(p, base, "fn", 24 * 4 * d)?;
    let b = param(p, base, "base", 24)?;
    let scale = param(p, base, "scale", 3)?;
    let inv = (dot(x, x) / x.len() as f32 + EPS).sqrt().recip();
    let z: Vec<_> = x.iter().map(|v| v * inv).collect();
    let m: Vec<_> = f.chunks_exact(4 * d).map(|r| dot(&z, r)).collect();
    let mut pre = [0.0f32; 4];
    let mut post = pre;
    let mut comb = [[0.0f32; 4]; 4];
    for i in 0..4 {
        pre[i] = sig(m[i].mul_add(scale[0], b[i])) + HC_EPS;
        post[i] = 2. * sig(m[4 + i].mul_add(scale[1], b[4 + i]));
        let row = &mut comb[i];
        for (j, v) in row.iter_mut().enumerate() {
            let k = 8 + 4 * i + j;
            *v = m[k].mul_add(scale[2], b[k]);
        }
        let max = row.iter().copied().fold(f32::NEG_INFINITY, f32::max);
        row.iter_mut().for_each(|a| *a = (*a - max).exp());
        let inv = (row.iter().sum::<f32>() + HC_EPS).recip();
        row.iter_mut().for_each(|a| *a = (*a).mul_add(inv, HC_EPS));
    }
    for it in 0..20 {
        if it > 0 {
            for row in &mut comb {
                let inv = (row.iter().sum::<f32>() + HC_EPS).recip();
                for el in row {
                    *el *= inv;
                }
            }
        }
        for j in 0..4 {
            let inv = (comb.iter().map(|r| r[j]).sum::<f32>() + HC_EPS).recip();
            for r in &mut comb {
                r[j] *= inv;
            }
        }
    }
    let mut collapsed = vec![0.; d];
    for i in 0..d {
        collapsed[i] = bf(pre[0].mul_add(
            x[i],
            pre[1].mul_add(
                x[d + i],
                pre[2].mul_add(x[2 * d + i], pre[3] * x[3 * d + i]),
            ),
        ));
    }
    finite(&collapsed, "mHC collapsed")?;
    Ok(Mix {
        pre,
        post,
        comb,
        collapsed,
    })
}
fn witness_mix(w: &mut impl Witness, i: usize, n: &str, m: &Mix) -> R<()> {
    let mut c = Vec::with_capacity(24);
    c.extend_from_slice(&m.pre);
    c.extend_from_slice(&m.post);
    for row in m.comb {
        c.extend_from_slice(&row);
    }
    w.vector(i, n, &c)
}
fn append_cold(row: &[f32], width: usize, keep: usize) -> R<(Vec<f32>, usize)> {
    if width == 0 || keep == 0 || row.len() != width {
        return Err("bad cold cache append".into());
    }
    let mut image = vec![0.; (keep - 1) * width];
    let before = image.len() / width;
    image.extend_from_slice(row);
    let advances = image.len() / width - before;
    Ok((image, advances))
}
fn expand(x: &[f32], branch: &[f32], m: &Mix) -> R<Vec<f32>> {
    let d = branch.len();
    let mut y = vec![0.; 4 * d];
    for j in 0..4 {
        for i in 0..d {
            let r = (0..4).map(|h| m.comb[h][j] * x[h * d + i]).sum::<f32>();
            y[j * d + i] = bf(m.post[j].mul_add(branch[i], r));
        }
    }
    finite(&y, "mHC residual")?;
    Ok(y)
}
fn mlp(p: &mut impl Provider, base: &str, id: Option<usize>, x: &[f32], ff: usize) -> R<Vec<f32>> {
    let mut g = proj(p, base, "gate_proj", id, x, ff)?;
    let u = proj(p, base, "up_proj", id, x, ff)?;
    for (gg, uu) in g.iter_mut().zip(u) {
        *gg = bf(silu_b(gg.min(10.0)) * uu.clamp(-10., 10.));
    }
    proj(p, base, "down_proj", id, &g, x.len())
}
fn selected(scores: &[f32], corrected: &[f32], ids: &[usize], k: usize) -> R<(Vec<f32>, f32)> {
    let n = scores.len();
    if n != corrected.len() || k == 0 || k >= n || ids.len() != k {
        return Err("route geometry".into());
    }
    finite(scores, "router sigmoid")?;
    finite(corrected, "router corrected")?;
    let mut picked = vec![false; n];
    for &id in ids {
        if id >= n || picked[id] {
            return Err("invalid or duplicate route".into());
        }
        picked[id] = true;
    }
    let mut min = f32::INFINITY;
    let mut max = f32::NEG_INFINITY;
    for i in 0..n {
        if picked[i] {
            min = min.min(corrected[i]);
        } else {
            max = max.max(corrected[i]);
        }
    }
    // Cutoff ties have no unique membership and cannot receive a qualified reference.
    if min <= max {
        return Err(format!(
            "ambiguous or wrong route membership: {min} <= {max}"
        ));
    }
    let den = ids.iter().map(|i| scores[*i]).sum::<f32>();
    if !den.is_finite() || den <= 0. {
        return Err("zero/nonfinite route denominator".into());
    }
    Ok((
        ids.iter().map(|i| scores[*i] / den * 2.5).collect(),
        min - max,
    ))
}
fn moe(
    p: &mut impl Provider,
    w: &mut impl Witness,
    i: usize,
    b: &str,
    x: &[f32],
    s: Shape,
) -> R<Vec<f32>> {
    let lg = proj(p, b, "gate", None, x, s.experts)?;
    let bias = param(p, b, "gate.e_score_correction_bias", s.experts)?;
    let scores: Vec<_> = lg.into_iter().map(sig).collect();
    let c: Vec<_> = scores.iter().zip(bias).map(|(a, b)| a + b).collect();
    finite(&c, "corrected scores")?;
    let ids = p.partition(&c, s.select)?;
    let (weights, gap) = selected(&scores, &c, &ids, s.select)?;
    w.vector(i, "moe.corrected", &c)?;
    w.route(i, &ids, &weights, gap)?;
    let mut sum = vec![0.; s.d];
    for (&id, &coeff) in ids.iter().zip(&weights) {
        let y = mlp(p, &format!("{b}.switch_mlp"), Some(id), x, s.expert_ff)?;
        for (v, y) in sum.iter_mut().zip(y) {
            *v += coeff * y;
        }
    }
    sum.iter_mut().for_each(|v| *v = bf(*v));
    w.vector(i, "moe.routed", &sum)?;
    let shared = mlp(p, &format!("{b}.shared_experts"), None, x, s.expert_ff)?;
    w.vector(i, "moe.shared", &shared)?;
    for (z, a) in sum.iter_mut().zip(shared) {
        *z = bf(*z + a);
    }
    Ok(sum)
}
/// Decay the entire [value,key] state before updating it. A separate test calls
/// this same primitive with nonzero initial state because decay is invisible at cold zero.
fn delta_step(
    q: &[f32],
    k: &[f32],
    v: &[f32],
    decay: &[f32],
    beta: f32,
    state: &mut [f32],
) -> Vec<f32> {
    let dk = q.len();
    let mut y = vec![0.; v.len()];
    for (j, row) in state.chunks_exact_mut(dk).enumerate() {
        for (t, g) in row.iter_mut().zip(decay) {
            *t *= *g;
        }
        let delta = (v[j] - dot(row, k)) * beta;
        for (a, b) in row.iter_mut().zip(k) {
            *a = b.mul_add(delta, *a);
        }
        y[j] = bf(dot(row, q));
    }
    y
}
fn kda(
    p: &mut impl Provider,
    w: &mut impl Witness,
    i: usize,
    b: &str,
    x: &[f32],
    s: Shape,
) -> R<Vec<f32>> {
    let hd = s.kda_d;
    let qn = s.kda_h * hd;
    let mut mixed = Vec::with_capacity(3 * qn);
    for key in ["q_proj", "k_proj", "v_proj"] {
        mixed.extend(proj(p, b, key, None, x, qn)?);
    }
    let fa = proj(p, b, "forget_gate.f_a_proj", None, x, hd)?;
    let a = proj(p, b, "forget_gate.f_b_proj", None, &fa, qn)?;
    let gb = proj(p, b, "g_a_proj", None, x, hd)?;
    let gate = proj(p, b, "g_b_proj", None, &gb, qn)?;
    let beta = proj(p, b, "b_proj", None, x, s.kda_h)?;
    let decay_log = param(p, b, "forget_gate.A_log", s.kda_h)?;
    let dt = param(p, b, "forget_gate.dt_bias", qn)?;
    let cw = param(p, b, "conv1d.weight", 3 * qn * 4)?;
    // Three empty convolution slots before appending mixed; retention keeps two
    // empty slots and the current pre-convolution q,k,v. Original tensor [3Q,4,1].
    let (conv, offset) = append_cold(&mixed, 3 * qn, 3)?;
    w.vector(i, "kda.conv_state", &conv)?;
    let conv_out: Vec<_> = mixed
        .iter()
        .enumerate()
        .map(|(j, v)| silu_b(bf(v * cw[j * 4 + 3])))
        .collect();
    let mut q = conv_out[..qn].to_vec();
    let mut k = conv_out[qn..2 * qn].to_vec();
    let v = &conv_out[2 * qn..];
    let wo = param(p, b, "o_norm.weight", hd)?;
    let mut state = vec![0.; s.kda_h * hd * hd];
    let mut out = Vec::with_capacity(qn);
    let mut used_beta = Vec::with_capacity(s.kda_h);
    let mut used_decay = Vec::with_capacity(qn);
    for h in 0..s.kda_h {
        let r = h * hd..(h + 1) * hd;
        normalized_l2(&mut q[r.clone()], (hd as f32).sqrt().recip());
        normalized_l2(&mut k[r.clone()], 1.);
        let strength = decay_log[h].exp();
        if !strength.is_finite() {
            return Err("nonfinite KDA gate strength".into());
        }
        let decay: Vec<_> = r
            .clone()
            .map(|j| (-5. * sig(strength * (a[j] + dt[j]))).exp())
            .collect();
        finite(&decay, "KDA decay")?;
        used_decay.extend_from_slice(&decay);
        let beta_h = bf(sig(beta[h]));
        used_beta.push(beta_h);
        let act = delta_step(
            &q[r.clone()],
            &k[r.clone()],
            &v[r.clone()],
            &decay,
            beta_h,
            &mut state[h * hd * hd..(h + 1) * hd * hd],
        );
        let inv = (dot(&act, &act) / hd as f32 + EPS).sqrt().recip();
        for (j, a) in act.into_iter().enumerate() {
            out.push(bf((a * inv * wo[j]) * sig(gate[h * hd + j])));
        }
    }
    finite(&state, "KDA state")?;
    w.vector(i, "kda.recurrent_state", &state)?;
    let mut qkvb = Vec::with_capacity(3 * qn + s.kda_h);
    for data in [q.as_slice(), k.as_slice(), v, &used_beta] {
        qkvb.extend_from_slice(data);
    }
    w.vector(i, "kda.qkv_beta", &qkvb)?;
    w.vector(i, "kda.decay", &used_decay)?;
    w.vector(i, "state.offset", &[offset as f32])?;
    proj(p, b, "o_proj", None, &out, s.d)
}
fn mla(
    p: &mut impl Provider,
    w: &mut impl Witness,
    i: usize,
    b: &str,
    x: &[f32],
    s: Shape,
) -> R<Vec<f32>> {
    let qa = proj(p, b, "q_a_proj", None, x, s.qrank)?;
    let qr = norm(p, b, "q_a_layernorm.weight", &qa)?;
    let allq = proj(p, b, "q_b_proj", None, &qr, s.sparse_h * s.sparse_d)?;
    let kv = proj(p, b, "kv_a_proj_with_mqa", None, x, s.latent)?;
    let kv = norm(p, b, "kv_a_layernorm.weight", &kv)?;
    // Latent K and V are the same finite vector; record one canonical image.
    let (kv, lp) = append_cold(&kv, s.latent, 1)?;
    w.vector(i, "mla.latent", &kv)?;
    let ix = format!("{b}.indexer");
    let _iq = proj(p, &ix, "wq_b", None, &qr, s.index_h * s.index_d)?;
    let kw = proj(p, &ix, "wk", None, x, s.index_d)?;
    let nw = param(p, &ix, "k_norm.weight", s.index_d)?;
    let nb = param(p, &ix, "k_norm.bias", s.index_d)?;
    let mut indexer = layer_norm(&kw, &nw, &nb);
    let cg = param(p, &ix, "index_kpool_compress_gate", s.index_d * s.d)?;
    indexer.extend(cg.chunks_exact(s.d).map(|row| bf(dot(row, x))));
    indexer.push(1.);
    finite(&indexer, "indexer cache")?;
    let (indexer, ip) = append_cold(&indexer, 2 * s.index_d + 1, 1)?;
    if lp != ip {
        return Err("latent/indexer cache position".into());
    }
    w.vector(i, "mla.indexer", &indexer)?;
    w.vector(i, "state.offset", &[ip as f32])?;
    // T=1 <= index_topk(2048) after the indexer cache append: canonical source bypasses pools.
    // L=1 uses embed_q(q), q·latent / sqrt(d), latent values, per-head unembed.
    // For a finite singleton score, stable softmax = exp(score-score)/exp(score-score) = 1.
    let mut out = Vec::with_capacity(s.sparse_h * s.sparse_d);
    for (h, q) in allq.chunks_exact(s.sparse_d).enumerate() {
        let qh = proj(p, b, "embed_q", Some(h), q, s.latent)?;
        let logit = dot(&qh, &kv) / (s.sparse_d as f32).sqrt();
        if !logit.is_finite() {
            return Err("nonfinite singleton MLA score".into());
        }
        out.extend(proj(p, b, "unembed_out", Some(h), &kv, s.sparse_d)?);
    }
    proj(p, b, "o_proj", None, &out, s.d)
}
pub fn forward<P: Provider, W: Witness>(
    p: &mut P,
    w: &mut W,
    token: usize,
) -> R<(Vec<f32>, usize)> {
    cold(p, w, token, FLASH)
}
fn cold(
    p: &mut impl Provider,
    w: &mut impl Witness,
    token: usize,
    s: Shape,
) -> R<(Vec<f32>, usize)> {
    if token >= s.vocab {
        return Err("input outside text vocabulary".into());
    }
    let emb = bvec(
        exact(
            p.embedding("language_model.model.embed_tokens", token)?,
            s.d,
            "embedding",
        )?,
        "embedding",
    )?;
    let mut x = emb.repeat(4);
    w.vector(0, "input.embedding", &emb)?;
    for i in 0..s.layers {
        let root = format!("language_model.model.layers.{i}");
        let att = format!("{root}.self_attn");
        let ffn = format!("{root}.mlp");
        let a = hyper(p, &format!("{root}.attn_hc"), &x, s.d)?;
        witness_mix(w, i, "mhc.attn", &a)?;
        let y = norm(p, &root, "input_layernorm.weight", &a.collapsed)?;
        let branch = if i % 4 == 3 {
            mla(p, w, i, &att, &y, s)?
        } else {
            kda(p, w, i, &att, &y, s)?
        };
        w.vector(i, "attention.output", &branch)?;
        x = expand(&x, &branch, &a)?;
        let m = hyper(p, &format!("{root}.ffn_hc"), &x, s.d)?;
        witness_mix(w, i, "mhc.ffn", &m)?;
        let y = norm(p, &root, "post_attention_layernorm.weight", &m.collapsed)?;
        let branch = if i < s.dense_layers {
            mlp(p, &ffn, None, &y, s.dense_ff)?
        } else {
            moe(p, w, i, &ffn, &y, s)?
        };
        w.vector(i, "ffn.output", &branch)?;
        x = expand(&x, &branch, &m)?;
        w.vector(i, "layer.streams", &x)?;
    }
    let pool: Vec<_> = (0..s.d)
        .map(|j| bf((0..4).map(|h| x[h * s.d + j]).sum::<f32>() * 0.25))
        .collect();
    let n = norm(p, "language_model.model", "norm.weight", &pool)?;
    w.vector(s.layers, "final.norm", &n)?;
    let logits = proj(p, "language_model", "lm_head", None, &n, s.vocab)?;
    let winner = greedy(&logits)?;
    Ok((logits, winner))
}
fn greedy(logits: &[f32]) -> R<usize> {
    finite(logits, "full logits")?;
    // MLX argmax returns the first maximal index. Separate grader rejects reference ambiguity.
    let mut best = 0;
    for j in 1..logits.len() {
        if logits[j] > logits[best] {
            best = j;
        }
    }
    Ok(best)
}
#[cfg(test)]
mod tests {
    use super::*;
    use std::collections::BTreeMap;
    #[test]
    fn router_membership_is_corrected_weights_are_uncorrected() {
        let raw = [0.1, 0.8, 0.4, 0.2];
        let corrected = [0.95, 0.8, 0.4, 0.2];
        let (w, gap) = selected(&raw, &corrected, &[1, 0], 2).unwrap();
        assert!((w[0] - 2.5 * 0.8 / 0.9).abs() < 1e-5 && (w[1] - 2.5 * 0.1 / 0.9).abs() < 1e-5);
        assert!((gap - 0.4).abs() < 1e-6);
        assert!(selected(&raw, &corrected, &[0, 0], 2).is_err());
        assert!(selected(&raw, &corrected, &[1, 2], 2).is_err());
        assert!(selected(&raw, &[0.9, 0.8, 0.8, 0.1], &[0, 1], 2).is_err());
    }
    #[test]
    fn nonzero_prior_state_discriminates_forget_axis_and_value_major_order() {
        // q=[1,0], k=[0,1]; state [[4,8],[2,6]] times per-column [.5,.25].
        let mut a = [4., 8., 2., 6.];
        let y = delta_step(&[1., 0.], &[0., 1.], &[10., 20.], &[0.5, 0.25], 0.5, &mut a);
        assert_eq!(a, [2., 6., 1., 10.75]);
        assert_eq!(y, [2., 1.]);
        let mut cold = [0.; 4];
        let y = delta_step(&[1., 0.], &[1., 1.], &[2., 4.], &[0.3, 0.7], 0.5, &mut cold);
        assert_eq!(cold, [1., 1., 2., 2.]);
        assert_eq!(y, [1., 2.]);
    }
    #[test]
    fn residual_combination_uses_source_stream_rows() {
        let m = Mix {
            pre: [0.; 4],
            post: [0., 0., 0., 0.],
            comb: [
                [0., 1., 0., 0.],
                [0., 0., 1., 0.],
                [0., 0., 0., 1.],
                [1., 0., 0., 0.],
            ],
            collapsed: vec![],
        };
        assert_eq!(
            expand(&[1., 2., 3., 4.], &[9.], &m).unwrap(),
            [4., 1., 2., 3.]
        );
    }
    #[test]
    fn finite_argmax_preserves_token_index() {
        assert_eq!(greedy(&[-12., -5., -7., -5.]).unwrap(), 1);
        assert!(greedy(&[2., f32::NAN, 3.]).is_err());
        assert!(greedy(&[]).is_err());
        assert_eq!(bf(f32::from_bits(0x3f808000)), 1.0);
        assert_eq!(bf(f32::from_bits(0x3f818000)).to_bits(), 0x3f820000);
    }
    struct Clamp;
    impl Provider for Clamp {
        fn linear(&mut self, p: &str, _: Option<usize>, x: &[f32]) -> R<Vec<f32>> {
            match p {
                "test.gate_proj" => Ok(vec![30., -20., 0.]),
                "test.up_proj" => Ok(vec![30., -30., 5.]),
                "test.down_proj" => Ok(x.to_vec()),
                _ => Err(p.into()),
            }
        }
        fn partition(&mut self, _: &[f32], _: usize) -> R<Vec<usize>> {
            unreachable!()
        }
        fn tensor(&mut self, _: &str) -> R<Vec<f32>> {
            unreachable!()
        }
        fn embedding(&mut self, _: &str, _: usize) -> R<Vec<f32>> {
            unreachable!()
        }
    }
    #[test]
    fn saturated_up_and_gate_keep_negative_gate_unclamped() {
        let y = mlp(&mut Clamp, "test", None, &[1., 1., 1.], 3).unwrap();
        assert_eq!(y[0], 100.);
        assert!(y[1] > 3.0e-7 && y[1] < 5.0e-7);
        assert_eq!(y[2], 0.);
    }

    // A deliberately small 5-layer composition traverses dense KDA; routed MLA;
    // and routed KDA. Each projection depends on its actual input. Distinct rows
    // are used for different selected experts/heads; no preloaded route exists.
    const SMALL: Shape = Shape {
        d: 4,
        vocab: 7,
        layers: 5,
        dense_layers: 3,
        dense_ff: 6,
        expert_ff: 3,
        experts: 5,
        select: 2,
        kda_h: 2,
        kda_d: 2,
        sparse_h: 2,
        sparse_d: 3,
        qrank: 3,
        latent: 2,
        index_h: 2,
        index_d: 2,
    };
    #[derive(Default)]
    struct Tiny {
        bad: bool,
        loads: Vec<(String, Option<usize>)>,
    }
    impl Provider for Tiny {
        fn tensor(&mut self, p: &str) -> R<Vec<f32>> {
            let n = if p.ends_with(".fn") {
                24 * 4 * 4
            } else if p.ends_with(".base") {
                24
            } else if p.ends_with(".scale") {
                3
            } else if p.ends_with("norm.weight") {
                if p.contains(".self_attn.o_norm.")
                    || p.contains("kv_a_layernorm")
                    || p.contains("indexer.k_norm")
                {
                    2
                } else if p.contains("q_a_layernorm") {
                    3
                } else {
                    4
                }
            } else if p.ends_with("k_norm.bias") {
                2
            } else if p.ends_with("index_kpool_compress_gate") {
                8
            } else if p.ends_with("conv1d.weight") {
                3 * 4 * 4
            } else if p.ends_with("A_log") {
                2
            } else if p.ends_with("dt_bias") {
                4
            } else if p.ends_with("e_score_correction_bias") {
                return Ok(vec![0.01, 0.02, 0.03, 0.04, 0.05]);
            } else {
                return Err(p.into());
            };
            let a = (0..n)
                .map(|j| {
                    if p.ends_with("norm.weight") {
                        1.
                    } else if p.ends_with(".fn") {
                        (j as i32 % 9 - 4) as f32 * 0.015625
                    } else if p.ends_with(".base") {
                        (((j * 3) % 13) as i32 - 6) as f32 * 0.125
                    } else if p.ends_with(".scale") {
                        1.
                    } else if p.ends_with("conv1d.weight") {
                        if j % 4 == 3 {
                            1.
                        } else {
                            0.25
                        }
                    } else {
                        0.125
                    }
                })
                .collect();
            Ok(a)
        }
        fn embedding(&mut self, p: &str, token: usize) -> R<Vec<f32>> {
            assert_eq!(p, "language_model.model.embed_tokens");
            Ok(vec![0.25 + token as f32, -0.5, 0.125, 0.75])
        }
        fn linear(&mut self, p: &str, axis: Option<usize>, x: &[f32]) -> R<Vec<f32>> {
            self.loads.push((p.into(), axis));
            let key = p.rsplit('.').next().unwrap();
            if p.ends_with("mlp.gate") {
                return Ok((0..5)
                    .map(|i| x[i % 4] * (i as f32 - 2.0) * 0.3125)
                    .collect());
            }
            let n = match key {
                "lm_head" => {
                    if self.bad {
                        6
                    } else {
                        7
                    }
                }
                "q_proj" | "k_proj" | "v_proj" => 4,
                "f_a_proj" | "g_a_proj" | "b_proj" | "kv_a_proj_with_mqa" | "wk" | "embed_q" => 2,
                "f_b_proj" | "g_b_proj" | "o_proj" | "down_proj" | "wq_b" => 4,
                "q_a_proj" | "unembed_out" => 3,
                "q_b_proj" => 6,
                "gate_proj" | "up_proj" => {
                    if p.contains("switch_mlp") || p.contains("shared_experts") {
                        3
                    } else {
                        6
                    }
                }
                _ => return Err(p.into()),
            };
            Ok((0..n)
                .map(|j| bf(x[j % x.len()] * (1. + (axis.unwrap_or(0) + j % 3) as f32 / 8.)))
                .collect())
        }
        fn partition(&mut self, c: &[f32], k: usize) -> R<Vec<usize>> {
            let mut ids: Vec<_> = (0..c.len()).collect();
            ids.sort_by(|a, b| c[*b].total_cmp(&c[*a]));
            ids.truncate(k);
            ids.reverse();
            Ok(ids)
        }
    }
    #[derive(Default)]
    struct Audit {
        obs: BTreeMap<(usize, String), Vec<f32>>,
        routes: Vec<(usize, Vec<usize>)>,
        stop: bool,
    }
    impl Witness for Audit {
        fn vector(&mut self, i: usize, n: &str, x: &[f32]) -> R<()> {
            if self.stop && i == 1 {
                return Err("cancelled".into());
            }
            if self.obs.insert((i, n.into()), x.to_vec()).is_some() {
                return Err("duplicate boundary".into());
            }
            Ok(())
        }
        fn route(&mut self, i: usize, ids: &[usize], w: &[f32], gap: f32) -> R<()> {
            assert!((w.iter().sum::<f32>() - 2.5).abs() < 1e-5 && gap > 0.);
            self.routes.push((i, ids.to_vec()));
            Ok(())
        }
    }
    #[test]
    fn complete_tiny_cold_graph_has_all_states_routes_and_untied_logits() {
        let mut p = Tiny::default();
        let mut w = Audit::default();
        let (lg, id) = cold(&mut p, &mut w, 1, SMALL).unwrap();
        assert_eq!(lg.len(), 7);
        assert_eq!(id, greedy(&lg).unwrap());
        assert_eq!(w.routes.len(), 2);
        assert_eq!(w.routes[0].0, 3);
        assert_eq!(w.routes[1].0, 4);
        for i in 0..5 {
            let v = |name: &str| &w.obs[&(i, name.into())];
            assert_eq!(v("state.offset"), &[1.]);
            assert_eq!(v("layer.streams").len(), 16);
            if i == 3 {
                assert_eq!(v("mla.latent").len(), 2);
                let ix = v("mla.indexer");
                assert_eq!(ix.len(), 5);
                assert_eq!(ix[4], 1.);
            } else {
                let conv = v("kda.conv_state");
                assert_eq!(conv.len(), 36);
                assert!(conv[..24].iter().all(|x| *x == 0.));
                assert!(conv[24..].iter().any(|x| *x != 0.));
                let state = v("kda.recurrent_state");
                assert_eq!(state.len(), 8);
                assert!(state.iter().any(|x| *x != 0.));
            }
            if i >= 3 {
                let a = v("moe.routed");
                let b = v("moe.shared");
                let z = v("ffn.output");
                assert!(b.iter().any(|x| *x != 0.));
                for j in 0..4 {
                    assert_eq!(z[j], bf(a[j] + b[j]));
                }
            }
        }
        for (i, ids) in &w.routes {
            let key = format!("language_model.model.layers.{i}.mlp.switch_mlp.down_proj");
            let opened: Vec<_> = p
                .loads
                .iter()
                .filter(|(n, _)| *n == key)
                .map(|(_, x)| x.unwrap())
                .collect();
            assert_eq!(&opened, ids);
        }
        let mut p = Tiny {
            bad: true,
            ..Default::default()
        };
        assert!(cold(&mut p, &mut Audit::default(), 1, SMALL)
            .unwrap_err()
            .contains("shape"));
        let mut p = Tiny::default();
        let mut w = Audit {
            stop: true,
            ..Default::default()
        };
        assert_eq!(cold(&mut p, &mut w, 1, SMALL), Err("cancelled".into()));
        assert!(!p.loads.iter().any(|(n, _)| n.ends_with(".lm_head")));
    }
}

#[cfg(test)]
#[test]
fn bf16_silu_rounds_sigmoid_before_multiplication() {
    assert_eq!(silu_b(0.06640625), 0.0341796875);
    assert_ne!(silu_b(0.06640625), bf(0.06640625 * sig(0.06640625)));
}

#[cfg(test)]
mod studio017_coefficient_controls {
    use super::*;

    struct Controlled;
    impl Provider for Controlled {
        fn tensor(&mut self, key: &str) -> R<Vec<f32>> {
            if key.ends_with(".fn") {
                return Ok(vec![0.; 96]);
            }
            if key.ends_with(".scale") {
                return Ok(vec![1.; 3]);
            }
            if key.ends_with(".base") {
                let mut a = vec![0.; 8];
                a.extend_from_slice(&[
                    0., -12., -12., -12., 0., 0., -12., -12., -12., 0., 0., -12., -12., -12., 0.,
                    0.,
                ]);
                return Ok(a);
            }
            Err(key.into())
        }
        fn linear(&mut self, _: &str, _: Option<usize>, _: &[f32]) -> R<Vec<f32>> {
            unreachable!()
        }
        fn embedding(&mut self, _: &str, _: usize) -> R<Vec<f32>> {
            unreachable!()
        }
        fn partition(&mut self, _: &[f32], _: usize) -> R<Vec<usize>> {
            unreachable!()
        }
    }
    #[test]
    fn twenty_sinkhorn_rounds_match_decimal20_not_decimal19() {
        let m = hyper(&mut Controlled, "tiny", &[1., 0., 0., 0.], 1).unwrap();
        // Independent scalar decimal(60) control in test_studio017_scientific.
        assert!((m.comb[2][1] - 0.10214507536130281_f32).abs() < 3e-7);
        assert!((m.comb[2][1] - 0.10693918866237061_f32).abs() > 0.004);
    }
    #[test]
    fn norm_weights_epsilons_and_cache_append() {
        let h = 1.0f32 / 512.;
        let z = 1.0f32 / 128.;
        let w = [1., 2., 3., 4.];
        let off = [0.5, 0.25, -0.25, 0.125];
        let r = rms(&[h, -h, h, -h], &w);
        let expected = [h, -2. * h, 3. * h, -4. * h].map(|a| bf(a / (h * h + 1e-5).sqrt()));
        assert_eq!(r, expected);
        let n = layer_norm(&[1., 1. + z, 1. - z, 1.], &w, &off);
        let want = [0., 2. * z, -3. * z, 0.]
            .iter()
            .zip(off)
            .map(|(v, b)| bf(v / (z * z * 0.5 + 1e-6).sqrt() + b))
            .collect::<Vec<_>>();
        assert_eq!(n, want);
        assert!(append_cold(&[], 3, 1).is_err());
        let (a, p) = append_cold(&[-1., 0., 1.], 3, 3).unwrap();
        assert!(a[..6].iter().all(|x| x.to_bits() == 0));
        assert_eq!(p, 1);
        assert_eq!(&a[6..], &[-1., 0., 1.]);
    }
}

#[cfg(all(test, pulsar_native_mlx))]
#[path = "native_controls.rs"]
mod native_controls;
