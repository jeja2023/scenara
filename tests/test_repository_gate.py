from __future__ import annotations

import base64
from pathlib import Path

from scripts.repository_gate import has_possible_secret, is_scannable_text


def test_repository_gate_scans_environment_examples_and_rejects_usable_secrets() -> None:
    assert is_scannable_text(Path("deploy/.env.production.example"))
    insecure_fernet_key = base64.urlsafe_b64encode(b"0" * 32).decode("ascii")
    assert has_possible_secret(f"SCENARA_SECRET_ENCRYPTION_KEY={insecure_fernet_key}")
    assert has_possible_secret("SCENARA_API_TOKEN=" + "a-real-looking-production-token-12345")
    assert has_possible_secret("SCENARA_API_TOKEN=" + "test-production-token-that-must-not-pass")
    assert not has_possible_secret("SCENARA_API_TOKEN=replace-with-long-random-api-token")
