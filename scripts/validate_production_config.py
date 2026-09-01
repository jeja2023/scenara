from __future__ import annotations

import argparse
import base64
import json
import os
import re
import stat
from pathlib import Path
from urllib.parse import urlsplit

PLACEHOLDER = re.compile(r"(?:replace-with|changeme|todo|tbd|<[^>]+>)", re.IGNORECASE)
FACTORY = re.compile(r"^[A-Za-z_][A-Za-z0-9_.]*:[A-Za-z_][A-Za-z0-9_]*$")
SHA256_IMAGE = re.compile(r"^[^\s@]+@sha256:[0-9a-f]{64}$")

REQUIRED = {
    "SCENARA_POSTGRES_PASSWORD",
    "SCENARA_REDIS_PASSWORD",
    "SCENARA_MINIO_ROOT_USER",
    "SCENARA_MINIO_ROOT_PASSWORD",
    "SCENARA_S3_ACCESS_KEY",
    "SCENARA_S3_SECRET_KEY",
    "SCENARA_DATA_PLATFORM_URL",
    "SCENARA_DATA_PLATFORM_SERVICE_TOKEN",
    "SCENARA_DATA_EVENT_SERVICE_TOKEN",
    "SCENARA_API_TOKEN",
    "SCENARA_SECRET_ENCRYPTION_KEY",
    "SCENARA_OCR_ENGINE_FACTORY",
    "SCENARA_BEHAVIOR_ENGINE_FACTORY",
    "SCENARA_FASHION_ENGINE_FACTORY",
    "SCENARA_ALLOWED_HOSTS",
    "SCENARA_FORWARDED_ALLOW_IPS",
    "SCENARA_IMAGE_REFERENCE",
}

SECRET_NAMES = {
    "SCENARA_POSTGRES_PASSWORD",
    "SCENARA_REDIS_PASSWORD",
    "SCENARA_MINIO_ROOT_PASSWORD",
    "SCENARA_S3_SECRET_KEY",
    "SCENARA_DATA_PLATFORM_SERVICE_TOKEN",
    "SCENARA_DATA_EVENT_SERVICE_TOKEN",
    "SCENARA_API_TOKEN",
    "SCENARA_SECRET_ENCRYPTION_KEY",
    "SCENARA_BOOTSTRAP_ADMIN_PASSWORD",
    "SCENARA_QDRANT_API_KEY",
}


def parse_env_file(path: Path) -> tuple[dict[str, str], list[str]]:
    values: dict[str, str] = {}
    errors: list[str] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as exc:
        return {}, [f"cannot read environment file: {exc}"]
    for line_number, raw in enumerate(lines, 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        if "=" not in line:
            errors.append(f"line {line_number}: expected NAME=value")
            continue
        name, value = line.split("=", 1)
        name = name.strip()
        if not re.fullmatch(r"[A-Z][A-Z0-9_]*", name):
            errors.append(f"line {line_number}: invalid variable name")
            continue
        if name in values:
            errors.append(f"line {line_number}: duplicate variable {name}")
            continue
        values[name] = value.strip().strip('"').strip("'")
    if os.name != "nt":
        mode = stat.S_IMODE(path.stat().st_mode)
        if mode & 0o077:
            errors.append(f"environment file permissions must be 0600 or stricter, found {mode:04o}")
    return values, errors


def _secret(values: dict[str, str], name: str) -> str:
    inline = values.get(name, "").strip()
    file_name = values.get(f"{name}_FILE", "").strip()
    if inline and file_name:
        return ""
    if inline:
        return inline
    if not file_name:
        return ""
    try:
        return Path(file_name).read_text(encoding="utf-8").strip()
    except (OSError, UnicodeError):
        return ""


def _fernet_key(value: str) -> bool:
    try:
        return len(base64.urlsafe_b64decode(value.encode("ascii"))) == 32
    except (ValueError, UnicodeError):
        return False


def _positive_int(values: dict[str, str], name: str, default: int) -> tuple[int | None, str | None]:
    raw = values.get(name, str(default)).strip()
    try:
        value = int(raw)
    except ValueError:
        return None, f"{name} must be an integer"
    if value < 1:
        return None, f"{name} must be positive"
    return value, None


def validate(values: dict[str, str], *, file_mode: bool) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    for name in sorted(REQUIRED):
        value = _secret(values, name) if name in SECRET_NAMES else values.get(name, "").strip()
        if not value:
            errors.append(f"{name} is required")
        elif PLACEHOLDER.search(value):
            errors.append(f"{name} still contains a placeholder")

    secrets = {name: _secret(values, name) for name in SECRET_NAMES if _secret(values, name)}
    short = sorted(name for name, value in secrets.items() if name != "SCENARA_SECRET_ENCRYPTION_KEY" and len(value) < 24)
    if short:
        errors.append("secrets must contain at least 24 characters: " + ", ".join(short))
    duplicate_groups: dict[str, list[str]] = {}
    for name, value in secrets.items():
        duplicate_groups.setdefault(value, []).append(name)
    reused = [names for names in duplicate_groups.values() if len(names) > 1]
    for names in reused:
        errors.append("secrets must not be reused across trust boundaries: " + ", ".join(sorted(names)))

    encryption_key = _secret(values, "SCENARA_SECRET_ENCRYPTION_KEY")
    if encryption_key and not _fernet_key(encryption_key):
        errors.append("SCENARA_SECRET_ENCRYPTION_KEY must be a valid Fernet key")

    data_url = values.get("SCENARA_DATA_PLATFORM_URL", "").strip()
    allow_insecure = values.get("SCENARA_ALLOW_INSECURE_INTERNAL_ENDPOINTS", "false").lower() == "true"
    if data_url:
        parts = urlsplit(data_url)
        if not parts.hostname or parts.scheme not in {"http", "https"}:
            errors.append("SCENARA_DATA_PLATFORM_URL must be an absolute HTTP(S) URL")
        elif parts.scheme != "https" and not allow_insecure:
            errors.append("SCENARA_DATA_PLATFORM_URL must use HTTPS unless internal HTTP is explicitly allowed")

    for name in (
        "SCENARA_OCR_ENGINE_FACTORY",
        "SCENARA_BEHAVIOR_ENGINE_FACTORY",
        "SCENARA_FASHION_ENGINE_FACTORY",
    ):
        value = values.get(name, "").strip()
        if value and not FACTORY.fullmatch(value):
            errors.append(f"{name} must use module.path:factory_name")
        if value.startswith("scenara.domains."):
            errors.append(f"{name} cannot use an unqualified built-in reference adapter")

    hosts = [item.strip() for item in values.get("SCENARA_ALLOWED_HOSTS", "").split(",") if item.strip()]
    if not hosts or "*" in hosts:
        errors.append("SCENARA_ALLOWED_HOSTS must explicitly list every accepted Host header")

    forwarded = values.get("SCENARA_FORWARDED_ALLOW_IPS", values.get("FORWARDED_ALLOW_IPS", "")).strip()
    if forwarded == "*":
        errors.append("SCENARA_FORWARDED_ALLOW_IPS cannot trust every proxy")

    if values.get("SCENARA_AUTH_REQUIRED", "true").lower() != "true":
        errors.append("SCENARA_AUTH_REQUIRED must be true")
    if values.get("SCENARA_PRODUCTION_MODELS_REQUIRED", "true").lower() != "true":
        errors.append("SCENARA_PRODUCTION_MODELS_REQUIRED must be true")
    if values.get("SCENARA_S3_VERIFY_TLS", "true").lower() != "true":
        warnings.append("S3 TLS verification is disabled; this is acceptable only for an isolated in-cluster endpoint")

    max_media, media_error = _positive_int(values, "SCENARA_MAX_MEDIA_BYTES", 20 * 1024 * 1024 * 1024)
    max_multipart, multipart_error = _positive_int(
        values, "SCENARA_MAX_MULTIPART_UPLOAD_BYTES", 512 * 1024 * 1024
    )
    for error in (media_error, multipart_error):
        if error:
            errors.append(error)
    if max_media is not None and max_multipart is not None and max_multipart > max_media:
        errors.append("SCENARA_MAX_MULTIPART_UPLOAD_BYTES cannot exceed SCENARA_MAX_MEDIA_BYTES")

    pool_min, pool_min_error = _positive_int(values, "SCENARA_POSTGRES_POOL_MIN_SIZE", 1)
    pool_max, pool_max_error = _positive_int(values, "SCENARA_POSTGRES_POOL_MAX_SIZE", 4)
    for error in (pool_min_error, pool_max_error):
        if error:
            errors.append(error)
    if pool_min is not None and pool_max is not None and pool_max < pool_min:
        errors.append("SCENARA_POSTGRES_POOL_MAX_SIZE must be at least SCENARA_POSTGRES_POOL_MIN_SIZE")

    image = values.get("SCENARA_IMAGE_REFERENCE", "").strip()
    if image and not PLACEHOLDER.search(image) and not SHA256_IMAGE.fullmatch(image):
        errors.append("SCENARA_IMAGE_REFERENCE must pin the application image by sha256 digest")

    bind = values.get("SCENARA_BIND_ADDRESS", "127.0.0.1").strip()
    if bind not in {"127.0.0.1", "::1"} and values.get("SCENARA_ALLOW_DIRECT_HTTP", "false").lower() != "true":
        errors.append("non-loopback HTTP binding requires SCENARA_ALLOW_DIRECT_HTTP=true and an external TLS boundary")

    try:
        retention = [
            int(values.get("SCENARA_RAW_MEDIA_RETENTION_DAYS", "7")),
            int(values.get("SCENARA_PREVIEW_RETENTION_DAYS", "30")),
            int(values.get("SCENARA_STRUCTURED_RESULT_RETENTION_DAYS", "180")),
        ]
        if retention != sorted(retention):
            errors.append("retention periods must satisfy raw <= preview <= structured result")
    except ValueError:
        errors.append("retention periods must be integers")
    return errors, warnings


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate Scenara production configuration without printing secrets")
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--runtime", action="store_true", help="validate the current process environment")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()
    if bool(args.env_file) == bool(args.runtime):
        parser.error("choose exactly one of --env-file or --runtime")
    parse_errors: list[str] = []
    if args.env_file:
        values, parse_errors = parse_env_file(args.env_file)
    else:
        values = dict(os.environ)
    errors, warnings = validate(values, file_mode=bool(args.env_file))
    errors = [*parse_errors, *errors]
    result = {"schema_version": "1.0", "valid": not errors, "errors": errors, "warnings": warnings}
    if not args.quiet or errors:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if not errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
