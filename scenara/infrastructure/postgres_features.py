from __future__ import annotations

from typing import Any

from scenara.platform.features import (
    FeatureMatch,
    FeatureRecord,
    FeatureSpace,
    FeatureStoreError,
    normalize_embedding,
)


def _vector(values: list[float]) -> Any:
    try:
        from pgvector import Vector
    except ImportError as exc:  # pragma: no cover - production dependency
        raise RuntimeError("pgvector is required for the PostgreSQL feature store") from exc
    return Vector(values)


class PostgresFeatureStore:
    def __init__(self, pool: Any) -> None:
        self._pool = pool

    async def create_space(self, space: FeatureSpace) -> FeatureSpace:
        async with self._pool.connection() as conn:
            await conn.execute(
                """INSERT INTO scenara_feature_spaces
                (feature_space_id, domain, modality, model_id, model_version, dimension, distance_metric, threshold)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (feature_space_id) DO NOTHING""",
                (
                    space.feature_space_id,
                    space.domain,
                    space.modality,
                    space.model_id,
                    space.model_version,
                    space.dimension,
                    space.distance_metric,
                    space.threshold,
                ),
            )
        stored = await self.get_space(space.feature_space_id)
        if stored is None or stored.model_dump(exclude={"created_at"}) != space.model_dump(exclude={"created_at"}):
            raise FeatureStoreError("feature space conflicts with an existing contract")
        return stored

    async def get_space(self, feature_space_id: str) -> FeatureSpace | None:
        async with self._pool.connection() as conn:
            cursor = await conn.execute(
                """SELECT feature_space_id, domain, modality, model_id, model_version, dimension,
                   distance_metric, threshold, extract(epoch from created_at) FROM scenara_feature_spaces
                   WHERE feature_space_id = %s""",
                (feature_space_id,),
            )
            row = await cursor.fetchone()
        if row is None:
            return None
        return FeatureSpace(
            feature_space_id=row[0],
            domain=row[1],
            modality=row[2],
            model_id=row[3],
            model_version=row[4],
            dimension=row[5],
            distance_metric=row[6],
            threshold=row[7],
            created_at=row[8],
        )

    async def add(self, feature: FeatureRecord) -> FeatureRecord:
        space = await self.get_space(feature.feature_space_id)
        if space is None:
            raise FeatureStoreError("feature does not match its feature space")
        embedding = _vector(normalize_embedding(feature.embedding, space.dimension))
        async with self._pool.connection() as conn:
            await conn.execute(
                """INSERT INTO scenara_features
                (tenant_id, project_id, feature_id, feature_space_id, subject_type, subject_id, embedding, created_at, expires_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, to_timestamp(%s), to_timestamp(%s))""",
                (
                    feature.tenant_id,
                    feature.project_id,
                    feature.feature_id,
                    feature.feature_space_id,
                    feature.subject_type,
                    feature.subject_id,
                    embedding,
                    feature.created_at,
                    feature.expires_at,
                ),
            )
        return feature.model_copy(deep=True)

    async def search(
        self,
        tenant_id: str,
        project_id: str,
        feature_space_id: str,
        embedding: list[float],
        *,
        limit: int,
        threshold: float | None = None,
    ) -> list[FeatureMatch]:
        if not 1 <= limit <= 1000:
            raise FeatureStoreError("feature search limit must be between 1 and 1000")
        space = await self.get_space(feature_space_id)
        if space is None:
            raise FeatureStoreError("query does not match its feature space")
        query = _vector(normalize_embedding(embedding, space.dimension))
        cutoff = space.threshold if threshold is None else threshold
        operators = {"cosine": "<=>", "l2": "<->", "inner_product": "<#>"}
        operator = operators[space.distance_metric]
        async with self._pool.connection() as conn:
            cursor = await conn.execute(
                f"""SELECT feature_id, subject_type, subject_id, embedding {operator} %s::vector AS distance
                FROM scenara_features WHERE tenant_id = %s AND project_id = %s AND feature_space_id = %s
                AND (expires_at IS NULL OR expires_at > now()) ORDER BY distance ASC LIMIT %s""",
                (query, tenant_id, project_id, feature_space_id, limit),
            )
            rows = await cursor.fetchall()
        matches = []
        for row in rows:
            distance = float(row[3])
            score = (
                -distance
                if space.distance_metric == "inner_product"
                else 1.0 - distance
                if space.distance_metric == "cosine"
                else 1.0 / (1.0 + distance)
            )
            if cutoff is None or score >= cutoff:
                matches.append(
                    FeatureMatch(
                        feature_id=row[0], subject_type=row[1], subject_id=row[2], score=score, distance=distance
                    )
                )
        return matches

    async def delete_subject(self, tenant_id: str, project_id: str, subject_type: str, subject_id: str) -> int:
        async with self._pool.connection() as conn:
            cursor = await conn.execute(
                "DELETE FROM scenara_features WHERE tenant_id = %s AND project_id = %s AND subject_type = %s AND subject_id = %s",
                (tenant_id, project_id, subject_type, subject_id),
            )
        return int(cursor.rowcount)

    async def delete_expired(self, before: float, limit: int) -> int:
        if not 1 <= limit <= 10_000:
            raise FeatureStoreError("feature retention limit must be between 1 and 10000")
        async with self._pool.connection() as conn, conn.transaction():
            cursor = await conn.execute(
                """DELETE FROM scenara_features WHERE ctid IN (
                       SELECT ctid FROM scenara_features
                       WHERE expires_at IS NOT NULL AND expires_at <= to_timestamp(%s)
                       ORDER BY expires_at, feature_id LIMIT %s
                   )""",
                (before, limit),
            )
        return int(cursor.rowcount)


__all__ = ["PostgresFeatureStore"]
