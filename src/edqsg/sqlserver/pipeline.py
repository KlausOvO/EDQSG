"""[CORE] SQL Server数据库采集到EDQSG模型、图表与报告的一体化流水线。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..config import EDQSGConfig
from ..core import EDQSGModel

from .adapter import QueryExecutor, SQLServerAdapter
from .analyzer import SQLServerEvidenceBuilder
from .config import SQLServerAssessmentConfig
from .metadata import SQLServerMetadataCollector
from .profiler import SQLServerProfiler
from .reporting import SQLServerPipelineResult


class SQLServerAssessmentPipeline:
    """自动执行连接测试、元数据采集、数据剖析、证据构建和EDQSG评价。"""

    def __init__(
        self,
        config: SQLServerAssessmentConfig,
        *,
        executor: QueryExecutor | None = None,
        model_config: EDQSGConfig | None = None,
    ):
        config.validate()
        self.config = config
        self.executor = executor or SQLServerAdapter(
            config.database, read_uncommitted=config.scan.read_uncommitted
        )
        self.model_config = model_config or EDQSGConfig()
        self.model = EDQSGModel(self.model_config)

    @classmethod
    def from_file(
        cls,
        path: str | Path,
        *,
        executor: QueryExecutor | None = None,
        model_config: EDQSGConfig | None = None,
    ) -> "SQLServerAssessmentPipeline":
        return cls(
            SQLServerAssessmentConfig.from_file(path),
            executor=executor,
            model_config=model_config,
        )

    def run(self) -> SQLServerPipelineResult:
        connection_info: dict[str, Any] = {}
        if hasattr(self.executor, "test_connection"):
            connection_info = getattr(self.executor, "test_connection")()

        metadata = SQLServerMetadataCollector(
            self.executor, self.config.scan
        ).collect()
        profile = SQLServerProfiler(
            self.executor,
            metadata,
            self.config.scan,
            self.config.rules,
        ).profile()
        builder = SQLServerEvidenceBuilder(
            metadata,
            profile,
            self.config.scan,
            self.config.rules,
            self.model_config,
        )
        redundancy = builder.build_redundancy_results()
        indicators = builder.build_indicators(redundancy)
        triggers = builder.build_bottom_line_triggers()
        calibrations = builder.build_coupling_calibrations()
        templates = builder.build_governance_templates(triggers)
        default_dq, default_sg = builder.default_weights()
        dq_weights = self.config.dq_weights or default_dq
        sg_weights = self.config.sg_weights or default_sg

        calibrated_relations = self.model.coupling_calibrator.calibrate_many(calibrations)
        report = self.model.evaluate(
            indicators=indicators,
            dq_weights=dq_weights,
            sg_weights=sg_weights,
            coupling_calibrations=calibrations,
            bottom_line_triggers=triggers,
            governance_templates=templates,
            redundancy_results=redundancy,
            metadata={
                "source": "sqlserver",
                "server": connection_info.get("server_name", metadata.server_name),
                "database": metadata.database_name,
                "product_version": metadata.product_version,
                "edition": metadata.edition,
                "profile_mode": profile.mode,
                "table_count": len(metadata.tables),
                "foreign_key_count": len(metadata.foreign_keys),
                "logical_foreign_key_rule_count": len(profile.logical_foreign_keys),
                "relationship_control_rule_count": len(profile.relationship_controls),
                "relationship_without_trusted_physical_fk_count": sum(
                    not item.physical_fk_trusted for item in profile.relationship_controls
                ),
                "approved_alternative_relationship_control_count": sum(
                    (not item.physical_fk_trusted) and item.exception_governance_score >= 0.8
                    for item in profile.relationship_controls
                ),
                "master_data_consistency_rule_count": len(profile.master_data_consistency),
                "supplemental_evidence_count": len(self.config.rules.supplemental_evidence),
                "profiling_issue_count": len(profile.issues),
                "indicator_weights": {**dq_weights, **sg_weights},
                "configuration_note": (
                    "未配置业务规则的指标可能使用弱代理证据或中性基础分；"
                    "未定义物理外键不等同于结构缺陷，应结合预期关系、替代控制、"
                    "受控例外和实际孤儿率判断；低分还应结合可信度和未知度解释。"
                ),
            },
        )
        robustness = None
        if self.config.visualization.generate_robustness:
            robustness = self.model.robustness(
                indicators=indicators,
                dq_weights=dq_weights,
                sg_weights=sg_weights,
                coupling_relations=calibrated_relations,
                bottom_line_triggers=triggers,
                governance_templates=templates,
                redundancy_results=redundancy,
                iterations=self.config.visualization.robustness_iterations,
                perturbation=self.config.visualization.robustness_perturbation,
            )
        return SQLServerPipelineResult(report, metadata, profile, robustness)

    def run_and_export(self, output_dir: str | Path | None = None) -> SQLServerPipelineResult:
        result = self.run()
        directory = Path(output_dir or self.config.output_dir)
        directory.mkdir(parents=True, exist_ok=True)
        result.export_json(directory / "edqsg_sqlserver_report.json")
        result.export_markdown(directory / "edqsg_sqlserver_report.md")
        result.export_html(directory / "edqsg_sqlserver_report.html")
        if self.config.visualization.enabled:
            figure_dir = directory / "figures"
            artifacts = result.export_figures(figure_dir, self.config.visualization)
            # 图形清单便于论文写作时核对图号、含义与文件名。
            import json
            manifest = [
                {
                    "figure_id": item.figure_id,
                    "title": item.title,
                    "description": item.description,
                    "files": list(item.files),
                }
                for item in artifacts
            ]
            (figure_dir / "figure_manifest.json").write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            if self.config.visualization.generate_dashboard:
                result.export_dashboard(artifacts, directory / "edqsg_dashboard.html")
        return result

    def close(self) -> None:
        if hasattr(self.executor, "dispose"):
            getattr(self.executor, "dispose")()
