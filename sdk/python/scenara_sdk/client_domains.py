from __future__ import annotations

import mimetypes
from pathlib import Path
from typing import Any, cast

import httpx
from .client_core import ScenaraClientCore
from .client_types import ScenaraError
from .models import (
    FeedbackRecord,
    HardSampleManifest,
    ModelDeploymentEvent,
    ModelPackage,
    ModelRelease,
)


class ScenaraClient(ScenaraClientCore):
    def create_portrait_identity(
        self,
        display_name: str,
        *,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return cast(
            dict[str, Any],
            self._request(
                "POST",
                "/api/v1/portrait/identities",
                json={"display_name": display_name, "metadata": metadata or {}},
            ),
        )

    def delete_portrait_identity(self, identity_id: str) -> None:
        self._request("DELETE", f"/api/v1/portrait/identities/{identity_id}")

    def enroll_portrait_identity(
        self,
        identity_id: str,
        enrollment: dict[str, Any],
    ) -> dict[str, Any]:
        return cast(
            dict[str, Any],
            self._request(
                "POST",
                f"/api/v1/portrait/identities/{identity_id}/enrollments",
                json=enrollment,
            ),
        )

    def search_portrait(self, query: dict[str, Any]) -> dict[str, Any]:
        return cast(
            dict[str, Any],
            self._request("POST", "/api/v1/portrait/search", json=query),
        )

    def compare_portrait(self, comparison: dict[str, Any]) -> dict[str, Any]:
        return cast(
            dict[str, Any],
            self._request("POST", "/api/v1/portrait/compare", json=comparison),
        )

    def list_long_term_identities(
        self,
        *,
        status: str | None = None,
        camera_id: str | None = None,
        since: float | None = None,
        until: float | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"offset": offset, "limit": limit}
        for key, value in (
            ("status", status),
            ("camera_id", camera_id),
            ("since", since),
            ("until", until),
        ):
            if value is not None:
                params[key] = value
        return cast(
            dict[str, Any],
            self._request(
                "GET", "/api/v1/portrait/trajectories/identities", params=params
            ),
        )

    def get_long_term_identity(self, identity_id: str) -> dict[str, Any]:
        return cast(
            dict[str, Any],
            self._request(
                "GET", f"/api/v1/portrait/trajectories/identities/{identity_id}"
            ),
        )

    def update_long_term_identity(
        self, identity_id: str, changes: dict[str, Any]
    ) -> dict[str, Any]:
        return cast(
            dict[str, Any],
            self._request(
                "PATCH",
                f"/api/v1/portrait/trajectories/identities/{identity_id}",
                json=changes,
            ),
        )

    def delete_long_term_identity(self, identity_id: str) -> None:
        self._request(
            "DELETE", f"/api/v1/portrait/trajectories/identities/{identity_id}"
        )

    def list_long_term_identity_segments(
        self,
        identity_id: str,
        *,
        camera_id: str | None = None,
        since: float | None = None,
        until: float | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"offset": offset, "limit": limit}
        for key, value in (
            ("camera_id", camera_id),
            ("since", since),
            ("until", until),
        ):
            if value is not None:
                params[key] = value
        return cast(
            dict[str, Any],
            self._request(
                "GET",
                f"/api/v1/portrait/trajectories/identities/{identity_id}/segments",
                params=params,
            ),
        )

    def get_long_term_identity_timeline(self, identity_id: str) -> list[dict[str, Any]]:
        return cast(
            list[dict[str, Any]],
            self._request(
                "GET",
                f"/api/v1/portrait/trajectories/identities/{identity_id}/timeline",
            ),
        )

    def merge_long_term_identities(
        self, target_identity_id: str, source_identity_ids: list[str]
    ) -> dict[str, Any]:
        return cast(
            dict[str, Any],
            self._request(
                "POST",
                "/api/v1/portrait/trajectories/identities/merge",
                json={
                    "target_identity_id": target_identity_id,
                    "source_identity_ids": source_identity_ids,
                },
            ),
        )

    def split_long_term_identity(
        self, identity_id: str, segment_ids: list[str], *, display_name: str = ""
    ) -> dict[str, Any]:
        return cast(
            dict[str, Any],
            self._request(
                "POST",
                f"/api/v1/portrait/trajectories/identities/{identity_id}/split",
                json={"segment_ids": segment_ids, "display_name": display_name},
            ),
        )

    def register_portrait_camera(
        self,
        camera_id: str,
        *,
        display_name: str = "",
        location: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return cast(
            dict[str, Any],
            self._request(
                "POST",
                "/api/v1/portrait/cameras",
                json={
                    "camera_id": camera_id,
                    "display_name": display_name,
                    "location": location,
                    "metadata": metadata or {},
                },
            ),
        )

    def list_portrait_cameras(self) -> list[dict[str, Any]]:
        return cast(
            list[dict[str, Any]], self._request("GET", "/api/v1/portrait/cameras")
        )

    def update_portrait_camera(
        self, camera_id: str, changes: dict[str, Any]
    ) -> dict[str, Any]:
        return cast(
            dict[str, Any],
            self._request(
                "PATCH", f"/api/v1/portrait/cameras/{camera_id}", json=changes
            ),
        )

    def delete_portrait_camera(self, camera_id: str) -> None:
        self._request("DELETE", f"/api/v1/portrait/cameras/{camera_id}")

    def list_portrait_camera_transitions(self, camera_id: str) -> list[dict[str, Any]]:
        return cast(
            list[dict[str, Any]],
            self._request("GET", f"/api/v1/portrait/cameras/{camera_id}/transitions"),
        )

    def set_portrait_camera_transitions(
        self, camera_id: str, transitions: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        return cast(
            list[dict[str, Any]],
            self._request(
                "PUT",
                f"/api/v1/portrait/cameras/{camera_id}/transitions",
                json={"transitions": transitions},
            ),
        )

    def enroll_portrait_identity_image(
        self,
        identity_id: str,
        path: str | Path,
        *,
        feature_space_id: str | None = None,
        quality: float | None = None,
    ) -> dict[str, Any]:
        source = Path(path)
        content_type = (
            mimetypes.guess_type(source.name)[0] or "application/octet-stream"
        )
        data = {"feature_space_id": feature_space_id, "quality": quality}
        with source.open("rb") as handle:
            return cast(
                dict[str, Any],
                self._request(
                    "POST",
                    f"/api/v1/portrait/identities/{identity_id}/enrollments/image",
                    files={"file": (source.name, handle, content_type)},
                    data={
                        key: str(value)
                        for key, value in data.items()
                        if value is not None
                    },
                ),
            )

    def search_portrait_image(
        self,
        path: str | Path,
        *,
        feature_space_id: str | None = None,
        limit: int = 20,
        threshold: float | None = None,
    ) -> dict[str, Any]:
        source = Path(path)
        content_type = (
            mimetypes.guess_type(source.name)[0] or "application/octet-stream"
        )
        data = {
            "feature_space_id": feature_space_id,
            "limit": limit,
            "threshold": threshold,
        }
        with source.open("rb") as handle:
            return cast(
                dict[str, Any],
                self._request(
                    "POST",
                    "/api/v1/portrait/search/image",
                    files={"file": (source.name, handle, content_type)},
                    data={
                        key: str(value)
                        for key, value in data.items()
                        if value is not None
                    },
                ),
            )

    def compare_portrait_images(
        self,
        left_path: str | Path,
        right_path: str | Path,
        *,
        feature_space_id: str | None = None,
        threshold: float | None = None,
    ) -> dict[str, Any]:
        left = Path(left_path)
        right = Path(right_path)
        left_type = mimetypes.guess_type(left.name)[0] or "application/octet-stream"
        right_type = mimetypes.guess_type(right.name)[0] or "application/octet-stream"
        data = {"feature_space_id": feature_space_id, "threshold": threshold}
        with left.open("rb") as left_handle, right.open("rb") as right_handle:
            return cast(
                dict[str, Any],
                self._request(
                    "POST",
                    "/api/v1/portrait/compare/images",
                    files={
                        "left": (left.name, left_handle, left_type),
                        "right": (right.name, right_handle, right_type),
                    },
                    data={
                        key: str(value)
                        for key, value in data.items()
                        if value is not None
                    },
                ),
            )

    def compare_portrait_asset_image(
        self,
        asset_id: str,
        image_path: str | Path,
        *,
        feature_space_id: str | None = None,
        threshold: float | None = None,
    ) -> dict[str, Any]:
        source = Path(image_path)
        content_type = (
            mimetypes.guess_type(source.name)[0] or "application/octet-stream"
        )
        data = {
            "asset_id": asset_id,
            "feature_space_id": feature_space_id,
            "threshold": threshold,
        }
        with source.open("rb") as handle:
            return cast(
                dict[str, Any],
                self._request(
                    "POST",
                    "/api/v1/portrait/compare/asset-image",
                    files={"file": (source.name, handle, content_type)},
                    data={
                        key: str(value)
                        for key, value in data.items()
                        if value is not None
                    },
                ),
            )

    def compare_portrait_image_asset(
        self,
        image_path: str | Path,
        asset_id: str,
        *,
        feature_space_id: str | None = None,
        threshold: float | None = None,
    ) -> dict[str, Any]:
        source = Path(image_path)
        content_type = (
            mimetypes.guess_type(source.name)[0] or "application/octet-stream"
        )
        data = {
            "asset_id": asset_id,
            "feature_space_id": feature_space_id,
            "threshold": threshold,
        }
        with source.open("rb") as handle:
            return cast(
                dict[str, Any],
                self._request(
                    "POST",
                    "/api/v1/portrait/compare/image-asset",
                    files={"file": (source.name, handle, content_type)},
                    data={
                        key: str(value)
                        for key, value in data.items()
                        if value is not None
                    },
                ),
            )

    def search_text(
        self,
        query: str,
        *,
        domains: list[str] | None = None,
        media_kinds: list[str] | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        return cast(
            dict[str, Any],
            self._request(
                "POST",
                "/api/v1/search/text",
                json={
                    "query": query,
                    "domains": domains or [],
                    "media_kinds": media_kinds or [],
                    "limit": limit,
                },
            ),
        )

    def search_portrait_results(
        self,
        path: str | Path,
        *,
        feature_space_id: str | None = None,
        media_kinds: list[str] | None = None,
        limit: int = 50,
        threshold: float | None = None,
    ) -> dict[str, Any]:
        source = Path(path)
        content_type = (
            mimetypes.guess_type(source.name)[0] or "application/octet-stream"
        )
        data = {
            "feature_space_id": feature_space_id,
            "media_kinds": ",".join(media_kinds or []),
            "limit": limit,
            "threshold": threshold,
        }
        with source.open("rb") as handle:
            return cast(
                dict[str, Any],
                self._request(
                    "POST",
                    "/api/v1/search/image",
                    files={"file": (source.name, handle, content_type)},
                    data={
                        key: str(value)
                        for key, value in data.items()
                        if value not in (None, "")
                    },
                ),
            )

    def search_portrait_asset(
        self,
        asset_id: str,
        *,
        feature_space_id: str | None = None,
        media_kinds: list[str] | None = None,
        limit: int = 50,
        threshold: float | None = None,
    ) -> dict[str, Any]:
        return cast(
            dict[str, Any],
            self._request(
                "POST",
                "/api/v1/search/asset",
                json={
                    "asset_id": asset_id,
                    "feature_space_id": feature_space_id,
                    "media_kinds": media_kinds or [],
                    "limit": limit,
                    "threshold": threshold,
                },
            ),
        )

    def list_search_indexes(self, *, domain: str | None = None) -> list[dict[str, Any]]:
        return cast(
            list[dict[str, Any]],
            self._request(
                "GET", "/api/v1/indexes", params={"domain": domain} if domain else None
            ),
        )

    def list_search_index_records(
        self,
        index_id: str,
        *,
        source_type: str | None = None,
        source_id: str | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        return cast(
            list[dict[str, Any]],
            self._request(
                "GET",
                f"/api/v1/indexes/{index_id}/records",
                params={
                    "source_type": source_type,
                    "source_id": source_id,
                    "offset": offset,
                    "limit": limit,
                },
            ),
        )

    def query_search_index_text(
        self, index_id: str, query: str, *, limit: int = 20
    ) -> list[dict[str, Any]]:
        return cast(
            list[dict[str, Any]],
            self._request(
                "POST",
                f"/api/v1/indexes/{index_id}/query/text",
                json={"query": query, "limit": limit},
            ),
        )

    def query_search_index_vector(
        self,
        index_id: str,
        vector: list[float],
        *,
        limit: int = 20,
        threshold: float | None = None,
    ) -> list[dict[str, Any]]:
        return cast(
            list[dict[str, Any]],
            self._request(
                "POST",
                f"/api/v1/indexes/{index_id}/query/vector",
                json={"vector": vector, "limit": limit, "threshold": threshold},
            ),
        )

    def create_feedback(self, feedback: dict[str, Any]) -> FeedbackRecord:
        return cast(
            FeedbackRecord, self._request("POST", "/api/v1/feedback", json=feedback)
        )

    def list_feedback(self) -> list[FeedbackRecord]:
        return cast(list[FeedbackRecord], self._request("GET", "/api/v1/feedback"))

    def review_feedback(
        self, feedback_id: str, *, status: str, notes: str = ""
    ) -> FeedbackRecord:
        return cast(
            FeedbackRecord,
            self._request(
                "POST",
                f"/api/v1/feedback/{feedback_id}/review",
                json={"status": status, "notes": notes},
            ),
        )

    def create_hard_sample_manifest(
        self,
        *,
        dataset_id: str,
        version: str,
        feedback_ids: list[str],
        label_schema: str = "scenara.feedback.correction.v1",
        split: str = "train",
    ) -> HardSampleManifest:
        return cast(
            HardSampleManifest,
            self._request(
                "POST",
                "/api/v1/hard-sample-manifests",
                json={
                    "dataset_id": dataset_id,
                    "version": version,
                    "label_schema": label_schema,
                    "split": split,
                    "feedback_ids": feedback_ids,
                },
            ),
        )

    def create_model_release(self, release: dict[str, Any]) -> ModelRelease:
        return cast(
            ModelRelease, self._request("POST", "/api/v1/model-releases", json=release)
        )

    def admit_model_package(self, package: ModelPackage) -> ModelPackage:
        return cast(
            ModelPackage,
            self._request("POST", "/api/v1/model-packages/admissions", json=package),
        )

    def list_model_releases(self) -> list[ModelRelease]:
        return cast(list[ModelRelease], self._request("GET", "/api/v1/model-releases"))

    def transition_model_release(
        self, model_id: str, version: str, *, status: str, reason: str
    ) -> ModelRelease:
        return cast(
            ModelRelease,
            self._request(
                "POST",
                f"/api/v1/model-releases/{model_id}/versions/{version}/transition",
                json={"status": status, "reason": reason},
            ),
        )

    def rollback_model_release(
        self, model_id: str, *, target_version: str, reason: str
    ) -> ModelRelease:
        return cast(
            ModelRelease,
            self._request(
                "POST",
                f"/api/v1/model-releases/{model_id}/rollback",
                json={"target_version": target_version, "reason": reason},
            ),
        )

    def list_model_deployment_events(
        self, *, limit: int = 100
    ) -> list[ModelDeploymentEvent]:
        return cast(
            list[ModelDeploymentEvent],
            self._request(
                "GET", "/api/v1/model-deployment-events", params={"limit": limit}
            ),
        )

    def control_plane_request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> Any:
        """Call a versioned post-1.0 control-plane resource.

        The generic escape hatch keeps the Python SDK usable as new product
        modules are enabled while their resource-specific types are generated
        from OpenAPI.
        """
        return self._request(method, path, json=json, params=params)

    def create_identity_provider(self, body: dict[str, Any]) -> dict[str, Any]:
        return cast(
            dict[str, Any],
            self.control_plane_request(
                "POST", "/api/v1/platform/identity-providers", json=body
            ),
        )

    def list_identity_providers(self) -> list[dict[str, Any]]:
        return cast(
            list[dict[str, Any]],
            self.control_plane_request("GET", "/api/v1/platform/identity-providers"),
        )

    def probe_identity_provider(self, provider_id: str) -> dict[str, Any]:
        return cast(
            dict[str, Any],
            self.control_plane_request(
                "POST", f"/api/v1/platform/identity-providers/{provider_id}/probe"
            ),
        )

    def request_project_lifecycle(self, body: dict[str, Any]) -> dict[str, Any]:
        return cast(
            dict[str, Any],
            self.control_plane_request(
                "POST", "/api/v1/platform/projects/lifecycle-requests", json=body
            ),
        )

    def decide_project_lifecycle(
        self, request_id: str, body: dict[str, Any]
    ) -> dict[str, Any]:
        return cast(
            dict[str, Any],
            self.control_plane_request(
                "POST",
                f"/api/v1/platform/projects/lifecycle-requests/{request_id}/decide",
                json=body,
            ),
        )

    def set_audit_retention(self, body: dict[str, Any]) -> dict[str, Any]:
        return cast(
            dict[str, Any],
            self.control_plane_request(
                "PUT", "/api/v1/platform/audit/retention", json=body
            ),
        )

    def purge_audit(self, body: dict[str, Any]) -> dict[str, Any]:
        return cast(
            dict[str, Any],
            self.control_plane_request(
                "POST", "/api/v1/platform/audit/purge", json=body
            ),
        )

    def create_session(
        self, user_id: str, *, ttl_seconds: int = 3600
    ) -> dict[str, Any]:
        return cast(
            dict[str, Any],
            self.control_plane_request(
                "POST",
                "/api/v1/platform/sessions",
                json={"user_id": user_id, "ttl_seconds": ttl_seconds},
            ),
        )

    def create_annotation_task(self, body: dict[str, Any]) -> dict[str, Any]:
        return cast(
            dict[str, Any],
            self.control_plane_request(
                "POST", "/api/v1/data/annotation-tasks", json=body
            ),
        )

    def register_annotation_provider(self, body: dict[str, Any]) -> dict[str, Any]:
        return cast(
            dict[str, Any],
            self.control_plane_request(
                "POST", "/api/v1/data/annotation-providers", json=body
            ),
        )

    def probe_annotation_provider(self, provider_id: str) -> dict[str, Any]:
        return cast(
            dict[str, Any],
            self.control_plane_request(
                "POST", f"/api/v1/data/annotation-providers/{provider_id}/probe"
            ),
        )

    def review_annotation_task(
        self, task_id: str, body: dict[str, Any]
    ) -> dict[str, Any]:
        return cast(
            dict[str, Any],
            self.control_plane_request(
                "POST", f"/api/v1/data/annotation-tasks/{task_id}/review", json=body
            ),
        )

    def create_flow(self, body: dict[str, Any]) -> dict[str, Any]:
        return cast(
            dict[str, Any],
            self.control_plane_request("POST", "/api/v1/flows", json=body),
        )

    def execute_flow(
        self, flow_id: str, context: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        return cast(
            dict[str, Any],
            self.control_plane_request(
                "POST",
                f"/api/v1/flows/{flow_id}/execute",
                json={"context": context or {}},
            ),
        )

    def decide_flow_approval(
        self, approval_id: str, body: dict[str, Any]
    ) -> dict[str, Any]:
        return cast(
            dict[str, Any],
            self.control_plane_request(
                "POST", f"/api/v1/flows/approvals/{approval_id}/decide", json=body
            ),
        )

    def create_search_ranking_profile(self, body: dict[str, Any]) -> dict[str, Any]:
        return cast(
            dict[str, Any],
            self.control_plane_request(
                "POST", "/api/v1/search/ranking-profiles", json=body
            ),
        )

    def register_index_backend(self, body: dict[str, Any]) -> dict[str, Any]:
        return cast(
            dict[str, Any],
            self.control_plane_request(
                "POST", "/api/v1/search/index-backends", json=body
            ),
        )

    def probe_index_backend(self, backend_id: str) -> dict[str, Any]:
        return cast(
            dict[str, Any],
            self.control_plane_request(
                "POST", f"/api/v1/search/index-backends/{backend_id}/probe"
            ),
        )

    def register_search_reranker(self, body: dict[str, Any]) -> dict[str, Any]:
        return cast(
            dict[str, Any],
            self.control_plane_request("POST", "/api/v1/search/rerankers", json=body),
        )

    def probe_search_reranker(self, reranker_id: str) -> dict[str, Any]:
        return cast(
            dict[str, Any],
            self.control_plane_request(
                "POST", f"/api/v1/search/rerankers/{reranker_id}/probe"
            ),
        )

    def evaluate_search(self, body: dict[str, Any]) -> dict[str, Any]:
        return cast(
            dict[str, Any],
            self.control_plane_request("POST", "/api/v1/search/evaluations", json=body),
        )

    def rebuild_index(self, index_id: str) -> dict[str, Any]:
        return cast(
            dict[str, Any],
            self.control_plane_request(
                "POST", "/api/v1/indexes/rebuild", json={"index_id": index_id}
            ),
        )

    def create_index(self, body: dict[str, Any]) -> dict[str, Any]:
        return cast(
            dict[str, Any],
            self.control_plane_request("POST", "/api/v1/indexes", json=body),
        )

    def register_edge_device(self, body: dict[str, Any]) -> dict[str, Any]:
        return cast(
            dict[str, Any],
            self.control_plane_request("POST", "/api/v1/edge/devices", json=body),
        )

    def heartbeat_edge_device(
        self, device_id: str, body: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        return cast(
            dict[str, Any],
            self.control_plane_request(
                "POST", f"/api/v1/edge/devices/{device_id}/heartbeat", json=body or {}
            ),
        )

    def deploy_edge(self, body: dict[str, Any]) -> dict[str, Any]:
        return cast(
            dict[str, Any],
            self.control_plane_request("POST", "/api/v1/edge/deployments", json=body),
        )

    def acknowledge_edge_deployment(
        self, deployment_id: str, body: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        return cast(
            dict[str, Any],
            self.control_plane_request(
                "POST",
                f"/api/v1/edge/deployments/{deployment_id}/acknowledge",
                json=body or {},
            ),
        )

    def register_agent_tool(self, body: dict[str, Any]) -> dict[str, Any]:
        return cast(
            dict[str, Any],
            self.control_plane_request("POST", "/api/v1/agents/tools", json=body),
        )

    def propose_agent_action(self, body: dict[str, Any]) -> dict[str, Any]:
        return cast(
            dict[str, Any],
            self.control_plane_request("POST", "/api/v1/agents/actions", json=body),
        )

    def decide_agent_action(
        self, action_id: str, body: dict[str, Any]
    ) -> dict[str, Any]:
        return cast(
            dict[str, Any],
            self.control_plane_request(
                "POST", f"/api/v1/agents/actions/{action_id}/decide", json=body
            ),
        )

    def execute_agent_action(self, action_id: str) -> dict[str, Any]:
        return cast(
            dict[str, Any],
            self.control_plane_request(
                "POST", f"/api/v1/agents/actions/{action_id}/execute"
            ),
        )

    def record_agent_trace(self, body: dict[str, Any]) -> dict[str, Any]:
        return cast(
            dict[str, Any],
            self.control_plane_request("POST", "/api/v1/agents/traces", json=body),
        )

    def record_agent_evaluation(self, body: dict[str, Any]) -> dict[str, Any]:
        return cast(
            dict[str, Any],
            self.control_plane_request("POST", "/api/v1/agents/evaluations", json=body),
        )

    def put_agent_memory(self, body: dict[str, Any]) -> dict[str, Any]:
        return cast(
            dict[str, Any],
            self.control_plane_request("PUT", "/api/v1/agents/memory", json=body),
        )

    def get_agent_memory(self, namespace: str, key: str) -> dict[str, Any] | None:
        return cast(
            dict[str, Any] | None,
            self.control_plane_request(
                "GET",
                "/api/v1/agents/memory",
                params={"namespace": namespace, "key": key},
            ),
        )

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        response = self._client.request(method, path, **kwargs)
        if response.status_code == 204:
            return None
        try:
            payload = response.json()
        except ValueError:
            payload = {}
        if response.is_error:
            self._raise_response_error(response, payload)
        if not isinstance(payload, dict) or "data" not in payload:
            raise ScenaraError(
                502, "INVALID_RESPONSE", "Scenara API response is missing data"
            )
        return payload["data"]

    @staticmethod
    def _raise_response_error(
        response: httpx.Response, payload: object | None = None
    ) -> None:
        if payload is None:
            try:
                payload = response.json()
            except ValueError:
                payload = {}
        error = payload.get("error", {}) if isinstance(payload, dict) else {}
        raise ScenaraError(
            response.status_code,
            str(error.get("code", "HTTP_ERROR")),
            str(error.get("message", response.reason_phrase)),
            payload.get("request_id") if isinstance(payload, dict) else None,
        )
