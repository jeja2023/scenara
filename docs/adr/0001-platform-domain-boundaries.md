# ADR 0001: Platform and domain boundaries

- Status: accepted
- Date: 2026-07-29

## Context

Scenara must support independently evolving visual domains without making the
platform kernel understand Portrait or OCR semantics. It must also support API,
batch worker, stream worker, and scheduler processes from the same contracts.

## Decision

The repository is divided into four dependency directions:

1. `scenara.platform` defines media, run, pipeline, result, model, feature,
   retention, audit, policy, and worker contracts. It never imports a concrete
   domain or infrastructure implementation.
2. `scenara.domains` implements those contracts. A domain is installed at build
   time and is visible only through `DomainPluginRegistry`. Runtime code upload
   is not supported.
3. `scenara.infrastructure` implements platform ports for PostgreSQL, Redis, and
   S3-compatible storage. It does not define domain behavior.
4. `scenara.enterprise` implements optional policy providers. Platform code
   calls a provider contract and does not import an enterprise implementation.

PostgreSQL is the source of truth. Redis contains delivery, lease, and ephemeral
event state only. S3-compatible storage contains media and immutable result
artifacts while PostgreSQL stores their references and checksums.

## Consequences

- Architectural import tests are release gates.
- Domain-specific discriminated result schemas remain in platform contracts so
  clients can safely decode registered, public domains. The execution kernel
  still dispatches entirely through registries.
- New domains require a plugin, typed result contract, fixed evaluation set,
  and console route; they do not require a platform execution branch.

