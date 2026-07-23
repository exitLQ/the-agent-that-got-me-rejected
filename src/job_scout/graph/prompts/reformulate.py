"""Prompt for the query-reformulation node (see prompts/__init__.py)."""

REFORMULATE_PROMPT_NAME = "reformulate"

REFORMULATE_PROMPT = """The previous job search returned too few good matches. Produce one broader, materially different job-search query.

Rules:
- Return 2 to 8 role and skill terms only.
- Do not include a location, employer, salary, explanation, label, or Boolean syntax.
- Do not repeat or merely reorder a previous query.
- On attempt 1, prefer a common adjacent job title and at most one strong skill.
- On attempt 2, remove niche specialization and use a broad established role family.

Candidate profile:
{profile}

Previous search query:
{previous_query}

Queries already tried:
{query_history}

Observed result quality:
{diagnostics}

Reformulation attempt:
{attempt}

Return only the new search query text, nothing else.
"""
