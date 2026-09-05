"""人像身份仓储的跨后端契约。

身份与注册记录是布控名单、轨迹身份和检索的共同锚点。删除身份时注册记录是否
一并消失、按特征标识反查是否命中，两种后端必须一致。
"""

from __future__ import annotations

import time
from uuid import uuid4

from scenara.domains.portrait.service import (
    PortraitEnrollment,
    PortraitIdentity,
    PortraitRepository,
)


async def assert_portrait_repository_contract(
    repository: PortraitRepository,
    *,
    tenant_id: str,
    project_id: str,
    feature_id: str | None = None,
    feature_space_id: str = "portrait.face.contract.v1",
) -> None:
    """跑完整套契约；任一后端不满足即抛 AssertionError。

    PostgreSQL 的注册表以外键指向 scenara_features，调用方需要传入已登记的特征
    标识与所属特征空间；内存实现不做该约束，缺省时自动生成。
    """

    now = time.time()
    identity_id = f"pid_{uuid4().hex}"
    identity = await repository.create_identity(
        PortraitIdentity(
            identity_id=identity_id,
            tenant_id=tenant_id,
            project_id=project_id,
            display_name="契约身份",
            metadata={"source": "contract"},
            created_at=now,
            updated_at=now,
        )
    )
    assert identity.identity_id == identity_id

    stored = await repository.get_identity(tenant_id, project_id, identity_id)
    assert stored is not None
    assert stored.display_name == "契约身份"
    assert stored.metadata == {"source": "contract"}
    assert identity_id in {
        item.identity_id for item in await repository.list_identities(tenant_id, project_id)
    }

    # 跨租户不可见。
    assert await repository.get_identity(f"{tenant_id}-other", project_id, identity_id) is None

    feature_id = feature_id or f"feat_{uuid4().hex}"
    enrollment = await repository.create_enrollment(
        PortraitEnrollment(
            enrollment_id=f"enr_{uuid4().hex}",
            tenant_id=tenant_id,
            project_id=project_id,
            identity_id=identity_id,
            feature_id=feature_id,
            feature_space_id=feature_space_id,
            modality="face",
            quality=0.93,
            created_at=now,
        )
    )
    by_feature = await repository.get_enrollment_by_feature(tenant_id, project_id, feature_id)
    assert by_feature is not None
    assert by_feature.enrollment_id == enrollment.enrollment_id
    assert by_feature.quality == 0.93
    assert await repository.get_enrollment_by_feature(
        tenant_id, project_id, f"feat_{uuid4().hex}"
    ) is None
    listed = await repository.list_enrollments(tenant_id, project_id, identity_id)
    assert [item.feature_id for item in listed] == [feature_id]

    # 删除身份连带清理其注册记录，避免残留指向已删身份的特征。
    assert await repository.delete_identity(tenant_id, project_id, identity_id) is True
    assert await repository.get_identity(tenant_id, project_id, identity_id) is None
    assert await repository.list_enrollments(tenant_id, project_id, identity_id) == []
    assert await repository.delete_identity(tenant_id, project_id, identity_id) is False


__all__ = ["assert_portrait_repository_contract"]
