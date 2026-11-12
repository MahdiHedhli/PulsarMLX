use crate::resident_fixture::{ensure, hex, Population, Result, INPUT_SHA, VIEW_SHA};
use backend::{step::StepRequest, CheckpointIdentity};
use mlx_expert_ranges::residency::{parse_hash, Hash256};
use mlx_native_affine::fixture::sha256_hex;

pub const MAX_PLANS: usize = 5;
pub const MAX_TERMS: usize = 12;
pub const ARITHMETIC: &str = "binary32-rne-mul-then-add-v1";
pub type Term = (u32, u32); // expert index, binary32 weight bits
const Q: u32 = 0x3e800000;
const H: u32 = 0x3f000000;
const T: u32 = 0x3f400000;
const ONE: u32 = 0x3f800000;
pub const FIXED: [&[Term]; 5] = [
    &[(0, ONE)],
    &[(0, T), (1, Q)],
    &[(0, H), (1, Q), (2, Q)],
    &[(0, Q), (1, H), (0, Q)],
    &[(0, H), (2, 0), (1, H)],
];

pub(super) fn quarters(bits: u32) -> Result<u32> {
    match bits {
        0 => Ok(0),
        Q => Ok(1),
        H => Ok(2),
        T => Ok(3),
        ONE => Ok(4),
        _ => Err("unsupported weight bits".into()),
    }
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Identity {
    pub profile: &'static str,
    pub manifest: Hash256,
    pub content: Hash256,
    pub input: Hash256,
    /// M, D, H, E, group size, layer.
    pub geometry: [u32; 6],
    pub bits: [u32; 3],
}
impl Identity {
    pub fn for_population(p: &Population) -> Result<Self> {
        let hash = |s| parse_hash(s).map_err(|e| e.to_string());
        Ok(Self {
            profile: p.profile,
            manifest: hash(VIEW_SHA)?,
            content: p.content,
            input: hash(INPUT_SHA)?,
            geometry: [1, 128, 64, 3, 64, 0],
            bits: p.bits,
        })
    }
}
struct Plan {
    terms: Box<[Term]>,
    digest: String,
}

/// Owns its route. No caller-owned vector or mutable provider participates in replay.
pub struct RouteBook {
    identity: Identity,
    digest: String,
    checkpoint: CheckpointIdentity,
    plans: Box<[Plan]>,
    encoded_len: usize,
}
fn field(out: &mut Vec<u8>, value: &[u8]) {
    out.extend_from_slice(&(value.len() as u32).to_le_bytes());
    out.extend_from_slice(value);
}
impl RouteBook {
    pub fn fixed(profile: &str) -> Result<Self> {
        let p = Population::load(profile)?;
        Self::new(Identity::for_population(&p)?, &FIXED)
    }
    pub fn new(identity: Identity, routes: &[&[Term]]) -> Result<Self> {
        ensure(matches!(identity.profile, "default" | "mixed"), "recipe")?;
        ensure((1..=MAX_PLANS).contains(&routes.len()), "plan count")?;
        let mut count = 0;
        for &terms in routes {
            ensure((1..=3).contains(&terms.len()), "plan length")?;
            count += terms.len();
            let mut sum = 0;
            for &(expert, bits) in terms {
                ensure(expert < 3, "expert index")?;
                sum += quarters(bits)?;
            }
            ensure(sum == 4 && count <= MAX_TERMS, "quarter sum or book length")?;
        }
        let mut encoding = b"weighted-book-v1\0".to_vec();
        field(&mut encoding, identity.profile.as_bytes());
        field(&mut encoding, ARITHMETIC.as_bytes());
        for hash in [&identity.manifest, &identity.content, &identity.input] {
            encoding.extend_from_slice(hash);
        }
        for number in identity
            .geometry
            .into_iter()
            .chain(identity.bits)
            .chain([routes.len() as u32])
        {
            encoding.extend_from_slice(&number.to_le_bytes());
        }
        let mut plans = Vec::with_capacity(routes.len());
        for &terms in routes {
            let mut encoded = b"weighted-plan-v1\0".to_vec();
            encoded.extend_from_slice(&(terms.len() as u32).to_le_bytes());
            for &(expert, weight) in terms {
                encoded.extend_from_slice(&expert.to_le_bytes());
                encoded.extend_from_slice(&weight.to_le_bytes());
            }
            field(&mut encoding, &encoded);
            plans.push(Plan {
                terms: terms.into(),
                digest: sha256_hex(&encoded),
            });
        }
        let digest = sha256_hex(&encoding);
        let checkpoint = CheckpointIdentity::try_new(
            hex(&identity.content),
            format!("weighted-route-v1.{digest}"),
        )
        .map_err(|e| e.to_string())?;
        Ok(Self {
            identity,
            digest,
            checkpoint,
            plans: plans.into_boxed_slice(),
            encoded_len: encoding.capacity(),
        })
    }
    pub fn digest(&self) -> &str {
        &self.digest
    }
    pub fn checkpoint(&self) -> &CheckpointIdentity {
        &self.checkpoint
    }
    pub fn terms(&self, pos: u64) -> Result<&[Term]> {
        Ok(&self.plan(pos)?.terms)
    }
    pub fn plan_digest(&self, pos: u64) -> Result<&str> {
        Ok(&self.plan(pos)?.digest)
    }
    fn plan(&self, pos: u64) -> Result<&Plan> {
        usize::try_from(pos)
            .ok()
            .and_then(|n| self.plans.get(n))
            .ok_or_else(|| "weighted position".into())
    }
    pub fn request(&self, pos: u64) -> Result<StepRequest> {
        let mut req = crate::resident::request(&self.checkpoint, pos);
        req.id = format!(
            "weighted-v1.{}.{pos}.{}",
            self.digest,
            self.plan_digest(pos)?
        );
        req.output_bytes = 512;
        Ok(req)
    }
    pub(super) fn check(&self, pop: &Population) -> Result<()> {
        ensure(
            self.identity == Identity::for_population(pop)?,
            "route population, input or geometry mismatch",
        )
    }
    pub(super) fn capacity(&self) -> usize {
        size_of::<Self>()
            + self.encoded_len
            + self.digest.capacity()
            + self.checkpoint.immutable_revision.capacity()
            + self.checkpoint.checkpoint_set_sha256.capacity()
            + size_of_val(&*self.plans)
            + self
                .plans
                .iter()
                .map(|p| size_of_val(&*p.terms) + p.digest.capacity())
                .sum::<usize>()
    }
}
