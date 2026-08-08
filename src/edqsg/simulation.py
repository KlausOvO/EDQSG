"""仅用于程序边界验证的可重复模拟数据工厂。

模拟结果不得作为论文实证结论。
"""

from __future__ import annotations

import random

import numpy as np

from .models import (
    CouplingCalibrationInput,
    Domain,
    Evidence,
    EvidenceType,
    GovernanceTemplate,
    Indicator,
    TaskLayer,
)

DQ_NAMES = ["完整性", "准确性", "规范性", "唯一性", "一致性", "关联完整性", "时效性", "可追溯性"]
SG_NAMES = ["字段设计", "表模型", "键与约束", "表间关系", "字段冗余", "表冗余", "主数据权威", "生命周期与互操作"]


class SimulationFactory:
    def __init__(self, seed: int = 123):
        self.np_rng = np.random.default_rng(seed)
        self.py_rng = random.Random(seed)

    def indicators(self) -> list[Indicator]:
        result: list[Indicator] = []
        for domain, names in (
            (Domain.DATA_QUALITY, DQ_NAMES),
            (Domain.STRUCTURAL_GOVERNANCE, SG_NAMES),
        ):
            for index, name in enumerate(names, start=1):
                evidences = []
                for e_index in range(2):
                    evidences.append(
                        Evidence(
                            evidence_id=f"E-{domain.value}{index}-{e_index+1}",
                            evidence_type=self.py_rng.choice(list(EvidenceType)),
                            source="simulation",
                            coverage=float(self.np_rng.uniform(0.65, 1.0)),
                            authority=float(self.np_rng.uniform(0.65, 1.0)),
                            timeliness=float(self.np_rng.uniform(0.60, 1.0)),
                            repeatability=float(self.np_rng.uniform(0.65, 1.0)),
                            business_fit=float(self.np_rng.uniform(0.70, 1.0)),
                            observed_score=float(self.np_rng.uniform(45.0, 95.0)),
                            importance=float(self.np_rng.uniform(0.75, 1.0)),
                        )
                    )
                result.append(
                    Indicator(
                        indicator_id=f"{domain.value}{index}",
                        name=name,
                        domain=domain,
                        evidences=tuple(evidences),
                    )
                )
        return result

    @staticmethod
    def equal_weights(prefix: str, count: int = 8) -> dict[str, float]:
        return {f"{prefix}{i}": 1 / count for i in range(1, count + 1)}

    def coupling_calibrations(self) -> list[CouplingCalibrationInput]:
        result = []
        for dq in range(1, 9):
            for sg in range(1, 9):
                result.append(
                    CouplingCalibrationInput(
                        dq_indicator_id=f"DQ{dq}",
                        sg_indicator_id=f"SG{sg}",
                        normative_strength=float(self.np_rng.uniform(0.05, 0.95)),
                        expert_strength=float(self.np_rng.uniform(0.05, 0.95)),
                        data_strength=float(self.np_rng.uniform(0.05, 0.95)),
                        normative_confidence=0.90,
                        expert_confidence=0.80,
                        data_confidence=0.75,
                    )
                )
        return result

    @staticmethod
    def governance_templates() -> list[GovernanceTemplate]:
        return [
            GovernanceTemplate(
                template_id=f"TPL-SG{i}",
                sg_indicator_id=f"SG{i}",
                bottom_line_rule_id=None,
                target_object=name,
                root_cause=f"{name}存在缺陷或控制不足",
                lifecycle_stage="设计与运维",
                measures=("核查证据", "制定整改规则", "实施整改并复评"),
                actors=("业务数据所有者", "数据管理员", "DBA"),
                acceptance_metrics={"关联质量指标改善": ">=10%"},
                task_layer=TaskLayer.STRUCTURE_GOVERNANCE,
                severity=0.8,
                impact=0.8,
                urgency=0.7,
                cost=0.5,
                dependency=0.2,
            )
            for i, name in enumerate(SG_NAMES, start=1)
        ]
