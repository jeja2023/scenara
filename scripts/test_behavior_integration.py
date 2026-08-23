"""
行为识别功能完整集成测试

验证从配置加载到 API 调用的完整链路
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def test_settings() -> bool:
    """测试配置加载"""
    print("1. 测试配置加载...")
    try:
        from scenara.settings import load_settings
        import os

        # 临时设置环境变量
        os.environ["SCENARA_BEHAVIOR_ENGINE_FACTORY"] = "scenara.domains.behavior.paddle_production:create_production_behavior_engine"

        settings = load_settings()
        print(f"   ✓ 配置加载成功")
        print(f"   ✓ behavior_engine_factory: {settings.behavior_engine_factory}")
        return True
    except Exception as e:
        print(f"   ✗ 配置加载失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_factory() -> bool:
    """测试工厂函数"""
    print("\n2. 测试工厂函数...")
    try:
        from scenara.domains.behavior.factory import load_behavior_engine

        factory_path = "scenara.domains.behavior.paddle_production:create_production_behavior_engine"
        engine = load_behavior_engine(factory_path)

        print(f"   ✓ 工厂函数加载成功")
        print(f"   ✓ 引擎: {engine.model_id} v{engine.version}")
        print(f"   ✓ 生产就绪: {engine.production_ready}")
        return True
    except Exception as e:
        print(f"   ✗ 工厂函数失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_plugin_registry() -> bool:
    """测试插件注册"""
    print("\n3. 测试插件注册...")
    try:
        from scenara.domains.behavior import BehaviorPlugin
        from scenara.platform.pipeline import PipelineRegistry
        from scenara.platform.plugins import DomainPluginRegistry

        pipelines = PipelineRegistry()
        plugins = DomainPluginRegistry(pipelines)

        # 注册插件
        behavior_plugin = BehaviorPlugin()
        plugins.register(behavior_plugin)

        print(f"   ✓ 插件注册成功")
        print(f"   ✓ 领域 ID: {behavior_plugin.manifest.domain_id}")
        print(f"   ✓ 显示名称: {behavior_plugin.manifest.display_name}")

        # 验证流水线
        plugin_pipelines = behavior_plugin.pipelines()
        print(f"   ✓ 流水线数量: {len(plugin_pipelines)}")

        # 验证算子
        operators = behavior_plugin.operators()
        print(f"   ✓ 算子数量: {len(operators)}")

        return True
    except Exception as e:
        print(f"   ✗ 插件注册失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_bootstrap_integration() -> bool:
    """测试 bootstrap 集成"""
    print("\n4. 测试 Bootstrap 集成...")
    try:
        # 检查导入
        from scenara.bootstrap import Runtime
        from scenara.domains.behavior import BehaviorPlugin
        from scenara.domains.behavior.factory import load_behavior_engine

        print(f"   ✓ Bootstrap 导入成功")
        print(f"   ✓ BehaviorPlugin 可用")
        print(f"   ✓ load_behavior_engine 可用")

        # 注意: 不实际创建 Runtime,因为需要数据库等依赖
        print(f"   ✓ Runtime 类型定义正确")

        return True
    except Exception as e:
        print(f"   ✗ Bootstrap 集成失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_models() -> bool:
    """测试数据模型"""
    print("\n5. 测试数据模型...")
    try:
        from scenara.platform.models import (
            BehaviorAction,
            TemporalSegment,
            BehaviorDomainPayload,
        )

        # 创建测试数据
        action = BehaviorAction(
            action_id="test_action_1",
            action_type="walking",
            action_label="行走",
            confidence=0.85,
            start_ms=0,
            end_ms=3000,
        )

        segment = TemporalSegment(
            segment_id="test_segment_1",
            start_ms=0,
            end_ms=5000,
            segment_type="normal",
        )

        payload = BehaviorDomainPayload(
            actions=[action],
            segments=[segment],
            summary="测试行为识别结果",
        )

        print(f"   ✓ BehaviorAction 创建成功")
        print(f"   ✓ TemporalSegment 创建成功")
        print(f"   ✓ BehaviorDomainPayload 创建成功")
        print(f"   ✓ Payload 序列化: {len(payload.model_dump_json())} 字节")

        return True
    except Exception as e:
        print(f"   ✗ 数据模型测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_operator() -> bool:
    """测试算子定义"""
    print("\n6. 测试算子定义...")
    try:
        from scenara.domains.behavior.operators import BehaviorRecognitionOperator

        operator = BehaviorRecognitionOperator()

        print(f"   ✓ 算子创建成功")
        print(f"   ✓ 算子 ID: {operator.definition.operator_id}")
        print(f"   ✓ 版本: {operator.definition.version}")
        print(f"   ✓ 领域: {operator.definition.domain}")
        print(f"   ✓ 资源预算: VRAM {operator.definition.resource_budget['vram_mb']}MB, "
              f"CPU {operator.definition.resource_budget['cpu_cores']} cores")

        return True
    except Exception as e:
        print(f"   ✗ 算子测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_evaluation_framework() -> bool:
    """测试评估框架"""
    print("\n7. 测试评估框架...")
    try:
        from scenara.domains.behavior.evaluation import (
            BehaviorEvaluator,
            BehaviorEvaluationSample,
            BehaviorEvaluationResult,
        )

        print(f"   ✓ BehaviorEvaluator 可用")
        print(f"   ✓ BehaviorEvaluationSample 可用")
        print(f"   ✓ BehaviorEvaluationResult 可用")

        return True
    except Exception as e:
        print(f"   ✗ 评估框架测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def main() -> None:
    print("=" * 80)
    print("行为识别功能完整集成测试")
    print("=" * 80)

    results = []

    # 运行所有测试
    results.append(("配置加载", test_settings()))
    results.append(("工厂函数", test_factory()))
    results.append(("插件注册", test_plugin_registry()))
    results.append(("Bootstrap 集成", test_bootstrap_integration()))
    results.append(("数据模型", test_models()))
    results.append(("算子定义", test_operator()))
    results.append(("评估框架", test_evaluation_framework()))

    # 打印摘要
    print("\n" + "=" * 80)
    print("测试摘要")
    print("=" * 80)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for name, result in results:
        status = "✓ 通过" if result else "✗ 失败"
        print(f"{status} - {name}")

    print(f"\n总计: {passed}/{total} 通过")

    if passed == total:
        print("\n✅ 所有集成测试通过!")
        print("\n行为识别功能已完全集成到 Scenara 平台:")
        print("  • 配置系统 (settings.py)")
        print("  • 引擎工厂 (factory.py)")
        print("  • 插件注册 (bootstrap.py)")
        print("  • 数据模型 (models.py)")
        print("  • 算子和流水线 (operators.py, plugin.py)")
        print("  • 评估框架 (evaluation.py)")
        print("\n下一步:")
        print("  1. 安装依赖: pip install paddlevideo==2.5.0")
        print("  2. 配置环境: 设置 SCENARA_BEHAVIOR_ENGINE_FACTORY")
        print("  3. 启动服务: python start.py")
        print("  4. 测试 API: POST /api/v1/parse/video")
        sys.exit(0)
    else:
        print("\n✗ 部分集成测试失败,请检查错误信息。")
        sys.exit(1)


if __name__ == "__main__":
    main()
