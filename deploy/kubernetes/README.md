# Scenara Kubernetes foundation

These manifests are a development and pre-production topology for the P0-P2
control-plane contracts. PostgreSQL, Redis, and S3/MinIO are external services;
the manifests do not embed credentials or model weights.

Create a Secret named `scenara-runtime` with the settings referenced by
`configmap.yaml`, then apply:

    kubectl apply -k deploy/kubernetes

Set `SCENARA_IMAGE` in an overlay or replace the image in
`kustomization.yaml`. The API and workers use the same image tag so their
OpenAPI and persistence contracts stay aligned. The default replica counts,
resource requests, and HPA values are conservative starting points and require
load, backup, and failover evidence before a production qualification claim.
