# Scenara Data service

`scenara_data` is the standalone Data-side process for dataset, dataset-version,
sample, annotation and Hard Sample intake boundaries. It owns its in-process
store in development and exposes only the internal versioned HTTP paths used by
Core's `HttpDataPlatformClient`.

The package does not import Core state stores or share the Core database. The
current store is a qualification/development implementation; production
PostgreSQL, object storage, migration import, shadow reads, backup/restore and
cutover evidence remain deployment work for the independent `scenara-data`
service.

Run locally with:

```text
SCENARA_DATA_SERVICE_TOKEN=dev-secret python -m scenara_data
```
