from __future__ import annotations

from scenara.domains.portrait.operators import PortraitPersonDetectionOperator
from scenara.platform.models import PipelineStatus
from scenara.platform.pipeline import PipelineDefinition, PipelineNode
from scenara.platform.plugins import DomainManifest


class PortraitPlugin:
    manifest = DomainManifest(
        domain_id="portrait",
        display_name="Portrait",
        schema_version="1.0",
        console_route="/portrait",
        capabilities=("person_detection",),
    )

    def operators(self) -> tuple[PortraitPersonDetectionOperator, ...]:
        return (PortraitPersonDetectionOperator(),)

    def pipelines(self) -> tuple[PipelineDefinition, ...]:
        return (
            PipelineDefinition(
                pipeline_id="portrait.person-detection",
                version="0.1.0",
                domain="portrait",
                status=PipelineStatus.ACTIVE,
                nodes=[
                    PipelineNode(
                        node_id="decode",
                        operator_id="platform.media.decode-image",
                        inputs={"data": "$media.bytes"},
                    ),
                    PipelineNode(
                        node_id="detect",
                        operator_id="portrait.person-detection",
                        inputs={"image": "decode.image"},
                    ),
                ],
                output="detect.result",
                allowed_parameters={"confidence", "iou", "max_detections"},
            ),
        )
