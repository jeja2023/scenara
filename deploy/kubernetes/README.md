# Scenara Kubernetes foundation

These manifests are a hardened production foundation for the P0-P2 control-plane
contracts. PostgreSQL, Redis, S3/MinIO, Scenara Data, TLS ingress, qualified model
PVC provisioning, secret injection and backup operators remain environment-owned.

Create a Secret named `scenara-runtime` with the settings referenced by
`configmap.yaml`, a Secret named `scenara-migration` containing `PGHOST`, `PGPORT`,
`PGDATABASE`, `PGUSER` and `PGPASSWORD`, and a read-only PVC named
`scenara-qualified-models`. Do not commit either Secret. Then apply:

Minimum `scenara-runtime` Secret keys:

- `SCENARA_POSTGRES_DSN` and authenticated `SCENARA_REDIS_URL`;
- `SCENARA_S3_ACCESS_KEY` and `SCENARA_S3_SECRET_KEY`;
- independent `SCENARA_DATA_PLATFORM_SERVICE_TOKEN` and `SCENARA_DATA_EVENT_SERVICE_TOKEN`;
- `SCENARA_API_TOKEN` and valid Fernet `SCENARA_SECRET_ENCRYPTION_KEY`;
- approved `SCENARA_OCR_ENGINE_FACTORY`, `SCENARA_BEHAVIOR_ENGINE_FACTORY` and `SCENARA_FASHION_ENGINE_FACTORY`.

Optionally include Bootstrap administrator credentials and Qdrant credentials.
Inject these values from an external secret manager; do not put `stringData` in a
tracked overlay. Patch `SCENARA_ALLOWED_HOSTS`, Data/S3 endpoints and
`FORWARDED_ALLOW_IPS` for the actual ingress and service network.

    kubectl apply -k deploy/kubernetes

The image tag is defined once in `kustomization.yaml` under `images:` and
applied to the API and worker deployments, keeping their OpenAPI and persistence
contracts aligned. Production overlays must use `digest: sha256:<digest>` rather
than a mutable tag.

The manifests enforce non-root execution, read-only root filesystems, dropped
capabilities, RuntimeDefault seccomp, disabled service-account token mounting,
bounded emptyDir volumes, API disruption protection, GPU limits for workers and
a default-deny network policy. Adapt the ingress namespace and approved service
ports to the target cluster before applying.

`scenara-migrate` is deliberately not part of `kustomization.yaml`, preventing
an unsafe race between schema migration and application rollout. Delete/recreate
the release-scoped Job (or use a unique name), wait for completion, and only then
roll API/workers/scheduler:

    kubectl apply -n scenara -f deploy/kubernetes/migrate-job.yaml
    kubectl wait -n scenara --for=condition=complete --timeout=10m job/scenara-migrate
    kubectl apply -k deploy/kubernetes

The production pipeline must run `scripts/validate_production_config.py` against
the secret source before rendering the overlay.
The default replica counts, resource requests, and HPA values are conservative
starting points and require load, backup, and failover evidence before a
production qualification claim.
