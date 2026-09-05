"""集成测试的租户与项目隔离辅助。

轨迹、布控等领域表都以 (tenant_id, project_id) 外键挂在 scenara_projects 上，
每个测试用独立作用域，才能在同一个数据库上反复运行而互不干扰。
"""

from __future__ import annotations

import os
import time
from uuid import uuid4

from scenara.domains.portrait.service import PortraitIdentity
from scenara.domains.portrait.trajectory import CameraRecord
from scenara.infrastructure.postgres_access import PostgresAccessRepository
from scenara.infrastructure.postgres_features import PostgresFeatureStore
from scenara.infrastructure.postgres_portrait import PostgresPortraitRepository
from scenara.infrastructure.postgres_trajectory import PostgresTrajectoryRepository
from scenara.infrastructure.postgres_state import PostgresStateStore
from scenara.platform.features import DistanceMetric, FeatureRecord, FeatureSpace
from scenara.platform.models import MediaSource, Organization, Project

POSTGRES_DSN = os.getenv(
    "SCENARA_INTEGRATION_POSTGRES_DSN",
    "postgresql://scenara:scenara-integration@127.0.0.1:55432/scenara",
)


async def create_isolated_scope(state: PostgresStateStore, prefix: str) -> tuple[str, str]:
    """建立一个新的租户与项目，返回可直接写入领域表的作用域。"""

    tenant_id = f"{prefix}_{uuid4().hex[:24]}"
    project_id = "qualification"
    now = time.time()
    access = PostgresAccessRepository(state.pool)
    await access.create_organization(
        Organization(
            tenant_id=tenant_id,
            display_name=f"{prefix} integration",
            created_at=now,
            updated_at=now,
        )
    )
    await access.create_project(
        Project(
            tenant_id=tenant_id,
            project_id=project_id,
            display_name="Qualification",
            created_at=now,
            updated_at=now,
        )
    )
    return tenant_id, project_id


async def create_portrait_identities(
    state: PostgresStateStore, tenant_id: str, project_id: str, count: int
) -> list[str]:
    """登记若干人像身份，供以外键引用它们的领域表使用。"""

    repository = PostgresPortraitRepository(state.pool)
    now = time.time()
    identity_ids: list[str] = []
    for index in range(count):
        identity_id = f"pid_{uuid4().hex}"
        await repository.create_identity(
            PortraitIdentity(
                identity_id=identity_id,
                tenant_id=tenant_id,
                project_id=project_id,
                display_name=f"契约身份 {index + 1}",
                created_at=now,
                updated_at=now,
            )
        )
        identity_ids.append(identity_id)
    return identity_ids


async def create_binding_targets(
    state: PostgresStateStore, tenant_id: str, project_id: str
) -> tuple[str, str]:
    """登记布控任务绑定所需的媒体来源与点位，返回 (source_id, camera_id)。"""

    now = time.time()
    source_id = f"src_{uuid4().hex}"
    camera_id = f"camera-{uuid4().hex[:20]}"
    await state.create_source(
        MediaSource(
            source_id=source_id,
            tenant_id=tenant_id,
            project_id=project_id,
            name="契约视频源",
            masked_url="rtsp://***",
            secret_ref=f"secret://tests/{source_id}",
            created_at=now,
        )
    )
    await PostgresTrajectoryRepository(state.pool).put_camera(
        CameraRecord(
            camera_id=camera_id,
            tenant_id=tenant_id,
            project_id=project_id,
            display_name="契约点位",
            created_at=now,
            updated_at=now,
        )
    )
    return source_id, camera_id


async def create_feature(
    state: PostgresStateStore, tenant_id: str, project_id: str, subject_id: str
) -> tuple[str, str]:
    """登记一个特征空间与一条特征，返回 (feature_id, feature_space_id)。"""

    store = PostgresFeatureStore(state.pool)
    marker = uuid4().hex[:12]
    feature_space_id = f"portrait.face.contract.{marker}"
    feature_id = f"feat_{uuid4().hex}"
    # scenara_feature_spaces 对 (domain, modality, model_id, model_version, dimension,
    # distance_metric) 唯一，模型标识必须随空间一起随机化才能重复运行。
    await store.create_space(
        FeatureSpace(
            feature_space_id=feature_space_id,
            domain="portrait",
            modality="face",
            model_id=f"contract-face-{marker}",
            model_version="1.0.0",
            dimension=2,
            distance_metric=DistanceMetric.COSINE,
            threshold=0.8,
        )
    )
    await store.add(
        FeatureRecord(
            feature_id=feature_id,
            tenant_id=tenant_id,
            project_id=project_id,
            feature_space_id=feature_space_id,
            subject_type="portrait_identity",
            subject_id=subject_id,
            embedding=[1.0, 0.0],
            created_at=time.time(),
        )
    )
    return feature_id, feature_space_id


__all__ = [
    "POSTGRES_DSN",
    "create_binding_targets",
    "create_feature",
    "create_isolated_scope",
    "create_portrait_identities",
]
