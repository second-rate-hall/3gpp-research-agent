# Publishing Checklist

- Confirm `.env` is not committed.
- Confirm no real API key appears in git history.
- Confirm generated 3GPP materials under `data/` are ignored.
- Add `LICENSE`.
- Add `CHANGELOG.md`.
- Run smoke test without API key.
- Run `ask` test with a valid local `NVIDIA_API_KEY`.
- Create GitHub repo, e.g. `3gpp-research-agent`.

Recommended repository description:

```text
Dedicated local 3GPP standards research agent powered by NVIDIA NIM and official evidence retrieval.
```
