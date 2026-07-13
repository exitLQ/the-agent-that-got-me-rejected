"""Gradio UI for Job Scout.

The UI is a delivery mechanism, not a lesson — default theme, no custom CSS.
It streams node-level progress during a run and shows a cost/latency/source/Opik
footer after every run, normalizing cost-awareness from the first click.
"""

from __future__ import annotations

from uuid import uuid4

import gradio as gr

from job_scout.runner import RunResult, stream_run
from job_scout.schemas import Profile
from job_scout.tools.cv_reader import CVReadError, extract_cv_text
from job_scout.tracing import opik_url, register_prompts

CAPTION = "Prepares applications, never submits them."
DF_HEADERS = ["title", "company", "location", "fit", "why / gaps", "url"]
DF_DATATYPES = ["str", "str", "str", "number", "str", "markdown"]


def _profile_card(profile: Profile | None) -> str:
    if profile is None:
        return "_Upload a CV and click **Find jobs** to see your profile here._"
    role = ", ".join(profile.primary_roles) or "—"
    return (
        f"**{profile.name or 'Candidate'}** · {profile.seniority}\n\n"
        f"**Role:** {role}  \n"
        f"**Experience:** {profile.years_experience or '—'} yrs  \n"
        f"**Locations:** {', '.join(profile.locations) or '—'}  \n"
        f"**Remote:** {'yes' if profile.remote_ok else 'no'}  \n"
        f"**Skills:** {', '.join(profile.skills) or '—'}"
    )


def _results_rows(result: RunResult) -> list[list]:
    rows = []
    for r in result.ranked_jobs:
        why = r.fit_explanation[:120] + ("…" if len(r.fit_explanation) > 120 else "")
        if r.gaps:
            why += f" (gaps: {', '.join(r.gaps[:3])})"
        url = f"[link]({r.job.url})" if r.job.url else ""
        rows.append([r.job.title, r.job.company, r.job.location, r.fit_score, why, url])
    return rows


def _footer(result: RunResult) -> str:
    sources = ", ".join(result.jobs_sources) or "none"
    link = f"[view traces in Opik]({result.opik_url or opik_url()})"
    if result.failed:
        return f"⚠ run failed — {result.error_message}. The trace has details · {link}"
    return f"run cost ${result.cost_usd:.4f} · {result.latency_s}s · source: {sources} · {link}"


def on_find(file_path: str | None, thread_id: str):
    """Generator handler: streams status, then emits profile + results + footer.

    During streaming only the status line changes; the other three outputs are
    left untouched with ``gr.update()`` (no value = keep current).
    """
    hold = (gr.update(), gr.update(), gr.update())

    if not file_path:
        yield ("Please upload a PDF CV first.", *hold)
        return

    try:
        cv_text = extract_cv_text(file_path)
    except CVReadError as exc:
        yield (f"Could not read that PDF: {exc}", *hold)
        return

    result = RunResult()
    for kind, payload in stream_run(cv_text, cv_path=file_path, thread_id=thread_id, tags=["phase-1", "ui"]):
        if kind == "status":
            yield (f"⏳ {payload}", *hold)
        else:
            result = payload  # type: ignore[assignment]

    status = "Run failed — see footer." if result.failed else f"Done — {result.n_jobs_ranked} jobs ranked."
    yield (status, _profile_card(result.profile), _results_rows(result), _footer(result))


def build_app() -> gr.Blocks:
    register_prompts()  # offline-safe; versions prompts in Opik when enabled

    with gr.Blocks(title="Job Scout") as demo:
        thread_id = gr.State(lambda: str(uuid4()))
        gr.State(None)  # selected_job_id — wired in Phase 2

        gr.Markdown("# Job Scout")
        gr.Markdown(f"_{CAPTION}_")

        with gr.Row():
            with gr.Column(scale=1):
                cv_file = gr.File(label="Your CV (PDF)", file_types=[".pdf"], type="filepath")
                find_btn = gr.Button("Find jobs", variant="primary")
            with gr.Column(scale=1):
                profile_md = gr.Markdown(_profile_card(None))

        status_md = gr.Markdown("")
        results_df = gr.Dataframe(headers=DF_HEADERS, datatype=DF_DATATYPES, wrap=True, interactive=False, label="Ranked jobs")

        # Disabled in Phase 1; the select handler + enablement ship in Phase 2.
        gr.Button("Tailor selected job", interactive=False)
        gr.Markdown("_Tailoring ships in part 2._")

        footer_md = gr.Markdown("")

        find_btn.click(
            on_find,
            inputs=[cv_file, thread_id],
            outputs=[status_md, profile_md, results_df, footer_md],
        )

    return demo


def main() -> None:
    build_app().launch()


if __name__ == "__main__":
    main()
