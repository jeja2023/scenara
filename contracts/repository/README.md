# Scenara cross-repository contracts

The published contract package is `@scenara/repository-contracts` version `1.0.0`. It contains one Draft 2020-12 JSON Schema and one valid example for each cross-repository payload, plus a checksummed manifest.

## Contracts

| Contract | Producer | Consumer | Transport |
|---|---|---|---|
| `model-package-admission` | `scenara-model` | `scenara` | immutable manifest |
| `deployment-feedback` | `scenara` | `scenara-model` | event / signed webhook |
| `hard-sample-handoff` | `scenara` | `scenara-data` | immutable manifest |
| `dataset-version-input` | `scenara-data` | `scenara-model` | versioned API |

`release-index.json` locks every published manifest by SHA-256. A published directory is immutable; incompatible changes require a new major release, while backward-compatible additions require a new minor release.

## Provider verification

Generate and verify the committed package:

```bash
python scripts/repository_contracts.py --check
```

Validate a producer document before publishing it:

```bash
python scripts/repository_contracts.py \
  --check \
  --verify-contract model-package-admission \
  --verify-document model-package.json
```

Build the deterministic release bundle used by CI:

```bash
python scripts/repository_contracts.py \
  --check \
  --bundle repository-contracts-1.0.0.zip
```

## Consumer compatibility

When preparing a later contract release, run the candidate against the last published directory:

```bash
python scripts/repository_contracts.py \
  --output-dir contracts/repository/v1.1.0 \
  --against contracts/repository/v1.0.0 \
  --check
```

The compatibility gate resolves local schema references and rejects new required properties, removed properties, enum or union narrowing, type narrowing, newly tightened string/number/array limits, and closed additional properties. Consumer repositories should also validate their own captured payload fixtures against the published schemas.

`--verify-document` runs both Draft 2020-12 validation and the canonical semantic validator. The semantic pass verifies cross-field digest equality for model packages and dataset references and recomputes the canonical hard-sample manifest checksum.
