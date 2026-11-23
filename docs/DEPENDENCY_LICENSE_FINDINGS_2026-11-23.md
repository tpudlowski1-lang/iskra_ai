# Python dependency license inventory — initial findings (2026-11-23)

## Evidence

- Workflow: [Iskra Python dependency license inventory, run 45118521065](https://github.com/tpudlowski1-lang/iskra_ai/actions/runs/45118521065).
- Artifact: `python-dependency-license-inventory`, artifact ID `14792457985`.
- Environment: Python 3.12, runtime dependencies installed from `requirements.txt`.
- Report: 28 installed Python distributions; license text and available NOTICE files were collected.

This is an inventory snapshot for the tested requirements lock state, not a complete software bill of materials or legal opinion.

## Findings requiring explicit review

| Package | Version | Declared license expression | Required action |
|---|---:|---|---|
| `psycopg` | 3.3.9 | LGPL-3.0-only | Legal review of distribution and linking model; preserve applicable license/notice obligations |
| `psycopg-binary` | 3.3.9 | LGPL-3.0-only | Legal review of binary wheel redistribution and notices |
| `certifi` | 2026.11.20 | MPL-2.0 | Review notice and any modified-file/source obligations if redistributed or modified |
| `packaging` | 26.3 | Apache-2.0 OR BSD-2-Clause | Record selected applicable license path and include required notices |

Other packages in this snapshot report MIT/MIT License, BSD-family, PSFL or PSF-2.0 declarations. The exact per-package evidence and bundled license texts are in the CI artifact.

The two Psycopg packages are not automatically prohibited. Their LGPL-3.0-only declarations are a material distribution consideration and require qualified review for the actual deployment and packaging model. Do not change the database driver or claim compliance based only on this table.

## Metadata completeness

No distribution in this 28-package snapshot lacked all three of: license expression, license metadata, and license classifier. Some fields individually say `UNKNOWN`; review the best available declared expression and bundled license text. Metadata can be incomplete or inaccurate.

## Release gate

Before a commercial distribution:
1. Review exact package and version license texts, including both Psycopg distributions.
2. Decide whether Iskra is delivered as hosted SaaS, customer-hosted image, desktop/mobile package, or a combination; distribution obligations differ.
3. Preserve required copyright, LICENSE and NOTICE texts with each relevant release.
4. Review operating-system/container packages, model providers and weights, embedding models, datasets, fonts, icons, images, copied code and runtime downloads separately.
5. Record reviewer, review date, decision and evidence in the product IP/license register.

**Status: preliminary inventory generated; commercial license clearance NOT COMPLETE.**
