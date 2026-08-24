from __future__ import annotations

import argparse
import base64
import os
import secrets
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "deploy" / ".env.production.example"


def _token(bytes_count: int = 32) -> str:
    return secrets.token_urlsafe(bytes_count)


def _fernet_key() -> str:
    return base64.urlsafe_b64encode(os.urandom(32)).decode("ascii")


def render() -> str:
    content = TEMPLATE.read_text(encoding="utf-8")
    replacements = {
        "replace-with-postgres-password": _token(),
        "replace-with-redis-password": _token(),
        "replace-with-minio-root-user": "scenara-root-" + secrets.token_hex(6),
        "replace-with-minio-root-password": _token(),
        "replace-with-s3-access-key": "scenara-app-" + secrets.token_hex(6),
        "replace-with-s3-secret-key": _token(),
        "replace-with-core-to-data-service-token": _token(),
        "replace-with-data-to-core-service-token": _token(),
        "replace-with-long-random-bootstrap-token": _token(48),
        "replace-with-generated-fernet-key": _fernet_key(),
        "replace-with-admin-password-16chars": _token(24),
    }
    for placeholder, value in replacements.items():
        content = content.replace(placeholder, value)
    return content


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a production env candidate with independent random secrets")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists():
        raise SystemExit(f"refusing to overwrite existing file: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render(), encoding="utf-8", newline="\n")
    if os.name != "nt":
        output.chmod(0o600)
    print(f"created {output}; fill external endpoints, image digest, allowed hosts, and approved model factories")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
