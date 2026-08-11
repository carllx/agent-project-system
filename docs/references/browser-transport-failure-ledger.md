# Browser Transport Failure Ledger

## Authority and use

本 Ledger 保存已经观察或证明的具体 Browser Transport 路径结果，用于阻止在实验变量未变化时重复已知失败。它不是 Protocol、Transport Contract 或新实验体系；身份、投递、no-resend 与 recovery 语义仍以 `docs/specs/opencli-session-discovery.md` 为权威。

证据等级必须明确写成以下之一：

- `OBSERVED`：真实运行中出现，但不足以建立普遍机制结论。
- `INFERENCE`：由 Observation 推出的候选解释，尚未证明。
- `PROVEN`：在声明的精确条件内已由充分 Evidence 建立；不得扩大到条件之外。

命中 `DO_NOT_REPEAT_WHEN` 时，只有 `RETRY_ONLY_IF` 中的变量确实改变后才可重试。相同失败条件、相同机制和相同 Evidence 预算下不得重复实验。

正式 bounded experiment 默认 `ONE_GOAL_ONE_FRESH_CONVERSATION`，顺序固定为 `/goal → read AGENTS/rules → read this Ledger → execute → report → stop`。新 Conversation 从本 Ledger 获得历史失败知识，不依赖旧 Conversation memory。已知 working path 和已查明的 CLI capability 不重新探索；一个实验不得边执行边持续重写 runner；background task 不得无界 schedule/poll；Evidence 足够后立即收口。

## KG-002 — Fenced code block to strict RR parser compatibility

- **EXPERIMENT_ID:** `RR-CODEBLOCK-PARSER-COMPAT-001`
- **EVIDENCE_CLASS:** `PROVEN`
- **PATH:** Browser unique fenced code block → OpenCLI plain extraction → unchanged repository-source `rr_response_fields()`.
- **RESULT:** `CODEBLOCK_STRICT_RR_COMPATIBILITY=PROVEN`; strict parse accepted `IN_REPLY_TO_MESSAGE_ID=RR-CODEBLOCK-PARSER-COMPAT-001-R1` and `REVIEW_DECISION=REVISE`.
- **FIRST_FAILURE_STAGE:** `NONE`.
- **RAW_ERROR:** `NONE`.
- **EVIDENCE:** Extracted plain text began/ended with exact RR sentinels and preserved literal underscores, list hyphens, and Status/Evidence indentation without normalize, replace, dedent, repair, or Markdown conversion.
- **CONFIDENCE:** `HIGH` for this exact representation path.
- **DO_NOT_REPEAT_WHEN:** The proposal only seeks to re-prove fenced-code-block compatibility with the unchanged strict parser.
- **RETRY_ONLY_IF:** Browser/OpenCLI plain extraction or strict parser behavior materially changes.
- **KNOWN_GOOD_ALTERNATIVE:** Require the complete machine RR wire in one fenced `text` code block with no outside text.

## KB-003 — SMOKE-002 representation false negative

- **EXPERIMENT_ID:** `SMOKE-002`
- **EVIDENCE_CLASS:** `OBSERVED`
- **PATH:** Automated Browser response representation used by SMOKE-002.
- **RESULT:** `SMOKE-002_RESPONSE_ACTUALLY_EXISTED=OBSERVED`; `SMOKE-002_FALSE_NEGATIVE_REPRESENTATION=OBSERVED`.
- **FIRST_FAILURE_STAGE:** Browser response representation / machine extraction classification.
- **RAW_ERROR:** The Product path classified the response as unavailable even though a Browser response was later observed to exist; no parser relaxation is authorized.
- **EVIDENCE:** Cleaned experiment result accepted by the user; KG-002 separately proves the copy-safe fenced representation path.
- **CONFIDENCE:** `HIGH` that the false negative occurred; broader causes remain unproven.
- **DO_NOT_REPEAT_WHEN:** Machine RR wire is again returned as ordinary Markdown prose instead of the known-good unique fenced block.
- **RETRY_ONLY_IF:** The response presentation changes to KG-002 or a causally relevant extraction variable changes.
- **KNOWN_GOOD_ALTERNATIVE:** KG-002 fenced code block presentation plus unchanged plain extraction and strict parser.

## U-003 — Intermittent stale controlled tab

- **EXPERIMENT_ID:** `NOT_ASSIGNED`.
- **EVIDENCE_CLASS:** `OBSERVED`
- **PATH:** Antigravity/OpenCLI controlled Browser tab state.
- **RESULT:** `INTERMITTENT_STALE_CONTROLLED_TAB=USER_OBSERVED_NOT_REPRODUCED`.
- **FIRST_FAILURE_STAGE:** `UNVERIFIED`.
- **RAW_ERROR:** No reproducible raw error captured.
- **EVIDENCE:** User observation only; current controlled reproduction did not reproduce it.
- **CONFIDENCE:** `LOW` pending a natural future occurrence.
- **DO_NOT_REPEAT_WHEN:** The sole purpose is to force reproduction without a real Product blocker.
- **RETRY_ONLY_IF:** A future bounded Product run naturally exposes the same symptom with capturable Evidence.
- **KNOWN_GOOD_ALTERNATIVE:** Use the current known-good fresh-Conversation path.

This entry is not `STALE_CONTROLLED_TAB_DISPROVEN`.

## KB-004 — SMOKE-003 collapsed outbound extraction false negative

- **EXPERIMENT_ID:** `AUTONOMOUS-BROWSER-PRODUCT-SMOKE-003`.
- **EVIDENCE_CLASS:** `PROVEN` for the stated extraction failure; outbound visibility and the Product false negative are `OBSERVED` facts.
- **PATH:** Product first write → exact post-send Conversation URL → current-page read → exact-ID detail with a collapsed outbound Product packet.
- **RESULT:** `SMOKE-003_OUTBOUND_ACTUALLY_VISIBLE=OBSERVED`; `SMOKE-003_DELIVERY_FALSE_NEGATIVE=OBSERVED`; `TRUNCATED_EXTRACTION_DELIVERY_FALSE_NEGATIVE=PROVEN` for this exact compact-packet-plus-`Show more` representation.
- **FIRST_FAILURE_STAGE:** Outbound delivery marker verification, before Response 1 continuation.
- **RAW_ERROR:** Both read and exact-ID detail ended the outbound user text with `Show more`; OpenCLI extraction inserted an unescaped newline inside the compact JSON string, so strict full-object JSON decoding failed at character 369 and both exact identity predicates returned false. Product state recorded `delivery_marker_count=0`, `delivery_marker_status=MISSING`, and `DELIVERY_UNKNOWN`.
- **EVIDENCE:** Canonical state recorded one write, exact candidate/current/recovered Conversation `6a7b319b-6088-83ea-9c1c-c48fd93439bd`, no candidate conflict, and no Delivery. Raw `08-read-after-send.json` and `09-detail.json` each contained the exact outer Work Item and Message identity prefix plus trailing `Show more`; `10-status-after-send.json` returned the same exact Conversation URL.
- **CONFIDENCE:** `HIGH` for this exact collapsed extraction and false-negative mechanism; no claim is made about unrelated truncation representations.
- **DO_NOT_REPEAT_WHEN:** The same compact Product packet is verified only by full-object JSON decoding despite explicit trailing `Show more` collapse evidence.
- **RETRY_ONLY_IF:** The bounded exact-ID truncation-aware verifier is under Product smoke validation or the extraction representation materially changes.
- **KNOWN_GOOD_ALTERNATIVE:** On the already selected exact Conversation, require exactly one user message whose collapsed compact Product packet begins with the exact Work Item and Message identities; otherwise retain `DELIVERY_UNKNOWN` and never resend.

This failure occurred before Response 1 entered formal reading. It is not evidence of Gemini, `/goal`, Hook, or autonomous continuation failure.

## KG-001 — Direct Node minimal autonomous loop

- **EXPERIMENT_ID:** `AG-BROWSER-AUTONOMOUS-MULTIPATH-BATCH-001`
- **EVIDENCE_CLASS:** `PROVEN`
- **PATH:** Direct Node OpenCLI invocation with minimal messages; new Conversation, two messages, same Browser Conversation, automatic response reads.
- **RESULT:** `FULL_AUTONOMOUS_LOOP=PASS`; clean path reproduced; `USER_MANUAL_RELAY_COUNT=0`.
- **FIRST_FAILURE_STAGE:** `NONE`.
- **RAW_ERROR:** `NONE`.
- **EVIDENCE:** User-accepted Batch result and external Experiment runtime; reference probe used `node <installed-package-bin-entry> chatgpt ...`.
- **CONFIDENCE:** `HIGH` within the stated Windows installation and minimal-message conditions.
- **DO_NOT_REPEAT_WHEN:** Not applicable to this known-good path.
- **RETRY_ONLY_IF:** A Product smoke needs to verify the Product integration or a relevant runtime variable changed.
- **KNOWN_GOOD_ALTERNATIVE:** `NONE_REQUIRED`.

This proves only the observed autonomous Browser path. It does not prove a model as primary cause, universal OpenCLI reliability, Hook necessity, or every payload size and Conversation state.

## KB-001 — Windows command shim under observed payload conditions

- **EXPERIMENT_ID:** `AG-BROWSER-AUTONOMOUS-MULTIPATH-BATCH-001` and prior recorded Windows long-argv incidents.
- **EVIDENCE_CLASS:** `OBSERVED`
- **PATH:** Windows `.cmd` / current argv invocation under the payload conditions exercised by those runs.
- **RESULT:** Argument or length handling failure before a usable autonomous Product exchange.
- **FIRST_FAILURE_STAGE:** OpenCLI process invocation / argument transmission.
- **RAW_ERROR:** Exact raw errors remain in the external experiment Evidence; the Product conclusion is limited to the observed argument/length failure class.
- **EVIDENCE:** Batch failure records plus `docs/references/windows-opencli-long-argv-001.md`.
- **CONFIDENCE:** `HIGH` for the observed payload conditions; not a universal statement about every `.cmd` invocation.
- **DO_NOT_REPEAT_WHEN:** The same Windows shim, argv payload conditions, and invocation mechanism are unchanged.
- **RETRY_ONLY_IF:** The invocation mechanism or another causally relevant variable changes and the new path remains bounded.
- **KNOWN_GOOD_ALTERNATIVE:** Resolve the installed npm package's declared `opencli` bin and invoke it through Node directly.

## KB-002 — PATH-D one-shot short Conversation discovery

- **EXPERIMENT_ID:** `AG-BROWSER-AUTONOMOUS-MULTIPATH-BATCH-001-PATH-D`
- **EVIDENCE_CLASS:** `PROVEN`
- **PATH:** New Conversation followed by one fixed three-second wait and one Conversation ID observation.
- **RESULT:** Invalid discovery design for the observed asynchronous navigation behavior.
- **FIRST_FAILURE_STAGE:** Conversation identity capture.
- **RAW_ERROR:** No exact Conversation ID was available at the single short observation.
- **EVIDENCE:** External `run_batch.py` uses `time.sleep(3)` followed by one `status` call; existing Product Evidence requires bounded navigation observation.
- **CONFIDENCE:** `HIGH` for rejecting this one-shot design.
- **DO_NOT_REPEAT_WHEN:** Conversation discovery is known to require bounded retry/poll observation and the proposal still uses one fixed short wait.
- **RETRY_ONLY_IF:** The observation mechanism changes to the already implemented bounded Product discovery path or new Evidence establishes a different completion signal.
- **KNOWN_GOOD_ALTERNATIVE:** Existing Product bounded status observation, followed by exact marker verification.

## U-001 — PATH-C timeout boundary

- **EXPERIMENT_ID:** `AG-BROWSER-AUTONOMOUS-MULTIPATH-BATCH-001-PATH-C`
- **EVIDENCE_CLASS:** `OBSERVED`
- **PATH:** Existing Conversation path exercised in PATH-C.
- **RESULT:** Response detail timeout in that run.
- **FIRST_FAILURE_STAGE:** Response 1 read.
- **RAW_ERROR:** `chatgpt detail timed out after 60s`.
- **EVIDENCE:** External Batch `run_batch.py` path and reported result.
- **CONFIDENCE:** `HIGH` that the timeout occurred; `LOW` for any broader causal explanation.
- **DO_NOT_REPEAT_WHEN:** All relevant PATH-C conditions are unchanged and the only purpose is to reproduce the same timeout.
- **RETRY_ONLY_IF:** A causally relevant variable changes or a real Product path exposes the same blocker.
- **KNOWN_GOOD_ALTERNATIVE:** The clean reproduced Direct Node new-Conversation path.

`INFERENCE` boundary: this timeout does not prove that existing-Conversation continuation is generally unavailable.

## U-002 — Model and Hook boundaries

- **EXPERIMENT_ID:** `AG-BROWSER-AUTONOMOUS-MULTIPATH-BATCH-001`
- **EVIDENCE_CLASS:** `INFERENCE`
- **PATH:** Cross-path interpretation after the autonomous clean reproduction.
- **RESULT:** `UNRESOLVED`.
- **FIRST_FAILURE_STAGE:** Not applicable; this is a causal-boundary entry.
- **RAW_ERROR:** `NONE`.
- **EVIDENCE:** Known-good path passed without Hook; strict model A/B was not completed.
- **CONFIDENCE:** `LOW` for model performance causality; `HIGH` only that Hook was not required by the reproduced known-good path.
- **DO_NOT_REPEAT_WHEN:** A proposal merely relabels the same observations as proof of universal model or Hook behavior.
- **RETRY_ONLY_IF:** A future Product blocker makes a strict causal comparison necessary.
- **KNOWN_GOOD_ALTERNATIVE:** Keep Hook disabled for the known-good Product smoke and use Direct Node invocation.

The PATH-D short-poll failure does not prove that new Conversation creation is unavailable. Model performance impact remains unresolved. Hook absence is proven only for the reproduced known-good path, not as a universal architecture conclusion.
