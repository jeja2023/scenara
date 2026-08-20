"""Registered public API error codes.

The set is intentionally explicit so an implementation exception cannot leak
an unregistered database/provider error code to a cross-repository consumer.
"""

REGISTERED_ERROR_CODES = frozenset(
    {
        "HTTP_ERROR", "VALIDATION_ERROR", "NOT_FOUND", "INVALID_ARGUMENT",
        "POLICY_DENIED", "POLICY_UNAVAILABLE", "AUDIT_UNAVAILABLE",
        "ACCESS_NOT_FOUND", "DATASET_NOT_FOUND", "DATASET_CONFLICT",
        "FEEDBACK_NOT_FOUND", "FEEDBACK_CONFLICT", "PORTRAIT_NOT_FOUND",
        "PORTRAIT_CONFLICT", "PORTRAIT_ENCODING_ERROR", "TRAJECTORY_NOT_FOUND",
        "TRAJECTORY_CONFLICT", "WEBHOOK_NOT_FOUND", "SAVED_SEARCH_NOT_FOUND",
        "SAVED_SEARCH_CONFLICT", "FEATURE_SPACE_CONFLICT", "INDEX_CONTRACT_ERROR",
        "INVALID_RUN_TRANSITION", "STATE_CONFLICT", "PIPELINE_ERROR",
        "IMMUTABLE_OBJECT_CONFLICT", "OBJECT_INTEGRITY_ERROR",
        "OBJECT_CAPABILITY_UNAVAILABLE", "DATA_PLATFORM_PROTOCOL_ERROR",
        "QUEUE_UNAVAILABLE", "INTERNAL_SERVER_ERROR",
    }
)


def registered_error_code(code: str) -> str:
    return code if code in REGISTERED_ERROR_CODES else "INTERNAL_SERVER_ERROR"


__all__ = ["REGISTERED_ERROR_CODES", "registered_error_code"]
