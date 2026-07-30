from __future__ import annotations

from scenara.domains.portrait.analysis import (
    PORTRAIT_CAPABILITIES,
    PortraitAnalysisBackend,
    PortraitFullAnalysisOperator,
)
from scenara.domains.portrait.operators import PortraitPersonDetectionOperator
from scenara.platform.models import PipelineStatus
from scenara.platform.pipeline import Operator, PipelineDefinition, PipelineNode
from scenara.platform.plugins import DomainManifest


class PortraitPlugin:
    manifest = DomainManifest(
        domain_id="portrait",
        display_name="人像",
        schema_version="1.0",
        console_route="/portrait",
        capabilities=tuple(sorted(PORTRAIT_CAPABILITIES)),
    )

    def __init__(self, backend: PortraitAnalysisBackend | None = None) -> None:
        self._backend = backend

    def operators(self) -> tuple[Operator, ...]:
        return (
            PortraitPersonDetectionOperator(),
            PortraitFullAnalysisOperator(self._backend),
        )

    def pipelines(self) -> tuple[PipelineDefinition, ...]:
        decode = PipelineNode(
            node_id="decode",
            operator_id="platform.media.decode",
            inputs={"media": "$media.input"},
        )
        return (
            PipelineDefinition(
                pipeline_id="portrait.person-detection",
                version="0.1.0",
                domain="portrait",
                status=PipelineStatus.ACTIVE,
                nodes=[
                    decode,
                    PipelineNode(
                        node_id="detect",
                        operator_id="portrait.person-detection",
                        inputs={"batch": "decode.batch"},
                    ),
                ],
                output="detect.result",
                allowed_parameters={"confidence", "iou", "max_detections", "max_units", "sample_interval_ms"},
                pausable=True,
            ),
            PipelineDefinition(
                pipeline_id="portrait.analysis",
                version="0.4.0",
                domain="portrait",
                status=PipelineStatus.ACTIVE,
                nodes=[
                    decode.model_copy(deep=True),
                    PipelineNode(
                        node_id="analyze",
                        operator_id="portrait.full-analysis",
                        inputs={"batch": "decode.batch"},
                    ),
                ],
                output="analyze.result",
                allowed_parameters={"capabilities", "max_units", "sample_interval_ms"},
                pausable=True,
            ),
        )
