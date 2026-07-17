# Job Scout — Architecture

![Job Scout architecture](images/architecture.png)

Grounded in the current code (`src/job_scout/…`). Renders anywhere Mermaid is
supported (GitHub, most blog engines). Legend: **solid arrows** = data flow,
**dotted arrows** = cross-cutting concerns (LLM calls, Opik tracing, config).

The diagram above is also available as editable Mermaid source:

```mermaid
flowchart TB
  U(["User"]) -->|"upload CV (PDF)"| UI

  subgraph UI_L["Gradio UI · app.py"]
    UI["3-step wizard<br/>Resume → Profile → Jobs<br/>streamed status · fit gauges · footer"]
  end

  UI -->|"filepath"| CVR["cv_reader.py<br/>pypdf: PDF → text"]
  CVR -->|"CV text"| EP["profile.py · extract_profile<br/>1 LLM call · structured output"]
  EP -->|"Profile"| RUN

  subgraph ORCH["runner.py · orchestrator (UI + batch share it)"]
    RUN["stream_search / run_once<br/>measures cost + latency · streams node status"]
  end

  RUN -->|"Profile"| G

  subgraph G["LangGraph agent · graph.py (MemorySaver checkpoint)"]
    direction TB
    S((START)) --> FJ
    FJ["fetch_jobs<br/>LLM picks search args via tool call"] --> RJ
    RJ["rank_jobs<br/>batched LLM scoring · BATCH_SIZE=5"] --> D{"enough good matches?<br/>≥5 jobs scoring ≥60"}
    D -->|"no · under 2 loops"| RQ["reformulate_query<br/>broaden the query"]
    RQ --> FJ
    D -->|"yes · or cap hit"| E((END))
  end

  FJ -->|"query · country · remote"| SRCH
  subgraph SRCH["run_search cascade · jobs_api.py (fall-through, keyless-safe)"]
    direction LR
    JS["JSearch<br/>primary"] --> AZ["Adzuna<br/>international"] --> RM["Remotive<br/>keyless"] --> CA["Cache<br/>~247 offline jobs"]
  end
  SRCH -->|"JobPostings"| RJ

  E -->|"RankedJobs"| RUN
  RUN -->|"ranked cards + cost/latency + Opik link"| UI

  subgraph LLM_L["LLM · llm.py (get_chat_model + ensure_budget ≤25)"]
    OA["OpenAI gpt-4o-mini<br/>(or Groq / Ollama via SCOUT_MODEL)"]
  end
  EP -. "LLM" .-> OA
  FJ -. "LLM" .-> OA
  RJ -. "LLM" .-> OA
  RQ -. "LLM" .-> OA

  subgraph OBS["Opik observability · tracing.py"]
    TR["track_langgraph + OpikTracer<br/>span tree · agent graph · per-run cost"]
    PL["prompt library<br/>3 prompts, versioned"]
    AT["CV attached to trace"]
  end
  RUN -. "wrap + traces" .-> TR
  G -. "spans" .-> TR
  EP -. "register" .-> PL
  CVR -. "PDF" .-> AT

  CFG["config.py · Settings<br/>SecretStr keys · SCOUT_MODEL · budget=25"] -. "config" .-> RUN

  classDef llm fill:#e8f0fe,stroke:#4285f4,color:#111;
  classDef obs fill:#e6f4ea,stroke:#137333,color:#111;
  classDef node fill:#fff7e6,stroke:#b06000,color:#111;
  class OA,LLM_L llm;
  class TR,PL,AT,OBS obs;
  class FJ,RJ,RQ node;
```

## Reading it

1. **Upload → text → profile.** The Gradio wizard hands the PDF to `cv_reader`
   (pypdf), then `extract_profile` turns the text into a typed `Profile` with one
   structured-output LLM call — *before* the graph, so it's extracted once.
2. **The agent graph.** `runner.py` feeds the profile into the LangGraph:
   `fetch_jobs` (the LLM chooses the search arguments) → `rank_jobs` (batched fit
   scoring) → a conditional edge that either loops through `reformulate_query`
   (max 2) to broaden the search, or ends.
3. **Job sources.** `fetch_jobs` calls the `run_search` cascade — JSearch →
   Adzuna → Remotive → offline cache — each tried only if the previous returned
   too few, so it runs with **zero API keys**.
4. **Cross-cutting (dotted).** Every node's LLM call goes through `llm.py`
   (provider-agnostic + a per-run call budget). **Opik** wraps the whole graph in
   one line (`track_langgraph`), producing a span tree, the auto-drawn agent
   graph, per-run cost, the versioned prompt library, and the CV attached to the
   trace. `config.py` supplies keys and settings.
