# ADR 0002: Runtime processes and storage authority

- Status: accepted
- Date: 2026-07-29

## Decision

Scenara ships a modular API/control-plane process, a batch GPU worker, a stream
worker, and a governance scheduler. They share versioned contracts and obtain
operators and pipelines from the same build-time registry.

Run delivery is at least once. Workers acquire leases and all persistent state
transitions use optimistic revisions in PostgreSQL, so retrying a delivery must
not create a second run or publish a second logical result. Events use a
monotonic per-run identifier and clients deduplicate by `(run_id, event_id)`.

S3 objects are immutable after publication. A result reference is committed only
after the object is written and includes its SHA-256 checksum. Deleting media or
biometric subjects removes both the database record and referenced objects.

