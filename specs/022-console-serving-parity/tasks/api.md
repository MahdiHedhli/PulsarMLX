# Task detail: HTTP transport, dialects, monitoring and admin routes, process lifecycle

Feature 022, PulsarMLX Console. This file gives the full specification of each work package
with the prefix `API-`. The task list, the milestone order and the binding cross-cutting
decisions are in [`../tasks.md`](../tasks.md); **a binding decision or a reconciliation
there overrides any conflicting sentence in this file**.

Provenance: rendered without paraphrase from the planning records of 2026-11-14 (one planning
agent per subsystem, reading the pinned donor source). Path shorthand: `MAYA` is the pinned
project-maya checkout (commit `7e68a30f`), `ORIGIN` is this repository at `main` when the plan
was written. Sizes are estimates. Donor names such as `MAYA_*` variables describe the donor;
the product names are in [`../contracts/naming.md`](../contracts/naming.md).

## Subsystem summary

The API subsystem is everything in MAYA/serve/server.py (7,456 lines) that sits between the socket and the inference pipeline. It covers the listener and HTTP/1.0 close-delimited transport, body limits, chunked request bodies, timeouts and client-disconnect detection. It covers API keys, CORS and the cross-site rules (foreign_page, own_page), the dispatch order of do_GET, do_POST, do_DELETE and do_OPTIONS, and the error-body and status conventions. It covers request validation, sampling normalisation and shared defaults, and the OpenAI Chat Completions and Anthropic Messages adapters with their exact SSE frame sequences, usage, finish and stop_reason accounting, keep-alives and mid-stream error frames. It covers the resumable web-app streams (strata_resume, GET /v1/strata/stream, POST /v1/strata/cancel, answers/<id>.jsonl), the monitor model and monitoring routes (/health, /status, /v1/status, /metrics, /metrics/prometheus), and the llama.cpp-compatible discovery and utility routes (/v1/models, /models, /props, /slots, /tokenize, /detokenize, /api/tokens). It also covers the static dashboard routes, the dashboard-private admin routes in server.py, and the process lifecycle: CLI, run config, environment variables, logging, signals, the parent-pipe watch, graceful shutdown and the exit-code-76 restart. Full parity means a Rust server driven by the synthetic engines gives the same status codes, headers, JSON shapes and key order, SSE byte sequences, persisted files, CLI behaviour, environment handling and exit codes as server.py at 7e68a30f. This is measured by re-expressing every in-scope GPU-free test method (about 125 methods in test_server.py, test_stream_jobs.py, test_stop.py, test_logprobs.py and test_dashboard.py; the rest of those files belongs to other subsystems). Every method gets a row in a parity ledger, so nothing is silently dropped. Parity also includes the transport details Python's stdlib gave for free: HTTP/1.0 status lines, Date and Server headers, 501 for unsupported methods, 414/431 for oversized request lines or headers, no 100-continue, and connection close after every response. Branding, security hardening and synthetic labelling are listed as explicit deviations. The engine client, prompt building, Responses, MCP, attachments, media, model management and telemetry are consumed through named seams and are not planned here. This plan does provide the router and guard primitives those subsystems register their routes through.

## Build order proposed by the planner

- API-01 (first; no dependencies)
- API-15, API-04 and API-05 in parallel after API-01
- API-02 after API-01, in parallel with the three above
- API-03 after API-02
- API-19 right after API-03, so later packages share the test kit (needs the engine planner's MockEngine and the prompting planner's byte tokenizer and template fixture)
- API-16 in parallel with API-03 (needs only API-15)
- API-07 after API-03, API-04 and API-19, plus the core planner's prepare/run seam
- API-08 and API-09 in parallel after API-07
- API-10 after API-08
- API-06, API-11 and API-12 in parallel after API-03 and API-05 (API-12 also needs the web planner's asset set)
- API-13 and API-14 in parallel after API-03 and API-15
- API-17 after all of the above (integration)
- API-18 after API-17
- API-20 last: its contract skeleton can start with API-03, and its inventory gate closes the subsystem

## Work packages

<a id="api-01"></a>
### API-01 Wire foundations: Python-compatible JSON, error model, ids

- **Milestone:** M1
- **Rust target:** console-core::pyjson (formatter shared by every subsystem) and console-http::error
- **Platform:** platform-neutral
- **Risk:** low. Python float repr in exponent form is the only subtle part. The shortest-digit core comes from ryu, which serde_json already uses, and only the exponent and integral-float rendering are custom.
- **Depends on:** nothing
- **Estimated size:** 550 lines of code; 400 lines of tests
- **New dependencies:** serde_json feature preserve_order (pulls indexmap)
- **Donor sources:** MAYA/serve/server.py:416-428 (ContextOverflow, error_body), 5375-5381 (BadBody), 5457-5463 (_json: json.dumps ensure_ascii=False), 6152-6158 (_fail), 6283-6297 (exception mapping), 4936 and 5251 (uuid4 hex[:24] ids), 2577/2818/2863/2918 (json.dumps indent=1 for persisted files, ensure_ascii default True), 167-171 (text_file_limit), 163 (CTX_SLACK)

**Behaviors to reproduce**

- pyjson::to_wire(value) reproduces Python json.dumps(obj, ensure_ascii=False): item separator ', ', key separator ': ', raw UTF-8, keys in insertion order (serde_json preserve_order).
- pyjson::to_file(value) reproduces json.dumps(obj, indent=1): newline plus one space per level, ensure_ascii=True (non-ASCII as \uXXXX with surrogate pairs), ': ' key separator and no trailing spaces.
- Floats are formatted like Python repr: shortest round-trip digits, exponent form at 1e16 and above or below 1e-4, written '1e-05' and '1e+16', and integral floats as '2.0'. Integers keep their integer form. The same formatter backs the Prometheus value rendering (str(value)).
- The error taxonomy maps to bodies exactly. BadBody(status,msg) gives {error:{type:'invalid_request_error',message}}. Validation(msg[,code]) gives 400 and adds code only for context_length_exceeded. JobError/StoreBusy(status default 503) gives type server_error. EngineDied gives 503 server_error with message '<msg>; the next request restarts it'. Malformed gives 400 'malformed request (<Category>: <detail>)'. NotFound gives 404 {error:{message:'not found'}}. Overloaded gives 503 overloaded_error and Retry-After: 30. Auth gives 401 authentication_error 'missing or wrong API key'. Permission gives 403 permission_error.
- A response-state flag answer_started becomes true when the status line is written. After that, an error is only logged to stderr as 'request failed mid-answer: <msg>' and the connection is closed (the _fail semantics).
- random_hex(n) draws from OS randomness (libc getentropy on unix): 'chatcmpl-' and 'msg_' ids carry 24 lowercase hex characters.
- text_file_limit(ctx) = clamp(ctx*4, 524288, 16777216).

**Parity tests**

No dedicated maya test. Golden-byte unit tests are derived from documented Python behaviour: separators, ensure_ascii escaping including astral characters, and float repr edge cases (0.1, 1e-05, 1e16, 123456789.0, -0.0). These are indirectly exercised by every HTTP test in later packages. The ledger records these as 'foundation, no maya method'.

**Definition of done**

A reviewer can run the unit tests and see byte-exact outputs for a table of at least 40 values, each matching the Python output recorded in the test file with its expected string. Every error constructor produces the documented body and status. No dependency beyond serde, serde_json (preserve_order) and libc.

<a id="api-02"></a>
### API-02 HTTP/1.x transport: listener, request parsing, bodies, responses, disconnect watch

- **Milestone:** M1
- **Rust target:** console-http::transport (tokio + httparse, one request per connection)
- **Platform:** platform-neutral
- **Risk:** medium. Hand-rolled HTTP parsing is security-sensitive. It is mitigated by httparse for the request line and headers, one request per connection (no pipelining or smuggling surface), rejecting requests that carry both Content-Length and chunked Transfer-Encoding (a hardening listed as a deviation), and strict limits. The peek-based watcher must not consume bytes and must stop once the response is written.
- **Depends on:** API-01
- **Estimated size:** 1100 lines of code; 700 lines of tests
- **New dependencies:** tokio (rt-multi-thread, net, io-util, time, sync, macros); httparse
- **Donor sources:** MAYA/serve/server.py:5346-5372 (backlog, request_timeout, body_limit), 5403-5455 (handler class, protocol_version HTTP/1.0, log_message no-op, send_response, _body with chunked decoding), 5457-5463, 6463-6474 (_sse with TCP_NODELAY), 5019-5044 (watch_client), 6715-6734 (Server: allow_reuse_address, request_queue_size, handle_error), 6797-6803 (serve), 7166-7171 (port probe); Python http.server/BaseHTTPRequestHandler semantics (status line, Server and Date headers, send_error for 400/414/431/501/505)

**Behaviors to reproduce**

- Bind host:port with tokio TcpSocket. The listen backlog comes from the backlog env var: default 256, minimum 5, non-numeric falls back to 256. Port 0 is supported and the bound port is reported. A probe_port(host,port) helper binds and closes for the start-up check.
- Each accepted connection serves exactly one request and then closes. Responses use the status line 'HTTP/1.0 <code> <reason>' followed by 'Server: pulsar-console/<version>' and 'Date: <RFC 1123 GMT>' (see deviations), then handler headers. Bodies without Content-Length are delimited by closing the connection. No 100 Continue is ever sent.
- Request-line and header limits follow BaseHTTPRequestHandler. A request line over 65536 bytes gets 414. A header line over 65536 bytes or more than 100 headers gets 431. A malformed request line gets 400 'Bad request syntax'. A version other than HTTP/1.x gets 505. A method other than GET, POST, DELETE or OPTIONS (HEAD, PUT, PATCH and so on) gets 501 'Unsupported method'. These use Python's default HTML error page format with Content-Type text/html;charset=utf-8.
- Body reading checks Transfer-Encoding first: when the last comma-separated value is 'chunked', the body is decoded with size lines read up to 1025 bytes, optional ';ext', and up to 64 trailer lines of at most 8193 bytes. A bad size, a missing CRLF or a short chunk gives BadBody 400 'malformed chunked request body'. A running total over the limit gives 413 'the request body is larger than N MiB (<ENV> raises the limit)' and closes the connection. Otherwise Content-Length is used: a non-integer or negative value gives 400 'invalid Content-Length', and a value over the limit gives 413 before any body byte is read. A missing Content-Length means an empty body. The limit comes from the body-limit env var in MiB (default 256; zero or invalid means 256).
- Every socket read or write gets a per-operation timeout from the request-timeout env var (default 300 s; zero, negative or invalid means 300). There is no overall request deadline.
- Response writers: json(code, value) with Content-Type application/json and Content-Length; text(code, ctype, bytes); redirect(302, location) with Content-Length 0; sse_start() sets TCP_NODELAY and writes 200 with Content-Type text/event-stream and Cache-Control: no-cache (no Content-Length); ndjson_start() for the model API planner; and a raw frame sink whose write failure is reported as ClientGone.
- A client watcher used for non-resumable requests runs a tokio task that every 0.5 s peeks one byte (TcpStream::peek). On EOF or a reset it fires the request's CancelToken. Received data is not treated as EOF. The watcher stops when the request completes or is cancelled.
- The path is normalised for routing: the query string is dropped and trailing slashes are removed with rstrip('/'), so '/' becomes ''. The raw path and query are kept for handlers that test substrings ('requests=all', 'force=1') or parse_qs.
- There is no access log. Connection errors (reset, broken pipe) are swallowed silently. Other handler panics are caught per connection and logged with a short line without crashing the server.
- Graceful stop: stop accepting; in-flight connections continue; a JoinSet tracks them for shutdown orchestration (API-17).

**Parity tests**

test_server.py RequestBodies: test_a_body_over_the_limit_is_refused_unread, test_a_bad_content_length, test_a_chunked_body, test_a_malformed_body_is_a_400, test_the_listen_backlog (5 methods; test_several_api_keys goes to API-03). NoDelayStreaming.test_sse_sets_tcp_nodelay (1). The raw-socket parts of GoneClients and QueuedKeepAlives are re-expressed as transport tests with a fake handler that blocks. New tests cover the 501/414/431/505 paths and the per-operation timeout, using a short timeout from the env var. All are re-expressed in Rust with the raw socket client from API-19, writing bytes and reading to EOF exactly as the Python tests do.

**Definition of done**

All listed tests pass under cargo test --locked in the console workspace. A raw socket that sends 'Content-Length: 314572800' gets 413 without the server reading the body (verified with a test socket that never sends a body and still receives the answer). Chunked bodies decode, including with trailers. A blocked handler is cancelled within 1 s of the client closing. SSE sockets have TCP_NODELAY set (getsockopt assertion). A reviewer can confirm there is no keep-alive and no chunked response encoding by inspecting raw response bytes in a test.

<a id="api-03"></a>
### API-03 Router, authentication, CORS and cross-site guards

- **Milestone:** M1
- **Rust target:** console-http::router and console-http::guard
- **Platform:** platform-neutral
- **Risk:** medium. Dispatch-order subtleties matter. POST authenticates before the foreign check but DELETE checks foreign first. Unknown GETs skip auth. These are pinned by the exhaustive table test. The DNS-rebinding guard is a behaviour change the owner must approve.
- **Depends on:** API-01; API-02
- **Estimated size:** 750 lines of code; 650 lines of tests
- **Donor sources:** MAYA/serve/server.py:5383-5400 (key_list, parse_cors_origins), 5780-5819 (_cors_allow, end_headers, do_OPTIONS, _authorized), 5821-5826 (_response_owner), 5923-5933 (do_DELETE), 5934-6139 (do_GET order), 6141-6150 (_foreign_page), 6160-6282 (do_POST order), 6327-6338 (_own_page), 6434-6450 (attach-style guard)

**Behaviors to reproduce**

- The route table reproduces maya's dispatch order exactly. GET checks /models/sse first, then the Ollama GET set, /v1/responses/*, /fonts/*, /web, /web/*, /metrics, /metrics/prometheus, /settings, /mcp, '', /health, the /api/* dashboard GETs, /status, /v1/models and /models, /props, /slots, /v1/status and /v1/strata/stream. Anything else gets 404 {error:{message:'not found'}} with no auth check.
- POST checks the API key first, then the foreign origin, then matches the path in maya's order. The body-reading POST routes parse JSON and require an object ('the request body must be a JSON object' 400).
- DELETE runs the foreign-origin check first. /v1/responses/* goes to the Responses handler and /api/delete is authorised and then goes to the model API handler. Anything else is authorised and gets 404.
- Other subsystems register handlers into named slots in this table (Responses, Ollama model API, llama.cpp /models/*, attach), so dispatch order stays centralised and testable.
- API keys come from a comma-separated string with each key trimmed and empties dropped, or from a config list of strings (a key may contain a comma). Comparison is constant-time and done in-house. The key is presented as 'Authorization: Bearer <k>' (case-insensitive 'bearer ', value trimmed), else the x-api-key header. A missing or wrong key gives 401 {error:{type:'authentication_error',message:'missing or wrong API key'}}.
- The key is required on every POST and DELETE and on every GET except '', /health, /web/*, /fonts/*, the /web redirect, unknown paths and /models/sse (that route checks the key inside its handler, which the model API planner owns). /v1/strata/stream, /v1/models, /models, /props, /slots, /v1/status, /status, /metrics*, /settings, /mcp and the /api/* GETs check it.
- cors_allow returns None unless cors_origins is non-empty and the raw path starts with /v1/. If the list contains '*' it returns '*'. Otherwise it returns the request Origin (trailing slash stripped) when listed. Every response on such a request, including errors and streams, gets Access-Control-Allow-Origin, plus Vary: Origin unless the value is '*'.
- OPTIONS on any path needs no key. When allowed it returns 204 with Access-Control-Allow-Methods 'GET, POST, DELETE, OPTIONS', Access-Control-Allow-Headers echoing Access-Control-Request-Headers or 'Content-Type, Authorization, x-api-key', Access-Control-Max-Age 600 and Content-Length 0. When not allowed it returns 403 with Content-Length 0 and no CORS headers.
- foreign_page: an Origin whose text after '://' differs from the Host header, and that is not CORS-allowed, gets 403 {error:{type:'permission_error',message:'requests from other web pages are refused (the config's cors_origins lists the pages allowed)'}}. A request without an Origin passes.
- own_page(what): Content-Type must start with application/json, else 415 {error:{message:'send application/json'}}. Any Origin not equal to Host gets 403 {error:{message:'<what> only from <product>'s own page'}}, rebranded. The attach variant requires application/octet-stream or application/pdf (parameters stripped, lower-cased), else 415 with maya's message, and uses the same origin rule with its own message.
- response_owner(): 'public' when no key is configured, else the lowercase hex SHA-256 of the presented key, for the Responses planner. The SHA-256 implementation is provided by console-core (shared with Responses).
- Deviation (security, owner approval needed): a Host allow-list against DNS rebinding. When the bind address is loopback, Host must be localhost, 127.0.0.1 or [::1] (any port), or be listed in a new config key allowed_hosts. Otherwise the request gets 403 permission_error before routing. This is off when bound to a non-loopback address unless allowed_hosts is set.

**Parity tests**

test_server.py CorsOptIn (8 methods: test_without_the_setting_nothing_changes, test_a_listed_page_gets_its_preflight_and_the_header, test_another_page_gets_nothing, test_a_trailing_slash_in_the_config_is_forgiven, test_star_allows_every_page, test_settings_and_the_page_itself_stay_closed, test_another_page_cannot_post_without_a_preflight, test_the_config_value; the last also touches API-15). RequestBodies.test_several_api_keys (1). WebApp.test_discovery_needs_the_api_key and test_metrics_need_the_key_when_one_is_set (2, shared with API-06/11). SharedSettings.test_only_strata_s_own_page_may_set_them and test_they_need_the_key_when_one_is_set (2, shared with API-13). ModelManagement.test_the_api_key_guards_them_and_status (route-guard half). ClientShapes.test_query_string (1). A new exhaustive dispatch-table test asserts, for every route, auth required or not, the guard applied, and the 404 behaviour. A new rebinding test covers the deviation.

**Definition of done**

A table-driven test enumerates every route in maya's do_GET, do_POST, do_DELETE and do_OPTIONS with and without a key and with foreign, same-host and absent Origin, and asserts the status. A reviewer can diff that table against the dispatch order cited in server.py. All listed maya methods are re-expressed and pass.

<a id="api-04"></a>
### API-04 Request validation, sampling normalisation and shared defaults

- **Milestone:** M1
- **Rust target:** console-core::request (typed RequestOptions over a preserve-order JSON map) and console-core::sampling
- **Platform:** platform-neutral
- **Risk:** medium. Python numeric coercion quirks (bool is an int, float('1e3') accepted, ' 5 ' accepted, huge integers) must be reproduced on a serde_json Value that separates i64, u64 and f64. Integers beyond u64 are an accepted, documented divergence. Reasoning-level word validation belongs to the prompting planner and is only called from here.
- **Depends on:** API-01
- **Estimated size:** 900 lines of code; 750 lines of tests
- **Donor sources:** MAYA/serve/server.py:497-521 (logprobs_of, logprobs_asked), 624-632 (client_stop_strings), 635-718 (PENALTY_WINDOW_MAX, SAMPLING_TYPES, check_request_sampling, logit_bias_of), 2489-2530 (Service.check_request), 2571-2609 (set_shared, with_shared), 4275-4278 (precedence), 6806-6854 (clean_shared_defaults), 6899-6960 (sampling_defaults_from_config), 1263-1319 (semantic sampling rules the engine line applies); MAYA/docs/SETTINGS.md:407-464

**Behaviors to reproduce**

- Numeric fields: temperature, top_p, min_p, presence_penalty, frequency_penalty and repetition_penalty are numbers; top_k, penalty_last_n and seed are integers. Absent or null fields are not checked. A non-blank string parses with Python float() semantics (surrounding whitespace allowed) and becomes an int when it matches an optional sign plus digits, or when the field is an integer field with an integral value. NaN, infinity, bool, a JSON float for an integer field (40.5, and 40.0 sent as a number) and other types give 400 '<field>: a number' or '<field>: an integer'. The window field is named by whichever alias the request used.
- Aliases: repeat_penalty is copied to repetition_penalty when that is absent, and repeat_last_n to penalty_last_n. penalty_last_n below -1 gives 400 '<key>: -1 (the whole context), 0 (no penalties) or a positive number of tokens'.
- loop_guard accepts bool, the strings true/false/on/off/1/0 (case-insensitive, trimmed) or the integers 0/1. Anything else gives 400 'loop_guard: true or false'. ablate must be bool ('ablate: true or false'), and true requires engine INFO ablate=1. ignore_eos must be bool and needs a positive max tokens plus engine logit_bias=1; it then bans every stop and EOS id at -100.0.
- logit_bias must be an object whose keys are digit strings, with id at most 2^31-1 and below the vocabulary size. Biases are numbers or numeric strings in -100..100. It cannot ban the whole vocabulary, and it needs engine INFO logit_bias=1. Each failure has maya's exact message, rebranded where it says 'update Maya'.
- logprobs must be bool; top_logprobs is 0..20 (an int or a numeric string) and only allowed with logprobs true. Engine INFO logprobs must be an int at least n, else 400 with maya's message.
- Stop strings: 'stop' (a string or list) or else 'stop_sequences'; the first 16 non-empty strings are kept.
- Max tokens: OpenAI uses int(max_completion_tokens or max_tokens or 0) and Anthropic int(max_tokens or 0). Zero or negative means the rest of the context.
- Shared defaults keep only known keys within ranges: reasoning_effort in {none,auto,low,medium,high,xhigh,max}, temperature 0..2, top_p (0,1], min_p [0,1), integer top_k 0..64, positive integer seed and max_tokens, repetition_penalty (0,10], frequency_penalty and presence_penalty -2..2, experimental_speed_projection bool. Null or empty values are dropped. An unknown key or bad value gives 400 naming it.
- with_shared(req, dialect) fills max_tokens when the request has neither max field. For OpenAI it fills reasoning_effort when the request has no reasoning_effort, no reasoning and no chat_template_kwargs.enable_thinking or reasoning_effort. For Anthropic it sets thinking {type:'disabled'} for 'none', else output_config.effort, but only when the request has no thinking and no output_config. It marks _level_shared when filled and the template is glm_dsa.
- Precedence when resolving sampling: non-null request value, then shared settings, then run-config sampling block (or the model's built-in defaults supplied by the manage planner when the config has no sampling block), then nothing.
- ResolvedSampling applies the semantic rules. temperature <= 0 means greedy and suppresses top_p, top_k, min_p and seed but keeps penalties. top_p is kept only below 1. top_k 1..64 is kept as given; 0 or above 64 becomes 64. min_p is kept only in (0,1]. seed is kept only above 0. Penalties are kept only when non-neutral, with window: positive as given, -1 means 4096, absent means 64, and 0 disables all penalties. The output is an ordered key list that the engine planner encodes into GEN keys.
- Run-config sampling is validated at start-up (types and top_k 1..64) and a bad value aborts with maya's message.
- Deviation (security): every client key beginning with '_' is removed at the dialect boundary before any processing. Maya removes only _restore. Internal markers travel in a typed struct, never in the client map.

**Parity tests**

test_server.py SamplingKeys (9 methods): the semantic assertions are re-expressed against ResolvedSampling, and the exact engine-line string (for example ' temperature=0.7 penalty_repeat=1.1 penalty_last_n=64 seed=5') is asserted jointly with the engine planner's GEN encoder. RequestChecks (7 methods). test_logprobs.py Fields.test_asking and test_refused (2). SharedSettings.test_other_apps_get_the_chat_settings, test_top_k_and_min_p_off_win_over_the_run_config, test_penalties_only_when_set and test_off_again (4, HTTP halves with API-13). New unit tests cover every error message and the underscore-stripping deviation.

**Definition of done**

Every message string from check_request_sampling, logit_bias_of, check_request and clean_shared_defaults appears in a Rust test with the triggering input. A precedence matrix test (request, shared, config, model defaults) passes. SamplingKeys expectations hold through the engine encoder in a joint test.

<a id="api-05"></a>
### API-05 Monitor model: status, live rate, peaks, totals, history and queue watchdog

- **Milestone:** M4
- **Rust target:** console-core::monitor
- **Platform:** platform-neutral
- **Risk:** low. Ownership boundary: the core run loop (another planner) calls these hooks. The hook list must be agreed before either side is coded.
- **Depends on:** API-01
- **Estimated size:** 650 lines of code; 550 lines of tests
- **Donor sources:** MAYA/serve/server.py:172-196 (RATE_WINDOW_S, RATE_MIN_SPAN_S, QUEUE_* constants, PEAK_MIN_TOKENS), 2345-2379 (RequestStat), 2383-2480 (Service status fields: status, history deque 500, totals, current_requests, latest_request, last_timings, last_request_at, started_at, loop_guard_counts), 3239-3311 (start_queue_watch, _tok_s, _note_peak, _tok_s_mean, _prefill_tok_s_mean), 3774-3811 (_note/_progress status updates, tail 600), 4692-4756 (history row and totals in run's finally), 4766-4793 (own_prompt_figures, request_timings)

**Behaviors to reproduce**

- The status record holds busy, queued, phase ('reading the prompt' | 'thinking' | 'answering' | 'writing a tool call: <name>' | 'tool call complete'), prompt_tokens, generated, tool, tail (the last 600 characters written), max_tokens and started. Before the first request it is exactly {busy:false, queued:0}.
- RequestStat implements a 5 s sliding window. The base is the last sample at or before now-5. The rate runs from base (or the first sample) to the newest sample. With a span under 0.25 s it is (n1-n0+1)/max(0.25, now-t0). The rate is never negative.
- The live rate is the sum over requests decoding now and is 0.0 when not busy. Each reading feeds the peak: rounded to 0.1, recorded when at least 32 tokens are counted and above the previous peak, as {tok_s, tokens, time}.
- tok_s_mean = generated / (now - first_token) for the latest request. prefill_tok_s_mean is the engine figure while reading the prompt, else 0.0.
- History is a ring of 500 rows with fields projection, time, duration_s, finish (stop|length|cancel|error|disconnect), api (openai|anthropic|web|responses tag from the request), prefill_tok_s, prompt_tokens, reused, output_tokens, engine_generated, prompt_ms, decode_ms, decode_tok_s, hit_rate, drafts_offered, drafts_accepted, spec_off and loop_guard. Totals hold since, requests, prompt_tokens, reused, output_tokens, prompt_ms, decode_ms and peak_decode.
- request_timings(engine clock) produces llama.cpp names: cache_n, prompt_n, prompt_ms, prompt_per_token_ms, prompt_per_second, predicted_n, predicted_ms, predicted_per_token_ms, predicted_per_second, plus draft_n and draft_n_accepted when drafting. It returns None without a clock.
- Hook API for the core run loop: queue_enter/leave, request_start(api, prompt_tokens, max_tokens), phase(...), tokens(n, now), text_written(s), request_end(row, timings). All are guarded by one mutex. Updating only through these hooks keeps the record consistent after a consumer stops early.
- Queue watchdog: every 15 s, if a waiter is at least 120 s old and no warning came in the last 60 s, log maya's WARNING line (rebranded) with the waiting count, oldest age, what is running, fifo.held_by() and the active count.
- A wait of 5 s or more is logged when the request's turn comes (the line text comes from maya).

**Parity tests**

test_server.py LiveRateBursts (5), LiveRate (3), TimingsDrafts.test_draft_fields (1), StatsAfterConsumerStops.test_final_stats_are_kept_and_next_request_is_clean (1, jointly with the core run loop). test_dashboard.py Dashboard.test_peak_decode_speed, test_peak_decode_follows_the_live_figure and test_requests_record_their_api (3). The time source is injectable so the window tests are deterministic.

**Definition of done**

All listed tests pass with an injected clock. The hook trait is documented in specs/022 contracts. A reviewer can check that RequestStat matches the Python arithmetic on maya's burst scenarios (300-token burst then one token 0.3 s later is not about 1000 tok/s).

<a id="api-06"></a>
### API-06 Monitoring routes: /health, /status, /v1/status, /metrics, /metrics/prometheus

- **Milestone:** M4
- **Rust target:** console-http::routes::monitor
- **Platform:** platform-neutral
- **Risk:** medium. Wide surface that depends on many other subsystems' views. Key order and the conditional presence of fields must match. Exposition values must use the Python str() formatting from API-01.
- **Depends on:** API-03; API-05; CORE run loop and FIFO introspection (oldest_wait, waiting, capacity); HOST telemetry snapshot; ENGINE view (info, stat, stat_history, vram, progress, multi, alive, unloaded); ENGINE gpu_map view port; RESPONSES stats(); MANAGE savings summary, updater busy, storage
- **Estimated size:** 900 lines of code; 700 lines of tests
- **Donor sources:** MAYA/serve/server.py:6019-6049 (/health), 6087-6100 (/status), 5989-6002 (/metrics and /metrics/prometheus routing), 3313-3374 (metrics), 3376-3388 (_gpu_map call), 3390-3472 (PROM_STAT, prometheus), 3474-3524 (v1_status), 2316-2343 (speculation_modes), 2481-2487 (ablate_state)

**Behaviors to reproduce**

- /health needs no key and is always 200, with fields in maya's order: status ('updating' when the updater is busy, 'reloading' during a context reload, else 'ok'), max_context, model, max_text_file, model_label, images, api_key (bool), defaults (temperature, top_p, top_k and min_p from the sampling defaults, plus reasoning_effort shown with the template-specific level naming supplied by the prompting planner), videos, version, mcp_tools, unloaded, history_thinking, ablate {available, default, why}, text_only (only when true) and thinking_budget_max (only when non-zero).
- /status needs the key. It copies the status record; when busy it adds elapsed_s (1 decimal) and, while answering, tokens_per_s and tokens_per_s_mean (1 decimal). started is removed.
- /metrics needs the key and returns {engine, live, tiers, gpu_map, requests (newest first, 12 unless the raw path contains 'requests=all'), requests_kept, totals, loop_guard (counts plus on), hardware (telemetry now without 'vram'), hardware_static, history, time, reload, storage, savings}. live.state is 'reading' while busy before the first token, 'generating' while answering, else 'unloaded' or 'idle'. The other live fields and the progress-derived prompt_read, prompt_total and prompt_reused follow maya. engine merges model, model_label, max_context, images, engine INFO keys, version, trained_context, dspark when set, and speculation from speculation_modes (DSpark, then DFlash2 or else MTP, then Lookup). tiers carries now plus history series for the ten STAT keys when the engine reports STAT lines.
- /metrics/prometheus needs the key and uses Content-Type 'text/plain; version=0.0.4; charset=utf-8'. It emits '# HELP n h\n# TYPE n kind\nn value\n' triples in maya's order and with maya's help texts: the llamacpp:* counters and gauges (prompt_n = prompt_tokens - reused; throughput 0 when no time), requests_total, decode_peak, engine_alive, the eight loop_guard counters, engine_<key> for each numeric non-bool STAT key in PROM_STAT order (eg_lookup_* as counters), and responses_cache_<k> and responses_jobs_<k> from the Responses stats, gauge or counter per maya's gauge key set. The maya:* prefix is renamed (see deviations) and llamacpp:* stays unchanged.
- /v1/status needs the key and returns {service, model, engine, started, uptime_s, cache_max_tokens, context {native, max_positions}, concurrency {serving, requested}, dialects [the three routes], responses {cache, jobs, structured_outputs {mode:'validate-before-publish', schema_draft:'2020-12', constrained_decoding:false}}, vision {enabled, available, error}, memory_note, activity {requests, in_flight, queue {waiting, first_waited_s, places}, last_request_at}, last_timings, machine {at, gpu or null, ram or null}}, with the scaling and rounding from maya.
- Every monitoring route reads state through traits (EngineView, TelemetryView, SavingsView, ResponsesStats, LoopGuardCounts, UpdaterState, ReloadState), so the synthetic build fills hardware fields from the host sampler and labels them.
- Deviation (D3 labelling): /health and /v1/status gain synthetic:true and backend:'mock'|'line-protocol'.

**Parity tests**

test_server.py PrometheusMetrics (1), WebApp.test_metrics, test_the_model_shown_model_first, test_text_file_limit_follows_the_context and test_metrics_need_the_key_when_one_is_set (4), UsageAndStatus.test_v1_status (1). test_dashboard.py Dashboard.test_health_has_the_version, test_health_history_thinking, test_metrics_say_whether_deepseek_drafts, test_metrics_list_the_drafters_that_run, test_stat_lines_carry_the_draft_counts_and_the_ssd_bytes (Prometheus half) and test_requests_carry_the_drafts_offered_and_kept (6). GpuMap.test_metrics_carry_it (route half only). About 13 methods, re-expressed against the fake engine with an injected telemetry stub.

**Definition of done**

Golden JSON tests for /health, /v1/status and /metrics against the fake engine assert key order and conditional fields. A Prometheus golden test checks the whole exposition text byte for byte for a seeded state. All listed maya methods appear in the ledger as passing.

<a id="api-07"></a>
### API-07 Inference request lifecycle driver (dialect-agnostic)

- **Milestone:** M1
- **Rust target:** console-http::inference
- **Platform:** platform-neutral
- **Risk:** high. Cancellation correctness: dropping the stream must always produce STOP plus drain before the FIFO place is released. That depends on the core planner's RAII guard. The joint test 'a gone client never reaches the engine and frees the place' is the acceptance gate.
- **Depends on:** API-02; API-03; API-04; CORE Pipeline::prepare and Pipeline::run item stream with RAII stop-and-drain; ATTACH expand_request; ENGINE reload state and MANAGE updater busy
- **Estimated size:** 600 lines of code; 550 lines of tests
- **Donor sources:** MAYA/serve/server.py:6160-6166 and 6241-6297 (POST preamble, JSON object check, reload or update 503 gate, attach expansion call, dialect dispatch, exception mapping), 5019-5044 (watch_client wiring), 6607-6624 and 6692-6710 (stream loops, write failure means cancel plus generator close), 4796-4808 (_debug_req), 2093-2110 (turn_mark, MAYA_TURN_TRACE), 3680-3694 (errors raised by prepare)

**Behaviors to reproduce**

- For /v1/chat/completions, /v1/responses and /v1/messages: while a context reload is waiting or running, or the updater is busy, answer 503 {error:{type:'overloaded_error',message}} with Retry-After: 30 and maya's two messages (rebranded) before any parsing beyond the body.
- Next, the attachment planner's expand_request(req, dialect, want_images, text_limit=text_file_limit(ctx), text_only) is called, then the dialect handler.
- Error mapping before headers: BadBody keeps its status; Validation, ContextOverflow and engine ERR give 400 (code only for overflow); ModelStarting gives 503 type invalid_request_error 'the model is starting; try again in a moment'; EngineDied gives 503 server_error; JobError/StoreBusy give their own status; typed-extraction failures give 400 'malformed request (...)'.
- A request context carries a CancelToken, the client watcher (started unless the request is a streamed strata_resume chat), the embeddings handle and the monitor api tag.
- StreamDriver<D: DialectSerializer> pulls the run items. Ping without progress becomes ': keep-alive\n\n'. Frames are written and flushed one at a time. On ClientGone it fires cancel and drops the run stream, which makes the core loop send STOP and drain to DONE while still holding the FIFO place. On EngineDied or engine ERR after headers it writes the dialect's error tail.
- The non-stream path drains the same item stream into the dialect collector before any header is written, so failures become real statuses.
- The debug env var logs one '[console] <api>: ...' line per request with the last message's 80-character preview, max_new, thinking and prompt tokens, matching maya's format. The turn-trace env var records monotonic marks (http, body, json, prepare_start, prepared) for the engine trace line.
- A server that is stopping refuses queued requests through the core FIFO (the message comes from the core planner) and maps that to the same 503 shape maya produces.

**Parity tests**

test_server.py EngineDeath.test_error_then_restart and test_engine_err_mid_stream (2, the HTTP framing halves), GoneClients.test_a_queued_request_leaves_when_its_client_goes (1), QueuedKeepAlives.test_keep_alives_while_queued (1, both dialects), ModelManagement.test_a_request_while_the_engine_starts_gets_a_retryable_503 (1), MaxTokens.test_debug_log_shows_the_resolved_budget (1). test_dashboard.py Dashboard.test_chat_gets_503_while_reloading (1). Re-expressed with HeldEngine-style fakes from API-19 and the engine planner.

**Definition of done**

Gone-client and keep-alive tests pass reliably 50 times in a loop. Every exception class maps to the documented status and body in a table test. A reviewer can see that a write failure triggers exactly one engine STOP in a fake-engine transcript.

<a id="api-08"></a>
### API-08 OpenAI Chat Completions adapter and SSE stream

- **Milestone:** M1
- **Rust target:** console-http::dialect::openai
- **Platform:** platform-neutral
- **Risk:** medium. The exact frame order and the content null-versus-empty rule are easy to break. The JSON-mode hold buffer and logprob attachment must exclude tool-call tokens, which the core planner enforces upstream.
- **Depends on:** API-07; PROMPT openai_to_messages and Event model (reasoning, content, tool_start, tool_args, tool_call with call.id, name, arguments, to_openai); MCP run_with_mcp, hub wait and template_tools; CORE done record (finish, completion_tokens, reused, timings, stop_sequence, prompt_tokens)
- **Estimated size:** 750 lines of code; 700 lines of tests
- **Donor sources:** MAYA/serve/server.py:6566-6624 (_openai), 4909-4930 (json_from_text), 4933-5008 (openai_chunks), 5204-5246 (openai_collect), 581-596 (logprob entry shape); MAYA/serve/frontend.py:561-724 (conversion, called through the prompting planner)

**Behaviors to reproduce**

- Handler order: with_shared, set the api tag ('web' when strata_resume is exactly true, else 'openai'), check_request, openai_to_messages (prompting planner), resolve max tokens (max_completion_tokens wins). When strata_mcp is exactly true and an MCP hub exists: apply the own_page guard ('MCP tools can be used'), wait up to 10 s for the hub, and append hub tools that do not clash with request tool names (the request's own win), turning MCP on only if any were added. Then prepare, carry _prefill, _blocked, _think_resume and _think_max into the typed run options, create the cancel context, and run either with MCP (run_with_mcp) or plainly.
- Chunk shape: {id:'chatcmpl-'+24 hex, object:'chat.completion.chunk', created (epoch int), model:<configured model name>, choices:[{index:0, delta, finish_reason:null}]}. The first chunk's delta is {role:'assistant', content:''} and is produced before queueing.
- Run events: reasoning text becomes delta.reasoning_content and content text becomes delta.content; empty texts are skipped. tool_start becomes {tool_calls:[{index, id, type:'function', function:{name, arguments:''}}]}, tool_args becomes {tool_calls:[{index, function:{arguments:piece}}]}, a tool_call already streamed is skipped, and a whole tool_call becomes one entry with the next index. Mcp items become a chunk with an empty delta plus strata_mcp. A ping with progress becomes a chunk with an empty delta plus top-level prompt_progress, but only when return_progress and stream are both truthy; otherwise it becomes a keep-alive.
- With logprobs requested, each text chunk's choice carries logprobs {content:[entries], refusal:null}, or reasoning entries under logprobs.reasoning_content with content [].
- JSON mode (response_format.type json_object or json_schema): content text and its logprob entries are held, and json_from_text(joined text) is sent as one content chunk at Done. json_from_text tries the whole stripped text, then the first ```json fence body, then the first decodable object or array starting at any '[' or '{' (using the serde_json stream deserializer byte offset), else returns the original text.
- The final chunk has delta {} and finish_reason 'tool_calls' when any call was emitted and finish is stop, 'stop' for cancel, else stop or length. It always carries usage {prompt_tokens (the done record's prompt_tokens, else the prompt length), completion_tokens, total_tokens, prompt_tokens_details:{cached_tokens: reused or 0}}, plus timings when present. After it comes 'data: [DONE]\n\n'.
- Mid-stream EngineDied writes 'data: {"error":{"type":"server_error","message":"<m>; the next request restarts it"}}\n\ndata: [DONE]\n\n', and engine ERR writes the same with the raw message. The error JSON uses Python default separators with ensure_ascii=True, unlike normal chunks, which use ensure_ascii=False.
- The non-stream collector skips None and prompt_progress chunks, gathers strata_mcp items, concatenates content and reasoning, and merges tool-call pieces by index (id, namespace, name and arguments appended). It returns {id, object:'chat.completion', created, model, choices:[{index:0, message:{role, content or null, reasoning_content?, tool_calls?, strata_mcp?}, finish_reason}], usage, logprobs? ({content, refusal:null, reasoning_content?}), timings?}.
- model, n, user and stream_options in the request are ignored, as maya ignores them.

**Parity tests**

test_server.py MaxTokens (5: the HTTP half of each; the context check is the core planner's), FitMaxTokens (3, HTTP half), UsageAndStatus.test_openai, test_openai_stream and test_no_clock (3), PromptProgressStream (3), MalformedToolCallAnswers.test_the_request_answers (1), ClientShapes.test_openai_late_developer_and_system and test_leading_system_unchanged (2, HTTP half). test_logprobs.py Api (7). ThinkingBudget (6, OpenAI cases jointly with the prompting and core planners). About 30 methods.

**Definition of done**

Golden SSE transcripts (raw bytes) for plain text, reasoning plus text, streamed tool call, whole tool call, JSON mode, logprobs, prompt progress, cancel and engine death match the expected byte strings in the test files. The non-stream collector matches the corresponding JSON goldens. All listed maya methods pass.

<a id="api-09"></a>
### API-09 Anthropic Messages adapter and event stream

- **Milestone:** M2
- **Rust target:** console-http::dialect::anthropic
- **Platform:** platform-neutral
- **Risk:** low. The block-index state machine is the only subtle part, and it is covered by goldens.
- **Depends on:** API-07; PROMPT anthropic_to_messages and Event model; CORE done record
- **Estimated size:** 450 lines of code; 450 lines of tests
- **Donor sources:** MAYA/serve/server.py:6674-6710 (_anthropic), 5250-5314 (anthropic_events), 5317-5343 (anthropic_collect), 6268-6282 (/v1/messages/count_tokens falls to 404); MAYA/serve/frontend.py:727-797 and 290-296 (conversion and budget-to-effort mapping, through the prompting planner)

**Behaviors to reproduce**

- Handler order: with_shared(anthropic), api tag 'anthropic', check_request, anthropic_to_messages, max_new = int(max_tokens or 0), prepare, carry the typed run options, start the client watcher, then stream or collect. The query string and the anthropic-version and anthropic-beta headers are ignored.
- Frames are 'event: <name>\ndata: <json>\n\n'. Keep-alives are ': keep-alive\n\n'. There is no ping event and no [DONE].
- message_start {type, message:{id:'msg_'+24 hex, type:'message', role:'assistant', model, content:[], stop_reason:null, stop_sequence:null, usage:{input_tokens: prompt length, output_tokens:0}}}.
- Block state machine: kinds reasoning→thinking, content→text, tool_start and tool_call→tool_use. Empty texts are skipped. A new block starts when the kind changes and for every tool block; the previous block is closed first with content_block_stop. content_block_start carries {type:'thinking', thinking:'', signature:''}, {type:'text', text:''} or {type:'tool_use', id, name, input:{}}. Deltas are thinking_delta, text_delta or input_json_delta: tool_args pieces go to the current index, and a whole tool_call gives one input_json_delta of its JSON-encoded arguments (ensure_ascii=False).
- At Done the open block is closed. message_delta {type, delta:{stop_reason, stop_sequence}, usage:{input_tokens: prompt minus reused (reused clamped to the prompt length), cache_read_input_tokens: reused, output_tokens}} is followed by message_stop. stop_reason is tool_use when a tool block was used and finish is stop; else stop_sequence when the done record has one; else stop and cancel map to end_turn and length to max_tokens.
- Mid-stream EngineDied or engine ERR writes 'event: error\ndata: {"type": "error", "error": {"type": "api_error", "message": ...}}\n\n'.
- The collector rebuilds the message: blocks in order, text and thinking concatenated, input_json pieces parsed at block stop ('{}' when empty), stop_reason, stop_sequence and usage updated from message_delta.
- Pre-stream errors keep maya's OpenAI-shaped body (parity; see open questions). POST /v1/messages/count_tokens returns 404 {error:{message:'not found'}}.

**Parity tests**

test_server.py UsageAndStatus.test_anthropic (1), ClientShapes.test_anthropic_mid_conversation_system (1, HTTP half), EngineDeath.test_engine_err_mid_stream (Anthropic path), QueuedKeepAlives (Anthropic path), ThinkingBudget Anthropic cases and MaxTokens Anthropic cases (jointly). About 8 methods plus new goldens.

**Definition of done**

Golden event transcripts for thinking then text, thinking then tool_use (streamed and whole), two consecutive tool calls (two blocks), stop_sequence, max_tokens and engine death match byte for byte. The collector output matches the JSON goldens.

<a id="api-10"></a>
### API-10 Resumable web-app streams and answers/*.jsonl

- **Milestone:** M4
- **Rust target:** console-http::resume
- **Platform:** platform-neutral
- **Risk:** medium. The job outlives its connection, so the run stream's RAII stop must only fire on cancel or completion, never on reader disconnect. The file format must stay byte-compatible so the Phase 1 dashboard reconnect works unchanged.
- **Depends on:** API-08; API-15 (config folder); MEDIA embeddings handle (explicit, replaces thread-local)
- **Estimated size:** 600 lines of code; 550 lines of tests
- **Donor sources:** MAYA/serve/server.py:5011-5016 (carry_embeddings), 5047-5119 (StreamJob), 5122-5201 (JOBS, JOB_KEEP_S, JOB_KEEP_N, JOBS_DIR, JOB_ID, RESTARTED, job_file, _jobs_forget, jobs_load, jobs_put), 6598-6606 (strata_resume branch), 6626-6672 (_stream_job, _job_get, _job_cancel), 7348-7350 (jobs_load at start)

**Behaviors to reproduce**

- A streamed chat completion with strata_resume exactly true becomes a job. Its id is the first chunk's chatcmpl id. The first chunk is pulled on the request task, then a spawned task drives the rest with the request's embeddings handle passed explicitly (the Rust form of carry_embeddings). No client watcher runs, so a dropped connection never cancels the job.
- The job keeps items in an append-only vector plus done, ended (epoch float), a reader count and a Notify. Heartbeat items are not stored. EngineDied is stored as the chunk {error:{type:'server_error',message:'<m>; the next request restarts it'}}, and any other failure as {error:{type:'server_error',message}}.
- Writing: the initial request and every GET /v1/strata/stream?id=<id>&from=<n> stream items from index n (from parsed as int, invalid means 0, negative means 0). A wait of 10 s with no new item and not done writes ': keep-alive'. When done and all items are written, 'data: [DONE]' follows. A reader write failure just ends that reader.
- An unknown id gives 404 {error:{message:'no such answer (finished more than a day ago, or the server restarted since)'}}. The route needs the key when one is set.
- POST /v1/strata/cancel runs the own_page guard ('answers can be stopped'), reads {id} (an invalid body means id ''), sets that job's cancel and returns 200 {cancelled: bool}.
- Registry: before inserting, finished jobs older than 86400 s are evicted, then the oldest finished jobs are dropped while at least 32 remain. A running job is never evicted. Eviction deletes the job's file.
- Persistence: when a config is present, files live in answers/ beside it, named '<id>.jsonl' only if id matches [A-Za-z0-9_-]{1,80}. Each chunk is written as one line (pyjson wire form). The file is flushed when more than 2 s have passed since the last flush and at the end. The last line is {"_done": <epoch float>}. A disk failure only stops the file.
- jobs_load at start creates the folder, deletes files older than 86400 s by mtime or with other names, and reads lines until an invalid line or _done. Without _done it appends {error:{type:'server_error',message:<restart note, rebranded>}} and uses the mtime as ended. It keeps the newest 32 by ended, deletes the rest, logs '<k> web-chat answer(s) of the last day kept for the page (answers/)' and returns the count.
- Without a config folder nothing is written to disk.

**Parity tests**

test_stream_jobs.py StreamJobs: test_an_unread_answer_runs_to_its_end, test_a_new_answer_never_cancels_a_running_unread_one, test_finished_answers_stay_a_day_and_the_oldest_go_first, test_running_answers_are_never_dropped_to_make_room. StreamJobFiles: test_a_finished_answer_survives_a_restart, test_an_answer_cut_by_a_stop_comes_back_with_a_note, test_old_files_and_strange_names_are_removed_and_eviction_deletes_the_file, test_without_a_folder_nothing_is_written (8). test_server.py TestCarryEmbeddings (1, re-expressed as 'the job task sees the request's embeddings handle'). Plus new HTTP tests for reconnect from an index, cancel, and the 404 message. The clock is injectable for the day and size limits.

**Definition of done**

All 9 maya methods pass as Rust tests. A kill-and-restart integration test (the server process killed mid-job, then started again) shows the restart note appended and the stream replayable. A reviewer can open a generated .jsonl and confirm one chunk per line plus the _done line.

<a id="api-11"></a>
### API-11 llama.cpp-compatible discovery and utility routes

- **Milestone:** M4
- **Rust target:** console-http::routes::llama
- **Platform:** platform-neutral
- **Risk:** low. /props exposes the chat template source. When a vendor-licensed template is supplied at run time (not vendored), exposing it to a local client is fine but must not be cached in fixtures.
- **Depends on:** API-03; PROMPT ChatTemplate (source, render_ids), tokenizer (encode parse_special, decode, special_ids.bos), effort kwargs; MEDIA media_of and picture token counts; ENGINE view (alive, unloaded, multi, model_path, info.version)
- **Estimated size:** 450 lines of code; 400 lines of tests
- **Donor sources:** MAYA/serve/server.py:6101-6131 (/v1/models, /models, /slots), 6299-6325 (_props), 6247-6255 (/api/tokens, /tokenize, /detokenize routing), 3704-3763 (chat_prompt, tokenize, detokenize, count_tokens)

**Behaviors to reproduce**

- /v1/models and /models need the key. They return {object:'list', data:[{id:model, object:'model', status:{value:'loaded'|'unloaded'}, meta:{n_ctx}, context_length, architecture:{input_modalities:['text'] or ['text','image'] or ['text','image','video'], output_modalities:['text']}}]}. data is [] when the engine is dead and not idle-unloaded, and checking does not restart a dead engine. There is no /v1/models/{id} route (404).
- /props[?model=] needs the key. A different model name gives 404 {error:{message:'model not found'}}. A dead engine that is not unloaded gives 503 {error:{message:'the engine is not running'}}. The body is {default_generation_settings:{n_ctx, params:{temperature, top_p, top_k, min_p, seed, repeat_penalty, presence_penalty, frequency_penalty, repeat_last_n (renamed from the merged sampling defaults plus shared), n_predict: shared max_tokens or -1}}, total_slots: max(1, multi), model_alias, chat_template:<template source>, modalities:{vision}, models_autoload:false, is_sleeping:false, model_path?, build_info? (rebranded), ablate}.
- /slots needs the key and returns [{id, n_ctx, is_processing}] for max(1, multi) slots. is_processing is busy when there is one slot, else i < active. It returns [] when not loaded.
- /tokenize: when messages are present it uses chat_prompt (template messages, tools including MCP tools when strata_mcp is true and a hub exists, the default effort kwargs unless the request names a level) and render_ids. Otherwise content or prompt must be a string ('tokenize needs content (or prompt) as a string, or messages' 400), encoded with parse_special unless that is exactly false, with BOS prefixed when add_special or add_special_tokens is truthy and a BOS exists. Returns {tokens, count, max_model_len}.
- /detokenize: tokens must be a list of non-negative non-bool integers ('detokenize needs tokens as a list of token ids' 400). Returns {content, prompt}.
- /api/tokens returns {tokens, images, approximate, max_context}. Media count as their markers, and approximate is true when there is any media. The engine-vision families' picture-token adjustment is delegated to the media planner's picture() when available.

**Parity tests**

test_server.py WebApp.test_model_discovery_and_props, test_build_model_path_and_slot_status and test_discovery_does_not_restart_a_dead_engine (3). test_dashboard.py Dashboard.test_token_count_matches_the_prompt and test_tokenize_and_detokenize (2). Key checks on these routes are in API-03.

**Definition of done**

All 5 maya methods pass. Golden JSON for /props, /slots and /v1/models in loaded, unloaded and dead states. Error messages match.

<a id="api-12"></a>
### API-12 Static dashboard routes and embedded assets

- **Milestone:** M8
- **Rust target:** console-http::routes::static_assets plus a console-http build step that embeds console/web
- **Platform:** platform-neutral
- **Risk:** low. Embedding the assets instead of reading them per request is listed as a deviation. The behaviour visible to clients is identical.
- **Depends on:** API-03; WEB adapted Phase 1 asset set under console/web
- **Estimated size:** 300 lines of code; 250 lines of tests
- **Donor sources:** MAYA/serve/server.py:5946-5988 (/fonts, /web redirect, /web/<name>), 6012-6018 (GET / index.html); MAYA/serve/web (asset set, adapted by the web planner)

**Behaviors to reproduce**

- GET '' (that is, '/') returns index.html with Content-Type text/html; charset=utf-8 and Content-Length. No key is needed.
- GET /web/<name>: no '/' or '\\' in the name, an extension in {.css: text/css; charset=utf-8, .js: text/javascript; charset=utf-8, .svg: image/svg+xml, .png: image/png, .webmanifest: application/manifest+json}, and the file must exist. It is served with Cache-Control: no-cache. Anything else, including /web/index.html, gets 404 JSON not found.
- GET /fonts/<name>: no separators, a .woff2 name and the file must exist. It is served as font/woff2 with Cache-Control: max-age=86400.
- GET /web and /web/ return 302 with Location './' or '../' (by whether the raw path ends in '/') plus the original query, and Content-Length 0.
- Assets are embedded at build time from console/web through a generated table (build.rs with include_bytes, no new crate). An optional dev override (CLI flag or env var) serves the same names from a disk directory with identical rules, so the front end can iterate without rebuilding.
- The asset list is tested to cover every file the adapted dashboard references by relative URL.

**Parity tests**

test_server.py WebApp.test_page_and_files, test_home_screen_start_url and test_only_the_app_files_are_served (3). New tests cover the embed-versus-disk override equivalence and path traversal attempts (/web/..%2f, backslashes, absolute names).

**Definition of done**

All 3 maya methods pass. Traversal tests pass. The binary serves the dashboard with no disk access to console/web, which is verified by running the test from a temp working directory.

<a id="api-13"></a>
### API-13 Dashboard admin routes: settings, thinking budget, port and report

- **Milestone:** M4
- **Rust target:** console-http::routes::admin
- **Platform:** platform-neutral
- **Risk:** medium. Rewriting run scripts and the run config must preserve unknown keys, their order and formatting, which is what RunConfigStore in API-15 provides. The exit-76 restart only means something with a launcher. Without one, the env var is unset and the port applies from the next start, as in maya.
- **Depends on:** API-03; API-04; API-15; MANAGE check_thinking_budget, default_thinking_budget and config_label (or this package ports maya_quants.check_thinking_budget if the manage planner does not); MCP status(); HOST telemetry snapshot; ENGINE info and log_path, and close_for_restart through the lifecycle (API-17)
- **Estimated size:** 750 lines of code; 600 lines of tests
- **Donor sources:** MAYA/serve/server.py:6003-6006 and 6419-6432 (/settings), 2571-2582 (set_shared persistence), 6054-6056 and 6191-6202 (/api/thinking-budget), 2831-2867 (think_budget_info, set_think_budget), 6057-6060 and 6354-6366 (/api/port), 2869-2929 (port_info, set_port, _restart_on_port, _save_port), 6078-6086 and 3181-3217 (/api/report, report), 158-159 (REPORT_LINES), 7368-7376 (shared settings load at start); MAYA/tools/maya_quants.py:158-165 (check_thinking_budget)

**Behaviors to reproduce**

- GET /settings returns {shared: bool, defaults}. POST /settings reads the body first, then runs the own_page guard ('settings can be changed'). It applies clean_shared_defaults on req.defaults (400 on error) and saves '<config stem>.shared-settings.json' with pyjson indent=1, or deletes the file when the result is empty; a failed write is only logged. It logs '[console] other apps now use the Chat settings: k=v, ...' or '... use their own settings again' and returns {shared, defaults}.
- GET /api/thinking-budget returns {budget, supported: think_end_id present, saved: config present, max_level? (when think_budget_max is non-zero)}. POST runs the own_page guard ('the thinking budget can be changed'). It accepts 0 or 256..262144, with maya_quants' validation messages. A model without an end-of-thinking token gives 400 'this model has no thinking budget'. On success it sets the budget and zeroes think_budget_max, writes thinking_budget and installer.thinking_budget_set=true into the run config atomically, logs the change, and returns {budget, supported:true, saved}.
- GET /api/port returns {port, host, restarts: restart env var set, saved: config present, restarting}. POST runs the own_page guard ('the port can be changed') and validates in order: 1024..65535; differs from the current port; a config exists; no move already running; and a test bind on the server's host (IPv6 when the host contains ':') succeeds. Each failure has maya's 400 message (rebranded). On success it writes 'port' to the run config atomically and rewrites every run-*.bat and run-*.sh beside the config whose bytes contain the config file name, replacing every '--port<ws>N' with the new port byte for byte (CRLF preserved); a per-file failure is only logged. When the restart env var is set it records port_restart, sleeps 0.5 s, takes the whole FIFO, closes the engine, vision and MCP for restart, and exits with code 76. It logs the outcome and returns 202 {port, restarts}.
- GET /api/report returns text/plain; charset=utf-8. Lines: the product and version with a 'report of YYYY-mm-dd HH:MM' header; System (OS and console version, see deviations); GPU and VRAM and CPU and RAM from the telemetry snapshot (with '?' or 'not readable' fallbacks); Model with label and context; 'Engine: k=v' sorted by key when INFO is present; 'Config: <name>: args ...; gpu ...; env {...}', where env values whose names contain key, token, secret or password (case-insensitive) become '***' and names are shown in their user-facing form. Then an empty line, a heading, and the last 150 lines from the final 2 MiB of the engine log that match the REPORT_LINES alternation (case-insensitive substring and the 'glm prefill: <digit>' form, implemented without the regex crate). It always ends with a newline.
- GET /mcp needs the key and returns the hub status, or {servers:[], tools:0} when there is no hub.

**Parity tests**

test_server.py SharedSettings (6 methods, HTTP halves; validation is in API-04). test_dashboard.py Port.test_saved_and_reported and test_refused_with_nothing_saved (2), Dashboard.test_report_leaves_secrets_out (1). New tests cover the run-script rewrite (.sh and CRLF .bat, scripts naming another config left alone), the pyjson file format of the shared-settings and run-config writes, and the exit-76 path (spawned binary with the restart env var set).

**Definition of done**

All listed maya methods pass. File-format goldens for the shared-settings and run-config rewrites match the Python indent=1 output recorded in the tests. The report test shows secrets masked and log filtering applied.

<a id="api-14"></a>
### API-14 Context reload route and the delegated dashboard route shells

- **Milestone:** M4
- **Rust target:** console-http::routes::admin_delegated
- **Platform:** platform-neutral
- **Risk:** medium. Ownership overlap with the manage, engine and attachment planners. The lead must assign the handler shells either here or there, never both. The reload state machine crosses the FIFO and the engine lifecycle.
- **Depends on:** API-03; API-15; ENGINE restart_with_context, multi and info (kv_*, vram_*), load_s; CORE FIFO acquire-all and set_capacity; MANAGE context_range, settings_of, turbo_info/set_turbo, models_info/switch_model/delete_model/delete_leftover/model_settings, savings report/reset/set_price, updater check/start; ATTACH extract and MAX_BYTES; HOST RAM figures
- **Estimated size:** 600 lines of code; 500 lines of tests
- **Donor sources:** MAYA/serve/server.py:6050-6053 and 6340-6352 (/api/context), 2721-2821 (reloading, context_limits, set_context, _restart_with, _reload, _save_context), 6061-6077 and 6203-6240 (GET /api/turbo, /api/models, /api/savings, /api/update; POST /api/update, /api/turbo, /api/models/*, /api/savings/reset, /api/savings/prices), 6368-6417 (_models, _turbo, _update), 6179-6181 and 6434-6461 (/attach and /pdf)

**Behaviors to reproduce**

- GET /api/context returns {context, <manage planner's context_range fields: min, max, ...>, kv_gb, kv_ctx, kv_resident (or 0), kv_ram_gb (sum of engine vram kv_ram in GiB with 3 decimals, or null), ram_gb and ram_free_gb only when kv_ram is non-zero and the host sampler gives RAM, vram_gb, vram_slots, reload (a copy or null), load_s}.
- POST /api/context reads the body, runs the own_page guard ('the context size can be changed') and parses max_context as int (400 on failure). Out of range gives 400 'the context must be between A and B tokens', and a reload already waiting or running gives 400 'the model is already reloading'. Otherwise it sets reload {state:'waiting', from, to, started, error:null}, spawns the reload and returns 202 {reload}. The reload takes the whole FIFO, sets the state to 'running', calls the engine planner's restart_with_context(n), and on failure restarts with the old context and builds maya's error strings. It resets FIFO capacity to the engine's multi, and on success saves --max-context into the run config args (replacing the value or appending the pair) after recording installer.as_set_up through the manage planner's settings_of when absent. It ends with state 'done' or 'failed', plus error, ended and context. The mock engine sleeps for the mock-reload env var (default 2 s) and then sets max_context.
- Delegated shells, keeping maya's guards and status codes and calling manage-planner traits. GET /api/turbo, /api/models, /api/savings (fallback {usd:null, models:[]}) and /api/update (force when the raw path contains 'force=1'). POST /api/turbo: own_page ('Turbo can be switched'); the body must be {on: bool}, else 400 'send {"on": true} or {"on": false}'; returns 202 when restarting_now, else 200. POST /api/models/{settings,switch,delete,leftovers}: own_page ('models can be changed'); the body must be an object; returns 200 for delete or leftovers when the result is not deleting, or for settings with dry_run, else 202. POST /api/savings/reset: own_page; 400 'nothing is counted here' without a ledger; 200 report. POST /api/savings/prices: own_page; body object; 200 report. POST /api/update: own_page ('an update can be started'); 202 {update: state}; ValueError gives 400.
- POST /attach and /pdf: read the body first, run the attach guard (octet-stream or pdf content type, origin rule), and check the attachment size limit (413 with maya's message). The name comes from X-File-Name, percent-decoded and cut to 255 characters, defaulting to 'file.pdf' or 'file'. It calls the attachment planner's extract(name, bytes, want_images, text_limit, text_only) and returns 200 with its JSON.
- The reloading() and updater-busy predicates feed the API-07 gate and /health.

**Parity tests**

test_dashboard.py Dashboard.test_context_range and test_deepseek_context_range (route halves; ranges are manage's), test_reload_changes_the_context_and_saves_it, test_out_of_range_and_foreign_pages_are_refused (4), ContextCost.test_set_context_rewrites_the_command (1). test_turbo.py TurboServer (2, route halves). test_server.py FailedRestartKeepsContext.test_failed_restart (1, jointly with the engine planner). The attach shell's guard tests are re-expressed here and the extraction tests stay with the attachment planner.

**Definition of done**

All listed maya methods pass with fake manage and engine traits. A route table test shows each delegated route's guard and status-code rules. The reload test shows 503 on inference routes while a reload is waiting or running, the 'done' and 'failed' end states, and --max-context saved.

<a id="api-15"></a>
### API-15 Run config store, environment variables and settings

- **Milestone:** M1
- **Rust target:** console-core::config (RunConfigStore, EnvSettings)
- **Platform:** platform-neutral
- **Risk:** low. Env tests mutate process-global state. Tests take an injected env map instead of touching std::env, and only the binary reads the real environment.
- **Depends on:** API-01
- **Estimated size:** 650 lines of code; 500 lines of tests
- **Donor sources:** MAYA/serve/server.py:395-409 and 599-621 (queue ping, fair slice, model_management_setting, loop_guard_setting), 5347-5372, 6737-6755 (SERVER_ENV, apply_server_env), 6857-6960 (checked_config_effort call site, sampling_defaults_from_config), 7139-7166 and 7327-7333 (api key sources, cors, host), 7153-7154 (BOM-tolerant load); MAYA/tools/maya_names.py:1-78; MAYA/serve/response_config.py:4-14; MAYA/docs/SETTINGS.md:206-217

**Behaviors to reproduce**

- Load the run config as a UTF-8 JSON object with a tolerated BOM, keeping key order and unknown keys (preserve_order Value plus typed accessors).
- Atomic rewrite: mutate the Value, write '<name>.tmp' with pyjson indent=1 (ensure_ascii), then rename. Every subsystem that edits the run config uses this one writer.
- Environment variable names use one renamed prefix (see deviations). There is one EnvSettings struct with every variable maya reads and its exact default, minimum and parsing rule: API key; backlog 256 (min 5); body MiB 256; request timeout 300; queue ping 2.0 (min 0.01); fair slice 0; engine stall 90 (0 = off); request quiet 900; drain 60 (min 1); engine quit 50; engine wrap 40 (0 = cut at once); loop guard (0/off/false/no/none = off); model management (1/on/true/yes); server log (path, or 0/off/no/false/none = terminal only); debug; prompt memo (1, 0, verify); turn trace; think reserve 1024; restore points 4 and tail 512; keep-thinking; video max frames 240; restart-on-update; update check; pack template; pull command (test hook); mock tok/s; mock reload seconds; and the Responses store and job limits as an opaque list owned by the Responses planner.
- Config 'env' entries named in the SERVER_ENV list are exported into the process environment before start, and the backlog and watchdog values are re-read afterwards. Other entries pass to the engine's child environment (engine planner).
- model_management and loop_guard: when the env var is set and non-blank it wins, else the config key. API key: CLI, then env, then config. cors_origins: None or '' means none; otherwise it must be a list of non-blank strings, trailing '/' stripped, else start-up aborts with 'config: "cors_origins" must be a list of origins like ...'. fit_max_tokens: CLI flag, or config true. idle_unload_s: CLI, else config, minimum 0. host: CLI, else config host, else 127.0.0.1.
- Every setting is documented in specs/022 with its maya name, the new name and the default.

**Parity tests**

test_server.py StallWatchdog.test_the_config_env_reaches_the_server (1), CorsOptIn.test_the_config_value (1), ModelManagement.test_on_unless_the_config_turns_it_off (1), RequestBodies.test_the_listen_backlog (1, with API-02). New unit tests cover each env var's default, minimum and invalid input, the BOM, and the order-preserving round trip.

**Definition of done**

A settings table in specs/022 lists every maya env var and run-config key in this subsystem with its new name, and a test asserts the table and EnvSettings agree. A round-trip test proves an untouched config is rewritten byte-identical to Python's indent=1 output for a fixture containing non-ASCII, floats and nested objects.

<a id="api-16"></a>
### API-16 Logging, signals and parent watch

- **Milestone:** M4
- **Rust target:** pulsar-console (lib target) ::logging and ::signals
- **Platform:** platform-neutral
- **Risk:** low. Local time formatting needs libc localtime_r on unix. The Windows equivalents are in API-18.
- **Depends on:** API-15
- **Estimated size:** 550 lines of code; 450 lines of tests
- **New dependencies:** tokio feature signal; libc
- **Donor sources:** MAYA/serve/server.py:6963-7041 (request_stop, wait_for_stop, stop_signals, watch_parent), 7044-7112 (ServerLogTee, StampedStdout, tee_server_log), 7155-7163 (log setup order)

**Behaviors to reproduce**

- The server's own lines start with '[console]' (rebranded '[maya]'). A line-start-aware writer stamps local 'HH:MM:SS ' only before such lines, however the line is written in pieces. Engine lines and indented '[console]' text pass through unstamped.
- Log tee: when the server-log env var is unset, the config 'log' path is used. When the value is not in {'', 0, off, no, false, none} the file is opened for append, line-buffered, and the line '[console] this server's lines go to <abs path> too' is printed. A failure to open prints maya's 'cannot also go to' line and keeps terminal output. A write failure to the file never affects terminal output.
- request_stop(why) sets the stop flag once and prints '[console] stopping (<why>): the engine ends'. Later calls do nothing.
- Signals: SIGTERM, SIGINT and SIGHUP request a stop with the signal name. A signal whose current disposition is SIG_IGN (for example under nohup) is left ignored, checked through sigaction. While stopping, a second SIGINT means 'stop at once' (exit 130) and other signals are ignored.
- Parent watch (--parent-pipe): one task reads stdin to EOF and then stops with 'the program that started it ended'. On POSIX another task polls the parent pid every 1 s and stops with 'its parent process ended' when it changes. Without --parent-pipe, closing stdin changes nothing.
- The main wait does not depend on a lock a signal handler could contend. In Rust this is a tokio select over the signal streams and stop sources.

**Parity tests**

test_server.py StampedLog.test_only_maya_lines_get_a_time (1). test_stop.py WatchParent.test_eof_on_the_pipe_stops, test_a_new_parent_stops, test_stop_once, test_the_main_wait_never_holds_the_events_lock and test_a_signal_handler_stops_the_main_wait (5), re-expressed with injectable stdin, getppid and signal sources.

**Definition of done**

All 6 maya methods pass. A spawned-binary test shows SIGHUP under an inherited SIG_IGN is ignored, and the double SIGINT gives exit 130.

<a id="api-17"></a>
### API-17 pulsar-console binary: CLI, start-up assembly and graceful shutdown

- **Milestone:** M4
- **Rust target:** pulsar-console (bin plus lib)
- **Platform:** platform-neutral
- **Risk:** high. This is the integration point for every subsystem. Its start-up order affects user-visible errors (the port check before the model load, MCP failing fast). The shutdown order is subtle: QUIT goes only after the cut request has read its last lines. It depends on the engine planner's fake engine binary.
- **Depends on:** API-02; API-03; API-06; API-07; API-08; API-09; API-10; API-11; API-12; API-13; API-14; API-15; API-16; ENGINE MockEngine, line-protocol engine, wrap/stop/close, fake engine binaries; PROMPT tokenizer loading and template loading; MCP hub_from_config/start/close; MANAGE savings ledger, finish_delete, model defaults; HOST RAM total
- **Estimated size:** 900 lines of code; 550 lines of tests
- **Donor sources:** MAYA/serve/server.py:7115-7452 (main), 6758-6794 (warn_tight_ram, lan_addresses), 6797-6803 (serve), 7414-7452 (shutdown), 1702-1728 (wrap and stop semantics used at shutdown); MAYA/serve/update.py:20 (RESTART_EXIT=76); MAYA/serve/test_stop.py:1-140 (fake config and process helpers)

**Behaviors to reproduce**

- The CLI follows argparse conventions: long options, --opt=value form, unique-prefix abbreviations, repeatable --script, usage errors exit 2 with 'usage: ...' and 'error: ...' on stderr, and --help. The options are --engine {mock, line} (default mock; see deviations for the maya and strata names), --config, --host, --port (default 8095), --script, --gpu, --tokenizer, --open, --idle-unload SECONDS, --fit-max-tokens, --api-key (default from env), --mcp-config, --parent-pipe and a dev flag for the asset directory.
- Start-up order follows maya. Alias the env, load the config, export SERVER_ENV, stamp stdout, tee the log, apply --gpu to the config, resolve the host, then probe the port and fail with argparse error 'port N is already in use - ...' before any model load. Next: tokenizer (byte tokenizer for mock when vocab.json is absent; the line engine requires it), MCP hub from config (fails fast), chat template, configured effort check, engine construction (MockEngine with scripts, default script, and mock tok/s env; or the line-protocol engine, which requires --config), sampling defaults (config, else model defaults, plus ablate default), service build, FIFO capacity from multi, default effort log, thinking budget, idle unload, model-management and loop-guard logs, API key, CORS log, savings ledger and finish-delete when a config is present, jobs_load, trained context and model dir, shared settings load, MCP start, serve, idle-unload start.
- The ready line is exact: 'ready: http://<here>:<port>/v1  (OpenAI: /v1/chat/completions, /v1/responses, Anthropic: /v1/messages, context N tokens[, images on][, API key required])' followed by the browser hint line. here is 127.0.0.1 for 0.0.0.0, '' or '::'. A synthetic-backend marker is added (deviation).
- Non-loopback host: print the LAN addresses (the default-route address found by connecting a UDP socket, which sends nothing, plus getaddrinfo(hostname) for AF_INET, excluding 127.*, 169.254.* and 0.*), the no-API-key WARNING and the Windows firewall hint on Windows only.
- --open launches the platform opener with the local URL once ready.
- Shutdown on stop: stop accepting; set stopping so queued requests are refused; if the wrap time (from the engine-wrap env var) is above 0, the engine supports wrap and a request is busy, send WRAP and wait up to that time to acquire the whole FIFO; otherwise or on timeout, STOP and wait for the FIFO. Then close the engine (QUIT, and the engine-quit timeout is the engine planner's), vision and the MCP hub. Exit 0. A second Ctrl+C during this exits 130 with '[console] stopped at once: ...'.
- warn_tight_ram: when INFO arena_mib is present and the host's total RAM minus the arena is under 6 GiB, print maya's warning with the platform-specific clause.
- Exit code 76 is reserved for restarts requested by the admin routes (API-13, API-14 and the manage planner).

**Parity tests**

test_stop.py ServerStops.test_old_engine_name (re-expressed for the renamed engine flag and the accepted alias), test_parent_pipe_closed, test_stdin_closed_without_parent_pipe_changes_nothing, test_sigterm and test_sighup (5), using the spawned binary and the engine planner's fake engine process. The binary asserts '[console] stopping (<why>): the engine ends', exit 0 and no orphaned engine process (checked by enumerating child pids with libc or ps). New spawned-binary tests cover the port-in-use error, the ready line, the --api-key env default, and the wrap-then-QUIT order shown in the fake engine's transcript.

**Definition of done**

All 5 ServerStops methods pass on macOS and Linux runners. A reviewer can read a start-up sequence test that asserts the exact order of log lines for the mock engine and for the line engine with a fake engine. A shutdown transcript test shows WRAP, then DONE or STOP, then QUIT in that order.

<a id="api-18"></a>
### API-18 Windows-specific lifecycle and transport shims (unverified on hardware)

- **Milestone:** M9
- **Rust target:** pulsar-console::platform::windows and console-http::transport (cfg(windows) branches)
- **Platform:** hardware-or-os-specific
- **Risk:** medium. It cannot be run in this program's CI. The type check for the Windows target needs that target's standard library installed in the workflow (rustup target add). If the owner does not want that, the code stays behind cfg with a documented 'not compiled in CI' label.
- **Depends on:** API-02; API-16; API-17
- **Estimated size:** 250 lines of code; 120 lines of tests
- **Donor sources:** MAYA/serve/server.py:6716-6718 (allow_reuse_address false on Windows), 6991 (SIGBREAK), 7007-7020 (PeekNamedPipe parent-pipe polling, ERROR_BROKEN_PIPE 109), 7032-7033 (no parent-pid watch on Windows), 7401-7405 (firewall hint), 6442 (read the body before refusing: Windows reset workaround), 6773-6774 (Windows RAM-warning clause)

**Behaviors to reproduce**

- On Windows the listener does not set SO_REUSEADDR (and uses exclusive address use), so a second server on the same port fails loudly.
- Ctrl+Break (SIGBREAK) requests a stop like SIGINT, through the Windows console control handler.
- The parent-pipe watch on Windows polls PeekNamedPipe every 0.25 s, drains the available bytes, and treats ERROR_BROKEN_PIPE (109) as the parent ending. It never blocks on a read of stdin. There is no parent-pid watch.
- Firewall hint text is printed on non-loopback binds, with maya's command line (product name rebranded).
- Refusal paths that answer before reading the body (attach, own_page routes) read the body first on every platform. This is a no-op cost elsewhere and keeps the Windows reset workaround.
- OS randomness and local-time helpers have Windows implementations (raw extern calls, no new crate).

**Parity tests**

There are no GPU-free maya tests for these paths: test_stop.py WindowsJob is launcher scope and skipped off Windows. Unit tests run under cfg(windows) only. On macOS and Linux CI the package is checked with 'cargo check --target x86_64-pc-windows-msvc' (no link step), and every item is labelled unverified on Windows in the ledger.

**Definition of done**

The code compiles for x86_64-pc-windows-msvc in CI with cargo check. Every behaviour is listed in the ledger as 'ported, unverified on Windows'. No Windows API is used outside this module.

<a id="api-19"></a>
### API-19 HTTP test kit and parity ledger

- **Milestone:** M1
- **Rust target:** console-testkit (dev-dependency crate) and console/parity/ (ledger data)
- **Platform:** platform-neutral
- **Risk:** low. The ledger is the anti-drop mechanism. Its maya ids are typed in by hand from the pinned commit and must be reviewed against the files once, by the reviewer reading MAYA as data.
- **Depends on:** API-02; ENGINE MockEngine and fake engine binary; PROMPT byte tokenizer and test template fixture
- **Estimated size:** 700 lines of code; 300 lines of tests
- **Donor sources:** MAYA/serve/test_server.py:31-35 (RecordingEngine), 1869-1883 (ClockedEngine), the GoneClients HeldEngine and raw helpers at 2037-2070 and 2364-2475, and the WebApp get helper at 1671-1692; MAYA/serve/test_logprobs.py:35-52 and 160-192 (LpEngine, Http base); MAYA/serve/test_stop.py:1-140 (Proc, fake_config, free_port)

**Behaviors to reproduce**

- The raw client writes arbitrary request bytes, reads to EOF or until a marker or timeout, and parses status, headers and body.
- An SSE parser splits data and event frames and comment keep-alives, keeping raw bytes for golden comparison.
- TestServer::builder() starts an in-process server on port 0 with a chosen fake engine, the byte tokenizer, the test chat template fixture, an optional API key, CORS, config folder and an injected clock and env.
- Fake engines wrap the engine planner's MockEngine: Recording (last max_new and sampling), Held (blocks until released, counts calls), Clocked (reports engine timings), Lp (logprobs INFO and lines) and Dying (dies mid-stream or sends ERR).
- A process helper spawns the pulsar-console binary with a temporary config pointing at the engine planner's fake engine binary, waits for 'ready:', sends signals and reaps.
- The parity ledger (console/parity/serve-api.tsv) has one row per maya test method in this subsystem's scope: file, class, method, owning package, Rust test path, and status (ported, joint-with:<subsystem>, deviation:<id>, out-of-scope:<subsystem>). A Rust test asserts that every Rust test path named in the ledger exists (through a generated list) and that the ledger has no duplicate maya ids.

**Parity tests**

No maya methods of its own. It enables the roughly 125 in-scope methods. The initial ledger lists all 244 methods of the eight files assigned to the API reader plus the test_dashboard.py methods touching these routes, each attributed to a package or to another subsystem.

**Definition of done**

The kit is used by at least API-02 and API-03 tests. The ledger covers every test method in test_server.py, test_stream_jobs.py, test_stop.py (WatchParent and ServerStops; the others marked launcher), test_logprobs.py, test_multi.py, test_fair.py, test_turbo.py, test_detok.py and the related test_dashboard.py methods, with an owner for each. A reviewer can reproduce the method count with grep against MAYA.

<a id="api-20"></a>
### API-20 HTTP API contract documents and route inventory gate

- **Milestone:** M4
- **Rust target:** specs/022-*/contracts/http/ (Markdown plus JSON Schema per route) and a console-http test
- **Platform:** platform-neutral
- **Risk:** low. Documentation drifts unless gated. The inventory test is the gate.
- **Depends on:** API-03; API-06; API-08; API-09; API-10; API-11; API-12; API-13; API-14; WEB route inventory of the adapted dashboard
- **Estimated size:** 300 lines of code; 200 lines of tests
- **Donor sources:** All routes above; MAYA/serve/web/*.js route references (the dashboard's call list); READERS maya-api.json contracts

**Behaviors to reproduce**

- One contract file per route group: inference dialects, SSE grammars, resumable streams, monitoring, llama.cpp utilities, static, admin, errors and headers, auth/CORS/cross-site, and the CLI and env settings table. Each states the request fields read, the response shape with key order, status codes and error messages, and marks the deviations.
- A separate UI-to-server contract index lists exactly the routes and fields the Phase 1 dashboard uses (from the web planner's inventory), as the stable target for the Phase 2 Rust/WebAssembly front end.
- A route inventory test asserts that the router's registered (method, path pattern) set equals the inventory in the contract index, so no route can be added or dropped silently. JSON Schemas are checked against the golden responses produced by API-06, API-08, API-09 and API-11 using a small in-house validator for the needed subset, or by structural tests if the Responses planner's schema validator is available.

**Parity tests**

No maya methods. It documents the behaviour the other packages' tests define.

**Definition of done**

Every route in the router appears in the contract index and the reverse. Every deviation id appears in the contract where it applies. A reviewer can follow any route from contract to handler to tests.
