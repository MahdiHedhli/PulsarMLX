//! Instantiable real bounded-P1 math producer. Preflight and one-shot
//! authority stay in the wrapper; this object owns the complete token graph.

use crate::loader::SecureCheckpoint;
use crate::model::{execute_one_token, ModelConfig, NativeMlxBackend};
use stream::{BoundedP1Math, MlxContext};

pub struct FullNativeP1Math {
    pub checkpoint: SecureCheckpoint,
    pub config: ModelConfig,
    invocations: u32,
}
impl FullNativeP1Math {
    pub fn new(checkpoint: SecureCheckpoint, config: ModelConfig) -> Self {
        Self {
            checkpoint,
            config,
            invocations: 0,
        }
    }
}
impl BoundedP1Math for FullNativeP1Math {
    fn backend_id(&self) -> &'static str {
        "NATIVE_RUST_MLX_FULL_GLM52_ONE_TOKEN"
    }
    fn execute_one(&mut self, context: &MlxContext, prompt_token: u32) -> Result<u32, String> {
        if self.invocations != 0 {
            return Err("bounded math invoked more than once".into());
        }
        self.invocations = 1;
        execute_one_token(
            &mut self.checkpoint,
            &mut NativeMlxBackend { context },
            &self.config,
            prompt_token,
        )
    }
}
