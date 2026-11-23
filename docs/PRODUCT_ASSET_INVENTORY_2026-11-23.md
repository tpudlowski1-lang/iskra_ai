# Product asset inventory — 2026-11-23

## Scope and evidence

This inventory is a repository snapshot, not a complete IP or legal audit.

- Repository: `tpudlowski1-lang/iskra_ai`.
- Base commit inspected: `6b49760a2274464c1b0f787b850f60c8c4e014f8`.
- Git tree object: `34e95a731dd8bc91a2e2f4ea3369d88f95035450`.
- Recursive Git tree response: 99 tracked entries; GitHub reported `truncated=false`.
- No tracked files matched common bundled asset/model extensions: WOFF/WOFF2, TTF/OTF, PNG/JPEG/WebP/SVG/ICO, ONNX, safetensors, GGUF, PT/PTH, model or binary weight files.
- No tracked paths matched model/tokenizer/embedding/font/assets/static naming patterns in this snapshot.
- `requirements.txt` contains Flask, Flask-Limiter, requests, Gunicorn, Psycopg binary, pypdf and defusedxml; it does not declare local model runtimes such as PyTorch, Transformers or sentence-transformers.
- The dashboard HTML/CSS is embedded in `app.py` and uses a generic system sans-serif font; no bundled font or image asset was identified.

## Findings

1. The inspected source snapshot does not contain bundled model weights, tokenizer files, embedding models, fonts, icons or frontend image assets requiring a separate per-file license review.
2. The current LLM integration calls external hosted providers; their API terms and data handling are tracked separately in `docs/LLM_PROVIDER_DATA_HANDLING.md` on the privacy review branch.
3. The product plan describes a future RAG/embedding feature. Any future embedding model, tokenizer, reranker, dataset, vector database extension or downloaded weight must be added to the IP/license register before use or redistribution.
4. Inline HTML/CSS and source code remain subject to the repository's own license and any copied/third-party snippets; this inventory does not establish provenance for every line of code.

## Limitations

- The result applies only to the exact inspected commit/tree, not other branches, future commits, generated release bundles, hosting images, OS packages, runtime downloads, user-provided documents, or external provider infrastructure.
- Filename/extension scans cannot detect vendored assets hidden under unusual names or embedded in source files.
- The absence of local model weights does not remove the need to review hosted model provider terms, customer data processing, output usage restrictions, and API agreements.
- This is not a legal opinion or proof that the entire product is free of third-party IP obligations.

## Release gate

Keep the commercial IP/license gate open until the reviewer has:
- reconciled this snapshot with the final release artifact and deployment/container SBOM;
- reviewed the Python dependency license inventory and the two Psycopg LGPL-3.0-only declarations;
- checked source provenance, copied snippets, future model/embedding/tokenizer/dataset licenses and all external provider terms;
- preserved all required license, copyright and NOTICE texts with the commercial release.

**Status: no bundled model/font/image assets found in the inspected tracked tree; full IP/license clearance NOT COMPLETE.**
