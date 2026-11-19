# Issue #26: reusable agent runtime and staged memory

Status: architecture and incremental plan approved by the user on 2026-11-19; documentation delivery only.
Evidence baseline: `6b206553b2bb87d5d91926e4f9026d6a0d889be2`; research date: 2026-11-19.

## Decision summary

Keep native Ollama tool calling, SQLite domain storage, backend-only `/confirm`, and the old planner as a migration reference. Build a small reusable runtime with explicit tool effects and policies, not a commitments-only agent or a plugin framework. Develop its state contract in memory first, then add SQLite sessions in a separate reviewed milestone. The first persistent-session version automatically saves local sessions and history under the approved policy below. Do not add a semantic memory engine now; future adoption of Engram, LangGraph, Letta, or vector retrieval requires comparative evidence and separate approval.

The user approved the architecture, SQLite session persistence, and incremental plan, including a reusable runtime, serializable state, and read/preparation-only model capabilities. The current authorization covers finalizing, committing, and publishing this design as a documentation-only PR to `main`. Merge and functional implementation are separate actions; do not start PR1 or later phases automatically.

### Approved first-version session policy

- Automatically save sessions and conversation history locally in SQLite once the persistence milestone is delivered. This policy does not add an extra opt-in step for ordinary session recording.
- Provide backend-controlled deletion of one session or all conversation history. Remove the affected messages, snapshots, and session references so deleted sessions cannot be restored or retrieved. Do not delete commitments or unrelated domain records.
- Make retention configurable, with no automatic deletion initially. Finite retention must be explicitly configured; do not introduce an implicit expiration period.
- Do not persist credentials, secrets, or unnecessary complete tool results. Apply data minimization and sensitive-data exclusion before writing any history, snapshots, diagnostics, or exports; do not store raw model reasoning. Store only the tool-result fields needed for continuity, with references to current domain data.
- On recovery, invalidate all previous authorizations and verify current tool data again before proposing modifications. Restored drafts and historical confirmations never grant execution permission.
- Keep external tools disabled in the commitments agent. Adding session persistence does not enable OS, shell, web, or arbitrary filesystem tools.

These are requirements for future implementation, not claims that recording, deletion, or filtering already exists. Deletion covers active conversation storage and derived retrieval data; backup retention and forensic-erasure limitations must remain explicit.

## 1. Evidence and current architecture

The complete issue [#26](https://github.com/IFMLinares/viernes-pilot/issues/26) and related issues #3–#7 were read, including comments. The local source was inspected; no test suite, real-model evaluation, service probe, or private database inspection was performed. Source observations are not runtime acceptance results.

| Path | Observed behavior |
| --- | --- |
| `main.py:105-195` | Legacy REPL retrieves memory, sends native tools to Ollama, dispatches `tool_calls`, and presents/stores responses. Its OS capabilities must not enter the new registry. |
| `main.py:202-217`; `core/planner.py:917-944` | `--planner` selects a separate runtime with local Ollama and SQLite. |
| `core/planner.py:269-404,422-463` | Planner uses structured content with custom `action="tool"`, not native `tool_calls`; tool results are appended to the system message. |
| `core/planner.py:535-610,692-888` | Planner owns capture, clarification, proposal, routing, and commands. The pending guard at 733-735 blocks natural corrections. |
| `core/queries.py:7-96`; `core/planner.py:216-227` | Keyword/allowlist/typo routing and fixed area recognition constrain semantic understanding. |
| `core/planner_tools.py:45-150` | Reusable allowlisted registry and deterministic Caracas date resolver; only dates are currently registered. |
| `core/commitments.py:10-137` | Validated SQLite records; transactional create/edit/complete; no delete operation. |
| `core/presentation.py:149-212` | Reusable structured presentation of proposals and records. |
| `tools/evaluate_interpreter.py:346-379` | In-memory accounting counts interpreter calls, which may contain several HTTP attempts. It is not durable per-POST accounting. |

Preserve deterministic validation of commands, IDs, schemas, dates, permissions, transactions, and confirmations. Move semantic intent, tool selection, and contextual clarification to the model. Changing routing does not authorize removing safety checks or changing current query scope semantics.

### Existing memory is not an architectural obligation

`core/memory.py:7-34,69-73` uses HTTP search/save/delete routes; it does not identify the server version or prove compatibility with current upstream Engram. Requests in these functions show no explicit authentication header or timeout. Actual service exposure and authentication remain unverified.

`search_expanded` at 37-66 issues a full query plus up to three word queries and deduplicates by ID. It does not implement semantic ranking. `learn_from_interaction` at 109-193 asks the LLM to propose saves/deletions and executes them at 179-189. Do not inherit this write authority in the new runtime. A configured embedding-model name is not evidence that this adapter uses embeddings.

## 2. Four different kinds of information

| Kind | Examples | Authority and lifetime |
| --- | --- | --- |
| Operational state | Active goal, draft, proposal revision, pending clarification, turn budget | Backend-owned structured state. Restore data, never authority or in-flight effects. |
| Conversation history | User/assistant turns, tool-call/result records, interrupted turns | Historical evidence with session scope and retention. Not necessarily current or correct. |
| Long-term memory | Explicit preferences, useful facts, durable decisions | Curated assertions with provenance and correction/forgetting rules. Not required to recover a session. |
| Current tool data | Current commitments, current time, actual operation result | Read from the owning tool/store when needed; historical copies are not authoritative. |

Restart recovery is a state-storage problem, not proof of a need for semantic search. Similarity retrieval is not truth, authorization, or verification that a commitment still exists. An old preference cannot override the user's current correction; an old record snapshot cannot override a fresh store read. Conflicting evidence requires clarification rather than a universal score-based priority rule.

## 3. Reusable runtime: minimum contracts

These are proposed interfaces, not implemented APIs. The core must not import `CommitmentStore`, task-area enums, or commitment-specific intents.

| Contract | Minimum behavior |
| --- | --- |
| `ModelAdapter.next(messages, tool_specs, budget)` | Return validated assistant content/calls or a typed failure. Account for every outbound attempt before sending. No tool execution. |
| `ToolSpec` | Stable name/version, description, strict input/output schemas, effect set, resource scope, handler, and output-size bound. Registration is explicit application composition. |
| `ToolExecutor.execute(call, context)` | Resolve only registered handlers, validate arguments and output, enforce policy/budgets, return a structured result. No `eval`, arbitrary imports, SQL, or shell supplied by the model. |
| `Policy.authorize(spec, context, arguments)` | Decide from trusted principal, enabled capabilities, effect set, resource scope, and lifecycle state. Default deny; model arguments cannot create permission. |
| `ConversationState` | Versioned JSON primitives with session ID, revision, messages/cursors, goal/draft/proposal data, provenance, reference metadata, and interrupted-turn status. No handlers, connections, executable objects, credentials, or valid grants. |
| `SessionStore.load/save/list/export/delete/delete_all` | In-memory implementation for the early runtime unit; SQLite for persistent sessions. Validate schema/version and session scope, use expected-revision checks, export minimized plain versioned data, and apply configurable retention with no automatic deletion initially. Individual and all-history deletion are backend-authorized, not model tools. |
| `Runtime.handle_turn(input, state, context)` | Produce the next state and typed response/proposal; bounded sequential calls, no automatic effect replay. Application policy owns valid domain transitions. |
| `ConfirmationService.confirm(active_proposal, trusted_input)` | Outside model tools. Verify presentation, current revision, fresh domain state, current-process grant, and transactional outcome. |

Memory retrieval is an optional later boundary: `search(query, scope, limit)` returns bounded items with source IDs, timestamps, provenance, and status. It cannot modify operational state directly. Do not build multiple adapters, generalized workflow DSLs, provider discovery, or a memory engine before a measured need exists.

The commitments capability supplies the existing store, date resolver, query/search/get tools, proposal validators, and renderers. Future capabilities register their own tools and policies without changing the runtime's intent classifier. Tool schemas should be bounded and selected by trusted capability configuration, not an ever-growing prompt or an LLM permission decision.

### Effects and permissions

| Effect | Meaning | Model availability in this stage |
| --- | --- | --- |
| `read` | Retrieve allowed local data without changing domain records | Allowed only for enabled scopes. |
| `prepare` | Compute a candidate change or revise a draft, without committing it | Allowed; validated and versioned by the backend. |
| `write` | Change durable domain data or long-term memory | Denied to model dispatch. Backend confirmation required. |
| `external` | Interact with an external system, host application, network destination, or other side-effect boundary | Disabled; requires a future capability-specific policy and consent. |

Effects are sets, not a loophole through one label: an external read needs both `read` and `external`; a memory deletion is `write`. Unknown effects are denied. Permission also includes resource scope and principal, not just effect class. The configured loopback Ollama transport is infrastructure, not an external-action tool available to the model. Nothing here permits web, shell, OS, or arbitrary filesystem tools.

Backend session journaling and diagnostic accounting are infrastructure writes, not LLM write tools. The user-approved recording policy authorizes automatic local session/history saves once that milestone is implemented, subject to minimization and exclusion of secrets. `/confirm` remains required for a proposed commitment or durable-memory change, not for every automatic journal entry. Session/history deletion is a separate explicit user action through the backend; the model cannot delete history autonomously.

### Tool envelopes and truthfulness

Use strict `ok/data/error/meta` responses. Errors include `INVALID_ARGUMENTS`, `NOT_FOUND`, `AMBIGUOUS_REFERENCE`, `DATE_CONFLICT`, `STALE_PROPOSAL`, `UNAUTHORIZED`, `TOOL_UNAVAILABLE`, and `BUDGET_EXCEEDED`. Empty results are successful empty collections. Backend-generated call IDs identify real tool outcomes. Tool data remains in tool-role messages, never system instructions.

The initial capability offers query/search/get, existing date resolution, and prepare create/edit/complete; no delete and no confirm tool. Bound arguments, result counts, and text sizes; validate IDs against actual reads. Structured renderers present proposals and successful writes from backend results, not model claims. Clarify missing necessary fields, including area, rather than silently inventing them. Preserve details and fields the user did not correct.

## 4. Serializable state and safe restart

Separate `ConversationState` from a non-serializable `ExecutionContext` containing process epoch, cancellation, current principal, and grants. Never reconstruct grants from chat text, summaries, imported data, provider checkpoints, or serialized booleans. Unknown state versions fail closed or use an explicit tested migration; do not deserialize pickle or executable objects.

Within a session, resolve references against identified tool-result sets. Corrections produce a new proposal revision. A goal switch suspends the previous proposal and makes it unconfirmable; resuming requires showing a fresh proposal. `/cancel` discards the draft's operational availability; retained history under the recording policy does not make it resumable.

On restart:

1. Create a new process epoch and an empty grant set.
2. Load and validate a selected session and the last committed state/history boundary. Reject foreign or corrupt snapshots.
3. Mark unfinished inference/tool turns interrupted; do not resume a queued call automatically.
4. Restore goals and drafts as data; mark proposals unconfirmed and references potentially stale.
5. Re-read current tool records before preparing a fresh proposal. Recompute dates only when appropriate and make changed interpretations visible.
6. Present the recovered situation and require new `/confirm` for a newly presented proposal.

An old `/confirm` in history is never executable input. Completed-operation records are evidence, not reusable grants. If a crash occurs after a domain commit but before response/session save, do not blindly repeat it. Add an operation identity and committed-result record in the same domain transaction before claiming reliable commit reconciliation; separate session/domain databases are not an atomic unit. Until that exists, surface an uncertain result and reconcile by reading the domain store.

Initially stop recovery at user-turn boundaries, not the exact program instruction. This deliberately avoids reimplementing a durable workflow engine. A single-session owner plus expected-revision checks is sufficient initially; multiple writers and network-mounted databases are out of scope.

## 5. Memory alternatives: evidence and tradeoffs

These alternatives occupy different layers. LangGraph and Letta are runtime choices, while FTS/vector retrieval are indexing choices. They cannot be ranked as interchangeable databases. No local performance benchmark, installed-provider compatibility test, or retrieval-quality experiment was run.

### A. Application SQLite sessions/history; optional FTS5

- **Fit:** closest to the existing local Python/SQLite application. Plain records, turn-boundary snapshots, and indexed session/message IDs need no additional model. This is application persistence, not a custom semantic memory engine.
- **Cost:** low deployment cost, but schema versioning, crash consistency, retention, backup/restore, deletion, and context selection remain our responsibility. Do not minimize this maintenance burden.
- **Performance:** direct local transactions and no network service for state; no measured latency claim. One writer per database; never hold transactions across model calls. WAL is optional, not a prerequisite or cure for concurrency.
- **Recovery:** load a transactional snapshot and messages; SQLite does not itself decide what is safe to resume. Grants remain outside persistence.
- **Retrieval:** session ID/recent messages solve continuity exactly; FTS5 supports lexical ranking, not general paraphrase understanding. Spanish tokenization and accents need tests; Porter stemming is English-specific. Check FTS5 availability before enabling it and safely compile literal search input.
- **Privacy/security:** local files, journals, indexes, and backups contain sensitive data. Restrict permissions, minimize content, and define retention. Standard SQLite is not an encryption or access-control policy. Logical deletion does not promise forensic erasure from backups/WAL.
- **Reversibility:** versioned JSON export and SQL tables are portable; FTS is disposable and rebuildable. A small separate sessions database can avoid changing commitments, but domain-effect reconciliation must remain transactionally inside the domain database.

**Challenge to this default:** it becomes a poor choice if we implement arbitrary step replay, distributed workers, extensive checkpoint migrations, or a sophisticated retrieval/compaction engine ourselves. Reassess before that happens. Even a single-user app can accumulate too much history; retrieval and retention cannot be deferred indefinitely once persistence ships.

### B. Engram as a memory provider

- **Fit:** upstream Gentleman-Programming/engram documents local SQLite/FTS5 and coding-agent observations, sessions, and search. That makes it a candidate for long-term observations, not proof it fits Viernes operational checkpoints. Current HTTP adapter compatibility/version remains unverified.
- **Cost:** delegates observation CRUD/search and some memory lifecycle functionality, but adds a provider deployment, versioned API, namespace design, health/failure handling, export/import mapping, and potentially two sources of truth if misused.
- **Performance/models:** upstream FTS retrieval does not inherently need embeddings. Extraction/summarization via Viernes's current learning loop does consume LLM calls; Engram adoption does not remove this cost. No performance advantage over direct SQLite is established.
- **Recovery:** durable observations are not sufficient to restore a proposal revision, interrupted turn, or safe confirmation. Keep authoritative session state separate unless a tested contract proves otherwise.
- **Retrieval:** useful lexical observations and metadata may help; quality depends on what is written and searched, not the product name. No verified advantage over an equivalent FTS baseline exists here.
- **Privacy/security:** isolate personal-assistant data from coding-agent projects; review auth/exposure, cloud/sync settings, and deletion propagation. Do not assume the orchestrator's Engram installation is Viernes's provider or permission to reuse it.
- **Reversibility:** upstream documents exports/sync, but completeness of observation/session metadata for Viernes needs a round-trip test. Preserve source IDs and provider-neutral export. Do not auto-import existing coding memories.

### C. LangGraph with persistent checkpointing

- **Fit:** its documented checkpointer stores thread-scoped graph state; its separate Store handles cross-thread memory. It is a real option when durable workflow continuation is needed, not an automatic semantic-memory upgrade.
- **Cost:** graph/runtime adoption, checkpoint saver dependency, graph-state migrations, and replay semantics. This revisits the currently approved no-framework direction and needs separate justification/approval.
- **Performance/models:** basic checkpointing needs no embedder; semantic Store search does. Checkpoint I/O and graph orchestration have unmeasured local cost; LLM calls are not made cheaper by checkpoints.
- **Recovery:** built-in checkpoints/interrupts can reduce custom recovery work. Resumed nodes can re-execute; effects must be idempotent. Viernes must invalidate old approval even if the checkpoint remembers a confirmed-looking state.
- **Retrieval:** checkpoints restore a thread, not relevance across old conversations; that requires additional Store/retrieval design.
- **Privacy/security:** state serialization can persist prompts/tool data; thread isolation and checkpointer access need policy. Tracing or remote services are deployment choices, not automatically local or required.
- **Reversibility:** exporting our state is feasible; porting graph control position and checkpoint semantics is more expensive. Keep domain data and grants independent.

### D. Letta as a memory-oriented agent runtime

- **Fit:** current docs describe a stateful runtime with local/self-hosted and cloud paths, not a drop-in search provider. Adopting it changes who owns the agent loop and memory lifecycle and risks duplicating our proposed runtime.
- **Cost:** runtime/server lifecycle and adaptation of tools, state, permissions, models, and export. Exact requirements depend on the selected current deployment; do not assume all Letta variants use one fixed database or old archival-memory architecture.
- **Performance/models:** local storage does not guarantee local inference. Configure local Ollama explicitly. Memory management/background work can consume additional model calls; quantify those calls in comparisons. Current MemFS docs distinguish keyword search from optional semantic/hybrid search through QMD.
- **Recovery:** persisted agent state can survive restarts; self-host backup is still an operational responsibility. Viernes approval rules must override any resumed runtime state.
- **Retrieval:** current MemFS uses in-context root memory and deeper files read on demand; conversation-history search is separate. Available semantic/hybrid features depend on backend/deployment. None demonstrates better Spanish personal-assistant recall without evaluation.
- **Privacy/security:** memory files, transcripts, model destinations, server auth, and background consolidation all matter. Review available default tools and disable unneeded effects. Do not route personal data to cloud merely to obtain memory features.
- **Reversibility:** memory backup/export is documented; complete export of conversations, operational state, and execution semantics has not been verified. A Letta comparison must measure migration-out, not merely successful startup.

### E. SQLite plus local vector retrieval

- **Fit:** incremental retrieval layer over canonical sessions/facts, not a replacement for structured state or fresh domain reads. SQLite itself does not make embeddings; an extension such as sqlite-vec supplies vector search.
- **Cost:** embedding model/runtime, text chunking, embedding-version metadata, update/delete propagation, relevance thresholds, and index rebuilds. sqlite-vec's README currently warns it is pre-v1 with possible breaking changes.
- **Performance/models:** adds embedding computation, storage and local CPU/RAM/possibly GPU contention with Ollama. No extra generative model is inherently required, but an embedding model is. Changing embedding dimensions/models requires reindexing.
- **Recovery:** vector indexes persist, but session restore still needs the same structured store. Rebuild indexes from canonical text and tolerate index unavailability.
- **Retrieval:** can help paraphrase/cross-language queries; can also retrieve semantically similar but wrong, stale, or negated facts. Evaluate hybrid lexical/vector retrieval against lexical and recent-context baselines.
- **Privacy/security:** local embeddings avoid a remote embedding API only when configured locally. Vectors are sensitive derived data, not anonymization. Verify extension loading/supply chain and forgetting across indexes/backups.
- **Reversibility:** high if indexes are disposable and source text remains canonical; lower if only vectors/summaries survive. Keep embedding fingerprint/dimensions and do not couple domain IDs to an index format.

## 6. Approved staging, with limits

1. Implement the reusable runtime with in-memory, JSON-serializable state first. Session selection and recent context need no semantic engine.
2. Add automatic local SQLite session/history persistence as an isolated milestone before promising recovery after restarts. The approved first-version policy includes individual/all-history deletion and configurable retention with no automatic deletion initially. Record turn boundaries atomically, never raw chain-of-thought, secrets, credentials, or unnecessary tool payloads. Keep minimized diagnostics separate from user-visible history. The in-memory-only runtime unit is an implementation step, not the completed persistent-session version.
3. Restore by session ID and bounded recent context plus structured goals/drafts. Do not inject the entire archive into every prompt. A derived summary, if later added, is non-authoritative and must retain source links.
4. Keep long-term memory disabled initially. A later approved milestone may add user-confirmed structured preferences/facts without a semantic engine; durable memory changes still follow backend authorization.
5. Add FTS5 only if measured cross-session keyword retrieval is needed. Compare Engram or vectors on identical records before creating a home-grown relevance/curation subsystem.
6. Reconsider LangGraph for measured durable-workflow complexity or Letta as a deliberate alternative runtime, not as a memory library casually inserted into the current loop.

The approved SQLite sessions design contains conceptual `sessions`, ordered `messages`, and versioned `snapshots`; this is not a finalized SQL schema. Optional facts and indexes are separate future work. Export includes minimized source messages, state schema version, revisions, timestamps, and provenance, but never secrets or reusable authorization. Recovery, deletion, exclusion, retention, and backup tests must exist before using persistence with real user data.

## 7. Decision experiments and acceptance gates

Use synthetic personal-assistant histories with source labels and held-out questions, then separately authorized real-model runs. Do not copy private conversations into a benchmark. Keep the same Ollama model/digest, context budget, fixtures, generation settings, and questions across alternatives. Count inference used for extraction, dreaming, summarization, query rewriting, and embeddings as well as answering. Separate retrieval-only scores from end-to-end behavior and framework/runtime changes from retrieval changes.

| Experiment | Cases and acceptance |
| --- | --- |
| Serialization | JSON round-trip of partial drafts, goal switches, cancel, tool references, schema mismatch, malformed/foreign sessions; no executable objects or grants accepted. |
| Restart boundaries | Stop before/after user save, model call, tool result, proposal presentation, confirmation, domain commit, and response. Restore last durable boundary; never automatically replay a write or revive an old `/confirm`. |
| Persistence failure | Disk-full, busy database, interrupted save, corrupt snapshot, schema incompatibility, backup/restore. No invented durability or partial valid-looking state; clearly report unsaved turns. |
| Approved recording policy | New sessions/turns save automatically; sensitive fixtures in user/assistant messages and tool outputs never reach history, snapshots, diagnostics, or exports. Unnecessary full tool payloads are excluded. No extra recording opt-in is required. |
| Deletion and retention | Delete one session without affecting others; delete all history including snapshots/references without deleting commitments; deleted sessions cannot be recovered from active session storage. No automatic deletion by default, including after restart; explicitly configured finite retention follows its documented boundary. |
| Freshness | Complete/edit a record externally after it appears in history, then refer to it. Re-read domain data and require new review; old memory never supplies current status. |
| Retrieval ablation | A: structured state + recent turns; B: A + session/recency filters + FTS; C: same records through Engram; D: A + local vector/hybrid search. Evaluate LangGraph/Letta separately for runtime recovery and equivalent tool-policy enforcement. |
| Context quality | Exact names, paraphrases without shared terms, Spanish/English variants, long gaps, ambiguous people, changed preferences, negation, obsolete facts, and questions whose answer was never stored. |
| Security | Poisoned memory saying “ignore policy”, another session's IDs, forged approved snapshot, stale confirmation, unauthorized memory deletion, and external tools. Zero policy bypasses or cross-scope disclosures in the security corpus. |
| Portability/forgetting | Export/import into an empty store and compare IDs/provenance and user-visible state; logical forgetting removes retrieval from active stores and indexes. Document backup retention separately; do not claim forensic erasure. |

Measure Recall@k/Precision@k for supporting sources, MRR where rank matters, grounded-answer correctness, stale-fact rate, appropriate abstention, conversation success, correction preservation, and tool-grounding. Also measure p50/p95 latency, peak RAM, storage/index size, request/token/embedding counts, rebuild time, and export completeness.

The design's advancement gate is to improve held-out end-to-end memory-dependent task success by at least 5 percentage points over the simplest viable baseline, with a paired uncertainty interval supporting a positive improvement; no security/restart gate failures and no increase in stale-fact errors. Pre-register absolute local resource/latency budgets after baseline measurement, and obtain the separate authorization for any live evaluation. Report sample size and repeated-run variance. Inconclusive evidence means keep the simpler option, not declare equivalence or adopt advanced memory by default. Do not freeze the exact history-window size or k without baseline measurements.

## 8. Revised PR sequence: stop after each phase

Each PR contains its behavior, tests, documentation, acceptance evidence, and rollback boundary. The old planner remains the reference; no implicit PR creation, publishing, default switch, or progression to the next unit is authorized.

| PR | Dependency and scope | Risk and completion evidence |
| --- | --- | --- |
| 1. Conversation baseline and HTTP accounting | First functional unit after the design delivery is merged and work on PR1 is explicitly started. Synthetic full conversations from #3–#6; durable count-before-send for each actual POST, shared caps/timeouts, partial reports. No new agent/memory dependency. | Counter bypass and unbounded inference. Test multiple POSTs per interpreter call, failure, restart accounting, stop-first-failure, and report distinction between mock/replay/live. No model run until its budget is separately approved. |
| 2. Minimal reusable runtime | After PR1 review. Native Ollama adapter, explicit ToolSpec/executor/policy, read/prepare restrictions, in-memory serializable state, deterministic safe test tools and existing date capability. No commitment writes. | Protocol/model mismatch and accidental permissions. JSON round-trip, deny write/external/unknown, tool failure and budget tests; separately bounded native-tool model probe. |
| 3. Persistent sessions and restart | After PR2 review and explicit start of this phase. SQLite session/history store with automatic saves, individual/all-history deletion, configurable retention defaulting to no automatic deletion, minimized export/import, turn-boundary restore, and safe authorization invalidation; no FTS, vectors, or extracted long-term memory. | Persisted sensitive content, state migration, lost turns. Crash-boundary, isolation, deletion, secret/tool-payload exclusion, default/configured retention, backup/restore, stale-reference, failure, and forged-authorization tests. No promises of domain exactly-once yet. |
| 4. Commitment reads and preparation | After PR2; integrate with reviewed PR3 baseline before delivery. Query/search/get plus prepare create/edit/complete, provenance, reuse existing validators/renderers. | Query compatibility, invented IDs/fields. Differential public behavior, real result grounding, ambiguity, and unchanged domain database on preparation. |
| 5. Multi-turn corrections and goals | After PR4. Correct/resume/suspend/cancel proposals, preserve unrelated fields, display revised proposals; include restored-session conversations. | Stale/accidental operations. Full-turn state/output/data assertions, cancelled-reference explanation, and no lost fields. |
| 6. Backend confirmation and reconciliation | After PR3–PR5 review. `/confirm` bound to displayed current revision and current process, transactional conflict checks, domain operation identity/result where needed. | Security, concurrency, persisted format additions. Repeated confirmation, post-restart denial, commit/response crash reconciliation, rollback, and domain compatibility tests. |
| 7. Comparative adoption gate | After PR6. Old/new corpus and separately approved local real-model evaluation; document remaining failures and rollback. | Regressions and premature stability claims. Zero critical safety failures; approved conversation targets and local budgets; explicit decision before changing defaults or retiring routing. |
| Optional later: memory improvement experiment | Only after an observed retrieval deficit and separate approval. FTS/Engram/vector ablations or isolated LangGraph/Letta proof. | Retrieval poisoning, added dependencies and lock-in. Meet Section 7 improvement/resource/portability gates; otherwise do not integrate. |

Do not rewrite the legacy memory adapter during the baseline PR. Isolate the new runtime from its autonomous write path rather than silently changing default REPL behavior. Existing issues remain open until their own observed acceptance evidence is satisfied.

## 9. Approval boundary

Approved: reusable native-Ollama runtime, no LangGraph or additional semantic memory engine now, SQLite domain/session storage, serializable in-memory initial runtime unit, effect classification, model limited to read/prepare, backend `/confirm`, clarification, old planner reference, and real-model evaluation before adoption. The first-version session policy is automatic local recording, individual/all-history deletion, configurable retention with no automatic deletion initially, exclusion of secrets and unnecessary complete tool results, fresh verification and authorization invalidation on recovery, and disabled external tools.

Current delivery: finalize the consistency review, create a documentation-only commit on `docs/issue-26-design`, and publish a PR to `main` linked to #26 without closing its unimplemented migration criteria. This does not authorize merging, starting functional PRs, changing the default runtime, or live model calls. After the design is merged, PR1 is the next unit; each later phase remains isolated and stops for review. Concrete SQL/configuration interfaces and live-evaluation budgets belong to their respective future phase, not this documentation commit.

## Sources and uncertainty

- [SQLite appropriate uses](https://sqlite.org/whentouse.html): local application storage and single-writer limitations.
- [SQLite FTS5](https://sqlite.org/fts5.html): lexical search, BM25, tokenization, build availability, index consistency.
- [SQLite WAL](https://sqlite.org/wal.html) and [backup API](https://sqlite.org/backup.html): WAL tradeoffs, database-level atomicity, supported backup.
- [Engram upstream](https://github.com/Gentleman-Programming/engram): coding-agent memory, local SQLite/FTS5, interfaces and export/sync; not proof of the configured Viernes server/version.
- [LangGraph persistence](https://docs.langchain.com/oss/python/langgraph/persistence) and [durable execution](https://docs.langchain.com/oss/python/langgraph/durable-execution): checkpoints versus Store, replay and effect safety.
- [Letta self-hosting](https://docs.letta.com/self-hosting/), [MemFS](https://docs.letta.com/concepts/memfs/), [memory configuration](https://docs.letta.com/configuration/memory/), and [CLI reference](https://docs.letta.com/platform/cli/reference/): deployment-specific persistence/search and memory export.
- [sqlite-vec](https://github.com/asg017/sqlite-vec): vector-search extension and current pre-v1 compatibility warning.
- [Ollama tool calling](https://docs.ollama.com/capabilities/tool-calling): native tool messages and sequential agent loop. Installed-model behavior still requires measured evaluation.

External product docs can change. Pin versions and verify the selected local deployment before implementation. Neither product marketing nor this source review establishes comparative retrieval quality, performance, or security of a running installation.
