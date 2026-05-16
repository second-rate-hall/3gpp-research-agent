# Contributing

Contributions should preserve the core project rule: no confirmed 3GPP conclusion without official evidence.

Useful contribution areas:

- Better CR / TDoc / Meeting Report metadata extraction.
- 3GPP Portal search adapters.
- Clause-aware chunking.
- GraphRAG relation extraction.
- Additional smoke tests.
- Better NVIDIA model configuration examples.

Do not commit:

- API keys.
- `.env`.
- Large downloaded 3GPP materials.
- Generated databases under `data/index/`.

Before submitting a change, run:

```bash
python -m py_compile agent3gpp/store.py agent3gpp/nvidia_client.py agent3gpp/agent.py agent3gpp/__main__.py
python -m agent3gpp --help
python -m agent3gpp search RRCSetup --limit 1
```
