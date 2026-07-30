"""Create a local, source-linked application review PDF with fpdf2.

The renderer consumes only validated session models. It writes a transient,
non-submission-ready review document and never sends content to another
service. PDF failures are reported to the UI without invalidating the
successfully generated text draft.
"""

from __future__ import annotations

import hashlib
import re
import tempfile
from pathlib import Path

from fpdf import FPDF
from fpdf.enums import WrapMode, XPos, YPos

from job_scout.corpus import CorpusItem
from job_scout.graph.schemas import Profile, RankedJob
from job_scout.runner import TailoringResult

_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_LONG_TOKEN = re.compile(r"\S{48,}")
_PUNCTUATION = str.maketrans(
    {
        "\u2010": "-",
        "\u2011": "-",
        "\u2012": "-",
        "\u2013": "-",
        "\u2014": "-",
        "\u2018": "'",
        "\u2019": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u2022": "-",
        "\u2026": "...",
    }
)


class ApplicationPdfError(RuntimeError):
    """Raised when a validated application package cannot be rendered."""


class _ApplicationPdf(FPDF):
    """Small fpdf2 document with a stable footer."""

    def footer(self) -> None:
        self.set_y(-12)
        self.set_font("Helvetica", size=8)
        self.set_text_color(100, 100, 100)
        self.cell(
            w=0,
            h=5,
            text=f"Local review draft - page {self.page_no()}",
            align="C",
        )


def _pdf_text(value: object) -> str:
    """Return core-font-safe text without executable PDF control characters."""
    text = _CONTROL.sub("", str(value).replace("\r\n", "\n").replace("\r", "\n"))
    text = text.translate(_PUNCTUATION)
    text = text.encode("latin-1", errors="replace").decode("latin-1")
    return _LONG_TOKEN.sub(
        lambda match: " ".join(
            match.group()[start : start + 47]
            for start in range(0, len(match.group()), 47)
        ),
        text,
    )


def _paragraph(pdf: FPDF, text: object, *, line_height: float = 5.2) -> None:
    pdf.multi_cell(
        w=0,
        h=line_height,
        text=_pdf_text(text),
        new_x=XPos.LMARGIN,
        new_y=YPos.NEXT,
        wrapmode=WrapMode.WORD,
    )
    pdf.ln(1.5)


def _section(pdf: FPDF, title: str) -> None:
    pdf.ln(2)
    pdf.set_font("Helvetica", style="B", size=13)
    pdf.set_text_color(14, 110, 74)
    _paragraph(pdf, title, line_height=6)
    pdf.set_font("Helvetica", size=10)
    pdf.set_text_color(32, 31, 29)


def _bullet(pdf: FPDF, text: object) -> None:
    _paragraph(pdf, f"- {text}")


def _draft_path(thread_id: str) -> Path:
    """Return a PII-free path derived from the opaque UI thread identifier."""
    token = hashlib.sha256(thread_id.encode("utf-8")).hexdigest()[:20]
    root = Path(tempfile.gettempdir()) / "job-scout-application-drafts"
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    return root / f"application-draft-{token}.pdf"


def render_application_pdf(
    profile: Profile,
    selected_job: RankedJob,
    candidate_corpus: list[CorpusItem],
    result: TailoringResult,
    *,
    thread_id: str,
    output_path: str | Path | None = None,
) -> Path:
    """Render one local application review package and return its PDF path.

    The selected IDs must agree before any file is written. User-derived values
    are treated only as text, converted to the built-in font encoding, and
    wrapped at character boundaries so unusually long tokens cannot break the
    layout.
    """
    pack = result.tailoring
    job_id = selected_job.job.job_id
    if pack is None:
        raise ApplicationPdfError("No application draft is available for PDF export.")
    if result.selected_job_id != job_id or pack.selected_job_id != job_id:
        raise ApplicationPdfError("The application draft does not match the selected job.")

    path = Path(output_path) if output_path is not None else _draft_path(thread_id)
    temporary_path = path.with_suffix(".tmp")
    corpus_by_id = {item.item_id: item for item in candidate_corpus}

    try:
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        pdf = _ApplicationPdf(orientation="P", unit="mm", format="A4")
        pdf.set_margins(18, 16, 18)
        pdf.set_auto_page_break(auto=True, margin=17)
        pdf.set_title(_pdf_text("Application review draft"))
        pdf.set_author(_pdf_text(profile.name or "Candidate"))
        pdf.add_page()

        pdf.set_fill_color(14, 110, 74)
        pdf.rect(x=0, y=0, w=210, h=8, style="F")
        pdf.set_font("Helvetica", style="B", size=20)
        pdf.set_text_color(32, 31, 29)
        _paragraph(pdf, "Application review draft", line_height=9)
        pdf.set_font("Helvetica", style="B", size=11)
        _paragraph(
            pdf,
            f"{selected_job.job.title} at {selected_job.job.company}",
            line_height=6,
        )
        pdf.set_font("Helvetica", size=9)
        pdf.set_text_color(110, 74, 24)
        _paragraph(
            pdf,
            "Review every claim before use. This file is prepared locally and is never submitted automatically.",
        )

        _section(pdf, "Cover letter draft")
        _paragraph(pdf, pack.cover_letter)

        _section(pdf, "Tailored CV draft")
        pdf.set_font("Helvetica", style="B", size=16)
        _paragraph(pdf, profile.name or "Candidate", line_height=7)
        pdf.set_font("Helvetica", size=10)
        if profile.raw_summary:
            _paragraph(pdf, profile.raw_summary)

        if pack.selected_skills:
            pdf.set_font("Helvetica", style="B", size=10)
            _paragraph(pdf, "Selected skills")
            pdf.set_font("Helvetica", size=10)
            _paragraph(pdf, " | ".join(item.name for item in pack.selected_skills))

        pdf.set_font("Helvetica", style="B", size=10)
        _paragraph(pdf, "Experience emphasis")
        pdf.set_font("Helvetica", size=10)
        for item in pack.tailored_bullets:
            _bullet(pdf, item.text)

        _section(pdf, "Source evidence")
        for item in pack.tailored_bullets:
            pdf.set_font("Helvetica", style="B", size=9)
            _paragraph(pdf, item.text)
            pdf.set_font("Helvetica", size=9)
            for reference in item.corpus_refs:
                source = corpus_by_id.get(reference)
                source_text = source.text if source is not None else "Source item unavailable."
                _bullet(pdf, f"{reference}: {source_text}")

        if pack.selected_skills:
            pdf.set_font("Helvetica", style="B", size=9)
            _paragraph(pdf, "Skill sources")
            pdf.set_font("Helvetica", size=9)
            for item in pack.selected_skills:
                source = corpus_by_id.get(item.corpus_ref)
                source_text = source.text if source is not None else "Source item unavailable."
                _bullet(pdf, f"{item.name} [{item.corpus_ref}]: {source_text}")

        _section(pdf, "Honesty and validation")
        _paragraph(pdf, pack.honesty_note)
        report = result.fabrication_report
        if report is None:
            _paragraph(
                pdf,
                "Validation report unavailable. Do not use this draft until its claims have been checked.",
            )
        elif report.flags == 0:
            _paragraph(
                pdf,
                (
                    f"No claims were flagged in {report.claims_checked} deterministic checks. "
                    "This is not a guarantee of truth."
                ),
            )
        else:
            _paragraph(
                pdf,
                f"{report.flags} of {report.claims_checked} checked claims require review.",
            )
            for flag in report.flagged:
                refs = f" Sources: {', '.join(flag.corpus_refs)}." if flag.corpus_refs else ""
                _bullet(
                    pdf,
                    f"{flag.claim_type} at {flag.where}: {flag.text} Reason: {flag.reason}.{refs}",
                )

        pdf_bytes = pdf.output()
        if not pdf_bytes:
            raise ApplicationPdfError("The PDF renderer returned an empty document.")
        temporary_path.write_bytes(bytes(pdf_bytes))
        temporary_path.replace(path)
    except ApplicationPdfError:
        temporary_path.unlink(missing_ok=True)
        raise
    except Exception as exc:
        temporary_path.unlink(missing_ok=True)
        raise ApplicationPdfError("The application PDF could not be created.") from exc

    return path
