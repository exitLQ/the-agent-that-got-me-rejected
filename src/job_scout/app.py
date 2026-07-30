"""Gradio UI for the-agent-that-got-me-rejected.

A four-step wizard with a refined editorial look: warm-paper background with a
faint gradient-and-grain wash, a display serif (Fraunces) paired with a mono for
data (IBM Plex Mono), emerald accent. The flow is (1) drop your resume,
(2) review the extracted profile, (3) find jobs — ranked as cards with a
conic-gauge fit score, matched-skill chips, and honest gaps, and (4) explicitly
select one job and review a source-linked application draft plus every
deterministic validator warning.
"""

from __future__ import annotations

from html import escape
from urllib.parse import urlparse
from uuid import uuid4

import gradio as gr

from job_scout.applications import (
    APPLICATION_STATUSES,
    ApplicationRecord,
    ApplicationStoreError,
    get_application_store,
)
from job_scout.config import get_settings
from job_scout.corpus import CorpusItem, build_candidate_corpus
from job_scout.graph.schemas import Profile, RankedJob, SkillEvidence
from job_scout.llm import (
    ModelConfigurationError,
    OllamaRuntimeError,
    model_configuration_status,
    model_provider,
    qualify_model,
    validate_model_configuration,
)
from job_scout.privacy import delete_temporary_upload
from job_scout.profile import extract_profile
from job_scout.renderer import ApplicationPdfError, render_application_pdf
from job_scout.runner import (
    RunResult,
    TailoringResult,
    stream_search,
    stream_tailoring,
)
from job_scout.tools.cv_reader import CVReadError, extract_cv_text
from job_scout.tools.jobs_api import CacheSource
from job_scout.tracing import opik_url, register_prompts

CAPTION = "Prepares applications — never submits them."
PROVIDERS = ["ollama", "openai", "anthropic", "xai", "groq"]

INTRO_HTML = """
<p class="js-lead">Drop your resume and let the-agent-that-got-me-rejected find roles that actually match it —
ranked by fit, with the gaps shown honestly.</p>
<ol class="js-steps">
  <li><span class="js-num">1</span><div><b>Drop your resume</b> (PDF) below.</div></li>
  <li><span class="js-num">2</span><div>We <b>read it</b> and show your skills, experience, and locations.</div></li>
  <li><span class="js-num">3</span><div>Hit <b>Find jobs</b> to get openings ranked by fit.</div></li>
  <li><span class="js-num">4</span><div>Select one job and <b>review a grounded application draft</b>.</div></li>
</ol>
"""

THEME = gr.themes.Soft(
    primary_hue=gr.themes.colors.emerald,
    secondary_hue=gr.themes.colors.stone,
    neutral_hue=gr.themes.colors.stone,
    font=(
        gr.themes.Font("Public Sans"),
        gr.themes.Font("ui-sans-serif"),
        gr.themes.Font("system-ui"),
        gr.themes.Font("sans-serif"),
    ),
    radius_size=gr.themes.sizes.radius_md,
).set(
    body_background_fill="#FBFAF8",
    body_background_fill_dark="#141311",
    block_background_fill="#FFFFFF",
    block_background_fill_dark="#1E1D1A",
    button_primary_background_fill="#0E6E4A",
    button_primary_background_fill_hover="#0A5539",
    button_primary_text_color="#FFFFFF",
    button_large_radius="12px",
)

# Fine tiled grain, kept as a constant so the CSS block stays within line length.
_GRAIN = "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='140' height='140'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.85' numOctaves='2'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)' opacity='0.5'/%3E%3C/svg%3E\")"  # noqa: E501

CSS = """
:root {
  --js-accent: #0E6E4A;
  --js-accent-bright: #0E9C68;
  --js-ring-track: rgba(20,19,17,0.08);
}
.dark {
  --js-ring-track: rgba(255,255,255,0.10);
}

/* --- Atmospheric background: faint emerald + amber wash over warm paper --- */
.gradio-container {
  max-width: 760px !important;
  margin: 0 auto !important;
  position: relative;
}
body::before {
  content: "";
  position: fixed; inset: 0; z-index: 0; pointer-events: none;
  background:
    radial-gradient(60% 45% at 12% 4%, rgba(14,156,104,0.10), transparent 70%),
    radial-gradient(55% 45% at 92% 8%, rgba(180,83,9,0.07), transparent 72%);
}
.dark body::before {
  background:
    radial-gradient(60% 45% at 12% 4%, rgba(14,156,104,0.14), transparent 70%),
    radial-gradient(55% 45% at 92% 8%, rgba(180,83,9,0.10), transparent 72%);
}
/* fine grain */
body::after {
  content: "";
  position: fixed; inset: 0; z-index: 0; pointer-events: none; opacity: 0.35;
  background-image: __GRAIN__;
}
.dark body::after { opacity: 0.5; mix-blend-mode: screen; }
.gradio-container > * { position: relative; z-index: 1; }

/* --- Header --- */
#js-header { text-align: center; padding: 22px 0 4px; }
#js-header .js-mark {
  display: inline-flex; align-items: center; justify-content: center; gap: 10px;
}
#js-header .js-mark svg { width: 30px; height: 30px; color: var(--js-accent); }
#js-header h1 {
  font-family: 'Fraunces', Georgia, serif; font-weight: 600;
  font-size: 2.85rem; letter-spacing: -0.025em; margin: 0; line-height: 1.02;
}
#js-header .js-tag {
  display: inline-block; margin-top: 13px; font-size: 0.76rem; letter-spacing: 0.01em;
  color: var(--body-text-color-subdued);
  border: 1px solid var(--border-color-primary); border-radius: 999px; padding: 4px 14px;
  background: color-mix(in srgb, var(--block-background-fill) 55%, transparent);
  backdrop-filter: blur(4px);
}

/* --- Stepper --- */
.js-stepper {
  list-style: none; display: flex; align-items: center; justify-content: center;
  gap: 0; margin: 20px auto 6px; padding: 0; max-width: 420px;
}
.js-step { display: flex; align-items: center; gap: 9px; font-size: 0.82rem; }
.js-step-dot {
  width: 26px; height: 26px; border-radius: 50%; flex: none;
  display: grid; place-items: center; font-size: 0.78rem; font-weight: 700;
  font-family: 'IBM Plex Mono', monospace;
  border: 1.5px solid var(--border-color-primary); color: var(--body-text-color-subdued);
  background: var(--block-background-fill); transition: all .2s ease;
}
.js-step-label { color: var(--body-text-color-subdued); font-weight: 500; }
.js-step::after {
  content: ""; width: 34px; height: 1.5px; margin: 0 12px;
  background: var(--border-color-primary); border-radius: 2px;
}
.js-step:last-child::after { display: none; }
.js-step-active .js-step-dot {
  border-color: var(--js-accent); color: #fff; background: var(--js-accent);
  box-shadow: 0 0 0 4px rgba(14,110,74,0.14);
}
.js-step-active .js-step-label { color: var(--body-text-color); font-weight: 600; }
.js-step-done .js-step-dot {
  border-color: var(--js-accent); color: var(--js-accent);
  background: rgba(14,110,74,0.12);
}

/* --- Intro --- */
.js-lead { text-align: center; font-size: 1.05rem; line-height: 1.55; color: var(--body-text-color-subdued);
  margin: 14px auto 4px; max-width: 480px; }
.js-steps { list-style: none; padding: 0; margin: 18px auto 8px; max-width: 470px; }
.js-steps li { display: flex; gap: 13px; align-items: flex-start; padding: 9px 0; font-size: 0.95rem; line-height: 1.45; }
.js-steps .js-num { flex: none; width: 26px; height: 26px; border-radius: 50%;
  background: rgba(14,110,74,0.12); color: var(--js-accent); font-weight: 700; font-size: 0.82rem;
  font-family: 'IBM Plex Mono', monospace; margin-top: 1px;
  display: flex; align-items: center; justify-content: center; }

.js-section-label { font-size: 0.76rem; font-weight: 600; letter-spacing: 0.08em;
  text-transform: uppercase; color: var(--body-text-color-subdued); margin: 4px 0 10px 2px; }
.js-muted { color: var(--body-text-color-subdued); }

/* --- Dropzone polish --- */
.js-drop { border: 1.5px dashed var(--border-color-primary) !important;
  border-radius: 16px !important; background: color-mix(in srgb, var(--block-background-fill) 70%, transparent) !important;
  transition: border-color .2s ease, background .2s ease; }
.js-drop:hover { border-color: var(--js-accent) !important; }

/* --- Cards --- */
.js-card { background: var(--block-background-fill); border: 1px solid var(--border-color-primary);
  border-radius: 16px; padding: 20px 22px; box-shadow: 0 1px 2px rgba(20,19,17,0.03); }
.js-profile-name { font-family: 'Fraunces', serif; font-size: 1.5rem; font-weight: 600; margin: 0; letter-spacing: -0.01em; }
.js-profile-sub { color: var(--body-text-color-subdued); font-size: 0.92rem; margin: 3px 0 14px; }
.js-profile-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin: 4px 0 14px;
  border-top: 1px solid var(--border-color-primary); padding-top: 14px; }
.js-stat .js-stat-val { font-family: 'IBM Plex Mono', monospace; font-size: 1.15rem; font-weight: 600; line-height: 1; }
.js-stat .js-stat-key { font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.05em;
  color: var(--body-text-color-subdued); margin-top: 5px; }
.js-profile-row { font-size: 0.9rem; margin: 3px 0; }
.js-profile-row b { font-weight: 600; }
.js-pill { display: inline-block; font-size: 0.75rem; padding: 3px 11px; border-radius: 999px;
  background: rgba(14,110,74,0.10); color: var(--js-accent); margin: 5px 5px 0 0; }

/* --- Job cards --- */
.js-jobs { display: flex; flex-direction: column; gap: 12px; }
.js-job { border: 1px solid var(--border-color-primary); border-radius: 14px;
  padding: 17px 19px; background: var(--block-background-fill);
  box-shadow: 0 1px 2px rgba(20,19,17,0.03);
  transition: box-shadow .18s ease, transform .18s ease, border-color .18s ease;
  opacity: 0; transform: translateY(8px); animation: js-rise .4s ease forwards; }
.js-job:hover { box-shadow: 0 12px 30px rgba(20,19,17,0.09); transform: translateY(-2px);
  border-color: color-mix(in srgb, var(--js-accent) 40%, var(--border-color-primary)); }
@keyframes js-rise { to { opacity: 1; transform: none; } }

.js-job-head { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; }
.js-job-title { font-weight: 600; font-size: 1.06rem; text-decoration: none; color: var(--body-text-color);
  line-height: 1.3; }
.js-job-title:hover { color: var(--js-accent); }
.js-job-meta { font-size: 0.85rem; color: var(--body-text-color-subdued); margin-top: 4px;
  display: flex; align-items: center; flex-wrap: wrap; gap: 7px; }
.js-remote, .js-source { font-size: 0.66rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.04em;
  border-radius: 5px; padding: 2px 7px; line-height: 1.5; }
.js-remote { color: var(--js-accent); border: 1px solid rgba(14,110,74,0.35); }
.js-score-breakdown { margin: 0.55rem 0; color: var(--js-muted); font: 500 0.68rem/1.55 monospace; }
.js-score-breakdown span { display: inline-block; margin-right: 0.65rem; white-space: nowrap; }
.js-source { color: var(--body-text-color-subdued); border: 1px solid var(--border-color-primary); }
.js-job-why { font-size: 0.92rem; line-height: 1.55; margin: 12px 0 0; }

/* chips */
.js-chips { margin-top: 11px; display: flex; flex-wrap: wrap; gap: 6px; }
.js-chip { display: inline-flex; align-items: center; gap: 4px; font-size: 0.75rem;
  padding: 3px 10px; border-radius: 999px; line-height: 1.5; }
.js-chip-match { background: rgba(14,110,74,0.11); color: var(--js-accent); }
.js-chip-gap { background: rgba(100,116,139,0.13); color: var(--body-text-color-subdued); }
.js-evidence { margin-top: 10px; color: var(--body-text-color-subdued); font-size: 0.75rem; }
.js-evidence summary { cursor: pointer; font-weight: 600; }
.js-evidence ul { margin: 6px 0 0; padding-left: 18px; }
.js-evidence li { margin: 4px 0; line-height: 1.45; }
.js-query-audit { margin: 0 0 14px; padding: 10px 13px; border: 1px solid var(--border-color-primary);
  border-radius: 8px; color: var(--body-text-color-subdued); font-size: 0.78rem; }
.js-query-audit summary { cursor: pointer; font-weight: 600; }
.js-query-audit ol { margin: 7px 0 0; padding-left: 20px; }
.js-query-audit li { margin: 5px 0; line-height: 1.45; }

/* --- Tailoring review --- */
.js-pack { display: flex; flex-direction: column; gap: 14px; }
.js-tailored-list { display: flex; flex-direction: column; gap: 12px; }
.js-tailored-item { border: 1px solid var(--border-color-primary); border-radius: 12px;
  padding: 14px 16px; background: var(--block-background-fill); }
.js-tailored-item p { margin: 5px 0; line-height: 1.5; }
.js-source-text { color: var(--body-text-color-subdued); font-size: 0.84rem; }
.js-ref { display: inline-block; font-family: 'IBM Plex Mono', monospace; font-size: 0.67rem;
  color: var(--js-accent); background: rgba(14,110,74,0.09); border-radius: 5px;
  padding: 2px 6px; margin: 2px 5px 2px 0; }
.js-honesty { border-left: 3px solid #D97706; background: rgba(217,119,6,0.07);
  border-radius: 0 12px 12px 0; padding: 12px 16px; font-size: 0.9rem; line-height: 1.55; }
.js-fab-ok { border: 1px solid rgba(14,110,74,0.35); background: rgba(14,110,74,0.06);
  border-radius: 12px; padding: 12px 16px; font-size: 0.88rem; }
.js-fab-warn { border: 1px solid rgba(217,119,6,0.45); background: rgba(217,119,6,0.07);
  border-radius: 12px; padding: 12px 16px; font-size: 0.88rem; }
.js-fab-warn b, .js-honesty b { color: #B45309; }
.js-fab-warn ol { margin: 9px 0 0; padding-left: 1.3em; }
.js-fab-warn li { margin: 7px 0; line-height: 1.5; }
.js-fab-reason { display: block; color: var(--body-text-color-subdued); font-size: 0.8rem; }

/* --- Fit gauge --- */
.js-fit-ring { --size: 56px; width: var(--size); height: var(--size); flex: none;
  border-radius: 50%; display: grid; place-items: center; position: relative;
  background: conic-gradient(var(--ring) calc(var(--val) * 1%), var(--js-ring-track) 0); }
.js-fit-ring::before { content: ""; position: absolute; inset: 5px; border-radius: 50%;
  background: var(--block-background-fill); }
.js-fit-num { position: relative; font-family: 'IBM Plex Mono', monospace; font-weight: 600;
  font-size: 1.05rem; color: var(--tier-fg); }
.js-fit-high { --ring: var(--js-accent-bright); --tier-fg: #0E6E4A; }
.js-fit-mid  { --ring: #D97706; --tier-fg: #B45309; }
.js-fit-low  { --ring: #94A3B8; --tier-fg: #64748B; }
.dark .js-fit-high { --tier-fg: #34D399; }
.dark .js-fit-mid  { --tier-fg: #FBBF24; }
.dark .js-fit-low  { --tier-fg: #94A3B8; }

/* --- States --- */
.js-empty { text-align: center; padding: 40px 20px; color: var(--body-text-color-subdued); }
.js-empty .js-empty-icon { font-size: 1.8rem; opacity: 0.8; margin-bottom: 8px; }
.js-status { font-size: 0.86rem; color: var(--body-text-color-subdued); text-align: center; min-height: 18px; }
.js-status-err { color: #B45309; }
.js-spin { display: inline-block; width: 13px; height: 13px; margin-right: 8px; vertical-align: -1px;
  border: 2px solid rgba(14,110,74,0.25); border-top-color: var(--js-accent); border-radius: 50%;
  animation: js-rotate .7s linear infinite; }
@keyframes js-rotate { to { transform: rotate(360deg); } }

/* --- Footer --- */
.js-footer { text-align: center; font-size: 0.82rem; color: var(--body-text-color-subdued);
  border-top: 1px solid var(--border-color-primary); margin-top: 20px; padding-top: 15px; }
.js-footer .js-meta-mono { font-family: 'IBM Plex Mono', monospace; }
.js-footer a { color: var(--js-accent); text-decoration: none; }
.js-footer a:hover { text-decoration: underline; }

/* accessibility: visible focus */
a:focus-visible, button:focus-visible, .js-job-title:focus-visible {
  outline: 2px solid var(--js-accent); outline-offset: 2px; border-radius: 4px; }

@media (max-width: 520px) {
  #js-header h1 { font-size: 2.3rem; }
  .js-step-label { display: none; }
  .js-step::after { width: 22px; margin: 0 8px; }
  .js-profile-grid { grid-template-columns: repeat(3, 1fr); gap: 8px; }
}
@media (prefers-reduced-motion: reduce) {
  .js-job { animation: none; opacity: 1; transform: none; }
  .js-spin { animation: none; }
}
""".replace("__GRAIN__", _GRAIN)

# Small compass mark for the wordmark.
_MARK = (
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" '
    'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
    '<circle cx="12" cy="12" r="9"/><path d="m15.5 8.5-2.1 5-5 2.1 2.1-5z"/></svg>'
)


def _stepper(active: int) -> str:
    """Render the 4-step progress indicator with ``active`` (1-4) highlighted."""
    labels = ("Resume", "Profile", "Jobs", "Application")
    items = []
    for i, label in enumerate(labels, 1):
        state = "done" if i < active else "active" if i == active else "todo"
        mark = "✓" if state == "done" else str(i)
        items.append(
            f'<li class="js-step js-step-{state}">'
            f'<span class="js-step-dot">{mark}</span>'
            f'<span class="js-step-label">{label}</span></li>'
        )
    return f'<ol class="js-stepper">{"".join(items)}</ol>'


def _loading_html(text: str) -> str:
    """Centered spinner with a message."""
    return f'<div class="js-empty"><div class="js-empty-icon"><span class="js-spin"></span></div><div>{escape(text)}</div></div>'


def _chips(items: list[str], kind: str, limit: int) -> str:
    """Render a row of matched-skill or gap chips."""
    icon = "✓ " if kind == "match" else ""
    shown = "".join(f'<span class="js-chip js-chip-{kind}">{icon}{escape(s)}</span>' for s in items[:limit])
    return f'<div class="js-chips">{shown}</div>' if shown else ""


def _evidence_html(matches: list[SkillEvidence], gaps: list[SkillEvidence]) -> str:
    """Render expandable provenance for every displayed skill claim."""
    rows = []
    for kind, items in (("match", matches), ("gap", gaps)):
        for item in items:
            rows.append(
                f"<li><b>{kind}: {escape(item.skill)}</b> — "
                f"{escape(item.profile_evidence)} — {escape(item.job_evidence)}</li>"
            )
    if not rows:
        return ""
    return (
        '<details class="js-evidence"><summary>Skill evidence</summary>'
        f'<ul>{"".join(rows)}</ul></details>'
    )


def _profile_html(profile: Profile | None) -> str:
    """Render the extracted profile as a card."""
    if profile is None:
        return '<div class="js-card js-muted">Could not read a profile from that resume.</div>'
    skills = "".join(f'<span class="js-pill">{escape(s)}</span>' for s in profile.skills) or "—"
    years = f"{profile.years_experience:g}" if profile.years_experience else "—"
    languages = escape(", ".join(profile.languages) or "—")
    return (
        '<div class="js-card">'
        f'<p class="js-profile-name">{escape(profile.name or "Candidate")}</p>'
        f'<p class="js-profile-sub">{escape(profile.seniority.title())} · '
        f"{escape(', '.join(profile.primary_roles) or '—')}</p>"
        '<div class="js-profile-grid">'
        f'<div class="js-stat"><div class="js-stat-val">{years}</div><div class="js-stat-key">Years exp</div></div>'
        f'<div class="js-stat"><div class="js-stat-val">{"Yes" if profile.remote_ok else "No"}</div>'
        '<div class="js-stat-key">Remote</div></div>'
        f'<div class="js-stat"><div class="js-stat-val">{len(profile.skills)}</div><div class="js-stat-key">Skills</div></div>'
        "</div>"
        f'<p class="js-profile-row"><b>Locations</b> &nbsp;{escape(", ".join(profile.locations) or "—")}</p>'
        f'<p class="js-profile-row"><b>Languages</b> &nbsp;{languages}</p>'
        f'<div style="margin-top:12px">{skills}</div>'
        "</div>"
    )


def _fit_class(score: int) -> str:
    """Return the CSS tier class for a fit score."""
    if score >= 80:
        return "js-fit-high"
    if score >= 60:
        return "js-fit-mid"
    return "js-fit-low"


def _fit_ring(score: int) -> str:
    """Render the hybrid fit score as a conic-gradient gauge."""
    return (
        f'<div class="js-fit-ring {_fit_class(score)}" style="--val:{score}" '
        f'role="img" aria-label="Hybrid fit score {score} out of 100">'
        f'<span class="js-fit-num">{score}</span></div>'
    )


def _job_card(ranked: RankedJob, index: int) -> str:
    """Render one ranked job as a card with a conic fit gauge and skill chips."""
    job = ranked.job
    title = escape(job.title)
    if job.url:
        title_html = f'<a class="js-job-title" href="{escape(job.url)}" target="_blank" rel="noopener">{title}</a>'
    else:
        title_html = f'<span class="js-job-title">{title}</span>'
    remote = '<span class="js-remote">Remote</span>' if job.remote else ""
    source = f'<span class="js-source">{escape(job.source)}</span>'
    matched = _chips(ranked.matched_skills, "match", 6)
    gaps = _chips(ranked.gaps, "gap", 4)
    evidence = _evidence_html(
        ranked.matched_skill_evidence[:6],
        ranked.gap_evidence[:4],
    )
    breakdown = ""
    if ranked.score_breakdown:
        score = ranked.score_breakdown
        breakdown = (
            '<div class="js-score-breakdown" aria-label="Hybrid score breakdown">'
            f"<span>rules {score.deterministic}</span><span>model {score.llm}</span>"
            f"<span>skills {score.skills}</span><span>role {score.role}</span>"
            f"<span>seniority {score.seniority}</span><span>location {score.location}</span>"
            "</div>"
        )
    delay = f"animation-delay:{min(index, 8) * 55}ms"
    return (
        f'<div class="js-job" style="{delay}">'
        '<div class="js-job-head">'
        f"<div>{title_html}"
        f'<div class="js-job-meta">{escape(job.company)} · {escape(job.location)}{remote}{source}</div></div>'
        f"{_fit_ring(ranked.fit_score)}"
        "</div>"
        f'<p class="js-job-why">{escape(ranked.fit_explanation)}</p>'
        f"{breakdown}"
        f"{matched}{gaps}{evidence}"
        "</div>"
    )


def _results_html(result: RunResult) -> str:
    """Render the ranked jobs as cards, or an empty state."""
    audit = _query_audit_html(result)
    if not result.ranked_jobs:
        return (
            f'{audit}<div class="js-empty"><div class="js-empty-icon">🔍</div>'
            "<div>No matching jobs found. Try a resume with more detail, or check back later.</div></div>"
        )
    cards = "".join(_job_card(r, i) for i, r in enumerate(result.ranked_jobs))
    return f'{audit}<div class="js-jobs">{cards}</div>'


def _query_audit_html(result: RunResult) -> str:
    """Render the initial query and every auditable reformulation."""
    if not result.query_history:
        return ""
    rows = [f"<li><b>initial</b>: {escape(result.query_history[0])}</li>"]
    for record in result.reformulation_log:
        rows.append(
            f"<li><b>attempt {record.attempt}</b>: {escape(record.query)} "
            f"({escape(record.strategy)}; {escape(record.reason)}; "
            f"{record.jobs_seen} jobs, {record.good_jobs} good, best {record.best_score})</li>"
        )
    return (
        '<details class="js-query-audit"><summary>'
        f"Query audit ({len(result.query_history)} searches)</summary>"
        f'<ol>{"".join(rows)}</ol></details>'
    )


def _footer_html(result: RunResult) -> str:
    """Render run metadata and a trace link only when tracing is active."""
    settings = get_settings()
    privacy_note = "privacy: raw resume discarded" if settings.privacy_mode else "privacy mode: off"
    selected_model = result.model or settings.scout_model
    provider = model_provider(selected_model)
    model_note = (
        f"cloud LLM: CV content sent to {escape(provider)}"
        if provider and provider != "ollama"
        else "local LLM: Ollama"
    )
    if settings.offline_mode:
        cache_meta = CacheSource().metadata()
        offline_note = (
            f"offline cache: {cache_meta['job_count']} jobs, "
            f"file date {cache_meta['modified_date']}; results may be stale"
        )
        link = escape(offline_note)
    elif settings.has_opik:
        link = f'<a href="{result.opik_url or opik_url()}" target="_blank" rel="noopener">view traces in Opik ↗</a>'
    else:
        link = "tracing: disabled"
    if result.failed:
        details = " The trace has details." if settings.has_opik else ""
        body = (
            f"run failed — {escape(result.error_message)}.{details} · "
            f"{link} · {privacy_note} · {model_note}"
        )
    else:
        sources = escape(", ".join(result.jobs_sources) or "none")
        sep = ' <span class="js-muted">·</span> '
        query_path = escape(" -> ".join(result.query_history) or "none")
        query_meta = (
            f'<span class="js-meta-mono" title="{query_path}">'
            f"queries: {len(result.query_history)}</span>"
        )
        ranking_meta = (
            f'<span class="js-meta-mono" title="ranking latency">'
            f"ranking: {result.ranking_batch_count} batches / "
            f"{result.ranking_workers} workers / {result.ranking_latency_s:.3f}s / "
            f"{result.ranking_failed_batches} failed"
            f"</span>"
        )
        cost_meta = (
            f"${result.cost_usd:.4f}"
            if result.cost_estimate_available
            else "cost: check provider dashboard"
        )
        body = (
            f'<span class="js-meta-mono">{cost_meta}</span>{sep}'
            f'<span class="js-meta-mono">{result.latency_s}s</span>{sep}'
            f"source: {sources}{sep}{query_meta}{sep}{ranking_meta}{sep}{link}"
            f"{sep}{privacy_note}{sep}{model_note}"
        )
    return f'<div class="js-footer">{body}</div>'


def _fabrication_html(result: TailoringResult) -> str:
    """Render every deterministic warning without claiming a proof of truth."""
    report = result.fabrication_report
    if report is None:
        return (
            '<div class="js-fab-warn"><b>Validation report unavailable.</b> '
            "Do not use this draft until its claims have been checked.</div>"
        )
    thresholds = (
        f"bullet {report.thresholds['bullet']:.2f}, "
        f"skill {report.thresholds['skill']:.2f}, "
        f"letter {report.thresholds['letter']:.2f}"
    )
    if report.flags == 0:
        return (
            '<div class="js-fab-ok"><b>No claims were flagged by the deterministic checks.</b> '
            f"{report.claims_checked} claims checked at {escape(thresholds)}. "
            "This is not a guarantee of truth; review the draft before using it.</div>"
        )
    items = []
    for flag in report.flagged:
        refs = " ".join(
            f'<span class="js-ref">{escape(ref)}</span>'
            for ref in flag.corpus_refs
        )
        refs_html = f"<br>{refs}" if refs else ""
        items.append(
            f"<li><b>{escape(flag.claim_type.replace('_', ' '))}</b> "
            f"at <span class=\"js-ref\">{escape(flag.where)}</span>: "
            f"{escape(flag.text)}{refs_html}"
            f'<span class="js-fab-reason">{escape(flag.reason)} '
            f"(best ratio {flag.best_match_ratio:.3f})</span></li>"
        )
    return (
        f'<div class="js-fab-warn"><b>{report.flags} of '
        f"{report.claims_checked} checked claims require review.</b> "
        "Warnings are not hidden and do not prove that a statement is false. "
        f"Thresholds: {escape(thresholds)}."
        f'<ol>{"".join(items)}</ol></div>'
    )


def _source_evidence_html(
    references: list[str],
    corpus_by_id: dict[str, CorpusItem],
) -> str:
    """Render every cited source item beside a generated suggestion."""
    rows = []
    for reference in references:
        item = corpus_by_id.get(reference)
        source = item.text if item is not None else "Source item is unavailable."
        rows.append(
            f'<p class="js-source-text"><span class="js-ref">{escape(reference)}</span> '
            f"{escape(source)}</p>"
        )
    return "".join(rows)


def _tailoring_html(
    result: TailoringResult,
    corpus: list[CorpusItem],
) -> str:
    """Render grounded suggestions, source evidence, honesty note, and warnings."""
    if result.tailoring is None:
        why = "; ".join(result.errors) or result.error_message or "unknown error"
        return (
            '<div class="js-empty"><div><b>Could not prepare this application.</b>'
            f"<p>{escape(why)}</p></div></div>"
        )

    pack = result.tailoring
    corpus_by_id = {item.item_id: item for item in corpus}
    requirements = "".join(
        f"<li>{escape(requirement)}</li>"
        for requirement in pack.addressed_requirements
    )
    bullets = []
    for bullet in pack.tailored_bullets:
        bullets.append(
            '<div class="js-tailored-item">'
            f"<p><b>Suggested rewrite</b><br>{escape(bullet.text)}</p>"
            f"<p class=\"js-source-text\"><b>Why</b><br>{escape(bullet.reason)}</p>"
            f"{_source_evidence_html(bullet.corpus_refs, corpus_by_id)}"
            "</div>"
        )
    skills = []
    for skill in pack.selected_skills:
        skills.append(
            '<div class="js-tailored-item">'
            f"<p><b>{escape(skill.name)}</b></p>"
            f"{_source_evidence_html([skill.corpus_ref], corpus_by_id)}"
            "</div>"
        )
    skill_section = (
        '<p class="js-section-label">Source-linked skills</p>'
        f'<div class="js-tailored-list">{"".join(skills)}</div>'
        if skills
        else ""
    )
    return (
        '<div class="js-pack">'
        f"{_fabrication_html(result)}"
        '<p class="js-section-label">Requirements addressed</p>'
        f'<div class="js-card"><ul>{requirements}</ul></div>'
        '<p class="js-section-label">CV rewrite suggestions and sources</p>'
        f'<div class="js-tailored-list">{"".join(bullets)}</div>'
        f"{skill_section}"
        f'<div class="js-honesty"><b>Honesty note</b><br>{escape(pack.honesty_note)}</div>'
        "</div>"
    )


def _tailor_footer_html(result: TailoringResult) -> str:
    """Render tailoring metadata without exposing trace links when disabled."""
    settings = get_settings()
    provider = model_provider(result.model)
    execution = (
        f"external model: {escape(provider)}"
        if provider and provider != "ollama"
        else "local model: Ollama"
    )
    if settings.has_opik:
        trace = (
            f'<a href="{result.opik_url or opik_url()}" '
            'target="_blank" rel="noopener">view traces in Opik ↗</a>'
        )
    else:
        trace = "tracing: disabled"
    if result.failed:
        return (
            '<div class="js-footer">run failed · '
            f"{escape(result.error_message)} · {trace} · {execution}</div>"
        )
    cost = (
        f"${result.cost_usd:.4f}"
        if result.cost_estimate_available
        else "cost: check provider dashboard"
    )
    flags = (
        result.fabrication_report.flags
        if result.fabrication_report is not None
        else "unavailable"
    )
    return (
        '<div class="js-footer">'
        f'<span class="js-meta-mono">{escape(cost)}</span> · '
        f'<span class="js-meta-mono">{result.latency_s}s</span> · '
        f"validator warnings: {flags} · {trace} · {execution}</div>"
    )


def _status(text: str, error: bool = False) -> str:
    """Render a status line on the start page."""
    cls = "js-status js-status-err" if error else "js-status"
    return f'<div class="{cls}">{escape(text)}</div>'


def _application_choices(
    records: list[ApplicationRecord] | None = None,
) -> list[tuple[str, str]]:
    """Return readable dropdown labels for locally tracked applications."""
    records = get_application_store().list() if records is None else records
    return [
        (f"{record.status} | {record.title} — {record.company}", record.job_id)
        for record in records
    ]


def _application_dashboard_html(
    records: list[ApplicationRecord] | None = None,
) -> str:
    """Render an escaped overview of locally tracked applications."""
    records = get_application_store().list() if records is None else records
    if not records:
        return (
            '<div class="js-card"><b>No saved applications yet.</b>'
            "<p>Run a search and save a ranked job to start tracking it.</p></div>"
        )

    rows = []
    for record in records:
        title = escape(record.title)
        parsed_url = urlparse(record.url)
        if parsed_url.scheme in {"http", "https"} and parsed_url.netloc:
            title = (
                f'<a href="{escape(record.url, quote=True)}" '
                f'target="_blank" rel="noopener noreferrer">{title}</a>'
            )
        notes = escape(record.notes)
        note_html = f"<br><small>{notes}</small>" if notes else ""
        rows.append(
            "<tr>"
            f"<td>{title}<br><small>{escape(record.company)}</small></td>"
            f"<td>{escape(record.status)}</td>"
            f'<td class="js-meta-mono">{record.fit_score}%</td>'
            f"<td>{escape(record.location)}{note_html}</td>"
            "</tr>"
        )
    return (
        '<div class="js-card"><div style="overflow-x:auto"><table>'
        "<thead><tr><th>Role</th><th>Status</th><th>Fit</th><th>Location / notes</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table></div></div>"
    )


def _selected_application_values(
    records: list[ApplicationRecord],
) -> tuple[str | None, str, str]:
    """Return the newest record's identifier and editable values."""
    if not records:
        return None, "Found", ""
    record = records[0]
    return record.job_id, record.status, record.notes


def refresh_application_tracker():
    """Reload the tracker controls and dashboard from SQLite."""
    records = get_application_store().list()
    selected, status, notes = _selected_application_values(records)
    return (
        gr.update(choices=_application_choices(records), value=selected),
        gr.update(value=status),
        notes,
        _application_dashboard_html(records),
        _status(f"Loaded {len(records)} saved application(s)."),
    )


def load_application(job_id: str | None):
    """Load the status and notes for one selected application."""
    if not job_id:
        return gr.update(value="Found"), ""
    record = get_application_store().get(job_id)
    if record is None:
        return gr.update(value="Found"), ""
    return gr.update(value=record.status), record.notes


def save_ranked_application(
    ranked_jobs: list[RankedJob] | list[dict] | None,
    job_id: str | None,
    status: str,
    notes: str,
):
    """Save one search result and refresh the shared tracker."""
    ranked = next(
        (
            item if isinstance(item, RankedJob) else RankedJob.model_validate(item)
            for item in (ranked_jobs or [])
            if (item.job.job_id if isinstance(item, RankedJob) else item.get("job", {}).get("job_id")) == job_id
        ),
        None,
    )
    if ranked is None:
        return (
            _status("Select a ranked job before saving.", error=True),
            gr.update(),
            gr.update(),
            gr.update(),
            gr.update(),
            "",
        )
    try:
        record = get_application_store().save(ranked, status=status, notes=notes)
    except ApplicationStoreError as exc:
        return (
            _status(str(exc), error=True),
            gr.update(),
            gr.update(),
            gr.update(),
            gr.update(),
            "",
        )
    records = get_application_store().list()
    return (
        _status(f"Saved {record.title} at {record.company}."),
        gr.update(choices=_application_choices(records), value=record.job_id),
        _application_dashboard_html(records),
        gr.update(value=record.status),
        record.notes,
        "",
    )


def update_application(job_id: str | None, status: str, notes: str):
    """Update a selected locally tracked application."""
    if not job_id:
        return _status("Select a saved application first.", error=True), gr.update(), gr.update()
    try:
        record = get_application_store().update(job_id, status=status, notes=notes)
    except ApplicationStoreError as exc:
        return _status(str(exc), error=True), gr.update(), gr.update()
    records = get_application_store().list()
    return (
        _status(f"Updated {record.title} to {record.status}."),
        gr.update(choices=_application_choices(records), value=record.job_id),
        _application_dashboard_html(records),
    )


def delete_application(job_id: str | None):
    """Delete a selected application after an explicit button click."""
    if not job_id:
        return (
            _status("Select a saved application first.", error=True),
            gr.update(),
            gr.update(),
            gr.update(),
            "",
        )
    store = get_application_store()
    deleted = store.delete(job_id)
    records = store.list()
    selected, status, notes = _selected_application_values(records)
    message = "Removed the application from the local tracker." if deleted else "Application was already removed."
    return (
        _status(message, error=not deleted),
        gr.update(choices=_application_choices(records), value=selected),
        _application_dashboard_html(records),
        gr.update(value=status),
        notes,
    )


def _cloud_warning_html(model: str) -> str:
    """Render an explicit external-data-transfer warning for cloud models."""
    provider = model_provider(model)
    if not provider or provider == "ollama":
        return ""
    return (
        '<div class="js-card js-status-err"><b>Cloud model active.</b> '
        f"Resume text and job content are sent to {escape(provider)}. "
        "Do not upload data you are not authorized to share.</div>"
    )


def _tailor_transfer_html(model: str) -> str:
    """Explain exactly where selected job and corpus content will be processed."""
    provider = model_provider(model)
    if provider and provider != "ollama":
        return (
            '<div class="js-card js-status-err"><b>External tailoring model.</b> '
            f"After confirmation, the selected job and temporary CV corpus are sent to "
            f"{escape(provider)} using <span class=\"js-meta-mono\">{escape(model)}</span>. "
            "Private tracker notes, API keys, the original PDF, and other jobs are not sent.</div>"
        )
    return (
        '<div class="js-card"><b>Local tailoring model.</b> '
        "After confirmation, the selected job and temporary CV corpus are processed "
        f"by local Ollama using <span class=\"js-meta-mono\">{escape(model)}</span>. "
        "Private tracker notes are not used.</div>"
    )


def _provider_status_html(provider: str, model_name: str) -> str:
    """Render non-secret readiness and data-transfer status for one selection."""
    try:
        selected_model = qualify_model(provider, model_name)
    except ModelConfigurationError as exc:
        return _status(str(exc), error=True)
    status = model_configuration_status(selected_model)
    css_class = "js-status" if status.ready and not status.external else "js-status js-status-err"
    readiness = "Ready" if status.ready else "Not ready"
    return (
        f'<div class="{css_class}"><b>{readiness}:</b> {escape(status.message)} '
        f'<span class="js-meta-mono">{escape(selected_model)}</span></div>'
    )


def on_provider_change(provider: str):
    """Clear a stale model identifier when the provider changes."""
    return gr.update(value=""), _provider_status_html(provider, "")


def on_upload(file_path: str | None, thread_id: str, provider: str, model_name: str):
    """Step 1 → 2: read the resume, extract the profile, and reveal the profile page.

    Outputs include page visibility, profile, model, and temporary corpus state.
    """
    stay = gr.update(visible=True), gr.update(visible=False)
    go = gr.update(visible=False), gr.update(visible=True)

    if not file_path:
        yield (*stay, gr.update(), _status("Please drop a PDF resume.", error=True), None, None, None)
        return
    try:
        selected_model = qualify_model(provider, model_name)
        validate_model_configuration(selected_model)
    except (ModelConfigurationError, OllamaRuntimeError) as exc:
        if get_settings().privacy_mode:
            delete_temporary_upload(file_path)
        yield (*stay, gr.update(), _status(f"Model is not ready: {exc}", error=True), None, None, None)
        return
    try:
        cv_text = extract_cv_text(file_path)
    except CVReadError as exc:
        yield (*stay, gr.update(), _status(f"Could not read that PDF: {exc}", error=True), None, None, None)
        return
    finally:
        if get_settings().privacy_mode:
            delete_temporary_upload(file_path)

    corpus = build_candidate_corpus(cv_text)
    yield (*go, _loading_html("Reading your resume…"), "", gr.update(), selected_model, gr.update())
    try:
        profile = extract_profile(
            cv_text,
            thread_id=thread_id,
            tags=["phase-1", "ui", "extract"],
            model_name=selected_model,
        )
    except Exception as exc:  # noqa: BLE001 - show a friendly error and return to start
        cv_text = ""
        corpus = []
        yield (*stay, gr.update(), _status(f"Couldn't read a profile: {exc}", error=True), None, None, None)
        return
    cv_text = ""
    yield (*go, _profile_html(profile), "", profile, selected_model, corpus)


def on_find(profile: Profile | None, thread_id: str, model_name: str | None):
    """Step 2 → 3: run the job-finding graph for the extracted profile and stream results.

    Outputs include page visibility, rendered results, both job selectors, and state.
    """
    go = gr.update(visible=False), gr.update(visible=True)
    if profile is None:
        yield (
            gr.update(visible=True),
            gr.update(visible=False),
            gr.update(),
            "",
            gr.update(),
            [],
            gr.update(),
            False,
        )
        return

    yield (
        *go,
        _loading_html("Searching for jobs…"),
        "",
        gr.update(),
        gr.update(),
        gr.update(),
        False,
    )
    result = RunResult()
    for kind, payload in stream_search(
        profile,
        thread_id=thread_id,
        tags=["phase-1", "ui"],
        model_name=model_name,
    ):
        if kind == "status":
            yield (
                *go,
                _loading_html(str(payload)),
                "",
                gr.update(),
                gr.update(),
                gr.update(),
                False,
            )
        elif kind == "result":
            result = payload  # type: ignore[assignment]

    choices = [
        (f"{ranked.job.title} — {ranked.job.company}", ranked.job.job_id)
        for ranked in result.ranked_jobs
    ]
    selected = choices[0][1] if choices else None
    yield (
        *go,
        _results_html(result),
        _footer_html(result),
        gr.update(choices=choices, value=selected),
        result.ranked_jobs,
        gr.update(choices=choices, value=None, interactive=bool(choices)),
        False,
    )


def on_tailor(
    profile: Profile | dict | None,
    ranked_jobs: list[RankedJob] | list[dict] | None,
    candidate_corpus: list[CorpusItem] | list[dict] | None,
    selected_job_id: str | None,
    confirmed: bool,
    thread_id: str,
    previous_pdf_path: str | None = None,
):
    """Step 3 → 4 after explicit selection and one-run data-transfer consent."""
    stay = gr.update(visible=True), gr.update(visible=False)
    go = gr.update(visible=False), gr.update(visible=True)
    unchanged = tuple(gr.update() for _ in range(7))

    if not selected_job_id:
        yield (*stay, *unchanged, _status("Select one job before tailoring.", error=True))
        return
    if not confirmed:
        yield (
            *stay,
            *unchanged,
            _status("Confirm this specific tailoring run before any job or CV content is processed.", error=True),
        )
        return
    try:
        parsed_profile = (
            profile
            if isinstance(profile, Profile)
            else Profile.model_validate(profile)
        )
        parsed_jobs = [
            item if isinstance(item, RankedJob) else RankedJob.model_validate(item)
            for item in (ranked_jobs or [])
        ]
        parsed_corpus = [
            item if isinstance(item, CorpusItem) else CorpusItem.model_validate(item)
            for item in (candidate_corpus or [])
        ]
    except Exception:  # noqa: BLE001 - corrupted session state must remain local
        yield (
            *stay,
            *unchanged,
            _status("Tailoring session data is invalid. Start over and upload the resume again.", error=True),
        )
        return
    if not any(item.job.job_id == selected_job_id for item in parsed_jobs):
        yield (
            *stay,
            *unchanged,
            _status("The selected job is no longer available in this search.", error=True),
        )
        return
    if not parsed_corpus:
        yield (
            *stay,
            *unchanged,
            _status("The temporary CV corpus is unavailable. Upload the resume again.", error=True),
        )
        return

    model_name = get_settings().scout_tailor_model
    try:
        validate_model_configuration(model_name)
    except (ModelConfigurationError, OllamaRuntimeError) as exc:
        yield (
            *stay,
            *unchanged,
            _status(f"Tailoring model is not ready: {exc}", error=True),
        )
        return

    if previous_pdf_path:
        delete_temporary_upload(previous_pdf_path)
    yield (
        *go,
        _loading_html("Preparing the application draft…"),
        "",
        gr.update(value=None, visible=False),
        "",
        "",
        None,
        None,
        "",
    )
    result = TailoringResult(
        selected_job_id=selected_job_id,
        model=model_name,
    )
    for kind, payload in stream_tailoring(
        parsed_profile,
        parsed_jobs,
        parsed_corpus,
        selected_job_id=selected_job_id,
        thread_id=thread_id,
        tags=["phase-2", "ui", "tailor"],
        model_name=model_name,
    ):
        if kind == "status":
            yield (
                *go,
                _loading_html(str(payload)),
                "",
                gr.update(value=None, visible=False),
                "",
                "",
                None,
                None,
                "",
            )
        elif kind == "result":
            result = payload  # type: ignore[assignment]

    cover_letter = result.tailoring.cover_letter if result.tailoring else ""
    pdf_path: str | None = None
    pdf_download = gr.update(value=None, visible=False)
    pdf_status = ""
    if result.tailoring is not None:
        selected_job = next(
            item for item in parsed_jobs if item.job.job_id == selected_job_id
        )
        try:
            rendered_path = render_application_pdf(
                parsed_profile,
                selected_job,
                parsed_corpus,
                result,
                thread_id=thread_id,
            )
            pdf_path = str(rendered_path)
            pdf_download = gr.update(value=pdf_path, visible=True)
        except ApplicationPdfError:
            pdf_status = _status(
                "The application text is ready, but the local PDF could not be created. "
                "You can still copy the cover letter and review the source-linked suggestions.",
                error=True,
            )
    yield (
        *go,
        _tailoring_html(result, parsed_corpus),
        cover_letter,
        pdf_download,
        pdf_status,
        _tailor_footer_html(result),
        result,
        pdf_path,
        "",
    )


def on_tailor_job_change():
    """A new selection requires a new explicit confirmation."""
    return False, ""


def back_to_jobs():
    """Return to ranked jobs and invalidate the previous confirmation."""
    return (
        gr.update(visible=True),
        gr.update(visible=False),
        False,
        "",
    )


def reset(application_pdf_path: str | None = None):
    """Return to step 1 and clear the wizard.

    Outputs include all four pages, cleared content, a fresh thread, and
    temporary session state.
    """
    if application_pdf_path:
        delete_temporary_upload(application_pdf_path)
    return (
        gr.update(visible=True),
        gr.update(visible=False),
        gr.update(visible=False),
        gr.update(visible=False),
        None,
        "",
        "",
        "",
        None,
        None,
        gr.update(choices=[], value=None),
        [],
        [],
        gr.update(choices=[], value=None),
        False,
        "",
        "",
        "",
        gr.update(value=None, visible=False),
        "",
        "",
        None,
        None,
        str(uuid4()),
    )


def build_app() -> gr.Blocks:
    """Build the four-step wizard app."""
    register_prompts()
    settings = get_settings()
    mode_caption = "Offline mode: local model and cache only" if settings.offline_mode else CAPTION
    if settings.privacy_mode:
        mode_caption = f"{mode_caption} | Privacy mode: resume data minimized"
    provider = model_provider(settings.scout_model) or "ollama"
    model_name = settings.scout_model.partition(":")[2].strip()

    with gr.Blocks(title="the-agent-that-got-me-rejected") as demo:
        thread_id = gr.State(lambda: str(uuid4()))
        profile_state = gr.State(None)
        selected_model_state = gr.State(None)
        ranked_jobs_state = gr.State([])
        corpus_state = gr.State([])
        tailoring_result_state = gr.State(None)
        application_pdf_state = gr.State(None)

        gr.HTML(
            f'<div id="js-header"><div class="js-mark">{_MARK}<h1>the-agent-that-got-me-rejected</h1></div>'
            f'<div><span class="js-tag">{mode_caption}</span></div></div>'
        )
        saved_records = get_application_store().list()
        saved_id, saved_status, saved_notes = _selected_application_values(saved_records)
        with gr.Accordion("Application tracker", open=False):
            tracked_job_input = gr.Dropdown(
                choices=_application_choices(saved_records),
                value=saved_id,
                label="Saved application",
                interactive=True,
            )
            with gr.Row():
                tracked_status_input = gr.Dropdown(
                    choices=list(APPLICATION_STATUSES),
                    value=saved_status,
                    label="Status",
                    interactive=True,
                )
                tracked_notes_input = gr.Textbox(
                    value=saved_notes,
                    label="Private local notes",
                    max_lines=4,
                )
            with gr.Row():
                update_application_btn = gr.Button("Update application", variant="primary")
                refresh_applications_btn = gr.Button("Refresh")
                delete_application_btn = gr.Button("Remove", variant="stop")
            tracker_status = gr.HTML()
            tracker_dashboard = gr.HTML(_application_dashboard_html(saved_records))

        with gr.Group(visible=True) as page_start:
            gr.HTML(_stepper(1))
            gr.HTML(INTRO_HTML)
            gr.HTML('<p class="js-section-label">Model provider</p>')
            with gr.Row():
                provider_input = gr.Dropdown(
                    choices=PROVIDERS,
                    value=provider,
                    label="Provider",
                    interactive=True,
                )
                model_input = gr.Textbox(
                    value=model_name,
                    label="Model identifier",
                    placeholder="Enter the provider model identifier",
                )
            provider_status = gr.HTML(_provider_status_html(provider, model_name))
            cv_file = gr.File(label="", file_types=[".pdf"], type="filepath", height=150, elem_classes=["js-drop"])
            start_status = gr.HTML('<div class="js-status"></div>')

        with gr.Group(visible=False) as page_profile:
            gr.HTML(_stepper(2))
            gr.HTML('<p class="js-section-label">Your profile</p>')
            profile_out = gr.HTML()
            find_btn = gr.Button("Find jobs", variant="primary", size="lg")
            change_btn = gr.Button("Upload a different resume", variant="secondary")

        with gr.Group(visible=False) as page_results:
            gr.HTML(_stepper(3))
            gr.HTML('<p class="js-section-label">Ranked jobs</p>')
            results_out = gr.HTML()
            footer_out = gr.HTML()
            gr.HTML('<p class="js-section-label" style="margin-top:16px">Prepare an application</p>')
            tailor_job_input = gr.Dropdown(
                choices=[],
                value=None,
                label="Select exactly one ranked job",
                interactive=True,
            )
            gr.HTML(_tailor_transfer_html(settings.scout_tailor_model))
            tailor_consent_input = gr.Checkbox(
                value=False,
                label=(
                    "I selected this job and confirm this one tailoring run. "
                    "I understand where the selected job and temporary CV corpus will be processed."
                ),
            )
            tailor_btn = gr.Button("Prepare application draft", variant="primary", size="lg")
            tailor_status = gr.HTML()
            with gr.Accordion("Save to application tracker", open=False):
                result_job_input = gr.Dropdown(
                    choices=[],
                    label="Ranked job",
                    interactive=True,
                )
                result_status_input = gr.Dropdown(
                    choices=list(APPLICATION_STATUSES),
                    value="Interested",
                    label="Status",
                    interactive=True,
                )
                result_notes_input = gr.Textbox(
                    label="Private local notes",
                    max_lines=4,
                    placeholder="Optional next step, contact, or interview note",
                )
                save_application_btn = gr.Button("Save application", variant="primary")
                save_application_status = gr.HTML()
            restart_btn = gr.Button("Start over", variant="secondary")

        with gr.Group(visible=False) as page_tailor:
            gr.HTML(_stepper(4))
            gr.HTML('<p class="js-section-label">Application review</p>')
            tailor_out = gr.HTML()
            cover_letter_out = gr.Textbox(
                label="Cover letter draft",
                lines=14,
                interactive=False,
                buttons=["copy"],
            )
            application_pdf_out = gr.DownloadButton(
                label="Download application review PDF",
                value=None,
                visible=False,
                variant="primary",
            )
            application_pdf_status = gr.HTML()
            tailor_footer = gr.HTML()
            back_btn = gr.Button("Back to jobs", variant="secondary")
            restart_btn_tailor = gr.Button("Start over", variant="secondary")

        provider_input.change(
            on_provider_change,
            inputs=[provider_input],
            outputs=[model_input, provider_status],
        )
        model_input.change(
            _provider_status_html,
            inputs=[provider_input, model_input],
            outputs=[provider_status],
        )
        cv_file.upload(
            on_upload,
            inputs=[cv_file, thread_id, provider_input, model_input],
            outputs=[
                page_start,
                page_profile,
                profile_out,
                start_status,
                profile_state,
                selected_model_state,
                corpus_state,
            ],
        )
        find_btn.click(
            on_find,
            inputs=[profile_state, thread_id, selected_model_state],
            outputs=[
                page_profile,
                page_results,
                results_out,
                footer_out,
                result_job_input,
                ranked_jobs_state,
                tailor_job_input,
                tailor_consent_input,
            ],
        )
        tailor_job_input.change(
            on_tailor_job_change,
            outputs=[tailor_consent_input, tailor_status],
        )
        tailor_btn.click(
            on_tailor,
            inputs=[
                profile_state,
                ranked_jobs_state,
                corpus_state,
                tailor_job_input,
                tailor_consent_input,
                thread_id,
                application_pdf_state,
            ],
            outputs=[
                page_results,
                page_tailor,
                tailor_out,
                cover_letter_out,
                application_pdf_out,
                application_pdf_status,
                tailor_footer,
                tailoring_result_state,
                application_pdf_state,
                tailor_status,
            ],
        )
        back_btn.click(
            back_to_jobs,
            outputs=[
                page_results,
                page_tailor,
                tailor_consent_input,
                tailor_status,
            ],
        )
        tracked_job_input.change(
            load_application,
            inputs=[tracked_job_input],
            outputs=[tracked_status_input, tracked_notes_input],
        )
        refresh_applications_btn.click(
            refresh_application_tracker,
            outputs=[
                tracked_job_input,
                tracked_status_input,
                tracked_notes_input,
                tracker_dashboard,
                tracker_status,
            ],
        )
        update_application_btn.click(
            update_application,
            inputs=[tracked_job_input, tracked_status_input, tracked_notes_input],
            outputs=[tracker_status, tracked_job_input, tracker_dashboard],
        )
        delete_application_btn.click(
            delete_application,
            inputs=[tracked_job_input],
            outputs=[
                tracker_status,
                tracked_job_input,
                tracker_dashboard,
                tracked_status_input,
                tracked_notes_input,
            ],
        )
        save_application_btn.click(
            save_ranked_application,
            inputs=[ranked_jobs_state, result_job_input, result_status_input, result_notes_input],
            outputs=[
                save_application_status,
                tracked_job_input,
                tracker_dashboard,
                tracked_status_input,
                tracked_notes_input,
                result_notes_input,
            ],
        )
        reset_outputs = [
            page_start,
            page_profile,
            page_results,
            page_tailor,
            cv_file,
            start_status,
            results_out,
            footer_out,
            profile_state,
            selected_model_state,
            result_job_input,
            ranked_jobs_state,
            corpus_state,
            tailor_job_input,
            tailor_consent_input,
            tailor_status,
            tailor_out,
            cover_letter_out,
            application_pdf_out,
            application_pdf_status,
            tailor_footer,
            tailoring_result_state,
            application_pdf_state,
            thread_id,
        ]
        change_btn.click(reset, inputs=[application_pdf_state], outputs=reset_outputs)
        restart_btn.click(reset, inputs=[application_pdf_state], outputs=reset_outputs)
        restart_btn_tailor.click(
            reset,
            inputs=[application_pdf_state],
            outputs=reset_outputs,
        )

    return demo


def main() -> None:
    """Launch the Gradio app."""
    build_app().launch(theme=THEME, css=CSS)


if __name__ == "__main__":
    main()
