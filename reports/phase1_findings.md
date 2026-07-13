# Phase 1 findings

The baseline batch (`scripts/run_batch.py`) surfaces failures and weaknesses.
**These are documented here, not fixed** — fixing happens in Phase 3 through the
Ollie / Test Suite workflow, so the fix itself becomes content. Phase 1's job is
to make the weaknesses observable.

## How to reproduce

```bash
uv run python scripts/run_batch.py --yes
```

Writes `reports/baseline.json`. The numbers below are read from that file.

## Baseline numbers

_Populated from `reports/baseline.json` after the batch runs. Fields: runs,
failures, empty-result runs, reformulation triggers, latency mean/median/p95,
mean/total cost, fit-score distribution._

| metric | value |
|---|---|
| runs | _pending_ |
| failures | _pending_ |
| empty_result_runs | _pending_ |
| reformulation_triggered | _pending_ |
| latency mean / median / p95 (s) | _pending_ |
| cost mean / total (USD) | _pending_ |
| fit-score mean | _pending_ |

## Known weaknesses (by design — do NOT fix in Phase 1/2)

These are expected consequences of the deliberately-unoptimized first-draft
prompts and the honest tool-calling design. Confirm and quantify each against
the batch traces; they are the seed list for Phase 2 evaluation and Phase 3
optimization.

1. **Ranking prompt is a plain first draft.** No few-shot, no rubric, no
   calibration. Expect inconsistent score scales across batches and vague
   `fit_explanation`s. (This is the prompt Phase 3 optimizes.)
2. **`matched_skills` may not be grounded.** Nothing enforces that returned
   `matched_skills` actually appear in both the profile and the job text —
   candidate for fabrication on the career-changer CV. (Phase 2 adds the
   `MatchedSkillsGrounding` metric.)
3. **Location constraints are advisory only.** The LLM chooses the search
   country; it can ignore the profile's locations, and ranking does not penalize
   a location mismatch.
4. **Reformulation can produce worse queries.** The broadening step may drift to
   an unrelated query and still return thin results, hitting the 2-loop cap.
   Cap-hit runs are logged — inspect them.
5. **No-tool-call fallback.** When `fetch_jobs`'s LLM issues no tool call, a
   profile-derived query is used and recorded in `errors`. Count how often.
6. **Offline / cache coverage is remote-only** until Adzuna keys are added and
   `make snapshot` is re-run — the committed cache is built from Remotive
   (keyless), so country-specific offline results are limited.

## Per-case observations

_Populated after the batch: note the specific case_ids that failed, returned
empty, or triggered reformulation, with a one-line hypothesis each._
