"""Admission records for Mahdi's explicit Studio017 local operator authorization."""

from studio017_guard import MODEL, STATE, cmd, digest, enc, hexid, need, parse, path, read, sha

MODE = "operator-supervised"
AMENDMENT = "9bb8d3d996c5475e420ed558dcee9f3ca1c52e96c622382d84d8fe7c121dc41f"
RUN = "6855f3a4414e4dc31a5bcd7dbbd5d173b4656ac6fdf9cf2fd00eaa2027124f98"
INPUT = "34e68b0c293990cde58d6ac21fadeda806cf16c1ce2db1f293b84afed77b83b8"
CRITERIA = "e3b323b2de50ee683c790046551ff2bd7a731e3c17d602d155cef318233326c7"
RESOURCES = "66003e80f02499306151d34e6e26c3ec418e139c65caccb01bae837b60e36140"
VERDICT = "ACCEPT_OPERATOR_SUPERVISED_GOLDEN_TOKEN_EXPERIMENT"
BRANCH = "codex/studio017-full-flash-golden-token"
WORKFLOW = ".github/workflows/macos.yml"
REQUIRED_JOBS = ("Classify committed change", "Apple Silicon workspace baseline",
                 "Apple MLX small-fixture validation", "CI aggregate status")


def original(row, limit=16 << 20):
    """Hash and return the very same bounded read from the canonical file."""
    need(set(row) == {"path", "sha256"}, "original artifact fields")
    raw = read(path(row["path"]), limit)
    need(sha(raw) == hexid(row["sha256"], 64), "changed original artifact")
    return raw


def validate_config(c):
    need(c["schema"] == "studio017-operator-config/1" and c["mode"] == MODE and
         c["run"] == RUN, "explicit operator configuration or run")
    amendment = c["artifacts"]["operator-amendment"]
    need(amendment["sha256"] == AMENDMENT and sha(original(amendment)) == AMENDMENT,
         "different operator amendment")
    for key, expected in (("input", INPUT), ("criteria", CRITERIA), ("resource", RESOURCES)):
        need(digest(c[key]) == expected, "changed frozen operator " + key)


def _run(run, head, attempt):
    need(type(run["id"]) is int and run["id"] > 0 and run["head_sha"] == head and
         run["event"] == "push" and run["head_branch"] == BRANCH and run["path"] == WORKFLOW and
         run["status"] == "completed" and type(run["run_attempt"]) is int and
         run["run_attempt"] == attempt, "wrong ordinary CI run or attempt")


def _jobs(run, listing):
    jobs = listing["jobs"]
    need(len(jobs) == listing["total_count"] and 0 < len(jobs) <= 100 and
         len({j["id"] for j in jobs}) == len({j["name"] for j in jobs}) == len(jobs),
         "incomplete or duplicate CI jobs")
    for job in jobs:
        need(job["run_id"] == run["id"] and job["head_sha"] == run["head_sha"] and
             job["run_attempt"] == run["run_attempt"] and job["status"] == "completed",
             "CI job identity")
    return jobs


def summarize_infra(head, run, jobs, annotations):
    """Return the failed job IDs for which a failed-jobs-only retry has evidence."""
    _run(run, head, run["run_attempt"])
    need(run["conclusion"] in ("cancelled", "failure"), "original CI was not failed or cancelled")
    population = _jobs(run, jobs)
    roots = []
    aggregate = None
    for job in population:
        if job["conclusion"] in ("success", "skipped", "neutral"):
            continue
        need(job["conclusion"] in ("cancelled", "failure"), "unclassified CI failure")
        logs = annotations.get(str(job["id"]), [])
        need(isinstance(logs, list) and len(logs) <= 100, "bounded original CI annotations")
        messages = [x["message"].lower() for x in logs]
        unacquired = not job["runner_id"] and not job["steps"] and any(
            "not acquired by runner" in m or "capacity constraints" in m for m in messages)
        service_failure = any("lost communication with the server" in m or
                              "runner has received a shutdown signal" in m or
                              "github actions service encountered an internal error" in m for m in messages)
        failed = [step["name"] for step in job["steps"] if step["conclusion"] == "failure"]
        if unacquired or (service_failure and not failed):
            roots.append(job["id"])
        elif job["name"] == "CI aggregate status" and failed == ["Enforce selected mode result"]:
            aggregate = job["id"]
        else:
            raise ValueError("CI failure lacks independent infrastructure diagnosis: " + job["name"])
    need(bool(roots), "no diagnosed infrastructure failure")
    allowed = set(map(str, roots)) | ({str(aggregate)} if aggregate is not None else set())
    need(set(annotations) <= allowed, "annotation belongs to another job")
    return sorted(roots)


def retry_intent(head, run_row, jobs_row, annotation_rows, operation):
    run = parse(original(run_row))
    jobs = parse(original(jobs_row))
    notes = {key: parse(original(row)) for key, row in annotation_rows.items()}
    job_ids = summarize_infra(head, run, jobs, notes)
    need(1 <= run["run_attempt"] <= 2, "no further CI retry")
    return dict(schema="studio017-ci-retry/1", head=head, run_id=run["id"], from_attempt=run["run_attempt"],
                job_ids=job_ids, run_sha256=run_row["sha256"], jobs_sha256=jobs_row["sha256"],
                annotation_sha256={key: row["sha256"] for key, row in annotation_rows.items()},
                operation=hexid(operation, 32))


def validate_ci(c, ci, live=False):
    head = c["source"]["head"]
    chain = parse(original(c["artifacts"]["ci-attempts"]))
    rows = chain["attempts"]
    need(chain["schema"] == "studio017-operator-ci/1" and 1 <= len(rows) <= 3, "CI attempt population")
    latest = {}
    operations = set()
    for number, item in enumerate(rows, 1):
        run = parse(original(item["run"]))
        _run(run, head, number)
        need(run["id"] == ci["id"], "different CI run in attempt chain")
        jobs = _jobs(run, parse(original(item["jobs"])))
        for job in jobs:
            latest[job["name"]] = job
        if number < len(rows):
            stated = parse(original(item["retry_intent"]))
            expected = retry_intent(head, item["run"], item["jobs"], item["annotations"], stated["operation"])
            need(stated == expected and stated["operation"] not in operations, "original CI retry authorization")
            operations.add(stated["operation"])
        else:
            need(run == ci and run["conclusion"] == "success" and not item["annotations"] and
                 item["retry_intent"] is None, "successful original CI attempt")
    for name in REQUIRED_JOBS:
        job = latest.get(name)
        need(job and job["conclusion"] == "success" and (job["runner_id"] or 0) > 0 and
             any(s["conclusion"] == "success" for s in job["steps"]), "required CI job: " + name)
    if live:
        url = "repos/MahdiHedhli/PulsarMLX/actions/runs/%d/attempts/%d" % (ci["id"], len(rows))
        actual = parse(cmd(["/opt/homebrew/bin/gh", "api", "--method", "GET", url], timeout=40))
        _run(actual, head, len(rows))
        need(actual["id"] == ci["id"] and actual["conclusion"] == "success", "live exact ordinary CI")


def _decision(raw):
    text = raw.strip()
    if text.startswith(b"```json\n") and text.endswith(b"\n```"):
        text = text[8:-4]
    return parse(text)


def validate_review(c, rev, control):
    files = c["artifacts"]
    raw_report = original(files["operator-provider-report"])
    stream = original(files["operator-provider-stream"], 32 << 20)
    verified = parse(original(files["operator-review-verification"]))
    disposition = parse(original(files["operator-review-exceptions"]))
    report = _decision(raw_report)
    head, tree = c["source"]["head"], c["source"]["tree"]
    for record in (report, verified, disposition):
        need((record["head"], record["tree"], record["amendment_sha256"]) == (head, tree, AMENDMENT),
             "review does not cover this amended source")
    need(report["run"] == verified["run"] == RUN and report["verdict"] == VERDICT and
         report["strict_deployment"] == "NOT_ESTABLISHED" and
         all(report[key] is True for key in ("method_accepted", "reference_independence_accepted",
                                             "lifecycle_resource_accepted")) and
         report["unresolved_blockers"] == [] and report["missing_coverage"] == [] and
         isinstance(report["exceptions"], list) and disposition["exceptions"] == report["exceptions"],
         "affirmative operator source, science, lifecycle and resource review")
    bindings = dict(input_sha256=INPUT, criteria_sha256=CRITERIA, resource_sha256=RESOURCES,
                    checkpoint_sha256=digest(path(c["checkpoint"]) / "receipt.json"),
                    runtime_sha256=c["controls_runtime_sha256"],
                    python_policy_sha256=files["python-policy"]["sha256"],
                    controls_sha256=digest(c["controls"]), lifecycle_sha256=files["operator-lifecycle"]["sha256"],
                    native_binary_sha256=digest(c["stages"]["native"]["program"]))
    named = report.get("bindings")
    declared_sha = report.get("bindings_sha256")
    need((named is not None or declared_sha is not None) and
         (named is None or named == bindings) and
         (declared_sha is None or declared_sha == sha(enc(bindings))),
         "reviewed build, runtime, control and scientific inputs")
    model = rev["actual_model"]
    need(model in ("claude-fable-5-2", "gemini-4-carbon", "gemini-4-astra") and
         verified["actual_models"] == [model] and verified["terminal_success"] is True and
         verified["request_id"] == rev["request_id"] and bool(rev["request_id"]) and
         sha(raw_report) == verified["original_report_sha256"] == rev["original_report_sha256"] and
         sha(stream) == verified["original_provider_stream_sha256"] == rev["original_provider_stream_sha256"],
         "original reviewer identity and decision bytes")
    # The normalized decision is also bound to the actual provider return. The separate
    # verification receipt covers route/selector and tools against the complete source.
    if model == "claude-fable-5-2":
        terminals = []
        models = set()
        for line in stream.splitlines():
            event = parse(line)
            if event.get("type") == "assistant":
                models.add(event["message"]["model"])
            elif event.get("type") == "result":
                terminals.append(event)
        need(len(terminals) == 1 and models == {model}, "single eligible reviewer session")
        end = terminals[0]
        need(end["session_id"] == verified["session"] and end["uuid"] == rev["request_id"] and
             end["subtype"] == "success" and end["is_error"] is False and
             end["result"].encode().strip() == raw_report.strip() and
             verified["eligible_route"] == ["claude.ai", "firstParty"], "authenticated original Fable decision")
    # Gemini uses the independently verified approved provider's terminal/selector receipt.
    # Its report and full provider output have the same byte bindings above.
    need(control["head"] == head, "controls belong to a different reviewed source")


def validate_lifecycle(c, rev, control):
    validate_review(c, rev, control)
    proof = parse(original(c["artifacts"]["operator-lifecycle"]))
    need(proof["schema"] == "studio017-operator-lifecycle/1" and
         (proof["head"], proof["tree"]) == (c["source"]["head"], c["source"]["tree"]) and
         proof["runtime_sha256"] == c["controls_runtime_sha256"] == control["runtime_sha256"] and
         proof["resource_sha256"] == digest(c["resource"]) == RESOURCES and
         proof["python_policy_sha256"] == c["artifacts"]["python-policy"]["sha256"] ==
         control["python_policy_sha256"], "lifecycle evidence identity")
    records = proof["originals"]
    decoded = {key: parse(original(records[key])) for key in
               ("monitor", "monitor-intent", "ack", "reap", "kernel-exit", "guardian",
                "watchdog-exit", "image-owner", "admission")}
    mon, intent, ack, reap = [decoded[k] for k in ("monitor", "monitor-intent", "ack", "reap")]
    need(intent["source"] == c["source"] and intent["resource_sha256"] == RESOURCES and
         intent["build_root"] == c["build_root"] and intent["synthetic_witness_count"] == 23 and
         mon["clean_reap"] is True and mon["helper_limit_seconds"] == 20 and 0 < mon["reply_seconds"] < 20 and
         [i["source_checked"] for i in mon["intervals"]] == [False, True] and
         all(0 < i["seconds"] < 20 for i in mon["intervals"]) and
         ack["operation"] == mon["operation"] == reap["operation"] and ack["status"] == "passed" and
         ack["production_stage_rejected_fixture"] is True and ack["real_grant"] is False and
         reap["clean_reap"] is True and reap["residual"] is False and reap["exit"] == 0,
         "original monitor, admission and reap control")
    death, guard, watchdog = [decoded[k] for k in ("kernel-exit", "guardian", "watchdog-exit")]
    need(death["owner_status"] == -9 and death["owner"] == guard["owner_pid"] and
         set(death["registered_exit_events"]) == {guard["watcher_pid"], guard["worker_pgid"]} and
         guard["watcher_pid"] != guard["worker_pgid"] and watchdog["exit"] == 0 and
         watchdog["source_unchanged"] is True and watchdog["claims_absent"] is True,
         "original owner-loss and kernel exit evidence")
    images = decoded["image-owner"]
    need(images["source"] == c["source"] and len(images["refusals"]) >= 10 and
         all(k in images["refusals"] for k in ("absent", "wrong-pid", "wrong-tree", "changed-image")),
         "original owner loader controls")
    need(b"PASS: sandbox blocked forbidden contents" in original(records["sandbox"]), "sandbox isolation control")
    entry = decoded["admission"]
    need(entry["head"] == c["source"]["head"] and entry["tree"] == c["source"]["tree"] and
         entry["passed"] is True and entry["real_claims"] == 0 and
         all(entry["checks"].get(k) is True for k in REQUIRED_ADMISSION), "original operator admission controls")


REQUIRED_ADMISSION = ("explicit-mode", "wrong-source", "wrong-role", "reference-before-native",
                      "duplicate-claim", "output-isolation", "lifecycle", "resources")


def manifest(c, role, facts, golden=None):
    """Bind the qualified common envelope and the operator's exact frozen inputs."""
    validate_config(c)
    need(role in ("reference", "native") and facts["run"] == RUN and facts["stage"] == role and
         facts["attempt"] == "initial" and facts["source"] == c["source"] and facts["revision"] == MODEL and
         facts["children"] == 1 and facts["one_cold_input"] is True and
         (facts["input_sha256"], facts["criteria_sha256"], facts["resource_sha256"]) == (INPUT, CRITERIA, RESOURCES),
         "operator manifest role, source or frozen population")
    record = dict(facts)
    need(not {"schema", "authority", "sshsig_verifier_sha256", "golden"}.intersection(record),
         "mixed authority modes")
    record.update(schema="studio017-operator-authorization/1", mode=MODE, task="Studio017",
                  amendment_sha256=AMENDMENT, lifecycle_sha256=c["artifacts"]["operator-lifecycle"]["sha256"])
    if role == "native":
        need(isinstance(golden, dict) and set(golden) == {"seal_sha256", "eligibility_sha256",
             "claim_sha256", "full_logits_sha256"} and all(hexid(v, 64) for v in golden.values()),
             "native needs eligible original reference")
        record["golden"] = golden
    else:
        need(golden is None, "reference has no golden input")
    return record


def manifest_path(role):
    need(role in ("reference", "native"), "operator authorization role")
    return STATE / ("operator-" + role + "-authorization.json")


def verified_manifest(c, role, expected):
    need(expected["mode"] == c["mode"] == MODE and expected["schema"] == "studio017-operator-authorization/1" and
         expected["run"] == c["run"] == RUN and expected["stage"] == role and expected["source"] == c["source"] and
         expected["amendment_sha256"] == AMENDMENT, "operator authorization binding")
    raw = read(manifest_path(role))
    need(raw == enc(expected), "frozen operator authorization differs from current admission")
    return dict(schema="studio017-local-authorization-binding/1", stage=role, run=RUN, sha256=sha(raw))
