"""Prompt for the profile-extraction node.

First-draft quality on purpose (see prompts/__init__.py). Registered in the Opik
prompt library under EXTRACT_PROFILE_PROMPT_NAME.
"""

EXTRACT_PROFILE_PROMPT_NAME = "extract_profile"

EXTRACT_PROFILE_PROMPT = """You are a recruiting assistant. Read the CV text below and extract a structured candidate profile.

Fill in every field:
- name: the candidate's name, or null if not present.
- seniority: one of junior, mid, senior, lead, or unknown.
- primary_roles: the job titles/roles this person is a fit for.
- skills: a list of their skills, lowercased.
- years_experience: total years of professional experience as a number, or null.
- locations: locations where they could work.
- languages: spoken languages.
- remote_ok: true if they are open to remote work.
- raw_summary: a 3-4 sentence summary of the candidate.

CV text:
{cv_text}
"""
