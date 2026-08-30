from __future__ import annotations

import time
from contextlib import suppress
from typing import Protocol
from urllib.parse import urlsplit
from uuid import uuid4

from scenara.platform.audit import AuditLogger
from scenara.platform.models import (
    CreateWebhookSubscriptionRequest,
    PrincipalContext,
    WebhookDeliveryRecord,
    WebhookSubscription,
    WebhookSubscriptionView,
)
from scenara.platform.network import validate_external_url
from scenara.platform.policy import PolicyProvider, require_allowed
from scenara.platform.secrets import SecretStore
from scenara.platform.store import StateConflict, StateStore
from scenara.platform.webhooks import WebhookDeliveryError, WebhookDeliveryService, WebhookEndpoint

SUPPORTED_WEBHOOK_EVENTS = frozenset(
    {
        "result.available",
        "result.delta",
        "alert.triggered",
        "alert.triaged",
        "model.deployment.changed",
        "run.cancelled",
        "run.cancelling",
        "run.completed",
        "run.error",
        "run.failed",
        "run.paused",
        "run.pausing",
        "run.queued",
        "run.running",
        "stream.segment.completed",
        "stream.segment.started",
        "stream.session.error",
    }
)


class WebhookNotFound(RuntimeError):
    pass


class WebhookSender(Protocol):
    async def deliver(
        self,
        endpoint: WebhookEndpoint,
        event_id: str,
        event_type: str,
        payload: dict[str, object],
        *,
        max_attempts: int = 5,
    ) -> object: ...


class WebhookService:
    def __init__(
        self,
        *,
        state: StateStore,
        secrets: SecretStore,
        audit: AuditLogger,
        policy: PolicyProvider,
        allow_private_targets: bool = False,
        sender: WebhookSender | None = None,
    ) -> None:
        self._state = state
        self._secrets = secrets
        self._audit = audit
        self._policy = policy
        self._allow_private_targets = allow_private_targets
        self._sender = sender or WebhookDeliveryService(allow_private_targets=allow_private_targets)

    @staticmethod
    def view(endpoint: WebhookSubscription) -> WebhookSubscriptionView:
        return WebhookSubscriptionView(
            endpoint_id=endpoint.endpoint_id,
            name=endpoint.name,
            url=endpoint.url,
            event_types=endpoint.event_types,
            enabled=endpoint.enabled,
            created_at=endpoint.created_at,
        )

    async def create(
        self, context: PrincipalContext, request: CreateWebhookSubscriptionRequest
    ) -> WebhookSubscriptionView:
        await require_allowed(self._policy, context, "create", "webhook_subscription")
        await validate_external_url(
            request.url,
            allowed_schemes=frozenset({"https"}),
            allow_private=self._allow_private_targets,
        )
        parsed = urlsplit(request.url)
        if parsed.query or parsed.fragment:
            raise ValueError("webhook URL must not contain query credentials or a fragment")
        unsupported = sorted(request.event_types - SUPPORTED_WEBHOOK_EVENTS)
        if unsupported:
            raise ValueError("unsupported webhook event types: " + ", ".join(unsupported))
        endpoint_id = f"whk_{uuid4().hex}"
        secret_ref = f"secret://webhooks/{context.tenant_id}/{context.project_id}/{endpoint_id}"
        endpoint = WebhookSubscription(
            endpoint_id=endpoint_id,
            tenant_id=context.tenant_id,
            project_id=context.project_id,
            name=request.name,
            url=request.url,
            secret_ref=secret_ref,
            event_types=request.event_types,
            created_at=time.time(),
        )
        await self._secrets.put(secret_ref, request.secret)
        stored: WebhookSubscription | None = None
        try:
            stored = await self._state.create_webhook_subscription(endpoint)
            await self._audit.record(
                context,
                action="webhook.subscription.create",
                resource_type="webhook_subscription",
                resource_id=endpoint_id,
                evidence={"url": endpoint.url, "event_types": sorted(endpoint.event_types)},
            )
            return self.view(stored)
        except Exception:
            if stored is not None:
                with suppress(Exception):
                    await self._state.delete_webhook_subscription(
                        context.tenant_id, context.project_id, endpoint_id
                    )
            with suppress(Exception):
                await self._secrets.delete(secret_ref)
            raise

    async def subscriptions(self, context: PrincipalContext) -> list[WebhookSubscriptionView]:
        await require_allowed(self._policy, context, "read", "webhook_subscription")
        rows = await self._state.list_webhook_subscriptions(context.tenant_id, context.project_id)
        return [self.view(item) for item in rows]

    async def delete(self, context: PrincipalContext, endpoint_id: str) -> None:
        await require_allowed(
            self._policy, context, "delete", "webhook_subscription", {"endpoint_id": endpoint_id}
        )
        endpoint = await self._state.get_webhook_subscription(
            context.tenant_id, context.project_id, endpoint_id
        )
        if endpoint is None:
            raise WebhookNotFound("webhook subscription not found")
        await self._audit.record(
            context,
            action="webhook.subscription.delete",
            resource_type="webhook_subscription",
            resource_id=endpoint_id,
            evidence={"url": endpoint.url},
        )
        await self._state.delete_webhook_subscription(context.tenant_id, context.project_id, endpoint_id)
        await self._secrets.delete(endpoint.secret_ref)

    async def deliveries(self, context: PrincipalContext, *, limit: int = 100) -> list[WebhookDeliveryRecord]:
        await require_allowed(self._policy, context, "read", "webhook_delivery")
        return await self._state.list_webhook_deliveries(context.tenant_id, context.project_id, limit)

    async def deliver_due(self, *, limit: int = 100, lease_seconds: int = 60) -> tuple[int, int]:
        if not 1 <= limit <= 1000:
            raise ValueError("webhook delivery limit must be between 1 and 1000")
        now = time.time()
        rows = await self._state.claim_webhook_deliveries(now, now + lease_seconds, limit)
        delivered = 0
        failed = 0
        for row in rows:
            endpoint = await self._state.get_webhook_subscription(
                row.tenant_id, row.project_id, row.endpoint_id
            )
            if endpoint is None or not endpoint.enabled:
                with suppress(StateConflict):
                    await self._state.save_webhook_delivery(
                        row.model_copy(
                            update={
                                "status": "dead_letter",
                                "last_error": "webhook subscription is unavailable",
                                "attempts": row.attempts + 1,
                                "updated_at": time.time(),
                            }
                        )
                    )
                failed += 1
                continue
            try:
                secret = await self._secrets.get(endpoint.secret_ref)
                receipt = await self._sender.deliver(
                    WebhookEndpoint(
                        endpoint_id=endpoint.endpoint_id,
                        url=endpoint.url,
                        secret=secret,
                        event_types=endpoint.event_types,
                        enabled=endpoint.enabled,
                    ),
                    row.event_id,
                    row.event_type,
                    row.payload,
                    max_attempts=1,
                )
                completed_at = time.time()
                await self._state.save_webhook_delivery(
                    row.model_copy(
                        update={
                            "status": "delivered",
                            "attempts": row.attempts + 1,
                            "status_code": getattr(receipt, "status_code", 200),
                            "last_error": None,
                            "updated_at": completed_at,
                            "delivered_at": completed_at,
                        }
                    )
                )
                delivered += 1
            except (WebhookDeliveryError, OSError, RuntimeError, ValueError) as exc:
                attempts = row.attempts + 1
                dead = attempts >= 8
                retry_at = time.time() + min(3600.0, 2.0**attempts)
                await self._state.save_webhook_delivery(
                    row.model_copy(
                        update={
                            "status": "dead_letter" if dead else "pending",
                            "attempts": attempts,
                            "next_attempt_at": retry_at,
                            "last_error": str(exc)[:500],
                            "updated_at": time.time(),
                        }
                    )
                )
                failed += 1
        return delivered, failed


__all__ = ["SUPPORTED_WEBHOOK_EVENTS", "WebhookNotFound", "WebhookSender", "WebhookService"]
