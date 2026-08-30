"""Run a non-destructive PostgreSQL schema and MinIO recovery drill locally.

Unlike the Docker deployment drill, this script only requires a locally
reachable PostgreSQL database, the native ``pg_dump`` / ``pg_restore`` tools,
and an S3-compatible endpoint.  It creates one temporary schema, verifies a
backup/restore cycle, verifies a MinIO object round-trip, writes a JSON report,
then removes all temporary resources.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import psycopg
from dotenv import dotenv_values


ROOT = Path(__file__).resolve().parents[1]


def _tool(name: str) -> Path:
    executable = f"{name}.exe" if __import__("os").name == "nt" else name
    candidates = [
        *sorted(Path("C:/Program Files/PostgreSQL").glob(f"*/bin/{executable}"), reverse=True),
        *sorted(Path("/usr/bin").glob(executable)),
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise RuntimeError(f"native {name} executable was not found")


def _version(tool: Path) -> str:
    return subprocess.check_output([str(tool), "--version"], text=True, encoding="utf-8").strip()


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the local native PostgreSQL/MinIO recovery drill")
    parser.add_argument("--env-file", type=Path, default=ROOT / ".env")
    parser.add_argument("--output", type=Path, default=ROOT / "runtime-state" / "local-native-backup-restore.json")
    args = parser.parse_args()

    values = dotenv_values(args.env_file)
    dsn = values.get("SCENARA_POSTGRES_DSN")
    endpoint = values.get("SCENARA_S3_ENDPOINT_URL")
    bucket = values.get("SCENARA_S3_BUCKET")
    region = values.get("SCENARA_S3_REGION") or "us-east-1"
    access_key = values.get("SCENARA_S3_ACCESS_KEY")
    secret_key = values.get("SCENARA_S3_SECRET_KEY")
    if not all(isinstance(item, str) and item for item in (dsn, endpoint, bucket, access_key, secret_key)):
        raise RuntimeError("env file must define PostgreSQL and S3 connection values")

    pg_dump = _tool("pg_dump")
    pg_restore = _tool("pg_restore")
    started = time.perf_counter()
    schema = f"qualification_backup_{uuid4().hex[:16]}"
    marker = f"marker-{uuid4().hex}"
    work_dir = Path(tempfile.mkdtemp(prefix="scenara-native-backup-"))
    dump_path = work_dir / "postgres.dump"
    copied_path = work_dir / "object.bin"
    object_key = f"qualification/native-backup/{uuid4().hex}.bin"
    object_payload = b"scenara-native-backup-restore-qualification"
    object_deleted = False
    report: dict[str, object] = {
        "schema_version": "1.0",
        "status": "failed",
        "executed_at": _utc_now(),
        "postgres": {"pg_dump": _version(pg_dump), "pg_restore": _version(pg_restore)},
        "object_store": {"endpoint": endpoint, "bucket": bucket},
    }

    try:
        with psycopg.connect(dsn, autocommit=True) as connection:
            connection.execute(f'CREATE SCHEMA "{schema}"')
            connection.execute(f'CREATE TABLE "{schema}".qualification_marker (value text PRIMARY KEY)')
            connection.execute(f'INSERT INTO "{schema}".qualification_marker VALUES (%s)', (marker,))

        subprocess.run(
            [str(pg_dump), f"--dbname={dsn}", "--format=custom", f"--schema={schema}", f"--file={dump_path}"],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        if not dump_path.is_file() or dump_path.stat().st_size == 0:
            raise RuntimeError("pg_dump did not create a non-empty backup")

        with psycopg.connect(dsn, autocommit=True) as connection:
            connection.execute(f'DROP SCHEMA "{schema}" CASCADE')
            connection.execute(f'CREATE SCHEMA "{schema}"')

        restored = subprocess.run(
            [str(pg_restore), f"--dbname={dsn}", f"--schema={schema}", "--exit-on-error", str(dump_path)],
            check=False,
            text=True,
            encoding="utf-8",
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        if restored.returncode:
            raise RuntimeError(f"pg_restore failed: {restored.stderr[-1000:]}")
        with psycopg.connect(dsn) as connection:
            row = connection.execute(f'SELECT value FROM "{schema}".qualification_marker').fetchone()
            if row is None or row[0] != marker:
                raise RuntimeError("restored PostgreSQL marker does not match")

        import boto3

        client = boto3.client(
            "s3",
            endpoint_url=endpoint,
            region_name=region,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            verify=False,
        )
        client.put_object(Bucket=bucket, Key=object_key, Body=object_payload)
        client.download_file(bucket, object_key, str(copied_path))
        if hashlib.sha256(copied_path.read_bytes()).digest() != hashlib.sha256(object_payload).digest():
            raise RuntimeError("restored MinIO object checksum does not match")
        client.delete_object(Bucket=bucket, Key=object_key)
        object_deleted = True

        report.update(
            {
                "status": "passed",
                "duration_seconds": round(time.perf_counter() - started, 3),
                "postgres": {
                    **report["postgres"],
                    "schema_backup_sha256": hashlib.sha256(dump_path.read_bytes()).hexdigest(),
                    "schema_restored": True,
                },
                "object_store": {**report["object_store"], "sha256_verified": True},
            }
        )
    except Exception as exc:
        report.update({"error": str(exc), "duration_seconds": round(time.perf_counter() - started, 3)})
        raise
    finally:
        try:
            with psycopg.connect(dsn, autocommit=True) as connection:
                connection.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
        finally:
            if not object_deleted:
                try:
                    import boto3

                    boto3.client(
                        "s3",
                        endpoint_url=endpoint,
                        region_name=region,
                        aws_access_key_id=access_key,
                        aws_secret_access_key=secret_key,
                        verify=False,
                    ).delete_object(Bucket=bucket, Key=object_key)
                except Exception:
                    pass
            shutil.rmtree(work_dir, ignore_errors=True)
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(json.dumps(report, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
