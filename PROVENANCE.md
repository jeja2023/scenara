# Source provenance

Scenara starts from a curated snapshot of `https://github.com/jeja2023/portrait-hub` without copying its Git history.

The exact source anchor is recorded in `source-manifest.json` when the initial Scenara root commit is created. The candidate observed during bootstrap was `ae9798f3119099a5b3aec554a830e25d97293e66`; the manifest, not this explanatory paragraph, is authoritative.

Imported categories:

- media decoding and validation;
- inference runtime and scheduling;
- Portrait algorithms and storage adapters used by the migration Domain;
- Console Next source used as a UI migration base;
- model cards, labels and dependency locks without model weights.

Excluded categories:

- Portrait Hub Git history and release notes;
- legacy OpenAPI baselines and generated clients;
- runtime state, `.env`, credentials, customer data and model weights;
- experimental Go, Java and Node SDKs;
- obsolete plans and compatibility promises.

Until Portrait Hub is archived, any blocking fix ported into Scenara must reference the source commit in the Scenara commit message or change record.
