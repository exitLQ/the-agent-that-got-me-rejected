## Summary

Describe the problem and the solution in a few sentences.

## Change type

- [ ] Bug fix
- [ ] Feature
- [ ] Refactor
- [ ] Documentation
- [ ] Tests or CI
- [ ] Dependency update

## Validation

List the exact commands and manual checks that were run.

```text
uv lock --check
uv run ruff check .
uv run python scripts/check_repository.py
uv run pytest
uv build
```

## Privacy and network review

- [ ] Offline mode still prevents external job-provider and tracing requests.
- [ ] Cloud model use still requires explicit consent and the matching key.
- [ ] No credentials, resume content, personal data, or local `.env` file are included.
- [ ] New external requests, stored data, and third-party services are documented.
- [ ] Untrusted job and resume content is treated as data, not instructions.

## Documentation and compatibility

- [ ] User-visible behavior and configuration changes are documented in English.
- [ ] Documentation contains no emojis.
- [ ] The sponsor block is unchanged.
- [ ] Tests cover the changed behavior.
- [ ] The change targets Python 3.12 and the locked dependency set.

## Additional notes

Document limitations, migration steps, screenshots, or follow-up work.
