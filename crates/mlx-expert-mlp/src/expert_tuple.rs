//! Host-only immutable tuple; inherited expert selection remains authoritative.
use mlx_native_affine::compose::{compose, SelectedPlane, Source};

pub const ROLES: [&str; 3] = [
    "synthetic.experts.gate",
    "synthetic.experts.up",
    "synthetic.experts.down",
];

pub struct ExpertTuple<'a> {
    planes: [SelectedPlane<'a>; 3],
}

impl<'a> ExpertTuple<'a> {
    pub fn select(
        source: &'a Source,
        expert: u64,
        d: u64,
        h: u64,
        mixed: bool,
    ) -> Result<Self, String> {
        let gate = compose(source, ROLES[0], &[expert])
            .map_err(|e| format!("MLP-R-TUPLE: inherited gate selection {e}"))?;
        let up = compose(source, ROLES[1], &[expert])
            .map_err(|e| format!("MLP-R-TUPLE: inherited up selection {e}"))?;
        let down = compose(source, ROLES[2], &[expert])
            .map_err(|e| format!("MLP-R-TUPLE: inherited down selection {e}"))?;
        Self::bind(source, [gate, up, down], expert, d, h, mixed)
    }

    pub fn bind(
        source: &'a Source,
        planes: [SelectedPlane<'a>; 3],
        expert: u64,
        d: u64,
        h: u64,
        mixed: bool,
    ) -> Result<Self, String> {
        if expert >= 3 || ![64, 128].contains(&d) || ![64, 128].contains(&h) {
            return Err("MLP-R-TUPLE: population geometry/index".into());
        }
        for (i, p) in planes.iter().enumerate() {
            let id = p.identity();
            let bits = if mixed && i != 1 { 8 } else { 4 };
            let [n, k] = if i == 2 { [d, h] } else { [h, d] };
            let meta = source
                .checkpoint()
                .catalog()
                .get(&format!("{}.weight", ROLES[i]))
                .ok_or("MLP-R-TUPLE: missing role weight")?;
            let checks = [
                (
                    "source_identity",
                    id.source_identity == source.backing().source_identity(),
                ),
                (
                    "checkpoint",
                    id.checkpoint == source.checkpoint().root_name(),
                ),
                ("module", id.module == ROLES[i]),
                ("index_path", id.index_path == [expert]),
                ("expert_geometry", meta.shape == [3, n, k * bits / 32]),
                ("logical_shape", id.logical_shape == [n, k]),
                ("packed_shape", id.packed_shape == [n, k * bits / 32]),
                ("metadata_shape", id.metadata_shape == [n, k / 64]),
                ("bits", id.bits == bits as u32),
                ("group_size", id.group_size == 64),
                ("metadata_dtype", id.metadata_dtype == "BF16"),
                ("transpose", id.transpose),
                (
                    "resolved_from",
                    id.resolved_from
                        == if mixed && i != 1 {
                            "override"
                        } else {
                            "default"
                        },
                ),
            ];
            for (field, ok) in checks {
                if !ok {
                    return Err(format!("MLP-R-TUPLE: {field} for role {}", ROLES[i]));
                }
            }
            for suffix in ["scales", "biases"] {
                if source
                    .checkpoint()
                    .catalog()
                    .get(&format!("{}.{}", ROLES[i], suffix))
                    .ok_or("MLP-R-TUPLE: missing metadata")?
                    .shape
                    != [3, n, k / 64]
                {
                    return Err("MLP-R-TUPLE: metadata expert geometry".into());
                }
            }
        }
        Ok(Self { planes })
    }
    pub fn planes(&self) -> &[SelectedPlane<'a>; 3] {
        &self.planes
    }
}
