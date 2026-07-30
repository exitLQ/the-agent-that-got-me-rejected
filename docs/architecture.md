# the-agent-that-got-me-rejected architecture

Grounded in the current code (`src/job_scout/…`). Renders anywhere Mermaid is
supported (GitHub, most blog engines). Legend: **solid arrows** = data flow,
**dotted arrows** = cross-cutting concerns (LLM calls, Opik tracing, config).

```mermaid
flowchart TB
  U(["User"]) -->|"upload CV (PDF)"| UI

  subgraph UI_L["Gradio UI · app.py"]
    UI["3-step wizard<br/>session model → Resume → Profile → Jobs<br/>provider status · streamed progress · fit gauges"]
  end

  UI -->|"filepath"| CVR["cv_reader.py<br/>pypdf: PDF → text"]
  CVR -->|"transient CV text"| EP["profile.py · extract_profile<br/>1 LLM call · structured output"]
  CVR -->|"transient CV text"| COR["corpus.py<br/>typed addressable facts<br/>session memory only"]
  CVR -->|"delete temporary UI copy"| DEL["privacy.py<br/>temp-boundary deletion"]
  EP -->|"Profile"| RUN

  subgraph ORCH["runner.py · orchestrator (UI + batch share it)"]
    RUN["stream_search / stream_tailoring / run_once<br/>measures cost + latency · streams node status"]
  end

  RUN -->|"explicit current-run inputs"| G

  subgraph G["LangGraph agent · graph.py (MemorySaver checkpoint)"]
    direction TB
    S((START)) --> ENTRY{"selected_job_id<br/>present?"}
    ENTRY -->|"no"| FJ
    ENTRY -->|"yes"| TA["tailor<br/>strict TailoringPack<br/>dedicated model"]
    TA --> VAL["validate_tailoring<br/>deterministic claim checks<br/>typed FabricationReport"]
    FJ["fetch_jobs<br/>LLM picks search args via tool call"] --> RJ
    RJ["rank_jobs<br/>5-job batches · bounded concurrent workers<br/>deterministic aggregation · hybrid score"] --> D{"enough good matches?<br/>≥5 jobs scoring ≥60"}
    D -->|"no · under 2 loops"| RQ["reformulate_query<br/>quality feedback · validation · history<br/>deterministic fallback when needed"]
    RQ --> FJ
    D -->|"yes · or cap hit"| E((END))
    VAL --> E
  end
  COR -. "AgentContext<br/>runtime only" .-> TA
  COR -. "reference lookup<br/>runtime only" .-> VAL

  FJ -->|"query · country · remote"| SRCH
  subgraph SRCH["run_search · jobs_api.py"]
    direction LR
    MODE{"OFFLINE_MODE?"} -->|"true"| CA["Cache<br/>local-only"]
    MODE -->|"false"| JS["JSearch<br/>primary"]
    JS --> AZ["Adzuna<br/>international"] --> RM["Remotive<br/>keyless"] --> CA
  end
  SRCH -->|"JobPostings"| LOC["location gate<br/>exact city → remote scope → same country<br/>known mismatches removed"]
  LOC --> RJ

  E -->|"RankedJobs or tailoring report"| RUN
  RUN -->|"ranked cards + cost/latency + Opik link"| UI
  UI -->|"selected job + status + notes"| DB["applications.py<br/>local SQLite tracker"]
  DB -->|"saved application overview"| UI

  subgraph LLM_L["LLM · llm.py (provider guard + get_chat_model + ensure_budget ≤25)"]
    OA["Ollama local default<br/>OpenAI · Anthropic · xAI/Grok optional<br/>cloud requires consent + matching key"]
  end
  EP -. "LLM" .-> OA
  FJ -. "LLM" .-> OA
  RJ -. "LLM" .-> OA
  RQ -. "LLM" .-> OA
  TA -. "LLM" .-> OA

  subgraph OBS["Opik observability · tracing.py"]
    TR["track_langgraph + OpikTracer<br/>span tree · agent graph · per-run cost"]
    PL["prompt library<br/>3 prompts, versioned"]
    AT["CV attachment<br/>privacy mode must be off"]
  end
  RUN -. "wrap + traces" .-> TR
  G -. "spans" .-> TR
  EP -. "register" .-> PL
  CVR -. "PDF only when privacy is off" .-> AT

  CFG["config.py · Settings<br/>SecretStr keys · privacy/offline boundaries · budget=25"] -. "config" .-> RUN

  classDef llm fill:#e8f0fe,stroke:#4285f4,color:#111;
  classDef obs fill:#e6f4ea,stroke:#137333,color:#111;
  classDef node fill:#fff7e6,stroke:#b06000,color:#111;
  class OA,LLM_L llm;
  class TR,PL,AT,OBS obs;
  class FJ,RJ,RQ,TA,VAL node;
```

## Reading it

1. **Provider → upload → text → profile.** The first page combines a provider
   and model identifier into a canonical session model. It checks local or
   cloud readiness before reading the PDF and never stores keys in browser
   state. The Gradio wizard then hands the PDF to `cv_reader`
   (pypdf), then `extract_profile` turns the text into a typed `Profile` with one
   structured-output LLM call before the graph, so it is extracted once. In
   privacy mode the temporary UI upload is deleted after reading, and raw text
   is not stored in Gradio state or passed into LangGraph.
2. **The agent graph.** `runner.py` supplies explicit current-run inputs to
   LangGraph. The entry router starts at `tailor` only for a non-empty
   `selected_job_id`; otherwise it starts at `fetch_jobs`. Search then runs
   `fetch_jobs` (the LLM chooses the search arguments) → `rank_jobs` (batched
   model assessment plus deterministic skill, role, seniority, and location
   components) → a conditional edge that either loops through
   `reformulate_query` (max 2) to broaden the search, or ends. The displayed
   score uses 60% deterministic rules and 40% model assessment. Displayed skill
   matches and gaps are reconstructed from profile and job evidence instead of
   trusting the model lists directly. Independent five-job assessment batches
   run through a bounded worker pool and are reassembled by original batch
   index, so completion timing cannot alter aggregation.
3. **Controlled reformulation.** When quality is low, the node summarizes scores,
   validates a novel two-to-eight-term query, and records an audit entry. A
   deterministic adjacent-role fallback replaces invalid or repeated output.
   The fetch node executes this query directly and prioritizes new unique jobs
   during the 25-result merge.
4. **Job sources.** `fetch_jobs` calls `run_search`. With `OFFLINE_MODE=true`,
   it returns directly from the committed cache and never initializes a live
   adapter. With offline mode disabled, it uses the JSearch → Adzuna → Remotive
   → cache cascade.
5. **Location gate.** Every preferred profile location is normalized locally.
   Exact city matches rank above eligible remote scopes and same-country
   fallbacks; known geographical mismatches are removed before LLM ranking.
6. **Cross-cutting (dotted).** Every node's LLM call goes through `llm.py`
   (provider guard, provider-agnostic model factory, and per-run call budget).
   The selected model travels in LangGraph state, so profile extraction and all
   graph nodes use one session-scoped choice without mutating process settings.
   Ollama is local by default. OpenAI, Anthropic, and xAI/Grok require
   `OFFLINE_MODE=false`, `CLOUD_LLM_ENABLED=true`, and a matching key. **Opik**
   is available only when
   both offline mode and privacy mode are disabled and tracing is explicitly
   configured. Privacy mode also blocks PDF attachments and excludes the
   candidate name from ranking prompts. `config.py` supplies keys, both
   boundaries, and other settings.
7. **Application tracker.** Ranked results remain temporary until the user
   explicitly saves one. `applications.py` then upserts a job snapshot, one of
   six validated statuses, private notes, and timestamps in local SQLite. The
   tracker does not persist CV text, candidate profiles, prompts, model output,
   or credentials. `Start over` clears the wizard session but deliberately
   leaves saved applications intact.
8. **Temporary CV corpus.** During upload, `corpus.py` segments the transient CV
   text into deterministic `summary`, `skill`, `experience`, and `education`
   items. It removes direct contact channels and the usual preamble before the
   items enter Gradio session state. The corpus travels through LangGraph only
   as runtime `AgentContext`; it is not placed in graph state, checkpoints,
   SQLite, or logs. It is cleared by `Start over` and provides the addressable
   evidence contract for tailoring and validation.
9. **Strict tailoring contracts.** `TailoredBullet`, `TailoredSkill`, and
   `TailoringPack` define the only accepted shape for future generated
   application material. Bullets and skills require syntactically valid corpus
   references; the pack requires a selected job, at least two distinct
   requirements, an honesty note, and a cover letter capped at 350 words.
   Unknown fields and normalized duplicates are rejected. These are structural
   guarantees only; the following deterministic node resolves references
   against the session corpus and compares requirements with the selected job.
10. **Tailoring node.** `tailor_application` validates the selected job,
    profile, session corpus, and call budget before invoking the dedicated
    tailoring model. `AgentContext` carries the corpus as a run dependency so it
    never becomes checkpointed `AgentState`. The safety contract is a system
    message; bounded JSON job, profile, and corpus data are supplied separately
    as untrusted content. The node returns a strict `TailoringPack` or a bounded
    error and rejects packs for another job.
11. **Entry isolation.** Search explicitly passes `selected_job_id=None` and
    clears both `tailoring` and `fabrication_report`, while `stream_tailoring`
    explicitly passes the current profile, ranked jobs, and selection. The
    latter carries the temporary corpus and dedicated model only through
    `AgentContext`. Consequently a checkpoint cannot silently select a job,
    retain an older draft, or persist the corpus.
12. **Deterministic validation.** `validate_tailoring` always follows successful
    or failed generation. With a pack, it resolves cited corpus identifiers,
    measures normalized bullet and skill similarity, verifies addressed
    requirements against the job, and checks factual-looking cover-letter
    sentences. First-person letter claims can use only CV evidence. It returns a
    typed report with counts, warnings, ratios, and the exact configured
    thresholds without copying source corpus text into checkpointed state. It
    makes no LLM call and does not automatically repair or reject the draft.
    The Gradio UI does not call this branch until the later explicit-selection
    step is implemented.
