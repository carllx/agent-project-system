# Browser Transport Failure Ledger

## Authority and use

本 Ledger 保存已经观察或证明的具体 Browser Transport 路径结果，用于阻止在实验变量未变化时重复已知失败。它不是 Protocol、Transport Contract 或新实验体系；身份、投递、no-resend 与 recovery 语义仍以 `docs/specs/opencli-session-discovery.md` 为权威。

证据等级必须明确写成以下之一：

- `OBSERVED`：真实运行中出现，但不足以建立普遍机制结论。
- `INFERENCE`：由 Observation 推出的候选解释，尚未证明。
- `PROVEN`：在声明的精确条件内已由充分 Evidence 建立；不得扩大到条件之外。

命中 `DO_NOT_REPEAT_WHEN` 时，只有 `RETRY_ONLY_IF` 中的变量确实改变后才可重试。相同失败条件、相同机制和相同 Evidence 预算下不得重复实验。

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
