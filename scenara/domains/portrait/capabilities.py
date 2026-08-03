from __future__ import annotations

from scenara.platform.portrait_intelligence import (
    PORTRAIT_CAPABILITY_IDS,
    CapabilitySnapshot,
)


def portrait_capability_snapshot() -> dict[str, CapabilitySnapshot]:
    from app.portrait_model_capabilities import capability_status, production_model_ready

    snapshot: dict[str, CapabilitySnapshot] = {}
    for capability_id in PORTRAIT_CAPABILITY_IDS:
        capability = capability_status(capability_id)
        snapshot[capability_id] = CapabilitySnapshot(
            readiness=capability.get("status", "not_configured"),
            production_ready=bool(production_model_ready(capability_id)),
            current_model=capability.get("model_id") or None,
            target_model=capability.get("production_model") or None,
            embedding_dimension=capability.get("embedding_dim") or None,
            target_embedding_dimension=capability.get("production_embedding_dim") or None,
        )
    return snapshot


__all__ = ["portrait_capability_snapshot"]
