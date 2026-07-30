from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = (
    "LICENSE",
    "NOTICE",
    "PROVENANCE.md",
    "source-manifest.json",
    "MODEL_ASSETS.md",
    "SECURITY.md",
    "THIRD_PARTY_NOTICES.md",
    "docs/openapi.json",
)
FORBIDDEN_TRACKED = (".env", "runtime-state/", "node_modules/")
LEGACY_PUBLIC_PATTERN = re.compile(r"(?i)portrait[_ -]?hub|vision[_ -]?hub|PORTRAIT_HUB_|景析")
LEGACY_PUBLIC_ALLOWLIST = {
    "NOTICE",
    "PROVENANCE.md",
    "README.md",
    "source-manifest.json",
    "docs/adr/0001-platform-domain-boundaries.md",
    "docs/release/IMPLEMENTATION_MATRIX.md",
    "docs/release/PORTRAIT_HUB_CAPABILITY_MATRIX.md",
    "docs/adr/0003-chinese-brand-jingshu.md",
    "CHANGELOG.md",
    "scripts/repository_gate.py",
    "Scenara 景枢全面优化升级方案.md",
}
SECRET_PATTERNS = (
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"(?i)(?:api[_-]?key|secret[_-]?key|password)\s*[:=]\s*['\"]?[A-Za-z0-9+/=_-]{24,}"),
)
TEXT_SUFFIXES = {".py", ".ts", ".vue", ".js", ".json", ".yml", ".yaml", ".md", ".txt", ".toml", ".sql", ".env"}
ALLOWED_MODEL_SUFFIXES = (".governance.yml", ".labels.txt", ".model-card.yml")
SHA256 = re.compile(r"^[0-9a-f]{64}$")


def repository_files() -> list[str]:
    output = subprocess.check_output(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=ROOT,
    )
    return [item.decode("utf-8") for item in output.split(b"\0") if item]


def main() -> None:
    errors: list[str] = []
    for name in REQUIRED:
        if not (ROOT / name).is_file():
            errors.append(f"missing required release file: {name}")
    manifest = json.loads((ROOT / "source-manifest.json").read_text(encoding="utf-8"))
    if manifest.get("history_imported") is not False or not manifest.get("source_commit"):
        errors.append("source-manifest.json must record a source commit and history_imported=false")
    for name in repository_files():
        normalized = name.replace("\\", "/")
        if normalized == FORBIDDEN_TRACKED[0] or normalized.startswith(FORBIDDEN_TRACKED[1:]):
            errors.append(f"forbidden tracked path: {name}")
            continue
        if normalized.startswith("models/") and not normalized.endswith(ALLOWED_MODEL_SUFFIXES):
            errors.append(f"model artifact must not be tracked: {name}")
            continue
        path = ROOT / name
        if path.suffix.lower() not in TEXT_SUFFIXES or not path.is_file() or path.stat().st_size > 2_000_000:
            continue
        value = path.read_text(encoding="utf-8", errors="ignore")
        if any(pattern.search(value) for pattern in SECRET_PATTERNS):
            errors.append(f"possible secret in tracked file: {name}")
        if (
            LEGACY_PUBLIC_PATTERN.search(value)
            and not normalized.startswith(("app/", "models/"))
            and normalized not in LEGACY_PUBLIC_ALLOWLIST
        ):
            errors.append(f"legacy product identifier in public Scenara surface: {name}")
    for card in sorted((ROOT / "models").glob("*.model-card.yml")):
        document = yaml.safe_load(card.read_text(encoding="utf-8"))
        artifact = document.get("model", {}).get("artifact", {}) if isinstance(document, dict) else {}
        if not SHA256.fullmatch(str(artifact.get("sha256", ""))):
            errors.append(f"model card has no valid artifact SHA-256: {card.name}")
        governance = card.with_name(card.name.replace(".model-card.yml", ".governance.yml"))
        if not governance.is_file():
            errors.append(f"model card has no governance record: {card.name}")
    for governance in sorted((ROOT / "models").glob("*.governance.yml")):
        card = governance.with_name(governance.name.replace(".governance.yml", ".model-card.yml"))
        if not card.is_file():
            errors.append(f"governance record has no model card: {governance.name}")
    if errors:
        raise SystemExit("\n".join(errors))


if __name__ == "__main__":
    main()
