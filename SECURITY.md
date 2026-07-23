# Security Policy

## Supported versions

This project is currently maintained from the `main` branch.

| Version | Security updates |
|---|---|
| Latest commit on `main` | Supported |
| Older commits and forks | Not supported |

## Reporting a vulnerability

Do not open a public issue for a suspected vulnerability.

Use GitHub's private vulnerability reporting feature:

1. Open the repository's **Security** page.
2. Open **Advisories**.
3. Select **Report a vulnerability**.
4. Provide the affected component, impact, reproduction steps, and any proposed
   mitigation.

Repository link:
[Report a vulnerability privately](https://github.com/exitLQ/the-agent-that-got-me-rejected/security/advisories/new)

Do not include real API keys, resume content, personal data, or third-party
credentials in the report. Use synthetic examples and redact sensitive values.

If the private reporting button is unavailable, contact the maintainer through
the contact options on the [exitLQ GitHub profile](https://github.com/exitLQ).
Share only enough information to request a private channel. Do not disclose
technical vulnerability details publicly.

## What to include

A useful report contains:

- a concise description of the vulnerability;
- the affected commit, file, function, or configuration;
- prerequisites and a minimal reproduction;
- the expected and observed behavior;
- the security and privacy impact;
- whether exploitation requires a cloud provider, local service, or uploaded
  file; and
- a suggested fix, if available.

## Response process

The maintainer will:

1. acknowledge the report when it is reviewed;
2. validate the impact and affected versions;
3. coordinate questions and remediation privately;
4. prepare tests and a fix;
5. publish an advisory when disclosure is appropriate; and
6. credit the reporter when requested and safe to do so.

Response and remediation time depend on severity, reproducibility, and
maintainer availability. Please allow a reasonable private remediation period
before public disclosure.

## Security boundaries

The project treats the following areas as security-sensitive:

- API-key and `.env` handling;
- offline-mode and cloud-consent enforcement;
- resume upload retention and deletion;
- prompt injection and untrusted job content;
- external job-source and model-provider requests;
- dependency and GitHub Actions integrity; and
- trace data and attachments.

Reports about ordinary matching quality, stale job data, expected model
hallucinations, or unsupported deployment configurations are usually bugs
rather than security vulnerabilities and should use the issue tracker.
