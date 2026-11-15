//! Golden transcripts of the OpenAI Chat Completions dialect within the M1 subset (plain
//! content): the raw bytes of streamed answers (the `Date` value normalized) and the JSON
//! bodies of collected ones, with the scripted engine and the ENG-02 doubles. The `model`
//! field is `pulsar-console-synthetic` (deviation PLAN-2) in every one.
//!
//! The transcripts of reasoning, streamed and whole tool calls and JSON mode on a template
//! with thinking need the output parsers of M2 (PRM-06, PRM-09, PRM-16); the chunk writer's
//! renderings of those events are pinned by the unit tests of
//! `console_http::dialect::openai::chunks`. The prompt token counts here are those of the
//! M1 synthetic prompt (lead decision LD45), not parity figures.

#[path = "api08_kit.rs"]
mod kit;

use std::sync::Arc;

use console_engine::fake::doubles::{
    ClockedEngine, DyingEngine, ErrEngine, HeldEngine, LpEngine, PacedEngine,
};
use console_engine::fake::DEFAULT_MAX_CONTEXT;
use console_testkit::engines::{script, shared};
use console_testkit::raw::{self, RawRequest};
use kit::*;

fn engine(text: &str) -> Arc<dyn console_core::engine::EngineFactory> {
    match script(text, DEFAULT_MAX_CONTEXT).build() {
        Ok(f) => shared(f),
        Err(e) => panic!("{e}"),
    }
}

#[tokio::test]
async fn a_plain_stream_is_the_golden_transcript() {
    let s = server(engine("Hi!")).await;
    let r = post(&s, &chat("\"stream\": true")).await;
    let want = format!(
        "{}{}{}{}{DONE}",
        sse_head(),
        first_frame(),
        content_frames("Hi!"),
        // Three letters and the end-of-turn token.
        final_frame("stop", HI_PROMPT_TOKENS, 4, 0)
    );
    assert_eq!(normalized(&r), want);
    // A literal check of one whole transcript, independent of the kit's builders.
    let literal = "data: {\"id\": \"chatcmpl-0123456789abcdef01234567\", \"object\": \"chat.completion.chunk\", \"created\": 1700000000, \"model\": \"pulsar-console-synthetic\", \"choices\": [{\"index\": 0, \"delta\": {\"role\": \"assistant\", \"content\": \"\"}, \"finish_reason\": null}]}\n\n\
data: {\"id\": \"chatcmpl-0123456789abcdef01234567\", \"object\": \"chat.completion.chunk\", \"created\": 1700000000, \"model\": \"pulsar-console-synthetic\", \"choices\": [{\"index\": 0, \"delta\": {\"content\": \"H\"}, \"finish_reason\": null}]}\n\n\
data: {\"id\": \"chatcmpl-0123456789abcdef01234567\", \"object\": \"chat.completion.chunk\", \"created\": 1700000000, \"model\": \"pulsar-console-synthetic\", \"choices\": [{\"index\": 0, \"delta\": {\"content\": \"i\"}, \"finish_reason\": null}]}\n\n\
data: {\"id\": \"chatcmpl-0123456789abcdef01234567\", \"object\": \"chat.completion.chunk\", \"created\": 1700000000, \"model\": \"pulsar-console-synthetic\", \"choices\": [{\"index\": 0, \"delta\": {\"content\": \"!\"}, \"finish_reason\": null}]}\n\n\
data: {\"id\": \"chatcmpl-0123456789abcdef01234567\", \"object\": \"chat.completion.chunk\", \"created\": 1700000000, \"model\": \"pulsar-console-synthetic\", \"choices\": [{\"index\": 0, \"delta\": {}, \"finish_reason\": \"stop\"}], \"usage\": {\"prompt_tokens\": 73, \"completion_tokens\": 4, \"total_tokens\": 77, \"prompt_tokens_details\": {\"cached_tokens\": 0}}}\n\n\
data: [DONE]\n\n";
    assert_eq!(String::from_utf8_lossy(&r.body), literal);
}

#[tokio::test]
async fn the_collected_answer_is_the_golden_body() {
    let s = server(engine("Hi!")).await;
    let r = post(&s, &chat("")).await;
    let body = "{\"id\": \"chatcmpl-0123456789abcdef01234567\", \"object\": \"chat.completion\", \"created\": 1700000000, \"model\": \"pulsar-console-synthetic\", \"choices\": [{\"index\": 0, \"message\": {\"role\": \"assistant\", \"content\": \"Hi!\"}, \"finish_reason\": \"stop\"}], \"usage\": {\"prompt_tokens\": 73, \"completion_tokens\": 4, \"total_tokens\": 77, \"prompt_tokens_details\": {\"cached_tokens\": 0}}}";
    assert_eq!(
        normalized(&r),
        format!("{}{body}", json_head("200 OK", body.len()))
    );
}

#[tokio::test]
async fn a_budget_cut_finishes_with_length_and_an_empty_answer_is_null() {
    let s = server(engine("Hi!")).await;
    let r = post(&s, &chat("\"stream\": true, \"max_tokens\": 2")).await;
    assert_eq!(
        String::from_utf8_lossy(&r.body),
        format!(
            "{}{}{}{DONE}",
            first_frame(),
            content_frames("Hi"),
            final_frame("length", HI_PROMPT_TOKENS, 2, 0)
        )
    );
    // The answer is only the end-of-turn token: no content is `null`.
    let s = server(engine("")).await;
    let r = post(&s, &chat("")).await;
    assert_eq!(
        String::from_utf8_lossy(&r.body),
        "{\"id\": \"chatcmpl-0123456789abcdef01234567\", \"object\": \"chat.completion\", \"created\": 1700000000, \"model\": \"pulsar-console-synthetic\", \"choices\": [{\"index\": 0, \"message\": {\"role\": \"assistant\", \"content\": null}, \"finish_reason\": \"stop\"}], \"usage\": {\"prompt_tokens\": 73, \"completion_tokens\": 1, \"total_tokens\": 74, \"prompt_tokens_details\": {\"cached_tokens\": 0}}}"
    );
}

#[tokio::test]
async fn a_client_stop_string_ends_the_answer_before_it() {
    let s = server(engine("abcSTOPdef")).await;
    let r = post(&s, &chat("\"stream\": true, \"stop\": [\"STOP\", \"\"]")).await;
    // "S", "ST" and "STO" are held back; "STOP" ends the answer with "abc" sent. Its
    // tokens count (the donor counts every token it takes).
    assert_eq!(
        String::from_utf8_lossy(&r.body),
        format!(
            "{}{}{}{DONE}",
            first_frame(),
            content_frames("abc"),
            final_frame("stop", HI_PROMPT_TOKENS, 7, 0)
        )
    );
}

fn lp_engine(text: &str) -> Arc<dyn console_core::engine::EngineFactory> {
    match LpEngine::new(script(text, DEFAULT_MAX_CONTEXT)) {
        Ok(f) => shared(f),
        Err(e) => panic!("{e}"),
    }
}

#[tokio::test]
async fn logprobs_ride_with_their_text_chunks() {
    let s = server(lp_engine("ok")).await;
    let r = post(
        &s,
        &chat("\"stream\": true, \"logprobs\": true, \"top_logprobs\": 1"),
    )
    .await;
    let lp = |tok: &str, id: u32, v: &str| {
        format!(
            "{{\"content\": [{{\"token\": \"{tok}\", \"logprob\": {v}, \"bytes\": [{id}], \"top_logprobs\": [{{\"token\": \"{tok}\", \"logprob\": {v}, \"bytes\": [{id}]}}]}}], \"refusal\": null}}"
        )
    };
    let text = |tok: &str, id: u32, v: &str| {
        format!(
            "data: {}{{\"content\": \"{tok}\"}}, \"finish_reason\": null, \"logprobs\": {}}}]}}\n\n",
            chunk_head(),
            lp(tok, id, v)
        )
    };
    assert_eq!(
        String::from_utf8_lossy(&r.body),
        format!(
            "{}{}{}{}{DONE}",
            first_frame(),
            text("o", 111, "-0.1"),
            text("k", 107, "-0.2"),
            final_frame("stop", HI_PROMPT_TOKENS, 3, 0)
        )
    );
    // Collected: every entry in order on the choice.
    let r = post(&s, &chat("\"logprobs\": true, \"top_logprobs\": 1")).await;
    let body = format!(
        "{{\"id\": \"{ID}\", \"object\": \"chat.completion\", \"created\": {CREATED}, \"model\": \"{MODEL}\", \"choices\": [{{\"index\": 0, \"message\": {{\"role\": \"assistant\", \"content\": \"ok\"}}, \"finish_reason\": \"stop\", \"logprobs\": {{\"content\": [{{\"token\": \"o\", \"logprob\": -0.1, \"bytes\": [111], \"top_logprobs\": [{{\"token\": \"o\", \"logprob\": -0.1, \"bytes\": [111]}}]}}, {{\"token\": \"k\", \"logprob\": -0.2, \"bytes\": [107], \"top_logprobs\": [{{\"token\": \"k\", \"logprob\": -0.2, \"bytes\": [107]}}]}}], \"refusal\": null}}}}], \"usage\": {{\"prompt_tokens\": 73, \"completion_tokens\": 3, \"total_tokens\": 76, \"prompt_tokens_details\": {{\"cached_tokens\": 0}}}}}}"
    );
    assert_eq!(String::from_utf8_lossy(&r.body), body);
}

#[tokio::test]
async fn prompt_progress_chunks_come_before_the_answer() {
    let paced = match PacedEngine::new(script("ok", DEFAULT_MAX_CONTEXT)) {
        Ok(f) => shared(f),
        Err(e) => panic!("{e}"),
    };
    let s = server(paced).await;
    let r = post(&s, &chat("\"stream\": true, \"return_progress\": true")).await;
    let progress = |processed: u32, ms: u32| {
        format!(
            "data: {}{{}}, \"finish_reason\": null}}], \"prompt_progress\": {{\"total\": 8192, \"cache\": 2048, \"processed\": {processed}, \"time_ms\": {ms}}}}}\n\n",
            chunk_head()
        )
    };
    assert_eq!(
        String::from_utf8_lossy(&r.body),
        format!(
            "{}{}{}{}{}{DONE}",
            first_frame(),
            progress(4096, 251),
            progress(8192, 500),
            content_frames("ok"),
            final_frame("stop", HI_PROMPT_TOKENS, 3, 0)
        )
    );
    // Without `return_progress` the same pings are keep-alive comments.
    let r = post(&s, &chat("\"stream\": true")).await;
    assert_eq!(
        String::from_utf8_lossy(&r.body),
        format!(
            "{}: keep-alive\n\n: keep-alive\n\n{}{}{DONE}",
            first_frame(),
            content_frames("ok"),
            final_frame("stop", HI_PROMPT_TOKENS, 3, 0)
        )
    );
}

#[tokio::test]
async fn json_mode_holds_the_answer_and_sends_its_json() {
    let s = server(lp_engine("Sure: {\"a\": 1} ok")).await;
    let r = post(
        &s,
        &chat("\"stream\": true, \"response_format\": {\"type\": \"json_object\"}"),
    )
    .await;
    assert_eq!(
        String::from_utf8_lossy(&r.body),
        format!(
            "{}{}{}{DONE}",
            first_frame(),
            frame("{\"content\": \"{\\\"a\\\": 1}\"}"),
            final_frame("stop", HI_PROMPT_TOKENS, 18, 0)
        )
    );
    let r = post(
        &s,
        &chat("\"response_format\": {\"type\": \"json_schema\", \"json_schema\": {}}"),
    )
    .await;
    assert_eq!(
        String::from_utf8_lossy(&r.body),
        format!("{{\"id\": \"{ID}\", \"object\": \"chat.completion\", \"created\": {CREATED}, \"model\": \"{MODEL}\", \"choices\": [{{\"index\": 0, \"message\": {{\"role\": \"assistant\", \"content\": \"{{\\\"a\\\": 1}}\"}}, \"finish_reason\": \"stop\"}}], \"usage\": {{\"prompt_tokens\": 73, \"completion_tokens\": 18, \"total_tokens\": 91, \"prompt_tokens_details\": {{\"cached_tokens\": 0}}}}}}")
    );
}

#[tokio::test]
async fn an_engine_death_mid_stream_is_an_error_event_then_done() {
    let dying = match DyingEngine::new(script("Hello world", DEFAULT_MAX_CONTEXT)) {
        Ok(f) => f,
        Err(e) => panic!("{e}"),
    };
    let s = server(shared(dying.clone())).await;
    let r = post(&s, &chat("\"stream\": true, \"max_tokens\": 50")).await;
    assert_eq!(
        normalized(&r),
        format!(
            "{}{}{}data: {{\"error\": {{\"type\": \"server_error\", \"message\": \"the engine stopped unexpectedly (exit code -9); the next request restarts it\"}}}}\n\n{DONE}",
            sse_head(),
            first_frame(),
            content_frames("Hello")
        )
    );
    // The next request starts the engine again and is answered whole.
    let r = post(&s, &chat("\"max_tokens\": 50")).await;
    assert!(String::from_utf8_lossy(&r.body).contains("\"content\": \"Hello world\""));
    assert_eq!(dying.restarts(), 1);
}

#[tokio::test]
async fn an_engine_error_after_the_stream_began_is_an_error_event() {
    let err = match ErrEngine::new(script("unused", DEFAULT_MAX_CONTEXT)) {
        Ok(f) => shared(f),
        Err(e) => panic!("{e}"),
    };
    let s = server(err).await;
    let r = post(&s, &chat("\"stream\": true, \"max_tokens\": 20")).await;
    // The donor's double yields a heartbeat before its ERR, so its stream holds one
    // `: keep-alive` there; here heartbeats are the server's own timer (contract section
    // 7), which these tests turn off, so the error event follows the first chunk.
    assert_eq!(
        String::from_utf8_lossy(&r.body),
        format!(
            "{}data: {{\"error\": {{\"type\": \"server_error\", \"message\": \"verify: layer 31 never rang (an illegal memory access was encountered)\"}}}}\n\n{DONE}",
            first_frame()
        )
    );
    // Collected, the same error is the donor's 400 before any byte of the answer.
    let r = post(&s, &chat("\"max_tokens\": 20")).await;
    assert_eq!(r.status, 400);
    assert_eq!(
        String::from_utf8_lossy(&r.body),
        "{\"error\": {\"type\": \"invalid_request_error\", \"message\": \"verify: layer 31 never rang (an illegal memory access was encountered)\"}}"
    );
}

#[tokio::test]
async fn a_client_that_leaves_cancels_the_turn() {
    let held = match HeldEngine::new(script("never sent", DEFAULT_MAX_CONTEXT)) {
        Ok(f) => f,
        Err(e) => panic!("{e}"),
    };
    let finished = Finished::default();
    let s = match builder(shared(held.clone()))
        .observer(Arc::new(finished.clone()))
        .start()
        .await
    {
        Ok(s) => s,
        Err(e) => panic!("{e}"),
    };
    let request = RawRequest::post("/v1/chat/completions")
        .header("Host", &s.host())
        .header("Content-Type", "application/json")
        .body(chat("\"stream\": true").as_bytes())
        .to_bytes();
    let mut stream = raw::connect(s.addr).await;
    raw::write(&mut stream, &request).await;
    let first = first_frame();
    let got = raw::read_until(&mut stream, |b| raw::contains(b, first.as_bytes())).await;
    let text = String::from_utf8_lossy(&got).into_owned();
    assert!(text.ends_with(&first), "{text}");
    let held_now = tokio::task::spawn_blocking(move || held.wait_held(DEADLINE)).await;
    assert!(matches!(held_now, Ok(true)));
    drop(stream);
    // The client watch sees it go: the turn is cancelled before the engine wrote a token.
    let records = finished.wait(1).await;
    assert_eq!(
        records
            .iter()
            .map(|r| (r.finish, r.output_tokens))
            .collect::<Vec<_>>(),
        vec![("cancel", 0)]
    );
}

#[tokio::test]
async fn the_engine_clock_gives_cached_tokens_and_timings() {
    let clocked = match ClockedEngine::new(script("ok", DEFAULT_MAX_CONTEXT)) {
        Ok(f) => shared(f),
        Err(e) => panic!("{e}"),
    };
    let s = server(clocked).await;
    let r = post(&s, &chat("")).await;
    let timings = "{\"cache_n\": 5, \"prompt_n\": 68, \"prompt_ms\": 40.0, \"prompt_per_token_ms\": 0.588, \"prompt_per_second\": 1700.0, \"predicted_n\": 3, \"predicted_ms\": 60.0, \"predicted_per_token_ms\": 20.0, \"predicted_per_second\": 50.0}";
    assert_eq!(
        String::from_utf8_lossy(&r.body),
        format!("{{\"id\": \"{ID}\", \"object\": \"chat.completion\", \"created\": {CREATED}, \"model\": \"{MODEL}\", \"choices\": [{{\"index\": 0, \"message\": {{\"role\": \"assistant\", \"content\": \"ok\"}}, \"finish_reason\": \"stop\"}}], \"usage\": {{\"prompt_tokens\": 73, \"completion_tokens\": 3, \"total_tokens\": 76, \"prompt_tokens_details\": {{\"cached_tokens\": 5}}}}, \"timings\": {timings}}}")
    );
}

#[tokio::test]
async fn a_prompt_over_the_context_is_refused_before_the_answer() {
    // The context rule of the turn driver, mapped by API-07: a 400 with its code.
    let s = server(match script("x", 64).build() {
        Ok(f) => shared(f),
        Err(e) => panic!("{e}"),
    })
    .await;
    let r = post(&s, &chat("\"stream\": true")).await;
    assert_eq!(r.status, 400);
    let body = String::from_utf8_lossy(&r.body).into_owned();
    assert!(
        body.contains("\"code\": \"context_length_exceeded\""),
        "{body}"
    );
    assert!(
        body.contains("maximum context length is 64 tokens"),
        "{body}"
    );
}
