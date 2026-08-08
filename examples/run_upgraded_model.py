"""升级版 EDQSG 的手工输入示例。

示例数值仅用于说明接口，不代表任何真实系统结论。
"""

import json

from edqsg import (
    BottomLineTrigger,
    CouplingCalibrationInput,
    Domain,
    EDQSGConfig,
    EDQSGModel,
    Evidence,
    EvidenceType,
    GovernanceTemplate,
    Indicator,
    RedundancyAnalyzer,
    TaskLayer,
)


def evidence(eid, etype, source, beliefs, unknown, reliability, description):
    return Evidence(
        evidence_id=eid,
        evidence_type=etype,
        source=source,
        coverage=reliability[0],
        authority=reliability[1],
        timeliness=reliability[2],
        repeatability=reliability[3],
        business_fit=reliability[4],
        belief_degrees=beliefs,
        unknown_degree=unknown,
        description=description,
        importance=1.0,
    )


cfg = EDQSGConfig()
model = EDQSGModel(cfg)
indicators = [
    Indicator(
        "DQ4",
        "唯一性",
        Domain.DATA_QUALITY,
        evidences=(
            evidence(
                "E-DQ4-DATA", EvidenceType.DATA, "器材主数据全量扫描",
                (0.0, 0.1, 0.3, 0.5, 0.0), 0.1,
                (1.0, 0.9, 1.0, 1.0, 1.0),
                "发现同物多码和重复业务对象。",
            ),
            evidence(
                "E-DQ4-EXPERT", EvidenceType.EXPERT, "业务专家复核",
                (0.0, 0.1, 0.4, 0.3, 0.0), 0.2,
                (0.8, 0.9, 0.9, 0.8, 1.0),
                "确认多个编码实际指向同一器材。",
            ),
        ),
    ),
    Indicator(
        "SG3",
        "键与约束完整性",
        Domain.STRUCTURAL_GOVERNANCE,
        evidences=(
            evidence(
                "E-SG3-DDL", EvidenceType.STRUCTURE, "数据库DDL审查",
                (0.0, 0.0, 0.2, 0.6, 0.1), 0.1,
                (1.0, 1.0, 1.0, 1.0, 1.0),
                "核心表缺少业务唯一约束。",
            ),
        ),
    ),
]

calibrations = [
    CouplingCalibrationInput(
        dq_indicator_id="DQ4",
        sg_indicator_id="SG3",
        normative_strength=0.95,
        expert_strength=0.90,
        data_strength=0.75,
        normative_confidence=0.95,
        expert_confidence=0.85,
        data_confidence=0.75,
        evidence_ids=("STD-UNIQUE", "DELPHI-01", "HISTORY-01"),
    )
]

templates = [
    GovernanceTemplate(
        template_id="TPL-SG3",
        sg_indicator_id="SG3",
        bottom_line_rule_id=None,
        target_object="器材主数据表及业务唯一约束",
        root_cause="核心业务对象缺少统一唯一约束和单一权威来源",
        lifecycle_stage="数据创建与维护",
        measures=(
            "制定器材业务唯一键规则",
            "清理历史重复与同物多码记录",
            "增加数据库唯一约束或等效服务校验",
            "治理后重新计算业务对象唯一率",
        ),
        actors=("业务数据所有者", "主数据管理员", "DBA"),
        acceptance_metrics={
            "新增重复编码拦截率": "100%",
            "同物多码率": "低于项目约定阈值",
        },
        task_layer=TaskLayer.STRUCTURE_GOVERNANCE,
        severity=0.9,
        impact=0.95,
        urgency=0.9,
        cost=0.6,
        dependency=0.2,
    )
]

redundancy = RedundancyAnalyzer(
    cfg.field_similarity_weights,
    cfg.table_similarity_weights,
    cfg.redundancy_risk_weights,
    cfg.redundancy_risk_thresholds,
).assess_table(
    left_object="equipment_base_a",
    right_object="equipment_base_b",
    features=(0.9, 0.9, 0.8, 0.9, 0.2, 0.8),
    necessity=0.1,
    conflict=0.8,
    update_independence=0.9,
    sync_control=0.2,
    impact=0.9,
    evidence_ids=("DDL-A-B", "DATA-OVERLAP-A-B"),
)

report = model.evaluate(
    indicators=indicators,
    dq_weights={"DQ4": 1.0},
    sg_weights={"SG3": 1.0},
    coupling_calibrations=calibrations,
    governance_templates=templates,
    redundancy_results=[redundancy],
    metadata={"case": "manual-upgraded-example"},
)
print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
