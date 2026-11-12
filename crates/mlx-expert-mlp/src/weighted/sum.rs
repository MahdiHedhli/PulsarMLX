use super::book::quarters;
use crate::resident_fixture::{ensure, Result};
use mlx_native_affine::{dtype::Dtype, fixture::HostTensor};

/// Accumulator starts at positive zero. A failed addition destroys the partial sum.
pub struct WeightedSum(Vec<u8>);
impl Default for WeightedSum {
    fn default() -> Self {
        Self(vec![0; 512])
    }
}
impl WeightedSum {
    pub fn add(mut self, weight: u32, output: &HostTensor) -> Result<Self> {
        quarters(weight)?;
        ensure(
            output.dtype == Dtype::F32 && output.shape == [1, 128] && output.bytes.len() == 512,
            "weighted vector descriptor",
        )?;
        for (destination, source) in self.0.chunks_exact_mut(4).zip(output.bytes.chunks_exact(4)) {
            let value = f32::from_le_bytes(source.try_into().unwrap());
            let previous = f32::from_le_bytes((*destination).try_into().unwrap());
            ensure(value.is_finite(), "non-finite weighted input")?;
            let product = f32::from_bits(weight) * value;
            let sum = previous + product;
            ensure(
                product.is_finite() && sum.is_finite(),
                "non-finite weighted arithmetic",
            )?;
            destination.copy_from_slice(&sum.to_le_bytes());
        }
        Ok(self)
    }
    pub fn into_bytes(self) -> Vec<u8> {
        self.0
    }
}
