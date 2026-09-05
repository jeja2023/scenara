"""长期轨迹仓储的跨后端契约。

内存与 PostgreSQL 两套实现必须在段落检索和可达性探针上给出同一语义，否则
开发环境通过、生产环境行为漂移。可达性探针尤其关键：它决定 tracklet 归并到
既有身份还是新建身份，语义偏差会直接表现为身份碎片化。
"""

from __future__ import annotations

import time
from uuid import uuid4

from scenara.domains.portrait.trajectory import (
    LongTermIdentity,
    ReachabilityProbe,
    TrajectoryRepository,
    TrajectorySegment,
)


def _segment(
    identity_id: str,
    tenant_id: str,
    project_id: str,
    camera_id: str,
    window: tuple[float, float],
) -> TrajectorySegment:
    return TrajectorySegment(
        segment_id=f"lts_{uuid4().hex}",
        identity_id=identity_id,
        tenant_id=tenant_id,
        project_id=project_id,
        run_id=f"run_{uuid4().hex[:12]}",
        camera_id=camera_id,
        first_seen_at=window[0],
        last_seen_at=window[1],
        created_at=time.time(),
    )


async def assert_trajectory_repository_contract(
    repository: TrajectoryRepository,
    *,
    tenant_id: str,
    project_id: str,
) -> None:
    """跑完整套契约；任一后端不满足即抛 AssertionError。"""

    now = time.time()
    identity_id = f"lti_{uuid4().hex}"
    await repository.put_identity(
        LongTermIdentity(
            identity_id=identity_id,
            tenant_id=tenant_id,
            project_id=project_id,
            display_name=identity_id,
            first_seen_at=now,
            last_seen_at=now,
            created_at=now,
            updated_at=now,
        )
    )

    def make(camera_id: str, window: tuple[float, float]) -> TrajectorySegment:
        return _segment(identity_id, tenant_id, project_id, camera_id, window)

    async def probe(camera_id: str, window: tuple[float, float]) -> ReachabilityProbe:
        return await repository.probe_reachability(
            tenant_id,
            project_id,
            identity_id=identity_id,
            camera_id=camera_id,
            window=window,
        )

    # 空身份没有任何邻域约束。
    empty = await probe("camera-c", (300.0, 310.0))
    assert empty.overlapping is False
    assert empty.previous is None and empty.following is None

    # 前驱按 last_seen_at 取最近，而不是按 first_seen_at。
    long_span = make("camera-a", (100.0, 250.0))
    late_start = make("camera-b", (200.0, 210.0))
    await repository.put_segment(long_span)
    await repository.put_segment(late_start)
    ahead = await probe("camera-c", (300.0, 310.0))
    assert ahead.overlapping is False
    assert ahead.previous is not None
    assert ahead.previous.camera_id == "camera-a"
    assert ahead.previous.last_seen_at == 250.0
    assert ahead.following is None

    # 后继按 first_seen_at 取最近，而不是按 last_seen_at。
    await repository.put_segment(make("camera-d", (400.0, 500.0)))
    await repository.put_segment(make("camera-e", (420.0, 430.0)))
    around = await probe("camera-c", (300.0, 310.0))
    assert around.following is not None
    assert around.following.camera_id == "camera-d"
    assert around.following.first_seen_at == 400.0

    # 紧邻观测落在本次机位时同样要返回，判定层据此识别“未发生转移”。
    await repository.put_segment(make("camera-c", (280.0, 290.0)))
    same_camera = await probe("camera-c", (300.0, 310.0))
    assert same_camera.previous is not None
    assert same_camera.previous.camera_id == "camera-c"
    assert same_camera.previous.last_seen_at == 290.0

    # 边界相等归入重叠，不落进前驱或后继。
    boundary_identity = f"lti_{uuid4().hex}"
    await repository.put_segment(
        _segment(boundary_identity, tenant_id, project_id, "camera-a", (200.0, 300.0))
    )
    boundary = await repository.probe_reachability(
        tenant_id,
        project_id,
        identity_id=boundary_identity,
        camera_id="camera-b",
        window=(300.0, 310.0),
    )
    assert boundary.overlapping is True
    assert boundary.previous is None and boundary.following is None

    # 同一机位内的时间重叠不是时空冲突，由 tracklet 归属规则处理。
    same_camera_identity = f"lti_{uuid4().hex}"
    await repository.put_segment(
        _segment(same_camera_identity, tenant_id, project_id, "camera-b", (300.0, 320.0))
    )
    tolerated = await repository.probe_reachability(
        tenant_id,
        project_id,
        identity_id=same_camera_identity,
        camera_id="camera-b",
        window=(310.0, 330.0),
    )
    assert tolerated.overlapping is False
    assert tolerated.previous is None and tolerated.following is None

    # 历史长度不得影响探针结果：旧实现只取前 200 条，超出后判定即失真。
    crowded_identity = f"lti_{uuid4().hex}"
    for index in range(205):
        await repository.put_segment(
            _segment(
                crowded_identity,
                tenant_id,
                project_id,
                "camera-a",
                (float(index * 10), float(index * 10 + 5)),
            )
        )
    await repository.put_segment(
        _segment(crowded_identity, tenant_id, project_id, "camera-b", (2_100.0, 2_110.0))
    )
    crowded = await repository.probe_reachability(
        tenant_id,
        project_id,
        identity_id=crowded_identity,
        camera_id="camera-c",
        window=(2_200.0, 2_210.0),
    )
    assert crowded.overlapping is False
    assert crowded.previous is not None
    assert crowded.previous.camera_id == "camera-b"
    assert crowded.previous.last_seen_at == 2_110.0


__all__ = ["assert_trajectory_repository_contract"]
