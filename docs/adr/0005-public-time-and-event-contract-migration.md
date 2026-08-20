# ADR 0005: Public time and event contract migration

- Status: accepted
- Date: 2026-08-20

## Decision

New public events use a versioned envelope with UTC RFC 3339 `occurred_at`,
producer, tenant/project, request, and trace context. Run SSE and Webhook
deliveries use event version `1.0`.

Existing public resource timestamps remain numeric epoch seconds during the
`0.3.x` compatibility window. The next API major version will publish RFC 3339
timestamp fields as the canonical values and retain legacy epoch values only
for the announced compatibility period. Duration and media timeline fields
remain explicitly suffixed with `_ms`.

## Consequences

- Consumers must treat `event_version` as part of event compatibility.
- Event consumers deduplicate by `event_id` and must accept at-least-once delivery.
- A bulk timestamp type replacement is prohibited before the major-version
  contract, generated SDKs, Console formatters, and migration evidence ship
  together.
