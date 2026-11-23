# Python dependency license inventory

## Purpose

The `Iskra Python dependency license inventory` workflow creates a machine-readable inventory of the Python packages installed from the pinned runtime requirements. It includes package name/version, declared license information, project URLs, and available license/NOTICE file contents. The JSON is uploaded as the `python-dependency-license-inventory` GitHub Actions artifact for 30 days.

## How to review

1. Open the workflow run for the release candidate SHA.
2. Download `python-dependency-license-inventory`.
3. Review every direct and transitive package, version, license expression/classifier, upstream URL and available license/NOTICE text.
4. Resolve UNKNOWN/missing metadata by checking the exact upstream release and distribution archive; do not infer a license from a repository name.
5. Record attribution, redistribution, copyleft, NOTICE and source-offer obligations in the product's legal inventory.
6. Repeat when dependencies or pinned versions change.

## Scope and limits

- The report covers Python distributions installed from `requirements.txt` in the CI environment. It is not a full SBOM and does not include operating-system packages, container base images, external services, model weights, embeddings, datasets, fonts, icons, images, copied code, or runtime downloads not installed by that requirements file.
- Metadata and bundled license files are evidence for human review, not a legal opinion. Package metadata can be incomplete, stale or inaccurate.
- A successful workflow means the inventory was generated and attached; it does not mean all licenses have been approved for commercial use.
- The artifact is temporary CI output retained for 30 days. Before a commercial release, preserve the reviewed inventory and required license/NOTICE texts with the release package and record reviewer/date.
- No dependency is automatically accepted, removed or blocked solely based on a license label. Legal review must consider the exact package, version, use, distribution model and applicable terms.

## Release gate

The commercial-readiness checklist remains blocked until a reviewer has reconciled the generated report with the complete product asset/model/data inventory and documented commercial-use rights and attribution obligations. This workflow is an evidence-gathering control only.
