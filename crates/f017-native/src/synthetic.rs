//! Public-safe tiny full-model fixture source. It contains only committed
//! synthetic numbers and has no path, file, environment, or checkpoint API.

use crate::model::{Matrix, ModelConfig, TensorSource};
use serde::Deserialize;
use std::collections::BTreeMap;

#[derive(Clone, Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct MatrixFixture {
    pub rows: usize,
    pub columns: usize,
    pub values: Vec<f32>,
}
#[derive(Clone, Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ExpertFixture {
    pub name: String,
    pub expert: usize,
    pub matrix: MatrixFixture,
}
#[derive(Clone, Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct SyntheticFixture {
    pub schema: String,
    pub seed: u64,
    pub config: ModelConfig,
    pub prompt_token: u32,
    pub expected_token: u32,
    pub vectors: BTreeMap<String, Vec<f32>>,
    pub matrices: BTreeMap<String, MatrixFixture>,
    pub expert_matrices: Vec<ExpertFixture>,
}

pub struct SyntheticSource {
    vectors: BTreeMap<String, Vec<f32>>,
    matrices: BTreeMap<String, Matrix>,
    experts: BTreeMap<(String, usize), Matrix>,
}
impl SyntheticSource {
    pub fn from_fixture(f: SyntheticFixture) -> Result<(Self, ModelConfig, u32, u32), String> {
        let accepted = (f.schema == "pulsarmlx.f017.native-tiny-full-model-fixture/1.0.0"
            && f.seed == 17017)
            || (f.schema == "pulsarmlx.f017.native-full-graph-differential-fixture/1.0.0"
                && (17018..=17023).contains(&f.seed));
        if !accepted {
            return Err("synthetic fixture authority".into());
        }
        f.config.validate()?;
        let matrices = f
            .matrices
            .into_iter()
            .map(|(n, m)| {
                (
                    n,
                    Matrix {
                        rows: m.rows,
                        columns: m.columns,
                        values: m.values,
                    },
                )
            })
            .collect();
        let experts = f
            .expert_matrices
            .into_iter()
            .map(|e| {
                (
                    (e.name, e.expert),
                    Matrix {
                        rows: e.matrix.rows,
                        columns: e.matrix.columns,
                        values: e.matrix.values,
                    },
                )
            })
            .collect();
        Ok((
            Self {
                vectors: f.vectors,
                matrices,
                experts,
            },
            f.config,
            f.prompt_token,
            f.expected_token,
        ))
    }
}
impl TensorSource for SyntheticSource {
    fn vector(&mut self, name: &str, length: usize) -> Result<Vec<f32>, String> {
        let v = self
            .vectors
            .get(name)
            .ok_or_else(|| format!("missing {name}"))?
            .clone();
        if v.len() != length {
            return Err(format!("shape {name}"));
        }
        Ok(v)
    }
    fn matrix(&mut self, name: &str, rows: usize, columns: usize) -> Result<Matrix, String> {
        let m = self
            .matrices
            .get(name)
            .ok_or_else(|| format!("missing {name}"))?
            .clone();
        if m.rows != rows || m.columns != columns {
            return Err(format!("shape {name}"));
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
            .ok_or_else(|| format!("missing {name}[{expert}]"))?
            .clone();
        if m.rows != rows || m.columns != columns {
            return Err(format!("shape {name}"));
        }
        Ok(m)
    }
}
