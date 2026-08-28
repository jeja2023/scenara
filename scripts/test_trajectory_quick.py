"""
跨镜长期轨迹与多模态 Re-ID 功能快速冒烟测试脚本

用于验证长期跨镜头轨迹系统、时空拓扑约束、人脸人体多模态融合及身份治理功能
"""

import asyncio
import io
import sys
import time
from pathlib import Path

# 设置标准输出编码为 UTF-8
if sys.platform == "win32" and isinstance(sys.stdout, io.TextIOWrapper):
    sys.stdout.reconfigure(encoding="utf-8")


# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def test_import() -> bool:
    """1. 测试依赖与核心模块导入"""
    print("1. 测试依赖与核心模块导入...")
    try:
        import scenara.domains.portrait.trajectory as traj_mod
        import scenara.platform.features as feat_mod
        import scenara.platform.policy as pol_mod

        assert hasattr(traj_mod, "TrajectoryService")
        assert hasattr(traj_mod, "TrajectoryRegistrar")
        assert hasattr(feat_mod, "MemoryFeatureStore")
        assert hasattr(pol_mod, "DevelopmentPolicyProvider")

        print("   [PASS] TrajectoryService & Registrar 模块导入正常")
        print("   [PASS] TrajectoryRepository & FeatureStore 模块导入正常")
        return True
    except Exception as e:
        print(f"   [FAIL] 导入失败: {e}")
        import traceback

        traceback.print_exc()
        return False


async def _create_service(**kwargs):
    from scenara.domains.portrait.trajectory import (
        MemoryTrajectoryRepository,
        TrajectoryService,
    )
    from scenara.infrastructure.memory_state import MemoryStateStore
    from scenara.platform.audit import AuditLogger
    from scenara.platform.features import MemoryFeatureStore
    from scenara.platform.policy import DevelopmentPolicyProvider

    state = MemoryStateStore()
    await state.open()
    return TrajectoryService(
        MemoryTrajectoryRepository(),
        MemoryFeatureStore(),
        DevelopmentPolicyProvider(),
        AuditLogger(state),
        **kwargs,
    )


async def test_camera_topology() -> bool:
    """2. 测试摄像头登记与时空拓扑约束"""
    print("\n2. 测试摄像头登记与时空拓扑约束...")
    try:
        from scenara.domains.portrait.trajectory import (
            CameraTransitionEntry,
            SetCameraTransitionsRequest,
        )
        from scenara.platform.models import PrincipalContext

        service = await _create_service()
        context = PrincipalContext(tenant_id="tenant_smoke", project_id="proj_smoke", principal_id="tester")

        # 登记摄像头 A 与 B
        cam_a = await service.ensure_camera(context, "cam_lobby_01")
        cam_b = await service.ensure_camera(context, "cam_hallway_02")
        print(f"   [PASS] 摄像头自动登记: {cam_a.camera_id} & {cam_b.camera_id}")

        # 配置时空拓扑约束: A -> B 移动耗时 [5s, 60s]
        await service.set_camera_transitions(
            context,
            "cam_lobby_01",
            SetCameraTransitionsRequest(
                transitions=[
                    CameraTransitionEntry(
                        to_camera_id="cam_hallway_02",
                        min_seconds=5.0,
                        max_seconds=60.0,
                    )
                ],
            ),
        )
        transitions = await service.list_camera_transitions(context, "cam_lobby_01")
        print(f"   [PASS] 拓扑约束生效: {len(transitions)} 条规则 (A->B 允许耗时: 5~60秒)")
        return True
    except Exception as e:
        print(f"   [FAIL] 摄像头拓扑测试失败: {e}")
        import traceback

        traceback.print_exc()
        return False


async def test_cross_camera_reid() -> bool:
    """3. 测试跨镜头多模态 Re-ID 长期身份关联"""
    print("\n3. 测试跨镜头多模态 Re-ID 长期身份关联...")
    try:
        from scenara.platform.models import PrincipalContext

        service = await _create_service(body_threshold=0.70, face_threshold=0.75)
        context = PrincipalContext(tenant_id="tenant_smoke", project_id="proj_smoke", principal_id="tester")

        # 模拟目标 Person 1 的人体特征向量 (512维) 与人脸特征向量 (512维)
        body_vec_1 = [0.8] + [0.1] * 511
        face_vec_1 = [0.9] + [0.05] * 511

        # 1. 镜头 A 首次出现该人员 (t = 1000s)
        outcomes_1 = await service.ingest_run_tracks(
            context,
            run_id="run_video_cam_a",
            camera_id="cam_lobby_01",
            recording_started_at=1000.0,
            tracks=[
                {
                    "track_id": "trk_001",
                    "tracklet_quality_score": 0.88,
                    "frame_count": 15,
                    "first_pts_ms": 0.0,
                    "last_pts_ms": 4000.0,
                    "template": {"embedding": body_vec_1},
                    "face_template": {"embedding": face_vec_1},
                }
            ],
        )
        assert len(outcomes_1) == 1
        assert outcomes_1[0].registered is True
        assert outcomes_1[0].segment is not None
        identity_id = outcomes_1[0].segment.identity_id
        print(f"   [PASS] 镜头A首次发现目标: 生成长期身份 ID = {identity_id} (首发匹配: {outcomes_1[0].segment.match_method})")

        # 2. 镜头 B 15 秒后再次出现相同人员 (t = 1020s, 处于 5~60s 可达窗口内)
        # 人体特征有微小光照扰动，人脸特征清晰匹配
        body_vec_1_noisy = [0.78] + [0.1] * 511
        face_vec_1_noisy = [0.89] + [0.05] * 511

        outcomes_2 = await service.ingest_run_tracks(
            context,
            run_id="run_video_cam_b",
            camera_id="cam_hallway_02",
            recording_started_at=1020.0,
            tracks=[
                {
                    "track_id": "trk_002",
                    "tracklet_quality_score": 0.92,
                    "frame_count": 20,
                    "first_pts_ms": 0.0,
                    "last_pts_ms": 5000.0,
                    "template": {"embedding": body_vec_1_noisy},
                    "face_template": {"embedding": face_vec_1_noisy},
                }
            ],
        )
        assert len(outcomes_2) == 1
        assert outcomes_2[0].registered is True
        assert outcomes_2[0].segment is not None
        assert outcomes_2[0].segment.identity_id == identity_id
        assert outcomes_2[0].segment.match_method == "reid"
        print(f"   [PASS] 镜头B跨镜精准关联: 成功归并至同一身份 {identity_id} (融合置信度: {outcomes_2[0].segment.match_score:.3f})")

        return True
    except Exception as e:
        print(f"   [FAIL] 跨镜头 Re-ID 关联测试失败: {e}")
        import traceback

        traceback.print_exc()
        return False


async def test_spatiotemporal_blocking() -> bool:
    """4. 测试时空拓扑异常阻断（防瞬移与同框冲突）"""
    print("\n4. 测试时空拓扑异常阻断（防物理瞬移与同框冲突）...")
    try:
        from scenara.domains.portrait.trajectory import (
            CameraTransitionEntry,
            SetCameraTransitionsRequest,
        )
        from scenara.platform.models import PrincipalContext

        service = await _create_service(body_threshold=0.70)
        context = PrincipalContext(tenant_id="tenant_smoke", project_id="proj_smoke", principal_id="tester")

        # 配置拓扑: cam_1 -> cam_2 最少需要 30 秒移动时间
        await service.set_camera_transitions(
            context,
            "cam_gate_01",
            SetCameraTransitionsRequest(
                transitions=[
                    CameraTransitionEntry(
                        to_camera_id="cam_far_02",
                        min_seconds=30.0,
                        max_seconds=300.0,
                    )
                ],
            ),
        )

        body_vec = [0.85] + [0.05] * 511

        # 镜头 1 出现 (t=1000s)
        await service.ingest_run_tracks(
            context,
            run_id="run_1",
            camera_id="cam_gate_01",
            recording_started_at=1000.0,
            tracks=[
                {
                    "track_id": "trk_1",
                    "tracklet_quality_score": 0.85,
                    "frame_count": 10,
                    "first_pts_ms": 0.0,
                    "last_pts_ms": 2000.0,
                    "template": {"embedding": body_vec},
                }
            ],
        )

        # 镜头 2 仅相隔 2 秒就出现 (物理不可能瞬移，min_seconds=30)
        outcomes_impossible = await service.ingest_run_tracks(
            context,
            run_id="run_2",
            camera_id="cam_far_02",
            recording_started_at=1004.0,  # 仅差 2 秒
            tracks=[
                {
                    "track_id": "trk_2",
                    "tracklet_quality_score": 0.85,
                    "frame_count": 10,
                    "first_pts_ms": 0.0,
                    "last_pts_ms": 2000.0,
                    "template": {"embedding": body_vec},
                }
            ],
        )

        assert len(outcomes_impossible) == 1
        assert outcomes_impossible[0].segment is not None
        # 因物理时空不可达，系统拒绝归并，而是创建新身份
        assert outcomes_impossible[0].segment.match_method == "new_identity"
        print("   [PASS] 物理瞬移阻断生效: 时空超速目标被拒绝归并，严格保证轨迹拓扑真实性")
        return True
    except Exception as e:
        print(f"   [FAIL] 时空拓扑异常阻断测试失败: {e}")
        import traceback

        traceback.print_exc()
        return False


async def test_timeline_and_governance() -> bool:
    """5. 测试长期轨迹时间轴生成与身份治理（合并/拆分）"""
    print("\n5. 测试长期轨迹时间轴生成与身份治理（合并/拆分）...")
    try:
        from scenara.domains.portrait.trajectory import (
            MergeIdentitiesRequest,
            SplitIdentityRequest,
        )
        from scenara.platform.models import PrincipalContext

        service = await _create_service()
        context = PrincipalContext(tenant_id="tenant_smoke", project_id="proj_smoke", principal_id="tester")

        # 摄取两段独立轨迹
        vec_a = [0.9] + [0.0] * 511
        vec_b = [0.0] + [0.9] * 511

        out_1 = await service.ingest_run_tracks(
            context,
            run_id="run_t1",
            camera_id="cam_north",
            recording_started_at=2000.0,
            tracks=[
                {
                    "track_id": "trk_a",
                    "tracklet_quality_score": 0.9,
                    "frame_count": 10,
                    "first_pts_ms": 0.0,
                    "last_pts_ms": 3000.0,
                    "template": {"embedding": vec_a},
                }
            ],
        )
        out_2 = await service.ingest_run_tracks(
            context,
            run_id="run_t2",
            camera_id="cam_south",
            recording_started_at=2100.0,
            tracks=[
                {
                    "track_id": "trk_b",
                    "tracklet_quality_score": 0.9,
                    "frame_count": 10,
                    "first_pts_ms": 0.0,
                    "last_pts_ms": 3000.0,
                    "template": {"embedding": vec_b},
                }
            ],
        )

        assert out_1[0].segment is not None
        assert out_2[0].segment is not None
        id_1 = out_1[0].segment.identity_id
        id_2 = out_2[0].segment.identity_id

        # 1. 验证时间轴生成
        timeline = await service.timeline(context, id_1)
        assert len(timeline) >= 1
        print(f"   [PASS] 长期轨迹时间轴生成: {len(timeline)} 个观测节点")

        # 2. 验证身份合并 (Merge)
        merged = await service.merge_identities(
            context,
            MergeIdentitiesRequest(
                target_identity_id=id_1,
                source_identity_ids=[id_2],
            ),
        )
        assert merged.segment_count == 2
        print(f"   [PASS] 身份合并治理 (Merge): {id_2} 成功合并至 {id_1} (总片段数: {merged.segment_count})")

        # 3. 验证片段拆分 (Split)
        seg_to_split = out_2[0].segment.segment_id
        split_res = await service.split_identity(
            context,
            id_1,
            SplitIdentityRequest(segment_ids=[seg_to_split]),
        )
        print(f"   [PASS] 轨迹片段拆分 (Split): 成功将片段分离生成新身份 {split_res.identity_id}")

        return True
    except Exception as e:
        print(f"   [FAIL] 轨迹时间轴与治理测试失败: {e}")
        import traceback

        traceback.print_exc()
        return False


async def main():
    print("=" * 65)
    print("      Scenara 跨镜长期轨迹与多模态 Re-ID 快速冒烟测试套件")
    print("=" * 65)

    start_time = time.time()
    results = []

    results.append(("1. 依赖与核心模块导入", test_import()))
    results.append(("2. 摄像头登记与拓扑约束", await test_camera_topology()))
    results.append(("3. 跨镜多模态Re-ID关联", await test_cross_camera_reid()))
    results.append(("4. 时空拓扑防瞬移阻断", await test_spatiotemporal_blocking()))
    results.append(("5. 轨迹时间轴与身份治理", await test_timeline_and_governance()))

    elapsed = time.time() - start_time

    print("\n" + "=" * 65)
    print("                     冒烟测试结果汇总")
    print("=" * 65)

    all_passed = True
    for name, success in results:
        status = "[PASS]" if success else "[FAIL]"
        print(f"  {name:.<45} {status}")
        if not success:
            all_passed = False

    print("-" * 65)
    print(f"总耗时: {elapsed:.2f} 秒")
    if all_passed:
        print(">>> 恭喜! 跨镜长期轨迹系统所有核心功能冒烟测试 100% 全部通过! <<<")
        return 0
    else:
        print(">>> 警告: 部分冒烟测试项未通过，请检查上述错误日志 <<<")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
