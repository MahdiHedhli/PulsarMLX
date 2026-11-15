//! Owned by API-08. The client dialects; API-09 adds the Anthropic dialect in M2.
//!
//! [`openai`] is the OpenAI Chat Completions dialect on the inference driver of API-07
//! (`crate::inference`): request preparation, the streamed chunks and the non-stream
//! collector. Nothing here is qualified beyond synthetic backends.

pub mod openai;
