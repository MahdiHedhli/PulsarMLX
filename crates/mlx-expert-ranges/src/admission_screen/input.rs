use crate::residency::{parse_hash, Hash256};
use serde::{
    de::{value::MapAccessDeserializer, Error, MapAccess, SeqAccess, Visitor},
    Deserialize, Deserializer, Serialize,
};
use sha2::{Digest, Sha256};
use std::{fmt, marker::PhantomData, mem::size_of};

use super::{checked, Ledger, Result, LIMIT, MAX_CALLS, MAX_OCCURRENCES};

/// A JSON sequence with a hard element limit, checked before storing another item.
struct List<T, const N: usize>(Vec<T>);
impl<'de, T: Deserialize<'de>, const N: usize> Deserialize<'de> for List<T, N> {
    fn deserialize<D: Deserializer<'de>>(d: D) -> std::result::Result<Self, D::Error> {
        struct Items<T, const N: usize>(PhantomData<T>);
        impl<'de, T: Deserialize<'de>, const N: usize> Visitor<'de> for Items<T, N> {
            type Value = List<T, N>;
            fn expecting(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
                write!(f, "at most {N} entries")
            }
            fn visit_seq<A: SeqAccess<'de>>(
                self,
                mut seq: A,
            ) -> std::result::Result<Self::Value, A::Error> {
                let mut items = Vec::new();
                while items.len() < N {
                    match seq.next_element()? {
                        Some(x) => items.push(x),
                        None => return Ok(List(items)),
                    }
                }
                if seq.next_element::<serde::de::IgnoredAny>()?.is_some() {
                    return Err(A::Error::custom("sequence bound"));
                }
                Ok(List(items))
            }
        }
        d.deserialize_seq(Items::<T, N>(PhantomData))
    }
}
struct Calls(Vec<Box<[u16]>>);
impl<'de> Deserialize<'de> for Calls {
    fn deserialize<D: Deserializer<'de>>(d: D) -> std::result::Result<Self, D::Error> {
        struct CallVisitor;
        impl<'de> Visitor<'de> for CallVisitor {
            type Value = Calls;
            fn expecting(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
                f.write_str("bounded calls")
            }
            fn visit_seq<A: SeqAccess<'de>>(
                self,
                mut a: A,
            ) -> std::result::Result<Calls, A::Error> {
                let mut calls = Vec::new();
                let mut total = 0;
                while calls.len() < MAX_CALLS {
                    let Some(List(ids)) = a.next_element::<List<u16, 64>>()? else {
                        return Ok(Calls(calls));
                    };
                    total += ids.len();
                    if ids.is_empty() || total > MAX_OCCURRENCES {
                        return Err(A::Error::custom("total occurrence limit or empty call"));
                    }
                    calls.push(ids.into_boxed_slice());
                }
                if a.next_element::<serde::de::IgnoredAny>()?.is_some() {
                    return Err(A::Error::custom("call count"));
                }
                Ok(Calls(calls))
            }
        }
        d.deserialize_seq(CallVisitor)
    }
}
// Serde struct derives also accept positional arrays. This wire schema requires named objects.
fn object<'de, D: Deserializer<'de>, T: Deserialize<'de>>(
    d: D,
) -> std::result::Result<T, D::Error> {
    struct Map<T>(PhantomData<T>);
    impl<'de, T: Deserialize<'de>> Visitor<'de> for Map<T> {
        type Value = T;
        fn expecting(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
            f.write_str("named JSON object")
        }
        fn visit_map<A: MapAccess<'de>>(self, a: A) -> std::result::Result<T, A::Error> {
            T::deserialize(MapAccessDeserializer::new(a))
        }
    }
    d.deserialize_map(Map(PhantomData))
}
#[derive(Deserialize)]
struct Hash(#[serde(deserialize_with = "hash")] Hash256);
fn hash<'de, D: Deserializer<'de>>(d: D) -> std::result::Result<Hash256, D::Error> {
    parse_hash(<&str>::deserialize(d)?).map_err(D::Error::custom)
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Class {
    content: Hash,
    metadata: Hash,
    layer: u32,
    d: u32,
    h: u32,
    group: u32,
    bits: [u32; 3],
    components: [u64; 9],
    persistent_slots: u8,
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Entry {
    expert: u32,
    domain: Hash,
    binding: Hash,
}
#[derive(Deserialize)]
struct NamedEntry(#[serde(deserialize_with = "object")] Entry);
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Wire<'a> {
    schema: &'a str,
    provenance_kind: &'a str,
    #[serde(deserialize_with = "object")]
    class: Class,
    catalog: List<NamedEntry, 4096>,
    calls: Calls,
}
#[derive(Clone, Debug, Serialize)]
pub struct Source {
    pub content: String,
    pub metadata: String,
    pub layer: u32,
    pub d: u32,
    pub h: u32,
    pub group: u32,
    pub bits: [u32; 3],
    pub components: [u64; 9],
    pub persistent_slots: u8,
}
impl Class {
    fn validate(&self) -> Result<u64> {
        if self.persistent_slots != 2
            || self.group != 64
            || self.d == 0
            || self.h == 0
            || self.d % 64 != 0
            || self.h % 64 != 0
        {
            return Err("unsupported tuple geometry".into());
        }
        let mut total = 0;
        for i in 0..3 {
            let (n, k) = if i == 2 {
                (self.d, self.h)
            } else {
                (self.h, self.d)
            };
            let bits = self.bits[i];
            if ![4, 8].contains(&bits) {
                return Err("unsupported packed recipe".into());
            }
            let elems = u64::from(n) * u64::from(k);
            let weight = elems
                .checked_mul(bits as u64)
                .ok_or("packed geometry overflow")?
                / 8;
            let metadata = elems / 64 * 2;
            if self.components[i * 3..i * 3 + 3] != [weight, metadata, metadata] {
                return Err("component geometry/length".into());
            }
            total = checked(total, checked(weight, 2 * metadata)?)?;
        }
        if total > crate::MAX_SELECTED_BYTES {
            return Err("tuple exceeds selected-byte limit".into());
        }
        Ok(total)
    }
    fn domain(&self) -> Hash256 {
        let mut h = Sha256::new();
        h.update(b"admission-screen.domain/1\0");
        h.update(self.content.0);
        h.update(self.metadata.0);
        for n in [self.layer, self.d, self.h, self.group]
            .into_iter()
            .chain(self.bits)
        {
            h.update(n.to_le_bytes())
        }
        for n in self.components {
            h.update(n.to_le_bytes())
        }
        h.finalize().into()
    }
}
pub(super) fn hex(h: &Hash256) -> String {
    format!("{:x}", sha2::digest::Output::<Sha256>::from(*h))
}
/// Complete, immutable synthetic input. Catalog ordinals are routed expert indices.
pub struct Trace {
    pub(super) source: Source,
    pub(super) domain: Hash256,
    pub(super) input: Hash256,
    pub(super) bindings: Box<[Hash256]>,
    pub(super) calls: Box<[Box<[u16]>]>,
    pub(super) count: usize,
    pub(super) tuple: u64,
}
impl Trace {
    pub fn parse(raw: &[u8]) -> Result<Self> {
        if raw.len() > LIMIT {
            return Err("input exceeds 8 MiB".into());
        }
        let mut parser = serde_json::Deserializer::from_slice(raw);
        let wire: Wire = object(&mut parser).map_err(|e| e.to_string())?;
        parser.end().map_err(|e| e.to_string())?;
        if wire.schema != "pulsarmlx.admission-screen.input/1"
            || wire.provenance_kind != "synthetic"
        {
            return Err("unsupported schema or provenance".into());
        }
        let class = wire.class;
        let tuple = class.validate()?;
        let domain = class.domain();
        let entries = wire.catalog.0;
        if entries.is_empty() || wire.calls.0.is_empty() {
            return Err("empty catalog or calls".into());
        }
        let mut unique = std::collections::BTreeSet::new();
        let mut bindings = Vec::with_capacity(entries.len());
        for (index, NamedEntry(e)) in entries.into_iter().enumerate() {
            if e.expert as usize != index || e.domain.0 != domain || !unique.insert(e.binding.0) {
                return Err("catalog domain, expert or binding".into());
            }
            bindings.push(e.binding.0);
        }
        let calls = wire.calls.0;
        let mut count = 0;
        for ids in &calls {
            count += ids.len();
            if ids.is_empty()
                || count > MAX_OCCURRENCES
                || ids.iter().any(|i| *i as usize >= bindings.len())
            {
                return Err("unknown expert or occurrence bound".into());
            }
        }
        let source = Source {
            content: hex(&class.content.0),
            metadata: hex(&class.metadata.0),
            layer: class.layer,
            d: class.d,
            h: class.h,
            group: class.group,
            bits: class.bits,
            components: class.components,
            persistent_slots: 2,
        };
        Ok(Self {
            source,
            domain,
            input: Sha256::digest(raw).into(),
            bindings: bindings.into_boxed_slice(),
            calls: calls.into_boxed_slice(),
            count,
            tuple,
        })
    }
    pub fn ledger(&self) -> Result<Ledger> {
        Ledger::for_trace(self)
    }
    pub fn calls(&self) -> impl Iterator<Item = &[u16]> {
        self.calls.iter().map(|c| c.as_ref())
    }
    pub(super) fn input_bytes(&self) -> u64 {
        (size_of::<Self>()
            + self.source.content.capacity()
            + self.source.metadata.capacity()
            + std::mem::size_of_val(self.calls.as_ref())
            + self.count * size_of::<u16>()) as u64
    }
}
