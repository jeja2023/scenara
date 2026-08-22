# Scenara Data service

`scenara_data` is the standalone Data-side process for dataset, dataset-version,
sample, annotation, quality, lineage and Hard Sample intake boundaries. It owns
its tenant/project-scoped state and exposes only the internal versioned HTTP
paths used by Core's `HttpDataPlatformClient`.

The package does not import Core state stores or share the Core database. Local
tests can use an in-memory `DataStore`; the standalone process uses a durable
SQLite state journal when `SCENARA_DATA_STATE_PATH` is configured. The
PostgreSQL schema baseline is in `migrations/data/0001_data_domain.sql` and is
owned by the independent service. Production object-storage binding,
shadow-read comparison, backup/restore and final cutover evidence remain
explicit release gates.

Run locally with:

```text
SCENARA_DATA_SERVICE_TOKEN=dev-secret \
SCENARA_DATA_STATE_PATH=runtime-state/scenara-data.db \
python -m scenara_data
```

The migration importer verifies `checksums.txt` before preserving source IDs:

```text
python scripts/import_data_migration.py ./scenara-data-migration-<timestamp>
```

`/readyz` checks the configured state backend. `GET /internal/v1/events/outbox`
exposes pending versioned events for a delivery worker; it does not replace
Core's unified audit query.
