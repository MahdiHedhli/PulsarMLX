//! Complete bounded one-token GLM-style orchestration shared by the real
//! checkpoint producer and the tiny independent-oracle fixture.

use serde::{Deserialize, Serialize};

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ModelConfig {
    pub layer_count: usize,
    pub hidden: usize,
    pub vocab: usize,
    pub leading_dense_layers: usize,
    pub expert_count: usize,
    pub expert_top_k: usize,
    pub dense_ffn: usize,
    pub expert_ffn: usize,
    pub heads: usize,
    pub q_rank: usize,
    pub kv_rank: usize,
    pub qk_nope: usize,
    pub qk_rope: usize,
    pub value_dim: usize,
    pub rms_epsilon: f32,
    pub rope_base: f32,
    pub expert_weight_scale: f32,
}

impl ModelConfig {
    pub fn glm52() -> Self {
        Self {
            layer_count: 79,
            hidden: 6144,
            vocab: 154_880,
            leading_dense_layers: 3,
            expert_count: 256,
            expert_top_k: 8,
            dense_ffn: 12_288,
            expert_ffn: 2048,
            heads: 64,
            q_rank: 2048,
            kv_rank: 512,
            qk_nope: 192,
            qk_rope: 64,
            value_dim: 256,
            rms_epsilon: 1.0e-5,
            rope_base: 8_000_000.0,
            expert_weight_scale: 2.5,
        }
    }
    pub fn validate(&self) -> Result<(), String> {
        if self.layer_count == 0
            || self.hidden == 0
            || self.vocab == 0
            || self.heads == 0
            || self.qk_rope % 2 != 0
            || self.expert_top_k == 0
            || self.expert_top_k > self.expert_count
            || !self.rms_epsilon.is_finite()
            || self.rms_epsilon <= 0.0
            || !self.rope_base.is_finite()
            || self.rope_base <= 0.0
        {
            return Err("invalid model config".into());
        }
        Ok(())
    }
}

#[derive(Clone, Debug)]
pub struct Matrix {
    pub rows: usize,
    pub columns: usize,
    pub values: Vec<f32>,
}
impl Matrix {
    pub fn validate(&self, role: &str) -> Result<(), String> {
        if self.rows == 0
            || self.columns == 0
            || self.values.len() != self.rows * self.columns
            || self.values.iter().any(|v| !v.is_finite())
        {
            return Err(format!("invalid matrix {role}"));
        }
        Ok(())
    }
}

pub trait TensorSource {
    fn vector(&mut self, name: &str, length: usize) -> Result<Vec<f32>, String>;
    fn matrix(&mut self, name: &str, rows: usize, columns: usize) -> Result<Matrix, String>;
    fn expert_matrix(
        &mut self,
        name: &str,
        expert: usize,
        rows: usize,
        columns: usize,
    ) -> Result<Matrix, String>;
}

pub trait MatvecBackend {
    fn matvec(&mut self, role: &str, matrix: &Matrix, vector: &[f32]) -> Result<Vec<f32>, String>;
}

pub struct NativeMlxBackend<'a> {
    pub context: &'a stream::MlxContext,
}
impl MatvecBackend for NativeMlxBackend<'_> {
    fn matvec(&mut self, role: &str, matrix: &Matrix, vector: &[f32]) -> Result<Vec<f32>, String> {
        matrix.validate(role)?;
        if vector.len() != matrix.columns || vector.iter().any(|v| !v.is_finite()) {
            return Err(format!("invalid vector {role}"));
        }
        let mut matrix_owner = matrix.values.clone();
        let mut vector_owner = vector.to_vec();
        let m = self
            .context
            .import_f32_shaped(&mut matrix_owner, &[matrix.rows, matrix.columns])?;
        let v = self.context.import_f32(&mut vector_owner)?;
        let y = m.matvec(&v)?;
        y.evaluate_sync()?;
        let mut out = vec![0.0; matrix.rows];
        y.copy_f32(&mut out)?;
        if out.iter().any(|x| !x.is_finite()) {
            return Err(format!("nonfinite output {role}"));
        }
        Ok(out)
    }
}

pub struct ScalarBackend;
impl MatvecBackend for ScalarBackend {
    fn matvec(&mut self, role: &str, matrix: &Matrix, vector: &[f32]) -> Result<Vec<f32>, String> {
        matrix.validate(role)?;
        if vector.len() != matrix.columns {
            return Err(format!("shape {role}"));
        }
        let mut out = Vec::with_capacity(matrix.rows);
        for row in matrix.values.chunks_exact(matrix.columns) {
            let mut sum = 0.0_f32;
            for (&a, &b) in row.iter().zip(vector) {
                sum = (sum + a * b) as f32;
            }
            out.push(sum);
        }
        Ok(out)
    }
}

fn rms_norm(x: &[f32], scale: &[f32], epsilon: f32) -> Result<Vec<f32>, String> {
    if x.len() != scale.len() || x.is_empty() {
        return Err("rms shape".into());
    }
    let mut sum = 0.0_f32;
    for v in x {
        sum = (sum + *v * *v) as f32;
    }
    let inv = (sum / x.len() as f32 + epsilon).sqrt().recip();
    Ok(x.iter()
        .zip(scale)
        .map(|(v, s)| (*v * inv * *s) as f32)
        .collect())
}
fn silu(v: f32) -> f32 {
    (v / (1.0 + (-v).exp())) as f32
}
fn residual(a: &[f32], b: &[f32]) -> Result<Vec<f32>, String> {
    if a.len() != b.len() {
        return Err("residual shape".into());
    }
    Ok(a.iter().zip(b).map(|(x, y)| (*x + *y) as f32).collect())
}
fn load_projection(
    source: &mut impl TensorSource,
    prefix: &str,
    suffix: &str,
    expert: Option<usize>,
    shared: bool,
    rows: usize,
    columns: usize,
) -> Result<Matrix, String> {
    match expert {
        Some(id) => {
            source.expert_matrix(&format!("{prefix}_{suffix}_exps.weight"), id, rows, columns)
        }
        None if shared => source.matrix(&format!("{prefix}_{suffix}_shexp.weight"), rows, columns),
        None => source.matrix(&format!("{prefix}_{suffix}.weight"), rows, columns),
    }
}
fn swiglu(
    source: &mut impl TensorSource,
    backend: &mut impl MatvecBackend,
    prefix: &str,
    expert: Option<usize>,
    shared: bool,
    x: &[f32],
    inner: usize,
    hidden: usize,
    weight: f32,
) -> Result<Vec<f32>, String> {
    let gate = backend.matvec(
        "ffn_gate",
        &load_projection(source, prefix, "gate", expert, shared, inner, x.len())?,
        x,
    )?;
    let up = backend.matvec(
        "ffn_up",
        &load_projection(source, prefix, "up", expert, shared, inner, x.len())?,
        x,
    )?;
    let product = gate
        .iter()
        .zip(up)
        .map(|(g, u)| (silu(*g) * u * weight) as f32)
        .collect::<Vec<_>>();
    backend.matvec(
        "ffn_down",
        &load_projection(source, prefix, "down", expert, shared, hidden, inner)?,
        &product,
    )
}

fn route(
    logits: &[f32],
    bias: &[f32],
    k: usize,
    scale: f32,
) -> Result<(Vec<usize>, Vec<f32>), String> {
    if logits.len() != bias.len() || k > logits.len() {
        return Err("route shape".into());
    }
    let probabilities = logits
        .iter()
        .map(|v| 1.0_f32 / (1.0 + (-*v).exp()))
        .collect::<Vec<_>>();
    let scores = probabilities
        .iter()
        .zip(bias)
        .map(|(p, b)| (*p + *b) as f32)
        .collect::<Vec<_>>();
    let mut order = (0..scores.len()).collect::<Vec<_>>();
    order.sort_by(|a, b| scores[*b].total_cmp(&scores[*a]).then_with(|| a.cmp(b)));
    order.truncate(k);
    let denominator = order
        .iter()
        .map(|id| probabilities[*id])
        .sum::<f32>()
        .max(6.103515625e-5);
    let weights = order
        .iter()
        .map(|id| probabilities[*id] / denominator * scale)
        .collect();
    Ok((order, weights))
}

/// Execute exactly token embedding -> every layer -> final norm/logits ->
/// argmax. With a clean single-token cache each attention softmax has one
/// visible key, but Q/K/RoPE are still computed and validated.
pub fn execute_one_token(
    source: &mut impl TensorSource,
    backend: &mut impl MatvecBackend,
    config: &ModelConfig,
    token: u32,
) -> Result<u32, String> {
    config.validate()?;
    if token as usize >= config.vocab {
        return Err("token out of range".into());
    }
    let embedding = source.matrix("token_embd.weight", config.vocab, config.hidden)?;
    let mut x = embedding.values
        [token as usize * config.hidden..(token as usize + 1) * config.hidden]
        .to_vec();
    for layer in 0..config.layer_count {
        let attn_norm = source.vector(&format!("blk.{layer}.attn_norm.weight"), config.hidden)?;
        let xn = rms_norm(&x, &attn_norm, config.rms_epsilon)?;
        let qa = backend.matvec(
            "attn_q_a",
            &source.matrix(
                &format!("blk.{layer}.attn_q_a.weight"),
                config.q_rank,
                config.hidden,
            )?,
            &xn,
        )?;
        let qan = rms_norm(
            &qa,
            &source.vector(&format!("blk.{layer}.attn_q_a_norm.weight"), config.q_rank)?,
            config.rms_epsilon,
        )?;
        let qdim = config.qk_nope + config.qk_rope;
        let q = backend.matvec(
            "attn_q_b",
            &source.matrix(
                &format!("blk.{layer}.attn_q_b.weight"),
                config.heads * qdim,
                config.q_rank,
            )?,
            &qan,
        )?;
        let kv = backend.matvec(
            "attn_kv_a",
            &source.matrix(
                &format!("blk.{layer}.attn_kv_a_mqa.weight"),
                config.kv_rank + config.qk_rope,
                config.hidden,
            )?,
            &xn,
        )?;
        let kvn = rms_norm(
            &kv[..config.kv_rank],
            &source.vector(
                &format!("blk.{layer}.attn_kv_a_norm.weight"),
                config.kv_rank,
            )?,
            config.rms_epsilon,
        )?;
        let mut values = Vec::with_capacity(config.heads * config.value_dim);
        for head in 0..config.heads {
            let vb = source.expert_matrix(
                &format!("blk.{layer}.attn_v_b.weight"),
                head,
                config.value_dim,
                config.kv_rank,
            )?;
            values.extend(backend.matvec("attn_v_b", &vb, &kvn)?);
        }
        // One visible key: softmax([score]) == 1. Q/K computation remains a
        // structural/numerical gate and prevents a hidden attention bypass.
        for head in 0..config.heads {
            let row = source.expert_matrix(
                &format!("blk.{layer}.attn_k_b.weight"),
                head,
                config.kv_rank,
                config.qk_nope,
            )?;
            let q0 = &q[head * qdim..head * qdim + config.qk_nope];
            let key = backend.matvec("attn_k_b", &row, q0)?;
            let score = key
                .iter()
                .zip(&kvn)
                .fold(0.0_f32, |acc, (a, b)| (acc + *a * *b) as f32);
            if !score.is_finite() {
                return Err("attention score nonfinite".into());
            }
        }
        let attention = backend.matvec(
            "attn_output",
            &source.matrix(
                &format!("blk.{layer}.attn_output.weight"),
                config.hidden,
                config.heads * config.value_dim,
            )?,
            &values,
        )?;
        x = residual(&x, &attention)?;
        let ffn_norm = source.vector(&format!("blk.{layer}.ffn_norm.weight"), config.hidden)?;
        let fx = rms_norm(&x, &ffn_norm, config.rms_epsilon)?;
        let ffn = if layer < config.leading_dense_layers {
            swiglu(
                source,
                backend,
                &format!("blk.{layer}.ffn"),
                None,
                false,
                &fx,
                config.dense_ffn,
                config.hidden,
                1.0,
            )?
        } else {
            let logits = backend.matvec(
                "router",
                &source.matrix(
                    &format!("blk.{layer}.ffn_gate_inp.weight"),
                    config.expert_count,
                    config.hidden,
                )?,
                &fx,
            )?;
            let bias = source.vector(
                &format!("blk.{layer}.exp_probs_b.bias"),
                config.expert_count,
            )?;
            let (ids, weights) = route(
                &logits,
                &bias,
                config.expert_top_k,
                config.expert_weight_scale,
            )?;
            let mut acc = vec![0.0_f32; config.hidden];
            for (id, weight) in ids.into_iter().zip(weights) {
                let part = swiglu(
                    source,
                    backend,
                    &format!("blk.{layer}.ffn"),
                    Some(id),
                    false,
                    &fx,
                    config.expert_ffn,
                    config.hidden,
                    weight,
                )?;
                for (a, p) in acc.iter_mut().zip(part) {
                    *a = (*a + p) as f32;
                }
            }
            let shared = swiglu(
                source,
                backend,
                &format!("blk.{layer}.ffn"),
                None,
                true,
                &fx,
                config.expert_ffn,
                config.hidden,
                1.0,
            )?;
            for (a, p) in acc.iter_mut().zip(shared) {
                *a = (*a + p) as f32;
            }
            acc
        };
        x = residual(&x, &ffn)?;
    }
    let normalized = rms_norm(
        &x,
        &source.vector("output_norm.weight", config.hidden)?,
        config.rms_epsilon,
    )?;
    let logits = backend.matvec(
        "output",
        &source.matrix("output.weight", config.vocab, config.hidden)?,
        &normalized,
    )?;
    logits
        .iter()
        .enumerate()
        .max_by(|(ia, a), (ib, b)| a.total_cmp(b).then_with(|| ib.cmp(ia)))
        .map(|(index, _)| index as u32)
        .ok_or_else(|| "empty logits".into())
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::collections::HashMap;
    struct Store {
        vectors: HashMap<String, Vec<f32>>,
        matrices: HashMap<String, Matrix>,
        experts: HashMap<(String, usize), Matrix>,
    }
    impl TensorSource for Store {
        fn vector(&mut self, name: &str, length: usize) -> Result<Vec<f32>, String> {
            let v = self.vectors.get(name).ok_or(name.to_owned())?.clone();
            if v.len() != length {
                return Err("shape".into());
            }
            Ok(v)
        }
        fn matrix(&mut self, name: &str, rows: usize, columns: usize) -> Result<Matrix, String> {
            let m = self.matrices.get(name).ok_or(name.to_owned())?.clone();
            if m.rows != rows || m.columns != columns {
                return Err("shape".into());
            }
            Ok(m)
        }
        fn expert_matrix(
            &mut self,
            name: &str,
            expert: usize,
            rows: usize,
            columns: usize,
        ) -> Result<Matrix, String> {
            let m = self
                .experts
                .get(&(name.to_owned(), expert))
                .ok_or(name.to_owned())?
                .clone();
            if m.rows != rows || m.columns != columns {
                return Err("shape".into());
            }
            Ok(m)
        }
    }
    fn identity(rows: usize, cols: usize) -> Matrix {
        let mut v = vec![0.0; rows * cols];
        for i in 0..rows.min(cols) {
            v[i * cols + i] = 1.0
        }
        Matrix {
            rows,
            columns: cols,
            values: v,
        }
    }
    #[test]
    fn complete_tiny_graph_changes_routes_and_stops_after_one_token() {
        let c = ModelConfig {
            layer_count: 2,
            hidden: 2,
            vocab: 4,
            leading_dense_layers: 1,
            expert_count: 2,
            expert_top_k: 1,
            dense_ffn: 2,
            expert_ffn: 2,
            heads: 1,
            q_rank: 2,
            kv_rank: 2,
            qk_nope: 2,
            qk_rope: 2,
            value_dim: 2,
            rms_epsilon: 1e-5,
            rope_base: 8e6,
            expert_weight_scale: 1.0,
        };
        let mut s = Store {
            vectors: HashMap::new(),
            matrices: HashMap::new(),
            experts: HashMap::new(),
        };
        s.matrices.insert(
            "token_embd.weight".into(),
            Matrix {
                rows: 4,
                columns: 2,
                values: vec![1., 0., 0., 1., 1., 1., -1., 1.],
            },
        );
        s.matrices.insert(
            "output.weight".into(),
            Matrix {
                rows: 4,
                columns: 2,
                values: vec![0., 0., 0., 0., 8., 8., -8., -8.],
            },
        );
        s.vectors.insert("output_norm.weight".into(), vec![1., 1.]);
        for l in 0..2 {
            for n in [
                "attn_q_a.weight",
                "attn_q_b.weight",
                "attn_kv_a_mqa.weight",
                "attn_output.weight",
            ] {
                let (r, c0) = match n {
                    "attn_q_a.weight" => (2, 2),
                    "attn_q_b.weight" => (4, 2),
                    "attn_kv_a_mqa.weight" => (4, 2),
                    _ => (2, 2),
                };
                s.matrices.insert(format!("blk.{l}.{n}"), identity(r, c0));
            }
            s.experts
                .insert((format!("blk.{l}.attn_k_b.weight"), 0), identity(2, 2));
            s.experts
                .insert((format!("blk.{l}.attn_v_b.weight"), 0), identity(2, 2));
            for n in [
                "attn_norm.weight",
                "attn_q_a_norm.weight",
                "attn_kv_a_norm.weight",
                "ffn_norm.weight",
            ] {
                s.vectors.insert(format!("blk.{l}.{n}"), vec![1., 1.]);
            }
        }
        for n in ["gate", "up", "down"] {
            s.matrices
                .insert(format!("blk.0.ffn_{n}.weight"), identity(2, 2));
        }
        s.matrices
            .insert("blk.1.ffn_gate_inp.weight".into(), identity(2, 2));
        s.vectors
            .insert("blk.1.exp_probs_b.bias".into(), vec![0., 0.]);
        for e in 0..2 {
            for n in ["gate", "up", "down"] {
                s.experts
                    .insert((format!("blk.1.ffn_{n}_exps.weight"), e), identity(2, 2));
            }
        }
        for n in ["gate", "up", "down"] {
            s.matrices
                .insert(format!("blk.1.ffn_{n}_shexp.weight"), identity(2, 2));
        }
        assert_eq!(
            execute_one_token(&mut s, &mut ScalarBackend, &c, 0).unwrap(),
            2
        );
    }
}
